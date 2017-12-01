
# Makefile.test

[![Project Status](http://opensource.box.com/badges/stable.svg)](http://opensource.box.com/badges)
[![CircleCI](https://circleci.com/gh/box/Makefile.test.svg?style=svg)](https://circleci.com/gh/box/Makefile.test)

A makefile used for running test scripts.

Makefile.test can be used to execute any type of test scripts. Parallel, serial
execution, various platforms and make versions are supported. Test scripts
can be organized in any desired way. The user only lists the test files, the
rest is taken care of Makefile.test.

## Usage:

### Example: A repo that has a `src` and a `test` directory.

A simple repository has a `src` and a `test` directory at its root. The
programmer places application code in `src` and test executables in `test`.
Using the `Makefile.test`, the executables in `test` can be executed with ease.

The directory structure can look like the following:

```
ExampleRepo
├── Makefile.test
├── src
│   └── ExampleApplication.sh
└── test
    ├── ExampleTest1.sh
    ├── ExampleTest2.py
    └── Makefile
```

> For a recommended way to place the Makefile.test into your own repo see the
> [Installation](#installation) section next.

The `Makefile` file in the `test` directory needs to list the executables in a
`TESTS` variable and include the `Makefile.test`


```
TESTS ?= \
	ExampleTest1.sh \
	ExampleTest2.py

include ../Makefile.test
```


To run the tests, any of the following can be used from the repo root.

```
cd test && make -j
make -C test -j
make -f test/Makefile -j
```

The output looks as follows:

```
  [ExampleTest1.sh] Running ExampleTest1
  [ExampleTest2.py] Running ExampleTest2
 PASSED: ExampleTest1.sh
 PASSED: ExampleTest2.py
---------------------------------
All        2 tests passed
---------------------------------
```

### Running one test at a time.

During development or debugging time, you may want to execute only one test at
a time. In order to achive that without modifying any files, overwrite the
TESTS environment variable from the command line:

```
TESTS=ExampleTest2.py make
```

Only runs the specified test:

```
  [ExampleTest2.py] Running ExampleTest2
 PASSED: ExampleTest2.py
---------------------------------
All        1 tests passed
---------------------------------
```

## Installation:

### Requirements

- [`bash`](https://www.gnu.org/software/bash/) needs to be installed at `/bin/bash`.

### Using git submodules and symlink to the Makefile.test.

In the directory you want to place Makefile.test execute the following:

```
git submodule add git@git.dev.box.net:skynet/Makefile.test.git .Makefile.test
ln -s .Makefile.test/Makefile.test
```

First command creates a hidden dir with the submoduled repo.
Second command symlinks the Makefile.test file.

The directory tree of `ExampleRepo` with the submodule and the symlink looks like
this:

```
 ExampleRepo
 ├── .Makefile.test
 │   ├── .....
 │   └── Makefile.test
 ├── Makefile.test -> .Makefile.test/Makefile.test
 ├── src
 │   └── ....
 └── test
     └── ....

```

### Update your `.gitignore` file.

In order to avoid temporary files that may be created by Makefile.test, you should
to update your `.gitignore` file.

```
# Intermediate files created by Makefile.test
**/.makefile_test_*ed_tests
```

## Killing, Interrupting `make`

If hung tests are encountered, one may want to kill the `make` execution.
For SIGTERM, the user should send SIGTERM to the *process group* of `make`. Using
something similar to:

```
kill -s TERM -- -<pgrp id of make>
```

If SIGTERM is only sent to `make` child processes will be orphaned and left behind.

If `make` is invoked interactively from a terminal, `CTRL-C` should kill all running
processes cleanly.



## Support

Need to contact us directly? Email oss@box.com and be sure to include the name of this project in the subject.

## Copyright and License

Copyright 2017 Box, Inc. All rights reserved.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

   http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
