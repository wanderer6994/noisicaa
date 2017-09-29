from libcpp.vector cimport vector
from libcpp.memory cimport unique_ptr

from noisicaa.core.status cimport *
from .buffers cimport *
from .control_value cimport *
from .opcodes cimport *
from .processor cimport *

cdef extern from "noisicaa/audioproc/vm/spec.h" namespace "noisicaa" nogil:
    cppclass Spec:
        Status append_opcode(OpCode opcode, ...)
        Status append_opcode_args(OpCode opcode, const vector[OpArg]& args)
        int num_ops() const
        OpCode get_opcode(int idx) const
        const OpArg& get_oparg(int idx, int arg) const

        Status append_buffer(const string& name, BufferType* type)
        int num_buffers() const
        const BufferType* get_buffer(int idx) const
        StatusOr[int] get_buffer_idx(const string& name) const

        Status append_control_value(ControlValue* cv)
        int num_control_values() const
        ControlValue* get_control_value(int idx) const
        StatusOr[int] get_control_value_idx(const ControlValue* cv) const

        Status append_processor(Processor* processor)
        int num_processors() const
        Processor* get_processor(int idx) const
        StatusOr[int] get_processor_idx(const Processor* processor) const


cdef class PySpec(object):
    cdef unique_ptr[Spec] __spec_ptr
    cdef Spec* __spec

    cdef Spec* ptr(self)
    cdef Spec* release(self)
