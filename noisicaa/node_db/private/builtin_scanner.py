#!/usr/bin/python3

import logging
import textwrap

from noisicaa import constants
from noisicaa import node_db

from . import scanner

logger = logging.getLogger(__name__)


class BuiltinScanner(scanner.Scanner):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def scan(self):
        yield (
            'builtin://passthru',
            node_db.UserNodeDescription(
                display_name='Mixer',
                node_cls='passthru',
                ports=[
                    node_db.AudioPortDescription(
                        name='in',
                        direction=node_db.PortDirection.Input,
                        channels='stereo'),
                    node_db.AudioPortDescription(
                        name='out',
                        direction=node_db.PortDirection.Output,
                        channels='stereo'),
                ])
        )

        yield (
            'builtin://pipeline_crasher',
            node_db.UserNodeDescription(
                display_name='PipelineCrasher',
                node_cls='pipeline_crasher',
                ports=[
                    node_db.AudioPortDescription(
                        name='in',
                        direction=node_db.PortDirection.Input,
                        channels='stereo'),
                    node_db.AudioPortDescription(
                        name='out',
                        direction=node_db.PortDirection.Output,
                        channels='stereo'),
                ],
                parameters=[
                    node_db.FloatParameterDescription(
                        name='trigger',
                        display_name='Trigger',
                        min=-1.0,
                        max=1.0,
                        default=0.0),
                ])
        )

        yield (
            'builtin://split_channel',
            node_db.UserNodeDescription(
                display_name='Split Channels',
                node_cls='split_channels',
                ports=[
                    node_db.AudioPortDescription(
                        name='in',
                        direction=node_db.PortDirection.Input,
                        channels='stereo'),
                    node_db.AudioPortDescription(
                        name='left',
                        direction=node_db.PortDirection.Output,
                        channels='mono'),
                    node_db.AudioPortDescription(
                        name='right',
                        direction=node_db.PortDirection.Output,
                        channels='mono'),
                ])
        )

        yield (
            'builtin://join_channels',
            node_db.UserNodeDescription(
                display_name='Join Channels',
                node_cls='join_channels',
                ports=[
                    node_db.AudioPortDescription(
                        name='left',
                        direction=node_db.PortDirection.Input,
                        channels='mono'),
                    node_db.AudioPortDescription(
                        name='right',
                        direction=node_db.PortDirection.Input,
                        channels='mono'),
                    node_db.AudioPortDescription(
                        name='out',
                        direction=node_db.PortDirection.Output,
                        channels='stereo'),
                ])
        )

        yield (
            'builtin://custom_csound',
            node_db.UserNodeDescription(
                display_name='Custom CSound',
                node_cls='custom_csound',
                ports=[
                    node_db.AudioPortDescription(
                        name='in',
                        direction=node_db.PortDirection.Input,
                        channels='stereo'),
                    node_db.ControlPortDescription(
                        name='ctrl',
                        direction=node_db.PortDirection.Input),
                    node_db.EventPortDescription(
                        name='ev',
                        direction=node_db.PortDirection.Input),
                    node_db.AudioPortDescription(
                        name='out',
                        direction=node_db.PortDirection.Output,
                        channels='stereo'),
                ],
                parameters=[
                    node_db.TextParameterDescription(
                        name='orchestra',
                        display_name='Orchestra Code',
                        content_type='text/csound-orchestra',
                        default=textwrap.dedent("""\
                            instr 2
                                gaOutL = gaInL
                                gaOutR = gaInR
                            endin
                        """)),
                    node_db.TextParameterDescription(
                        name='score',
                        display_name='Score',
                        content_type='text/csound-score',
                        default='i2 0 -1'),
                ])
        )