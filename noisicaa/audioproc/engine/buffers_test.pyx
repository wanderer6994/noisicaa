# @begin:license
#
# Copyright (c) 2015-2019, Benjamin Niemann <pink@odahoda.de>
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

from libcpp.memory cimport unique_ptr

import struct
import sys

from noisidev import unittest
from noisidev cimport unittest_engine_mixins
#from noisicaa.bindings.lv2 cimport atom
#from noisicaa.bindings.lv2 import urid
from noisicaa.core.status cimport check
#from .buffers cimport *


# cdef class FloatTestMixin(unittest_engine_mixins.HostSystemMixin):
#     def test_init(self):
#         cdef:
#             Status status
#             unique_ptr[Buffer] bufptr
#             Buffer* buf
#             float* data

#         bufptr.reset(new Buffer(self.host_system.get(), new Float()))
#         buf = bufptr.get()
#         status = buf.allocate(64)
#         self.assertFalse(status.is_error())

#         self.assertEqual(buf.size(), sizeof(float))
#         data = <float*>buf.data()
#         self.assertEqual(data[0], 0.0)

#     def test_clear(self):
#         cdef:
#             Status status
#             unique_ptr[Buffer] bufptr
#             Buffer* buf
#             float* data

#         bufptr.reset(new Buffer(self.host_system.get(), new Float()))
#         buf = bufptr.get()
#         status = buf.allocate(64)
#         self.assertFalse(status.is_error())
#         data = <float*>buf.data()
#         data[0] = 2.0
#         status = buf.clear()
#         self.assertFalse(status.is_error())
#         self.assertEqual(data[0], 0.0)

#     def test_mul(self):
#         cdef:
#             Status status
#             unique_ptr[Buffer] bufptr
#             Buffer* buf
#             float* data

#         bufptr.reset(new Buffer(self.host_system.get(), new Float()))
#         buf = bufptr.get()
#         status = buf.allocate(64)
#         self.assertFalse(status.is_error())
#         data = <float*>buf.data()
#         data[0] = 2.0
#         status = buf.mul(2)
#         self.assertFalse(status.is_error())
#         self.assertEqual(data[0], 4.0)

#     def test_mix(self):
#         cdef:
#             Status status
#             unique_ptr[Buffer] bufptr1
#             unique_ptr[Buffer] bufptr2
#             Buffer* buf1
#             Buffer* buf2
#             float* data1
#             float* data2

#         bufptr1.reset(new Buffer(self.host_system.get(), new Float()))
#         buf1 = bufptr1.get()
#         status = buf1.allocate(64)
#         self.assertFalse(status.is_error())
#         data1 = <float*>buf1.data()

#         bufptr2.reset(new Buffer(self.host_system.get(), new Float()))
#         buf2 = bufptr2.get()
#         status = buf2.allocate(64)
#         self.assertFalse(status.is_error())
#         data2 = <float*>buf2.data()

#         data1[0] = 2.0
#         data2[0] = 3.0
#         status = buf1.mix(buf2)
#         self.assertFalse(status.is_error())
#         self.assertEqual(data1[0], 5.0)
#         self.assertEqual(data2[0], 3.0)


# class FloatTest(FloatTestMixin, unittest.TestCase):
#     pass


# cdef class FloatAudioBlockTestMixin(unittest_engine_mixins.HostSystemMixin):
#     def test_init(self):
#         cdef:
#             Status status
#             unique_ptr[Buffer] bufptr
#             Buffer* buf
#             float* data

#         bufptr.reset(new Buffer(self.host_system.get(), new FloatAudioBlock()))
#         buf = bufptr.get()

#         status = buf.allocate(64)
#         self.assertFalse(status.is_error())

#         self.assertEqual(buf.size(), 64 * sizeof(float))
#         data = <float*>buf.data()
#         for i in range(64):
#             self.assertEqual(data[i], 0.0)

#     def test_clear(self):
#         cdef:
#             Status status
#             unique_ptr[Buffer] bufptr
#             Buffer* buf
#             float* data

#         bufptr.reset(new Buffer(self.host_system.get(), new FloatAudioBlock()))
#         buf = bufptr.get()

#         status = buf.allocate(4)
#         self.assertFalse(status.is_error())

#         data = <float*>buf.data()
#         data[0:4] = [1.0, 2.0, 3.0, 4.0]
#         status = buf.clear()
#         self.assertFalse(status.is_error())
#         self.assertEqual([f for f in data[0:4]], [0.0, 0.0, 0.0, 0.0])

#     def test_mul(self):
#         cdef:
#             Status status
#             unique_ptr[Buffer] bufptr
#             Buffer* buf
#             float* data

#         bufptr.reset(new Buffer(self.host_system.get(), new FloatAudioBlock()))
#         buf = bufptr.get()
#         status = buf.allocate(4)
#         self.assertFalse(status.is_error())
#         data = <float*>buf.data()
#         data[0:4] = [1.0, 2.0, 3.0, 4.0]
#         status = buf.mul(2)
#         self.assertFalse(status.is_error())
#         self.assertEqual([f for f in data[0:4]], [2.0, 4.0, 6.0, 8.0])

#     def test_mix(self):
#         cdef:
#             Status status
#             unique_ptr[Buffer] bufptr1
#             unique_ptr[Buffer] bufptr2
#             Buffer* buf1
#             Buffer* buf2
#             float* data1
#             float* data2

#         bufptr1.reset(new Buffer(self.host_system.get(), new FloatAudioBlock()))
#         buf1 = bufptr1.get()
#         status = buf1.allocate(4)
#         self.assertFalse(status.is_error())
#         data1 = <float*>buf1.data()

#         bufptr2.reset(new Buffer(self.host_system.get(), new FloatAudioBlock()))
#         buf2 = bufptr2.get()
#         status = buf2.allocate(4)
#         self.assertFalse(status.is_error())
#         data2 = <float*>buf2.data()

#         data1[0:4] = [1.0, 2.0, 3.0, 4.0]
#         data2[0:4] = [3.0, 5.0, 1.0, 2.0]
#         status = buf1.mix(buf2)
#         self.assertFalse(status.is_error())
#         self.assertEqual([f for f in data1[0:4]], [4.0, 7.0, 4.0, 6.0])
#         self.assertEqual([f for f in data2[0:4]], [3.0, 5.0, 1.0, 2.0])


# cdef _fill_atom_buffer(Buffer* buf, data):
#     cdef atom.AtomForge forge = atom.AtomForge(urid.static_mapper)
#     forge.set_buffer(buf.data(), buf.size())

#     string_urid = urid.static_mapper.map('http://lv2plug.in/ns/ext/atom#String')
#     with forge.sequence():
#         for frames, item in data:
#             forge.write_atom_event(frames, string_urid, item, len(item))


# class FloatAudioBlockTest(FloatAudioBlockTestMixin, unittest.TestCase):
#     pass


# cdef _read_atom_buffer(Buffer* buf):
#     result = []

#     seq = atom.Atom.wrap(urid.static_mapper, buf.data())
#     assert isinstance(seq, atom.Sequence), type(seq)
#     for event in seq.events:
#         assert event.atom.type_uri == 'http://lv2plug.in/ns/ext/atom#String'
#         result.append((event.frames, event.atom.data))

#     return result


# cdef class AtomDataTestMixin(unittest_engine_mixins.HostSystemMixin):
#     def test_init(self):
#         cdef:
#             Status status
#             unique_ptr[Buffer] bufptr
#             Buffer* buf

#         bufptr.reset(new Buffer(self.host_system.get(), new AtomData()))
#         buf = bufptr.get()

#         status = buf.allocate(64)
#         self.assertFalse(status.is_error(), status.message())

#         self.assertEqual(buf.size(), 10240)
#         self.assertEqual(_read_atom_buffer(buf), [])

#     def test_clear(self):
#         cdef:
#             Status status
#             unique_ptr[Buffer] bufptr
#             Buffer* buf

#         bufptr.reset(new Buffer(self.host_system.get(), new AtomData()))
#         buf = bufptr.get()

#         status = buf.allocate(4)
#         self.assertFalse(status.is_error())

#         _fill_atom_buffer(buf, [(0, b'0'), (10, b'10'), (20, b'20'), (30, b'30')])
#         buf.clear()
#         self.assertEqual(_read_atom_buffer(buf), [])

#     def test_mul(self):
#         cdef:
#             Status status
#             unique_ptr[Buffer] bufptr
#             Buffer* buf

#         bufptr.reset(new Buffer(self.host_system.get(), new AtomData()))
#         buf = bufptr.get()
#         status = buf.allocate(4)
#         self.assertFalse(status.is_error())

#         status = buf.mul(2)
#         self.assertTrue(status.is_error())

#     def test_mix(self):
#         cdef:
#             Status status
#             unique_ptr[Buffer] bufptr1
#             unique_ptr[Buffer] bufptr2
#             Buffer* buf1
#             Buffer* buf2

#         bufptr1.reset(new Buffer(self.host_system.get(), new AtomData()))
#         buf1 = bufptr1.get()
#         status = buf1.allocate(4)
#         self.assertFalse(status.is_error())

#         bufptr2.reset(new Buffer(self.host_system.get(), new AtomData()))
#         buf2 = bufptr2.get()
#         status = buf2.allocate(4)
#         self.assertFalse(status.is_error())

#         _fill_atom_buffer(buf1, [(0, b'0'), (10, b'10'), (20, b'20'), (30, b'30')])
#         _fill_atom_buffer(buf2, [(1, b'1'), (9, b'9'), (11, b'11'), (15, b'15')])
#         status = buf1.mix(buf2)
#         self.assertFalse(status.is_error())
#         self.assertEqual(
#             _read_atom_buffer(buf1),
#             [(0, b'0'), (1, b'1'), (9, b'9'), (10, b'10'),
#              (11, b'11'), (15, b'15'), (20, b'20'), (30, b'30')])
#         self.assertEqual(
#             _read_atom_buffer(buf2),
#             [(1, b'1'), (9, b'9'), (11, b'11'), (15, b'15')])


# class AtomDataTest(AtomDataTestMixin, unittest.TestCase):
#     pass
