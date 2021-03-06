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

import logging
from typing import Any, List, Tuple

from . import stats

logger = logging.getLogger(__name__)


class InvalidExpressionError(ValueError):
    pass


Expression = List[Tuple[Any, ...]]


class Builder(object):
    def __init__(self, **labels: str) -> None:
        name = stats.StatName(**labels)
        self.__code = [('SELECT', name)]  # type: Expression

    def get_code(self) -> Expression:
        return self.__code

    def RATE(self) -> 'Builder':
        self.__code.append(('RATE',))
        return self


def compile_expression(expr: str) -> Expression:
    try:
        builder = eval(expr, {'SELECT': Builder})  # pylint: disable=eval-used
    except Exception as exc:
        raise InvalidExpressionError(str(exc))
    return builder.get_code()
