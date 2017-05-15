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
import gtest_parallel
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
    test_lib.assertListEqual(expected['execution_number'],
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

  def assertTaskWasExecuted(self, test_id, expected, retries):
    self.logger.assertRecorded(self, test_id, expected, retries)
    self.times.assertRecorded(self,test_id, expected, retries)
    self.test_results.assertRecorded(self,test_id, expected, retries)

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
      expected['execution_number'] = range(retry_failed + 1)
      self.assertTaskWasExecuted(test_id, expected, retry_failed + 1)

    self.assertEqual(len(task_manager.started), 0)
    self.assertListEqual(
        sorted(task.task_id for task in task_manager.passed),
        sorted(task.task_id for task in task_mock_factory.passed))
    self.assertListEqual(
        sorted(task.task_id for task in task_manager.failed),
        sorted(task.task_id for task in task_mock_factory.failed))

    self.assertEqual(task_manager.global_exit_code, 1)


if __name__ == '__main__':
  unittest.main()
