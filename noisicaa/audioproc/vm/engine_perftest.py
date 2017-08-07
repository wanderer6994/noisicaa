#!/usr/bin/python3

import logging
import struct
import threading
import unittest
import os.path

from noisicaa import node_db
from noisicaa import audioproc
from noisidev import perf_stats

from .. import backend
from .. import resample
from .. import nodes
from . import engine
from . import spec
from . import compiler
from . import graph

logger = logging.getLogger(__name__)


class TestBackend(backend.Backend):
    def __init__(self, *, num_frames=1000, skip_first=10):
        super().__init__()

        self.__frame_num = 0
        self.__num_frames = num_frames
        self.__skip_first = skip_first
        self.frame_times = []

    def begin_frame(self, ctxt):
        super().begin_frame(ctxt)
        ctxt.duration = 128
        ctxt.perf.start_span('frame')
        if self.__frame_num >= self.__num_frames:
            self.stop()
            return
        self.__frame_num += 1

    def end_frame(self):
        self.ctxt.perf.end_span()

        if not self.stopped:
            topspan = self.ctxt.perf.serialize().spans[0]
            assert topspan.parentId == 0
            assert topspan.name == 'frame'
            duration = (topspan.endTimeNSec - topspan.startTimeNSec) / 1000.0
            if self.__frame_num > self.__skip_first:
                self.frame_times.append(duration)

        super().end_frame()

    def output(self, channel, samples):
        pass


class PipelineVMPerfTest(unittest.TestCase):

    def test_fluidsynth(self):
        vm = engine.PipelineVM()
        try:
            vm.setup(start_thread=False)

            node1 = nodes.FluidSynthSource(
                id='node1',
                soundfont_path='/usr/share/sounds/sf2/TimGM6mb.sf2', bank=0, preset=0)
            node1.setup()
            vm.add_node(node1)

            node2 = nodes.FluidSynthSource(
                id='node2',
                soundfont_path='/usr/share/sounds/sf2/TimGM6mb.sf2', bank=0, preset=1)
            node2.setup()
            vm.add_node(node2)

            node3 = nodes.FluidSynthSource(
                id='node3',
                soundfont_path='/usr/share/sounds/sf2/TimGM6mb.sf2', bank=0, preset=2)
            node3.setup()
            vm.add_node(node3)

            sink = nodes.Sink()
            sink.setup()
            vm.add_node(sink)
            for src in (node1, node2, node3):
                sink.inputs['in:left'].connect(src.outputs['out:left'])
                sink.inputs['in:right'].connect(src.outputs['out:right'])

            vm.update_spec()

            be = TestBackend()
            vm.setup_backend(be)

            vm.vm_loop()

            perf_stats.write_frame_stats(
                os.path.splitext(os.path.basename(__file__))[0],
                '.'.join(self.id().split('.')[-2:]),
                be.frame_times)

        finally:
            vm.cleanup()


if __name__ == '__main__':
    unittest.main()