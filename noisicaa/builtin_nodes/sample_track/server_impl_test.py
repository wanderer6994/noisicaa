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

import os.path
from typing import List

from noisidev import unittest
from noisidev import unittest_mixins
from noisidev import demo_project
from noisicaa import audioproc
from noisicaa.music import pmodel_test
from noisicaa.music import project
from noisicaa.music import samples
from noisicaa.builtin_nodes import processor_message_registry_pb2
from . import server_impl


class SampleTrackConnectorTest(unittest_mixins.NodeDBMixin, unittest.AsyncTestCase):
    async def setup_testcase(self):
        self.pool = project.Pool()

        self.project = demo_project.empty(self.pool, project.BaseProject, node_db=self.node_db)
        self.track = self.pool.create(server_impl.SampleTrack, name='test')
        self.project.nodes.append(self.track)

        self.sample1 = self.pool.create(
            samples.Sample,
            path=os.path.join(unittest.TESTDATA_DIR, 'future-thunder1.wav'))
        self.project.samples.append(self.sample1)
        self.sample2 = self.pool.create(
            samples.Sample,
            path=os.path.join(unittest.TESTDATA_DIR, 'kick-gettinglaid.wav'))
        self.project.samples.append(self.sample2)

        self.messages = []  # type: List[str]

    def WhichOneof(self, msg):
        if msg.HasExtension(processor_message_registry_pb2.sample_script_add_sample):
            return 'sample_script_add_sample'
        if msg.HasExtension(processor_message_registry_pb2.sample_script_remove_sample):
            return 'sample_script_remove_sample'
        raise ValueError(msg)

    def message_cb(self, msg):
        self.assertEqual(int(msg.node_id, 16), self.track.id)
        # TODO: track the messages themselves and inspect their contents as well.
        self.messages.append(self.WhichOneof(msg))

    def test_messages_on_mutations(self):
        connector = self.track.create_node_connector(message_cb=self.message_cb)
        try:
            self.assertEqual(connector.init(), [])

            self.messages.clear()
            self.track.samples.insert(
                0,
                self.pool.create(
                    server_impl.SampleRef,
                    time=audioproc.MusicalTime(1, 4), sample=self.sample1))
            self.assertEqual(
                self.messages,
                ['sample_script_add_sample'])

            self.messages.clear()
            self.track.samples.insert(
                1,
                self.pool.create(
                    server_impl.SampleRef,
                    time=audioproc.MusicalTime(2, 4), sample=self.sample2))
            self.assertEqual(
                self.messages,
                ['sample_script_add_sample'])

            self.messages.clear()
            del self.track.samples[0]
            self.assertEqual(
                self.messages,
                ['sample_script_remove_sample'])

            self.messages.clear()
            self.track.samples[0].time = audioproc.MusicalTime(3, 4)
            self.assertEqual(
                self.messages,
                ['sample_script_remove_sample',
                 'sample_script_add_sample'])

            self.messages.clear()
            self.track.samples[0].sample = self.sample1
            self.assertEqual(
                self.messages,
                ['sample_script_remove_sample',
                 'sample_script_add_sample'])

        finally:
            connector.close()

    def test_messages_on_init(self):
        self.track.samples.insert(
            0,
            self.pool.create(
                server_impl.SampleRef,
                time=audioproc.MusicalTime(1, 4), sample=self.sample1))
        self.track.samples.insert(
            1,
            self.pool.create(
                server_impl.SampleRef,
                time=audioproc.MusicalTime(2, 4), sample=self.sample2))

        connector = self.track.create_node_connector(message_cb=self.message_cb)
        try:
            messages = connector.init()

            self.assertEqual(
                [self.WhichOneof(msg) for msg in messages],
                ['sample_script_add_sample',
                 'sample_script_add_sample'])

        finally:
            connector.close()


class SampleTrackTest(pmodel_test.TrackMixin, pmodel_test.ModelTest):
    cls = server_impl.SampleTrack
    create_args = {'name': 'test'}

    def setup_testcase(self):
        self.sample = self.pool.create(
            samples.Sample,
            path=os.path.join(unittest.TESTDATA_DIR, 'future-thunder1.wav'))

    def test_samples(self):
        track = self.pool.create(self.cls, **self.create_args)

        smpl = self.pool.create(
            server_impl.SampleRef, time=audioproc.MusicalTime(0, 4), sample=self.sample)
        track.samples.append(smpl)
        self.assertIs(track.samples[0], smpl)


class SampleRefTest(pmodel_test.ModelTest):
    def setup_testcase(self):
        self.sample = self.pool.create(
            samples.Sample,
            path=os.path.join(unittest.TESTDATA_DIR, 'future-thunder1.wav'))

    def test_time(self):
        ref = self.pool.create(
            server_impl.SampleRef, time=audioproc.MusicalTime(0, 4), sample=self.sample)

        ref.time = audioproc.MusicalTime(1, 4)
        self.assertEqual(ref.time, audioproc.MusicalTime(1, 4))

    def test_sample(self):
        ref = self.pool.create(
            server_impl.SampleRef, time=audioproc.MusicalTime(0, 4), sample=self.sample)

        smpl = self.pool.create(samples.Sample, path='/foo/bar')
        ref.sample = smpl
        self.assertIs(ref.sample, smpl)