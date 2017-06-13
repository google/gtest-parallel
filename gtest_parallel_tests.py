#!/usr/bin/env python2
# Copyright 2017 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import collections
import contextlib
import gtest_parallel
import os.path
import shutil
import sys
import tempfile
import unittest


class LoggerMock(object):
  def __init__(self):
    self.runtimes = collections.defaultdict(list)
    self.exit_codes = collections.defaultdict(list)
    self.last_execution_times = collections.defaultdict(list)
    self.execution_numbers = collections.defaultdict(list)

  def log_exit(self, task):
    self.runtimes[task.test_id].append(task.runtime_ms)
    self.exit_codes[task.test_id].append(task.exit_code)
    self.last_execution_times[task.test_id].append(task.last_execution_time)
    self.execution_numbers[task.test_id].append(task.execution_number)

  def assertRecorded(self, test_lib, test_id, expected, retries):
    test_lib.assertIn(test_id, self.runtimes)
    test_lib.assertListEqual(expected['runtime_ms'][:retries],
                             self.runtimes[test_id])
    test_lib.assertListEqual(expected['exit_code'][:retries],
                             self.exit_codes[test_id])
    test_lib.assertListEqual(expected['last_execution_time'][:retries],
                             self.last_execution_times[test_id])
    test_lib.assertListEqual(expected['execution_number'][:retries],
                                  self.execution_numbers[test_id])


class TimesMock(object):
  def __init__(self):
    self.last_execution_times = collections.defaultdict(list)

  def record_test_time(self, test_binary, test_name, last_execution_time):
    test_id = (test_binary, test_name)
    self.last_execution_times[test_id].append(last_execution_time)

  def assertRecorded(self, test_lib, test_id, expected, retries):
    test_lib.assertIn(test_id, self.last_execution_times)
    test_lib.assertListEqual(expected['last_execution_time'][:retries],
                             self.last_execution_times[test_id])


class TestResultsMock(object):
  def __init__(self):
    self.results = []

  def log(self, test_name, runtime_ms, actual_result):
    self.results.append((test_name, runtime_ms, actual_result))

  def assertRecorded(self, test_lib, test_id, expected, retries):
    test_results = [
        (test_id[1], runtime_ms, 'PASS' if exit_code == 0 else 'FAIL')
        for runtime_ms, exit_code in zip(expected['runtime_ms'][:retries],
                                         expected['exit_code'][:retries])
    ]
    for test_result in test_results:
      test_lib.assertIn(test_result, self.results)


class TaskMockFactory(object):
  def __init__(self, test_data):
    self.data = test_data
    self.passed = []
    self.failed = []

  def get_task(self, test_id, execution_number=0):
    task = TaskMock(test_id, execution_number, self.data[test_id])
    if task.exit_code == 0:
      self.passed.append(task)
    else:
      self.failed.append(task)
    return task

  def __call__(self, test_binary, test_name, test_command, execution_number,
               last_execution_time, output_dir):
    return self.get_task((test_binary, test_name), execution_number)


class TaskMock(object):
  def __init__(self, test_id, execution_number, test_data):
    self.test_id = test_id
    self.execution_number = execution_number

    self.runtime_ms = test_data['runtime_ms'][execution_number]
    self.exit_code = test_data['exit_code'][execution_number]
    self.last_execution_time = (
        test_data['last_execution_time'][execution_number])
    self.test_command = None
    self.output_dir = None

    self.test_binary = test_id[0]
    self.test_name = test_id[1]
    self.task_id = (test_id[0], test_id[1], execution_number)

  def run(self):
    pass


class TestTaskManager(unittest.TestCase):
  def setUp(self):
    self.passing_task = (
        ('fake_binary', 'Fake.PassingTest'), {
            'runtime_ms': [10],
            'exit_code': [0],
            'last_execution_time': [10],
        })
    self.failing_task = (
        ('fake_binary', 'Fake.FailingTest'), {
            'runtime_ms': [20, 30, 40],
            'exit_code': [1, 1, 1],
            'last_execution_time': [None, None, None],
        })
    self.fails_once_then_succeeds = (
        ('another_binary', 'Fake.Test.FailOnce'), {
            'runtime_ms': [21, 22],
            'exit_code': [1, 0],
            'last_execution_time': [None, 22],
        })
    self.fails_twice_then_succeeds = (
        ('yet_another_binary', 'Fake.Test.FailTwice'), {
            'runtime_ms': [23, 25, 24],
            'exit_code': [1, 1, 0],
            'last_execution_time': [None, None, 24],
        })

  def execute_tasks(self, tasks, retries, expected_exit_code):
    repeat = 1

    times = TimesMock()
    logger = LoggerMock()
    test_results = TestResultsMock()

    task_mock_factory = TaskMockFactory(dict(tasks))
    task_manager = gtest_parallel.TaskManager(
        times, logger, test_results, task_mock_factory, retries, repeat)

    for test_id, expected in tasks:
      task = task_mock_factory.get_task(test_id)
      task_manager.run_task(task)
      expected['execution_number'] = range(len(expected['exit_code']))

      logger.assertRecorded(self, test_id, expected, retries + 1)
      times.assertRecorded(self, test_id, expected, retries + 1)
      test_results.assertRecorded(self,test_id, expected, retries + 1)

    self.assertEqual(len(task_manager.started), 0)
    self.assertListEqual(
        sorted(task.task_id for task in task_manager.passed),
        sorted(task.task_id for task in task_mock_factory.passed))
    self.assertListEqual(
        sorted(task.task_id for task in task_manager.failed),
        sorted(task.task_id for task in task_mock_factory.failed))

    self.assertEqual(task_manager.global_exit_code, expected_exit_code)

  def test_passing_task_succeeds(self):
    self.execute_tasks(tasks=[self.passing_task], retries=0,
                       expected_exit_code=0)

  def test_failing_task_fails(self):
    self.execute_tasks(tasks=[self.failing_task], retries=0,
                       expected_exit_code=1)

  def test_failing_task_fails_even_with_retries(self):
    self.execute_tasks(tasks=[self.failing_task], retries=2,
                       expected_exit_code=1)

  def test_executing_passing_and_failing_fails(self):
    # Executing both a faling test and a passing one should make gtest-parallel
    # fail, no matter if the failing task is run first or last.
    self.execute_tasks(tasks=[self.failing_task, self.passing_task],
                       retries=2, expected_exit_code=1)

    self.execute_tasks(tasks=[self.passing_task, self.failing_task],
                       retries=2, expected_exit_code=1)

  def test_task_succeeds_with_one_retry(self):
    # Executes test and retries once. The first run should fail and the second
    # succeed, so gtest-parallel should succeed.
    self.execute_tasks(tasks=[self.fails_once_then_succeeds],
                       retries=1, expected_exit_code=0)

  def test_task_fails_with_one_retry(self):
    # Executes test and retries once, not enough for the test to start passing,
    # so gtest-parallel should return an error.
    self.execute_tasks(tasks=[self.fails_twice_then_succeeds],
                       retries=1, expected_exit_code=1)

  def test_runner_succeeds_when_all_tasks_eventually_succeeds(self):
    # Executes the test and retries twice. One test should pass in the first
    # attempt, another should take two runs, and the last one should take three
    # runs. All tests should succeed, so gtest-parallel should succeed too.
    self.execute_tasks(tasks=[self.passing_task,
                              self.fails_once_then_succeeds,
                              self.fails_twice_then_succeeds],
                       retries=2, expected_exit_code=0)

@contextlib.contextmanager
def guard_temp_dir():
  try:
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
  finally:
    shutil.rmtree(temp_dir)


@contextlib.contextmanager
def guard_temp_subdir(temp_dir, *path):
  assert path, 'Path should not be empty'

  try:
    temp_subdir = os.path.join(temp_dir, *path)
    os.makedirs(temp_subdir)
    yield temp_subdir
  finally:
    shutil.rmtree(os.path.join(temp_dir, path[0]))


@contextlib.contextmanager
def guard_patch_module(import_name, new_val):
  def patch(module, names, val):
    if len(names) == 1:
      old = getattr(module, names[0])
      setattr(module, names[0], val)
      return old
    else:
      return patch(getattr(module, names[0]), names[1:], val)

  try:
    old_val = patch(gtest_parallel, import_name.split('.'), new_val)
    yield old_val
  finally:
    patch(gtest_parallel, import_name.split('.'), old_val)


class TestSaveFilePath(unittest.TestCase):
  class StreamMock(object):
    def write(*args):
      # Suppress any output.
      pass

  def test_get_save_file_path_unix(self):
    with guard_temp_dir() as temp_dir, \
        guard_patch_module('os.path.expanduser', lambda p: temp_dir), \
        guard_patch_module('sys.stderr', TestSaveFilePath.StreamMock()), \
        guard_patch_module('sys.platform', 'darwin'):
      with guard_patch_module('os.environ', {}), \
          guard_temp_subdir(temp_dir, '.cache'):
        self.assertEqual(os.path.join(temp_dir, '.cache', 'gtest-parallel'),
                         gtest_parallel.get_save_file_path())

      with guard_patch_module('os.environ', {'XDG_CACHE_HOME': temp_dir}):
        self.assertEqual(os.path.join(temp_dir, 'gtest-parallel'),
                         gtest_parallel.get_save_file_path())

      with guard_patch_module('os.environ',
                              {'XDG_CACHE_HOME': os.path.realpath(__file__)}):
        self.assertEqual(os.path.join(temp_dir, '.gtest-parallel-times'),
                         gtest_parallel.get_save_file_path())

  def test_get_save_file_path_win32(self):
    with guard_temp_dir() as temp_dir, \
        guard_patch_module('os.path.expanduser', lambda p: temp_dir), \
        guard_patch_module('sys.stderr', TestSaveFilePath.StreamMock()), \
        guard_patch_module('sys.platform', 'win32'):
      with guard_patch_module('os.environ', {}), \
          guard_temp_subdir(temp_dir, 'AppData', 'Local'):
        self.assertEqual(os.path.join(temp_dir, 'AppData',
                                      'Local', 'gtest-parallel'),
                         gtest_parallel.get_save_file_path())

      with guard_patch_module('os.environ', {'LOCALAPPDATA': temp_dir}):
        self.assertEqual(os.path.join(temp_dir, 'gtest-parallel'),
                         gtest_parallel.get_save_file_path())

      with guard_patch_module('os.environ',
                              {'LOCALAPPDATA': os.path.realpath(__file__)}):
        self.assertEqual(os.path.join(temp_dir, '.gtest-parallel-times'),
                         gtest_parallel.get_save_file_path())


if __name__ == '__main__':
  unittest.main()
