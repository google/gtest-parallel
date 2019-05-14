#!/usr/bin/env python
# Copyright 2019 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from setuptools import find_packages, setup

description = ('Run Google Test suites in parallel.')

# Reading long Description from README.md file.
with open("README.md", "r") as fh:
    long_description = fh.read()

setup(
    name = 'gtest-parallel',
    url = 'http://github.com/google/gtest-parallel',
    author = 'Google Inc.',
    author_email = 'googletestframework@googlegroups.com',
    license = 'Apache 2.0',
    description = description,
    long_description = long_description,
    long_description_content_type = "text/markdown",
    packages = find_packages(),
    scripts=['./gtest-parallel']

)

