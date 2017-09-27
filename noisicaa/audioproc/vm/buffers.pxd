from libcpp.memory cimport unique_ptr
from libc.stdint cimport uint8_t, uint32_t

from noisicaa.bindings.lv2 cimport urid
from noisicaa.core.status cimport *

from .host_data cimport *

cdef extern from "noisicaa/audioproc/vm/buffers.h" namespace "noisicaa" nogil:
    ctypedef uint8_t* BufferPtr

    cppclass BufferType:
        pass

    cppclass Float(BufferType):
        pass

    cppclass FloatAudioBlock(BufferType):
        pass

    cppclass AtomData(BufferType):
        pass

    cppclass Buffer:
        Buffer(HostData* host_data, BufferType* type)

        const BufferType* type() const
        BufferPtr data()
        uint32_t size() const

        Status allocate(uint32_t block_size)

        Status clear()
        Status mix(const Buffer* other)
        Status mul(float factor)


cdef class PyBufferType(object):
    cdef unique_ptr[BufferType] cpptype