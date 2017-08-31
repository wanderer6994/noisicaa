from libcpp.string cimport string
from libcpp.memory cimport unique_ptr
from .status cimport *
from .block_context cimport *
from .buffers cimport *
from .processor cimport *
from .processor_spec cimport *
from .host_data cimport *

import unittest
import sys


class TestProcessorLV2(unittest.TestCase):
    def test_lv2(self):
        cdef Status status

        cdef unique_ptr[HostData] host_data
        host_data.reset(new HostData())
        status = host_data.get().setup_lilv()
        self.assertFalse(status.is_error(), status.message())

        cdef unique_ptr[Processor] processor_ptr
        processor_ptr.reset(Processor.create(host_data.get(), b'lv2'))
        self.assertTrue(processor_ptr.get() != NULL)

        cdef Processor* processor = processor_ptr.get()

        cdef unique_ptr[ProcessorSpec] spec
        spec.reset(new ProcessorSpec())
        spec.get().add_port(b'gain', PortType.kRateControl, PortDirection.Input)
        spec.get().add_port(b'in', PortType.audio, PortDirection.Input)
        spec.get().add_port(b'out', PortType.audio, PortDirection.Output)
        spec.get().add_parameter(new StringParameterSpec(b'lv2_uri', b'http://lv2plug.in/plugins/eg-amp'))

        status = processor.setup(spec.release())
        self.assertFalse(status.is_error(), status.message())

        cdef float gain
        cdef float inbuf[128]
        cdef float outbuf[128]

        processor.connect_port(0, <BufferPtr>&gain)
        processor.connect_port(1, <BufferPtr>inbuf)
        processor.connect_port(2, <BufferPtr>outbuf)

        gain = -6
        for i in range(128):
            inbuf[i] = 1.0
        for i in range(128):
            outbuf[i] = 0.0

        cdef BlockContext ctxt
        ctxt.block_size = 128

        processor.run(&ctxt)

        for i in range(128):
            self.assertAlmostEqual(outbuf[i], 0.5, places=2)

        processor.cleanup()