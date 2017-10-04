# @begin:license
#
# Copyright (c) 2015-2017, Benjamin Niemann <pink@odahoda.de>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# @end:license

from noisicaa.core.status cimport *


cdef class PyHostData(object):
    def __init__(self):
        self.__host_data_ptr.reset(new HostData())
        self.__host_data = self.__host_data_ptr.get()

    def setup(self):
        check(self.__host_data.setup())

    def cleanup(self):
        self.__host_data.cleanup()

    cdef HostData* ptr(self):
        return self.__host_data
