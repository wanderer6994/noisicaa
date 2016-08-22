#!/usr/bin/python3

import logging
import textwrap
import time

import numpy

from noisicaa.music import node_description

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

    def __init__(self, event_loop, description, name=None, id=None):
        super().__init__(event_loop, name, id)

        self._description = description

        port_cls_map = {
            (node_description.PortType.Audio,
             node_description.PortDirection.Input): ports.AudioInputPort,
            (node_description.PortType.Audio,
             node_description.PortDirection.Output): ports.AudioOutputPort,
            (node_description.PortType.Events,
             node_description.PortDirection.Input): ports.EventInputPort,
            (node_description.PortType.Events,
             node_description.PortDirection.Output): ports.EventOutputPort,
        }

        for port_desc in self._description.ports:
            port_cls = port_cls_map[
                (port_desc.port_type, port_desc.direction)]
            port = port_cls(port_desc.name)
            if port_desc.direction == node_description.PortDirection.Input:
                self.add_input(port)
            else:
                self.add_output(port)

        self._parameters = {}
        for parameter in self._description.parameters:
            if parameter.param_type == node_description.ParameterType.Float:
                self._parameters[parameter.name] = parameter.default

        self._csnd = None
        self._code = self._description.get_parameter('code').value

    def set_param(self, **kwargs):
        for parameter_name, value in kwargs.items():
            assert parameter_name in self._parameters
            assert isinstance(value, float)
            self._parameters[parameter_name] = value

    async def setup(self):
        await super().setup()

        self._csnd = csound.CSound()

        self._csnd.set_orchestra(self._code)
        self._csnd.add_score_event(b'i1 0 3600')

    async def cleanup(self):
        if self._csnd is not None:
            self._csnd.close()
            self._csnd = None

        await super().cleanup()

    def run(self, ctxt):
        in_samples = {}
        for port in self.inputs.values():
            assert len(port.frame) == ctxt.duration
            in_samples[port.name] = port.frame.samples

        out_samples = {}
        for port in self.outputs.values():
            port.frame.resize(ctxt.duration)
            out_samples[port.name] = port.frame.samples

        pos = 0
        while pos < ctxt.duration:
            for port_name, samples in in_samples.items():
                self._csnd.set_audio_channel_data(
                    '%s/left' % port_name,
                    samples[0][pos:pos+self._csnd.ksmps])
                self._csnd.set_audio_channel_data(
                    '%s/right' % port_name,
                    samples[1][pos:pos+self._csnd.ksmps])

            for parameter in self._description.parameters:
                if parameter.param_type == node_description.ParameterType.Float:
                    self._csnd.set_control_channel_value(
                        parameter.name, self._parameters[parameter.name])

            self._csnd.perform()

            for port_name, samples in out_samples.items():
                samples[0][pos:pos+self._csnd.ksmps] = (
                    self._csnd.get_audio_channel_data(
                        '%s/left' % port_name))
                samples[1][pos:pos+self._csnd.ksmps] = (
                    self._csnd.get_audio_channel_data(
                        '%s/right' % port_name))

            pos += self._csnd.ksmps

        assert pos == ctxt.duration


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
        sample_pos = ctxt.sample_pos
        pending_events = list(self._input.events)
        while pos < num_samples:
            while (len(pending_events) > 0
                   and pending_events[0].sample_pos < sample_pos + self._csnd.ksmps):
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
            sample_pos += self._csnd.ksmps

        assert pos == num_samples
        assert len(pending_events) == 0
