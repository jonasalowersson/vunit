# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2014-2015, Lars Asplund lars.anders.asplund@gmail.com

"""
Interface towards NVC simulator
https://github.com/nickg/nvc
"""

from __future__ import print_function
from vunit.exceptions import CompileError
from distutils.spawn import find_executable
from vunit.ostools import Process
from os.path import dirname, exists
import subprocess
import os


class NvcInterface(object):
    """
    Interface towards NVC simulator
    """
    name = "nvc"

    @staticmethod
    def add_arguments(parser):
        """
        Add command line arguments
        """
        pass

    @classmethod
    def from_args(cls, output_path, args):
        return cls()

    @staticmethod
    def is_available():
        """
        Return True if NVC is installed
        """
        return find_executable('nvc') is not None

    def __init__(self):
        self._libraries = {}

    def compile_project(self, project, vhdl_standard):
        """
        Compile the project using vhdl_standard
        """

        libraries = project.get_libraries()
        self._libraries = libraries
        for library in libraries:
            if not exists(dirname(library.directory)):
                os.makedirs(dirname(library.directory))
            args = ['--std=%s' % vhdl_standard]
            args += ['--ignore-time']
            args += ['--work=%s:%s' % (library.name, library.directory)]
            args += ['-a']
            subprocess.check_output(['nvc'] + args)

        for source_file in project.get_files_in_compile_order():
            print('Compiling ' + source_file.name + ' ...')

            if source_file.file_type == 'vhdl':
                success = self.compile_vhdl_file(source_file.name, source_file.library.name, vhdl_standard)
            else:
                raise RuntimeError("Unkown file type: " + source_file.file_type)

            if not success:
                raise CompileError("Failed to compile '%s'" % source_file.name)

            for design_unit in source_file.design_units:
                if design_unit.unit_type == "package body":
                    args = []
                    args += ['--std=%s' % vhdl_standard]
                    for library in self._libraries:
                        args += ['--map=%s:%s' % (library.name, library.directory)]
                        if library.name == source_file.library.name:
                            args += ['--work=%s:%s' % (library.name, library.directory)]
                    print("Codegen %s" % design_unit.name)
                    subprocess.check_output(['nvc'] + args + ['--codegen', design_unit.name])

            project.update(source_file)

    def compile_vhdl_file(self, source_file_name, library_name, vhdl_standard):
        """
        Compiles a vhdl file into a specific library using a specfic vhdl_standard
        """
        try:
            args = ['--std=%s' % vhdl_standard]
            args += ['--ignore-time']
            for library in self._libraries:
                args += ['--map=%s:%s' % (library.name, library.directory)]
                if library.name == library_name:
                    args += ['--work=%s:%s' % (library.name, library.directory)]
            args += ['-a', source_file_name]
            proc = Process(['nvc'] + args)
            proc.consume_output()
        except Process.NonZeroExitCode:
            return False
        return True

    def simulate(self, output_path,  # pylint: disable=too-many-arguments
                 library_name, entity_name, architecture_name, config):
        """
        Simulate top level
        """
        # @TODO disable_ieee_warnings
        try:
            args = []
            args += ['--std=%s' % "2008"]
            args += ['--ignore-time']
            for library in self._libraries:
                args += ['--map=%s:%s' % (library.name, library.directory)]
                if library.name == library_name:
                    args += ['--work=%s:%s' % (library.name, library.directory)]
            args += ['--work', library_name]
            args += ['-e', entity_name, architecture_name]
            for item in config.generics.items():
                args += ['-g%s=%s' % item]

            if config.elaborate_only:
                proc = Process(['nvc'] + args)
                proc.consume_output()
                return True

            args += ['-r', entity_name, architecture_name]

            if config.fail_on_warning:
                args += ["--exit-severity=warning"]
            else:
                args += ["--exit-severity=error"]

            proc = Process(['nvc'] + args)
            proc.consume_output()

        except Process.NonZeroExitCode:
            return False

        return True
