#!/usr/bin/python3

# @begin:license
#
# Copyright (c) 2015-2018, Benjamin Niemann <pink@odahoda.de>
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

# mypy: loose
# TODO: pylint-unclean

import asyncio
import enum
import functools
import logging
import os
import os.path
import pickle
import pprint
import time
import traceback
from typing import Dict, Callable  # pylint: disable=unused-import
import uuid

from . import stats

logger = logging.getLogger(__name__)


class RemoteException(Exception):
    def __init__(self, server_address, tb):
        super().__init__("From server %s:\n%s" % (server_address, tb))

class Error(Exception): pass
class InvalidResponseError(Error): pass
class ConnectionClosed(Error): pass


class ConnState(enum.Enum):
    READ_MESSAGE = 1
    READ_PAYLOAD = 2


class ServerProtocol(asyncio.Protocol):
    def __init__(self, event_loop, server):
        self.event_loop = event_loop
        self.server = server
        self.id = server.new_connection_id()
        self.transport = None
        self.state = ConnState.READ_MESSAGE
        self.command = None
        self.payload_length = None
        self.inbuf = bytearray()
        self.logger = server.logger.getChild("conn-%d" % self.id)

    def connection_made(self, transport):
        self.logger.info("Accepted new connection.")
        self.transport = transport

    def connection_lost(self, exc):
        self.logger.info("Connection closed.")

    def data_received(self, data):
        if self.server.closed:
            self.logger.warning("Received data in closed server.")
            return

        self.inbuf.extend(data)
        self.server.stat_bytes_received.incr(len(data))

        while self.inbuf:
            if self.state == ConnState.READ_MESSAGE:
                try:
                    eol = self.inbuf.index(b'\n')
                except ValueError:
                    break

                header = bytes(self.inbuf[:eol])
                self.inbuf = self.inbuf[eol+1:]
                if header == b'PING':
                    self.logger.debug("PING received")
                    response = b'ACK 4\nPONG'
                    self.transport.write(response)
                    self.server.stat_bytes_sent.incr(len(response))

                elif header.startswith(b'CALL '):
                    command, length = header[5:].split(b' ')
                    self.command = command.decode('ascii')
                    self.payload_length = int(length)
                    #self.logger.debug("CALL %s received (%d bytes payload)", self.command, self.payload_length)
                    if self.payload_length > 0:
                        self.state = ConnState.READ_PAYLOAD
                    else:
                        task = self.event_loop(
                            self.server.handle_command(
                                self.command, None))
                        task.add_done_callback(self.command_complete)
                else:
                    self.logger.error("Received unknown message '%s'", header)
            elif self.state == ConnState.READ_PAYLOAD:
                if len(self.inbuf) < self.payload_length:
                    break
                payload = bytes(self.inbuf[:self.payload_length])
                del self.inbuf[:self.payload_length]
                task = self.event_loop.create_task(
                    self.server.handle_command(self.command, payload))
                task.add_done_callback(self.command_complete)
                self.state = ConnState.READ_MESSAGE
                self.command = None
                self.payload_length = None

    def command_complete(self, task):
        if task.exception() is not None:
            raise task.exception()

        response = task.result() or b''
        header = b'ACK %d\n' % len(response)
        self.transport.write(header)
        # TODO: uncomment when Server.cleanup waits for outstanding commands
        #self.server.stat_bytes_sent.incr(len(header))
        if response:
            self.transport.write(response)
            #self.server.stat_bytes_sent.incr(len(response))


class Server(object):
    serialize = functools.partial(
        pickle.dumps, protocol=pickle.HIGHEST_PROTOCOL)
    deserialize = pickle.loads

    def __init__(self, event_loop, name, socket_dir):
        self.event_loop = event_loop
        self.name = name
        self.id = uuid.uuid4().hex

        self.logger = logger.getChild(name)

        self.address = os.path.join(socket_dir, '%s.%s.sock' % (self.name, self.id))

        self._next_connection_id = 0
        self._server = None

        self._command_handlers = {}  # type: Dict[str, Callable]
        self._command_log_levels = {}  # type: Dict[str, int]

        self.stat_bytes_sent = None
        self.stat_bytes_received = None

    @property
    def closed(self):
        return self._server is None

    def add_command_handler(self, cmd, handler, log_level=None):
        assert cmd not in self._command_handlers
        self._command_handlers[cmd] = handler
        if log_level is not None:
            self._command_log_levels[cmd] = log_level

    def remove_command_handler(self, cmd):
        if cmd in self._command_handlers:
            del self._command_handlers[cmd]

    def new_connection_id(self):
        self._next_connection_id += 1
        return self._next_connection_id

    async def setup(self):
        self.stat_bytes_sent = stats.registry.register(
            stats.Counter,
            stats.StatName(
                name='ipc_server_bytes_sent',
                server_name=self.name,
                server_id=self.id))
        self.stat_bytes_received = stats.registry.register(
            stats.Counter,
            stats.StatName(
                name='ipc_server_bytes_received',
                server_name=self.name,
                server_id=self.id))

        self.logger.info("Creating server on socket %s", self.address)
        self._server = await self.event_loop.create_unix_server(
            functools.partial(ServerProtocol, self.event_loop, self),
            path=self.address)
        self.logger.info("Listening on socket %s", self.address)

    async def cleanup(self):
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

            if os.path.isfile(self.address):
                os.unlink(self.address)

            self._server = None
            self.logger.info("Server closed")

        if self.stat_bytes_sent is not None:
            self.stat_bytes_sent.unregister()
            self.stat_bytes_sent = None

        if self.stat_bytes_received is not None:
            self.stat_bytes_received.unregister()
            self.stat_bytes_received = None

    async def __aenter__(self):
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
        return False

    # def send_close(self):
    #     sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    #     sock.connect(self.address)
    #     sock.sendall(b'CLOSE\n')
    #     sock.close()

    # def wait_for_pending_connections(self):
    #     while len(self._connections) > 0:
    #         time.sleep(0.01)

    async def handle_command(self, command, payload):
        try:
            handler = self._command_handlers[command]

            args, kwargs = self.deserialize(payload)

            log_level = self._command_log_levels.get(command, logging.INFO)
            if log_level >= 0:
                logger.log(
                    log_level,
                    "%s(%s%s)",
                    command,
                    ', '.join(str(a) for a in args),
                    ''.join(', %s=%r' % (k, v)
                            for k, v in sorted(kwargs.items())))

            if asyncio.iscoroutinefunction(handler):
                result = await handler(*args, **kwargs)
            else:
                result = handler(*args, **kwargs)
            if result is not None:
                return b'OK:' + self.serialize(result)
            else:
                return b'OK'
        except Exception as exc:  # pylint: disable=broad-except
            return b'EXC:' + str(traceback.format_exc()).encode('utf-8')


class ClientProtocol(asyncio.Protocol):
    def __init__(self, stub, event_loop):
        self.stub = stub
        self.closed_event = asyncio.Event(loop=event_loop)
        self.state = 0
        self.buf = bytearray()
        self.length = None
        self.response = None
        self.response_queue = asyncio.Queue(loop=event_loop)  # type: asyncio.Queue

    def connection_lost(self, exc):
        self.closed_event.set()
        logger.info("%s: Connection lost.", self.stub.id)
        self.response_queue.put_nowait(self.stub.CLOSE_SENTINEL)

    def data_received(self, data):
        self.buf.extend(data)

        while self.buf:
            if self.state == 0:
                eol = self.buf.find(b'\n')
                if eol == -1:
                    break
                ack, length = self.buf[:eol].split(b' ')
                self.length = int(length)
                self.response = None
                del self.buf[:eol+1]
                assert ack == b'ACK'
                if self.length > 0:
                    self.state = 1
                else:
                    self.response_queue.put_nowait(self.response)
                    self.state = 0

            elif self.state == 1:
                if len(self.buf) < self.length:
                    break
                self.response = bytes(self.buf[:self.length])
                del self.buf[:self.length]
                self.response_queue.put_nowait(self.response)
                self.state = 0

            else:
                raise RuntimeError("Invalid state %d" % self.state)


class ResponseContainer(object):
    def __init__(self, event_loop):
        self.response = None
        self._event = asyncio.Event(loop=event_loop)

    def set(self, response):
        self.response = response
        self._event.set()

    async def wait(self):
        await self._event.wait()
        return self.response


class Stub(object):
    serialize = functools.partial(
        pickle.dumps, protocol=pickle.HIGHEST_PROTOCOL)
    deserialize = pickle.loads

    CLOSE_SENTINEL = object()

    def __init__(self, event_loop, server_address):
        self.id = uuid.uuid4().hex
        self._event_loop = event_loop
        self._server_address = server_address
        self._transport = None
        self._protocol = None
        self._command_queue = None
        self._command_loop_cancelled = None
        self._command_loop_task = None
        self._connected = False
        self._lock = asyncio.Lock(loop=event_loop)

    @property
    def server_address(self):
        return self._server_address

    @property
    def connected(self):
        return self._connected

    async def connect(self):
        async with self._lock:
            assert not self._connected

            self._transport, self._protocol = (
                await self._event_loop.create_unix_connection(
                    functools.partial(ClientProtocol, self, self._event_loop),
                    self._server_address))
            logger.info("%s: Connected to server at %s", self.id, self._server_address)

            self._command_queue = asyncio.Queue(loop=self._event_loop)
            self._command_loop_cancelled = asyncio.Event(loop=self._event_loop)
            self._command_loop_task = self._event_loop.create_task(self.command_loop())

            self._connected = True

    async def close(self):
        async with self._lock:
            if not self._connected:
                return

            logger.info("%s: Closing stub...", self.id)
            assert self._transport is not None
            self._transport.close()
            await self._protocol.closed_event.wait()
            logger.info("%s: Connection closed.", self.id)

            if self._command_loop_task is not None:
                self._command_loop_cancelled.set()
                await asyncio.wait_for(self._command_loop_task, None, loop=self._event_loop)
                logger.info("%s: Command queue cleaned up.", self.id)
                self._command_loop_task = None

            self._command_queue = None
            self._transport = None
            self._protocol = None

            logger.info("%s: Stub closed.", self.id)
            self._connected = True

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False

    async def command_loop(self):
        cancelled_task = asyncio.ensure_future(
            self._command_loop_cancelled.wait(), loop=self._event_loop)
        while not self._command_loop_cancelled.is_set():
            get_task = asyncio.ensure_future(self._command_queue.get(), loop=self._event_loop)
            done, pending = await asyncio.wait(
                [get_task, cancelled_task],
                return_when=asyncio.FIRST_COMPLETED,
                loop=self._event_loop)
            if get_task not in done:
                get_task.cancel()
                continue

            cmd, payload, response_container = get_task.result()

            if self._transport.is_closing():
                response_container.set(self.CLOSE_SENTINEL)
                continue

            logger.debug("sending %s to %s...", cmd.decode('utf-8'), self._server_address)
            start_time = time.time()
            self._transport.write(b'CALL %s %d\n' % (cmd, len(payload)))
            if payload:
                self._transport.write(payload)

            response = await self._protocol.response_queue.get()
            logger.debug(
                "%s to %s finished in %.2fmsec", cmd.decode('utf-8'), self._server_address, 1000 * (time.time() - start_time))
            response_container.set(response)

        cancelled_task.cancel()

    async def call(self, cmd, *args, **kwargs):
        if not isinstance(cmd, bytes):
            cmd = cmd.encode('ascii')
        try:
            payload = self.serialize([args, kwargs])
        except TypeError as exc:
            raise TypeError(
                "%s:\nargs=%s\nkwargs=%s" % (
                    exc, pprint.pformat(args), pprint.pformat(kwargs))
            ) from None

        response_container = ResponseContainer(self._event_loop)
        self._command_queue.put_nowait((cmd, payload, response_container))
        response = await response_container.wait()

        if response is self.CLOSE_SENTINEL:
            raise ConnectionClosed(self.id)
        elif response == b'OK':
            return None
        elif response.startswith(b'OK:'):
            return self.deserialize(response[3:])
        elif response.startswith(b'EXC:'):
            raise RemoteException(self._server_address, response[4:].decode('utf-8'))
        else:
            raise InvalidResponseError(response)

    def call_sync(self, cmd, payload=b''):
        return self._event_loop.run_until_complete(self.call(cmd, payload))

    async def ping(self):
        self._transport.write(b'PING\n')
        response = await self._protocol.response_queue.get()
        assert response == b'PONG', response
