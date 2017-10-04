#!/usr/bin/python3

# @begin:license
#
# Copyright (c) 2015-2017, Benjamin Niemann <pink@odahoda.de>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
#
# @end:license

import logging

from noisicaa import node_db

from .. import node

logger = logging.getLogger(__name__)

class TrackAudioSource(node.BuiltinNode):
    class_name = 'track_audio_source'

    def __init__(self, *, track_id, **kwargs):
        super().__init__(**kwargs)

        self.track_id = track_id

    def add_to_spec(self, spec):
        super().add_to_spec(spec)

        spec.append_opcode(
            'FETCH_BUFFER', 'track:' + self.track_id + ':left', self.outputs['out:left'].buf_name)
        spec.append_opcode(
            'FETCH_BUFFER', 'track:' + self.track_id + ':right', self.outputs['out:right'].buf_name)
