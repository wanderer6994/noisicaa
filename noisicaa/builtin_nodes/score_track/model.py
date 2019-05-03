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

import fractions
import logging
from typing import cast, Any, MutableSequence, Optional, Iterator, Iterable, Callable

from noisicaa.core.typing_extra import down_cast
from noisicaa import core
from noisicaa import audioproc
from noisicaa import value_types
from noisicaa import node_db
from noisicaa import model_base
from noisicaa.music import commands
from noisicaa.music import model
from noisicaa.music import base_track
from noisicaa.builtin_nodes import commands_registry_pb2
from noisicaa.builtin_nodes import model_registry_pb2
from . import commands_pb2
from . import node_description

logger = logging.getLogger(__name__)


class UpdateScoreTrack(commands.Command):
    proto_type = 'update_score_track'
    proto_ext = commands_registry_pb2.update_score_track

    def run(self) -> None:
        pb = down_cast(commands_pb2.UpdateScoreTrack, self.pb)
        track = down_cast(ScoreTrack, self.pool[pb.track_id])

        if pb.HasField('set_transpose_octaves'):
            track.transpose_octaves = pb.set_transpose_octaves


class UpdateScoreMeasure(commands.Command):
    proto_type = 'update_score_measure'
    proto_ext = commands_registry_pb2.update_score_measure

    def run(self) -> None:
        pb = down_cast(commands_pb2.UpdateScoreMeasure, self.pb)
        measure = down_cast(ScoreMeasure, self.pool[pb.measure_id])

        if pb.HasField('set_clef'):
            measure.clef = value_types.Clef.from_proto(pb.set_clef)

        if pb.HasField('set_key_signature'):
            measure.key_signature = value_types.KeySignature.from_proto(pb.set_key_signature)


class CreateNote(commands.Command):
    proto_type = 'create_note'
    proto_ext = commands_registry_pb2.create_note

    def run(self) -> None:
        pb = down_cast(commands_pb2.CreateNote, self.pb)
        measure = down_cast(ScoreMeasure, self.pool[pb.measure_id])

        assert 0 <= pb.idx <= len(measure.notes)
        note = self.pool.create(
            Note,
            pitches=[value_types.Pitch.from_proto(pb.pitch)],
            base_duration=audioproc.MusicalDuration.from_proto(pb.duration))
        measure.notes.insert(pb.idx, note)


class UpdateNote(commands.Command):
    proto_type = 'update_note'
    proto_ext = commands_registry_pb2.update_note

    def run(self) -> None:
        pb = down_cast(commands_pb2.UpdateNote, self.pb)
        note = down_cast(Note, self.pool[pb.note_id])

        if pb.HasField('set_pitch'):
            note.pitches[0] = value_types.Pitch.from_proto(pb.set_pitch)

        if pb.HasField('add_pitch'):
            pitch = value_types.Pitch.from_proto(pb.add_pitch)
            if pitch not in note.pitches:
                note.pitches.append(pitch)

        if pb.HasField('remove_pitch'):
            assert 0 <= pb.remove_pitch < len(note.pitches)
            del note.pitches[pb.remove_pitch]

        if pb.HasField('set_duration'):
            note.base_duration = audioproc.MusicalDuration.from_proto(pb.set_duration)

        if pb.HasField('set_dots'):
            if pb.set_dots > note.max_allowed_dots:
                raise ValueError("Too many dots on note")
            note.dots = pb.set_dots

        if pb.HasField('set_tuplet'):
            if pb.set_tuplet not in (0, 3, 5):
                raise ValueError("Invalid tuplet type")
            note.tuplet = pb.set_tuplet

        if pb.HasField('set_accidental'):
            assert 0 <= pb.set_accidental.pitch_idx < len(note.pitches)
            note.pitches[pb.set_accidental.pitch_idx] = (
                note.pitches[pb.set_accidental.pitch_idx].add_accidental(
                    pb.set_accidental.accidental))

        if pb.HasField('transpose'):
            for pidx, pitch in enumerate(note.pitches):
                note.pitches[pidx] = pitch.transposed(
                    half_notes=pb.transpose % 12,
                    octaves=pb.transpose // 12)


class DeleteNote(commands.Command):
    proto_type = 'delete_note'
    proto_ext = commands_registry_pb2.delete_note

    def run(self) -> None:
        pb = down_cast(commands_pb2.DeleteNote, self.pb)
        note = down_cast(Note, self.pool[pb.note_id])
        measure = note.measure
        del measure.notes[note.index]


class ScoreTrackConnector(base_track.MeasuredTrackConnector):
    _node = None  # type: ScoreTrack

    def _add_track_listeners(self) -> None:
        self._listeners['transpose_octaves'] = self._node.transpose_octaves_changed.add(
            self.__transpose_octaves_changed)

    def _add_measure_listeners(self, mref: base_track.MeasureReference) -> None:
        measure = down_cast(ScoreMeasure, mref.measure)
        self._listeners['measure:%s:notes' % mref.id] = measure.content_changed.add(
            lambda _=None: self.__measure_notes_changed(mref))  # type: ignore

    def _remove_measure_listeners(self, mref: base_track.MeasureReference) -> None:
        self._listeners.pop('measure:%s:notes' % mref.id).remove()

    def _create_events(
            self, time: audioproc.MusicalTime, measure: base_track.Measure
    ) -> Iterator[base_track.PianoRollInterval]:
        measure = down_cast(ScoreMeasure, measure)
        for note in measure.notes:
            if not note.is_rest:
                for pitch in note.pitches:
                    pitch = pitch.transposed(octaves=self._node.transpose_octaves)
                    event = base_track.PianoRollInterval(
                        time, time + note.duration, pitch, 127)
                    yield event

            time += note.duration

    def __transpose_octaves_changed(self, change: model_base.PropertyChange) -> None:
        self._update_measure_range(0, len(self._node.measure_list))

    def __measure_notes_changed(self, mref: base_track.MeasureReference) -> None:
        self._update_measure_range(mref.index, mref.index + 1)


class Note(model.ProjectChild):
    class NoteSpec(model_base.ObjectSpec):
        proto_type = 'note'
        proto_ext = model_registry_pb2.note

        pitches = model_base.WrappedProtoListProperty(value_types.Pitch)
        base_duration = model_base.WrappedProtoProperty(
            audioproc.MusicalDuration,
            default=audioproc.MusicalDuration(1, 4))
        dots = model_base.Property(int, default=0)
        tuplet = model_base.Property(int, default=0)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self.pitches_changed = core.Callback[model_base.PropertyListChange[value_types.Pitch]]()
        self.base_duration_changed = \
            core.Callback[model_base.PropertyChange[audioproc.MusicalDuration]]()
        self.dots_changed = core.Callback[model_base.PropertyChange[int]]()
        self.tuplet_changed = core.Callback[model_base.PropertyChange[int]]()

    def __str__(self) -> str:
        n = ''
        if len(self.pitches) == 1:
            n += str(self.pitches[0])
        else:
            n += '[' + ''.join(str(p) for p in self.pitches) + ']'

        duration = self.duration
        if duration.numerator == 1:
            n += '/%d' % duration.denominator
        elif duration.denominator == 1:
            n += ';%d' % duration.numerator
        else:
            n += ';%d/%d' % (duration.numerator, duration.denominator)

        return n

    def create(
            self, *,
            pitches: Optional[Iterable[value_types.Pitch]] = None,
            base_duration: Optional[audioproc.MusicalDuration] = None,
            dots: int = 0, tuplet: int = 0,
            **kwargs: Any) -> None:
        super().create(**kwargs)

        if pitches is not None:
            self.pitches.extend(pitches)
        if base_duration is None:
            base_duration = audioproc.MusicalDuration(1, 4)
        self.base_duration = base_duration
        self.dots = dots
        self.tuplet = tuplet

        assert (self.base_duration.numerator == 1
                and self.base_duration.denominator in (1, 2, 4, 8, 16, 32)), \
            self.base_duration

    @property
    def pitches(self) -> MutableSequence[value_types.Pitch]:
        return self.get_property_value('pitches')

    @property
    def base_duration(self) -> audioproc.MusicalDuration:
        return self.get_property_value('base_duration')

    @base_duration.setter
    def base_duration(self, value: audioproc.MusicalDuration) -> None:
        self.set_property_value('base_duration', value)

    @property
    def dots(self) -> int:
        return self.get_property_value('dots')

    @dots.setter
    def dots(self, value: int) -> None:
        self.set_property_value('dots', value)

    @property
    def tuplet(self) -> int:
        return self.get_property_value('tuplet')

    @tuplet.setter
    def tuplet(self, value: int) -> None:
        self.set_property_value('tuplet', value)

    @property
    def measure(self) -> 'ScoreMeasure':
        return cast(ScoreMeasure, self.parent)

    @property
    def is_rest(self) -> bool:
        pitches = self.pitches
        return len(pitches) == 1 and pitches[0].is_rest

    @property
    def max_allowed_dots(self) -> int:
        base_duration = self.base_duration
        if base_duration <= audioproc.MusicalDuration(1, 32):
            return 0
        if base_duration <= audioproc.MusicalDuration(1, 16):
            return 1
        if base_duration <= audioproc.MusicalDuration(1, 8):
            return 2
        return 3

    @property
    def duration(self) -> audioproc.MusicalDuration:
        duration = self.base_duration
        dots = self.dots
        tuplet = self.tuplet
        for _ in range(dots):
            duration *= fractions.Fraction(3, 2)
        if tuplet == 3:
            duration *= fractions.Fraction(2, 3)
        elif tuplet == 5:
            duration *= fractions.Fraction(4, 5)
        return audioproc.MusicalDuration(duration)

    def property_changed(self, change: model_base.PropertyChange) -> None:
        super().property_changed(change)
        if self.measure is not None:
            self.measure.content_changed.call()


class ScoreMeasure(base_track.Measure):
    class ScoreMeasureSpec(model_base.ObjectSpec):
        proto_type = 'score_measure'
        proto_ext = model_registry_pb2.score_measure

        clef = model_base.WrappedProtoProperty(value_types.Clef, default=value_types.Clef.Treble)
        key_signature = model_base.WrappedProtoProperty(
            value_types.KeySignature,
            default=value_types.KeySignature('C major'))
        notes = model_base.ObjectListProperty(Note)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self.clef_changed = core.Callback[model_base.PropertyChange[value_types.Clef]]()
        self.key_signature_changed = \
            core.Callback[model_base.PropertyChange[value_types.KeySignature]]()
        self.notes_changed = core.Callback[model_base.PropertyListChange[Note]]()

        self.content_changed = core.Callback[None]()

    def setup(self) -> None:
        super().setup()

        self.notes_changed.add(lambda _: self.content_changed.call())

    @property
    def clef(self) -> value_types.Clef:
        return self.get_property_value('clef')

    @clef.setter
    def clef(self, value: value_types.Clef) -> None:
        self.set_property_value('clef', value)

    @property
    def key_signature(self) -> value_types.KeySignature:
        return self.get_property_value('key_signature')

    @key_signature.setter
    def key_signature(self, value: value_types.KeySignature) -> None:
        self.set_property_value('key_signature', value)

    @property
    def notes(self) -> MutableSequence[Note]:
        return self.get_property_value('notes')

    @property
    def track(self) -> 'ScoreTrack':
        return down_cast(ScoreTrack, super().track)

    @property
    def empty(self) -> bool:
        return len(self.notes) == 0


class ScoreTrack(base_track.MeasuredTrack):
    class ScoreTrackSpec(model_base.ObjectSpec):
        proto_type = 'score_track'
        proto_ext = model_registry_pb2.score_track

        transpose_octaves = model_base.Property(int, default=0)

    measure_cls = ScoreMeasure

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self.transpose_octaves_changed = core.Callback[model_base.PropertyChange[int]]()

    def create(self, *, num_measures: int = 1, **kwargs: Any) -> None:
        super().create(**kwargs)

        for _ in range(num_measures):
            self.append_measure()

    @property
    def transpose_octaves(self) -> int:
        return self.get_property_value('transpose_octaves')

    @transpose_octaves.setter
    def transpose_octaves(self, value: int) -> None:
        self.set_property_value('transpose_octaves', value)

    def create_empty_measure(self, ref: Optional[base_track.Measure]) -> ScoreMeasure:
        measure = down_cast(ScoreMeasure, super().create_empty_measure(ref))

        if ref is not None:
            ref = down_cast(ScoreMeasure, ref)
            measure.key_signature = ref.key_signature
            measure.clef = ref.clef

        return measure

    def create_node_connector(
            self,
            message_cb: Callable[[audioproc.ProcessorMessage], None],
            audioproc_client: audioproc.AbstractAudioProcClient,
    ) -> ScoreTrackConnector:
        return ScoreTrackConnector(
            node=self, message_cb=message_cb, audioproc_client=audioproc_client)

    @property
    def description(self) -> node_db.NodeDescription:
        return node_description.ScoreTrackDescription
