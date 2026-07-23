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



class SpriteImage_CharacterSpawner(SLib.SpriteImage_StaticMultiple):  # 9
    def dataChanged(self):
        direction = self.parent.spritedata[2] & 1
        character = self.parent.spritedata[5] & 3

        directionstr = 'L' if direction else 'R'

        self.image = ImageCache['Character' + str(character + 1) + directionstr]

        self.offset = (
            -(self.image.width() / 3),
            -(self.image.height() / 1.5),
        )

        super().dataChanged()


class SpriteImage_BuzzyBeetle(SLib.SpriteImage_StaticMultiple):  # 24
    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('BuzzyBeetle', 'buzzy_beetle.png')
        SLib.loadIfNotInImageCache('BuzzyBeetleU', 'buzzy_beetle_u.png')
        SLib.loadIfNotInImageCache('BuzzyBeetleShell', 'buzzy_beetle_shell.png')
        SLib.loadIfNotInImageCache('BuzzyBeetleShellU', 'buzzy_beetle_shell_u.png')

    def dataChanged(self):

        orient = self.parent.spritedata[5] & 15
        if orient == 1:
            self.image = ImageCache['BuzzyBeetleU']
            self.yOffset = 0
        elif orient == 2:
            self.image = ImageCache['BuzzyBeetleShell']
            self.yOffset = 2
        elif orient == 3:
            self.image = ImageCache['BuzzyBeetleShellU']
            self.yOffset = 2
        else:
            self.image = ImageCache['BuzzyBeetle']
            self.yOffset = 0

        super().dataChanged()


class SpriteImage_Spiny(SLib.SpriteImage_StaticMultiple):  # 25
    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Spiny', 'spiny.png')
        SLib.loadIfNotInImageCache('SpinyShell', 'spiny_shell.png')
        SLib.loadIfNotInImageCache('SpinyShellU', 'spiny_shell_u.png')
        SLib.loadIfNotInImageCache('SpinyBall', 'spiny_ball.png')

    def dataChanged(self):

        orient = self.parent.spritedata[5] & 15
        if orient == 1:
            self.image = ImageCache['SpinyBall']
            self.yOffset = -2
        elif orient == 2:
            self.image = ImageCache['SpinyShell']
            self.yOffset = 1
        elif orient == 3:
            self.image = ImageCache['SpinyShellU']
            self.yOffset = 2
        else:
            self.image = ImageCache['Spiny']
            self.yOffset = 0

        super().dataChanged()


class SpriteImage_QSwitchBlock(SLib.SpriteImage_StaticMultiple):  # 43
    @staticmethod
    def loadImages():
        if 'QSwitchBlock' not in ImageCache:
            q = SLib.GetImg('q_switch_block.png', True)
            ImageCache['QSwitchBlock'] = QtGui.QPixmap.fromImage(q)
            ImageCache['QSwitchBlockU'] = QtGui.QPixmap.fromImage(q.mirrored(True, True))

    def dataChanged(self):
        upsideDown = self.parent.spritedata[5] & 1

        if upsideDown:
            self.image = ImageCache['QSwitchBlockU']
        else:
            self.image = ImageCache['QSwitchBlock']

        super().dataChanged()


class SpriteImage_ExcSwitchBlock(SLib.SpriteImage_StaticMultiple):  # 45
    @staticmethod
    def loadImages():
        if 'ESwitchBlock' not in ImageCache:
            e = SLib.GetImg('e_switch_block.png', True)
            ImageCache['ESwitchBlock'] = QtGui.QPixmap.fromImage(e)
            ImageCache['ESwitchBlockU'] = QtGui.QPixmap.fromImage(e.mirrored(True, True))

    def dataChanged(self):
        upsideDown = self.parent.spritedata[5] & 1

        if upsideDown:
            self.image = ImageCache['ESwitchBlockU']
        else:
            self.image = ImageCache['ESwitchBlock']

        super().dataChanged()


class SpriteImage_KoopaTroopa(SLib.SpriteImage_StaticMultiple):  # 57
    @staticmethod
    def loadImages():
        if 'KoopaG' in ImageCache: return
        ImageCache['KoopaG'] = SLib.GetImg('koopa_green.png')
        ImageCache['KoopaR'] = SLib.GetImg('koopa_red.png')
        ImageCache['KoopaShellG'] = SLib.GetImg('koopa_green_shell.png')
        ImageCache['KoopaShellR'] = SLib.GetImg('koopa_red_shell.png')

    def dataChanged(self):
        # get properties
        props = self.parent.spritedata[5]
        shell = (props >> 4) & 1
        red = props & 1

        if not shell:
            self.offset = (-7, -15)
            self.image = ImageCache['KoopaG'] if not red else ImageCache['KoopaR']
        else:
            del self.offset
            self.image = ImageCache['KoopaShellG'] if not red else ImageCache['KoopaShellR']

        super().dataChanged()


class SpriteImage_KoopaParatroopa(SLib.SpriteImage_StaticMultiple):  # 58
    def __init__(self, parent):
        super().__init__(parent, 1.5, None, (-7, -12))
        self.aux.append(SLib.AuxiliaryTrackObject(parent, 0, 0, 0))

    @staticmethod
    def loadImages():
        if 'ParakoopaG' not in ImageCache:
            ImageCache['ParakoopaG'] = SLib.GetImg('parakoopa_green.png')
            ImageCache['ParakoopaR'] = SLib.GetImg('parakoopa_red.png')
        if 'KoopaShellG' not in ImageCache:
            ImageCache['KoopaShellG'] = SLib.GetImg('koopa_green_shell.png')
            ImageCache['KoopaShellR'] = SLib.GetImg('koopa_red_shell.png')

    def dataChanged(self):

        # get properties
        color = self.parent.spritedata[5] & 1
        mode = (self.parent.spritedata[5] >> 4) & 3

        # 0: jumping
        # 3: shell
        if color == 0:
            if mode == 3:
                del self.offset
                self.image = ImageCache['KoopaShellG']
            else:
                self.offset = (-7, -12)
                self.image = ImageCache['ParakoopaG']
        else:
            if mode == 3:
                del self.offset
                self.image = ImageCache['KoopaShellR']
            else:
                self.offset = (-7, -12)
                self.image = ImageCache['ParakoopaR']

        if mode == 1 or mode == 2:

            track = self.aux[0]
            turnImmediately = self.parent.spritedata[4] & 1 == 1

            if mode == 1:
                track.direction = SLib.AuxiliaryTrackObject.Horizontal
                track.setSize(9 * 16, 16)
                if turnImmediately:
                    track.setPos(self.width / 2, self.height / 2)
                else:
                    track.setPos(-4 * 24 + self.width / 2, self.height / 2)
            else:
                track.direction = SLib.AuxiliaryTrackObject.Vertical
                track.setSize(16, 9 * 16)
                if turnImmediately:
                    track.setPos(self.width / 2, self.height / 2)
                else:
                    track.setPos(self.width / 2, -4 * 24 + self.height / 2)

        else:
            # hide the track
            self.aux[0].setSize(0, 0)

        super().dataChanged()


class SpriteImage_SpikeTop(SLib.SpriteImage_StaticMultiple):  # 60
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['SpikeTop00'],
            (0, -4),
        )

    @staticmethod
    def loadImages():
        if 'SpikeTop00' in ImageCache: return
        SpikeTop = SLib.GetImg('spiketop.png', True)

        Transform = QtGui.QTransform()
        ImageCache['SpikeTop00'] = QtGui.QPixmap.fromImage(SpikeTop.mirrored(True, False))
        Transform.rotate(90)
        ImageCache['SpikeTop10'] = ImageCache['SpikeTop00'].transformed(Transform)
        Transform.rotate(90)
        ImageCache['SpikeTop20'] = ImageCache['SpikeTop00'].transformed(Transform)
        Transform.rotate(90)
        ImageCache['SpikeTop30'] = ImageCache['SpikeTop00'].transformed(Transform)

        Transform = QtGui.QTransform()
        ImageCache['SpikeTop01'] = QtGui.QPixmap.fromImage(SpikeTop)
        Transform.rotate(90)
        ImageCache['SpikeTop11'] = ImageCache['SpikeTop01'].transformed(Transform)
        Transform.rotate(90)
        ImageCache['SpikeTop21'] = ImageCache['SpikeTop01'].transformed(Transform)
        Transform.rotate(90)
        ImageCache['SpikeTop31'] = ImageCache['SpikeTop01'].transformed(Transform)

    def dataChanged(self):
        orientation = (self.parent.spritedata[5] >> 4) & 3
        direction = self.parent.spritedata[5] & 1

        self.image = ImageCache['SpikeTop%d%d' % (orientation, direction)]

        self.offset = (
            (0, -4),
            (0, 0),
            (0, 0),
            (-4, 0),
        )[orientation]

        super().dataChanged()


class SpriteImage_GroundPiranha(SLib.SpriteImage_StaticMultiple):  # 73
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.xOffset = -20

    @staticmethod
    def loadImages():
        if 'GroundPiranha' in ImageCache: return
        GP = SLib.GetImg('ground_piranha.png', True)
        ImageCache['GroundPiranha'] = QtGui.QPixmap.fromImage(GP)
        ImageCache['GroundPiranhaU'] = QtGui.QPixmap.fromImage(GP.mirrored(False, True))

    def dataChanged(self):

        upsideDown = self.parent.spritedata[5] & 1
        if not upsideDown:
            self.yOffset = 6
            self.image = ImageCache['GroundPiranha']
        else:
            self.yOffset = 0
            self.image = ImageCache['GroundPiranhaU']

        super().dataChanged()


class SpriteImage_BigGroundPiranha(SLib.SpriteImage_StaticMultiple):  # 74
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.xOffset = -65

    @staticmethod
    def loadImages():
        if 'BigGroundPiranha' in ImageCache: return
        BGP = SLib.GetImg('big_ground_piranha.png', True)
        ImageCache['BigGroundPiranha'] = QtGui.QPixmap.fromImage(BGP)
        ImageCache['BigGroundPiranhaU'] = QtGui.QPixmap.fromImage(BGP.mirrored(False, True))

    def dataChanged(self):

        upsideDown = self.parent.spritedata[5] & 1
        if not upsideDown:
            self.yOffset = -32
            self.image = ImageCache['BigGroundPiranha']
        else:
            self.yOffset = 0
            self.image = ImageCache['BigGroundPiranhaU']

        super().dataChanged()


class SpriteImage_GroundFiretrap(SLib.SpriteImage_StaticMultiple):  # 75
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.xOffset = 5

    @staticmethod
    def loadImages():
        if 'GroundFiretrap' in ImageCache: return
        GF = SLib.GetImg('ground_firetrap.png', True)
        ImageCache['GroundFiretrap'] = QtGui.QPixmap.fromImage(GF)
        ImageCache['GroundFiretrapU'] = QtGui.QPixmap.fromImage(GF.mirrored(False, True))

    def dataChanged(self):

        upsideDown = self.parent.spritedata[5] & 1
        if not upsideDown:
            self.yOffset = -10
            self.image = ImageCache['GroundFiretrap']
        else:
            self.yOffset = 0
            self.image = ImageCache['GroundFiretrapU']

        super().dataChanged()


class SpriteImage_BigGroundFiretrap(SLib.SpriteImage_StaticMultiple):  # 76
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.xOffset = -14

    @staticmethod
    def loadImages():
        if 'BigGroundFiretrap' in ImageCache: return
        BGF = SLib.GetImg('big_ground_firetrap.png', True)
        ImageCache['BigGroundFiretrap'] = QtGui.QPixmap.fromImage(BGF)
        ImageCache['BigGroundFiretrapU'] = QtGui.QPixmap.fromImage(BGF.mirrored(False, True))

    def dataChanged(self):

        upsideDown = self.parent.spritedata[5] & 1
        if not upsideDown:
            self.yOffset = -68
            self.image = ImageCache['BigGroundFiretrap']
        else:
            self.yOffset = 0
            self.image = ImageCache['BigGroundFiretrapU']

        super().dataChanged()


class SpriteImage_CloudTrampoline(SLib.SpriteImage_StaticMultiple):  # 78
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['CloudTrSmall'],
            (-2, -2),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('CloudTrBig', 'cloud_trampoline_big.png')
        SLib.loadIfNotInImageCache('CloudTrSmall', 'cloud_trampoline_small.png')

    def dataChanged(self):

        size = (self.parent.spritedata[4] >> 4) & 1
        if size == 0:
            self.image = ImageCache['CloudTrSmall']
        else:
            self.image = ImageCache['CloudTrBig']

        super().dataChanged()


class SpriteImage_TrampolineWall(SLib.SpriteImage_StaticMultiple):  # 87
    def __init__(self, parent):
        super().__init__(parent, 1.5)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('UnusedPlatformDark', 'unused_platform_dark.png')

    def dataChanged(self):
        height = (self.parent.spritedata[5] & 15) + 1

        self.image = ImageCache['UnusedPlatformDark'].scaled(
            24, height * 24,
            Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        self.height = height * 16

        super().dataChanged()


class SpriteImage_ChainBall(SLib.SpriteImage_StaticMultiple):  # 109
    def __init__(self, parent):
        super().__init__(parent, 1.5)

    @staticmethod
    def loadImages():
        if 'ChainBallU' in ImageCache: return
        ImageCache['ChainBallU'] = SLib.GetImg('chainball_up.png')
        ImageCache['ChainBallR'] = SLib.GetImg('chainball_right.png')
        ImageCache['ChainBallD'] = SLib.GetImg('chainball_down.png')
        ImageCache['ChainBallL'] = SLib.GetImg('chainball_left.png')

    def dataChanged(self):
        direction = self.parent.spritedata[5] & 3
        if direction > 3: direction = 0

        if direction & 1 == 0:  # horizontal
            self.size = (96, 38)
        else:  # vertical
            self.size = (37, 96)

        if direction == 0:  # right
            self.image = ImageCache['ChainBallR']
            self.offset = (3, -8.5)
        elif direction == 1:  # up
            self.image = ImageCache['ChainBallU']
            self.offset = (-8.5, -81.5)
        elif direction == 2:  # left
            self.image = ImageCache['ChainBallL']
            self.offset = (-83, -11)
        elif direction == 3:  # down
            self.image = ImageCache['ChainBallD']
            self.offset = (-11, 3.5)

        super().dataChanged()


class SpriteImage_FlameCannon(SLib.SpriteImage_StaticMultiple):  # 114
    def __init__(self, parent):
        super().__init__(parent, 1.5)

        self.height = 64

    @staticmethod
    def loadImages():
        if 'FlameCannonR' in ImageCache: return
        transform90 = QtGui.QTransform()
        transform270 = QtGui.QTransform()
        transform90.rotate(90)
        transform270.rotate(270)

        image = SLib.GetImg('continuous_flame_cannon.png', True)
        ImageCache['FlameCannonR'] = QtGui.QPixmap.fromImage(image)
        ImageCache['FlameCannonD'] = QtGui.QPixmap.fromImage(image.transformed(transform90))
        ImageCache['FlameCannonL'] = QtGui.QPixmap.fromImage(image.mirrored(True, False))
        ImageCache['FlameCannonU'] = QtGui.QPixmap.fromImage(image.transformed(transform270).mirrored(True, False))

    def dataChanged(self):
        direction = self.parent.spritedata[5] & 15
        if direction > 3: direction = 0

        if direction == 0:  # right
            del self.offset
        elif direction == 1:  # left
            self.offset = (-48, 0)
        elif direction == 2:  # up
            self.offset = (0, -48)
        elif direction == 3:  # down
            del self.offset

        directionstr = 'RLUD'[direction]
        self.image = ImageCache['FlameCannon%s' % directionstr]

        super().dataChanged()


class SpriteImage_PulseFlameCannon(SLib.SpriteImage_StaticMultiple):  # 117
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.height = 112

    @staticmethod
    def loadImages():
        if 'PulseFlameCannonR' in ImageCache: return
        transform90 = QtGui.QTransform()
        transform270 = QtGui.QTransform()
        transform90.rotate(90)
        transform270.rotate(270)

        onImage = SLib.GetImg('synchro_flame_jet.png', True)
        ImageCache['PulseFlameCannonR'] = QtGui.QPixmap.fromImage(onImage)
        ImageCache['PulseFlameCannonD'] = QtGui.QPixmap.fromImage(onImage.transformed(transform90))
        ImageCache['PulseFlameCannonL'] = QtGui.QPixmap.fromImage(onImage.mirrored(True, False))
        ImageCache['PulseFlameCannonU'] = QtGui.QPixmap.fromImage(
            onImage.transformed(transform270).mirrored(True, False))

    def dataChanged(self):

        direction = self.parent.spritedata[5] & 15
        if direction > 3: direction = 0

        if direction == 0:
            del self.offset
        elif direction == 1:
            self.offset = (-96, 0)
        elif direction == 2:
            self.offset = (0, -96)
        elif direction == 3:
            del self.offset

        directionstr = 'RLUD'[direction]
        self.image = ImageCache['PulseFlameCannon%s' % directionstr]

        super().dataChanged()


class SpriteImage_UnusedCastlePlatform(SLib.SpriteImage_StaticMultiple):  # 123
    def __init__(self, parent):
        super().__init__(parent, 1.5)

        self.image = ImageCache['UnusedCastlePlatform']
        self.size = (255, 255)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('UnusedCastlePlatform', 'unused_castle_platform.png')

    def dataChanged(self):
        rawSize = self.parent.spritedata[4] >> 4

        if rawSize != 0:
            widthInBlocks = rawSize * 4
        else:
            widthInBlocks = 8

        topRadiusInBlocks = widthInBlocks / 10
        heightInBlocks = widthInBlocks + topRadiusInBlocks

        self.image = ImageCache['UnusedCastlePlatform'].scaled(widthInBlocks * 24, int(heightInBlocks * 24))

        self.offset = (
            -(self.image.width() / 1.5) / 2,
            -topRadiusInBlocks * 16,
        )

        super().dataChanged()


class SpriteImage_FenceKoopaHorz(SLib.SpriteImage_StaticMultiple):  # 125
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.offset = (-3, -12)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('FenceKoopaHG', 'fencekoopa_horz.png')
        SLib.loadIfNotInImageCache('FenceKoopaHR', 'fencekoopa_horz_red.png')

    def dataChanged(self):

        color = self.parent.spritedata[5] & 1
        if color == 1:
            self.image = ImageCache['FenceKoopaHR']
        else:
            self.image = ImageCache['FenceKoopaHG']

        super().dataChanged()


class SpriteImage_FenceKoopaVert(SLib.SpriteImage_StaticMultiple):  # 126
    def __init__(self, parent):
        super().__init__(parent, 1.5)

        self.offset = (-2, -12)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('FenceKoopaVG', 'fencekoopa_vert.png')
        SLib.loadIfNotInImageCache('FenceKoopaVR', 'fencekoopa_vert_red.png')

    def dataChanged(self):

        color = self.parent.spritedata[5] & 1
        if color == 1:
            self.image = ImageCache['FenceKoopaVR']
        else:
            self.image = ImageCache['FenceKoopaVG']

        super().dataChanged()


class SpriteImage_Arrow(SLib.SpriteImage_StaticMultiple):  # 143
    def __init__(self, parent):
        super().__init__(parent, 1.5)

    @staticmethod
    def loadImages():
        if 'Arrow0' in ImageCache: return
        for i in range(8):
            ImageCache['Arrow%d' % i] = SLib.GetImg('arrow_%d.png' % i)

    def dataChanged(self):
        ArrowOffsets = [(3, 0), (5, 4), (1, 3), (5, -1), (3, 0), (-1, -1), (0, 3), (-1, 4)]

        direction = self.parent.spritedata[5] & 7
        self.image = ImageCache['Arrow%d' % direction]

        self.width = self.image.width() / 1.5
        self.height = self.image.height() / 1.5
        self.offset = ArrowOffsets[direction]

        super().dataChanged()


class SpriteImage_Coin(SLib.SpriteImage_StaticMultiple):  # 147
    @staticmethod
    def loadImages():
        if 'CoinF' in ImageCache: return

        pix = QtGui.QPixmap(24, 24)
        pix.fill(Qt.GlobalColor.transparent)
        paint = QtGui.QPainter(pix)
        paint.setOpacity(0.9)
        paint.drawPixmap(0, 0, SLib.GetImg('iceblock00.png'))
        paint.setOpacity(0.6)
        paint.drawPixmap(0, 0, ImageCache['Coin'])
        del paint
        ImageCache['CoinF'] = pix

        ImageCache['CoinBubble'] = SLib.GetImg('coin_bubble.png')

    def dataChanged(self):
        type = self.parent.spritedata[5] & 0xF

        if type == 0:
            self.image = ImageCache['Coin']
            self.offset = (0, 0)
        elif type == 0xF:
            self.image = ImageCache['CoinF']
            self.offset = (0, 0)
        elif type in (1, 2, 4):
            self.image = ImageCache['CoinBubble']
            self.offset = (-4, -4)
        else:
            self.image = ImageCache['SpecialCoin']
            self.offset = (0, 0)

        super().dataChanged()


class SpriteImage_BigBrick(SLib.SpriteImage_StaticMultiple):  # 157
    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('BigBrick', 'big_brick.png')
        SLib.loadIfNotInImageCache('ShipKey', 'ship_key.png')
        SLib.loadIfNotInImageCache('5Coin', '5_coin.png')

        if 'YoshiFire' not in ImageCache:
            pix = QtGui.QPixmap(48, 24)
            pix.fill(Qt.GlobalColor.transparent)
            paint = QtGui.QPainter(pix)
            paint.drawPixmap(0, 0, ImageCache['BlockContents'][9])
            paint.drawPixmap(24, 0, ImageCache['BlockContents'][3])
            del paint
            ImageCache['YoshiFire'] = pix

        for power in range(16):
            if power in (0, 8, 12, 13):
                ImageCache['BigBrick%d' % power] = ImageCache['BigBrick']
                continue

            x = y = 24
            overlay = ImageCache['BlockContents'][power]
            if power == 9:
                overlay = ImageCache['YoshiFire']
                x = 12
            elif power == 10:
                overlay = ImageCache['5Coin']
            elif power == 14:
                overlay = ImageCache['ShipKey']
                x, y = 22, 18

            new = QtGui.QPixmap(ImageCache['BigBrick'])
            paint = QtGui.QPainter(new)
            paint.drawPixmap(x, y, overlay)
            del paint
            ImageCache['BigBrick%d' % power] = new

    def dataChanged(self):

        power = self.parent.spritedata[5] & 0xF
        self.image = ImageCache['BigBrick%d' % power]
        super().dataChanged()


class SpriteImage_FireSnake(SLib.SpriteImage_StaticMultiple):  # 158
    def __init__(self, parent):
        super().__init__(parent, 1.5)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('FireSnakeWait', 'fire_snake_0.png')
        SLib.loadIfNotInImageCache('FireSnake', 'fire_snake_1.png')

    def dataChanged(self):

        move = self.parent.spritedata[5] & 15
        if move == 1:
            del self.size
            self.yOffset = 0
            self.image = ImageCache['FireSnakeWait']
        else:
            self.size = (20, 32)
            self.yOffset = -16
            self.image = ImageCache['FireSnake']

        super().dataChanged()


class SpriteImage_PipeBubbles(SLib.SpriteImage_StaticMultiple):  # 161
    @staticmethod
    def loadImages():
        if 'PipeBubblesU' in ImageCache: return
        transform90 = QtGui.QTransform()
        transform180 = QtGui.QTransform()
        transform270 = QtGui.QTransform()
        transform90.rotate(90)
        transform180.rotate(180)
        transform270.rotate(270)

        image = SLib.GetImg('pipe_bubbles.png', True)
        ImageCache['PipeBubbles' + 'U'] = QtGui.QPixmap.fromImage(image)
        ImageCache['PipeBubbles' + 'R'] = QtGui.QPixmap.fromImage(image.transformed(transform90))
        ImageCache['PipeBubbles' + 'D'] = QtGui.QPixmap.fromImage(image.transformed(transform180))
        ImageCache['PipeBubbles' + 'L'] = QtGui.QPixmap.fromImage(image.transformed(transform270))

    def dataChanged(self):

        direction = self.parent.spritedata[5] & 15
        if direction == 0 or direction > 3:
            self.dimensions = (0, -52, 32, 53)
            direction = 'U'
        elif direction == 1:
            self.dimensions = (0, 16, 32, 53)
            direction = 'D'
        elif direction == 2:
            self.dimensions = (16, -16, 53, 32)
            direction = 'R'
        elif direction == 3:
            self.dimensions = (-52, -16, 53, 32)
            direction = 'L'

        self.image = ImageCache['PipeBubbles%s' % direction]

        super().dataChanged()


class SpriteImage_OneWayGate(SLib.SpriteImage_StaticMultiple):  # 174
    @staticmethod
    def loadImages():
        if '1WayGate00' in ImageCache: return

        # This loop generates all 1-way gate images from a single image
        gate = SLib.GetImg('1_way_gate.png', True)
        for flip in (0, 1):
            for direction in range(4):
                if flip:
                    newgate = QtGui.QPixmap.fromImage(gate.mirrored(True, False))
                else:
                    newgate = QtGui.QPixmap.fromImage(gate)

                width = 24
                height = 60  # constants, from the PNG
                xsize = width if direction in (0, 1) else height
                ysize = width if direction in (2, 3) else height
                if direction == 0:
                    rotValue = 0
                    xpos = 0
                    ypos = 0
                elif direction == 1:
                    rotValue = 180
                    xpos = -width
                    ypos = -height
                elif direction == 2:
                    rotValue = 270
                    xpos = -width
                    ypos = 0
                elif direction == 3:
                    rotValue = 90
                    xpos = 0
                    ypos = -height

                dest = QtGui.QPixmap(xsize, ysize)
                dest.fill(Qt.GlobalColor.transparent)
                p = QtGui.QPainter(dest)
                p.rotate(rotValue)
                p.drawPixmap(xpos, ypos, newgate)
                del p

                ImageCache['1WayGate%d%d' % (flip, direction)] = dest

    def dataChanged(self):

        flag = (self.parent.spritedata[5] >> 4) & 1
        direction = self.parent.spritedata[5] & 3
        self.image = ImageCache['1WayGate%d%d' % (flag, direction)]

        if direction > 3: direction = 3
        self.offset = (
            (0, -24),
            (0, 0),
            (-24, 0),
            (0, 0),
        )[direction]

        super().dataChanged()


class SpriteImage_HuckitCrab(SLib.SpriteImage_StaticMultiple):  # 195
    @staticmethod
    def loadImages():
        if 'HuckitCrabR' in ImageCache: return
        Huckitcrab = SLib.GetImg('huckit_crab.png', True)
        ImageCache['HuckitCrabL'] = QtGui.QPixmap.fromImage(Huckitcrab)
        ImageCache['HuckitCrabR'] = QtGui.QPixmap.fromImage(Huckitcrab.mirrored(True, False))

    def dataChanged(self):
        info = self.parent.spritedata[5]

        if info == 1:
            self.image = ImageCache['HuckitCrabR']
            self.xOffset = 0
        else:
            if info == 13:
                self.image = ImageCache['HuckitCrabR']
                self.xOffset = 0
            else:
                self.image = ImageCache['HuckitCrabL']
                self.xOffset = -16

        super().dataChanged()


class SpriteImage_Fishbones(SLib.SpriteImage_StaticMultiple):  # 196
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['FishbonesL'],
            (0, -2)
        )
        self.aux.append(SLib.AuxiliaryTrackObject(
            parent, 16, 16, SLib.AuxiliaryTrackObject.Horizontal
        ))

    def dataChanged(self):

        direction = self.parent.spritedata[5] >> 4
        distance = self.parent.spritedata[5] & 0xF

        # distance values > 1 result in a distance of 9
        if distance == 0:
            distance = 5
        elif distance == 1:
            distance = 7
        else:
            distance = 9

        self.aux[0].setSize(distance * 16, 16)
        self.aux[0].setPos(distance * -12 + 12, 2)

        if direction == 1:
            self.image = ImageCache['FishbonesR']
        else:
            self.image = ImageCache['FishbonesL']

        super().dataChanged()

    @staticmethod
    def loadImages():
        if 'FishbonesL' in ImageCache: return
        Fishbones = SLib.GetImg('fishbones.png', True)
        ImageCache['FishbonesL'] = QtGui.QPixmap.fromImage(Fishbones)
        ImageCache['FishbonesR'] = QtGui.QPixmap.fromImage(Fishbones.mirrored(True, False))


class SpriteImage_Clam(SLib.SpriteImage_StaticMultiple):  # 197
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.offset = (-29, -54)

    @staticmethod
    def loadImages():
        if 'ClamEmpty' in ImageCache: return

        if 'PSwitch' not in ImageCache:
            p = SLib.GetImg('p_switch.png', True)
            ImageCache['PSwitch'] = QtGui.QPixmap.fromImage(p)
            ImageCache['PSwitchU'] = QtGui.QPixmap.fromImage(p.mirrored(True, True))

        SLib.loadIfNotInImageCache('ClamEmpty', 'clam.png')

        overlays = (
            (26, 22, 'Star', ImageCache['StarCoin']),
            (40, 42, '1Up', ImageCache['BlockContents'][11]),
            (42, 42, 'PSwitch', ImageCache['PSwitch']),
            (42, 42, 'PSwitchU', ImageCache['PSwitchU']),
        )
        for x, y, clamName, overlayImage in overlays:
            newPix = QtGui.QPixmap(ImageCache['ClamEmpty'])
            painter = QtGui.QPainter(newPix)
            painter.setOpacity(0.6)
            painter.drawPixmap(x, y, overlayImage)
            del painter
            ImageCache['Clam' + clamName] = newPix

        # 2 coins special case
        newPix = QtGui.QPixmap(ImageCache['ClamEmpty'])
        painter = QtGui.QPainter(newPix)
        painter.setOpacity(0.6)
        painter.drawPixmap(28, 42, ImageCache['Coin'])
        painter.drawPixmap(52, 42, ImageCache['Coin'])
        del painter
        ImageCache['Clam2Coin'] = newPix

    def dataChanged(self):

        holds = self.parent.spritedata[5] & 0xF
        switchdir = self.parent.spritedata[4] & 0xF

        holdsStr = 'Empty'
        if holds == 1:
            holdsStr = 'Star'
        elif holds == 2:
            holdsStr = '2Coin'
        elif holds == 3:
            holdsStr = '1Up'
        elif holds == 4:
            if switchdir == 1:
                holdsStr = 'PSwitchU'
            else:
                holdsStr = 'PSwitch'

        self.image = ImageCache['Clam' + holdsStr]

        super().dataChanged()


class SpriteImage_Icicle(SLib.SpriteImage_StaticMultiple):  # 201
    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('IcicleSmallS', 'icicle_small_static.png')
        SLib.loadIfNotInImageCache('IcicleLargeS', 'icicle_large_static.png')

    def dataChanged(self):

        size = self.parent.spritedata[5] & 1
        if size == 0:
            self.image = ImageCache['IcicleSmallS']
        else:
            self.image = ImageCache['IcicleLargeS']

        super().dataChanged()


class SpriteImage_SpringBlock(SLib.SpriteImage_StaticMultiple):  # 223
    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('SpringBlock1', 'spring_block.png')
        SLib.loadIfNotInImageCache('SpringBlock2', 'spring_block_alt.png')

    def dataChanged(self):
        type = self.parent.spritedata[5] & 1
        self.image = ImageCache['SpringBlock2'] if type else ImageCache['SpringBlock1']

        super().dataChanged()


class SpriteImage_JumboRay(SLib.SpriteImage_StaticMultiple):  # 224
    @staticmethod
    def loadImages():
        if 'JumboRayL' in ImageCache: return
        Ray = SLib.GetImg('jumbo_ray.png', True)
        ImageCache['JumboRayL'] = QtGui.QPixmap.fromImage(Ray)
        ImageCache['JumboRayR'] = QtGui.QPixmap.fromImage(Ray.mirrored(True, False))

    def dataChanged(self):

        flyleft = self.parent.spritedata[4] & 15
        if flyleft:
            self.xOffset = 0
            self.image = ImageCache['JumboRayL']
        else:
            self.xOffset = -152
            self.image = ImageCache['JumboRayR']

        super().dataChanged()


class SpriteImage_MoveWhenOnMetalLavaBlock(SLib.SpriteImage_StaticMultiple):  # 257
    @staticmethod
    def loadImages():
        if 'MetalLavaBlock0' in ImageCache: return
        ImageCache['MetalLavaBlock0'] = SLib.GetImg('lava_iron_block_0.png')
        ImageCache['MetalLavaBlock1'] = SLib.GetImg('lava_iron_block_1.png')
        ImageCache['MetalLavaBlock2'] = SLib.GetImg('lava_iron_block_2.png')

    def dataChanged(self):
        size = (self.parent.spritedata[5] & 0xF) % 3
        self.image = ImageCache['MetalLavaBlock%d' % size]

        super().dataChanged()


class SpriteImage_FallingIcicle(SLib.SpriteImage_StaticMultiple):  # 265
    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('IcicleSmall', 'icicle_small.png')
        SLib.loadIfNotInImageCache('IcicleLarge', 'icicle_large.png')

    def dataChanged(self):
        super().dataChanged()

        size = self.parent.spritedata[5] & 1
        if size == 0:
            self.image = ImageCache['IcicleSmall']
            self.height = 19
        else:
            self.image = ImageCache['IcicleLarge']
            self.height = 36


class SpriteImage_TiltGrate(SLib.SpriteImage_StaticMultiple):  # 267
    @staticmethod
    def loadImages():
        if 'TiltGrateU' in ImageCache: return
        ImageCache['TiltGrateU'] = SLib.GetImg('tilt_grate_up.png')
        ImageCache['TiltGrateD'] = SLib.GetImg('tilt_grate_down.png')
        ImageCache['TiltGrateL'] = SLib.GetImg('tilt_grate_left.png')
        ImageCache['TiltGrateR'] = SLib.GetImg('tilt_grate_right.png')

    def dataChanged(self):
        direction = self.parent.spritedata[5] & 3
        if direction > 3: direction = 3

        if direction < 2:
            self.size = (69, 166)
        else:
            self.size = (166, 69)

        if direction == 0:
            self.offset = (-36, -115)
            self.image = ImageCache['TiltGrateU']
        elif direction == 1:
            self.offset = (-36, 12)
            self.image = ImageCache['TiltGrateD']
        elif direction == 2:
            self.offset = (-144, 0)
            self.image = ImageCache['TiltGrateL']
        elif direction == 3:
            self.offset = (-20, 0)
            self.image = ImageCache['TiltGrateR']

        super().dataChanged()


class SpriteImage_LavaGeyser(SLib.SpriteImage_StaticMultiple):  # 268
    def __init__(self, parent):
        super().__init__(parent, 1.5)

        self.parent.setZValue(24999)
        self.dimensions = (-37, -186, 69, 200)

    @staticmethod
    def loadImages():
        if 'LavaGeyser0' in ImageCache: return
        for i in range(7):
            ImageCache['LavaGeyser%d' % i] = SLib.GetImg('lava_geyser_%d.png' % i)

    def dataChanged(self):

        height = self.parent.spritedata[4] >> 4
        startsOn = self.parent.spritedata[5] & 1

        if height > 6: height = 0
        self.offset = (
            (-30, -170),
            (-28, -155),
            (-30, -155),
            (-43, -138),
            (-32, -105),
            (-26, -89),
            (-32, -34),
        )[height]

        self.alpha = 0.75 if startsOn else 0.5

        self.image = ImageCache['LavaGeyser%d' % height]

        super().dataChanged()


class SpriteImage_GiantIceBlock(SLib.SpriteImage_StaticMultiple):  # 280
    @staticmethod
    def loadImages():
        if 'BigIceBlockEmpty' in ImageCache: return
        ImageCache['BigIceBlockEmpty'] = SLib.GetImg('big_ice_block_empty.png')
        ImageCache['BigIceBlockBobomb'] = SLib.GetImg('big_ice_block_bobomb.png')
        ImageCache['BigIceBlockSpikeBall'] = SLib.GetImg('big_ice_block_spikeball.png')

    def dataChanged(self):

        item = self.parent.spritedata[5] & 3
        if item > 2: item = 0

        if item == 0:
            self.image = ImageCache['BigIceBlockEmpty']
        elif item == 1:
            self.image = ImageCache['BigIceBlockBobomb']
        elif item == 2:
            self.image = ImageCache['BigIceBlockSpikeBall']

        super().dataChanged()


class SpriteImage_WoodCircle(SLib.SpriteImage_StaticMultiple):  # 286
    @staticmethod
    def loadImages():
        if 'WoodCircle0' in ImageCache: return
        ImageCache['WoodCircle0'] = SLib.GetImg('wood_circle_0.png')
        ImageCache['WoodCircle1'] = SLib.GetImg('wood_circle_1.png')
        ImageCache['WoodCircle2'] = SLib.GetImg('wood_circle_2.png')

    def dataChanged(self):
        super().dataChanged()
        size = (self.parent.spritedata[5] & 0xF) % 3

        self.image = ImageCache['WoodCircle%d' % size]

        if size > 2: size = 0
        self.dimensions = (
            (-24, -24, 64, 64),
            (-40, -40, 96, 96),
            (-56, -56, 128, 128),
        )[size]


class SpriteImage_PathIceBlock(SLib.SpriteImage_StaticMultiple):  # 287
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = False
        self.alpha = 0.8

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('PathIceBlock', 'unused_path_ice_block.png')

    def dataChanged(self):
        width = (self.parent.spritedata[5] & 0xF) + 1
        height = (self.parent.spritedata[5] >> 4) + 1

        self.image = ImageCache['PathIceBlock'].scaled(width * 24, height * 24)

        super().dataChanged()


class SpriteImage_Box(SLib.SpriteImage_StaticMultiple):  # 289
    @staticmethod
    def loadImages():
        if 'Box00' in ImageCache: return
        for style, stylestr in ((0, 'wood'), (1, 'metal')):
            for size, sizestr in zip(range(4), ('small', 'wide', 'tall', 'big')):
                ImageCache['Box%d%d' % (style, size)] = SLib.GetImg('box_%s_%s.png' % (stylestr, sizestr))

    def dataChanged(self):

        style = self.parent.spritedata[4] & 1
        size = (self.parent.spritedata[5] >> 4) & 3

        self.image = ImageCache['Box%d%d' % (style, size)]

        super().dataChanged()


class SpriteImage_Parabeetle(SLib.SpriteImage_StaticMultiple):  # 291
    @staticmethod
    def loadImages():
        if 'Parabeetle0' in ImageCache: return
        ImageCache['Parabeetle0'] = SLib.GetImg('parabeetle_right.png')
        ImageCache['Parabeetle1'] = SLib.GetImg('parabeetle_left.png')
        ImageCache['Parabeetle2'] = SLib.GetImg('parabeetle_moreright.png')
        ImageCache['Parabeetle3'] = SLib.GetImg('parabeetle_atyou.png')

    def dataChanged(self):

        direction = self.parent.spritedata[5] & 3
        self.image = ImageCache['Parabeetle%d' % direction]
        self.yOffset = -6

        if direction == 0 or direction > 3:  # right
            self.xOffset = -12
        elif direction == 1:  # left
            self.xOffset = -10
        elif direction == 2:  # more right
            self.xOffset = -12
        elif direction == 3:  # at you
            self.xOffset = -26

        super().dataChanged()


class SpriteImage_HeavyParabeetle(SLib.SpriteImage_StaticMultiple):  # 292
    @staticmethod
    def loadImages():
        if 'HeavyParabeetle0' in ImageCache: return
        ImageCache['HeavyParabeetle0'] = SLib.GetImg('heavy_parabeetle_right.png')
        ImageCache['HeavyParabeetle1'] = SLib.GetImg('heavy_parabeetle_left.png')
        ImageCache['HeavyParabeetle2'] = SLib.GetImg('heavy_parabeetle_moreright.png')
        ImageCache['HeavyParabeetle3'] = SLib.GetImg('heavy_parabeetle_atyou.png')

    def dataChanged(self):

        direction = self.parent.spritedata[5] & 3
        self.image = ImageCache['HeavyParabeetle%d' % direction]
        self.yOffset = -60

        if direction == 0 or direction > 3:  # right
            self.xOffset = -38
        elif direction == 1:  # left
            self.xOffset = -38
        elif direction == 2:  # more right
            self.xOffset = -38
        elif direction == 3:  # at you
            self.xOffset = -52

        super().dataChanged()


class SpriteImage_NutPlatform(SLib.SpriteImage_StaticMultiple):  # 295
    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('NutPlatform', 'nut_platform.png')

    def dataChanged(self):
        offsetUp = self.parent.spritedata[5] >> 4
        offsetRight = self.parent.spritedata[5] & 7

        if offsetUp == 0:
            self.yOffset = -8
        else:
            self.yOffset = 0

        self.xOffset = (
            -16,
            -8,
            0,
            8,
            16,
            24,
            32,
            40,
        )[offsetRight]

        self.image = ImageCache['NutPlatform']

        super().dataChanged()


class SpriteImage_MegaBuzzy(SLib.SpriteImage_StaticMultiple):  # 296
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.offset = (-43, -74)

    @staticmethod
    def loadImages():
        if 'MegaBuzzyR' in ImageCache: return
        ImageCache['MegaBuzzyR'] = SLib.GetImg('megabuzzy_right.png')
        ImageCache['MegaBuzzyL'] = SLib.GetImg('megabuzzy_left.png')
        SLib.loadIfNotInImageCache('MegaBuzzyF', 'megabuzzy_front.png')

    def dataChanged(self):

        direction = self.parent.spritedata[5] & 3
        if direction == 0 or direction > 2:
            self.image = ImageCache['MegaBuzzyR']
        elif direction == 1:
            self.image = ImageCache['MegaBuzzyL']
        elif direction == 2:
            self.image = ImageCache['MegaBuzzyF']

        super().dataChanged()


class SpriteImage_LongCannon(SLib.SpriteImage_StaticMultiple):  # 298
    def __init__(self, parent):
        super().__init__(parent, 1.5)

    @staticmethod
    def loadImages():
        # TODO: make LongCannonER and BLongCannonER
        if 'LongCannonFL' in ImageCache: return
        ImageCache['LongCannonFL'] = SLib.GetImg('cannon_front_left.png')
        ImageCache['LongCannonFR'] = SLib.GetImg('cannon_front_right.png')
        ImageCache['LongCannonM'] = SLib.GetImg('cannon_middle.png')
        ImageCache['LongCannonEL'] = SLib.GetImg('cannon_end_left.png')

        ImageCache['BLongCannonFL'] = SLib.GetImg('cannonbig_front_left.png')
        ImageCache['BLongCannonFR'] = SLib.GetImg('cannonbig_front_right.png')
        ImageCache['BLongCannonM'] = SLib.GetImg('cannonbig_middle.png')
        ImageCache['BLongCannonEL'] = SLib.GetImg('cannonbig_end_left.png')

        ImageCache['LongCannonFU'] = SLib.GetImg('cannon_front_up.png')
        ImageCache['BLongCannonFU'] = SLib.GetImg('cannonbig_front_up.png')

        ImageCache['LongCannonER'] = ImageCache['LongCannonEL']
        ImageCache['BLongCannonER'] = ImageCache['BLongCannonEL']
        #ImageCache['LongCannonER'] = SLib.GetImg('cannon_end_right.png')
        #ImageCache['BLongCannonER'] = SLib.GetImg('cannonbig_end_right.png')

    def dataChanged(self):
        super().dataChanged()

        raw_length = self.parent.spritedata[4] & 0xF
        self.dir = self.parent.spritedata[5] & 1
        self.big = self.parent.spritedata[5] & 0x10 != 0

        self.bugged = (self.parent.spritedata[5] & 2 == 2) and self.dir == 0

        if self.bugged:
            self.dir = 1

        if self.big:
            self.height = 32
            self.tilesize = 48
            self.width = 16 * (raw_length + 3)
            if self.dir == 0:
                self.numMiddle = raw_length - 2
                self.xOffset = 16 - self.width
            else:
                self.xOffset = 0
                self.numMiddle = raw_length - 1

            if self.bugged:
                self.xOffset = -8
                self.width += 8
        else:
            self.height = 16
            self.tilesize = 24
            self.numMiddle = raw_length
            self.width = 16 * (raw_length + 2)
            if self.dir == 0:
                self.xOffset = 12 - self.width
            else:
                self.xOffset = 4

            if self.bugged:
                self.xOffset = 0
                self.height += 8
                self.width -= 4

    def paint(self, painter):
        super().paint(painter)

        big_s = 'B' if self.big else ''

        middle = ImageCache[big_s + 'LongCannonM']
        solid = SLib.GetTile(1)
        if self.dir == 0: # right
            front = ImageCache[big_s + 'LongCannonFR']
            end = ImageCache[big_s + 'LongCannonEL']
        else:
            front = ImageCache[big_s + 'LongCannonFL']
            end = ImageCache[big_s + 'LongCannonER']

        # the front
        if self.bugged and self.big:
            front = ImageCache['BLongCannonFU']
            painter.drawPixmap(0, 0, front)
        elif self.bugged:
            front = ImageCache['LongCannonFU']
            painter.drawPixmap(0, 12, front)
        elif self.big and self.dir == 0:
            painter.drawPixmap(24 + 24 * self.numMiddle + self.tilesize, 0, front)
        elif self.dir == 0:
            painter.drawPixmap(24 * self.numMiddle + self.tilesize, 0, front)
        else:
            painter.drawPixmap(0, 0, front)

        # the middle
        if self.bugged and self.big:
            painter.drawTiledPixmap(self.tilesize, 0, self.numMiddle * 24 + 8, self.tilesize, middle)
        elif self.bugged:
            painter.drawTiledPixmap(self.tilesize, 12, self.numMiddle * 24 - 8, self.tilesize, middle)
        elif self.dir == 0 and self.big:
            painter.drawTiledPixmap(self.tilesize + 24, 0, self.numMiddle * 24, self.tilesize, middle)
        else:
            painter.drawTiledPixmap(self.tilesize, 0, self.numMiddle * 24, self.tilesize, middle)

        # the end
        if self.bugged and self.big:
            painter.drawPixmap(24 * self.numMiddle + self.tilesize + 8, 0, end)
        elif self.bugged:
            painter.drawPixmap(24 * self.numMiddle + self.tilesize - 8, 12, end)
        elif self.dir == 0 and self.big:
            painter.drawTiledPixmap(0, 0, 24, 48, solid)
            painter.drawPixmap(24, 0, end)
        elif self.dir == 0:
            painter.drawPixmap(0, 0, end)
        else:
            painter.drawPixmap(24 * self.numMiddle + self.tilesize, 0, end)


class SpriteImage_CannonMulti(SLib.SpriteImage_StaticMultiple):  # 299
    def __init__(self, parent):
        super().__init__(parent, 1.5)

    @staticmethod
    def loadImages():
        if 'CannonMultiU0' in ImageCache: return
        CannonUR = SLib.GetImg('cannon_multi_0.png', True)
        CannonUL = SLib.GetImg('cannon_multi_1.png', True)
        ImageCache['CannonMultiU0'] = QtGui.QPixmap.fromImage(CannonUR)
        ImageCache['CannonMultiU1'] = QtGui.QPixmap.fromImage(CannonUL)
        ImageCache['CannonMultiD0'] = QtGui.QPixmap.fromImage(CannonUR.mirrored(False, True))
        ImageCache['CannonMultiD1'] = QtGui.QPixmap.fromImage(CannonUL.mirrored(False, True))

    def dataChanged(self):
        left = self.parent.spritedata[5] & 1
        upsideDown = (self.parent.spritedata[5] >> 4) & 1

        if upsideDown:
            self.image = ImageCache['CannonMultiD%d' % left]
            self.offset = (-8, -1)
        else:
            self.image = ImageCache['CannonMultiU%d' % left]
            self.offset = (-8, -11)

        super().dataChanged()


class SpriteImage_RotCannon(SLib.SpriteImage_StaticMultiple):  # 300
    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('RotCannon', 'rot_cannon.png')
        SLib.loadIfNotInImageCache('RotCannonU', 'rot_cannon_u.png')

    def dataChanged(self):

        upsideDown = (self.parent.spritedata[5] >> 4) & 1
        if not upsideDown:
            self.image = ImageCache['RotCannon']
            self.offset = (-12, -29)
        else:
            self.image = ImageCache['RotCannonU']
            self.offset = (-12, 0)

        super().dataChanged()


class SpriteImage_RotCannonPipe(SLib.SpriteImage_StaticMultiple):  # 301
    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('RotCannonPipe', 'rot_cannon_pipe.png')
        SLib.loadIfNotInImageCache('RotCannonPipeU', 'rot_cannon_pipe_u.png')

    def dataChanged(self):

        upsideDown = (self.parent.spritedata[5] >> 4) & 1
        if not upsideDown:
            self.image = ImageCache['RotCannonPipe']
            self.offset = (-40, -74)
        else:
            self.image = ImageCache['RotCannonPipeU']
            self.offset = (-40, 0)

        super().dataChanged()


class SpriteImage_MontyMole(SLib.SpriteImage_StaticMultiple):  # 303
    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Mole', 'monty_mole.png')
        SLib.loadIfNotInImageCache('MoleCave', 'monty_mole_hole.png')

    def dataChanged(self):

        notInCave = self.parent.spritedata[5] & 1
        if not notInCave:  # wow, that looks weird
            self.image = ImageCache['MoleCave']
            self.offset = (-6, -5)
        else:
            self.image = ImageCache['Mole']
            self.offset = (3.5, -4)

        super().dataChanged()


class SpriteImage_RotFlameCannon(SLib.SpriteImage_StaticMultiple):  # 304
    @staticmethod
    def loadImages():
        if 'RotFlameCannon0' in ImageCache: return
        for i in range(5):
            ImageCache['RotFlameCannon%d' % i] = SLib.GetImg('rotating_flame_cannon_%d.png' % i)
            originalImg = SLib.GetImg('rotating_flame_cannon_%d.png' % i, True)
            ImageCache['RotFlameCannonFlipped%d' % i] = QtGui.QPixmap.fromImage(originalImg.mirrored(False, True))

    def dataChanged(self):

        orientation = self.parent.spritedata[5] >> 4
        length = self.parent.spritedata[5] & 15
        orientation = '' if orientation == 0 else 'Flipped'

        if length > 4: length = 0
        if not orientation:
            self.yOffset = -2
        else:
            self.yOffset = 0

        self.image = ImageCache['RotFlameCannon%s%d' % (orientation, length)]

        super().dataChanged()


class SpriteImage_RotSpotlight(SLib.SpriteImage_StaticMultiple):  # 306
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.offset = (-22, -64)

    @staticmethod
    def loadImages():
        if 'RotSpotlight0' in ImageCache: return
        for i in range(16):
            ImageCache['RotSpotlight%d' % i] = SLib.GetImg('rotational_spotlight_%d.png' % i)

    def dataChanged(self):

        angle = self.parent.spritedata[3] & 15
        self.image = ImageCache['RotSpotlight%d' % angle]

        super().dataChanged()


class SpriteImage_SynchroFlameJet(SLib.SpriteImage_StaticMultiple):  # 309
    @staticmethod
    def loadImages():
        if 'SynchroFlameJetOnR' in ImageCache: return
        transform90 = QtGui.QTransform()
        transform270 = QtGui.QTransform()
        transform90.rotate(90)
        transform270.rotate(270)

        onImage = SLib.GetImg('synchro_flame_jet.png', True)
        offImage = SLib.GetImg('synchro_flame_jet_off.png', True)
        ImageCache['SynchroFlameJetOnR'] = QtGui.QPixmap.fromImage(onImage)
        ImageCache['SynchroFlameJetOnD'] = QtGui.QPixmap.fromImage(onImage.transformed(transform90))
        ImageCache['SynchroFlameJetOnL'] = QtGui.QPixmap.fromImage(onImage.mirrored(True, False))
        ImageCache['SynchroFlameJetOnU'] = QtGui.QPixmap.fromImage(
            onImage.transformed(transform270).mirrored(True, False))
        ImageCache['SynchroFlameJetOffR'] = QtGui.QPixmap.fromImage(offImage)
        ImageCache['SynchroFlameJetOffD'] = QtGui.QPixmap.fromImage(offImage.transformed(transform90))
        ImageCache['SynchroFlameJetOffL'] = QtGui.QPixmap.fromImage(offImage.mirrored(True, False))
        ImageCache['SynchroFlameJetOffU'] = QtGui.QPixmap.fromImage(
            offImage.transformed(transform270).mirrored(True, False))

    def dataChanged(self):
        mode = self.parent.spritedata[4] & 1
        direction = self.parent.spritedata[5] & 3

        mode = 'Off' if mode else 'On'
        self.offset = (
            (0, 0),
            (-96, 0),
            (0, -96),
            (0, 0),
        )[direction]
        directionstr = 'RLUD'[direction]

        self.image = ImageCache['SynchroFlameJet%s%s' % (mode, directionstr)]

        super().dataChanged()


class SpriteImage_ArrowSign(SLib.SpriteImage_StaticMultiple):  # 310
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.offset = (-8, -16)

    @staticmethod
    def loadImages():
        if 'ArrowSign0' in ImageCache: return
        for i in range(8):
            ImageCache['ArrowSign%d' % i] = SLib.GetImg('arrow_sign_%d.png' % i)

    def dataChanged(self):

        direction = self.parent.spritedata[5] & 0xF
        self.image = ImageCache['ArrowSign%d' % direction]

        super().dataChanged()


class SpriteImage_ArrowBlock(SLib.SpriteImage_StaticMultiple):  # 321
    @staticmethod
    def loadImages():
        if 'ArrowBlock0' in ImageCache: return
        ImageCache['ArrowBlock0'] = SLib.GetImg('arrow_block_up.png')
        ImageCache['ArrowBlock1'] = SLib.GetImg('arrow_block_down.png')
        ImageCache['ArrowBlock2'] = SLib.GetImg('arrow_block_left.png')
        ImageCache['ArrowBlock3'] = SLib.GetImg('arrow_block_right.png')

    def dataChanged(self):
        direction = self.parent.spritedata[5] & 3
        self.image = ImageCache['ArrowBlock%d' % direction]

        super().dataChanged()


class SpriteImage_BubbleCannon(SLib.SpriteImage_StaticMultiple):  # 328
    @staticmethod
    def loadImages():
        if 'BubbleCannon0' in ImageCache: return
        ImageCache['BubbleCannon0'] = SLib.GetImg('bubble_cannon_small.png')
        ImageCache['BubbleCannon1'] = SLib.GetImg('bubble_cannon_big.png')

    def dataChanged(self):
        size = self.parent.spritedata[5] & 1
        self.image = ImageCache['BubbleCannon%d' % size]
        self.offset = (
            (-17, -15),
            (-36, -31),
        )[size]

        super().dataChanged()


class SpriteImage_RopeLadder(SLib.SpriteImage_StaticMultiple):  # 330
    @staticmethod
    def loadImages():
        if 'RopeLadder0' in ImageCache: return
        ImageCache['RopeLadder0'] = SLib.GetImg('ropeladder_0.png')
        ImageCache['RopeLadder1'] = SLib.GetImg('ropeladder_1.png')
        ImageCache['RopeLadder2'] = SLib.GetImg('ropeladder_2.png')

    def dataChanged(self):

        size = self.parent.spritedata[5]
        if size > 2: size = 0

        self.image = ImageCache['RopeLadder%d' % size]
        self.offset = (-3, -2)

        super().dataChanged()


class SpriteImage_DishPlatform(SLib.SpriteImage_StaticMultiple):  # 331
    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('DishPlatform0', 'dish_platform_short.png')
        SLib.loadIfNotInImageCache('DishPlatform1', 'dish_platform_long.png')

    def dataChanged(self):

        size = self.parent.spritedata[4] & 15
        if size == 0:
            self.xOffset = -144
            self.width = 304
        else:
            self.xOffset = -208
            self.width = 433

        self.image = ImageCache['DishPlatform%d' % size]

        super().dataChanged()


class SpriteImage_BigShell(SLib.SpriteImage_StaticMultiple):  # 341
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.offset = (-97, -145)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('BigShell', 'bigshell_green.png')
        SLib.loadIfNotInImageCache('BigShellGrass', 'bigshell_green_grass.png')

    def dataChanged(self):
        style = self.parent.spritedata[5] & 1

        if style == 0:
            self.image = ImageCache['BigShellGrass']
        else:
            self.image = ImageCache['BigShell']

        super().dataChanged()


class SpriteImage_Muncher(SLib.SpriteImage_StaticMultiple):  # 342    
    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Muncher', 'muncher.png')
        SLib.loadIfNotInImageCache('MuncherF', 'muncher_frozen.png')

    def dataChanged(self):

        frozen = self.parent.spritedata[5] & 1
        if frozen == 1:
            self.image = ImageCache['MuncherF']
            self.offset = (0, 0)
        else:
            self.image = ImageCache['Muncher']
            self.offset = (0, -1)

        super().dataChanged()


class SpriteImage_Fuzzy(SLib.SpriteImage_StaticMultiple):  # 343
    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Fuzzy', 'fuzzy.png')
        SLib.loadIfNotInImageCache('FuzzyGiant', 'fuzzy_giant.png')

    def dataChanged(self):
        giant = self.parent.spritedata[4] & 1

        self.image = ImageCache['FuzzyGiant'] if giant else ImageCache['Fuzzy']
        self.offset = (-18, -18) if giant else (-7, -7)

        super().dataChanged()


class SpriteImage_HangingChainPlatform(SLib.SpriteImage_StaticMultiple):  # 346
    @staticmethod
    def loadImages():
        if 'HangingChainPlatform0' in ImageCache: return
        ImageCache['HangingChainPlatform0'] = SLib.GetImg('hanging_chain_platform_small.png')
        ImageCache['HangingChainPlatform1'] = SLib.GetImg('hanging_chain_platform_medium.png')
        ImageCache['HangingChainPlatform2'] = SLib.GetImg('hanging_chain_platform_large.png')

    def dataChanged(self):
        size = (self.parent.spritedata[4] & 3) % 3
        self.offset = (
            (-26, -12),
            (-42, -12),
            (-58, -12),
        )[size]
        self.image = ImageCache['HangingChainPlatform%d' % size]

        super().dataChanged()


class SpriteImage_Fruit(SLib.SpriteImage_StaticMultiple):  # 357
    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Fruit', 'fruit.png')
        SLib.loadIfNotInImageCache('FruitCookie', 'fruit_cookie.png')

    def dataChanged(self):

        style = self.parent.spritedata[5] & 1
        if style == 0:
            self.image = ImageCache['Fruit']
        else:
            self.image = ImageCache['FruitCookie']

        super().dataChanged()


class SpriteImage_CrystalBlock(SLib.SpriteImage_StaticMultiple):  # 361
    @staticmethod
    def loadImages():
        if 'CrystalBlock0' in ImageCache: return
        for size in range(3):
            ImageCache['CrystalBlock%d' % size] = SLib.GetImg('crystal_block_%d.png' % size)

    def dataChanged(self):
        size = self.parent.spritedata[4] & 3

        if size == 3:
            size = 2

        self.image = ImageCache['CrystalBlock%d' % size]

        super().dataChanged()


class SpriteImage_CubeKinokoRot(SLib.SpriteImage_StaticMultiple):  # 366
    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('CubeKinokoG', 'cube_kinoko_g.png')
        SLib.loadIfNotInImageCache('CubeKinokoR', 'cube_kinoko_r.png')

    def dataChanged(self):

        style = self.parent.spritedata[4] & 1
        if style == 0:
            self.image = ImageCache['CubeKinokoR']
        else:
            self.image = ImageCache['CubeKinokoG']

        super().dataChanged()


class SpriteImage_FlashRaft(SLib.SpriteImage_StaticMultiple):  # 368
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['FlashlightRaft'],
            (-11, -20),
        )

        self.aux.append(SLib.AuxiliaryImage(parent, 132, 120))
        self.aux[0].image = ImageCache['FlashlightLamp']
        self.aux[0].setPos(-22, -91)

        self.aux.append(SLib.AuxiliaryRectOutline(parent, 24, 24, 144, 30))
        self.aux[1].setIsBehindSprite(False)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('FlashlightRaft', 'flashraft.png')
        SLib.loadIfNotInImageCache('FlashlightLamp', 'flashraft_light.png')

    def dataChanged(self):
        pathcontrolled = self.parent.spritedata[5] & 1
        midway = (self.parent.spritedata[5] >> 4) & 1

        self.aux[1].setSize(24, 24, 136, 30) if pathcontrolled else self.aux[1].setSize(0, 0)

        if midway:
            self.alpha = 0.5
            self.aux[0].alpha = 0.5
        else:
            self.alpha = 1
            self.aux[0].alpha = 1

        super().dataChanged()


class SpriteImage_SlidingPenguin(SLib.SpriteImage_StaticMultiple):  # 369
    @staticmethod
    def loadImages():
        if 'PenguinL' in ImageCache: return
        penguin = SLib.GetImg('sliding_penguin.png', True)
        ImageCache['PenguinL'] = QtGui.QPixmap.fromImage(penguin)
        ImageCache['PenguinR'] = QtGui.QPixmap.fromImage(penguin.mirrored(True, False))

    def dataChanged(self):

        direction = self.parent.spritedata[5] & 1
        if direction == 0:
            self.image = ImageCache['PenguinL']
        else:
            self.image = ImageCache['PenguinR']

        super().dataChanged()


class SpriteImage_IceBlock(SLib.SpriteImage_StaticMultiple):  # 385
    @staticmethod
    def loadImages():
        if 'IceBlock00' in ImageCache: return
        for i in range(4):
            for j in range(4):
                ImageCache['IceBlock%d%d' % (i, j)] = SLib.GetImg('iceblock%d%d.png' % (i, j))

    def dataChanged(self):

        size = self.parent.spritedata[5]
        height = (size & 0x30) >> 4
        width = size & 3

        self.image = ImageCache['IceBlock%d%d' % (width, height)]
        self.xOffset = width * -4
        self.yOffset = height * -8

        super().dataChanged()


class SpriteImage_Bush(SLib.SpriteImage_StaticMultiple):  # 387
    def __init__(self, parent):
        # this sprite image should actually show behind layer 1...
        super().__init__(parent, 1.5)
        self.parent.setZValue(24999)

    @staticmethod
    def loadImages():
        if 'Bush00' in ImageCache: return
        for typenum, typestr in enumerate(('green', 'yellowish')):
            for sizenum, sizestr in enumerate(('small', 'med', 'large', 'xlarge')):
                ImageCache['Bush%d%d' % (typenum, sizenum)] = SLib.GetImg('bush_%s_%s.png' % (typestr, sizestr))

    def dataChanged(self):

        props = self.parent.spritedata[5]
        style = (props >> 4) & 1
        size = props & 3

        self.offset = (
            (-22, -25),
            (-30, -44),
            (-40, -60),
            (-53, -78),
        )[size]

        self.image = ImageCache['Bush%d%d' % (style, size)]

        super().dataChanged()


class SpriteImage_Gabon(SLib.SpriteImage_StaticMultiple):  # 414
    @staticmethod
    def loadImages():
        if 'GabonLeft' in ImageCache: return
        gabon = SLib.GetImg('gabon.png', True)
        ImageCache['GabonLeft'] = QtGui.QPixmap.fromImage(gabon)
        ImageCache['GabonRight'] = QtGui.QPixmap.fromImage(gabon.mirrored(True, False))
        SLib.loadIfNotInImageCache('GabonSpike', 'gabon_spike.png')

    def dataChanged(self):
        throwdir = self.parent.spritedata[5] & 1
        facing = self.parent.spritedata[4] & 1

        if throwdir == 0:
            self.image = ImageCache['GabonSpike']
            self.offset = (-7, -31) #-11, -47
        else:
            self.image = (
                ImageCache['GabonLeft'],
                ImageCache['GabonRight'],
            )[facing]
            self.offset = (-8, -33) #-12, -50

        super().dataChanged()


class SpriteImage_PalmTree(SLib.SpriteImage_StaticMultiple):  # 424
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.parent.setZValue(24999)
        self.xOffset = -24.5

    @staticmethod
    def loadImages():
        if 'PalmTree0' in ImageCache: return
        for i in range(8):
            ImageCache['PalmTree%d' % i] = SLib.GetImg('palmtree_%d.png' % i)

    def dataChanged(self):

        size = self.parent.spritedata[5] & 7
        self.image = ImageCache['PalmTree%d' % size]
        self.yOffset = 16 - (self.image.height() / 1.5)

        super().dataChanged()


class SpriteImage_WarpCannon(SLib.SpriteImage_StaticMultiple):  # 434
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.offset = (5, -25)

    @staticmethod
    def loadImages():
        if 'Warp0' in ImageCache: return
        ImageCache['Warp0'] = SLib.GetImg('warp_w5.png')
        ImageCache['Warp1'] = SLib.GetImg('warp_w6.png')
        ImageCache['Warp2'] = SLib.GetImg('warp_w8.png')

    def dataChanged(self):

        dest = self.parent.spritedata[5] & 3
        if dest == 3: dest = 0
        self.image = ImageCache['Warp%d' % dest]

        super().dataChanged()


class SpriteImage_CageBlocks(SLib.SpriteImage_StaticMultiple):  # 438
    @staticmethod
    def loadImages():
        if 'CageBlock0' in ImageCache: return

        for i in range(5):
            ImageCache['CageBlock%d' % i] = SLib.GetImg('cage_block_%d.png' % i)

    def dataChanged(self):

        type = (self.parent.spritedata[4] & 15) % 5

        self.offset = (
            (-112, -112),
            (-112, -112),
            (-97, -81),
            (-80, -96),
            (-112, -112),
        )[type]

        self.image = ImageCache['CageBlock%d' % type]

        super().dataChanged()


class SpriteImage_Seaweed(SLib.SpriteImage_StaticMultiple):  # 453
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.parent.setZValue(24998)

    @staticmethod
    def loadImages():
        if 'Seaweed0' in ImageCache: return
        for i in range(4):
            ImageCache['Seaweed%d' % i] = SLib.GetImg('seaweed_%d.png' % i)

    def dataChanged(self):
        SeaweedSizes = [0, 1, 2, 2, 3, 3]
        SeaweedXOffsets = [-15, -25, -29, -38]

        style = (self.parent.spritedata[5] & 0xF) % 6
        size = SeaweedSizes[style]

        self.image = ImageCache['Seaweed%d' % size]
        self.offset = (
            SeaweedXOffsets[size],
            16 - (self.image.height() / 1.5),
        )

        super().dataChanged()


class SpriteImage_BossBridge(SLib.SpriteImage_StaticMultiple):  # 456
    @staticmethod
    def loadImages():
        if 'BossBridgeL' in ImageCache: return
        ImageCache['BossBridgeL'] = SLib.GetImg('boss_bridge_left.png')
        ImageCache['BossBridgeM'] = SLib.GetImg('boss_bridge_middle.png')
        ImageCache['BossBridgeR'] = SLib.GetImg('boss_bridge_right.png')

    def dataChanged(self):
        style = (self.parent.spritedata[5] & 3) % 3
        self.image = (
            ImageCache['BossBridgeM'],
            ImageCache['BossBridgeR'],
            ImageCache['BossBridgeL'],
        )[style]

        super().dataChanged()


class SpriteImage_SilverGearBlock(SLib.SpriteImage_StaticMultiple):  # 460
    @staticmethod
    def loadImages():
        if 'SilverGearBlockDown3' in ImageCache: return
        for gear in range(4):
            image = SLib.GetImg('silver_gear_block_%d.png' % gear, True)
            ImageCache['SilverGearBlockUp%d' % gear] = QtGui.QPixmap.fromImage(image)
            ImageCache['SilverGearBlockDown%d' % gear] = QtGui.QPixmap.fromImage(image.mirrored(True, True))

    def dataChanged(self):
        style = self.parent.spritedata[5] & 3
        flipped = (self.parent.spritedata[5] >> 4) & 1

        if flipped:
            self.image = ImageCache['SilverGearBlockDown%d' % style]
        else:
            self.image = ImageCache['SilverGearBlockUp%d' % style]

        super().dataChanged()


class SpriteImage_SwingingVine(SLib.SpriteImage_StaticMultiple):  # 464
    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('SwingVine', 'swing_vine.png')
        SLib.loadIfNotInImageCache('SwingChain', 'swing_chain.png')

    def dataChanged(self):
        style = self.parent.spritedata[5] & 1
        self.image = ImageCache['SwingVine'] if not style else ImageCache['SwingChain']

        super().dataChanged()


class SpriteImage_IceFloe(SLib.SpriteImage_StaticMultiple):  # 475
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.alpha = 0.65

    @staticmethod
    def loadImages():
        if 'IceFloe0' in ImageCache: return

        for size in range(13):
            ImageCache['IceFloe%d' % size] = SLib.GetImg('ice_floe_%d.png' % size)

    def dataChanged(self):

        size = self.parent.spritedata[5] & 15

        if size > 12:
            size = 0

        self.offset = (
            (-1, -32),  # 0: 3x3
            (-2, -48),  # 1: 4x4
            (-2, -64),  # 2: 5x5
            (-2, -32),  # 3: 4x3
            (-2, -48),  # 4: 5x4
            (-3, -80),  # 5: 7x6
            (-3, -160),  # 6: 16x11
            (-3, -112),  # 7: 11x8
            (-1, -48),  # 8: 2x4
            (-2, -48),  # 9: 3x4
            (-2.5, -96),  # 10: 6x7
            (-1, -64),  # 11: 2x5
            (-1, -64),  # 12: 3x5
        )[size]

        self.image = ImageCache['IceFloe%d' % size]

        super().dataChanged()


class SpriteImage_BowserSwitchSm(SLib.SpriteImage_StaticMultiple):  # 478
    @staticmethod
    def loadImages():
        if 'ESwitch' in ImageCache: return
        e = SLib.GetImg('e_switch.png', True)
        ImageCache['ESwitch'] = QtGui.QPixmap.fromImage(e)
        ImageCache['ESwitchU'] = QtGui.QPixmap.fromImage(e.mirrored(True, True))

    def dataChanged(self):

        upsideDown = self.parent.spritedata[5] & 1
        if not upsideDown:
            self.image = ImageCache['ESwitch']
        else:
            self.image = ImageCache['ESwitchU']

        super().dataChanged()


class SpriteImage_BowserSwitchLg(SLib.SpriteImage_StaticMultiple):  # 479
    @staticmethod
    def loadImages():
        if 'ELSwitch' in ImageCache: return
        elg = SLib.GetImg('e_switch_lg.png', True)
        ImageCache['ELSwitch'] = QtGui.QPixmap.fromImage(elg)
        ImageCache['ELSwitchU'] = QtGui.QPixmap.fromImage(elg.mirrored(True, True))

    def dataChanged(self):

        upsideDown = self.parent.spritedata[5] & 1
        if not upsideDown:
            self.image = ImageCache['ELSwitch']
            self.offset = (-15, -25)
        else:
            self.image = ImageCache['ELSwitchU']
            self.offset = (-15, 0)

        super().dataChanged()


class SpriteImage_FinalBossRubble(SLib.SpriteImage_StaticMultiple):  # 481
    def __init__(self, parent):
        super().__init__(parent)

    @staticmethod
    def loadImages():
        if 'FinalBossRubble0' in ImageCache: return
        for size in range(2):
            ImageCache['FinalBossRubble%d' % size] = SLib.GetImg('final_boss_rubble_%d.png' % size)

    def dataChanged(self):
        size = self.parent.spritedata[5] & 1

        self.image = ImageCache['FinalBossRubble%d' % size]

        super().dataChanged()
