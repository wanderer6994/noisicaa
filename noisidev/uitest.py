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
import functools
import logging
import os.path
import uuid
import typing
from typing import cast, Any, Dict, Set

from PyQt5.QtCore import Qt
from PyQt5 import QtCore
from PyQt5 import QtGui
from PyQt5 import QtWidgets

from noisicaa.constants import TEST_OPTS
from noisicaa import runtime_settings as runtime_settings_lib
from noisicaa import audioproc
from noisicaa import core
from noisicaa import music
from noisicaa import node_db
from noisicaa import editor_main_pb2
from noisicaa.ui import ui_base
from noisicaa.ui import clipboard
from . import qttest
from . import unittest_mixins

if typing.TYPE_CHECKING:
    from noisicaa import instrument_db

logger = logging.getLogger(__name__)


class TestContext(object):
    def __init__(self, *, testcase: 'UITestCase') -> None:
        self.__testcase = testcase

    @property
    def app(self):
        return self.__testcase.app

    @property
    def audioproc_client(self):
        return self.__testcase.app.audioproc_client

    @property
    def window(self):
        return self.__testcase.window

    @property
    def event_loop(self):
        return self.__testcase.loop

    @property
    def project_connection(self):
        return self.__testcase.project_connection

    @property
    def project(self):
        return self.__testcase.project

    @property
    def project_client(self):
        return self.__testcase.project_client

    def call_async(self, coroutine, callback=None):
        task = self.event_loop.create_task(coroutine)
        task.add_done_callback(
            functools.partial(self.__call_async_cb, callback=callback))

    def __call_async_cb(self, task, callback):
        if task.exception() is not None:
            raise task.exception()
        if callback is not None:
            callback(task.result())

    def set_session_value(self, key, value):
        self.__testcase.session_data[key] = value

    def set_session_values(self, data):
        self.__testcase.session_data.update(data)

    def get_session_value(self, key, default):
        return self.__testcase.session_data.get(key, default)

    def add_session_listener(self, key, listener):
        raise NotImplementedError


class MockAudioProcClient(audioproc.AbstractAudioProcClient):  # pylint: disable=abstract-method
    def __init__(self):
        super().__init__()
        self.node_messages = core.CallbackMap[str, Dict[str, Any]]()
        self.node_state_changed = core.CallbackMap[str, audioproc.NodeStateChange]()


class MockSettings(object):
    def __init__(self):
        self.__data = {}  # type: Dict[str, Any]
        self.__grp = None  # type: str

    def value(self, key, default=None):
        if self.__grp:
            key = self.__grp + '/' + key
        return self.__data.get(key, default)

    def setValue(self, key, value):
        if self.__grp:
            key = self.__grp + '/' + key
        self.__data[key] = value

    def allKeys(self):
        assert self.__grp is None
        return list(self.__data.keys())

    def sync(self):
        pass

    def beginGroup(self, grp):
        assert self.__grp is None
        self.__grp = grp

    def endGroup(self):
        assert self.__grp is not None
        self.__grp = None


class MockProcess(core.ProcessBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.project = None


class MockApp(ui_base.AbstractEditorApp):  # pylint: disable=abstract-method
    globalMousePosChanged = QtCore.pyqtSignal(QtCore.QPoint)

    def __init__(self):
        super().__init__()

        self.audioproc_client = None  # type: audioproc.AbstractAudioProcClient
        self.process = None  # type: core.ProcessBase
        self.settings = None  # type: QtCore.QSettings
        self.pipeline_perf_monitor = None  # type: ui_base.AbstractPipelinePerfMonitor
        self.stat_monitor = None  # type: ui_base.AbstractStatMonitor
        self.runtime_settings = None  # type: runtime_settings_lib.RuntimeSettings
        self.node_db = None  # type: node_db.NodeDBClient
        self.instrument_db = None  # type: instrument_db.InstrumentDBClient
        self.default_style = None  # type: str
        self.qt_app = None  # type: QtWidgets.QApplication
        self.node_messages = None  # type: core.CallbackMap
        self.clipboard = None  # type: clipboard.Clipboard


class HIDState(object):
    def __init__(self):
        self.__pressed_keys = set()  # type: Set[Qt.Key]
        self.__pressed_mouse_buttons = set()  # type: Set[Qt.MouseButton]
        self.__mouse_pos = QtCore.QPointF(0, 0)

    @property
    def window_pos(self):
        return self.window_posf.toPoint()

    @property
    def window_posf(self):
        return QtCore.QPointF(100, 200)

    def press_mouse_button(self, button):
        assert button not in self.__pressed_mouse_buttons
        self.__pressed_mouse_buttons.add(button)

    def release_mouse_button(self, button):
        assert button in self.__pressed_mouse_buttons
        self.__pressed_mouse_buttons.remove(button)

    def set_mouse_pos(self, pos):
        self.__mouse_pos = pos

    @property
    def mouse_posf(self):
        return self.__mouse_pos

    @property
    def mouse_pos(self):
        return self.__mouse_pos.toPoint()

    @property
    def mouse_buttons(self):
        buttons = Qt.NoButton
        for button in self.__pressed_mouse_buttons:
            buttons |= button  # type: ignore[assignment]
        return buttons

    def press_key(self, key):
        assert key not in self.__pressed_keys
        self.__pressed_keys.add(key)

    def release_key(self, key):
        assert key in self.__pressed_keys
        self.__pressed_keys.remove(key)

    @property
    def modifiers(self):
        modifiers = Qt.KeyboardModifiers()
        for key in self.__pressed_keys:
            if key == Qt.Key_Shift:
                modifiers |= Qt.ShiftModifier
            elif key == Qt.Key_Control:
                modifiers |= Qt.ControlModifier
            elif key == Qt.Key_Alt:
                modifiers |= Qt.AltModifier
            elif key == Qt.Key_Meta:
                modifiers |= Qt.MetaModifier

        return modifiers


class Event(object):
    def replay(self, state, widget):
        raise NotImplementedError


class MoveMouse(Event):
    def __init__(self, p):
        self.__p = QtCore.QPointF(p)

    def replay(self, state, widget):
        state.set_mouse_pos(self.__p)
        widget.mouseMoveEvent(QtGui.QMouseEvent(
            QtCore.QEvent.MouseMove,
            self.__p,
            self.__p + widget.pos(),
            self.__p + widget.pos() + state.window_pos,
            Qt.NoButton,
            state.mouse_buttons,
            state.modifiers))


class PressMouseButton(Event):
    def __init__(self, button):
        self.__button = button

    def replay(self, state, widget):
        state.press_mouse_button(self.__button)
        widget.mousePressEvent(QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            state.mouse_pos,
            state.mouse_pos + widget.pos(),
            state.mouse_pos + widget.pos() + state.window_pos,
            self.__button,
            state.mouse_buttons,
            state.modifiers))


class DoubleClickButton(Event):
    def __init__(self, button):
        self.__button = button

    def replay(self, state, widget):
        state.press_mouse_button(self.__button)
        widget.mousePressEvent(QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonPress,
            state.mouse_pos,
            state.mouse_pos + widget.pos(),
            state.mouse_pos + widget.pos() + state.window_pos,
            self.__button,
            state.mouse_buttons,
            state.modifiers))
        widget.mouseReleaseEvent(QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            state.mouse_pos,
            state.mouse_pos + widget.pos(),
            state.mouse_pos + widget.pos() + state.window_pos,
            self.__button,
            state.mouse_buttons,
            state.modifiers))
        widget.mouseDoubleClickEvent(QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonDblClick,
            state.mouse_pos,
            state.mouse_pos + widget.pos(),
            state.mouse_pos + widget.pos() + state.window_pos,
            self.__button,
            state.mouse_buttons,
            state.modifiers))
        widget.mouseReleaseEvent(QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            state.mouse_pos,
            state.mouse_pos + widget.pos(),
            state.mouse_pos + widget.pos() + state.window_pos,
            self.__button,
            state.mouse_buttons,
            state.modifiers))


class ReleaseMouseButton(Event):
    def __init__(self, button):
        self.__button = button

    def replay(self, state, widget):
        state.release_mouse_button(self.__button)
        widget.mouseReleaseEvent(QtGui.QMouseEvent(
            QtCore.QEvent.MouseButtonRelease,
            state.mouse_pos,
            state.mouse_pos + widget.pos(),
            state.mouse_pos + widget.pos() + state.window_pos,
            self.__button,
            state.mouse_buttons,
            state.modifiers))


class MoveWheel(Event):
    def __init__(self, steps):
        self.__steps = steps

    def replay(self, state, widget):
        widget.wheelEvent(QtGui.QWheelEvent(
            state.mouse_pos,
            state.mouse_pos + widget.pos() + state.window_pos,
            QtCore.QPoint(0, 10 * self.__steps),
            QtCore.QPoint(0, 15 * self.__steps),
            0, Qt.Vertical,
            state.mouse_buttons,
            state.modifiers))


class PressKey(Event):
    def __init__(self, key):
        self.__key = key

    def replay(self, state, widget):
        state.press_key(self.__key)
        widget.keyPressEvent(QtGui.QKeyEvent(
            QtCore.QEvent.KeyPress,
            self.__key,
            state.modifiers,
            0,
            0,
            0,
            '',
            False,
            0))


class ReleaseKey(Event):
    def __init__(self, key):
        self.__key = key

    def replay(self, state, widget):
        state.release_key(self.__key)
        widget.keyReleaseEvent(QtGui.QKeyEvent(
            QtCore.QEvent.KeyRelease,
            self.__key,
            state.modifiers,
            0,
            0,
            0,
            '',
            False,
            0))


class OpenContextMenu(Event):
    def replay(self, state, widget):
        widget.contextMenuEvent(QtGui.QContextMenuEvent(
            QtGui.QContextMenuEvent.Mouse,
            state.mouse_pos,
            state.mouse_pos + widget.pos() + state.window_pos,
            state.modifiers))


class UITestCase(unittest_mixins.ProcessManagerMixin, qttest.QtTestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.process = None
        self.node_db_address = None
        self.node_db_client = None
        self.app = None
        self.context = None
        self.widget_under_test = None
        self.clipboard = None

    async def setup_testcase(self):
        self.hid_state = HIDState()

        self.setup_node_db_process(inline=True)
        self.setup_urid_mapper_process(inline=True)
        self.setup_instrument_db_process(inline=True)

        self.process = MockProcess(
            name='ui',
            manager=self.process_manager_client,
            event_loop=self.loop,
            tmp_dir=TEST_OPTS.TMP_DIR)
        await self.process.setup()

        create_node_db_response = editor_main_pb2.CreateProcessResponse()
        await self.process_manager_client.call(
            'CREATE_NODE_DB_PROCESS', None, create_node_db_response)
        self.node_db_address = create_node_db_response.address

        self.node_db_client = node_db.NodeDBClient(self.loop, self.process.server)
        await self.node_db_client.setup()
        await self.node_db_client.connect(self.node_db_address)

        self.context = TestContext(testcase=self)

        self.clipboard = clipboard.Clipboard(qt_app=self.qt_app, context=self.context)
        self.clipboard.setup()

        self.app = MockApp()
        self.app.qt_app = self.qt_app
        self.app.process = self.process
        self.app.runtime_settings = runtime_settings_lib.RuntimeSettings()
        self.app.settings = cast(QtCore.QSettings, MockSettings())
        self.app.node_db = self.node_db_client
        self.app.audioproc_client = MockAudioProcClient()
        self.app.node_messages = core.CallbackMap()
        self.app.clipboard = self.clipboard

        self.session_data = {}  # type: Dict[str, Any]

    async def cleanup_testcase(self):
        if self.clipboard is not None:
            self.clipboard.cleanup()

        if self.node_db_client is not None:
            await self.node_db_client.disconnect()
            await self.node_db_client.cleanup()

        if self.node_db_address is not None:
            await self.process_manager_client.call(
                'SHUTDOWN_PROCESS',
                editor_main_pb2.ShutdownProcessRequest(
                    address=self.node_db_address))

        if self.process is not None:
            await self.process.cleanup()

        self.app = None
        self.context = None
        self.widget_under_test = None

    def setWidgetUnderTest(self, widget):
        self.widget_under_test = widget

    async def processQtEvents(self):
        await asyncio.sleep(0, loop=self.loop)

    def renderWidget(self):
        pixmap = QtGui.QPixmap(self.widget_under_test.size())
        self.widget_under_test.render(pixmap)
        return pixmap

    async def replayEvents(self, *events):
        for event in events:
            event.replay(self.hid_state, self.widget_under_test)
            await self.processQtEvents()

    async def moveMouse(self, pos, steps=10):
        p1 = self.hid_state.mouse_pos
        p2 = pos
        for i in range(1, steps + 1):
            MoveMouse(i * (p2 - p1) / steps + p1).replay(self.hid_state, self.widget_under_test)
            await self.processQtEvents()

    async def pressKey(self, key):
        PressKey(key).replay(self.hid_state, self.widget_under_test)
        await self.processQtEvents()

    async def releaseKey(self, key):
        ReleaseKey(key).replay(self.hid_state, self.widget_under_test)
        await self.processQtEvents()

    async def pressMouseButton(self, button):
        PressMouseButton(button).replay(self.hid_state, self.widget_under_test)
        await self.processQtEvents()

    async def releaseMouseButton(self, button):
        ReleaseMouseButton(button).replay(self.hid_state, self.widget_under_test)
        await self.processQtEvents()

    async def clickMouseButton(self, button):
        await self.pressMouseButton(button)
        await self.releaseMouseButton(button)

    async def scrollWheel(self, direction):
        MoveWheel(direction).replay(self.hid_state, self.widget_under_test)
        await self.processQtEvents()

    async def openContextMenu(self):
        assert self.widget_under_test.findChild(QtWidgets.QMenu, 'context-menu') is None
        OpenContextMenu().replay(self.hid_state, self.widget_under_test)
        await self.processQtEvents()
        menu = self.widget_under_test.findChild(QtWidgets.QMenu, 'context-menu')
        assert menu is not None
        return menu

    def getMenuAction(self, menu, name):
        for action in menu.actions():
            if action.objectName() == name:
                return action
        raise AssertionError(name)

    async def triggerMenuAction(self, menu, name):
        action = self.getMenuAction(menu, name)
        self.assertTrue(action.isEnabled())
        action.trigger()
        await self.processQtEvents()


class ProjectMixin(
        unittest_mixins.ServerMixin,
        unittest_mixins.URIDMapperMixin,
        UITestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.project_client = None
        self.project = None

    async def setup_testcase(self):
        self.setup_writer_process(inline=True)

        self.project_client = music.ProjectClient(
            event_loop=self.loop,
            server=self.server,
            node_db=self.node_db_client,
            urid_mapper=self.urid_mapper,
            manager=self.process_manager_client,
            tmp_dir=TEST_OPTS.TMP_DIR)
        await self.project_client.setup()

        path = os.path.join(TEST_OPTS.TMP_DIR, 'test-project-%s' % uuid.uuid4().hex)
        await self.project_client.create(path)

        self.project = self.project_client.project

    async def cleanup_testcase(self):
        if self.project_client is not None:
            await self.project_client.cleanup()
