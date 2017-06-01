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


class TimesMock(object):
  def __init__(self):
    self.last_execution_times = collections.defaultdict(list)

  def record_test_time(self, test_binary, test_name, last_execution_time):
    test_id = (test_binary, test_name)
    self.last_execution_times[test_id].append(last_execution_time)


class TestResultsMock(object):
  def __init__(self):
    self.results = []

  def log(self, test_name, runtime_ms, actual_result):
    self.results.append((test_name, runtime_ms, actual_result))


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
    self.times = TimesMock()
    self.logger = LoggerMock()
    self.test_results = TestResultsMock()

    self.test_data = [
        # Passing task
        (('fake_binary', 'Fake.PassingTest'), {
            'runtime_ms': [10],
            'exit_code': [0],
            'last_execution_time': [10],
        }),
        # Fails once, then succeeds
        (('another_binary', 'Fake.Test.FailOnce'), {
            'runtime_ms': [21, 22],
            'exit_code': [3, 0],
            'last_execution_time': [None, 22],
        }),
        # Fails twice, then succeeds
        (('yet_another_binary', 'Fake.Test.FailTwice'), {
            'runtime_ms': [23, 25, 24],
            'exit_code': [2, 2, 0],
            'last_execution_time': [None, None, 24],
        }),
        # Failing task
        (('fake_binary', 'Fake.FailingTest'), {
            'runtime_ms': [20, 30, 40],
            'exit_code': [1, 1, 1],
            'last_execution_time': [None, None, None],
        })
    ]

  def test_run_task_basic(self):
    repeat = 1
    retry_failed = 0

    task_mock_factory = TaskMockFactory(dict(self.test_data))
    task_manager = gtest_parallel.TaskManager(
        self.times, self.logger, self.test_results,
        task_mock_factory, retry_failed, repeat)

    for test_id, expected in self.test_data:
      task = task_mock_factory.get_task(test_id)
      task_manager.run_task(task)

    self.assertEqual(len(task_manager.started), 0)
    self.assertListEqual(
        sorted(task.task_id for task in task_manager.passed),
        sorted(task.task_id for task in task_mock_factory.passed))
    self.assertListEqual(
        sorted(task.task_id for task in task_manager.failed),
        sorted(task.task_id for task in task_mock_factory.failed))

    self.assertEqual(task_manager.global_exit_code, 1)


@contextlib.contextmanager
def guard_environ(var, val):
  try:
    old_val = os.environ.get(var)
    if val is None:
      if old_val is not None:
        del os.environ[var]
    else:
      os.environ[var] = val
    yield old_val
  finally:
    if old_val is None:
      if val is not None:
        del os.environ[var]
    else:
      os.environ[var] = old_val


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
      with guard_environ('XDG_CACHE_HOME', None), \
          guard_temp_subdir(temp_dir, '.cache'):
        self.assertEqual(os.path.join(temp_dir, '.cache', 'gtest-parallel'),
                         gtest_parallel.get_save_file_path())

      with guard_environ('XDG_CACHE_HOME', temp_dir):
        self.assertEqual(os.path.join(temp_dir, 'gtest-parallel'),
                         gtest_parallel.get_save_file_path())

      with guard_environ('XDG_CACHE_HOME', os.path.realpath(__file__)):
        self.assertEqual(os.path.join(temp_dir, '.gtest-parallel-times'),
                         gtest_parallel.get_save_file_path())

  def test_get_save_file_path_win32(self):
    with guard_temp_dir() as temp_dir, \
        guard_patch_module('os.path.expanduser', lambda p: temp_dir), \
        guard_patch_module('sys.stderr', TestSaveFilePath.StreamMock()), \
        guard_patch_module('sys.platform', 'win32'):
      with guard_environ('LOCALAPPDATA', None), \
          guard_temp_subdir(temp_dir, 'AppData', 'Local'):
        self.assertEqual(os.path.join(temp_dir, 'AppData',
                                      'Local', 'gtest-parallel'),
                         gtest_parallel.get_save_file_path())

      with guard_environ('LOCALAPPDATA', temp_dir):
        self.assertEqual(os.path.join(temp_dir, 'gtest-parallel'),
                         gtest_parallel.get_save_file_path())

      with guard_environ('LOCALAPPDATA', os.path.realpath(__file__)):
        self.assertEqual(os.path.join(temp_dir, '.gtest-parallel-times'),
                         gtest_parallel.get_save_file_path())


if __name__ == '__main__':
  unittest.main()
