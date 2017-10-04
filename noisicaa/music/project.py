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

import base64
import email.parser
import email.policy
import email.message
import logging
import os.path
import time
import json
import textwrap

from noisicaa import core
from noisicaa.core import storage

from .pitch import Pitch
from .clef import Clef
from .key_signature import KeySignature
from .time_signature import TimeSignature
from .time import Duration
from . import beat_track
from . import score_track
from . import sample_track
from . import control_track
from . import pipeline_graph
from . import model
from . import state
from . import commands
from . import sheet
from . import misc

logger = logging.getLogger(__name__)


class AddSheet(commands.Command):
    name = core.Property(str, allow_none=True)

    def __init__(self, name=None, state=None):
        super().__init__(state=state)
        if state is None:
            self.name = name

    def run(self, project):
        assert isinstance(project, BaseProject)

        if self.name is not None:
            name = self.name
        else:
            idx = 1
            while True:
                name = 'Sheet %d' % idx
                if name not in [sheet.name for sheet in project.sheets]:
                    break
                idx += 1

        if name in [s.name for s in project.sheets]:
            raise ValueError("Sheet %s already exists" % name)
        s = sheet.Sheet(name)
        project.add_sheet(s)

commands.Command.register_command(AddSheet)


class ClearSheet(commands.Command):
    name = core.Property(str)

    def __init__(self, name=None, state=None):
        super().__init__(state=state)
        if state is None:
            self.name = name

    def run(self, project):
        assert isinstance(project, BaseProject)

        project.get_sheet(self.name).clear()

commands.Command.register_command(ClearSheet)


class DeleteSheet(commands.Command):
    name = core.Property(str)

    def __init__(self, name=None, state=None):
        super().__init__(state=state)
        if state is None:
            self.name = name

    def run(self, project):
        assert isinstance(project, BaseProject)

        assert len(project.sheets) > 1
        for idx, sheet in enumerate(project.sheets):
            if sheet.name == self.name:
                sheet.remove_from_pipeline()
                del project.sheets[idx]
                project.current_sheet = min(
                    project.current_sheet, len(project.sheets) - 1)
                return

        raise ValueError("No sheet %r" % self.name)

commands.Command.register_command(DeleteSheet)


class RenameSheet(commands.Command):
    name = core.Property(str)
    new_name = core.Property(str)

    def __init__(self, name=None, new_name=None, state=None):
        super().__init__(state=state)
        if state is None:
            self.name = name
            self.new_name = new_name

    def run(self, project):
        assert isinstance(project, BaseProject)

        if self.name == self.new_name:
            return

        if self.new_name in [s.name for s in project.sheets]:
            raise ValueError("Sheet %s already exists" % self.new_name)

        sheet = project.get_sheet(self.name)
        sheet.name = self.new_name

commands.Command.register_command(RenameSheet)


class SetCurrentSheet(commands.Command):
    name = core.Property(str)

    def __init__(self, name=None, state=None):
        super().__init__(state=state)
        if state is None:
            self.name = name

    def run(self, project):
        assert isinstance(project, BaseProject)

        project.current_sheet = project.get_sheet_index(self.name)

commands.Command.register_command(SetCurrentSheet)


class Metadata(model.Metadata, state.StateBase):
    pass

state.StateBase.register_class(Metadata)


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):  # pylint: disable=method-hidden
        if isinstance(obj, bytes):
            return {'__type__': 'bytes',
                    'value': base64.b85encode(obj).decode('ascii')}
        if isinstance(obj, Duration):
            return {'__type__': 'Duration',
                    'value': [obj.numerator, obj.denominator]}
        if isinstance(obj, Pitch):
            return {'__type__': 'Pitch',
                    'value': [obj.name]}
        if isinstance(obj, Clef):
            return {'__type__': 'Clef',
                    'value': [obj.value]}
        if isinstance(obj, KeySignature):
            return {'__type__': 'KeySignature',
                    'value': [obj.name]}
        if isinstance(obj, TimeSignature):
            return {'__type__': 'TimeSignature',
                    'value': [obj.upper, obj.lower]}
        if isinstance(obj, misc.Pos2F):
            return {'__type__': 'Pos2F',
                    'value': [obj.x, obj.y]}
        return super().default(obj)


class JSONDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, object_hook=self.object_hook, **kwargs)

    def object_hook(self, obj):  # pylint: disable=method-hidden
        objtype = obj.get('__type__', None)
        if objtype == 'bytes':
            return base64.b85decode(obj['value'])
        if objtype == 'Duration':
            return Duration(*obj['value'])
        if objtype == 'Pitch':
            return Pitch(*obj['value'])
        if objtype == 'Clef':
            return Clef(*obj['value'])
        if objtype == 'KeySignature':
            return KeySignature(*obj['value'])
        if objtype == 'TimeSignature':
            return TimeSignature(*obj['value'])
        if objtype == 'Pos2F':
            return misc.Pos2F(*obj['value'])
        return obj


class BaseProject(model.Project, state.RootMixin, state.StateBase):
    SERIALIZED_CLASS_NAME = 'Project'

    def __init__(self, *, node_db=None, state=None):
        self.listeners = core.CallbackRegistry()

        super().__init__(state)
        if state is None:
            self.metadata = Metadata()

        self.node_db = node_db

    def get_node_description(self, uri):
        return self.node_db.get_node_description(uri)

    def dispatch_command(self, obj_id, cmd):
        obj = self.get_object(obj_id)
        result = cmd.apply(obj)
        logger.info(
            "Executed command %s on %s (%d operations)",
            cmd, obj_id, len(cmd.log.ops))
        return result

    def add_sheet(self, sheet):
        self.sheets.append(sheet)
        sheet.add_pipeline_nodes()

    @classmethod
    def make_demo(cls, demo='basic', **kwargs):
        project = cls(**kwargs)
        s = sheet.Sheet(name="Demo Sheet")
        s.bpm = 140
        project.add_sheet(s)

        sheet_mixer = s.master_group.mixer_node

        if demo == 'basic':
            while len(s.property_track.measure_list) < 5:
                s.property_track.append_measure()

            track1 = score_track.ScoreTrack(
                name="Track 1",
                instrument='sf2:/usr/share/sounds/sf2/FluidR3_GM.sf2?bank=0&preset=73',
                num_measures=5)
            s.add_track(s.master_group, 0, track1)

            track2 = score_track.ScoreTrack(
                name="Track 2",
                instrument='sf2:/usr/share/sounds/sf2/FluidR3_GM.sf2?bank=0&preset=0',
                num_measures=5)
            s.add_track(s.master_group, 1, track2)

            track1.measure_list[0].measure.notes.append(
                score_track.Note(pitches=[Pitch('C5')], base_duration=Duration(1, 4)))
            track1.measure_list[0].measure.notes.append(
                score_track.Note(pitches=[Pitch('D5')], base_duration=Duration(1, 4)))
            track1.measure_list[0].measure.notes.append(
                score_track.Note(pitches=[Pitch('E5')], base_duration=Duration(1, 4)))
            track1.measure_list[0].measure.notes.append(
                score_track.Note(pitches=[Pitch('F5')], base_duration=Duration(1, 4)))

            track1.measure_list[1].measure.notes.append(
                score_track.Note(pitches=[Pitch('C5')], base_duration=Duration(1, 2)))
            track1.measure_list[1].measure.notes.append(
                score_track.Note(pitches=[Pitch('F5')], base_duration=Duration(1, 8)))
            track1.measure_list[1].measure.notes.append(
                score_track.Note(pitches=[Pitch('E5')], base_duration=Duration(1, 8)))
            track1.measure_list[1].measure.notes.append(
                score_track.Note(pitches=[Pitch('D5')], base_duration=Duration(1, 4)))

            track1.measure_list[2].measure.notes.append(
                score_track.Note(pitches=[Pitch('C5')], base_duration=Duration(1, 4)))
            track1.measure_list[2].measure.notes.append(
                score_track.Note(pitches=[Pitch('D5')], base_duration=Duration(1, 4)))
            track1.measure_list[2].measure.notes.append(
                score_track.Note(pitches=[Pitch('E5')], base_duration=Duration(1, 4)))
            track1.measure_list[2].measure.notes.append(
                score_track.Note(pitches=[Pitch('F5')], base_duration=Duration(1, 4)))

            track1.measure_list[3].measure.notes.append(
                score_track.Note(pitches=[Pitch('C5')], base_duration=Duration(1, 2)))
            track1.measure_list[3].measure.notes.append(
                score_track.Note(pitches=[Pitch('F5')], base_duration=Duration(1, 8)))
            track1.measure_list[3].measure.notes.append(
                score_track.Note(pitches=[Pitch('E5')], base_duration=Duration(1, 8)))
            track1.measure_list[3].measure.notes.append(
                score_track.Note(pitches=[Pitch('D5')], base_duration=Duration(1, 4)))

            track1.measure_list[4].measure.notes.append(
                score_track.Note(pitches=[Pitch('C5')], base_duration=Duration(1, 1)))


            track2.measure_list[0].measure.notes.append(
                score_track.Note(pitches=[Pitch('C4'), Pitch('E3'), Pitch('G3')],
                     base_duration=Duration(1, 1)))
            track2.measure_list[1].measure.notes.append(
                score_track.Note(pitches=[Pitch('F3'), Pitch('A4'), Pitch('C4')],
                     base_duration=Duration(1, 1)))

            track2.measure_list[2].measure.notes.append(
                score_track.Note(pitches=[Pitch('A3'), Pitch('C4'), Pitch('E4')],
                     base_duration=Duration(1, 1)))
            track2.measure_list[3].measure.notes.append(
                score_track.Note(pitches=[Pitch('C4'), Pitch('E3'), Pitch('G3')],
                     base_duration=Duration(1, 1)))

            track2.measure_list[4].measure.notes.append(
                score_track.Note(pitches=[Pitch('C4'), Pitch('E3'), Pitch('G3')],
                     base_duration=Duration(1, 1)))

        elif demo == 'complex':
            while len(s.property_track.measure_list) < 4:
                s.property_track.append_measure()

            track1 = score_track.ScoreTrack(
                name="Track 1",
                instrument='sf2:/usr/share/sounds/sf2/FluidR3_GM.sf2?bank=0&preset=0',
                num_measures=4)
            s.add_track(s.master_group, 0, track1)

            track1_mixer = track1.mixer_node

            track1_mixer.set_port_parameters('out:left', volume=0.2)
            track1_mixer.set_port_parameters('out:right', volume=0.2)

            for connection in s.pipeline_graph_connections:
                if (connection.source_node.id == track1_mixer.id
                    and connection.source_port == 'out:left'):
                    assert connection.dest_node.id == sheet_mixer.id
                    assert connection.dest_port == 'in:left'
                    s.remove_pipeline_graph_connection(connection)
                    break
            else:
                raise AssertionError("Connection not found.")

            for connection in s.pipeline_graph_connections:
                if (connection.source_node.id == track1_mixer.id
                    and connection.source_port == 'out:right'):
                    assert connection.dest_node.id == sheet_mixer.id
                    assert connection.dest_port == 'in:right'
                    s.remove_pipeline_graph_connection(connection)
                    break
            else:
                raise AssertionError("Connection not found.")

            eq_node_uri = 'ladspa://dj_eq_1901.so/dj_eq'
            eq_node = pipeline_graph.PipelineGraphNode(
                name='EQ',
                node_uri=eq_node_uri)
            s.add_pipeline_graph_node(eq_node)
            eq_node.set_control_value('Lo gain (dB)', -40.0)
            eq_node.set_control_value('Mid gain (dB)', 0.0)
            eq_node.set_control_value('Hi gain (dB)', 5.0)

            filter_node_uri = 'builtin://custom_csound'
            filter_node = pipeline_graph.PipelineGraphNode(
                name='Filter',
                node_uri=filter_node_uri)
            s.add_pipeline_graph_node(filter_node)
            filter_node.set_parameter(
                'orchestra',
                textwrap.dedent('''\
                    instr 2
                        printk(0.5, k(gaCtrl))
                        gaOutLeft = butterlp(gaInLeft, 200 + 2000 * gaCtrl)
                        gaOutRight = butterlp(gaInRight, 200 + 2000 * gaCtrl)
                    endin
                '''))

            s.add_pipeline_graph_connection(
                pipeline_graph.PipelineGraphConnection(
                    source_node=track1_mixer, source_port='out:left',
                    dest_node=eq_node, dest_port='Input L'))
            s.add_pipeline_graph_connection(
                pipeline_graph.PipelineGraphConnection(
                    source_node=track1_mixer, source_port='out:right',
                    dest_node=eq_node, dest_port='Input R'))

            s.add_pipeline_graph_connection(
                pipeline_graph.PipelineGraphConnection(
                    source_node=eq_node, source_port='Output L',
                    dest_node=filter_node, dest_port='in:left'))
            s.add_pipeline_graph_connection(
                pipeline_graph.PipelineGraphConnection(
                    source_node=eq_node, source_port='Output R',
                    dest_node=filter_node, dest_port='in:right'))

            s.add_pipeline_graph_connection(
                pipeline_graph.PipelineGraphConnection(
                    source_node=filter_node, source_port='out:left',
                    dest_node=sheet_mixer, dest_port='in:left'))
            s.add_pipeline_graph_connection(
                pipeline_graph.PipelineGraphConnection(
                    source_node=filter_node, source_port='out:right',
                    dest_node=sheet_mixer, dest_port='in:right'))

            for i in range(4):
                track1.measure_list[i].measure.notes.append(
                    score_track.Note(pitches=[Pitch('C4')], base_duration=Duration(1, 4)))
                track1.measure_list[i].measure.notes.append(
                    score_track.Note(pitches=[Pitch('E4')], base_duration=Duration(1, 4)))
                track1.measure_list[i].measure.notes.append(
                    score_track.Note(pitches=[Pitch('G4')], base_duration=Duration(1, 2)))

            track2 = beat_track.BeatTrack(
                name="Track 2",
                instrument='sample:' + os.path.abspath(os.path.join(
                    os.path.dirname(__file__), 'testdata', 'kick-gettinglaid.wav')),
                num_measures=4)
            track2.pitch = Pitch('C4')
            s.add_track(s.master_group, 1, track2)

            track2_mixer = track2.mixer_node

            for connection in s.pipeline_graph_connections:
                if (connection.source_node.id == track2_mixer.id
                    and connection.source_port == 'out:left'):
                    assert connection.dest_node.id == sheet_mixer.id
                    assert connection.dest_port == 'in:left'
                    s.remove_pipeline_graph_connection(connection)
                    break
            else:
                raise AssertionError("Connection not found.")

            for connection in s.pipeline_graph_connections:
                if (connection.source_node.id == track2_mixer.id
                    and connection.source_port == 'out:right'):
                    assert connection.dest_node.id == sheet_mixer.id
                    assert connection.dest_port == 'in:right'
                    s.remove_pipeline_graph_connection(connection)
                    break
            else:
                raise AssertionError("Connection not found.")

            delay_node_uri = 'http://drobilla.net/plugins/mda/Delay'
            delay_node = pipeline_graph.PipelineGraphNode(
                name='Delay',
                node_uri=delay_node_uri)
            s.add_pipeline_graph_node(delay_node)
            delay_node.set_control_value('l_delay', 0.3)
            delay_node.set_control_value('r_delay', 0.31)

            reverb_node_uri = 'builtin://csound/reverb'
            reverb_node = pipeline_graph.PipelineGraphNode(
                name='Reverb',
                node_uri=reverb_node_uri)
            s.add_pipeline_graph_node(reverb_node)

            s.add_pipeline_graph_connection(
                pipeline_graph.PipelineGraphConnection(
                    source_node=track2_mixer, source_port='out:left',
                    dest_node=delay_node, dest_port='left_in'))
            s.add_pipeline_graph_connection(
                pipeline_graph.PipelineGraphConnection(
                    source_node=track2_mixer, source_port='out:right',
                    dest_node=delay_node, dest_port='right_in'))

            s.add_pipeline_graph_connection(
                pipeline_graph.PipelineGraphConnection(
                    source_node=delay_node, source_port='left_out',
                    dest_node=reverb_node, dest_port='in:left'))
            s.add_pipeline_graph_connection(
                pipeline_graph.PipelineGraphConnection(
                    source_node=delay_node, source_port='right_out',
                    dest_node=reverb_node, dest_port='in:right'))

            s.add_pipeline_graph_connection(
                pipeline_graph.PipelineGraphConnection(
                    source_node=reverb_node, source_port='out:left',
                    dest_node=sheet_mixer, dest_port='in:left'))
            s.add_pipeline_graph_connection(
                pipeline_graph.PipelineGraphConnection(
                    source_node=reverb_node, source_port='out:right',
                    dest_node=sheet_mixer, dest_port='in:right'))

            for i in range(4):
                track2.measure_list[i].measure.beats.append(
                    beat_track.Beat(timepos=Duration(0, 4), velocity=100))
                track2.measure_list[i].measure.beats.append(
                    beat_track.Beat(timepos=Duration(1, 4), velocity=80))
                track2.measure_list[i].measure.beats.append(
                    beat_track.Beat(timepos=Duration(2, 4), velocity=60))
                track2.measure_list[i].measure.beats.append(
                    beat_track.Beat(timepos=Duration(3, 4), velocity=40))

            track3 = sample_track.SampleTrack(
                name="Track 3")
            s.add_track(s.master_group, 2, track3)

            smpl = sample_track.Sample(
                path=os.path.abspath(os.path.join(
                    os.path.dirname(__file__), 'testdata', 'future-thunder1.wav')))
            s.samples.append(smpl)

            track3.samples.append(
                sample_track.SampleRef(timepos=Duration(2, 4), sample_id=smpl.id))
            track3.samples.append(
                sample_track.SampleRef(timepos=Duration(14, 4), sample_id=smpl.id))

            track4 = control_track.ControlTrack(
                name="Track 4")
            s.add_track(s.master_group, 3, track4)

            track4.points.append(
                control_track.ControlPoint(timepos=Duration(0, 4), value=1.0))
            track4.points.append(
                control_track.ControlPoint(timepos=Duration(4, 4), value=0.0))
            track4.points.append(
                control_track.ControlPoint(timepos=Duration(8, 4), value=1.0))

            s.add_pipeline_graph_connection(
                pipeline_graph.PipelineGraphConnection(
                    source_node=track4.control_source_node, source_port='out',
                    dest_node=filter_node, dest_port='ctrl'))

        return project


class Project(BaseProject):
    VERSION = 1
    SUPPORTED_VERSIONS = [1]

    def __init__(self, state=None, **kwargs):
        super().__init__(state=state, **kwargs)

        self.storage = None

    @property
    def closed(self):
        return self.storage is None

    @property
    def path(self):
        if self.storage:
            return self.storage.path
        return None

    @property
    def data_dir(self):
        if self.storage:
            return self.storage.data_dir
        return None

    def open(self, path):
        assert self.storage is None

        self.storage = storage.ProjectStorage()
        self.storage.open(path)

        checkpoint_number, actions = self.storage.get_restore_info()

        serialized_checkpoint = self.storage.get_checkpoint(
            checkpoint_number)

        self.load_from_checkpoint(serialized_checkpoint)
        for action, log_number in actions:
            cmd_data = self.storage.get_log_entry(log_number)
            cmd, obj_id = self.deserialize_command(cmd_data)
            logger.info(
                "Replay action %s of command %s on %s (%d operations)",
                action, cmd, obj_id, len(cmd.log.ops))
            obj = self.get_object(obj_id)

            if action == storage.ACTION_FORWARD:
                cmd.redo(obj)
            elif action == storage.ACTION_BACKWARD:
                cmd.undo(obj)
            else:
                raise ValueError("Unsupported action %s" % action)

    def create(self, path):
        assert self.storage is None

        self.storage = storage.ProjectStorage.create(path)

        # Write initial checkpoint of an empty project.
        self.create_checkpoint()

    def close(self):
        if self.storage is not None:
            self.storage.close()
            self.storage = None

        self.listeners.clear()
        self.reset_state()

    def load_from_checkpoint(self, checkpoint_data):
        parser = email.parser.BytesParser()
        message = parser.parsebytes(checkpoint_data)

        version = int(message['Version'])
        if version not in self.SUPPORTED_VERSIONS:
            raise storage.UnsupportedFileVersionError()

        if message.get_content_type() != 'application/json':
            raise storage.CorruptedProjectError(
                "Unexpected content type %s" % message.get_content_type())

        serialized_checkpoint = message.get_payload()

        checkpoint = json.loads(serialized_checkpoint, cls=JSONDecoder)

        self.deserialize(checkpoint)
        self.init_references()

        def validate_node(root, parent, node):
            assert node.parent is parent, (node.parent, parent)
            assert node.root is root, (node.root, root)

            for c in node.list_children():
                validate_node(root, node, c)

        validate_node(self, None, self)

    def create_checkpoint(self):
        policy = email.policy.compat32.clone(
            linesep='\n',
            max_line_length=0,
            cte_type='8bit',
            raise_on_defect=True)
        message = email.message.Message(policy)

        message['Version'] = str(self.VERSION)
        message['Content-Type'] = 'application/json; charset=utf-8'

        checkpoint = json.dumps(
            self.serialize(),
            ensure_ascii=False, indent='  ', sort_keys=True,
            cls=JSONEncoder)
        serialized_checkpoint = checkpoint.encode('utf-8')
        message.set_payload(serialized_checkpoint)

        checkpoint_data = message.as_bytes()
        self.storage.add_checkpoint(checkpoint_data)

    def serialize_command(self, cmd, target_id, now):
        serialized = json.dumps(
            cmd.serialize(),
            ensure_ascii=False, indent='  ', sort_keys=True,
            cls=JSONEncoder)

        policy = email.policy.compat32.clone(
            linesep='\n',
            max_line_length=0,
            cte_type='8bit',
            raise_on_defect=True)
        message = email.message.Message(policy)
        message['Version'] = str(self.VERSION)
        message['Content-Type'] = 'application/json; charset=utf-8'
        message['Target'] = target_id
        message['Time'] = time.ctime(now)
        message['Timestamp'] = '%d' % now
        message.set_payload(serialized.encode('utf-8'))

        return message.as_bytes()

    def deserialize_command(self, cmd_data):
        parser = email.parser.BytesParser()
        message = parser.parsebytes(cmd_data)

        target_id = message['Target']
        cmd_state = json.loads(message.get_payload(), cls=JSONDecoder)
        cmd = commands.Command.create_from_state(cmd_state)

        return cmd, target_id

    def dispatch_command(self, obj_id, cmd):
        if self.closed:
            raise RuntimeError(
                "Command %s executed on closed project." % cmd)

        now = time.time()
        result = super().dispatch_command(obj_id, cmd)

        if not cmd.is_noop:
            self.storage.append_log_entry(
                self.serialize_command(cmd, obj_id, now))

            if self.storage.logs_since_last_checkpoint > 1000:
                self.create_checkpoint()

        return result

    def undo(self):
        if self.closed:
            raise RuntimeError("Undo executed on closed project.")

        if self.storage.can_undo:
            action, cmd_data = self.storage.get_log_entry_to_undo()
            cmd, obj_id = self.deserialize_command(cmd_data)
            logger.info(
                "Undo command %s on %s (%d operations)",
                cmd, obj_id, len(cmd.log.ops))
            obj = self.get_object(obj_id)

            if action == storage.ACTION_FORWARD:
                cmd.redo(obj)
            elif action == storage.ACTION_BACKWARD:
                cmd.undo(obj)
            else:
                raise ValueError("Unsupported action %s" % action)

            self.storage.undo()

    def redo(self):
        if self.closed:
            raise RuntimeError("Redo executed on closed project.")

        if self.storage.can_redo:
            action, cmd_data = self.storage.get_log_entry_to_redo()
            cmd, obj_id = self.deserialize_command(cmd_data)
            logger.info(
                "Redo command %s on %s (%d operations)",
                cmd, obj_id, len(cmd.log.ops))
            obj = self.get_object(obj_id)

            if action == storage.ACTION_FORWARD:
                cmd.redo(obj)
            elif action == storage.ACTION_BACKWARD:
                cmd.undo(obj)
            else:
                raise ValueError("Unsupported action %s" % action)

            self.storage.redo()
