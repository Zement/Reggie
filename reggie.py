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

import os
import sys

# Ensure the repo root is importable, so the (still-flat) sibling modules like
# `globals_`, `misc`, `spritelib` resolve whether launched as `python reggie.py`
# or by a frozen build. Python already puts a script's own directory on sys.path
# when run directly; this makes that explicit and robust for other launch modes.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reggie.app import main

if __name__ == '__main__':
    main()
