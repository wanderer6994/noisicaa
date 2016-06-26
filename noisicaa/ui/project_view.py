#!/usr/bin/python3

import logging

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QToolButton,
    QMenu,
    QStackedWidget,
)

from noisicaa.music import (
    AddSheet, DeleteSheet,
)
from .sheet_view import SheetView
from .tool_dock import Tool
from . import ui_base

logger = logging.getLogger(__name__)


class ProjectView(ui_base.ProjectMixin, QWidget):
    currentToolChanged = pyqtSignal(Tool)
    currentSheetChanged = pyqtSignal(object)

    def __init__(self, project_connection, app):
        super().__init__(
            project_connection=project_connection, app=app)

        self._sheets_widget = QStackedWidget(self)
        for sheet in self.project.sheets:
            view = SheetView(**self.context, sheet=sheet, parent=self)
            self._sheets_widget.addWidget(view)
        self._sheets_widget.currentChanged.connect(self.onCurrentSheetChanged)

        self._current_sheet_view = None

        # TODO: Persist what was the current sheet.
        if self._sheets_widget.count() > 0:
            self.setCurrentSheetView(self._sheets_widget.widget(0))

        self.sheet_menu = QMenu()
        self.updateSheetMenu()

        # Sheet selection should better be in a dock...
        sheet_menu_button = QToolButton(self)
        sheet_menu_button.setIcon(QIcon.fromTheme('start-here'))
        sheet_menu_button.setMenu(self.sheet_menu)
        sheet_menu_button.setPopupMode(QToolButton.InstantPopup)

        player_status = QWidget(self)

        bottom_layout = QHBoxLayout()
        bottom_layout.addWidget(sheet_menu_button)
        bottom_layout.addStretch(1)
        bottom_layout.addWidget(player_status)

        layout = QVBoxLayout()
        layout.addWidget(self._sheets_widget)
        layout.addLayout(bottom_layout)
        self.setLayout(layout)

        self._sheet_listener = self.project.listeners.add(
            'sheets', self.onSheetsChanged)

    @property
    def sheetViews(self):
        for idx in range(self._sheets_widget.count()):
            yield self._sheets_widget.widget(idx)

    def currentTool(self):
        if self.currentSheetView() is not None:
            return self.currentSheetView().currentTool()
        return None

    def setCurrentTool(self, tool):
        if self.currentSheetView() is not None:
            self.currentSheetView().setCurrentTool(tool)

    def currentSheetView(self):
        return self._sheets_widget.currentWidget()

    def setCurrentSheetView(self, sheet_view):
        if sheet_view == self._current_sheet_view:
            return

        if self._current_sheet_view is not None:
            self._current_sheet_view.currentToolChanged.disconnect(
                self.currentToolChanged)

        if sheet_view is not None:
            sheet_view.currentToolChanged.connect(
                self.currentToolChanged)

        self._current_sheet_view = sheet_view

        if sheet_view is not None:
            self.currentSheetChanged.emit(sheet_view.sheet)
        else:
            self.currentSheetChanged.emit(None)

    def updateView(self):
        for sheet_view in self.sheetViews:
            sheet_view.updateView()

    def closeEvent(self, event):
        logger.info("CloseEvent received: %s", event)

        self._sheet_listener.remove()

        while self._sheets_widget.count() > 0:
            sheet_view = self._sheets_widget.widget(0)
            self._sheets_widget.removeWidget(sheet_view)
            sheet_view.close()

        #TODO: self._project.close()
        event.accept()

    def onSheetsChanged(self, action, *args):
        if action == 'insert':
            idx, sheet = args
            view = SheetView(self, self.app, self.window, sheet)
            #view.setCurrentTool(self.currentTool())
            self._sheets_widget.insertWidget(idx, view)
            self.updateSheetMenu()

        elif action == 'delete':
            idx, = args
            self._sheets_widget.removeWidget(self._sheets_widget.widget(idx))
            self.updateSheetMenu()

        elif action == 'clear':
            while self._sheets_widget.count() > 0:
                self._sheets_widget.removeWidget(self._sheets_widget.widget(0))
            self.updateSheetMenu()

        else:  # pragma: no cover
            raise AssertionError("Unknown action %r" % action)

    def updateSheetMenu(self):
        self.sheet_menu.clear()

        action = self.sheet_menu.addAction(
            QIcon.fromTheme('document-new'), "Add Sheet")
        action.triggered.connect(self.onAddSheet)

        action = self.sheet_menu.addAction(
            QIcon.fromTheme('edit-delete'), "Delete Sheet")
        action.setEnabled(len(self.project.sheets) > 1)
        action.triggered.connect(self.onDeleteSheet)

        self.sheet_menu.addSeparator()
        for idx, sheet in enumerate(self.project.sheets): # pylint: disable=unused-variable
            action = self.sheet_menu.addAction(
                QIcon.fromTheme('audio-x-generic'), sheet.name)
            action.triggered.connect(
                lambda _, idx=idx: self._sheets_widget.setCurrentIndex(idx))

    def onCurrentSheetChanged(self, idx):
        if idx >= 0:
            sheet_view = self._sheets_widget.widget(idx)
        else:
            sheet_view = None
        self.setCurrentSheetView(sheet_view)

    def onAddSheet(self):
        self.project.dispatch_command('/', AddSheet())

    def onDeleteSheet(self):
        assert len(self.project.sheets) > 1
        self.project.dispatch_command(
            '/', DeleteSheet(name=self.project.get_current_sheet().name))

    def onPlayerStart(self):
        logger.info("Player start")

    def onPlayerPause(self):
        logger.info("Player pause")

    def onPlayerStop(self):
        logger.info("Player stop")
        for sheet_view in self.sheetViews:
            sheet_view.onPlaybackStop()

    def onAddTrack(self, track_type):
        view = self.currentSheetView()
        view.onAddTrack(track_type)

    def onRender(self):
        view = self.currentSheetView()
        view.onRender()
