import codecs
import re
import os
import sys

try:
  from setuptools import setup
except:
  print('please install setuptools via pip:')
  print('  <pip_exe> install setuptools')
  sys.exit(-1)

def find_version(*file_paths):
    version_file = codecs.open(os.path.join(os.path.abspath(
        os.path.dirname(__file__)), *file_paths), 'r').read()
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


setup(
    name='gtest-parallel',
    version=find_version('gtest_parallel', '__init__.py'),
    description='Run Google Test suites in parallel',
    license='Apache License Version 2.0',
    url='http://github.com/google/gtest-parallel',
    packages=['gtest_parallel'],
    scripts=['bin/gtest-parallel']
    #install_requires=[]
    )
