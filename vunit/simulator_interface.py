# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.
#
# Copyright (c) 2015, Lars Asplund lars.anders.asplund@gmail.com

"""
Generic simulator interface
"""

import sys
import os


class SimulatorInterface(object):
    """
    Generic simulator interface
    """

    @staticmethod
    def package_users_depend_on_bodies():
        """
        Returns True when package users also depend on package bodies with this simulator
        """
        return False

    @staticmethod
    def find_executable(executable):
        """
        Return a list of all executables found in PATH
        """
        path = os.environ['PATH']
        paths = path.split(os.pathsep)
        base, ext = os.path.splitext(executable)

        if (sys.platform == 'win32' or os.name == 'os2') and (ext != '.exe'):
            executable = executable + '.exe'

        result = []
        if isfile(executable):
            result.append(executable)

        for prefix in paths:
            file_name = os.path.join(prefix, executable)
            if isfile(file_name):
                # the file exists, we have a shot at spawn working
                result.append(file_name)
        return result

    @classmethod
    def find_toolchain(cls, executables, constraints=None):
        """
        Find the first path prefix containing all executables
        """
        constraints = [] if constraints is None else constraints

        if len(executables) == 0:
            return None

        all_paths = [[os.path.abspath(os.path.dirname(executables))
                      for executables in cls.find_executable(name)]
                     for name in executables]

        for path0 in all_paths[0]:
            if all([path0 in paths for paths in all_paths] +
                   [constraint(path0) for constraint in constraints]):
                return path0


def isfile(file_name):
    """
    Case insensitive os.path.isfile
    """
    if not os.path.isfile(file_name):
        return False

    return os.path.basename(file_name) in os.listdir(os.path.dirname(file_name))
