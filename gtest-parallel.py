#!/usr/bin/env python2
import Queue
import optparse
import subprocess
import sys
import threading

parser = optparse.OptionParser(
    usage = 'usage: %prog [options] executable [executable ...]')

parser.add_option('-w', '--workers', type='int', default=16,
                  help='number of workers to spawn')
parser.add_option('--gtest_filter', type='string', default='',
                  help='test filter')
parser.add_option('--gtest_also_run_disabled_tests', action='store_true',
                  default=False, help='run disabled tests too')

(options, binaries) = parser.parse_args()

if binaries == []:
  parser.print_usage()
  sys.exit(1)

log = Queue.Queue()
tests = Queue.Queue()

# Find tests.
job_id = 0
for test_binary in binaries:
  command = [test_binary]
  if options.gtest_filter != '':
    command += ['--gtest_filter=' + options.gtest_filter]
  if options.gtest_also_run_disabled_tests:
    command += ['--gtest_also_run_disabled_tests']

  test_list = subprocess.Popen(command + ['--gtest_list_tests'],
                               stdout=subprocess.PIPE).communicate()[0]

  test_group = ''
  for line in test_list.split('\n'):
    if not line.strip():
      continue
    if line[0] != " ":
      test_group = line.strip()
      continue
    line = line.strip()

    # Skip disabled tests unless they should be run
    if not options.gtest_also_run_disabled_tests and 'DISABLED' in line:
      continue

    test = test_group + line
    tests.put((command, job_id, test))
    print str(job_id) + ': TEST ' + test_binary + ' ' + test
    job_id += 1

def run_job((command, job_id, test)):
  sub = subprocess.Popen(command + ['--gtest_filter=' + test],
                         stdout = subprocess.PIPE,
                         stderr = subprocess.STDOUT)

  while True:
    line = sub.stdout.readline()

    if line == '':
      break

    log.put(str(job_id) + '> ' + line.rstrip())

  code = sub.wait()
  log.put(str(job_id) + ': EXIT ' + str(code))

def worker():
  while True:
    try:
      run_job(tests.get_nowait())
      tests.task_done()
    except Queue.Empty:
      return

def logger():
  while True:
    line = log.get()
    if line == "":
      return
    print line

threads = []
for i in range(options.workers):
  t = threading.Thread(target=worker)
  t.daemon = True
  threads.append(t)

[t.start() for t in threads]
printer = threading.Thread(target=logger)
printer.start()
[t.join() for t in threads]
log.put("")
printer.join()
