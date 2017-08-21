from libcpp.string cimport string

from .status cimport *
from .vm cimport *
from .buffers cimport *

cdef extern from "backend.h" namespace "noisicaa" nogil:
    cppclass Backend:
        @staticmethod
        Backend* create(const string& name)

        Status setup(VM* vm)
        void cleanup()
        Status begin_block()
        Status end_block()
        Status output(const string& channel, BufferPtr samples)