#!/usr/bin/python
# -*- coding: latin-1 -*-

# Reggie Next - New Super Mario Bros. Wii Level Editor
# Copyright (C) 2009-2020 Treeki, Tempus, angelsl, JasonP27, Kamek64,
# MalStar1000, RoadrunnerWMC, AboodXD, John10v10, TheGrop, CLF78,
# Zementblock, Danster64

# This file is part of Reggie Next.

# Reggie Next is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Reggie Next is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Reggie Next.  If not, see <http://www.gnu.org/licenses/>.

# reggie.py
# Thin launcher. The editor itself lives in the `reggie` package; this file
# stays at the repo root so `python reggie.py` and the PyInstaller entry point
# (build_reggie.py: SCRIPT_FILE = 'reggie.py') keep working unchanged.
#
# See _docs/plan/DIRECTORY_STRUCTURE.md for the package layout and the
# modularization plan.

import faulthandler
import os
import sys

# Ensure the repo root is importable, so the (still-flat) sibling modules like
# `globals_`, `misc`, `spritelib` resolve whether launched as `python reggie.py`
# or by a frozen build. Python already puts a script's own directory on sys.path
# when run directly; this makes that explicit and robust for other launch modes.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _enable_crash_traces():
    """
    Makes a hard crash say where it happened.

    A Qt application can die from an access violation inside C++ - a signal
    handler calling into a deleted widget, a stale pointer - and Python prints
    nothing at all for those: the process simply exits with 0xC0000005 and the
    last thing on screen is whatever unrelated line happened to print before it.
    faulthandler dumps the Python stack of every thread when that happens, which
    turns "it crashed somewhere during boot" into a file and a line number.

    Written to logs/crash.log beside the application, next to the collaboration
    logs, because a frozen build has no terminal to print to - which is exactly
    the case where this is hardest to diagnose without it. stderr is kept as
    well for the source checkout, where the terminal is the fastest route.

    Entirely optional: any failure here leaves the editor running without crash
    traces, which is what it had before.
    """
    try:
        faulthandler.enable()
    except Exception:
        return

    try:
        root = os.path.dirname(os.path.abspath(__file__))
        if getattr(sys, 'frozen', False):
            root = os.path.dirname(os.path.abspath(sys.executable))

        logs = os.path.join(root, 'logs')
        os.makedirs(logs, exist_ok=True)

        # Held open for the process's lifetime on purpose: faulthandler writes
        # to this descriptor from a crashing thread, so it must still be valid
        # at the moment things are going wrong. Never closed, and that is the
        # point.
        handle = open(os.path.join(logs, 'crash.log'), 'a', buffering=1)
        faulthandler.enable(file=handle, all_threads=True)

        # Keep a reference so the file object cannot be garbage collected.
        globals()['_CRASH_LOG'] = handle
    except Exception:
        pass


_enable_crash_traces()

from reggie.app import main

if __name__ == '__main__':
    main()
