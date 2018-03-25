# @begin:license
#
# Copyright (c) 2015-2018, Benjamin Niemann <pink@odahoda.de>
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

cdef extern from "noisicaa/audioproc/engine/message_queue.h" namespace "noisicaa" nogil:
    enum MessageType:
        SOUND_FILE_COMPLETE
        PORT_RMS

    cppclass Message:
        MessageType type
        size_t size

    cppclass NodeMessage(Message):
        char node_id[256]

    cppclass SoundFileCompleteMessage(NodeMessage):
        pass

    cppclass PortRMSMessage(NodeMessage):
        int port_index
        float rms

    cppclass MessageQueue:
        void clear()
        Message* first() const
        Message* next(Message* it) const
        int is_end(Message* it) const


cdef class PyMessage(object):
    cdef const Message* __msg

    @staticmethod
    cdef PyMessage create(const Message* msg)