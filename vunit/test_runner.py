# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2014-2015, Lars Asplund lars.anders.asplund@gmail.com

"""
Provided functionality to run a suite of test in a robust way
"""


from __future__ import print_function

from os.path import join
import traceback
import vunit.ostools as ostools
from vunit.test_report import PASSED, FAILED

import threading
import sys
import time

import logging
LOGGER = logging.getLogger(__name__)


class TestRunner(object):
    """
    Administer the execution of a list of test suites
    """
    def __init__(self, report, output_path, verbose=False, num_threads=1):
        self._lock = threading.Lock()
        self._local = threading.local()
        self._report = report
        self._output_path = output_path
        self._verbose = verbose
        self._num_threads = num_threads

    def run(self, test_suites):
        """
        Run a list of test suites
        """
        num_tests = 0
        for test_suite in test_suites:
            for test_name in test_suite.test_cases:
                num_tests += 1
                if self._verbose:
                    print("Running test: " + test_name)

        if self._verbose:
            print("Running %i tests" % num_tests)
            print()

        scheduler = TestScheduler(test_suites)

        threads = []

        # Disable continuous output in parallel mode
        write_stdout = self._verbose and self._num_threads == 1

        try:
            sys.stdout = ThreadLocalOutput(self._local)
            sys.stderr = ThreadLocalOutput(self._local)

            # Start P-1 worker threads
            for _ in range(self._num_threads - 1):
                new_thread = threading.Thread(target=self._run_thread,
                                              args=(write_stdout, scheduler, num_tests, False))
                threads.append(new_thread)
                new_thread.start()

            # Run one worker in main thread such that P=1 is not multithreaded
            self._run_thread(write_stdout, scheduler, num_tests, True)

            scheduler.wait_for_finish()

        except KeyboardInterrupt:
            LOGGER.debug("TestRunner: Caught Ctrl-C shutting down")
            ostools.PROGRAM_STATUS.shutdown()
            raise

        finally:
            for thread in threads:
                thread.join()

            sys.stdout = sys.__stdout__
            sys.stderr = sys.__stderr__
            LOGGER.debug("TestRunner: Leaving")

    def _run_thread(self, write_stdout, scheduler, num_tests, is_main):
        """
        Run worker thread
        """
        self._local.output = sys.__stdout__

        while True:
            test_suite = None
            try:
                test_suite = scheduler.next()

                with self._lock:
                    for test_name in test_suite.test_cases:
                        print("Starting %s" % test_name)

                self._run_test_suite(test_suite, write_stdout, num_tests)

            except StopIteration:
                return

            except KeyboardInterrupt:
                # Only main thread should handle KeyboardInterrupt
                if is_main:
                    raise
                else:
                    return

            finally:
                if test_suite is not None:
                    scheduler.test_done()

    def _run_test_suite(self, test_suite, write_stdout, num_tests):
        """
        Run the actual test suite
        """
        start_time = ostools.get_time()

        output_path = join(self._output_path, test_suite.name)
        output_file_name = join(output_path, "output.txt")

        try:
            # If we could not clean output path, fail all tests
            ostools.renew_path(output_path)
            output_file = open(output_file_name, "w")
        except KeyboardInterrupt:
            raise
        except:  # pylint: disable=bare-except
            results = self._fail_suite(test_suite)
            with self._lock:
                traceback.print_exc()
                self._add_results(test_suite, results, start_time, num_tests)
            return

        try:
            if write_stdout:
                self._local.output = TeeToFile([sys.__stdout__, output_file])
            else:
                self._local.output = TeeToFile([output_file])

            results = test_suite.run(output_path)
        except KeyboardInterrupt:
            raise
        except:  # pylint: disable=bare-except
            traceback.print_exc()
            results = self._fail_suite(test_suite)
        finally:
            self._local.output = sys.__stdout__
            output_file.flush()
            output_file.close()

        any_not_passed = any(value != PASSED for value in results.values())

        with self._lock:
            if (not write_stdout) and (any_not_passed or self._verbose):
                self._print_output(output_file_name)
            self._add_results(test_suite, results, start_time, num_tests)

    @staticmethod
    def _print_output(output_file_name):
        """
        Print contents of output file if it exists
        """
        with open(output_file_name, "r") as fread:
            for line in fread:
                print(line, end="")

    def _add_results(self, test_suite, results, start_time, num_tests):
        """
        Add results to test report
        """
        output_file_name = join(self._output_path, test_suite.name, "output.txt")
        runtime = ostools.get_time() - start_time
        time_per_test = runtime / len(results)

        for test_name in test_suite.test_cases:
            status = results[test_name]
            self._report.add_result(test_name,
                                    status,
                                    time_per_test,
                                    output_file_name)
            self._report.print_latest_status(total_tests=num_tests)
        print()

    @staticmethod
    def _fail_suite(test_suite):
        """ Return failure for all tests in suite """
        results = {}
        for test_name in test_suite.test_cases:
            results[test_name] = FAILED
        return results


class TeeToFile(object):
    """
    Provide a write method which writes to multiple files
    like the unix 'tee' command.
    """
    def __init__(self, files):
        self._files = files

    def write(self, txt):
        for ofile in self._files:
            ofile.write(txt)

    def flush(self):
        for ofile in self._files:
            ofile.flush()


class ThreadLocalOutput(object):
    """
    Replacement for stdout/err that separates re-directs
    output to a thread local file interface
    """
    def __init__(self, local):
        self._local = local

    def write(self, txt):
        if hasattr(self._local, "output"):
            self._local.output.write(txt)
        else:
            sys.__stdout__.write(txt)

    def flush(self):
        if hasattr(self._local, "output"):
            self._local.output.flush()
        else:
            sys.__stdout__.flush()


class TestScheduler(object):
    """
    Schedule tests to different treads
    """

    def __init__(self, tests):
        self._lock = threading.Lock()
        self._tests = tests
        self._idx = 0
        self._num_done = 0

    def __iter__(self):
        return self

    def __next__(self):
        """
        Iterator in Python 3
        """
        return self.__next__()

    def next(self):
        """
        Iterator in Python 2
        """
        ostools.PROGRAM_STATUS.check_for_shutdown()
        with self._lock:
            if self._idx < len(self._tests):
                idx = self._idx
                self._idx += 1
                return self._tests[idx]
            else:
                raise StopIteration

    def test_done(self):
        """
        Signal that a test has been done
        """
        with self._lock:
            self._num_done += 1

    def is_finished(self):
        with self._lock:
            return self._num_done >= len(self._tests)

    def wait_for_finish(self):
        """
        Block until all tests have been done
        """
        while not self.is_finished():
            time.sleep(0.05)
