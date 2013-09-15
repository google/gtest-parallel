#!/usr/bin/env python2
import optparse
import multiprocessing
import subprocess
import sys

parser = optparse.OptionParser(
    usage = "usage: %prog [options] executable [executable ...]")

parser.add_option('-p', '--processes', type="int", default=16,
                  help='number of processes to spawn')
parser.add_option('--gtest_filter', type="string", default='',
                  help='test filter')
parser.add_option('--gtest_also_run_disabled_tests', action='store_true',
                  default=False, help='run disabled tests too')

(options, binaries) = parser.parse_args()

if binaries == []:
  parser.print_usage()
  sys.exit(1)

tests = []
# Find tests.
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
      test_group = line
      continue
    line = line.strip()

    # Skip disabled tests unless they should be run
    if not options.gtest_also_run_disabled_tests and 'DISABLED' in line:
      continue

    tests.append((command, len(tests), test_group + line))

def run_job((command, job_id, test)):
  sub = subprocess.Popen(command + ['--gtest_filter=' + test],
                         stdout = subprocess.PIPE,
                         stderr = subprocess.STDOUT)

  do_print = False
  while True:
    line = sub.stdout.readline()

    # EOF, stop reading.
    if line == '':
      break

    if line[0] == '[' and test in line:
      do_print = not do_print
      print str(job_id) + ">", line,
      continue

    if do_print:
      print str(job_id) + ">", line,

  return sub.wait()

return_codes = multiprocessing.Pool(options.processes).map(run_job, tests)

for code in return_codes:
  if code != 0:
    sys.exit(code)
