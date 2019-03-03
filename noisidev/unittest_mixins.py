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

import asyncio
import logging
import urllib.parse

from noisicaa import core
from noisicaa import editor_main_pb2
from noisicaa.core import empty_message_pb2
from noisicaa.core import ipc
from noisicaa.constants import TEST_OPTS
from noisicaa.node_db.private import db as node_db

logger = logging.getLogger(__name__)


class ServerMixin(object):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.server = None

    async def setup_testcase(self):
        self.server = ipc.Server(self.loop, 'test', socket_dir=TEST_OPTS.TMP_DIR)
        await self.server.setup()

    async def cleanup_testcase(self):
        if self.server is not None:
            await self.server.cleanup()


class NodeDBMixin(object):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.node_db = None

    def setup_testcase(self):
        self.node_db = node_db.NodeDB()
        self.node_db.setup()

    def cleanup_testcase(self):
        if self.node_db is not None:
            self.node_db.cleanup()


class ProcessManagerMixin(object):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.process_manager = None
        self.process_manager_client = None

        self.__node_db_address = None
        self.__node_db_lock = None

        self.__instrument_db_address = None
        self.__instrument_db_lock = None

        self.__urid_mapper_address = None
        self.__urid_mapper_lock = None

    async def setup_testcase(self):
        self.process_manager = core.ProcessManager(event_loop=self.loop, tmp_dir=TEST_OPTS.TMP_DIR)
        await self.process_manager.setup()

        async def shutdown_process(request, response):
            await self.process_manager.shutdown_process(request.address)
        self.process_manager.server['main'].add_handler(
            'SHUTDOWN_PROCESS', shutdown_process,
            editor_main_pb2.ShutdownProcessRequest, empty_message_pb2.EmptyMessage)

        self.process_manager_client = ipc.Stub(
            self.loop, self.process_manager.server.address)
        await self.process_manager_client.connect()

        self.__node_db_lock = asyncio.Lock(loop=self.loop)
        self.__instrument_db_lock = asyncio.Lock(loop=self.loop)
        self.__urid_mapper_lock = asyncio.Lock(loop=self.loop)

    async def __shutdown_process(self, address):
        if address is None:
            return

        p = urllib.parse.urlparse(address)
        control_address = 'ipc://control@%s' % p.path

        try:
            stub = ipc.Stub(self.loop, control_address)
            try:
                await stub.connect()
                await stub.call('SHUTDOWN')
            finally:
                await stub.close()

        except ipc.Error as exc:
            logger.info("Failed to send SHUTDOWN to %s", address)

    async def cleanup_testcase(self):
        await self.__shutdown_process(self.__instrument_db_address)
        await self.__shutdown_process(self.__node_db_address)
        await self.__shutdown_process(self.__urid_mapper_address)

        if self.process_manager_client is not None:
            await self.process_manager_client.close()

        if self.process_manager is not None:
            await self.process_manager.cleanup()

    async def __create_node_db_process(self, inline, request, response):
        async with self.__node_db_lock:
            if self.__node_db_address is None:
                if inline:
                    proc = await self.process_manager.start_inline_process(
                        name='node_db',
                        entry='noisicaa.node_db.process.NodeDBProcess')
                    self.__node_db_address = proc.address
                else:
                    raise NotImplementedError

        response.address = self.__node_db_address

    def setup_node_db_process(self, *, inline):
        async def wrap(request, response):
            return await self.__create_node_db_process(inline, request, response)

        self.process_manager.server['main'].add_handler(
            'CREATE_NODE_DB_PROCESS', wrap,
            empty_message_pb2.EmptyMessage, editor_main_pb2.CreateProcessResponse)

    async def __create_instrument_db_process(self, inline, request, response):
        async with self.__instrument_db_lock:
            if self.__instrument_db_address is None:
                if inline:
                    proc = await self.process_manager.start_inline_process(
                        name='instrument_db',
                        entry='noisicaa.instrument_db.process.InstrumentDBProcess')
                    self.__instrument_db_address = proc.address
                else:
                    raise NotImplementedError

        response.address = self.__instrument_db_address

    def setup_instrument_db_process(self, *, inline):
        async def wrap(request, response):
            await self.__create_instrument_db_process(inline, request, response)

        self.process_manager.server['main'].add_handler(
            'CREATE_INSTRUMENT_DB_PROCESS', wrap,
            empty_message_pb2.EmptyMessage, editor_main_pb2.CreateProcessResponse)

    async def __create_urid_mapper_process(self, inline, request, response):
        async with self.__urid_mapper_lock:
            if self.__urid_mapper_address is None:
                if inline:
                    proc = await self.process_manager.start_inline_process(
                        name='urid_mapper',
                        entry='noisicaa.lv2.urid_mapper_process.URIDMapperProcess')
                else:
                    proc = await self.process_manager.start_subprocess(
                        name='urid_mapper',
                        entry='noisicaa.lv2.urid_mapper_process.URIDMapperSubprocess')
                self.__urid_mapper_address = proc.address

        response.address = self.__urid_mapper_address

    def setup_urid_mapper_process(self, *, inline):
        async def wrap(request, response):
            await self.__create_urid_mapper_process(inline, request, response)

        self.process_manager.server['main'].add_handler(
            'CREATE_URID_MAPPER_PROCESS', wrap,
            empty_message_pb2.EmptyMessage, editor_main_pb2.CreateProcessResponse)

    async def __create_audioproc_process(self, inline, request, response):
        if inline:
            proc = await self.process_manager.start_inline_process(
                name=request.name,
                entry='noisicaa.audioproc.audioproc_process.AudioProcProcess',
                block_size=(
                    request.host_parameters.block_size
                    if request.host_parameters.HasField('block_size')
                    else None),
                sample_rate=(
                    request.host_parameters.sample_rate
                    if request.host_parameters.HasField('sample_rate')
                    else None))
            response.address = proc.address
        else:
            raise NotImplementedError

    def setup_audioproc_process(self, *, inline):
        async def wrap(request, response):
            return await self.__create_audioproc_process(inline, request, response)

        self.process_manager.server['main'].add_handler(
            'CREATE_AUDIOPROC_PROCESS', wrap,
            editor_main_pb2.CreateAudioProcProcessRequest, editor_main_pb2.CreateProcessResponse)

    async def __create_plugin_host_process(self, inline, request, response):
        if inline:
            proc = await self.process_manager.start_inline_process(
                name='plugin_host',
                entry='noisicaa.audioproc.engine.plugin_host_process.PluginHostProcess')
        else:
            proc = await self.process_manager.start_subprocess(
                name='plugin_host',
                entry='noisicaa.audioproc.engine.plugin_host_process.PluginHostSubprocess')

        response.address = proc.address

    def setup_plugin_host_process(self, *, inline):
        async def wrap(request, response):
            return await self.__create_plugin_host_process(inline, request, response)

        self.process_manager.server['main'].add_handler(
            'CREATE_PLUGIN_HOST_PROCESS', wrap,
            empty_message_pb2.EmptyMessage, editor_main_pb2.CreateProcessResponse)

    async def __create_project_process(self, inline, request, response):
        if inline:
            proc = await self.process_manager.start_inline_process(
                name=request.uri,
                entry='noisicaa.music.project_process.ProjectProcess')
            response.address = proc.address
        else:
            raise NotImplementedError

    def setup_project_process(self, *, inline):
        async def wrap(request, response):
            return await self.__create_project_process(inline, request, response)

        self.process_manager.server['main'].add_handler(
            'CREATE_PROJECT_PROCESS', wrap,
            editor_main_pb2.CreateProjectProcessRequest, editor_main_pb2.CreateProcessResponse)
