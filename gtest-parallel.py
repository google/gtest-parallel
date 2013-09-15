#!/usr/bin/env python2
import argparse
import os
import subprocess

parser = argparse.ArgumentParser(prog=os.path.basename(__file__),
                                 description='Run gtests in parallel.')

parser.add_argument('gtest_binary', type=str, nargs='+')
parser.add_argument('-p', '--processes', type=int, nargs='?', default=16,
                    help='Number of processes to spawn (default: %(default)s).')
parser.add_argument('--gtest_filter', type=str, default='',
                    help='Test filter.')
parser.add_argument('--gtest_also_run_disabled_tests', action='store_true',
                    default=False, help='Run disabled tests too.')

args = parser.parse_args()

tests = []
# Find tests.
for test_binary in args.gtest_binary:
  command = [test_binary]
  if args.gtest_filter != '':
    command += ['--gtest_filter=' + args.gtest_filter]
  if args.gtest_also_run_disabled_tests:
    command += ['--gtest_also_run_disabled_tests']

  test_list = subprocess.check_output(command + ['--gtest_list_tests'])

  test_group = ''
  for line in test_list.split('\n'):
    if not line.strip():
      continue
    if line[0] != " ":
      test_group = line
      continue
    line = line.strip()

    # Skip disabled tests unless they should be run
    if not args.gtest_also_run_disabled_tests and 'DISABLED' in line:
      continue

    tests.append((command, test_group + line))

for (command, test) in tests:
  print test
