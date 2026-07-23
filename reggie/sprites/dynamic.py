"""Auto-split from the original sprites.py. See _docs/plan/REFACTORING_ANALYSIS.md.

Do not add cross-module SpriteImage_* inheritance across these files: classes
that inherit from another in-file sprite class all live together in base.py.
"""
#!/usr/bin/python
# -*- coding: latin-1 -*-

# Reggie Next - New Super Mario Bros. Wii Level Editor
# Milestone 4
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


# sprites.py
# Contains code to render sprite images from New Super Mario Bros. Wii


################################################################
################################################################

# Imports
import math
import random

from PyQt6 import QtCore, QtGui
Qt = QtCore.Qt

from reggie.core import spritelib as SLib
from reggie.core import sprites_common as common
from reggie.core import globals_
ImageCache = SLib.ImageCache


################################################################
################################################################



from reggie.sprites.base import *  # base sprite classes some of these subclass



# ---- High-Level Classes ----

class SpriteImage_MeasureJump(SLib.SpriteImage):
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.aux.append(SLib.AuxiliaryImage(parent, 312, 191))
        self.aux[0].image = ImageCache["JumpRun1"]
        self.aux[0].setPos(0, 0)

    @staticmethod
    def loadImages():
        if "JumpRun1" in ImageCache:
            return

        for i in range(1, 4):
            ImageCache["JumpRun%d" % i] = SLib.GetImg("jump_run_%d.png" % i)
            ImageCache["JumpRunSpin%d" % i] = SLib.GetImg("jump_run_spin_%d.png" % i)

    def dataChanged(self):
        super().dataChanged()

        jumptype = self.parent.spritedata[2] & 3
        flags = (self.parent.spritedata[3] & 0xF0) >> 4
        direction = flags >> 3
        spin = (flags & 4) >> 2
        vertical = (flags & 2) >> 1

        if jumptype > 2:
            jumptype = 0

        if spin:
            img = ImageCache["JumpRunSpin%d" % (jumptype + 1)]
        else:
            img = ImageCache["JumpRun%d" % (jumptype + 1)]

        if direction == 1:
            img = img.transformed(QtGui.QTransform().scale(-1, 1))

        self.aux[0].image = img
        width, height = img.width(), img.height()
        self.aux[0].setSize(width, height)

        if direction == 1:
            self.aux[0].setPos(-width, 0)
        else:
            self.aux[0].setPos(0, 0)


class SpriteImage_QSwitch(common.SpriteImage_Switch):  # 40
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.switchType = 'Q'

    def dataChanged(self):
        self.offset = (0, 0)
        super().dataChanged()


class SpriteImage_PSwitch(common.SpriteImage_Switch):  # 41
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.switchType = 'P'

    def dataChanged(self):
        self.offset = (0, 0)
        super().dataChanged()


class SpriteImage_ExcSwitch(common.SpriteImage_Switch):  # 42
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.switchType = 'E'

    def dataChanged(self):
        self.offset = (0, 0)
        super().dataChanged()


class SpriteImage_Podoboo(SLib.SpriteImage):  # 46
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.aux.append(SLib.AuxiliaryImage(parent, 48, 48))
        self.aux[0].image = ImageCache['Podoboo0']
        self.aux[0].setPos(-6, -6)
        self.aux[0].hover = False

        self.dimensions = (-3, 5, 24, 24)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Podoboo0', 'podoboo.png')


class SpriteImage_UnusedSeesaw(SLib.SpriteImage):  # 49
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.aux.append(SLib.AuxiliaryRotationAreaOutline(parent, 48))
        self.aux[0].setPos(128, -36)

        self.image = ImageCache['UnusedPlatformDark']
        self.dimensions = (0, -8, 256, 16)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('UnusedPlatformDark', 'unused_platform_dark.png')

    def dataChanged(self):
        w = self.parent.spritedata[5] & 15
        if w == 0:
            self.width = 16 * 16  # 16 blocks wide
        else:
            self.width = w * 32
        self.image = ImageCache['UnusedPlatformDark'].scaled(
            int(self.width * 1.5), int(self.height * 1.5),
            Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        self.xOffset = (8 * 16) - (self.width / 2)

        swingArc = self.parent.spritedata[5] >> 4
        swingArcs = (
            45,
            4.5,
            9,
            18,
            65,
            80,
        )
        if swingArc <= 5:
            realSwingArc = swingArcs[swingArc]
        elif swingArc in (11, 15):
            realSwingArc = 0
        else:
            realSwingArc = 100  # infinite

        # angle starts at the right position (3 o'clock)
        # negative = clockwise, positive = counter-clockwise
        startAngle = 90 - realSwingArc
        spanAngle = realSwingArc * 2

        self.aux[0].SetAngle(startAngle, spanAngle)
        self.aux[0].setPos((self.width / 1.5) - 36, -36)
        self.aux[0].update()

        super().dataChanged()

    def paint(self, painter):
        super().paint(painter)

        painter.drawPixmap(0, 0, self.image)


class SpriteImage_UnusedRotPlatforms(SLib.SpriteImage):  # 52
    def __init__(self, parent):
        super().__init__(parent, 1.5)

        for _ in range(4):
            img = SLib.AuxiliaryImage(parent, 144, 24)
            img.image = ImageCache["UnusedRotPlatform"]
            self.aux.append(img)

        self.aux[0].setPos(-60, -144) # top
        self.aux[1].setPos(-60, 144) # bottom
        self.aux[2].setPos(-204, 0) # left
        self.aux[3].setPos(84, 0) # right

    @staticmethod
    def loadImages():
        if 'UnusedRotPlatform' in ImageCache:
            return

        SLib.loadIfNotInImageCache('UnusedPlatformDark', 'unused_platform_dark.png')

        platform = ImageCache['UnusedPlatformDark'].scaled(
            144, 24,
            Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        img = QtGui.QPixmap(144, 24)
        img.fill(Qt.GlobalColor.transparent)
        paint = QtGui.QPainter(img)
        paint.setOpacity(0.8)
        paint.drawPixmap(0, 0, platform)
        ImageCache['UnusedRotPlatform'] = img


class SpriteImage_BigBoo(SLib.SpriteImage):  # 61
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.aux.append(SLib.AuxiliaryImage(parent, 243, 248))
        self.aux[0].image = ImageCache['BigBoo']
        self.aux[0].setPos(-48, -48)
        self.aux[0].hover = False

        self.dimensions = (-38, -80, 98, 102)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('BigBoo', 'bigboo.png')


class SpriteImage_SpinningFirebar(SLib.SpriteImage):  # 62
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False
        self.aux.append(SLib.AuxiliaryCircleOutline(parent, 12, Qt.AlignmentFlag.AlignCenter))

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('FirebarBase', 'firebar_base_0.png')
        SLib.loadIfNotInImageCache('FirebarBaseWide', 'firebar_base_1.png')

    def dataChanged(self):
        super().dataChanged()

        size = self.parent.spritedata[5] & 0xF
        wideBase = (self.parent.spritedata[3] >> 4) & 1

        width = ((size * 2) + 1) * 12
        self.aux[0].setSize(width)

        currentAuxX = self.aux[0].x()
        currentAuxY = self.aux[0].y()
        if wideBase: self.aux[0].setPos(currentAuxX + 12, currentAuxY)

        self.image = ImageCache['FirebarBase'] if not wideBase else ImageCache['FirebarBaseWide']
        self.xOffset = 0 if not wideBase else -8
        self.width = 16 if not wideBase else 32

    def paint(self, painter):
        super().paint(painter)
        painter.drawPixmap(0, 0, self.image)


class SpriteImage_BulletBillLauncher(SLib.SpriteImage):  # 92
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('BBLauncherT', 'bullet_launcher_top.png')
        SLib.loadIfNotInImageCache('BBLauncherM', 'bullet_launcher_middle.png')

    def dataChanged(self):
        super().dataChanged()
        height = (self.parent.spritedata[5] & 0xF0) >> 4

        self.height = (height + 2) * 16
        self.yOffset = (height + 1) * -16

    def paint(self, painter):
        super().paint(painter)

        painter.drawPixmap(0, 0, ImageCache['BBLauncherT'])
        painter.drawTiledPixmap(0, 48, 24, int(self.height * 1.5 - 48), ImageCache['BBLauncherM'])


class SpriteImage_RotationControllerSwaying(SLib.SpriteImage):  # 96
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.parent.setZValue(100000)
        self.aux.append(SLib.AuxiliaryRotationAreaOutline(parent, 48))

    def dataChanged(self):
        super().dataChanged()
        # get the swing arc: 4 == 90 degrees (45 left from the origin, 45 right)
        swingArc = self.parent.spritedata[2] >> 4
        realSwingArc = swingArc * 11.25

        # angle starts at the right position (3 o'clock)
        # negative = clockwise, positive = counter-clockwise
        startAngle = 90 - realSwingArc
        spanAngle = realSwingArc * 2

        self.aux[0].SetAngle(startAngle, spanAngle)
        self.aux[0].update()


class SpriteImage_PipeEnemyGenerator(SLib.SpriteImage):  # 99
    def __init__(self, parent):
        super().__init__(parent, 1.5)

    def dataChanged(self):
        super().dataChanged()

        self.spritebox.size = (16, 16)
        direction = (self.parent.spritedata[5] & 0xF) & 3
        if direction in (0, 1):  # vertical pipe
            self.spritebox.size = (32, 16)
        elif direction in (2, 3):  # horizontal pipe
            self.spritebox.size = (16, 32)

        self.yOffset = 0
        if direction in (2, 3):
            self.yOffset = -16


class SpriteImage_Pokey(SLib.SpriteImage):  # 105
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.dimensions = (-4, 0, 24, 32)

    @staticmethod
    def loadImages():
        if 'PokeyTop' in ImageCache: return
        ImageCache['PokeyTop'] = SLib.GetImg('pokey_top.png')
        ImageCache['PokeyMiddle'] = SLib.GetImg('pokey_middle.png')
        ImageCache['PokeyBottom'] = SLib.GetImg('pokey_bottom.png')

    def dataChanged(self):
        super().dataChanged()

        # get the height
        height = self.parent.spritedata[5] & 7
        self.height = (height * 16) + 16 + 25
        self.yOffset = 16 - self.height

    def paint(self, painter):
        super().paint(painter)

        painter.drawPixmap(0, 0, ImageCache['PokeyTop'])
        painter.drawTiledPixmap(0, 37, 36, int(self.height * 1.5 - 61), ImageCache['PokeyMiddle'])
        painter.drawPixmap(0, int(self.height * 1.5 - 24), ImageCache['PokeyBottom'])


class SpriteImage_Sunlight(SLib.SpriteImage):  # 110
    def __init__(self, parent):
        super().__init__(parent, 1.5)

        i = ImageCache['Sunlight']
        self.aux.append(SLib.AuxiliaryImage_FollowsRect(parent, i.width(), i.height()))
        self.aux[0].realimage = i
        self.aux[0].alignment = Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight
        self.aux[0].hover = False

        # Moving the sunlight when a repaint occured is overkill and causes an
        # infinite loop. Alternative idea: Only move the sunlight when
        # - scrolling or
        # - zooming
        # This causes small visual bugs while moving the sprite, but moving this
        # sprite makes little sense, so I guess it's fine.

        slot = self.moveSunlight

        # scrolling
        view = self.parent.scene().views()[0]
        view.XScrollBar.valueChanged.connect(slot)
        view.YScrollBar.valueChanged.connect(slot)

        # zooming
        self.parent.scene().getMainWindow().ZoomWidget.slider.valueChanged.connect(slot)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Sunlight', 'sunlight.png')

    def paint(self, painter):
        self.moveSunlight()
        SLib.SpriteImage.paint(self, painter)

    def moveSunlight(self):
        try:
            if not SLib.RealViewEnabled:
                self.aux[0].realimage = None
                return

            zone = self.parent.nearestZone(True)
            if zone is None:
                self.aux[0].realimage = None
                return

            zoneRect = QtCore.QRectF(zone.objx * 1.5, zone.objy * 1.5, zone.width * 1.5, zone.height * 1.5)
            view = self.parent.scene().views()[0]
            viewRect = view.mapToScene(view.viewport().rect()).boundingRect()
            bothRect = zoneRect & viewRect

            if bothRect.getRect() == (0, 0, 0, 0):
                # The zone is out of view -> hide the image
                self.aux[0].realimage = None
                return

            self.aux[0].realimage = ImageCache['Sunlight']
            self.aux[0].move(*bothRect.getRect())
        except RuntimeError:
            # happens if the parent was deleted
            pass


class SpriteImage_Flagpole(SLib.SpriteImage):  # 113
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.image = ImageCache['Flagpole']

        self.aux.append(SLib.AuxiliaryImage(parent, 144, 149))
        self.offset = (-30, -144)
        self.size = (self.image.width() / 1.5, self.image.height() / 1.5)

    @staticmethod
    def loadImages():
        if 'Flagpole' in ImageCache: return
        ImageCache['Flagpole'] = SLib.GetImg('flagpole.png')
        ImageCache['FlagpoleSecret'] = SLib.GetImg('flagpole_secret.png')
        ImageCache['Castle'] = SLib.GetImg('castle.png')
        ImageCache['CastleSecret'] = SLib.GetImg('castle_secret.png')
        ImageCache['SnowCastle'] = SLib.GetImg('snow_castle.png')
        ImageCache['SnowCastleSecret'] = SLib.GetImg('snow_castle_secret.png')

    def dataChanged(self):

        # get the info (mimic the way the game does it)
        exit_type = self.parent.spritedata[2] >> 4
        snow_type = self.parent.spritedata[5] & 0xF
        value = exit_type + snow_type * 2

        if value == 0:
            show_snow = show_secret = False
        elif value == 1:
            show_snow = False
            show_secret = True
        elif value == 2:
            show_snow = True
            show_secret = False
        else:
            show_snow = show_secret = True

        if show_secret:
            suffix = "Secret"
        else:
            suffix = ""

        self.image = ImageCache['Flagpole' + suffix]

        if show_snow:
            self.aux[0].image = ImageCache['SnowCastle' + suffix]
            self.aux[0].setPos(356, 91)
        else:
            self.aux[0].image = ImageCache['Castle' + suffix]
            self.aux[0].setPos(356, 97)

        super().dataChanged()

    def paint(self, painter):
        super().paint(painter)
        painter.drawPixmap(0, 0, self.image)


class SpriteImage_Cheep(SLib.SpriteImage):  # 115
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.aux.append(SLib.AuxiliaryTrackObject(self.parent, 24, 24, SLib.AuxiliaryTrackObject.Horizontal))

    @staticmethod
    def loadImages():
        if 'CheepGreen' in ImageCache: return
        ImageCache['CheepRedLeft'] = SLib.GetImg('cheep_red.png')
        ImageCache['CheepRedRight'] = QtGui.QPixmap.fromImage(SLib.GetImg('cheep_red.png', True).mirrored(True, False))
        ImageCache['CheepRedAtYou'] = SLib.GetImg('cheep_red_atyou.png')
        ImageCache['CheepGreen'] = SLib.GetImg('cheep_green.png')
        ImageCache['CheepYellow'] = SLib.GetImg('cheep_yellow.png')

    def dataChanged(self):

        type = self.parent.spritedata[5] & 0xF
        if type in (1, 7):
            self.image = ImageCache['CheepGreen']
        elif type == 8:
            self.image = ImageCache['CheepYellow']
        elif type == 5:
            self.image = ImageCache['CheepRedAtYou']
        else:
            self.image = ImageCache['CheepRedLeft']
        self.size = (self.image.width() / 1.5, self.image.height() / 1.5)

        if type == 3:
            distance = ((self.parent.spritedata[3] & 0xF) + 1) * 16
            self.aux[0].setSize((distance * 2) + 16, 16)
            self.aux[0].setPos(-distance * 1.5, 0)
        else:
            self.aux[0].setSize(0, 24)

        super().dataChanged()

    def paint(self, painter):
        super().paint(painter)
        painter.drawPixmap(0, 0, self.image)


class SpriteImage_CoinCheep(SLib.SpriteImage):  # 116
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

    @staticmethod
    def loadImages():
        if 'CheepRedLeft' in ImageCache: return
        ImageCache['CheepRedLeft'] = SLib.GetImg('cheep_red.png')
        ImageCache['CheepRedRight'] = QtGui.QPixmap.fromImage(SLib.GetImg('cheep_red.png', True).mirrored(True, False))
        ImageCache['CheepRedAtYou'] = SLib.GetImg('cheep_red_atyou.png')
        ImageCache['CheepGreen'] = SLib.GetImg('cheep_green.png')
        ImageCache['CheepYellow'] = SLib.GetImg('cheep_yellow.png')

    def dataChanged(self):

        waitFlag = self.parent.spritedata[5] & 1
        if waitFlag:
            self.spritebox.shown = False
            self.image = ImageCache['CheepRedAtYou']
        else:
            type = self.parent.spritedata[2] >> 4
            if type & 3 == 3:
                self.spritebox.shown = True
                self.image = None
            elif type < 7:
                self.spritebox.shown = False
                self.image = self.image = ImageCache['CheepRedRight']
            else:
                self.spritebox.shown = False
                self.image = self.image = ImageCache['CheepRedLeft']

        if self.image is not None:
            self.size = (self.image.width() / 1.5, self.image.height() / 1.5)
        super().dataChanged()

    def paint(self, painter):
        super().paint(painter)
        if self.image is None: return
        painter.drawPixmap(0, 0, self.image)


class SpriteImage_Boo(SLib.SpriteImage):  # 131
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.aux.append(SLib.AuxiliaryImage(parent, 50, 51))
        self.aux[0].image = ImageCache['Boo1']
        self.aux[0].setPos(-6, -6)

        self.dimensions = (-1, -4, 22, 22)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Boo1', 'boo1.png')


class SpriteImage_StalagmitePlatform(SLib.SpriteImage):  # 133
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.aux.append(SLib.AuxiliaryImage(parent, 48, 156))
        self.aux[0].image = ImageCache['StalagmitePlatformBottom']
        self.aux[0].setPos(24, 60)

        self.image = ImageCache['StalagmitePlatformTop']
        self.dimensions = (0, -8, 64, 40)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('StalagmitePlatformTop', 'stalagmite_platform_top.png')
        SLib.loadIfNotInImageCache('StalagmitePlatformBottom', 'stalagmite_platform_bottom.png')

    def paint(self, painter):
        super().paint(painter)
        painter.drawPixmap(0, 0, self.image)


class SpriteImage_RotBulletLauncher(SLib.SpriteImage):  # 136
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.dimensions = (-4, 0, 24, 16)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('RotLauncherCannon', 'bullet_cannon_rot_0.png')
        SLib.loadIfNotInImageCache('RotLauncherPivot', 'bullet_cannon_rot_1.png')

    def dataChanged(self):
        super().dataChanged()
        pieces = self.parent.spritedata[3] & 15
        if pieces > 7: pieces = 7
        self.yOffset = -pieces * 16
        self.height = (pieces + 1) * 16

    def paint(self, painter):
        super().paint(painter)

        pieces = (self.parent.spritedata[3] & 15) + 1
        if pieces > 8: pieces = 8
        pivot1_4 = self.parent.spritedata[4] & 15
        pivot5_8 = self.parent.spritedata[4] >> 4
        startleft1_4 = self.parent.spritedata[5] & 15
        startleft5_8 = self.parent.spritedata[5] >> 4

        pivots = [pivot1_4, pivot5_8]
        startleft = [startleft1_4, startleft5_8]

        ysize = self.height * 1.5

        for piece in range(pieces):
            bitpos = 1 << (piece & 3)
            if pivots[piece // 4] & bitpos:
                painter.drawPixmap(5, int(ysize - (piece + 1) * 24), ImageCache['RotLauncherPivot'])
            else:
                xo = 6
                image = ImageCache['RotLauncherCannon']
                if startleft[piece // 4] & bitpos:
                    transform = QtGui.QTransform()
                    transform.rotate(180)
                    image = QtGui.QPixmap(image.transformed(transform))
                    xo = 0
                painter.drawPixmap(xo, int(ysize - (piece + 1) * 24), image)


class SpriteImage_RotationControllerSpinning(SLib.SpriteImage):  # 149
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.parent.setZValue(100000)


class SpriteImage_QSwitchUnused(common.SpriteImage_Switch):  # 153
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.switchType = 'Q'

    def dataChanged(self):
        self.offset = (0, 0)
        super().dataChanged()


class SpriteImage_RedCoinRing(SLib.SpriteImage):  # 156
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.aux.append(SLib.AuxiliaryImage(parent, 76, 95))
        self.aux[0].image = ImageCache['RedCoinRing']
        self.aux[0].setPos(-10, -15)
        self.aux[0].hover = False

        self.dimensions = (-10, -8, 37, 48)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('RedCoinRing', 'redcoinring.png')

    def dataChanged(self):
        shifted = self.parent.spritedata[5] & 1
        self.xOffset = -2 if shifted else -10

        super().dataChanged()


class SpriteImage_BlockTrain(SLib.SpriteImage):  # 166
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('BlockTrain', 'block_train.png')

    def dataChanged(self):
        super().dataChanged()
        length = self.parent.spritedata[5] & 15
        self.width = (length + 3) * 16

    def paint(self, painter):
        super().paint(painter)

        endpiece = ImageCache['BlockTrain']
        painter.drawPixmap(0, 0, endpiece)
        painter.drawTiledPixmap(24, 0, int((self.width * 1.5) - 48), 24, ImageCache['BlockTrain'])
        painter.drawPixmap(int((self.width * 1.5) - 24), 0, endpiece)


class SpriteImage_FlyingQBlock(SLib.SpriteImage):  # 175
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.dimensions = (-12, -16, 42, 32)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('FlyingQBlock', 'flying_qblock.png')

    def paint(self, painter):
        super().paint(painter)

        theme = self.parent.spritedata[4] >> 4
        content = self.parent.spritedata[5] & 0xF

        if theme > 3:
            theme = 0

        if content == 2:
            content = 17
        elif content in (8, 9, 10, 12, 13, 14):
            content = 0

        painter.drawPixmap(0, 0, ImageCache['FlyingQBlock'])
        painter.drawPixmap(18, 23, ImageCache['Blocks'][theme])
        painter.drawPixmap(18, 23, ImageCache['BlockContents'][content])


class SpriteImage_ScalePlatform(SLib.SpriteImage):  # 178
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.offset = (0, -8)
        self.spritebox.shown = False

    @staticmethod
    def loadImages():
        if 'WoodenPlatformL' not in ImageCache:
            ImageCache['WoodenPlatformL'] = SLib.GetImg('wood_platform_left.png')
            ImageCache['WoodenPlatformM'] = SLib.GetImg('wood_platform_middle.png')
            ImageCache['WoodenPlatformR'] = SLib.GetImg('wood_platform_right.png')
        if 'ScaleRopeH' not in ImageCache:
            ImageCache['ScaleRopeH'] = SLib.GetImg('scale_rope_horz.png')
            ImageCache['ScaleRopeV'] = SLib.GetImg('scale_rope_vert.png')
            ImageCache['ScalePulley'] = SLib.GetImg('scale_pulley.png')

    def dataChanged(self):
        super().dataChanged()

        info1 = self.parent.spritedata[4]
        info2 = self.parent.spritedata[5]
        self.parent.platformWidth = (info1 & 0xF0) >> 4
        if self.parent.platformWidth > 12: self.parent.platformWidth = -1

        self.parent.ropeLengthLeft = info1 & 0xF
        self.parent.ropeLengthRight = (info2 & 0xF0) >> 4
        self.parent.ropeWidth = info2 & 0xF

        ropeWidth = self.parent.ropeWidth * 16
        platformWidth = (self.parent.platformWidth + 3) * 16
        self.width = ropeWidth + platformWidth

        maxRopeHeight = max(self.parent.ropeLengthLeft, self.parent.ropeLengthRight)
        self.height = maxRopeHeight * 16 + 19
        if maxRopeHeight == 0: self.height += 8

        self.xOffset = -(self.parent.platformWidth + 3) * 8

    def paint(self, painter):
        super().paint(painter)

        # this is FUN!! (not)
        ropeLeft = int(self.parent.ropeLengthLeft * 24 + 4)
        if self.parent.ropeLengthLeft == 0: ropeLeft += 12

        ropeRight = int(self.parent.ropeLengthRight * 24 + 4)
        if self.parent.ropeLengthRight == 0: ropeRight += 12

        ropeWidth = int(self.parent.ropeWidth * 24 + 8)
        platformWidth = int((self.parent.platformWidth + 3) * 24)

        ropeX = int(platformWidth / 2 - 4)

        painter.drawTiledPixmap(ropeX + 8, 0, ropeWidth - 16, 8, ImageCache['ScaleRopeH'])

        ropeVertImage = ImageCache['ScaleRopeV']
        painter.drawTiledPixmap(ropeX, 8, 8, ropeLeft - 8, ropeVertImage)
        painter.drawTiledPixmap(ropeX + ropeWidth - 8, 8, 8, ropeRight - 8, ropeVertImage)

        pulleyImage = ImageCache['ScalePulley']
        painter.drawPixmap(ropeX, 0, pulleyImage)
        painter.drawPixmap(ropeX + ropeWidth - 20, 0, pulleyImage)

        platforms = [(0, ropeLeft), (ropeX + ropeWidth - int(platformWidth / 2) - 4, ropeRight)]
        for x, y in platforms:
            painter.drawPixmap(x, y, ImageCache['WoodenPlatformL'])
            painter.drawTiledPixmap(x + 24, y, (platformWidth - 48), 24, ImageCache['WoodenPlatformM'])
            painter.drawPixmap(x + platformWidth - 24, y, ImageCache['WoodenPlatformR'])


class SpriteImage_SpecialExit(SLib.SpriteImage):  # 179
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.aux.append(SLib.AuxiliaryRectOutline(parent, 0, 0))

    def dataChanged(self):
        super().dataChanged()

        w = (self.parent.spritedata[4] & 15) + 1
        h = (self.parent.spritedata[5] >> 4) + 1
        if w == 1 and h == 1:  # no point drawing a 1x1 outline behind the self.parent
            self.aux[0].setSize(0, 0)
            return
        self.aux[0].setSize(w * 24, h * 24)


class SpriteImage_TileEvent(common.SpriteImage_TileEvent):  # 191
    def __init__(self, parent):
        super().__init__(parent)
        self.notAllowedTypes = (2, 5, 7)

    def getTileFromType(self, type_):
        if type_ == 0:
            return SLib.GetTile(55)

        if type_ == 1:
            return SLib.GetTile(48)

        if type_ == 3:
            return SLib.GetTile(52)

        if type_ == 4:
            return SLib.GetTile(51)

        if type_ == 6:
            return SLib.GetTile(45)

        if type_ == 12:
            return SLib.GetTile(256 * 3 + 67)

        if type_ == 14:
            return SLib.GetTile(256)

        return None


class SpriteImage_LarryKoopaCastleBoss(SLib.SpriteImage):  # 192
    def __init__(self, parent):
        super().__init__(parent)
        self.parent.setZValue(24999)

        self.aux.append(SLib.AuxiliaryImage(parent, 528, 240))
        self.aux[0].image = ImageCache['LarryKoopaCastleBoss']
        self.aux[0].setPos(48, 192)
        self.aux.append(SLib.AuxiliaryRectOutline(parent, 24, 24, 0, 288))

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('LarryKoopaCastleBoss', 'larry_castle_boss.png')


class SpriteImage_Zoom(SLib.SpriteImage):  # 206
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.aux.append(SLib.AuxiliaryRectOutline(parent, 0, 0))

    def dataChanged(self):
        super().dataChanged()

        w = self.parent.spritedata[5]
        h = self.parent.spritedata[4]
        if w == 0 and h == 0:  # no point drawing a 1x1 outline behind the self.parent
            self.aux[0].setSize(0, 0, 0, 0)
            return
        self.aux[0].setSize(w * 24, h * 24, 0, 24 - (h * 24))


class SpriteImage_BowserJr1stController(SLib.SpriteImage):  # 211
    def __init__(self, parent):
        super().__init__(parent)
        self.parent.setZValue(24999)

        self.aux.append(SLib.AuxiliaryImage(parent, 672, 80))
        self.aux[0].image = ImageCache['BowserJr1stController']
        self.aux[0].setPos(-504, -55)

        self.aux.append(SLib.AuxiliaryRectOutline(parent, 24, 24, -504, -312))

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('BowserJr1stController', 'boss_controller_bowserjr_1.png')


class SpriteImage_RollingHill(SLib.SpriteImage):  # 212
    RollingHillSizes = [0, 18 * 16, 32 * 16, 50 * 16, 64 * 16, 10 * 16, 14 * 16, 20 * 16, 0, 0, 0, 0, 0, 0, 0, 0]

    def __init__(self, parent):
        super().__init__(parent, 1.5)

        size = (self.parent.spritedata[3] >> 4) & 0xF
        realSize = self.RollingHillSizes[size]

        self.aux.append(SLib.AuxiliaryCircleOutline(parent, realSize))

    def dataChanged(self):
        super().dataChanged()

        size = (self.parent.spritedata[3] >> 4) & 0xF
        if size != 0:
            realSize = self.RollingHillSizes[size]
        else:
            adjust = self.parent.spritedata[4]
            realSize = 32 * (adjust + 1)

        self.aux[0].setSize(realSize)
        self.aux[0].update()


class SpriteImage_LineBlock(common.SpriteImage_LineBlock):  # 219

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('LineBlock', 'lineblock.png')

    def dataChanged(self):
        self.setLineBlockImage(ImageCache['LineBlock'])

        super().dataChanged()


class SpriteImage_PipeCannon(SLib.SpriteImage):  # 227
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        # self.aux[0] is the pipe image
        self.aux.append(SLib.AuxiliaryImage(parent, 24, 24))
        self.aux[0].hover = False

        # self.aux[1] is the trajectory indicator
        self.aux.append(SLib.AuxiliaryPainterPath(parent, QtGui.QPainterPath(), 24, 24))
        self.aux[1].fillFlag = False

        self.aux[0].setZValue(self.aux[1].zValue() + 1)

        self.size = (32, 64)

    @staticmethod
    def loadImages():
        if 'PipeCannon0' in ImageCache: return
        for i in range(7):
            ImageCache['PipeCannon%d' % i] = SLib.GetImg('pipe_cannon_%d.png' % i)

    def dataChanged(self):
        super().dataChanged()

        fireDirection = (self.parent.spritedata[5] & 0xF) % 7

        self.aux[0].image = ImageCache['PipeCannon%d' % (fireDirection)]

        if fireDirection == 0:
            # 30 deg to the right
            self.aux[0].setSize(84, 101, 0, -5)
            path = QtGui.QPainterPath(QtCore.QPointF(0, 184))
            path.cubicTo(QtCore.QPointF(152, -24), QtCore.QPointF(168, -24), QtCore.QPointF(264, 48))
            path.lineTo(QtCore.QPointF(480, 216))
            self.aux[1].setSize(480, 216, 24, -120)
        elif fireDirection == 1:
            # 30 deg to the left
            self.aux[0].setSize(85, 101, -36, -5)
            path = QtGui.QPainterPath(QtCore.QPointF(480 - 0, 184))
            path.cubicTo(QtCore.QPointF(480 - 152, -24), QtCore.QPointF(480 - 168, -24), QtCore.QPointF(480 - 264, 48))
            path.lineTo(QtCore.QPointF(480 - 480, 216))
            self.aux[1].setSize(480, 216, -480 + 24, -120)
        elif fireDirection == 2:
            # 15 deg to the right
            self.aux[0].setSize(60, 102, 0, -6)
            path = QtGui.QPainterPath(QtCore.QPointF(0, 188))
            path.cubicTo(QtCore.QPointF(36, -36), QtCore.QPointF(60, -36), QtCore.QPointF(96, 84))
            path.lineTo(QtCore.QPointF(144, 252))
            self.aux[1].setSize(144, 252, 30, -156)
        elif fireDirection == 3:
            # 15 deg to the left
            self.aux[0].setSize(61, 102, -12, -6)
            path = QtGui.QPainterPath(QtCore.QPointF(144 - 0, 188))
            path.cubicTo(QtCore.QPointF(144 - 36, -36), QtCore.QPointF(144 - 60, -36), QtCore.QPointF(144 - 96, 84))
            path.lineTo(QtCore.QPointF(144 - 144, 252))
            self.aux[1].setSize(144, 252, -144 + 18, -156)
        elif fireDirection == 4:
            # Straight up
            self.aux[0].setSize(135, 132, -43, -35)
            path = QtGui.QPainterPath(QtCore.QPointF(26, 0))
            path.lineTo(QtCore.QPointF(26, 656))
            self.aux[1].setSize(48, 656, 0, -632)
        elif fireDirection == 5:
            # 45 deg to the right
            self.aux[0].setSize(90, 98, 0, -1)
            path = QtGui.QPainterPath(QtCore.QPointF(0, 320))
            path.lineTo(QtCore.QPointF(264, 64))
            path.cubicTo(QtCore.QPointF(348, -14), QtCore.QPointF(420, -14), QtCore.QPointF(528, 54))
            path.lineTo(QtCore.QPointF(1036, 348))
            self.aux[1].setSize(1036, 348, 24, -252)
        elif fireDirection == 6:
            # 45 deg to the left
            self.aux[0].setSize(91, 98, -42, -1)
            path = QtGui.QPainterPath(QtCore.QPointF(1036 - 0, 320))
            path.lineTo(QtCore.QPointF(1036 - 264, 64))
            path.cubicTo(QtCore.QPointF(1036 - 348, -14), QtCore.QPointF(1036 - 420, -14), QtCore.QPointF(1036 - 528, 54))
            path.lineTo(QtCore.QPointF(1036 - 1036, 348))
            self.aux[1].setSize(1036, 348, -1036 + 24, -252)
        self.aux[1].setPath(path)


class SpriteImage_ExtendShroom(SLib.SpriteImage):  # 228
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False
        self.parent.setZValue(24999)

    @staticmethod
    def loadImages():
        if 'ExtendShroomB' in ImageCache: return
        ImageCache['ExtendShroomB'] = SLib.GetImg('extend_shroom_big.png')
        ImageCache['ExtendShroomS'] = SLib.GetImg('extend_shroom_small.png')
        ImageCache['ExtendShroomC'] = SLib.GetImg('extend_shroom_cont.png')
        ImageCache['ExtendShroomStem'] = SLib.GetImg('extend_shroom_stem.png')

    def dataChanged(self):

        props = self.parent.spritedata[5]
        size = self.parent.spritedata[4] & 1
        self.start = (props & 0x10) >> 4
        stemlength = props & 0xF

        if size == 0:  # big
            self.image = ImageCache['ExtendShroomB']
            self.width = 160
        else:  # small
            self.image = ImageCache['ExtendShroomS']
            self.width = 96

        if self.start == 0:  # contracted
            self.indicator, self.image = self.image, ImageCache['ExtendShroomC']

        self.xOffset = 8 - (self.width / 2)
        self.height = (stemlength * 16) + 48

        super().dataChanged()

    def paint(self, painter):
        super().paint(painter)

        if self.start == 0: # contracted, so paint indicator
            painter.save()
            painter.setOpacity(0.5)
            painter.drawPixmap(0, 0, self.indicator)
            painter.restore()

            painter.drawPixmap(int(self.width * 1.5 / 2 - 24), 0, self.image)
        else:
            painter.drawPixmap(0, 0, self.image)

        painter.drawTiledPixmap(
            int((self.width * 1.5) / 2 - 14),
            48,
            28,
            int((self.height * 1.5) - 48),
            ImageCache['ExtendShroomStem'],
        )


class SpriteImage_WiggleShroom(SLib.SpriteImage):  # 231
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False
        self.parent.setZValue(24999)
        self.aux.append(SLib.AuxiliaryTrackObject(parent, 16, 16, SLib.AuxiliaryTrackObject.Vertical))

    @staticmethod
    def loadImages():
        if 'WiggleShroomL' in ImageCache: return
        ImageCache['WiggleShroomL'] = SLib.GetImg('wiggle_shroom_left.png')
        ImageCache['WiggleShroomM'] = SLib.GetImg('wiggle_shroom_middle.png')
        ImageCache['WiggleShroomR'] = SLib.GetImg('wiggle_shroom_right.png')
        ImageCache['WiggleShroomS'] = SLib.GetImg('wiggle_shroom_stem.png')

    def dataChanged(self):
        super().dataChanged()
        width = (self.parent.spritedata[4] & 0xF0) >> 4
        long = (self.parent.spritedata[3] >> 2) & 1
        extends = (self.parent.spritedata[3] >> 5) & 1
        distance = self.parent.spritedata[3] & 3 # this is also the stem length

        self.xOffset = -(width * 8) - 20
        self.width = (width * 16) + 56
        self.wiggleleft = ImageCache['WiggleShroomL']
        self.wigglemiddle = ImageCache['WiggleShroomM']
        self.wiggleright = ImageCache['WiggleShroomR']
        self.wigglestem = ImageCache['WiggleShroomS']

        if extends:
            self.aux[0].setPos((self.width * 0.75) - 12, (-distance * 24))
            self.aux[0].setSize(16, (distance * 32))
            if long:
                self.height = 96
            else:
                self.height = 64
        else:
            self.aux[0].setSize(0, 0)
            self.height = (distance * 16) + 64

    def paint(self, painter):
        super().paint(painter)

        xsize = self.width * 1.5
        painter.drawPixmap(0, 0, self.wiggleleft)
        painter.drawTiledPixmap(18, 0, int(xsize - 36), 24, self.wigglemiddle)
        painter.drawPixmap(int(xsize - 18), 0, self.wiggleright)
        painter.drawTiledPixmap(int((xsize / 2) - 12), 24, 24, int((self.height * 1.5) - 24), self.wigglestem)


class SpriteImage_Bulber(SLib.SpriteImage):  # 233
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.aux.append(SLib.AuxiliaryImage(parent, 243, 248))
        self.aux[0].image = ImageCache['Bulber']
        self.aux[0].setPos(-8, 0)

        self.dimensions = (2, -4, 59, 50)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Bulber', 'bulber.png')


class SpriteImage_MovementController_TwoWayLine(SLib.SpriteImage):  # 260
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.aux.append(SLib.AuxiliaryTrackObject(parent, 16, 16, SLib.AuxiliaryTrackObject.Horizontal))

    def dataChanged(self):
        super().dataChanged()

        direction = self.parent.spritedata[3] & 3
        distance = (self.parent.spritedata[5] >> 4) + 1

        if direction <= 1:  # horizontal
            self.aux[0].direction = 1
            self.aux[0].setSize(distance * 16, 16)
        else:  # vertical
            self.aux[0].direction = 2
            self.aux[0].setSize(16, distance * 16)

        if direction == 0 or direction == 3:  # right, down
            self.aux[0].setPos(0, 0)
        elif direction == 1:  # left
            self.aux[0].setPos((-distance * 24) + 24, 0)
        elif direction == 2:  # up
            self.aux[0].setPos(0, (-distance * 24) + 24)


class SpriteImage_PoltergeistItem(SLib.SpriteImage):  # 262
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.aux.append(SLib.AuxiliaryImage(parent, 60, 60))
        self.aux[0].image = ImageCache['PolterQBlock']
        self.aux[0].setPos(-18, -18)
        self.aux[0].hover = False

    @staticmethod
    def loadImages():
        if 'PolterQBlock' in ImageCache: return

        SLib.loadIfNotInImageCache('GhostHouseStand', 'ghost_house_stand.png')

        polterstand = SLib.GetImg('polter_stand.png')
        polterblock = SLib.GetImg('polter_qblock.png')

        standpainter = QtGui.QPainter(polterstand)
        blockpainter = QtGui.QPainter(polterblock)

        standpainter.drawPixmap(18, 18, ImageCache['GhostHouseStand'])
        blockpainter.drawPixmap(18, 18, ImageCache['Blocks'][0])

        del standpainter
        del blockpainter

        ImageCache['PolterStand'] = polterstand
        ImageCache['PolterQBlock'] = polterblock

    def dataChanged(self):

        style = self.parent.spritedata[5] & 15
        if style == 0:
            self.offset = (0, 0)
            self.height = 16
            self.aux[0].setSize(60, 60)
            self.aux[0].image = ImageCache['PolterQBlock']
        else:
            self.offset = (8, -16)
            self.height = 32
            self.aux[0].setSize(60, 84)
            self.aux[0].image = ImageCache['PolterStand']

        self.aux[0].setPos(-18, -18)

        super().dataChanged()


class SpriteImage_ScaredyRat(SLib.SpriteImage):  # 271
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('ScaredyRat', 'scaredy_rat.png')

    def dataChanged(self):
        super().dataChanged()

        number = (self.parent.spritedata[5] >> 4) & 3
        direction = self.parent.spritedata[5] & 0xF

        self.width = (number + 1) * (ImageCache['ScaredyRat'].width() / 1.5)

        if direction == 0:  # Facing right
            self.xOffset = -self.width + 16
        else:
            self.xOffset = 0

    def paint(self, painter):
        super().paint(painter)

        direction = self.parent.spritedata[5] & 0xF

        rat = ImageCache['ScaredyRat']
        if direction == 1:
            rat = QtGui.QImage(rat)
            rat = QtGui.QPixmap.fromImage(rat.mirrored(True, False))

        painter.drawTiledPixmap(0, 0, int(self.width * 1.5), 24, rat)


class SpriteImage_CastleGear(SLib.SpriteImage):  # 274
    def __init__(self, parent):
        super().__init__(parent)
        self.aux.append(SLib.AuxiliaryImage(parent, 456, 456))
        self.parent.setZValue(24999)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('CastleGearL', 'castle_gear_large.png')
        SLib.loadIfNotInImageCache('CastleGearS', 'castle_gear_small.png')

    def dataChanged(self):
        big = (self.parent.spritedata[4] & 0xF) & 1

        if big:
            self.aux[0].image = ImageCache['CastleGearL']
            self.aux[0].setPos(-216, -216)
        else:
            self.aux[0].image = ImageCache['CastleGearS']
            self.aux[0].setPos(-144, -144)

        super().dataChanged()


class SpriteImage_DragonCoaster(SLib.SpriteImage):  # 297
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False
        self.height = 22

    @staticmethod
    def loadImages():
        if 'DragonHead' in ImageCache: return
        ImageCache['DragonHead'] = SLib.GetImg('dragon_coaster_head.png')
        ImageCache['DragonBody'] = SLib.GetImg('dragon_coaster_body.png')
        ImageCache['DragonTail'] = SLib.GetImg('dragon_coaster_tail.png')

    def dataChanged(self):
        super().dataChanged()

        raw_size = self.parent.spritedata[5] & 7

        if raw_size == 0:
            self.width = 32
            self.xOffset = 0
        else:
            self.width = (raw_size * 32) + 32
            self.xOffset = 32 - self.width

    def paint(self, painter):
        super().paint(painter)

        raw_size = self.parent.spritedata[5] & 15

        if raw_size == 0 or raw_size == 8:
            # just the head
            painter.drawPixmap(0, 0, ImageCache['DragonHead'])
        elif raw_size == 1:
            # head and tail only
            painter.drawPixmap(48, 0, ImageCache['DragonHead'])
            painter.drawPixmap(0, 0, ImageCache['DragonTail'])
        else:
            painter.drawPixmap(int((self.width * 1.5) - 48), 0, ImageCache['DragonHead'])
            if raw_size > 1:
                painter.drawTiledPixmap(48, 0, int((self.width * 1.5) - 96), 24, ImageCache['DragonBody'])
            painter.drawPixmap(0, 0, ImageCache['DragonTail'])


class SpriteImage_LightCircle(SLib.SpriteImage):  # 305
    def __init__(self, parent):
        super().__init__(parent, 1.5)

        self.aux.append(SLib.AuxiliaryImage(parent, 128, 128))
        self.aux[0].image = ImageCache['LightCircle']
        self.aux[0].setPos(-60, -60)
        self.aux[0].hover = False
        self.aux[0].setIsBehindSprite(False)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('LightCircle', 'light_circle.png')


class SpriteImage_BubbleGen(SLib.SpriteImage):  # 314

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('BubbleGenEffect', 'bubble_gen.png')

    def dataChanged(self):
        super().dataChanged()
        self.parent.scene().update()

    def positionChanged(self):
        super().positionChanged()
        self.parent.scene().update()

    def realViewZone(self, painter, zoneRect):

        # Constants (change these if you want)
        bubbleFrequency = .01
        bubbleEccentricityX = 16
        bubbleEccentricityY = 48

        size = self.parent.spritedata[5] & 0xF
        if size > 3: return

        Image = ImageCache['BubbleGenEffect']

        if size == 0:
            pct = 50.0
        elif size == 1:
            pct = 60.0
        elif size == 2:
            pct = 80.0
        else:
            pct = 70.0
        Image = Image.scaledToWidth(int(Image.width() * pct / 100))

        distanceFromTop = (self.parent.objy * 1.5) - zoneRect.topLeft().y()
        random.seed(distanceFromTop + self.parent.objx)  # looks ridiculous without this

        numOfBubbles = int(distanceFromTop * bubbleFrequency)
        for num in range(numOfBubbles):
            xmod = (random.random() * 2 * bubbleEccentricityX) - bubbleEccentricityX
            ymod = (random.random() * 2 * bubbleEccentricityY) - bubbleEccentricityY
            x = ((self.parent.objx * 1.5) - zoneRect.topLeft().x()) + xmod + 12 - (Image.width() / 2.0)
            y = ((num * 1.0 / numOfBubbles) * distanceFromTop) + ymod
            if not (0 < y < self.parent.objy * 1.5): continue
            painter.drawPixmap(int(x), int(y), Image)


class SpriteImage_BoltBox(SLib.SpriteImage):  # 316
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

    @staticmethod
    def loadImages():
        if 'BoltBoxTL' in ImageCache: return
        ImageCache['BoltBoxTL'] = SLib.GetImg('boltbox_tl.png')
        ImageCache['BoltBoxT'] = SLib.GetImg('boltbox_t.png')
        ImageCache['BoltBoxTR'] = SLib.GetImg('boltbox_tr.png')
        ImageCache['BoltBoxL'] = SLib.GetImg('boltbox_l.png')
        ImageCache['BoltBoxM'] = SLib.GetImg('boltbox_m.png')
        ImageCache['BoltBoxR'] = SLib.GetImg('boltbox_r.png')
        ImageCache['BoltBoxBL'] = SLib.GetImg('boltbox_bl.png')
        ImageCache['BoltBoxB'] = SLib.GetImg('boltbox_b.png')
        ImageCache['BoltBoxBR'] = SLib.GetImg('boltbox_br.png')

    def dataChanged(self):
        super().dataChanged()

        size = self.parent.spritedata[5]
        self.width = (size & 0xF) * 16 + 32
        self.height = ((size & 0xF0) >> 4) * 16 + 32

    def paint(self, painter):
        super().paint(painter)

        xsize = int(self.width * 1.5)
        ysize = int(self.height * 1.5)

        painter.drawPixmap(0, 0, ImageCache['BoltBoxTL'])
        painter.drawTiledPixmap(24, 0, xsize - 48, 24, ImageCache['BoltBoxT'])
        painter.drawPixmap(xsize - 24, 0, ImageCache['BoltBoxTR'])

        painter.drawTiledPixmap(0, 24, 24, ysize - 48, ImageCache['BoltBoxL'])
        painter.drawTiledPixmap(24, 24, xsize - 48, ysize - 48, ImageCache['BoltBoxM'])
        painter.drawTiledPixmap(xsize - 24, 24, 24, ysize - 48, ImageCache['BoltBoxR'])

        painter.drawPixmap(0, ysize - 24, ImageCache['BoltBoxBL'])
        painter.drawTiledPixmap(24, ysize - 24, xsize - 48, 24, ImageCache['BoltBoxB'])
        painter.drawPixmap(xsize - 24, ysize - 24, ImageCache['BoltBoxBR'])


class SpriteImage_BooCircle(SLib.SpriteImage):  # 323
    def __init__(self, parent):
        super().__init__(parent, 1.5)

        self.BooAuxImage = QtGui.QPixmap(1024, 1024)
        self.BooAuxImage.fill(Qt.GlobalColor.transparent)
        self.aux.append(SLib.AuxiliaryImage(parent, 1024, 1024))
        self.aux[0].image = self.BooAuxImage
        offsetX = ImageCache['Boo1'].width() / 4
        offsetY = ImageCache['Boo1'].height() / 4
        self.aux[0].setPos(-512 + offsetX, -512 + offsetY)
        self.aux[0].hover = False

    @staticmethod
    def loadImages():
        if 'Boo2' in ImageCache: return
        ImageCache['Boo1'] = SLib.GetImg('boo1.png')
        ImageCache['Boo2'] = SLib.GetImg('boo2.png')
        ImageCache['Boo3'] = SLib.GetImg('boo3.png')
        ImageCache['Boo4'] = SLib.GetImg('boo4.png')

    def dataChanged(self):
        # Constants (change these to fine-tune the boo positions)
        radiusMultiplier = 24  # pixels between boos per distance value
        radiusConstant = 24  # add to all radius values
        opacity = 0.5

        # Read the data
        outrad = self.parent.spritedata[2] & 15
        inrad = self.parent.spritedata[3] >> 4
        ghostnum = 1 + (self.parent.spritedata[3] & 15)
        differentRads = not (inrad == outrad)

        # Give up if the data is invalid
        if inrad > outrad:
            null = QtGui.QPixmap(2, 2)
            null.fill(Qt.GlobalColor.transparent)
            self.aux[0].image = null
            return

        # Create a pixmap
        pix = QtGui.QPixmap(1024, 1024)
        pix.fill(Qt.GlobalColor.transparent)
        paint = QtGui.QPainter(pix)
        paint.setOpacity(opacity)

        # Paint each boo
        for i in range(ghostnum):
            # Find the angle at which to place the ghost from the center
            MissingGhostWeight = 0.75 - (1 / ghostnum)  # approximate
            angle = math.radians(-360 * i / (ghostnum + MissingGhostWeight)) + 89.6

            # Since the origin of the boo img is in the top left, account for that
            offsetX = ImageCache['Boo1'].width() / 2
            offsetY = (ImageCache['Boo1'].height() / 2) + 16  # the circle is not centered

            # Pick a pixmap
            boo = ImageCache['Boo%d' % (1 if i == 0 else ((i - 1) % 3) + 2)]  # 1  2 3 4  2 3 4  2 3 4 ...

            # Find the abs pos, and paint the ghost at its inner position
            x = math.sin(angle) * ((inrad * radiusMultiplier) + radiusConstant) - offsetX
            y = -(math.cos(angle) * ((inrad * radiusMultiplier) + radiusConstant)) - offsetY
            paint.drawPixmap(int(x + 512), int(y + 512), boo)

            # Paint it at its outer position if it has one
            if differentRads:
                x = math.sin(angle) * ((outrad * radiusMultiplier) + radiusConstant) - offsetX
                y = -(math.cos(angle) * ((outrad * radiusMultiplier) + radiusConstant)) - offsetY
                paint.drawPixmap(int(x + 512), int(y + 512), boo)

        # Finish it
        paint = None
        self.aux[0].image = pix


class SpriteImage_KingBill(SLib.SpriteImage):  # 326
    def __init__(self, parent):
        super().__init__(parent, 1.5)

        self.aux.append(SLib.AuxiliaryPainterPath(parent, QtGui.QPainterPath(), 24, 24))
        self.aux[0].setSize(24 * 17, 24 * 17)

        self.paths = []
        for direction in range(4):

            # This has to be within the loop because the
            # following commands transpose them
            PointsRects = (  # These form a LEFT-FACING bullet
                QtCore.QPointF(192, -180 + 180),
                QtCore.QRectF(0, -180 + 180, 384, 384),
                QtCore.QPointF(192 + 72, 204 + 180),
                QtCore.QPointF(192 + 72 + 6, 204 - 24 + 180),
                QtCore.QPointF(192 + 72 + 42, 204 - 24 + 180),
                QtCore.QPointF(192 + 72 + 48, 204 + 180),
                QtCore.QPointF(192 + 72 + 96, 204 + 180),
                QtCore.QPointF(192 + 72 + 96 + 6, 204 - 6 + 180),
                QtCore.QPointF(192 + 72 + 96 + 6, -180 + 6 + 180),
                QtCore.QPointF(192 + 72 + 96, -180 + 180),
                QtCore.QPointF(192 + 72 + 48, -180 + 180),
                QtCore.QPointF(192 + 72 + 42, -180 + 24 + 180),
                QtCore.QPointF(192 + 72 + 6, -180 + 24 + 180),
                QtCore.QPointF(192 + 72, -180 + 180),
            )

            for thing in PointsRects:  # translate each point to flip the image
                if direction == 0:  # faces left
                    arc = 'LR'
                elif direction == 1:  # faces right
                    arc = 'LR'
                    if isinstance(thing, QtCore.QPointF):
                        thing.setX(408 - thing.x())
                    else:
                        thing.setRect(408 - thing.x(), thing.y(), -thing.width(), thing.height())
                elif direction == 2:  # faces down
                    arc = 'UD'
                    if isinstance(thing, QtCore.QPointF):
                        x = thing.y()
                        y = 408 - thing.x()
                        thing.setX(x)
                        thing.setY(y)
                    else:
                        x = thing.y()
                        y = 408 - thing.x()
                        thing.setRect(x, y, thing.height(), -thing.width())
                else:  # faces up
                    arc = 'UD'
                    if isinstance(thing, QtCore.QPointF):
                        x = thing.y()
                        y = thing.x()
                        thing.setX(x)
                        thing.setY(y)
                    else:
                        x = thing.y()
                        y = thing.x()
                        thing.setRect(x, y, thing.height(), thing.width())

            PainterPath = QtGui.QPainterPath()
            PainterPath.moveTo(PointsRects[0])
            if arc == 'LR':
                PainterPath.arcTo(PointsRects[1], 90, 180)
            else:
                PainterPath.arcTo(PointsRects[1], 180, -180)
            for point in PointsRects[2:]:
                PainterPath.lineTo(point)
            PainterPath.closeSubpath()
            self.paths.append(PainterPath)

    def dataChanged(self):

        direction = self.parent.spritedata[5] & 3

        self.aux[0].setPath(self.paths[direction])

        newx, newy = (
            (0, (-8 * 24) + 12),
            ((-24 * 16), (-8 * 24) + 12),
            ((-24 * 10), (-24 * 16)),
            ((-24 * 5), 0),
        )[direction]
        self.aux[0].setPos(newx, newy)

        super().dataChanged()


class SpriteImage_CheepGiant(SLib.SpriteImage):  # 334
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.aux.append(SLib.AuxiliaryTrackObject(self.parent, 24, 24, SLib.AuxiliaryTrackObject.Horizontal))

    @staticmethod
    def loadImages():
        if 'CheepGiantRedLeft' in ImageCache: return
        ImageCache['CheepGiantRedLeft'] = SLib.GetImg('cheep_giant_red.png')
        ImageCache['CheepGiantRedAtYou'] = SLib.GetImg('cheep_giant_red_atyou.png')
        ImageCache['CheepGiantGreen'] = SLib.GetImg('cheep_giant_green.png')
        ImageCache['CheepGiantYellow'] = SLib.GetImg('cheep_giant_yellow.png')

    def dataChanged(self):

        type = self.parent.spritedata[5] & 0xF
        if type in (1, 7):
            self.image = ImageCache['CheepGiantGreen']
        elif type == 8:
            self.image = ImageCache['CheepGiantYellow']
        elif type == 5:
            self.image = ImageCache['CheepGiantRedAtYou']
        else:
            self.image = ImageCache['CheepGiantRedLeft']
        self.size = (self.image.width() / 1.5, self.image.height() / 1.5)
        self.xOffset = 0 if type != 5 else -8

        if type == 3:
            distance = ((self.parent.spritedata[3] & 0xF) + 1) * 16
            self.aux[0].setSize((distance * 2) + 16, 16)
            self.aux[0].setPos(-distance * 1.5, 8)
        else:
            self.aux[0].setSize(0, 24)

        super().dataChanged()

    def paint(self, painter):
        super().paint(painter)
        painter.drawPixmap(0, 0, self.image)


# Copied and edited from Miyamoto, credit to mrbengtsson for original code
class SpriteImage_MovingBulletBillLauncher(SLib.SpriteImage):  # 338
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('BBLauncherT', 'bullet_launcher_top.png')
        SLib.loadIfNotInImageCache('BBLauncherM', 'bullet_launcher_middle.png')


    def dataChanged(self):
        self.image = None
        self.xOffset = 0
        self.width = 16

        self.cannonHeight = (self.parent.spritedata[5] & 0xF0) >> 4
        self.cannonHeightTwo = self.parent.spritedata[5] & 0xF

        if self.cannonHeight >= self.cannonHeightTwo:
            self.height = (self.cannonHeight + 2) * 16

        else:
            self.height = (self.cannonHeightTwo + 2) * 16

        if self.cannonHeight >= self.cannonHeightTwo:
            self.yOffset = -(self.cannonHeight + 1) * 16

        else:
            self.yOffset = -(self.cannonHeightTwo + 1) * 16

        super().dataChanged()

    def paint(self, painter):
        if self.cannonHeightTwo > self.cannonHeight:
            painter.setOpacity(0.5)
            painter.drawPixmap(0, 0, 24, 48, ImageCache['BBLauncherT'])
            painter.drawTiledPixmap(0, 48, 24, 24 * self.cannonHeightTwo, ImageCache['BBLauncherM'])
            painter.setOpacity(1)

            painter.drawPixmap(0, 24 * (self.cannonHeightTwo - self.cannonHeight), 24, 48, ImageCache['BBLauncherT'])
            painter.drawTiledPixmap(0, 24 * (self.cannonHeightTwo - self.cannonHeight + 2), 24, 48 * self.cannonHeight, ImageCache['BBLauncherM'])

        else:
            painter.drawPixmap(0, 0, 24, 48, ImageCache['BBLauncherT'])
            painter.drawTiledPixmap(0, 48, 24, 24 * self.cannonHeight, ImageCache['BBLauncherM'])


class SpriteImage_MortonKoopaCastleBoss(SLib.SpriteImage):  # 349
    def __init__(self, parent):
        super().__init__(parent)
        self.parent.setZValue(24999)

        self.aux.append(SLib.AuxiliaryImage(parent, 552, 408))
        self.aux[0].image = ImageCache['MortonKoopaCastleBoss']
        self.aux[0].setPos(48, 0)
        self.aux.append(SLib.AuxiliaryRectOutline(parent, 24, 24, 0, 288))

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('MortonKoopaCastleBoss', 'morton_castle_boss.png')


class SpriteImage_BrownBlock(SLib.SpriteImage):  # 356
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.aux.append(SLib.AuxiliaryTrackObject(parent, 16, 16, SLib.AuxiliaryTrackObject.Horizontal))

    @staticmethod
    def loadImages():
        for vert in 'TMB':
            for horz in 'LMR':
                SLib.loadIfNotInImageCache(
                    'BrownBlock' + vert + horz,
                    'brown_block_%s%s.png' % (vert, horz)
                )

    def dataChanged(self):
        super().dataChanged()

        size = self.parent.spritedata[5]
        height = size >> 4
        width = size & 0xF
        height = 1 if height == 0 else height
        width = 1 if width == 0 else width
        self.width = width * 16 + 16
        self.height = height * 16 + 16

        # now set up the track
        direction = self.parent.spritedata[2] & 3
        distance = (self.parent.spritedata[4] & 0xF0) >> 4

        if direction <= 1:  # horizontal
            self.aux[0].direction = 1
            self.aux[0].setSize(self.width + (distance * 16), self.height)
        else:  # vertical
            self.aux[0].direction = 2
            self.aux[0].setSize(self.width, self.height + (distance * 16))

        if (direction in (0, 3)) or (direction not in (1, 2)):  # right, down
            self.aux[0].setPos(0, 0)
        elif direction == 1:  # left
            self.aux[0].setPos(-distance * 24, 0)
        elif direction == 2:  # up
            self.aux[0].setPos(0, -distance * 24)

    def paint(self, painter):
        super().paint(painter)

        width = int(self.width * 1.5)
        height = int(self.height * 1.5)

        column2x = 24
        column3x = width - 24
        row2y = 24
        row3y = height - 24

        painter.drawPixmap(0, 0, ImageCache['BrownBlockTL'])
        painter.drawTiledPixmap(column2x, 0, width - 48, 24, ImageCache['BrownBlockTM'])
        painter.drawPixmap(column3x, 0, ImageCache['BrownBlockTR'])

        painter.drawTiledPixmap(0, row2y, 24, height - 48, ImageCache['BrownBlockML'])
        painter.drawTiledPixmap(column2x, row2y, width - 48, height - 48, ImageCache['BrownBlockMM'])
        painter.drawTiledPixmap(column3x, row2y, 24, height - 48, ImageCache['BrownBlockMR'])

        painter.drawPixmap(0, row3y, ImageCache['BrownBlockBL'])
        painter.drawTiledPixmap(column2x, row3y, width - 48, 24, ImageCache['BrownBlockBM'])
        painter.drawPixmap(column3x, row3y, ImageCache['BrownBlockBR'])


class SpriteImage_WallLantern(SLib.SpriteImage):  # 359
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.aux.append(SLib.AuxiliaryImage(parent, 128, 128))
        self.aux[0].image = ImageCache['WallLanternAux']
        self.aux[0].setPos(-48, -48)
        self.aux[0].hover = False

        self.image = ImageCache['WallLantern']
        self.yOffset = 8

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('WallLantern', 'wall_lantern.png')
        SLib.loadIfNotInImageCache('WallLanternAux', 'wall_lantern_aux.png')

    def paint(self, painter):
        super().paint(painter)
        painter.drawPixmap(0, 0, self.image)


class SpriteImage_ColoredBox(SLib.SpriteImage):  # 362
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

    @staticmethod
    def loadImages():
        if 'CBox0TL' in ImageCache: return
        for color in range(4):
            for direction in ('TL', 'T', 'TR', 'L', 'M', 'R', 'BL', 'B', 'BR'):
                ImageCache['CBox%d%s' % (color, direction)] = SLib.GetImg('cbox_%s_%d.png' % (direction, color))

    def dataChanged(self):
        super().dataChanged()
        self.color = (self.parent.spritedata[3] >> 4) & 3

        size = self.parent.spritedata[4]
        width = size >> 4
        height = size & 0xF

        self.width = (width + 3) * 16
        self.height = (height + 3) * 16

    def paint(self, painter):
        super().paint(painter)

        prefix = 'CBox%d' % self.color
        xsize = int(self.width * 1.5)
        ysize = int(self.height * 1.5)

        painter.drawPixmap(0, 0, ImageCache[prefix + 'TL'])
        painter.drawPixmap(xsize - 25, 0, ImageCache[prefix + 'TR'])
        painter.drawPixmap(0, ysize - 25, ImageCache[prefix + 'BL'])
        painter.drawPixmap(xsize - 25, ysize - 25, ImageCache[prefix + 'BR'])

        painter.drawTiledPixmap(25, 0, xsize - 50, 25, ImageCache[prefix + 'T'])
        painter.drawTiledPixmap(25, ysize - 25, xsize - 50, 25, ImageCache[prefix + 'B'])
        painter.drawTiledPixmap(0, 25, 25, ysize - 50, ImageCache[prefix + 'L'])
        painter.drawTiledPixmap(xsize - 25, 25, 25, ysize - 50, ImageCache[prefix + 'R'])

        painter.drawTiledPixmap(25, 25, xsize - 50, ysize - 50, ImageCache[prefix + 'M'])


class SpriteImage_RoyKoopaCastleBoss(SLib.SpriteImage):  # 364
    def __init__(self, parent):
        super().__init__(parent)
        self.parent.setZValue(24999)

        self.aux.append(SLib.AuxiliaryImage(parent, 528, 384))
        self.aux[0].image = ImageCache['RoyKoopaCastleBoss']
        self.aux[0].setPos(72, -96)
        self.aux.append(SLib.AuxiliaryRectOutline(parent, 24, 24, 24, 312))

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('RoyKoopaCastleBoss', 'roy_castle_boss.png')


class SpriteImage_LudwigVonKoopaCastleBoss(SLib.SpriteImage):  # 365
    def __init__(self, parent):
        super().__init__(parent)
        self.parent.setZValue(24999)

        self.aux.append(SLib.AuxiliaryImage(parent, 720, 840))
        self.aux[0].image = ImageCache['LudwigVonKoopaCastleBoss']
        self.aux[0].setPos(-24, -360)
        self.aux.append(SLib.AuxiliaryRectOutline(parent, 24, 24, 24, 288))
        self.aux.append(SLib.AuxiliaryRectOutline(parent, 528, 24, 72, 264))
        self.aux[2].fillFlag = False

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('LudwigVonKoopaCastleBoss', 'ludwig_castle_boss.png')


class SpriteImage_IggyKoopaCastleBoss(SLib.SpriteImage):  # 372
    def __init__(self, parent):
        super().__init__(parent)
        self.aux.append(SLib.AuxiliaryImage(parent, 240, 288))
        self.parent.setZValue(24999)
        self.aux[0].image = ImageCache['IggyKoopaCastleBoss']
        self.aux[0].setSize(240, 288, 360, 48)

        self.aux.append(SLib.AuxiliaryRectOutline(parent, 24, 24, 24, 312))

        self.aux.append(SLib.AuxiliaryRectOutline(parent, 528, 264, 72, 24))
        self.aux[2].fillFlag = False

        w = SLib.OutlinePen.widthF()
        self.aux.append(SLib.AuxiliaryRectOutline(parent, 336 + w, 24 + w, 168 - w / 2, 144 - w / 2))
        self.aux[3].fillFlag = False

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('IggyKoopaCastleBoss', 'iggy_castle_boss.png')


class SpriteImage_WendyKoopaCastleBoss(SLib.SpriteImage):  # 375
    def __init__(self, parent):
        super().__init__(parent)
        self.parent.setZValue(24999)

        self.aux.append(SLib.AuxiliaryImage(parent, 648, 528))
        self.aux[0].image = ImageCache['WendyKoopaCastleBoss']
        self.aux[0].setPos(0, -120)
        self.aux.append(SLib.AuxiliaryRectOutline(parent, 24, 24, 0, 288))

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('WendyKoopaCastleBoss', 'wendy_castle_boss.png')


class SpriteImage_MovingFence(SLib.SpriteImage):  # 376
    def __init__(self, parent, scale=1.5):
        super().__init__(parent, scale)
        self.spritebox.shown = False
        self.aux.append(SLib.AuxiliaryTrackObject(parent, 16, 16, SLib.AuxiliaryTrackObject.Horizontal))

    @staticmethod
    def loadImages():
        if 'MovingFence0' in ImageCache: return
        for shape in range(4):
            ImageCache['MovingFence%d' % shape] = SLib.GetImg('moving_fence_%d.png' % shape)

    def dataChanged(self):
        super().dataChanged()

        self.shape = (self.parent.spritedata[4] >> 4) & 3
        direction = self.parent.spritedata[5] & 1
        distance = (self.parent.spritedata[5] & 0xF0) >> 4

        self.size = (
            (64, 64),
            (64, 128),
            (64, 224),
            (192, 64)
        )[self.shape]

        self.xOffset = -self.size[0] / 2
        self.yOffset = -self.size[1] / 2

        if distance == 0:
            self.aux[0].setSize(0, 0)
        elif direction == 1: # horizontal
            self.aux[0].direction = 1
            self.aux[0].setSize((distance * 32) + self.width, 16)
            self.aux[0].setPos(-distance * 24, (self.height * 0.75) - 12)
        else: # vertical
            self.aux[0].direction = 2
            self.aux[0].setSize(16, (distance * 32) + self.height)
            self.aux[0].setPos((self.width * 0.75) - 12, -distance * 24)

    def paint(self, painter):
        super().paint(painter)

        painter.drawPixmap(0, 0, ImageCache['MovingFence%d' % self.shape])


class SpriteImage_LemmyKoopaCastleBoss(SLib.SpriteImage):  # 381
    def __init__(self, parent):
        super().__init__(parent)
        self.parent.setZValue(24999)

        self.aux.append(SLib.AuxiliaryImage(parent, 552, 216))
        self.aux[0].image = ImageCache['LemmyKoopaCastleBoss']
        self.aux[0].setPos(48, 168)
        self.aux.append(SLib.AuxiliaryRectOutline(parent, 24, 24, 0, 312))

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('LemmyKoopaCastleBoss', 'lemmy_castle_boss.png')


class SpriteImage_KamekController(SLib.SpriteImage):  # 383
    def __init__(self, parent):
        super().__init__(parent)
        self.aux.append(SLib.AuxiliaryImage(parent, 1272, 360))
        self.parent.setZValue(24999)
        self.aux[0].image = ImageCache['KamekController']
        self.aux[0].setPos(-144, 48)
        self.aux.append(SLib.AuxiliaryRectOutline(parent, 1154, 360, 0, 48))
        self.aux[1].fillFlag = False

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('KamekController', 'boss_controller_kamek.png')


class SpriteImage_PipeCooliganGenerator(SLib.SpriteImage):  # 384
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.size = (16, 32)
        self.spritebox.yOffset = -16


class SpriteImage_GlowBlock(SLib.SpriteImage):  # 391
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.aux.append(SLib.AuxiliaryImage(parent, 48, 48))
        self.aux[0].image = ImageCache['GlowBlock']
        self.aux[0].setPos(-12, -12)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('GlowBlock', 'glow_block.png')


class SpriteImage_MoveWhenOn(SLib.SpriteImage):  # 396
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

    @staticmethod
    def loadImages():
        if 'MoveWhenOnL' in ImageCache: return
        ImageCache['MoveWhenOnL'] = SLib.GetImg('mwo_left.png')
        ImageCache['MoveWhenOnM'] = SLib.GetImg('mwo_middle.png')
        ImageCache['MoveWhenOnR'] = SLib.GetImg('mwo_right.png')
        ImageCache['MoveWhenOnC'] = SLib.GetImg('mwo_circle.png')

        transform90 = QtGui.QTransform()
        transform180 = QtGui.QTransform()
        transform270 = QtGui.QTransform()
        transform90.rotate(90)
        transform180.rotate(180)
        transform270.rotate(270)

        image = SLib.GetImg('sm_arrow.png', True)
        ImageCache['SmArrowR'] = QtGui.QPixmap.fromImage(image)
        ImageCache['SmArrowD'] = QtGui.QPixmap.fromImage(image.transformed(transform90))
        ImageCache['SmArrowL'] = QtGui.QPixmap.fromImage(image.transformed(transform180))
        ImageCache['SmArrowU'] = QtGui.QPixmap.fromImage(image.transformed(transform270))

    def dataChanged(self):
        super().dataChanged()

        # get width
        self.raw_size = self.parent.spritedata[5] & 0xF
        if self.raw_size == 0:
            self.xOffset = -16
            self.width = 32
        else:
            self.xOffset = 0
            self.width = self.raw_size * 16

        # set direction
        self.direction = (self.parent.spritedata[3] >> 4) % 5

    def paint(self, painter):
        super().paint(painter)

        direction = ("R", "L", "U", "D", None)[self.direction]

        if self.raw_size == 0:
            # hack for the glitchy version
            painter.drawPixmap(0, 2, ImageCache['MoveWhenOnR'])
            painter.drawPixmap(24, 2, ImageCache['MoveWhenOnL'])
        elif self.raw_size == 1:
            painter.drawPixmap(0, 2, ImageCache['MoveWhenOnM'])
        else:
            painter.drawPixmap(0, 2, ImageCache['MoveWhenOnL'])
            if self.raw_size > 2:
                painter.drawTiledPixmap(24, 2, (self.raw_size - 2) * 24, 24, ImageCache['MoveWhenOnM'])
            painter.drawPixmap(int((self.width * 1.5) - 24), 2, ImageCache['MoveWhenOnR'])

        center = int((self.width / 2) * 1.5)
        painter.drawPixmap(center - 14, 0, ImageCache['MoveWhenOnC'])
        if direction is not None:
            painter.drawPixmap(center - 12, 1, ImageCache['SmArrow%s' % direction])


class SpriteImage_GhostHouseBox(SLib.SpriteImage):  # 397
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

    @staticmethod
    def loadImages():
        if 'GHBoxTL' in ImageCache: return
        for direction in ('TL', 'T', 'TR', 'L', 'M', 'R', 'BL', 'B', 'BR'):
            ImageCache['GHBox%s' % direction] = SLib.GetImg('ghbox_%s.png' % direction)

    def dataChanged(self):
        super().dataChanged()

        height = self.parent.spritedata[4] >> 4
        width = self.parent.spritedata[5] & 15

        self.width = (width + 2) * 16
        self.height = (height + 2) * 16

    def paint(self, painter):
        super().paint(painter)

        prefix = 'GHBox'
        xsize = int(self.width * 1.5)
        ysize = int(self.height * 1.5)

        # Corners
        painter.drawPixmap(0, 0, ImageCache[prefix + 'TL'])
        painter.drawPixmap(xsize - 24, 0, ImageCache[prefix + 'TR'])
        painter.drawPixmap(0, ysize - 24, ImageCache[prefix + 'BL'])
        painter.drawPixmap(xsize - 24, ysize - 24, ImageCache[prefix + 'BR'])

        # Edges
        painter.drawTiledPixmap(24, 0, xsize - 48, 24, ImageCache[prefix + 'T'])
        painter.drawTiledPixmap(24, ysize - 24, xsize - 48, 24, ImageCache[prefix + 'B'])
        painter.drawTiledPixmap(0, 24, 24, ysize - 48, ImageCache[prefix + 'L'])
        painter.drawTiledPixmap(xsize - 24, 24, 24, ysize - 48, ImageCache[prefix + 'R'])

        # Middle
        painter.drawTiledPixmap(24, 24, xsize - 48, ysize - 48, ImageCache[prefix + 'M'])


class SpriteImage_BowserJr2ndController(SLib.SpriteImage):  # 405
    def __init__(self, parent):
        super().__init__(parent)
        self.parent.setZValue(24999)

        self.aux.append(SLib.AuxiliaryImage(parent, 672, 384))
        self.aux[0].image = ImageCache['BowserJr2ndController']
        self.aux[0].setPos(-504, -336)

        self.aux.append(SLib.AuxiliaryRectOutline(parent, 24, 24, -504, -312))

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('BowserJr2ndController', 'boss_controller_bowserjr_2.png')


class SpriteImage_BowserJr3rdController(SLib.SpriteImage):  # 406
    def __init__(self, parent):
        super().__init__(parent)
        self.parent.setZValue(24999)

        self.aux.append(SLib.AuxiliaryImage(parent, 672, 372))
        self.aux[0].image = ImageCache['BowserJr3rdController']
        self.aux[0].setPos(-324, -192)

        self.aux.append(SLib.AuxiliaryRectOutline(parent, 24, 24, -324, -192))

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('BowserJr3rdController', 'boss_controller_bowserjr_3.png')


class SpriteImage_BossControllerCastleBoss(SLib.SpriteImage):  # 407
    def __init__(self, parent):
        super().__init__(parent)

        self.aux.append(SLib.AuxiliaryImage(parent, 48, 96))
        self.aux.append(SLib.AuxiliaryImage(parent, 48, 96))
        self.aux.append(SLib.AuxiliaryImage(parent, 48, 96))
        self.aux.append(SLib.AuxiliaryImage(parent, 48, 96))
        self.aux[0].image = ImageCache['ShutterDoor']
        self.aux[1].image = ImageCache['ShutterDoor']
        self.aux[1].alpha = 0.375
        self.aux[2].image = ImageCache['ShutterDoor']
        self.aux[3].image = ImageCache['ShutterDoor']
        self.aux[3].alpha = 0.375

    def dataChanged(self):
        boss = (self.parent.spritedata[5] & 0xF) % 7

        self.aux[0].setPos(*(
                (0, -216),
                (0, -216),
                (0, -216),
                (0, -216),
                (0, -216),
                (0, -240),
                (0, -216)
        )[boss])
        self.aux[1].setPos(self.aux[0].x(), self.aux[0].y() + 96)
        self.aux[2].setPos(*(
                (576, -120),
                (576, -120),
                (600, -120),
                (576, -120),
                (576, -120),
                (600, -120),
                (576, -487)
            )[boss])
        self.aux[3].setPos(self.aux[2].x(), self.aux[2].y() - 96)

        super().dataChanged()

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('ShutterDoor', 'shutter_door.png')


class SpriteImage_GiantGlowBlock(SLib.SpriteImage):  # 420
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.aux.append(SLib.AuxiliaryImage(parent, 100, 100))
        self.size = (32, 32)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('GiantGlowBlockOn', 'giant_glow_block.png')
        SLib.loadIfNotInImageCache('GiantGlowBlockOff', 'giant_glow_block_off.png')

    def dataChanged(self):
        super().dataChanged()

        type = self.parent.spritedata[4] >> 4
        if type == 0:
            self.aux[0].image = ImageCache['GiantGlowBlockOn']
            self.aux[0].setSize(100, 100, -25, -30)
        else:
            self.aux[0].image = ImageCache['GiantGlowBlockOff']
            self.aux[0].setSize(48, 48)


class SpriteImage_BowserController(SLib.SpriteImage):  # 431
    def __init__(self, parent):
        super().__init__(parent)

        self.aux.append(SLib.AuxiliaryImage(parent, 48, 288))
        self.aux[0].image = ImageCache['BowserShutterDoor']
        self.aux[0].setPos(1248, -288)

        self.aux.append(SLib.AuxiliaryRectOutline(parent, 768, 408, 1248, -336))
        self.aux[1].fillFlag = False

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('BowserShutterDoor', 'bowser_shutter_door.png')


class SpriteImage_PurplePole(SLib.SpriteImage):  # 437
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

    @staticmethod
    def loadImages():
        if 'VertPole' in ImageCache: return
        ImageCache['VertPoleTop'] = SLib.GetImg('purple_pole_top.png')
        ImageCache['VertPole'] = SLib.GetImg('purple_pole_middle.png')
        ImageCache['VertPoleBottom'] = SLib.GetImg('purple_pole_bottom.png')

    def dataChanged(self):
        super().dataChanged()

        length = self.parent.spritedata[5]
        self.height = (length + 3) * 16

    def paint(self, painter):
        super().paint(painter)

        painter.drawPixmap(0, 0, ImageCache['VertPoleTop'])
        painter.drawTiledPixmap(0, 24, 24, int(self.height * 1.5 - 48), ImageCache['VertPole'])
        painter.drawPixmap(0, int(self.height * 1.5 - 24), ImageCache['VertPoleBottom'])


class SpriteImage_HorizontalRope(SLib.SpriteImage):  # 440
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('HorzRope', 'horizontal_rope_middle.png')
        SLib.loadIfNotInImageCache('HorzRopeEnd', 'horizontal_rope_end.png')

    def dataChanged(self):
        super().dataChanged()

        length = self.parent.spritedata[5]
        self.width = (length + 3) * 16

    def paint(self, painter):
        super().paint(painter)

        endpiece = ImageCache['HorzRopeEnd']
        painter.drawPixmap(0, 0, endpiece)
        painter.drawTiledPixmap(24, 0, int(self.width * 1.5 - 48), 24, ImageCache['HorzRope'])
        painter.drawPixmap(int(self.width * 1.5 - 24), 0, endpiece)


class SpriteImage_MushroomPlatform(SLib.SpriteImage):  # 441
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

    @staticmethod
    def loadImages():
        if 'RedShroomL' in ImageCache: return
        ImageCache['RedShroomL'] = SLib.GetImg('red_mushroom_left.png')
        ImageCache['RedShroomM'] = SLib.GetImg('red_mushroom_middle.png')
        ImageCache['RedShroomR'] = SLib.GetImg('red_mushroom_right.png')
        ImageCache['GreenShroomL'] = SLib.GetImg('green_mushroom_left.png')
        ImageCache['GreenShroomM'] = SLib.GetImg('green_mushroom_middle.png')
        ImageCache['GreenShroomR'] = SLib.GetImg('green_mushroom_right.png')
        ImageCache['BlueShroomL'] = SLib.GetImg('blue_mushroom_left.png')
        ImageCache['BlueShroomM'] = SLib.GetImg('blue_mushroom_middle.png')
        ImageCache['BlueShroomR'] = SLib.GetImg('blue_mushroom_right.png')
        ImageCache['OrangeShroomL'] = SLib.GetImg('orange_mushroom_left.png')
        ImageCache['OrangeShroomM'] = SLib.GetImg('orange_mushroom_middle.png')
        ImageCache['OrangeShroomR'] = SLib.GetImg('orange_mushroom_right.png')

    def dataChanged(self):
        super().dataChanged()

        # get size/color
        self.color = self.parent.spritedata[4] & 1
        self.shroomsize = (self.parent.spritedata[5] >> 4) & 1
        self.height = 16 * (self.shroomsize + 1)

        # get width
        width = self.parent.spritedata[5] & 0xF
        if self.shroomsize == 0:
            self.width = (width << 4) + 32
            self.offset = (
                0 - (((width + 1) // 2) << 4),
                0,
            )
        else:
            self.width = (width << 5) + 64
            self.offset = (
                16 - (self.width / 2),
                -16,
            )

    def paint(self, painter):
        super().paint(painter)

        tilesize = 24 + (self.shroomsize * 24)
        if self.shroomsize == 0:
            if self.color == 0:
                color = 'Orange'
            else:
                color = 'Blue'
        else:
            if self.color == 0:
                color = 'Red'
            else:
                color = 'Green'

        painter.drawPixmap(0, 0, ImageCache[color + 'ShroomL'])
        painter.drawTiledPixmap(tilesize, 0, int((self.width * 1.5) - (tilesize * 2)), tilesize,
                                ImageCache[color + 'ShroomM'])
        painter.drawPixmap(int(self.width * 1.5) - tilesize, 0, ImageCache[color + 'ShroomR'])


class SpriteImage_UnderwaterLamp(SLib.SpriteImage):  # 447
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

        self.aux.append(SLib.AuxiliaryImage(parent, 105, 105))
        self.aux[0].image = ImageCache['UnderwaterLamp']
        self.aux[0].setPos(-34, -34)

        self.dimensions = (-4, -4, 24, 26)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('UnderwaterLamp', 'underwater_lamp.png')


class SpriteImage_LongMetalBar(SLib.SpriteImage):  # 458
    def __init__(self, parent):
        super().__init__(parent)
        i = ImageCache['LongMetalBar']
        self.aux.append(SLib.AuxiliaryImage(parent, i.width(), i.height()))
        self.aux[0].image = i
        self.aux[0].setSize(i.width(), i.height(), -252, -24)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('LongMetalBar', 'long_metal_bar.png')


class SpriteImage_EnormousBlock(SLib.SpriteImage):  # 462
    def __init__(self, parent):
        super().__init__(parent, 1.5)

        self.aux.append(SLib.AuxiliaryRectOutline(parent, 24, 24))
        self.aux.append(
            SLib.AuxiliaryPainterPath(parent, QtGui.QPainterPath(), 24, 24)
        )
        self.aux.append(
            SLib.AuxiliaryTrackObject(parent, 16, 16, SLib.AuxiliaryTrackObject.Horizontal)
        )

        self.spikes = []
        for height in (28, 16, 41, 47, 31):
            spikes = []
            for direction in range(2):
                # This has to be within the loop because the
                # following commands transpose them
                if direction == 0:
                    points = ((0, 0), (24, 12))
                else:
                    # faces right
                    points = ((24, 0), (0, 12))

                painterPath = QtGui.QPainterPath()
                painterPath.moveTo(direction * 24, 0)
                for i in range(height):
                    for point in points:
                        painterPath.lineTo(QtCore.QPointF(point[0], point[1] + i * 24))
                painterPath.lineTo(QtCore.QPointF(direction * 24, height * 24))
                painterPath.closeSubpath()
                spikes.append(painterPath)
            self.spikes.append(spikes)

    def dataChanged(self):
        # get sprite data
        size = (self.parent.spritedata[5] >> 1) & 7
        direction = self.parent.spritedata[2] & 1
        distance = (self.parent.spritedata[4] >> 4) + 1
        side = self.parent.spritedata[5] & 1

        # update the platform
        realsize = ((18, 28), (18, 16), (18, 41), (18, 47), (24, 31))[size]
        self.aux[0].setSize(realsize[0] * 24 - 24, realsize[1] * 24)
        if side == 0:
            self.aux[0].setPos(0, 0)
        else:
            self.aux[0].setPos(24, 0)

        # update the spikes
        self.aux[1].setSize(48, realsize[1] * 24 + 24)
        if side == 0:
            self.aux[1].setPos(realsize[0] * 24 - 24, 0)
        else:
            self.aux[1].setPos(0, 0)
        self.aux[1].setPath(self.spikes[size][side])

        # update the track
        self.aux[2].setSize(distance * 16, 16)
        halfheight = realsize[1] * 12 - 12
        halfwidth = realsize[0] * 12
        if direction == 0:
            self.aux[2].setPos(halfwidth, halfheight)
        else:
            self.aux[2].setPos(halfwidth - distance * 24, halfheight)


class SpriteImage_Glare(SLib.SpriteImage):  # 463
    def __init__(self, parent):
        super().__init__(parent)
        self.aux.append(SLib.AuxiliaryImage(parent, 1000, 1000))
        self.aux[0].image = ImageCache['SunGlare']
        self.aux[0].setSize(9 * 24, 9 * 24, -4 * 24 - 5, -4 * 24 - 20)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('SunGlare', 'glare.png')


class SpriteImage_BoltPlatform(SLib.SpriteImage):  # 469
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False

    @staticmethod
    def loadImages():
        if 'BoltPlatformL' in ImageCache: return
        ImageCache['BoltPlatformL'] = SLib.GetImg('bolt_platform_left.png')
        ImageCache['BoltPlatformM'] = SLib.GetImg('bolt_platform_middle.png')
        ImageCache['BoltPlatformR'] = SLib.GetImg('bolt_platform_right.png')

    def dataChanged(self):
        self.offset = (0, -2)
        super().dataChanged()

        length = self.parent.spritedata[5] & 0xF
        self.width = (length + 2) * 16

    def paint(self, painter):
        super().paint(painter)

        painter.drawPixmap(0, 0, ImageCache['BoltPlatformL'])
        painter.drawTiledPixmap(24, 3, int(self.width * 1.5) - 48, 24, ImageCache['BoltPlatformM'])
        painter.drawPixmap(int(self.width * 1.5) - 24, 0, ImageCache['BoltPlatformR'])


class SpriteImage_IceFloeGenerator(SLib.SpriteImage):  # 472
    def __init__(self, parent):
        super().__init__(parent)
        self.aux.append(SLib.AuxiliaryRectOutline(parent, 96, 120, 0, -96))


class SpriteImage_FloatingIceFloeGenerator(SLib.SpriteImage):  # 473
    def __init__(self, parent):
        super().__init__(parent)
        self.aux.append(SLib.AuxiliaryRectOutline(parent, 96, 96, 0, 24))


class SpriteImage_MortonSpikedStake(SLib.SpriteImage):  # 480
    def __init__(self, parent):
        super().__init__(parent)
        self.spritebox.shown = False
        self.dimensions = (0, -368, 64, 410)
        self.aux.append(SLib.AuxiliaryTrackObject(parent, 36, 591, SLib.AuxiliaryTrackObject.Vertical))

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('MortonStakeM', 'stake_down_m_0.png')
        SLib.loadIfNotInImageCache('MortonStakeE', 'stake_down_e_0.png')

    def dataChanged(self):
        super().dataChanged()

        self.aux[0].setPos(36, 591)
        self.aux[0].setSize(16, 160)

    def paint(self, painter):
        super().paint(painter)

        painter.drawTiledPixmap(0, 0, 98, 576, ImageCache['MortonStakeM'])
        painter.drawPixmap(0, 576, ImageCache['MortonStakeE'])


class SpriteImage_FinalBossEffects(SLib.SpriteImage):  # 482
    def __init__(self, parent):
        super().__init__(parent)
        self.aux.append(SLib.AuxiliaryImage(parent, 3612, 672))
        self.aux[0].image = ImageCache['FinalBossEffects0']
        self.aux[0].setPos(-228, -555)
        self.parent.setZValue(24999)

    @staticmethod
    def loadImages():
        if 'FinalBossEffects0' in ImageCache: return

        for i in range(3):
            ImageCache["FinalBossEffects%d" % i] = SLib.GetImg("final_boss_effects_%d.png" % i)

    def dataChanged(self):
        style = self.parent.spritedata[5] & 15

        # Styles greater than 2 load nothing
        if style > 2:
            self.aux[0].image = None

        else:
            self.aux[0].image = ImageCache['FinalBossEffects%d' % style]

            if style == 0:
                self.aux[0].setPos(-228, -555)
            elif style == 1:
                self.aux[0].setPos(-228, -408)
            else:
                self.aux[0].setPos(-24, -192)

        super().dataChanged()
