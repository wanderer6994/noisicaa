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
import threading
import uuid
import os
import os.path
import tempfile
import struct

import capnp

from . import block_data_capnp
from . import audio_stream


class TestProcessorIPC(unittest.TestCase):
    def test_ipc(self):
        cdef Status status

        cdef unique_ptr[HostData] host_data
        host_data.reset(new HostData())

        address = os.fsencode(
            os.path.join(
                tempfile.gettempdir(),
                'test.%s.pipe' % uuid.uuid4().hex))

        cdef unique_ptr[Processor] processor_ptr
        processor_ptr.reset(Processor.create(host_data.get(), b'ipc'))
        self.assertTrue(processor_ptr.get() != NULL)

        server = audio_stream.AudioStream.create_server(address)
        server.setup()

        def server_thread():
            try:
                while True:
                    request_bytes = server.receive_bytes()
                    request = block_data_capnp.BlockData.from_bytes(request_bytes)

                    response = block_data_capnp.BlockData.new_message()
                    response.blockSize = request.blockSize
                    response.samplePos = request.samplePos
                    response.init('buffers', 2)
                    b = response.buffers[0]
                    b.id = 'output:0'
                    b.data = struct.pack('ffff', 0.0, 0.5, 1.0, 0.5)
                    b = response.buffers[1]
                    b.id = 'output:1'
                    b.data = struct.pack('ffff', 0.0, -0.5, -1.0, -0.5)

                    response_bytes = response.to_bytes()
                    server.send_bytes(response_bytes)

            except audio_stream.ConnectionClosed:
                pass

        thread = threading.Thread(target=server_thread)
        thread.start()

        cdef Processor* processor = processor_ptr.get()

        cdef unique_ptr[ProcessorSpec] spec
        spec.reset(new ProcessorSpec())
        spec.get().add_port(b'left', PortType.audio, PortDirection.Output)
        spec.get().add_port(b'right', PortType.audio, PortDirection.Output)
        spec.get().add_parameter(new StringParameterSpec(b'ipc_address', address))

        status = processor.setup(spec.release())
        self.assertFalse(status.is_error(), status.message())

        cdef float leftbuf[4]
        cdef float rightbuf[4]

        status = processor.connect_port(0, <BufferPtr>leftbuf)
        self.assertFalse(status.is_error(), status.message())
        status = processor.connect_port(1, <BufferPtr>rightbuf)
        self.assertFalse(status.is_error(), status.message())

        for i in range(4):
            leftbuf[i] = 0.0
            rightbuf[i] = 0.0

        cdef BlockContext ctxt
        ctxt.block_size = 4
        ctxt.sample_pos = 1024

        with nogil:
            status = processor.run(&ctxt)
        self.assertFalse(status.is_error(), status.message())

        self.assertEqual(leftbuf, [0.0, 0.5, 1.0, 0.5])
        self.assertEqual(rightbuf, [0.0, -0.5, -1.0, -0.5])

        processor.cleanup()

        thread.join()
        server.cleanup()
