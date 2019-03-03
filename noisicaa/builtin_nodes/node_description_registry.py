#!/usr/bin/python3

# @begin:license
#
# Copyright (c) 2015-2019, Benjamin Niemann <pink@odahoda.de>
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

from typing import Iterator

from noisicaa import node_db
from .score_track.node_description import ScoreTrackDescription
from .beat_track.node_description import BeatTrackDescription
from .control_track.node_description import ControlTrackDescription
from .sample_track.node_description import SampleTrackDescription
from .instrument.node_description import InstrumentDescription
from .mixer.node_description import MixerDescription
from .custom_csound.node_description import CustomCSoundDescription
from .midi_source.node_description import MidiSourceDescription


def node_descriptions() -> Iterator[node_db.NodeDescription]:
    yield ScoreTrackDescription
    yield BeatTrackDescription
    yield ControlTrackDescription
    yield SampleTrackDescription
    yield InstrumentDescription
    yield MixerDescription
    yield CustomCSoundDescription
    yield MidiSourceDescription