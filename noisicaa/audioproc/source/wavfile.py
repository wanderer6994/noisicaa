#!/usr/bin/python3

import logging
import wave

from ..exceptions import EndOfStreamError
from ..resample import (Resampler,
                        AV_CH_LAYOUT_MONO,
                        AV_CH_LAYOUT_STEREO,
                        AV_SAMPLE_FMT_U8,
                        AV_SAMPLE_FMT_S16,
                        AV_SAMPLE_FMT_FLT)
from ..ports import AudioOutputPort
from ..node import Node
from ..frame import Frame
from ..node_types import NodeType

logger = logging.getLogger(__name__)


class WavFileSource(Node):
    desc = NodeType()
    desc.name = 'wavfile'
    desc.port('out', 'output', 'audio')
    desc.parameter('path', 'path')

    def __init__(self, path):
        super().__init__()

        self._output = AudioOutputPort('out')
        self.add_output(self._output)

        self._path = path
        self._fp = None
        self._start_pos = None
        self._timepos = None
        self._resampler = None

    def setup(self):
        super().setup()

        fp = wave.open(self._path, 'rb')

        logger.info("%s: %s", self._path, fp.getparams())

        if fp.getnchannels() == 1:
            ch_layout = AV_CH_LAYOUT_MONO
        elif fp.getnchannels() == 2:
            ch_layout = AV_CH_LAYOUT_STEREO
        else:
            raise Exception(
                "Unsupported number of channels: %d" % fp.getnchannels())

        if fp.getsampwidth() == 1:
            sample_fmt = AV_SAMPLE_FMT_U8
        elif fp.getsampwidth() == 2:
            sample_fmt = AV_SAMPLE_FMT_S16
        else:
            raise Exception(
                "Unsupported sample width: %d" % fp.getsampwidth())

        samples = fp.readframes(fp.getnframes())

        # TODO: Take output format from _output.audio_format
        resampler = Resampler(
            ch_layout, sample_fmt, fp.getframerate(),
            AV_CH_LAYOUT_STEREO, AV_SAMPLE_FMT_FLT, 44100)
        self._samples = resampler.convert(
            samples, len(samples) // (fp.getnchannels()
                                      * fp.getsampwidth()))
        self._pos = 0

        fp.close()

    def run(self, timepos):
        af = self._output.audio_format

        offset = self._pos
        length = 4096 * af.num_channels * af.bytes_per_sample
        samples = self._samples[offset:offset+length]
        self._pos += length
        if self._pos >= len(self._samples):
            self._pos = 0

        frame = Frame(af, 0, set())
        frame.append_samples(
            samples,
            len(samples) // (af.num_channels * af.bytes_per_sample))
        assert len(frame) <= 4096
        frame.resize(4096)

        self._output.frame.copy_from(frame)
