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
import base64
import enum
import errno
import functools
import importlib
import logging
import os
import pickle
import select
import shutil
import signal
import struct
import sys
import tempfile
import threading
import time
import traceback
from typing import Dict, List, Set  # pylint: disable=unused-import

import eventfd

from . import ipc
from . import stats
from . import stacktrace
from .logging import init_pylogging

logger = logging.getLogger(__name__)


class ProcessState(enum.Enum):
    NOT_STARTED = 'not_started'
    RUNNING = 'running'
    STOPPING = 'stopping'
    FINISHED = 'finished'


class PipeAdapter(asyncio.Protocol):
    def __init__(self, handler):
        super().__init__()
        self._handler = handler
        self._buf = bytearray()

    def data_received(self, data):
        self._buf.extend(data)
        while True:
            eol = self._buf.find(b'\n')
            if eol < 0:
                break
            line = self._buf[:eol].decode('utf-8')
            del self._buf[:eol+1]
            self._handler(line)

    def eof_received(self):
        if self._buf:
            line = self._buf.decode('utf-8')
            del self._buf[:]
            self._handler(line)


class LogAdapter(asyncio.Protocol):
    def __init__(self, logger):
        super().__init__()
        self._logger = logger
        self._buf = bytearray()
        self._state = 'header'
        self._length = None

    def data_received(self, data):
        self._buf.extend(data)
        while True:
            if self._state == 'header':
                if len(self._buf) < 6:
                    break
                header = self._buf[:6]
                del self._buf[:6]
                assert header == b'RECORD'
                self._state = 'length'
            elif self._state == 'length':
                if len(self._buf) < 4:
                    break
                packed_length = self._buf[:4]
                del self._buf[:4]
                self._length, = struct.unpack('>L', packed_length)
                self._state = 'record'
            elif self._state == 'record':
                if len(self._buf) < self._length:
                    break
                serialized_record = self._buf[:self._length]
                del self._buf[:self._length]

                record_attr = pickle.loads(serialized_record)
                record = logging.makeLogRecord(record_attr)
                self._logger.handle(record)

                self._state = 'header'

class ChildLogHandler(logging.Handler):
    def __init__(self, log_fd):
        super().__init__()
        self._log_fd = log_fd

    def handle(self, record):
        record_attrs = {
            'msg': record.getMessage(),
            'args': (),
        }
        for attr in (
                'created', 'exc_text', 'filename',
                'funcName', 'levelname', 'levelno', 'lineno',
                'module', 'msecs', 'name', 'pathname', 'process',
                'relativeCreated', 'thread', 'threadName'):
            record_attrs[attr] = record.__dict__[attr]

        serialized_record = pickle.dumps(record_attrs)
        msg = bytearray()
        msg += b'RECORD'
        msg += struct.pack('>L', len(serialized_record))
        msg += serialized_record

        while msg:
            written = os.write(self._log_fd, msg)
            msg = msg[written:]


class ChildConnection(object):
    def __init__(self, fd_in, fd_out):
        self.fd_in = fd_in
        self.fd_out = fd_out

        self.__reader_state = 0
        self.__reader_buf = None
        self.__reader_length = None

    def write(self, request):
        assert isinstance(request, bytes)
        header = b'#%d\n' % len(request)
        msg = header + request
        while msg:
            written = os.write(self.fd_out, msg)
            msg = msg[written:]

    def __reader_start(self):
        self.__reader_state = 0
        self.__reader_buf = None
        self.__reader_length = None

    def __read_internal(self):
        if self.__reader_state == 0:
            d = os.read(self.fd_in, 1)
            if not d:
                raise OSError(errno.EBADF, "File descriptor closed")
            assert d == b'#', d
            self.__reader_buf = bytearray()
            self.__reader_state = 1

        elif self.__reader_state == 1:
            d = os.read(self.fd_in, 1)
            if not d:
                raise OSError(errno.EBADF, "File descriptor closed")
            elif d == b'\n':
                self.__reader_length = int(self.__reader_buf)
                self.__reader_buf = bytearray()
                self.__reader_state = 2
            else:
                self.__reader_buf += d

        elif self.__reader_state == 2:
            if len(self.__reader_buf) < self.__reader_length:
                d = os.read(self.fd_in, self.__reader_length - len(self.__reader_buf))
                if not d:
                    raise OSError(errno.EBADF, "File descriptor closed")
                self.__reader_buf += d

            if len(self.__reader_buf) == self.__reader_length:
                self.__reader_state = 3

    @property
    def __reader_done(self):
        return self.__reader_state == 3

    @property
    def __reader_response(self):
        assert self.__reader_done
        return self.__reader_buf

    def read(self):
        self.__reader_start()
        while not self.__reader_done:
            self.__read_internal()
        return self.__reader_response

    async def read_async(self, event_loop):
        done = asyncio.Event(loop=event_loop)
        def read_cb():
            try:
                self.__read_internal()

            except OSError as exc:
                event_loop.remove_reader(self.fd_in)
                done.set()
                return

            except:
                event_loop.remove_reader(self.fd_in)
                raise

            if self.__reader_done:
                event_loop.remove_reader(self.fd_in)
                done.set()

        self.__reader_start()
        event_loop.add_reader(self.fd_in, read_cb)
        await done.wait()

        if self.__reader_done:
            return self.__reader_response
        else:
            raise OSError("Failed to read from connection")

    def close(self):
        os.close(self.fd_in)
        os.close(self.fd_out)


class ChildCollector(object):
    def __init__(self, stats_collector, collection_interval=100):
        self.__stats_collector = stats_collector
        self.__collection_interval = collection_interval

        self.__stat_poll_duration = None
        self.__stat_poll_count = None

        self.__lock = threading.Lock()
        self.__connections = {}  # type: Dict[int, ChildConnection]
        self.__stop = None  # type: threading.Event
        self.__thread = None  # type: threading.Thread

    def setup(self):
        self.__stat_poll_duration = stats.registry.register(
            stats.Counter, stats.StatName(name='stat_collector_duration_total'))
        self.__stat_poll_count = stats.registry.register(
            stats.Counter, stats.StatName(name='stat_collector_collections'))

        self.__stop = threading.Event()
        self.__thread = threading.Thread(target=self.__main)
        self.__thread.start()
        logger.info("Started ChildCollector thread 0x%08x", self.__thread.ident)

    def cleanup(self):
        if self.__thread is not None:
            logger.info("Stopping ChildCollector thread 0x%08x", self.__thread.ident)
            self.__stop.set()
            self.__thread.join()
            self.__thread = None
            self.__stop = None

        for connection in self.__connections.values():
            connection.close()
        self.__connections.clear()

        if self.__stat_poll_duration is not None:
            self.__stat_poll_duration.unregister()
            self.__stat_poll_duration = None

        if self.__stat_poll_count is not None:
            self.__stat_poll_count.unregister()
            self.__stat_poll_count = None

    def add_child(self, pid, connection):
        with self.__lock:
            self.__connections[pid] = connection

    def remove_child(self, pid):
        with self.__lock:
            connection = self.__connections.pop(pid, None)
            if connection is not None:
                connection.close()

    def collect(self):
        with self.__lock:
            poll_start = time.perf_counter()

            pending = {}
            poller = select.poll()
            for pid, connection in self.__connections.items():
                t0 = time.perf_counter()
                try:
                    connection.write(b'COLLECT_STATS')
                except OSError as exc:
                    logger.warning("Failed to collect stats from PID=%d", pid)
                else:
                    pending[connection.fd_in] = (t0, pid, connection)
                    poller.register(connection.fd_in)

            while pending:
                for fd, evt in poller.poll():
                    t0, pid, connection = pending[fd]
                    if evt & select.POLLIN:
                        response = connection.read()
                        latency = time.perf_counter() - t0

                        child_name = stats.StatName(pid=pid)
                        for name, value in pickle.loads(response):
                            self.__stats_collector.add_value(
                                name.merge(child_name), value)

                        poller.unregister(fd)
                        del pending[fd]

                    elif evt & select.POLLHUP:
                        logger.warning("Failed to collect stats from PID=%d", pid)
                        poller.unregister(fd)
                        del pending[fd]

            poll_duration = time.perf_counter() - poll_start
            self.__stat_poll_duration.incr(poll_duration)
            self.__stat_poll_count.incr(1)

        manager_name = stats.StatName(pid=os.getpid())
        for name, value in stats.registry.collect():
            self.__stats_collector.add_value(
                name.merge(manager_name), value)

    def __main(self):
        next_collection = time.perf_counter()
        while not self.__stop.is_set():
            delay = next_collection - time.perf_counter()
            if delay > 0:
                time.sleep(delay)

            self.collect()
            next_collection += self.__collection_interval / 1e3


class ProcessManager(object):
    def __init__(self, event_loop, collect_stats=True, tmp_dir=None):
        self._event_loop = event_loop
        self._processes = set()  # type: Set[ProcessHandle]
        self._sigchld_received = asyncio.Event(loop=event_loop)

        self._tmp_dir = tmp_dir
        self._clear_tmp_dir = False
        self._server = None

        if collect_stats:
            self._stats_collector = stats.Collector()
            self._child_collector = ChildCollector(self._stats_collector)
        else:
            self._stats_collector = None
            self._child_collector = None

    @property
    def server(self):
        return self._server

    async def setup(self):
        logger.info("Starting ProcessManager...")
        self._event_loop.add_signal_handler(signal.SIGCHLD, self.sigchld_handler)

        if self._tmp_dir is None:
            self._tmp_dir = tempfile.mkdtemp(
                prefix='noisicaa-%s-%d-' % (time.strftime('%Y%m%d-%H%M%S'), os.getpid()))
            self._clear_tmp_dir = True
            logger.info("Using %s for temp files.", self._tmp_dir)

        self._server = ipc.Server(self._event_loop, 'manager', socket_dir=self._tmp_dir)

        self._server.add_command_handler(
            'STATS_LIST', self.handle_stats_list)
        self._server.add_command_handler(
            'STATS_FETCH', self.handle_stats_fetch)

        await self._server.setup()

        if self._child_collector is not None:
            self._child_collector.setup()

    async def cleanup(self):
        if self._child_collector is not None:
            self._child_collector.cleanup()

        await self.terminate_all_children()

        if self._server is not None:
            await self._server.cleanup()

            self._server.remove_command_handler('STATS_LIST')
            self._server.remove_command_handler('STATS_FETCH')

            self._server = None

        if self._clear_tmp_dir:
            assert self._tmp_dir is not None
            shutil.rmtree(self._tmp_dir)
            self._clear_tmp_dir = False

        self._event_loop.remove_signal_handler(signal.SIGCHLD)

    async def __aenter__(self):
        await self.setup()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
        return False

    async def terminate_all_children(self, timeout=10):
        for sig in [signal.SIGTERM, signal.SIGKILL]:
            for proc in self._processes:
                if proc.state == ProcessState.RUNNING:
                    proc.kill(sig)

            deadline = time.time() + timeout
            processes_left = set()  # type: Set[ProcessHandle]
            while time.time() < deadline:
                self.collect_dead_children()
                if not self._processes:
                    break

                if self._processes != processes_left:
                    logger.info(
                        "%d children still running (%s), waiting for SIGCHLD signal...",
                        len(self._processes),
                        ", ".join(sorted(proc.id for proc in self._processes)))
                    processes_left = set(self._processes)

                try:
                    await asyncio.wait_for(
                        self._sigchld_received.wait(), min(0.05, timeout), loop=self._event_loop)
                    self._sigchld_received.clear()
                except asyncio.TimeoutError:
                    pass

        for proc in self._processes:
            logger.error("Failed to kill child %s", proc.id)

    async def start_inline_process(self, name, entry, **kwargs):
        proc = InlineProcessHandle(self._event_loop)
        self._processes.add(proc)

        proc.create_loggers()

        proc.manager_stub = ManagerStub(self._event_loop, self._server.address)
        await proc.manager_stub.connect()

        mod_name, cls_name = entry.rsplit('.', 1)
        mod = importlib.import_module(mod_name)
        cls = getattr(mod, cls_name)
        proc.process = cls(
            name=name,
            manager=proc.manager_stub,
            tmp_dir=self._tmp_dir,
            event_loop=self._event_loop,
            **kwargs)

        await proc.process.setup()
        assert proc.process.server is not None
        assert proc.process.server.address is not None
        proc.address = proc.process.server.address

        proc.task = self._event_loop.create_task(proc.process.run())
        proc.task.add_done_callback(proc.on_task_done)

        proc.state = ProcessState.RUNNING

        proc.logger.info("Created new subprocess '%s' (%s).", name, entry)

        return proc

    async def start_subprocess(self, name, entry, **kwargs):
        proc = SubprocessHandle(self._event_loop)

        # Open pipes without O_CLOEXEC, so they survive the exec() call.
        request_in, request_out = os.pipe2(0)
        response_in, response_out = os.pipe2(0)
        stdout_in, stdout_out = os.pipe2(0)
        stderr_in, stderr_out = os.pipe2(0)
        logger_in, logger_out = os.pipe2(0)

        manager_address = self._server.address

        pid = os.fork()
        if pid == 0:
            # In child process.
            try:
                # Close the "other ends" of the pipes.
                os.close(request_out)
                os.close(response_in)
                os.close(stdout_in)
                os.close(stderr_in)
                os.close(logger_in)

                # Use the pipes as out STDIN/-ERR.
                os.dup2(stdout_out, 1)
                os.dup2(stderr_out, 2)
                os.close(stdout_out)
                os.close(stderr_out)

                # TODO: ensure that sys.stdout/err use utf-8

                child_connection = ChildConnection(request_in, response_out)

                # Wait until manager told us it's ok to start. Avoid race
                # condition where child terminates and generates SIGCHLD
                # before manager has added it to its process map.
                msg = child_connection.read()
                assert msg == b'START'

                args = dict(
                    name=name,
                    entry=entry,
                    manager_address=manager_address,
                    tmp_dir=self._tmp_dir,
                    cwd=os.getcwd(),
                    logger_out=logger_out,
                    log_level=logging.getLogger().getEffectiveLevel(),
                    request_in=request_in,
                    response_out=response_out,
                    kwargs=kwargs,
                )

                cmdline = []  # type: List[str]
                cmdline += [sys.executable]
                cmdline += ['-m', 'noisicaa.core.process_manager']
                cmdline += [base64.b64encode(pickle.dumps(args, protocol=-1)).decode('ascii')]

                env = dict(**os.environ)
                env['PYTHONPATH'] = ':'.join(p for p in sys.path if p)

                os.chdir('/tmp')
                os.execve(cmdline[0], cmdline, env)

            except SystemExit as exc:
                rc = exc.code
            except:  # pylint: disable=bare-except
                traceback.print_exc()
                rc = 1
            finally:
                rc = rc or 0
                sys.stdout.write("_exit(%d)\n" % rc)
                sys.stdout.flush()
                sys.stderr.flush()
                os._exit(rc)
                assert False

        else:
            # In manager process.
            os.close(request_in)
            os.close(response_out)
            os.close(stdout_out)
            os.close(stderr_out)
            os.close(logger_out)

            proc.pid = pid
            self._processes.add(proc)

            child_connection = ChildConnection(response_in, request_out)

            proc.create_loggers()

            proc.logger.info("Created new subprocess '%s' (%s).", name, entry)

            await proc.setup_std_handlers(stdout_in, stderr_in, logger_in)

            # Unleash the child.
            proc.state = ProcessState.RUNNING
            child_connection.write(b'START')

            try:
                stub_address = await child_connection.read_async(self._event_loop)

            except OSError as exc:
                logger.error("Failed to read child's server address: %s", exc)
                raise OSError("Failed to start subprocess.")

            else:
                if self._child_collector is not None:
                    self._child_collector.add_child(pid, child_connection)
                else:
                    child_connection.close()

                proc.address = stub_address.decode('utf-8')
                logger.info("Child pid=%d has IPC address %s", pid, proc.address)

            return proc

    def sigchld_handler(self):
        logger.info("Received SIGCHLD.")
        self.collect_dead_children()
        self._sigchld_received.set()

    def collect_dead_children(self):
        dead_children = set()
        for proc in self._processes:
            if proc.try_collect():
                dead_children.add(proc)

        for proc in dead_children:
            if self._child_collector is not None and isinstance(proc, SubprocessHandle):
                self._child_collector.remove_child(proc.pid)
            self._processes.remove(proc)

    def handle_stats_list(self):
        if self._stats_collector is None:
            return RuntimeError("Stats collection not enabled.")
        return self._stats_collector.list_stats()

    def handle_stats_fetch(self, expressions):
        if self._stats_collector is None:
            return RuntimeError("Stats collection not enabled.")
        return self._stats_collector.fetch_stats(expressions)


class ChildConnectionHandler(object):
    def __init__(self, connection):
        self.connection = connection

        self.__stop = None
        self.__thread = None

    def setup(self):
        self.__stop = eventfd.EventFD()
        self.__thread = threading.Thread(target=self.__main)
        self.__thread.start()
        logger.info("Started ChildConnectionHandler thread 0x%08x", self.__thread.ident)

    def cleanup(self):
        if self.__thread is not None:
            logger.info("Stopping ChildConnectionHandler thread 0x%08x...", self.__thread.ident)
            self.__stop.set()
            self.__thread.join()
            self.__thread = None
            self.__stop = None

    def __main(self):
        fd_in = self.connection.fd_in

        poller = select.poll()
        poller.register(fd_in, select.POLLIN | select.POLLHUP)
        poller.register(self.__stop, select.POLLIN)
        while not self.__stop.is_set():
            for fd, evt in poller.poll():
                if fd == fd_in and evt & select.POLLIN:
                    request = self.connection.read()
                    if request == b'COLLECT_STATS':
                        data = stats.registry.collect()
                        response = pickle.dumps(data, protocol=-1)
                    else:
                        raise ValueError(request)

                    try:
                        self.connection.write(response)
                    except BrokenPipeError:
                        logger.warning("Failed to write COLLECT_STATS response.")

                elif fd == fd_in and evt & select.POLLHUP:
                    logger.warning("Child connection closed.")
                    poller.unregister(fd_in)

        logger.info("ChildConnectionHandler stopped.")


class ProcessBase(object):
    def __init__(self, *, name, manager, event_loop, tmp_dir):
        self.name = name
        self.manager = manager
        self.event_loop = event_loop
        self.tmp_dir = tmp_dir

        self.server = None  # type: ipc.Server

        self.__shutting_down = None
        self.__shutdown_complete = None

    async def setup(self):
        self.__shutting_down = asyncio.Event(loop=self.event_loop)
        self.__shutdown_complete = asyncio.Event(loop=self.event_loop)

        self.server = ipc.Server(self.event_loop, self.name, socket_dir=self.tmp_dir)
        await self.server.setup()

    async def cleanup(self):
        if self.server is not None:
            await self.server.cleanup()
            self.server = None

    async def run(self):
        await self.__shutting_down.wait()
        logger.info("Shutting down process '%s'...", self.name)
        await self.cleanup()
        self.__shutdown_complete.set()

    async def shutdown(self):
        logger.info("Shutdown received for process '%s'.", self.name)
        self.__shutting_down.set()
        logger.info("Waiting for shutdown of process '%s' to complete...", self.name)
        await self.__shutdown_complete.wait()
        logger.info("Shutdown of process '%s' complete.", self.name)


# mypy complains: Invalid type "asyncio.DefaultEventLoopPolicy"
# Not sure if that's related to https://github.com/python/mypy/issues/1843
class EventLoopPolicy(asyncio.DefaultEventLoopPolicy):  # type: ignore
    def get_event_loop(self):
        raise RuntimeError("get_event_loop() is not allowed.")

    def set_event_loop(self, loop):
        raise RuntimeError("set_event_loop() is not allowed.")


class SubprocessMixin(ProcessBase):
    def __init__(self, *, manager_address, **kwargs):
        super().__init__(manager=None, event_loop=None, **kwargs)

        self.manager_address = manager_address
        self.pid = os.getpid()

    def create_event_loop(self):
        return asyncio.new_event_loop()

    def error_handler(self, event_loop, context):
        try:
            event_loop.default_exception_handler(context)
        except:
            traceback.print_exc()

        try:
            msg = context['message']
            exc = context.get('exception', None)
            if exc is not None:
                tb = exc.__traceback__
                if tb is not None:
                    msg += '\n%s' % ''.join(traceback.format_exception(type(exc), exc, tb))
                else:
                    msg += '\n%s: %s\nNo traceback' % (type(exc).__name__, exc)
            logging.error(msg)

        except:
            traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)

    def main(self, child_connection, *args, **kwargs):
        event_loop_policy = EventLoopPolicy()
        asyncio.set_event_loop_policy(event_loop_policy)

        # Create a new event loop to replace the one we inherited.
        self.event_loop = self.create_event_loop()
        self.event_loop.set_exception_handler(self.error_handler)

        # mypy doesn't know about asyncio.SafeChildWatcher.
        child_watcher = asyncio.SafeChildWatcher()  # type: ignore
        child_watcher.attach_loop(self.event_loop)
        event_loop_policy.set_child_watcher(child_watcher)

        try:
            return self.event_loop.run_until_complete(
                self.main_async(child_connection, *args, **kwargs))
        finally:
            logger.info("Closing event loop...")
            pending_tasks = asyncio.Task.all_tasks(self.event_loop)
            if pending_tasks:
                logger.info("Waiting for %d tasks to complete...", len(pending_tasks))
                self.event_loop.run_until_complete(
                    asyncio.gather(*pending_tasks, loop=self.event_loop))
            self.event_loop.stop()
            self.event_loop.close()
            logger.info("Event loop closed.")

    async def main_async(self, child_connection, *args, **kwargs):
        self.manager = ManagerStub(self.event_loop, self.manager_address)
        async with self.manager:
            try:
                logger.info("Setting up process.")
                try:
                    await self.setup()
                except Exception as exc:
                    logger.error(
                        "Exception while setting up %s:\n%s",
                        self.name, traceback.format_exc())
                    return 1

                stub_address = self.server.address.encode('utf-8')
                child_connection.write(stub_address)

                child_connection_handler = ChildConnectionHandler(child_connection)
                child_connection_handler.setup()
                try:
                    logger.info("Entering run method.")
                    return await self.run(*args, **kwargs)

                except Exception as exc:
                    logger.error(
                        "Unhandled exception in process %s:\n%s",
                        self.name, traceback.format_exc())
                    return 1

                finally:
                    logger.info("Closing child connection...")
                    child_connection_handler.cleanup()
                    child_connection.close()
                    logger.info("Child connection closed.")

            finally:
                await self.cleanup()


class SetPIDHandler(logging.Handler):
    def __init__(self, pid):
        super().__init__()
        self._pid = pid

    def handle(self, record):
        record.process = self._pid


class ProcessHandle(object):
    def __init__(self, event_loop):
        self.event_loop = event_loop
        self.state = ProcessState.NOT_STARTED
        self.logger = None  # type: logging.Logger
        self.address = None  # type: str
        self.returncode = None  # type: int

    @property
    def id(self):
        raise NotImplementedError

    def __hash__(self):
        return hash(self.id)

    def create_loggers(self):
        raise NotImplementedError

    def kill(self, sig):
        raise NotImplementedError

    def try_collect(self):
        raise NotImplementedError

    async def wait(self):
        raise NotImplementedError


class InlineProcessHandle(ProcessHandle):
    def __init__(self, event_loop):
        super().__init__(event_loop)

        self.process = None  # type: ProcessBase
        self.task = None  # type: asyncio.Task
        self.cleanup_task = None  # type: asyncio.Task
        self.manager_stub = None  # type: ManagerStub

    @property
    def id(self):
        return 'inline:%016x' % id(self)

    def create_loggers(self):
        self.logger = logging.getLogger('childproc[%016x]' % id(self))

    def kill(self, sig):
        if not self.task.done():
            logger.warning("Cancelling left over child %s", self.id)
            self.task.cancel()

        if sig == signal.SIGKILL and self.cleanup_task is not None and not self.cleanup_task.done():
            logger.warning("Cancelling left over child %s", self.id)
            self.cleanup_task.cancel()

    def try_collect(self):
        if self.task is None:
            return True

        if not self.task.done():
            return False

        if self.cleanup_task is not None and not self.cleanup_task.done():
            return False

        if self.task.cancelled():
            self.returncode = 1
            self.logger.info("Cancelled")

        else:
            self.returncode = self.task.result() or 0
            self.logger.info("Terminated with rc=%d", self.returncode)

        return True

    async def wait(self):
        self.returncode = await asyncio.wait_for(self.task, None, loop=self.event_loop) or 0

    async def cleanup(self):
        await self.process.cleanup()
        if self.manager_stub is not None:
            await self.manager_stub.close()
            self.manager_stub = None

    def on_task_done(self, task):
        self.logger.info("run() finished, cleaning up...")
        self.state = ProcessState.STOPPING
        self.cleanup_task = self.event_loop.create_task(self.cleanup())
        self.cleanup_task.add_done_callback(self.on_cleanup_done)

    def on_cleanup_done(self, task):
        self.logger.info("cleanup() finished.")
        self.state = ProcessState.FINISHED
        task.result()


class SubprocessHandle(ProcessHandle):
    def __init__(self, event_loop):
        super().__init__(event_loop)

        self.pid = None  # type: int
        self.signal = None
        self.resinfo = None
        self.term_event = asyncio.Event(loop=event_loop)
        self.stdout_logger = None
        self.stderr_logger = None
        self.stdout_protocol = None
        self.stderr_protocol = None
        self.logger_protocol = None

        self._stderr_empty_lines = []  # type: List[str]

    @property
    def id(self):
        return 'subprocess:%d' % self.pid

    def create_loggers(self):
        assert self.pid is not None
        self.logger = logging.getLogger('childproc[%d]' % self.pid)

        self.stdout_logger = self.logger.getChild('stdout')
        self.stdout_logger.addHandler(SetPIDHandler(self.pid))
        self.stderr_logger = self.logger.getChild('stderr')
        self.stderr_logger.addHandler(SetPIDHandler(self.pid))

    def kill(self, sig):
        logger.warning("Sending %s to left over child pid=%d", sig.name, self.pid)
        os.kill(self.pid, sig)

    def try_collect(self):
        rpid, status, resinfo = os.wait4(self.pid, os.WNOHANG)
        if rpid == 0:
            return False
        assert rpid == self.pid

        if self.state != ProcessState.RUNNING:
            self.logger.error("Unexpected state %s", self.state)
            return False

        if os.WIFEXITED(status):
            self.returncode = os.WEXITSTATUS(status)
            self.logger.info("Terminated with rc=%d", self.returncode)
        elif os.WIFSIGNALED(status):
            self.returncode = 1
            self.signal = os.WTERMSIG(status)
            self.logger.info("Terminated by signal=%d", self.signal)
        elif os.WIFSTOPPED(status):
            sig = os.WSTOPSIG(status)
            self.logger.info("Stopped by signal=%d", sig)
            return False
        else:
            self.logger.error("Unexpected status %d", status)
            return False

        # The handle should receive an EOF when the child died and the
        # pipe gets closed. We should wait for it asynchronously.
        self.stdout_protocol.eof_received()
        self.stderr_protocol.eof_received()

        self.resinfo = resinfo
        # self.logger.info("Resource usage:")
        # self.logger.info("  utime=%f", resinfo.ru_utime)
        # self.logger.info("  stime=%f", resinfo.ru_stime)
        # self.logger.info("  maxrss=%d", resinfo.ru_maxrss)
        # self.logger.info("  ixrss=%d", resinfo.ru_ixrss)
        # self.logger.info("  idrss=%d", resinfo.ru_idrss)
        # self.logger.info("  isrss=%d", resinfo.ru_isrss)
        # self.logger.info("  minflt=%d", resinfo.ru_minflt)
        # self.logger.info("  majflt=%d", resinfo.ru_majflt)
        # self.logger.info("  nswap=%d", resinfo.ru_nswap)
        # self.logger.info("  inblock=%d", resinfo.ru_inblock)
        # self.logger.info("  oublock=%d", resinfo.ru_oublock)
        # self.logger.info("  msgsnd=%d", resinfo.ru_msgsnd)
        # self.logger.info("  msgrcv=%d", resinfo.ru_msgrcv)
        # self.logger.info("  nsignals=%d", resinfo.ru_nsignals)
        # self.logger.info("  nvcsw=%d", resinfo.ru_nvcsw)
        # self.logger.info("  nivcsw=%d", resinfo.ru_nivcsw)

        self.state = ProcessState.FINISHED
        self.term_event.set()

        return True

    async def wait(self):
        await self.term_event.wait()

    async def setup_std_handlers(self, stdout_fd, stderr_fd, logger_fd):
        _, self.stdout_protocol = await self.event_loop.connect_read_pipe(
            functools.partial(PipeAdapter, self.handle_stdout),
            os.fdopen(stdout_fd))

        _, self.stderr_protocol = await self.event_loop.connect_read_pipe(
            functools.partial(PipeAdapter, self.handle_stderr),
            os.fdopen(stderr_fd))

        _, self.logger_protocol = await self.event_loop.connect_read_pipe(
            functools.partial(LogAdapter, self.logger),
            os.fdopen(logger_fd))

    def handle_stdout(self, line):
        self.stdout_logger.info(line)

    def handle_stderr(self, line):
        if len(line.rstrip('\r\n')) == 0:
            # Buffer empty lines, so we can discard those that are followed
            # by a message that we also want to discard.
            self._stderr_empty_lines.append(line)
            return

        if 'fluid_synth_sfont_unref' in line:
            # Discard annoying error message from libfluidsynth. It is also
            # preceeded by a empty line, which we also throw away.
            self._stderr_empty_lines.clear()
            return

        while len(self._stderr_empty_lines) > 0:
            self.stderr_logger.warning(self._stderr_empty_lines.pop(0))
        self.stderr_logger.warning(line)


class ManagerStub(ipc.Stub):
    pass


if __name__ == '__main__':
    # Entry point for subprocesses.
    try:
        assert len(sys.argv) == 2

        args = pickle.loads(base64.b64decode(sys.argv[1]))

        request_in = args['request_in']
        response_out = args['response_out']
        logger_out = args['logger_out']
        log_level = args['log_level']
        entry = args['entry']
        name = args['name']
        manager_address = args['manager_address']
        tmp_dir = args['tmp_dir']
        kwargs = args['kwargs']

        # Remove all existing log handlers, and install a new
        # handler to pipe all log messages back to the manager
        # process.
        root_logger = logging.getLogger()
        while root_logger.handlers:
            root_logger.removeHandler(root_logger.handlers[0])
        root_logger.addHandler(ChildLogHandler(logger_out))
        root_logger.setLevel(log_level)

        # Make loggers of 3rd party modules less noisy.
        for other in ['quamash']:
            logging.getLogger(other).setLevel(logging.WARNING)

        stacktrace.init()
        init_pylogging()

        mod_name, cls_name = entry.rsplit('.', 1)
        mod = importlib.import_module(mod_name)
        cls = getattr(mod, cls_name)
        impl = cls(
            name=name, manager_address=manager_address, tmp_dir=tmp_dir,
            **kwargs)

        child_connection = ChildConnection(request_in, response_out)
        rc = impl.main(child_connection)

        frames = sys._current_frames()
        for thread in threading.enumerate():
            if thread.ident == threading.get_ident():
                continue
            logger.warning("Left over thread %s (%x)", thread.name, thread.ident)
            if thread.ident in frames:
                logger.warning("".join(traceback.format_stack(frames[thread.ident])))

    except SystemExit as exc:
        rc = exc.code
    except:  # pylint: disable=bare-except
        traceback.print_exc()
        rc = 1
    finally:
        rc = rc or 0
        sys.stdout.write("_exit(%d)\n" % rc)
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(rc)
