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

from PyQt5.QtCore import Qt
from PyQt5 import QtCore

from noisidev import uitest
from noisicaa import instrument_db
from . import instrument_list


class InstrumentListTest(uitest.UITestCase):
    def __mkinstr(self, path):
        return instrument_db.InstrumentDescription(
            uri='wav:' + path,
            path=path,
            display_name=os.path.splitext(os.path.basename(path))[0])

    async def test_addInstrument(self):
        model = instrument_list.InstrumentList(context=self.context)
        try:
            root_index = QtCore.QModelIndex()
            self.assertEqual(model.rowCount(root_index), 0)
            self.assertEqual(model.parent(root_index), QtCore.QModelIndex())

            model.addInstrument(self.__mkinstr('/test.wav'))
            self.assertEqual(model.rowCount(root_index), 1)

            folder1_index = model.index(0, parent=root_index)
            self.assertEqual(model.data(folder1_index, Qt.DisplayRole), '/')
            self.assertEqual(model.rowCount(folder1_index), 1)
            self.assertEqual(model.parent(folder1_index), root_index)

            instr1_index = model.index(0, parent=folder1_index)
            self.assertEqual(model.data(instr1_index, Qt.DisplayRole), 'test')
            self.assertEqual(model.rowCount(instr1_index), 0)
            self.assertEqual(model.parent(instr1_index), folder1_index)

        finally:
            model.cleanup()

    async def test_addInstrument_long_path(self):
        model = instrument_list.InstrumentList(context=self.context)
        try:
            model.addInstrument(self.__mkinstr('/some/path/test1.wav'))
            self.assertEqual(
                list(model.flattened()),
                [['/some/path'],
                 ['/some/path', 'test1']])

            model.addInstrument(self.__mkinstr('/some/path/test2.wav'))
            self.assertEqual(
                list(model.flattened()),
                [['/some/path'],
                 ['/some/path', 'test1'],
                 ['/some/path', 'test2']])

            model.addInstrument(self.__mkinstr('/some/path/more/test3.wav'))
            self.assertEqual(
                list(model.flattened()),
                [['/some/path'],
                 ['/some/path', 'more'],
                 ['/some/path', 'more', 'test3'],
                 ['/some/path', 'test1'],
                 ['/some/path', 'test2']])

            model.addInstrument(self.__mkinstr('/some/path2/test4.wav'))
            self.assertEqual(
                list(model.flattened()),
                [['/some'],
                 ['/some', 'path'],
                 ['/some', 'path', 'more'],
                 ['/some', 'path', 'more', 'test3'],
                 ['/some', 'path', 'test1'],
                 ['/some', 'path', 'test2'],
                 ['/some', 'path2'],
                 ['/some', 'path2', 'test4']])

        finally:
            model.cleanup()
