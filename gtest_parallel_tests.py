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

  def assertTaskWasExecuted(self, test_id, expected, retries):
    self.assertIn(test_id, self.logger.runtimes)
    self.assertListEqual(expected['runtime_ms'][:retries+1],
                         self.logger.runtimes[test_id])

    self.assertIn(test_id, self.logger.exit_codes)
    self.assertListEqual(expected['exit_code'][:retries+1],
                         self.logger.exit_codes[test_id])

    self.assertIn(test_id, self.logger.last_execution_times)
    self.assertListEqual(
        expected['last_execution_time'][:retries+1],
        self.logger.last_execution_times[test_id])

    self.assertIn(test_id, self.times.last_execution_times)
    self.assertListEqual(
        expected['last_execution_time'][:retries+1],
        self.times.last_execution_times[test_id])

    num_executions = min(retries + 1, len(expected['exit_code']))
    self.assertIn(test_id, self.logger.execution_numbers)
    self.assertListEqual(range(num_executions),
                         self.logger.execution_numbers[test_id])

    test_results = [
        (test_id[1], runtime_ms, 'PASS' if exit_code == 0 else 'FAIL')
        for runtime_ms, exit_code in zip(expected['runtime_ms'],
                                         expected['exit_code'])[:retries]
    ]
    for test_result in test_results:
      self.assertIn(test_result, self.test_results.results)

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
      self.assertTaskWasExecuted(test_id, expected, retry_failed)

    self.assertEqual(len(task_manager.started), 0)
    self.assertListEqual(
        sorted(task.task_id for task in task_manager.passed),
        sorted(task.task_id for task in task_mock_factory.passed))
    self.assertListEqual(
        sorted(task.task_id for task in task_manager.failed),
        sorted(task.task_id for task in task_mock_factory.failed))

    self.assertEqual(task_manager.global_exit_code, 1)

  def test_run_task_repeat_twice_fails(self):
    repeat = 1
    retry_failed = 2

    task_mock_factory = TaskMockFactory(dict(self.test_data))
    task_manager = gtest_parallel.TaskManager(
        self.times, self.logger, self.test_results,
        task_mock_factory, retry_failed, repeat)

    for test_id, expected in self.test_data:
      task = task_mock_factory.get_task(test_id)
      task_manager.run_task(task)
      self.assertTaskWasExecuted(test_id, expected, retry_failed)

    self.assertEqual(len(task_manager.started), 0)
    self.assertListEqual(
        sorted(task.task_id for task in task_manager.passed),
        sorted(task.task_id for task in task_mock_factory.passed))
    self.assertListEqual(
        sorted(task.task_id for task in task_manager.failed),
        sorted(task.task_id for task in task_mock_factory.failed))

    self.assertEqual(task_manager.global_exit_code, 1)

  def test_run_task_repeat_twice_succeeds(self):
    repeat = 1
    retry_failed = 2

    task_mock_factory = TaskMockFactory(dict(self.test_data))
    task_manager = gtest_parallel.TaskManager(
        self.times, self.logger, self.test_results,
        task_mock_factory, retry_failed, repeat)

    for test_id, expected in self.test_data[:3]:
      task = task_mock_factory.get_task(test_id)
      task_manager.run_task(task)
      self.assertTaskWasExecuted(test_id, expected, retry_failed)

    self.assertEqual(len(task_manager.started), 0)
    self.assertListEqual(
        sorted(task.task_id for task in task_manager.passed),
        sorted(task.task_id for task in task_mock_factory.passed))
    self.assertListEqual(
        sorted(task.task_id for task in task_manager.failed),
        sorted(task.task_id for task in task_mock_factory.failed))

    self.assertEqual(task_manager.global_exit_code, 0)


if __name__ == '__main__':
  unittest.main()
