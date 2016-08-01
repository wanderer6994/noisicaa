#!/usr/bin/python3

import logging
import textwrap
import time

import numpy

from .. import csound
from .. import ports
from .. import node
from .. import node_types
from .. import frame
from .. import events

logger = logging.getLogger(__name__)


class CSoundFilter(node.Node):
    desc = node_types.NodeType()
    desc.name = 'csound_filter'
    desc.port('in', 'input', 'audio')
    desc.port('out', 'output', 'audio')

    def __init__(self, event_loop, name=None, id=None):
        super().__init__(event_loop, name, id)

        self._input = ports.AudioInputPort('in')
        self.add_input(self._input)

        self._output = ports.AudioOutputPort('out')
        self.add_output(self._output)

        self._csnd = None

    async def setup(self):
        await super().setup()

        self._csnd = csound.CSound()

        orc = textwrap.dedent("""\
            ksmps=32
            nchnls=2

            gaInL chnexport "InL", 1
            gaInR chnexport "InR", 1

            gaOutL chnexport "OutL", 2
            gaOutR chnexport "OutR", 2

            instr 1
                gaOutL, gaOutR reverbsc gaInL, gaInR, 0.6, 12000
            endin
        """)
        self._csnd.set_orchestra(orc)
        self._csnd.add_score_event(b'i1 0 3600')

    async def cleanup(self):
        if self._csnd is not None:
            self._csnd.close()
            self._csnd = None

        await super().cleanup()

    def run(self, ctxt):
        num_samples = len(self._output.frame)

        in_samples = self._input.frame.samples
        out_samples = self._output.frame.samples

        pos = 0
        while pos < num_samples:
            self._csnd.set_audio_channel_data(
                'InL', in_samples[0][pos:pos+self._csnd.ksmps])
            self._csnd.set_audio_channel_data(
                'InR', in_samples[1][pos:pos+self._csnd.ksmps])

            self._csnd.perform()

            out_samples[0][pos:pos+self._csnd.ksmps] = (
                self._csnd.get_audio_channel_data('OutL'))
            out_samples[1][pos:pos+self._csnd.ksmps] = (
                self._csnd.get_audio_channel_data('OutR'))

            pos += self._csnd.ksmps

        assert pos == num_samples


class CSoundInstrument(node.Node):
    desc = node_types.NodeType()
    desc.name = 'csound_instrument'
    desc.port('in', 'input', 'events')
    desc.port('out', 'output', 'audio')

    def __init__(self, event_loop, name=None, id=None):
        super().__init__(event_loop, name, id)

        self._input = ports.EventInputPort('in')
        self.add_input(self._input)

        self._output = ports.AudioOutputPort('out')
        self.add_output(self._output)

        self._csnd = None

    async def setup(self):
        await super().setup()

        self._csnd = csound.CSound()

        orc = textwrap.dedent("""\
            ksmps=32

            gaOutL chnexport "OutL", 2
            gaOutR chnexport "OutR", 2

            instr 1
                iPitch = p4
                iVelocity = p5

                iFreq = cpsmidinn(iPitch)
                iVolume = -20 * log10(127^2 / iVelocity^2)

                print iPitch, iFreq, iVelocity, iVolume
                gaOutL = db(iVolume) * linsegr(0, 0.08, 1, 0.1, 0.6, 0.5, 0.0) * poscil(1.0, iFreq)
                gaOutR = gaOutL
            endin
        """)
        self._csnd.set_orchestra(orc)

    async def cleanup(self):
        if self._csnd is not None:
            self._csnd.close()
            self._csnd = None

        await super().cleanup()

    def run(self, ctxt):
        self._output.frame.clear()

        num_samples = len(self._output.frame)
        out = self._output.frame.samples

        pos = 0
        timepos = ctxt.timepos
        pending_events = list(self._input.events)
        while pos < num_samples:
            while (len(pending_events) > 0
                   and pending_events[0].timepos < timepos + self._csnd.ksmps):
                event = pending_events.pop(0)
                logger.info("Consuming event %s", event)
                if isinstance(event, events.NoteOnEvent):
                    self._csnd.add_score_event(
                        b'i1 0 0.2 %d %d' % (
                            event.note.midi_note, event.volume))
                elif isinstance(event, events.NoteOffEvent):
                    pass
                else:
                    raise NotImplementedError(
                        "Event class %s not supported" % type(event).__name__)

            self._csnd.perform()

            out[0][pos:pos+self._csnd.ksmps] = (
                self._csnd.get_audio_channel_data('OutL'))
            out[1][pos:pos+self._csnd.ksmps] = (
                self._csnd.get_audio_channel_data('OutR'))

            pos += self._csnd.ksmps
            timepos += self._csnd.ksmps

        assert pos == num_samples
        assert len(pending_events) == 0