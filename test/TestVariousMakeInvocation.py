#!/usr/bin/env python2.7

# In this test we verify different `make check` execution possibilities using the
# Makefile.test in this repo.

import os
import logging
import unittest
import shutil
import subprocess
import tempfile
import sys
import textwrap
import string
import errno
import time
import signal
import psutil
import multiprocessing

def wait_for_condition(cond, true_count=1, max_retries=None, sleep_time=0.1 ):
    retry = 0
    while not cond() and (max_retries == None or retry < max_retries):
        time.sleep(sleep_time)
        retry = retry + 1

    if retry == max_retries:
        assert not "Condition was not true after {} retries".format(max_retries)


class TempDir(object):
    """ A class that creates a temp directory at context creation time and
    removes the temp dir at exit of the context."""
    def __init__(self,retain=False):
        # For debuggability, if retain is True, do not delete the temp dir
        self.retain = retain

    def __enter__(self):
        self.d = tempfile.mkdtemp()
        logging.debug("Using temporary directory: {}".format(self.d))
        return self

    def dir(self):
        return self.d

    def __exit__(self,type,value,traceback):
        if self.retain:
            msg = "TempDir: {0}".format(self.d)
            logging.debug(msg)
            print(msg)
        else:
            shutil.rmtree(self.d,ignore_errors=True)

        return False

class Test(unittest.TestCase):

    @staticmethod
    def initLog(level):
        """Init the basic logging"""

        logging.basicConfig(
            format="%(asctime)s %(process)d %(threadName)s %(levelname)s " \
                +"%(message)s",
            stream=sys.stderr,
            level=level)

    @staticmethod
    def _makefile_test_path():
        """ Return the absolute path os the Makefile.test in this repo.
        The actual file that is distributed via this repo"""

        # Get the dir of the current script (TestVariousMakeInvocation.py) and
        # from there knowing the directory structure of the repo, reach to the
        # Makefile.test
        # TODO: This section strictly depends on the file hierarchy of the repo.
        file_dir = os.path.dirname(os.path.abspath(__file__))
        repo_root_dir = os.path.dirname(file_dir)
        makefile_test_path = os.path.join(repo_root_dir,"Makefile.test")

        rv = os.path.realpath(os.path.abspath(makefile_test_path))
        assert os.path.isfile(rv) and "Could not find Makefile.test"
        return rv

    @staticmethod
    def copy_makefile_test_to(d):
        """Copy the Makefile.test file from this repo to the given dir"""

        src = Test._makefile_test_path()
        dest = os.path.join(d, "Makefile.test")
        shutil.copy(src, dest)

    @staticmethod
    def populate_test_dir(d, tests, test_dir_relative_to_makefile):
        """The given directory is the directory for the tests. Add the leaf makefile
        there and copy the test scripts."""

        if test_dir_relative_to_makefile == Test.same_dir:
            path_to_makefile_test = "."
        elif test_dir_relative_to_makefile == Test.child_dir:
            path_to_makefile_test = ".."
        else:
            assert not "unexpected test_dir_relative_to_makefile"

        contents = string.Template("""
        TESTS ?= ${tests}
        MAKEFILE_DIR := $$(shell dirname $$(realpath $$(lastword $$(MAKEFILE_LIST))))
        include $$(MAKEFILE_DIR)/${path_to_makefile_test}/Makefile.test
            """).substitute(
                tests=" ".join(tests),
                path_to_makefile_test=path_to_makefile_test)

        contents = textwrap.dedent(contents)

        leaf_makefile_name = "Makefile"
        leaf_makefile_path = os.path.join(d, leaf_makefile_name)
        with open(leaf_makefile_path, "w") as f:
            f.write(contents)

        file_dir = os.path.dirname(os.path.abspath(__file__))
        for test_file in tests:
            shutil.copy(os.path.join(file_dir, test_file),
                os.path.join(d, test_file))

    @staticmethod
    def make_dirs_ignore_existing(p):
        """unix mkdir -p functionality. Creates the directory given in the path
        p. Also creates the intermediate directories. Does not complain if the
        root directory exists already."""
        try:
            os.makedirs(p)
        except OSError as e:
            if e.errno==errno.EEXIST and os.path.isdir(p):
                pass
            else:
                raise

    def find_file_at_root(self, d, seeked_files):
        """Check whether at least one of the given seeked_files exist in the given
        directory root. If found return the name of the file, otherwise return
        None"""

        for root, dirs, files in os.walk(d):
            for file_name in files:
                if file_name in seeked_files:
                    return file_name
        return None

    def check_no_intermediate_files(self, d):
        """Verify that in the directory tree rooted at d there are no intermediate
        files left behind"""

        # taken from the makefile.
        intermediate_file_names = [".makefile_test_failed_tests",
            ".makefile_test_executed_tests"]

        found_file = self.find_file_at_root(d, intermediate_file_names)

        if found_file != None:
            self.assertFalse("Found unexpected file: {} in dir: {}".format(
                found_file, d))

    def check_return_value(self, rv, expected_rv):
        """If expected_rv is zero, return value must be zero.
        If expected_outpus is non_zero, then the return value must be non_zero"""

        self.assertEqual(rv, expected_rv)

    def check_output(self, out, expected_output):
        """ Verify the stdout from the makefile. The given regex in expected_output
        must match in out"""
        self.assertRegexpMatches(out, expected_output)

    @staticmethod
    def pids_of_descendant_sleep(pid):
        """Look at all of the descendants of pid and find the sleep processes.
        Return the sleeps' pids"""

        p = psutil.Process(pid)
        descendants = p.children(recursive=True)

        sleep_pid = []
        for d in descendants:
            if "sleep" in d.exe():
                assert not (d.pid in sleep_pid)
                sleep_pid.append(d.pid)

        return sleep_pid

    @staticmethod
    def sleep_process_with_pid(pid):
        """Check that a sleep process with the given pid exists or not.
        If it does not return none"""

        try:
            p = psutil.Process(pid)
        except psutil.NoSuchProcess as e:
            return None

        exe = None
        while exe is None:
            try:
                exe = p.exe()
            except psutil.AccessDenied as e:
                pass
            except psutil.NoSuchProcess as e:
                return None

        if "sleep" in exe:
            return p
        else:
            return None


    @staticmethod
    def get_clean_env():
        """Get an environment to passed to the make executions.

	This script is executed in the same Makefile itself remove the
	exported environment variables so that the make execution tests can
	start from a clean slate"""

        env = dict(os.environ)
        env.pop("TESTS", None)
        env.pop("FIRST_MAKEFILE", None)
        env.pop("FIRST_MAKEFILE_DIR", None)
        env.pop("TEST_TARGETS", None)

	return env


    wait, term, sigint = range(3)
    do_check, skip_check = range(2)
    def call_make_do_checks(self, cmd, parent_dir, run_dir, expected_rv,
            expected_output, subprocess_handling, check_intermediate_files):
        """Spawns the make command and does some additional checking."""

        # remove the exported makefile variables from the environment.
        # This test verifies the Makefile.test but it is executed using
        # Makefile.test. The tests in this repo also use the Makefile.test.  In
        # the supported use case Makefile.test is designed to be a singleton.
        # With removing these exported variables, we remove the modifications
        # the parent makefile did on the environment.
        env = Test.get_clean_env()

        descendent_sleep_pids = None

        def in_new_pgrp():
            os.setpgrp()
            return

        if subprocess_handling == Test.wait:
            p = subprocess.Popen(cmd,
                cwd=run_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=in_new_pgrp)
        elif subprocess_handling == Test.term:
            p = subprocess.Popen(cmd,
                cwd=run_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=in_new_pgrp)
            # Wait for an executedTests file to appear. That means the tests
            # have started. Then terminate the make.
            wait_for_condition(lambda: self.find_file_at_root(parent_dir, \
                [".makefile_test_executed_tests"]) != None)

            descendent_sleep_pids = Test.pids_of_descendant_sleep(p.pid)
            while len(descendent_sleep_pids) == 0:
                descendent_sleep_pids = Test.pids_of_descendant_sleep(p.pid)

            # Send the signal to the entire process group id.
            # Killing the process group is the recommended way to kill hung makes.
            os.killpg(p.pid, signal.SIGTERM)
        elif subprocess_handling == Test.sigint:

            # Make has child processes. We want to send the SIGINT to the
            # entire process group of make. This resembles the CTRL-C behavior
            # from the terminal. In order to get its own process group, we call
            # the preexec_fn before spawn
            p = subprocess.Popen(cmd,
                cwd=run_dir,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=in_new_pgrp)
            # Wait for an executedTests file to appear. That means the tests
            # have started. Then ctrl-C the make .
            wait_for_condition(lambda: self.find_file_at_root(parent_dir, \
                [".makefile_test_executed_tests"]) != None)

            descendent_sleep_pids = Test.pids_of_descendant_sleep(p.pid)
            while len(descendent_sleep_pids) == 0:
                descendent_sleep_pids = Test.pids_of_descendant_sleep(p.pid)

            # Send the signal to the entire process group id.
            os.killpg(p.pid, signal.SIGINT)

        out, err = p.communicate()
        rv = p.returncode

        logging.debug(out)
        logging.debug(err)

        self.check_return_value(rv, expected_rv)
        if expected_output is not None:
            self.check_output(out, expected_output)
        if check_intermediate_files == Test.do_check:
            self.check_no_intermediate_files(parent_dir)
            self.check_no_intermediate_files(run_dir)

        if descendent_sleep_pids != None:
            # If we had any sleep processes, then they must have disappered by now.
            self.assertTrue(all(
                [Test.sleep_process_with_pid(p) == None \
                    for p in descendent_sleep_pids]))

    def handle_additional_filename(self,additional_file_name, test_dir_path):
        """The test_dir_path needs to have an additional_file_name. If the
        additional_file_name exists in current dir, copy it over. Otherwise
        create a new file in test_dir_path"""

        this_file_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(this_file_dir, additional_file_name)

        if os.path.isfile(file_path):
            shutil.copy(file_path, test_dir_path)
        else:
            with open(os.path.join(test_dir_path, additional_file_name), "w"):
                pass

    same_dir, child_dir = range(2)
    def make_execution(self,
        test_dir_relative_to_makefile,
        tests,
        expected_rv,
        expected_output,
        subprocess_handling,
        check_intermediate_files,
        additional_file_name=None,
        ):
        """Execute make in various different ways in a tests directory.
        1) cd <test_dir> && make check
        2) make -C <test_dir> make check
        3) make -f <test_dir>/Makefile check

        Depending on test_dir_relative_to_makefile, the
        The leaf makefile and the Makefile.test can be in the same or different
        directories.

        tests is a list of names of the tests to execute.

        Depending on expected_rv, the test are checked to pass or fail

        The regex given in expected_output must match in the stdout of the make
        execution

        subprocess_handling determines whether the caller is going to wait for make
        to complete, or terminate it or kill it.

        if an additional_file_name is specified, then a new file with that name
            is placed in the test directory. If the file exists in current dir,
            that gets copied. Otherwise a new file is touched. """

        with TempDir() as td:
            d = td.dir()

            if test_dir_relative_to_makefile == Test.same_dir:
                test_dir_path = d
            elif test_dir_relative_to_makefile == Test.child_dir:
                test_dir_path = os.path.join(d, "test")
            else:
                assert not "unexpected test_dir_relative_to_makefile"

            Test.make_dirs_ignore_existing(test_dir_path)

            if additional_file_name != None:
                self.handle_additional_filename(additional_file_name, test_dir_path)

            Test.copy_makefile_test_to(d)
            Test.populate_test_dir(test_dir_path, tests,
                test_dir_relative_to_makefile)

            # Execute make with jobserver and without.
            self.call_make_do_checks(["make"], d, test_dir_path, expected_rv,
                expected_output, subprocess_handling, check_intermediate_files)
            self.call_make_do_checks(["make", "-j"], d, test_dir_path, expected_rv,
                expected_output, subprocess_handling, check_intermediate_files)

            with TempDir() as runDir:
                rd = runDir.dir()

                self.call_make_do_checks(["make", "-C", test_dir_path], d, rd,
                    expected_rv, expected_output, subprocess_handling,
                    check_intermediate_files)
                self.call_make_do_checks(["make", "-j", "-C", test_dir_path], d, rd,
                    expected_rv, expected_output, subprocess_handling,
                    check_intermediate_files)

                leaf_makefile_path = os.path.join(test_dir_path, "Makefile")
                self.call_make_do_checks(["make", "-f", leaf_makefile_path], d, rd,
                    expected_rv, expected_output, subprocess_handling,
                    check_intermediate_files)
                self.call_make_do_checks(["make", "-j", "-f", leaf_makefile_path],
                    d, rd, expected_rv, expected_output, subprocess_handling,
                    check_intermediate_files)


    def test_make_execution_success(self):
        """Verify make behavior if the outcome is successful. Either all tests
        have passes or there were no tests to start with."""

        logging.debug("Running success tests")
        self.make_execution(Test.child_dir,
            ["passing_test.sh"],
            0,
            "All\s*1 tests passed",
            Test.wait,
            Test.do_check)
        self.make_execution(Test.child_dir,
            ["passing_test.sh", "passing_test1.sh"],
            0,
            "All\s*2 tests passed",
            Test.wait,
            Test.do_check)

        self.make_execution(Test.same_dir,
            ["passing_test.sh"],
            0,
            "All\s*1 tests passed",
            Test.wait,
            Test.do_check)
        self.make_execution(Test.same_dir,
            ["passing_test.sh","passing_test1.sh"],
            0,
            "All\s*2 tests passed",
            Test.wait,
            Test.do_check)

        # Empty Test.
        self.make_execution(Test.child_dir,
            [],
            0,
            "All\s*0 tests passed",
            Test.wait,
            Test.do_check)
        self.make_execution(Test.same_dir,
            [],
            0,
            "All\s*0 tests passed",
            Test.wait,
            Test.do_check)

        # A python test
        self.make_execution(Test.child_dir,
            ["ExamplePythonTest.py"],
            0,
            "All\s*1 tests passed",
            Test.wait,
            Test.do_check,
            additional_file_name="ExamplePythonLibrary.py")
        self.make_execution(Test.same_dir,
            ["ExamplePythonTest.py"],
            0,
            "All\s*1 tests passed",
            Test.wait,
            Test.do_check,
            additional_file_name="ExamplePythonLibrary.py")

    def test_make_execution_failure(self):
        """Verify make behavior if the outcome is unsuccessful. At least one test
        has failed."""

        logging.debug("Running failure tests")
        self.make_execution(Test.child_dir,
            ["failing_test.sh"],
            2,
            "Failed\s*1 out of\s*1 tests",
            Test.wait,
            Test.do_check)
        self.make_execution(Test.child_dir,
            ["failing_test.sh", "failing_test1.sh"],
            2,
            "Failed\s*2 out of\s*2 tests",
            Test.wait,
            Test.do_check)
        self.make_execution(Test.same_dir,
            ["failing_test.sh"],
            2,
            "Failed\s*1 out of\s*1 tests",
            Test.wait,
            Test.do_check)
        self.make_execution(Test.same_dir,
            ["failing_test.sh", "failing_test1.sh"],
            2,
            "Failed\s*2 out of\s*2 tests",
            Test.wait,
            Test.do_check)

        self.make_execution(Test.child_dir,
            ["passing_test.sh", "failing_test.sh"],
            2,
            "Failed\s*1 out of\s*2 tests",
            Test.wait,
            Test.do_check)
        self.make_execution(Test.same_dir,
            ["passing_test.sh", "failing_test.sh"],
            2,
            "Failed\s*1 out of\s*2 tests",
            Test.wait,
            Test.do_check)

        # A target with "TARGET_FOR_" prefix is used in the Makefile.test
        # implementation.  We make sure we still execute the test even if
        # coincidentally there is a file with that name in the test directory.
        self.make_execution(Test.child_dir,
            ["failing_test.sh"],
            2,
            "Failed\s*1 out of\s*1 tests",
            Test.wait,
            Test.do_check,
            additional_file_name="TARGET_FOR_failing_test.sh")
        self.make_execution(Test.same_dir,
            ["failing_test.sh"],
            2,
            "Failed\s*1 out of\s*1 tests",
            Test.wait,
            Test.do_check,
            additional_file_name="TARGET_FOR_failing_test.sh")

    def test_make_execution_sigterm(self):
        """Verify make behavior if it is terminated with SIGTERM"""

        logging.debug("Running sigterm tests")

        tests_lists = [
            ["indefinite_test.sh"],
            ["indefinite_test.sh", "indefinite_test1.sh"],
            ["indefinite_test.py"],
            ["indefinite_test.py", "indefinite_test1.py"],
        ]

        for test_list in tests_lists:
            # Makefile.test does not print a summary line if it gets TERMINATED
            self.make_execution(Test.child_dir,
                test_list,
                -signal.SIGTERM,
                None,
                Test.term,
                Test.do_check)
            self.make_execution(Test.same_dir,
                test_list,
                -signal.SIGTERM,
                None,
                Test.term,
                Test.do_check)

    def test_make_execution_sigint(self):
        """Verify make behavior if it is terminated with a CTRL-C from the terminal
        AKA send sigint to its process group"""

        logging.debug("Running sigint tests")

        tests_lists = [
            ["indefinite_test.sh"],
            ["indefinite_test.sh", "indefinite_test1.sh"],
            # Python exits with 1 in case of an unhandled KeyboardInterrupt
            # instaed of -SIGINT.  It is worth testing our Makefile.test with
            # executables that does not exit with -SIGINT in terms of a SIGINT.
            ["indefinite_test.py"],
            ["indefinite_test.py", "indefinite_test1.py"],
        ]

        for test_list in tests_lists:
            # Makefile.test does not print a summary line if it gets CTRL-C'ed
            self.make_execution(Test.child_dir,
                test_list,
                -signal.SIGINT,
                None,
                Test.sigint,
                Test.skip_check)
            self.make_execution(Test.same_dir,
                test_list,
                -signal.SIGINT,
                None,
                Test.sigint,
                Test.skip_check)

    @staticmethod
    def descendant_sleep_process_count(pid):
        """Count the number of descendant sleep processes of the given pid"""

        p = psutil.Process(pid)
        descendants = p.children(recursive=True)

        sleep_count = 0
        for d in descendants:
            if "sleep" in d.exe():
                sleep_count = sleep_count + 1

        return sleep_count


    def make_parallelism(self, cmd, tests, expected_parallel_jobs):
        """ Populate a test dir with the given tests, execute the given cmd.
        While the test is running verify that the expected number of parallel
        jobs can be found in the recursive chidren of the make command"""

        with TempDir() as td:
            d = td.dir()
            Test.copy_makefile_test_to(d)
            Test.populate_test_dir(d, tests, Test.same_dir)

            env = Test.get_clean_env()
            def in_new_pgrp():
                os.setpgrp()
                return
            p = subprocess.Popen(cmd,
                cwd=d,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=in_new_pgrp)

            pid = p.pid

            wait_for_condition(lambda: self.find_file_at_root(d, \
                [".makefile_test_executed_tests"]) != None)

            # Both of the indefinite_tests should be running in parallel.
            check_count = 3

            for i in range(check_count):
                wait_for_condition(lambda: Test.descendant_sleep_process_count(pid) \
                        == expected_parallel_jobs)

            os.killpg(pid, signal.SIGTERM)
            out, err = p.communicate()
            logging.debug(out)
            logging.debug(err)


    @unittest.skipIf(multiprocessing.cpu_count() == 1,
        "Host machine has only 1 processor, it does not support parallel execution.")
    def test_make_parallelism(self):
        """Verify that parallel execution of make actually executes processes in
	parallel"""

        self.make_parallelism(["make", "-j"],
            ["indefinite_test.sh", "indefinite_test1.sh"],
            2)

        self.make_parallelism(["make", "-j", "1"],
            ["indefinite_test.sh", "indefinite_test1.sh"],
            1)


if __name__ == '__main__':
    Test.initLog(logging.DEBUG)
    unittest.main()


# Test Plan
# 1) Add a test to verify command line overwrite of TESTS.


