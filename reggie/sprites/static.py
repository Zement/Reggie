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



class SpriteImage_Goomba(SLib.SpriteImage_Static):  # 20
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Goomba'],
            (-1, -4),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Goomba', 'goomba.png')


class SpriteImage_ParaGoomba(SLib.SpriteImage_Static):  # 21
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['ParaGoomba'],
            (1, -10),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('ParaGoomba', 'para_goomba.png')


class SpriteImage_UpsideDownSpiny(SLib.SpriteImage_Static):  # 26
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['SpinyU'],
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('SpinyU', 'spiny_u.png')


class SpriteImage_Thwomp(SLib.SpriteImage_Static):  # 47
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Thwomp'],
            (-6, -6),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Thwomp', 'thwomp.png')


class SpriteImage_GiantThwomp(SLib.SpriteImage_Static):  # 48
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['GiantThwomp'],
            (-8, -8),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('GiantThwomp', 'giant_thwomp.png')


class SpriteImage_TiltingGirder(SLib.SpriteImage_Static):  # 51
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['TiltingGirder'],
            (-1 / 1.5, -28 / 1.5),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('TiltingGirder', 'tilting_girder.png')


class SpriteImage_Lakitu(SLib.SpriteImage_Static):  # 54
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Lakitu'],
            (-16, -24),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Lakitu', 'lakitu.png')


class SpriteImage_UnusedRisingSeesaw(SLib.SpriteImage_Static):  # 55
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['UnusedPlatformDark'].scaled(
                377, 24,
                Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation,
            ),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('UnusedPlatformDark', 'unused_platform_dark.png')


class SpriteImage_RisingTiltGirder(SLib.SpriteImage_Static):  # 56
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['RisingTiltGirder'],
            (-32, -10),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('RisingTiltGirder', 'rising_girder.png')


class SpriteImage_SpikeBall(SLib.SpriteImage_Static):  # 63
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['SpikeBall'],
            (0, 16)
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('SpikeBall', 'spike_ball.png')


class SpriteImage_PipePiranhaUp(SLib.SpriteImage_Static):  # 65
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['PipePlantUp'],
            (4 / 1.5, -30),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('PipePlantUp', 'piranha_pipe_up.png')


class SpriteImage_PipePiranhaDown(SLib.SpriteImage_Static):  # 66
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['PipePlantDown'],
            (4 / 1.5, 32),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('PipePlantDown', 'piranha_pipe_down.png')


class SpriteImage_PipePiranhaRight(SLib.SpriteImage_Static):  # 67
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['PipePlantRight'],
            (32, 4 / 1.5),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('PipePlantRight', 'piranha_pipe_right.png')


class SpriteImage_PipePiranhaLeft(SLib.SpriteImage_Static):  # 68
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['PipePlantLeft'],
            (-30, 4 / 1.5),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('PipePlantLeft', 'piranha_pipe_left.png')


class SpriteImage_PipeFiretrapUp(SLib.SpriteImage_Static):  # 69
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['PipeFiretrapUp'],
            (-8 / 1.5, -26),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('PipeFiretrapUp', 'firetrap_pipe_up.png')


class SpriteImage_PipeFiretrapDown(SLib.SpriteImage_Static):  # 70
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['PipeFiretrapDown'],
            (-8 / 1.5, 32),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('PipeFiretrapDown', 'firetrap_pipe_down.png')


class SpriteImage_PipeFiretrapRight(SLib.SpriteImage_Static):  # 71
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['PipeFiretrapRight'],
            (32, 10 / 1.5),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('PipeFiretrapRight', 'firetrap_pipe_right.png')


class SpriteImage_PipeFiretrapLeft(SLib.SpriteImage_Static):  # 72
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['PipeFiretrapLeft'],
            (-26, 10 / 1.5),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('PipeFiretrapLeft', 'firetrap_pipe_left.png')


class SpriteImage_ShipKey(SLib.SpriteImage_Static):  # 77
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['ShipKey'],
            (0, -8),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('ShipKey', 'ship_key.png')


class SpriteImage_FireBro(SLib.SpriteImage_Static):  # 80
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['FireBro'],
            (-8, -22),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('FireBro', 'firebro.png')


class SpriteImage_BanzaiBillLauncher(SLib.SpriteImage_Static):  # 93
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['BanzaiLauncher'],
            (-32, -67),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('BanzaiLauncher', 'banzai_launcher.png')


class SpriteImage_BoomerangBro(SLib.SpriteImage_Static):  # 94
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['BoomerangBro'],
            (-8, -22),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('BoomerangBro', 'boomerangbro.png')


class SpriteImage_GiantSpikeBall(SLib.SpriteImage_Static):  # 98
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['GiantSpikeBall'],
            (-24, -16),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('GiantSpikeBall', 'giant_spike_ball.png')


class SpriteImage_Swooper(SLib.SpriteImage_Static):  # 100
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Swooper'],
            (2, 0),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Swooper', 'swooper.png')


class SpriteImage_Bobomb(SLib.SpriteImage_Static):  # 101
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Bobomb'],
            (-8, -8),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Bobomb', 'bobomb.png')


class SpriteImage_Broozer(SLib.SpriteImage_Static):  # 102
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Broozer'],
            (-9, -17),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Broozer', 'broozer.png')


class SpriteImage_Blooper(SLib.SpriteImage_Static):  # 111
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Blooper'],
            (-3, -10),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Blooper', 'blooper.png')


class SpriteImage_BlooperBabies(SLib.SpriteImage_Static):  # 112
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['BlooperBabies'],
            (-5, -10),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('BlooperBabies', 'blooper_babies.png')


class SpriteImage_DryBones(SLib.SpriteImage_Static):  # 118
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['DryBones'],
            (-7, -16),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('DryBones', 'drybones.png')


class SpriteImage_GiantDryBones(SLib.SpriteImage_Static):  # 119
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['GiantDryBones'],
            (-13, -24),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('GiantDryBones', 'giant_drybones.png')


class SpriteImage_SledgeBro(SLib.SpriteImage_Static):  # 120
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['SledgeBro'],
            (-8, -28.5),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('SledgeBro', 'sledgebro.png')


class SpriteImage_FlipFence(SLib.SpriteImage_Static):  # 127
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['FlipFence'],
            (-4, -8),
        )
        parent.setZValue(24999)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('FlipFence', 'flipfence.png')


class SpriteImage_FlipFenceLong(SLib.SpriteImage_Static):  # 128
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['FlipFenceLong'],
            (6, 0),
        )
        parent.setZValue(24999)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('FlipFenceLong', 'flipfence_long.png')


class SpriteImage_4Spinner(SLib.SpriteImage_Static):  # 129
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['4Spinner'],
            (-97 / 1.5, -48),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('4Spinner', '4spinner.png')

    def dataChanged(self):
        super().dataChanged()
        self.alpha = 0.6 if (self.parent.spritedata[2] >> 4) & 1 else 1


class SpriteImage_Wiggler(SLib.SpriteImage_Static):  # 130
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Wiggler'],
            (0, -12),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Wiggler', 'wiggler.png')


class SpriteImage_Crow(SLib.SpriteImage_Static):  # 134
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Crow'],
            (-3, -2),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Crow', 'crow.png')


class SpriteImage_HangingPlatform(SLib.SpriteImage_Static):  # 135
    def __init__(self, parent):
        super().__init__(parent, 1.5)

        self.aux.append(SLib.AuxiliaryImage(parent, 11, 378))
        self.aux[0].image = ImageCache['HangingPlatformTop']
        self.aux[0].setPos(138, -378)

        self.image = ImageCache['HangingPlatformBottom']
        self.size = (192, 32)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('HangingPlatformTop', 'hanging_platform_top.png')
        SLib.loadIfNotInImageCache('HangingPlatformBottom', 'hanging_platform_bottom.png')


class SpriteImage_RedCoin(SLib.SpriteImage_Static):  # 144
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['RedCoin'],
        )


class SpriteImage_FloatingBarrel(SLib.SpriteImage_Static):  # 145
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            offset = (-16, -9)
        )

        img = ImageCache['FloatingBarrel']
        self.width = (img.width() / self.scale) + 1
        self.height = (img.height() / self.scale) + 2

        self.aux.append(SLib.AuxiliaryImage(parent, img.width(), img.height()))
        self.aux[0].image = img

        path = QtGui.QPainterPath()
        path.lineTo(QtCore.QPointF(self.width * 1.5, 0))

        self.aux.append(SLib.AuxiliaryPainterPath(parent, path, img.width(),
            SLib.OutlinePen.width(), 0, 36))

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('FloatingBarrel', 'barrel_floating.png')

    def dataChanged(self):
        # Don't let SLib.SpriteImage_Static reset size
        SLib.SpriteImage.dataChanged(self)


class SpriteImage_ChainChomp(SLib.SpriteImage_Static):  # 146
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['ChainChomp'],
            (-90, -32),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('ChainChomp', 'chain_chomp.png')


class SpriteImage_Spring(SLib.SpriteImage_Static):  # 148
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Spring'],
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Spring', 'spring.png')

    def dataChanged(self):
        offset = (self.parent.spritedata[5] >> 4) & 1
        self.xOffset = 8 if offset else 0

        super().dataChanged()


class SpriteImage_Porcupuffer(SLib.SpriteImage_Static):  # 151
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Porcupuffer'],
            (-16, -18),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Porcupuffer', 'porcu_puffer.png')


class SpriteImage_ChestnutGoomba(SLib.SpriteImage_Static):  # 170
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['ChestnutGoomba'],
            (-6, -8),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('ChestnutGoomba', 'chestnut_goomba.png')


class SpriteImage_PowerupBubble(SLib.SpriteImage_Static):  # 171
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['MushroomBubble'],
            (-8, -8),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('MushroomBubble', 'powerup_bubble.png')


class SpriteImage_GiantFloatingLog(SLib.SpriteImage_Static):  # 173
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['GiantFloatingLog'],
            (-152, -32),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('GiantFloatingLog', 'giant_floating_log.png')


class SpriteImage_FireChomp(SLib.SpriteImage_Static):  # 177
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['FireChomp'],
            (-2, -20),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('FireChomp', 'fire_chomp.png')


class SpriteImage_CheepChomp(SLib.SpriteImage_Static):  # 180
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['CheepChomp'],
            (-32, -16),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('CheepChomp', 'cheep_chomp.png')


class SpriteImage_ToadBalloon(SLib.SpriteImage_Static):  # 185
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['ToadBalloon'],
            (-4, -4),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('ToadBalloon', 'toad_balloon.png')


class SpriteImage_PlayerBlock(SLib.SpriteImage_Static):  # 187
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['PlayerBlock'],
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('PlayerBlock', 'player_block.png')


class SpriteImage_MidwayFlag(SLib.SpriteImage_Static):  # 188
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['MidwayFlag'],
            (1 / 1.5, -55 / 1.5),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('MidwayFlag', 'midway_flag.png')


class SpriteImage_LarryKoopa(SLib.SpriteImage_Static):  # 189
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['LarryKoopa'],
            (-17, -33),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('LarryKoopa', 'Larry_Koopa.png')


class SpriteImage_TiltingGirderUnused(SLib.SpriteImage_Static):  # 190
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['TiltingGirder'],
            (0, -18),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('TiltingGirder', 'tilting_girder.png')


class SpriteImage_Urchin(SLib.SpriteImage_Static):  # 193
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Urchin'],
            (-12, -14),
        )

        self.aux.append(SLib.AuxiliaryTrackObject(
            parent, 16, 16, SLib.AuxiliaryTrackObject.Vertical
        ))
        self.aux[0].setPos(self.width * 0.75 - 12, self.height * 0.75 - 12)
        self.aux[0].setIsBehindSprite(False)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Urchin', 'urchin.png')

    def dataChanged(self):
        super().dataChanged()

        distance = ((self.parent.spritedata[5] & 0xF0) << 1) | 8
        horizontal = (self.parent.spritedata[5] & 1) == 1

        if horizontal:
            self.aux[0].direction = SLib.AuxiliaryTrackObject.Horizontal
            self.aux[0].setSize(distance + 8, 16)
            self.aux[0].setPos((self.width - distance) * 0.75 - 8, self.height * 0.75 - 12)
        else:
            self.aux[0].direction = SLib.AuxiliaryTrackObject.Vertical
            self.aux[0].setSize(16, distance + 8)
            self.aux[0].setPos(self.width * 0.75 - 12, (self.height - distance) * 0.75 - 8)

class SpriteImage_MegaUrchin(SLib.SpriteImage_Static):  # 194
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['MegaUrchin'],
            (-48, -46),
        )

        self.aux.append(SLib.AuxiliaryTrackObject(
            parent, 16, 16, SLib.AuxiliaryTrackObject.Vertical
        ))
        self.aux[0].setPos(self.width * 0.75 - 12, self.height * 0.75 - 12)
        self.aux[0].setIsBehindSprite(False)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('MegaUrchin', 'mega_urchin.png')

    def dataChanged(self):
        super().dataChanged()

        distance = ((self.parent.spritedata[5] & 0xF0) << 1) | 8
        horizontal = (self.parent.spritedata[5] & 1) == 1

        if horizontal:
            self.aux[0].direction = SLib.AuxiliaryTrackObject.Horizontal
            self.aux[0].setSize(distance + 8, 16)
            self.aux[0].setPos((self.width - distance) * 0.75 - 8, self.height * 0.75 - 12)
        else:
            self.aux[0].direction = SLib.AuxiliaryTrackObject.Vertical
            self.aux[0].setSize(16, distance + 8)
            self.aux[0].setPos(self.width * 0.75 - 12, (self.height - distance) * 0.75 - 8)


class SpriteImage_GiantGoomba(SLib.SpriteImage_Static):  # 198
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['GiantGoomba'],
            (-6, -19),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('GiantGoomba', 'giant_goomba.png')


class SpriteImage_MegaGoomba(SLib.SpriteImage_Static):  # 199
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['MegaGoomba'],
            (-11, -37),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('MegaGoomba', 'mega_goomba.png')


class SpriteImage_Microgoomba(SLib.SpriteImage_Static):  # 200
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Microgoomba'],
            (4, 8),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Microgoomba', 'microgoomba.png')


class SpriteImage_MGCannon(SLib.SpriteImage_Static):  # 202
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['MGCannon'],
            (-12, -42),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('MGCannon', 'mg_cannon.png')


class SpriteImage_FreefallPlatform(SLib.SpriteImage_Static):  # 214
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['FreefallGH'],
        )
        self.parent.setZValue(24999)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('FreefallGH', 'freefall_gh_platform.png')


class SpriteImage_ConveyorSpike(SLib.SpriteImage_Static):  # 222
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['SpikeU'],
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('SpikeU', 'spike_up.png')


class SpriteImage_SandPillar(SLib.SpriteImage_Static):  # 229
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['SandPillar'],
            (-33, -150),
        )
        self.alpha = 0.65

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('SandPillar', 'sand_pillar.png')


class SpriteImage_Bramball(SLib.SpriteImage_Static):  # 230
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Bramball'],
            (-50 / 1.5, -71 / 1.5),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Bramball', 'bramball.png')


class SpriteImage_MechaKoopa(SLib.SpriteImage_Static):  # 232
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['MechaKoopa'],
            (-8, -14),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('MechaKoopa', 'mechakoopa.png')


class SpriteImage_PCoin(SLib.SpriteImage_Static):  # 237
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['PCoin'],
        )


class SpriteImage_Foo(SLib.SpriteImage_Static):  # 238
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Foo'],
            (-8, -16),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Foo', 'foo.png')


class SpriteImage_GiantWiggler(SLib.SpriteImage_Static):  # 240
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['GiantWiggler'],
            (-24, -64),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('GiantWiggler', 'giant_wiggler.png')


class SpriteImage_FallingLedgeBar(SLib.SpriteImage_Static):  # 242
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['FallingLedgeBar'],
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('FallingLedgeBar', 'falling_ledge_bar.png')


# TODO: Make 'Filled Arrow' preview; Consider if it would be worth it to preview the formation repeats
class SpriteImage_CheepFormation(SLib.SpriteImage_Static):  # 247
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = True

        # Create auxes
        for i in range(16):
            self.aux.append(SLib.AuxiliaryImage(parent, 26, 24))
            self.aux[i].image = ImageCache['CheepRedLeft']
            self.aux[i].setIsBehindSprite(False)
            self.aux[i].hover = False

    @staticmethod
    def loadImages():
        if 'CheepRedLeft' in ImageCache: return
        ImageCache['CheepRedLeft'] = SLib.GetImg('cheep_red.png')
        ImageCache['CheepRedRight'] = QtGui.QPixmap.fromImage(SLib.GetImg('cheep_red.png', True).mirrored(True, False))

    def dataChanged(self):
        isLeft = (self.parent.spritedata[4] >> 4) & 0x1
        cheepNum = self.parent.spritedata[4] & 0xF
        doStretch = self.parent.spritedata[3] & 0x1
        formation = self.parent.spritedata[5] & 0xF
        if formation > 4:
            formation = 0

        # Setup stuff
        for i, aux in enumerate(self.aux):
            dirs = ['CheepRedRight', 'CheepRedLeft']
            aux.image = ImageCache[dirs[isLeft]]
            aux.alpha = 1.0 if i <= cheepNum else 0.0

        if formation == 0: # Arrow
            positions = [
                0,
                32, -32,
                64, -64,
                96, -96,
                128, -128,
                160, -160,
                192, -192,
                224, -224,
                256, -256
            ]

            for i, aux in enumerate(self.aux):
                yAdj = 0.75 if doStretch else 0.5
                xAdj = 1 if isLeft else -1
                aux.setPos(abs(positions[i])*1.5 * xAdj, -positions[i]*1.5 * yAdj)
        elif formation == 1: # Filled Arrow
            for aux in self.aux:
                aux.alpha = 0.0
        else: # Vertical, Diagonals
            for i, aux in enumerate(self.aux):
                xAdj = 1 if isLeft else -1
                yAdj = 0.75 if doStretch else 1
                yVal = (i * 32) * 1.5
                xVal = 0 if formation == 2 else yVal

                if formation == 3: # Upwards Diagonal
                    yAdj *= -1
                aux.setPos(xVal*xAdj, yVal*yAdj)

        super().dataChanged()


class SpriteImage_EventDeactivBlock(SLib.SpriteImage_Static):  # 252
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.image = SLib.GetTile(49)  # ? block


class SpriteImage_WaterPiranha(SLib.SpriteImage_Static):  # 263
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['WaterPiranhaBody'],
            (-4 / 1.5, -30),
        )

        # Highest point
        self.aux.append(SLib.AuxiliaryImage(parent, 38, 30))
        self.aux[0].image = ImageCache['WaterPiranhaBall']
        self.aux[0].setPos(2, -170)
        self.aux[0].hover = True

        # Lowest point
        self.aux.append(SLib.AuxiliaryImage(parent, 38, 30))
        self.aux[1].image = ImageCache['WaterPiranhaBall']
        self.aux[1].setPos(2, -24)
        self.aux[1].alpha = 0.5
        self.aux[1].hover = True

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('WaterPiranhaBody', 'water_piranha_body.png')
        SLib.loadIfNotInImageCache('WaterPiranhaBall', 'water_piranha_ball.png')


class SpriteImage_WalkingPiranha(SLib.SpriteImage_Static):  # 264
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['WalkPiranha'],
            (-4 / 1.5, -50),
        )
        self.aux.append(SLib.AuxiliaryTrackObject(parent, self.width, 16, SLib.AuxiliaryTrackObject.Horizontal))
        self.aux.append(SLib.AuxiliaryTrackObject(parent, self.width, 16, SLib.AuxiliaryTrackObject.Horizontal))

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('WalkPiranha', 'walk_piranha.png')

    def dataChanged(self):
        distance = self.parent.spritedata[5] & 0xF
        sideLen = (distance + 2) * 16

        self.aux[0].setPos(6 / 1.5, 112 / 1.5)
        self.aux[0].setSize(sideLen, 16)

        self.aux[1].setPos(-(sideLen * 1.5) + (42 / 1.5), 112 / 1.5)
        self.aux[1].setSize(sideLen, 16)

        self.aux[0].update()
        self.aux[1].update()
        super().dataChanged()


class SpriteImage_Parabomb(SLib.SpriteImage_Static):  # 269
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Parabomb'],
            (-2, -16),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Parabomb', 'parabomb.png')


class SpriteImage_IceBro(SLib.SpriteImage_Static):  # 272
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['IceBro'],
            (-5, -23),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('IceBro', 'icebro.png')


class SpriteImage_FiveEnemyRaft(SLib.SpriteImage_Static):  # 275
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['FiveEnemyRaft'],
            (0, -8),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('FiveEnemyRaft', '5_enemy_max_raft.png')


class SpriteImage_RollingBarrel(SLib.SpriteImage_Static):  # 288
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['RollingBarrel'],
            (2 / 1.5, -14 / 1.5),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('RollingBarrel', 'barrel_rolling.png')


class SpriteImage_IceCube(SLib.SpriteImage_Static):  # 294
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['IceCube'],
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('IceCube', 'ice_cube.png')


class SpriteImage_MegaIcicle(SLib.SpriteImage_Static):  # 311
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['MegaIcicle'],
            (-24, -3),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('MegaIcicle', 'mega_icicle.png')


class SpriteImage_Bolt(SLib.SpriteImage_Static):  # 315
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Bolt'],
            (2 / 1.5, 0),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Bolt', 'bolt.png')


class SpriteImage_GhostHouseStand(SLib.SpriteImage_Static):  # 325
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['GhostHouseStand'],
            (8, -16),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('GhostHouseStand', 'ghost_house_stand.png')


class SpriteImage_LinePlatformBolt(SLib.SpriteImage_Static):  # 327
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
        )

        self.dimensions = (0, -16, 112, 32)

    @staticmethod
    def loadImages():
        if 'LinePlatformBoltLeft' in ImageCache:
            return

        ImageCache['LinePlatformBoltLeft'] = SLib.GetImg('line_platform_with_bolt_left.png')
        ImageCache['LinePlatformBoltCenter'] = SLib.GetImg('line_platform_with_bolt_center.png')
        ImageCache['LinePlatformBoltRight'] = SLib.GetImg('line_platform_with_bolt_right.png')
        SLib.loadIfNotInImageCache('Bolt', 'bolt.png')

    def dataChanged(self):
        pass

    def paint(self, painter):
        super().paint(painter)

        painter.drawPixmap(62, 0, ImageCache['Bolt'])
        painter.drawPixmap(0, 24, ImageCache['LinePlatformBoltLeft'])
        painter.drawTiledPixmap(24, 24, 120, 24, ImageCache['LinePlatformBoltCenter'])
        painter.drawPixmap(144, 24, ImageCache['LinePlatformBoltRight'])


class SpriteImage_PlayerBlockPlatform(SLib.SpriteImage_Static):  # 333
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['PlayerBlockPlatform'],
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('PlayerBlockPlatform', 'player_block_platform.png')


class SpriteImage_CheepSchool(SLib.SpriteImage_Static):  # 335
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spritebox.shown = True

        # Make 4 auxiliaries for our formation Cheeps
        self.aux.append(SLib.AuxiliaryImage(parent, 26, 24))
        self.aux.append(SLib.AuxiliaryImage(parent, 26, 24))
        self.aux.append(SLib.AuxiliaryImage(parent, 26, 24))
        self.aux.append(SLib.AuxiliaryImage(parent, 26, 24))

    @staticmethod
    def loadImages():
        if 'CheepRedLeft' in ImageCache: return
        ImageCache['CheepRedLeft'] = SLib.GetImg('cheep_red.png')

    def dataChanged(self):
        formation = self.parent.spritedata[4] & 0xF
        shape = self.parent.spritedata[5] & 0xF
        noPreview = formation == 0 or formation > 3

        for aux in self.aux:
            aux.image = ImageCache['CheepRedLeft']
            aux.setIsBehindSprite(False)
            aux.hover = False
            # Hide them if its random or an invalid ID
            aux.alpha = 0.0 if noPreview else 1.0
        if noPreview: return

        if shape > 2:
            shape = 2

        positions = [
        ( # Shape 0
            # Aux 0   # Aux 1   # Aux 2   # Aux 3
            (), # Dummy space for random option
            ((16, 36), (32, 8), (28, 64), (48, 32)),
            ((16, 8), (32, 36), (48, 4), (64, 39)),
            ((16, 36), (32, 8), (48, 40), (64, 12)),
        ), ( # Shape 1
            (),
            ((8, 20), (36, 8), (64, 18), (92, 3)),
            ((8, 18), (36, 4), (64, 8), (92, 20)),
            ((8, 5), (36, 20), (64, 18), (92, 8)),
        ), ( # Shape 2
            (),
            ((8, 8), (24, 36), (5, 64), (20, 92)),
            ((20, 8), (13, 36), (8, 64), (24, 92)),
            ((8, 8), (28, 36), (24, 64), (4, 92)),
        )]

        for idx, aux in enumerate(self.aux):
            aux.setPos((positions[shape][formation][idx][0]-8) * 1.5, (positions[shape][formation][idx][1]-8) * 1.5)
        super().dataChanged()


class SpriteImage_WendyKoopa(SLib.SpriteImage_Static):  # 336
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['WendyKoopa'],
            (-23, -23),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('WendyKoopa', 'Wendy_Koopa.png')


class SpriteImage_IggyKoopa(SLib.SpriteImage_Static):  # 337
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['IggyKoopa'],
            (-17, -46),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('IggyKoopa', 'Iggy_Koopa.png')


class SpriteImage_LemmyKoopa(SLib.SpriteImage_Static):  # 340
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['LemmyKoopa'],
            (-16, -53),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('LemmyKoopa', 'Lemmy_Koopa.png')


class SpriteImage_MortonKoopa(SLib.SpriteImage_Static):  # 344
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['MortonKoopa'],
            (-17, -34),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('MortonKoopa', 'Morton_Koopa.png')


class SpriteImage_ChainHolder(SLib.SpriteImage_Static):  # 345
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['ChainHolder'],
            (0, -12)
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('ChainHolder', 'chain_holder.png')


class SpriteImage_RoyKoopa(SLib.SpriteImage_Static):  # 347
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['RoyKoopa'],
            (-27, -24)
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('RoyKoopa', 'Roy_Koopa.png')


class SpriteImage_LudwigVonKoopa(SLib.SpriteImage_Static):  # 348
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['LudwigVonKoopa'],
            (-20, -30),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('LudwigVonKoopa', 'Ludwig_Von_Koopa.png')


class SpriteImage_RockyWrench(SLib.SpriteImage_Static):  # 352
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['RockyWrench'],
            (-2, -41),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('RockyWrench', 'rocky_wrench.png')


class SpriteImage_CubeKinokoLine(SLib.SpriteImage_Static):  # 367
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['CubeKinokoP'],
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('CubeKinokoP', 'cube_kinoko_p.png')


class SpriteImage_CloudBlock(SLib.SpriteImage_Static):  # 370
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['CloudBlock'],
            (-4, -8),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('CloudBlock', 'cloud_block.png')


class SpriteImage_PowBlock(SLib.SpriteImage_Static):  # 386
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['POW']
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('POW', 'pow.png')


class SpriteImage_Barrel(SLib.SpriteImage_Static):  # 388
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Barrel'],
            (-4, -8),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Barrel', 'barrel.png')


class SpriteImage_PropellerBlock(SLib.SpriteImage_Static):  # 393
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['PropellerBlock'],
            (-3, -6),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('PropellerBlock', 'propeller_block.png')


class SpriteImage_LemmyBall(SLib.SpriteImage_Static):  # 394
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['LemmyBall'],
            (-6, 0),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('LemmyBall', 'lemmyball.png')


class SpriteImage_WendyRing(SLib.SpriteImage_Static):  # 413
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['WendyRing'],
            (-4, 4),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('WendyRing', 'wendy_ring.png')


class SpriteImage_BetaLarryKoopa(SLib.SpriteImage_Static):  # 415
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['LarryKoopaBeta'],
            (-13, -22.5),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('LarryKoopaBeta', 'Larry_Koopa_Unused.png')


class SpriteImage_InvisibleOneUp(SLib.SpriteImage_Static):  # 416
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['InvisibleOneUp'],
            (3, 5),
        )
        self.alpha = 0.65

    @staticmethod
    def loadImages():
        if 'InvisibleOneUp' in ImageCache: return
        ImageCache['InvisibleOneUp'] = ImageCache['BlockContents'][11].scaled(16, 16)


class SpriteImage_SpinjumpCoin(SLib.SpriteImage_Static):  # 417
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['SpecialCoin'],
        )
        self.alpha = 0.55


class SpriteImage_BanzaiGen(SLib.SpriteImage_Static):  # 418
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['BanzaiGen'],
            (-56 / 1.5, -16),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('BanzaiGen', 'banzai_bill_gen.png')


class SpriteImage_Bowser(SLib.SpriteImage_Static):  # 419
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Bowser'],
            (-35, -70),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Bowser', 'bowser.png')


class SpriteImage_UnusedGhostDoor(SLib.SpriteImage_Static):  # 421
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['GhostDoorU'],
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('GhostDoorU', 'ghost_door.png')


class SpriteImage_Jellybeam(SLib.SpriteImage_Static):  # 425
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Jellybeam'],
            (-13 / 1.5, -11 / 1,5),
        )

        self.aux.append(SLib.AuxiliaryTrackObject(parent, 16, 16, SLib.AuxiliaryTrackObject.Vertical))

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Jellybeam', 'jellybeam.png')

    def dataChanged(self):
        distance = self.parent.spritedata[5] & 3
        self.aux[0].setSize(16, (distance * 32) + 118)
        self.aux[0].setPos(self.width * 0.75 - 12, self.height * 0.75 - 16)

        super().dataChanged()


class SpriteImage_Kamek(SLib.SpriteImage_Static):  # 427
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Kamek'],
            (-19, -15),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Kamek', 'kamek.png')


class SpriteImage_MGPanel(SLib.SpriteImage_Static):  # 428
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['MGPanel'],
            (-2, -6),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('MGPanel', 'minigame_flip_panel.png')


class SpriteImage_Toad(SLib.SpriteImage_Static):  # 432
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Toad'],
            (8, -16),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Toad', 'toad.png')


class SpriteImage_CagePeachFake(SLib.SpriteImage_Static):  # 439
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['CagePeachFake'],
            (-18, -106),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('CagePeachFake', 'cage_peach_fake.png')


class SpriteImage_ReplayBlock(SLib.SpriteImage_Static):  # 443
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['ReplayBlock'],
            (-8, -16),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('ReplayBlock', 'replay_block.png')


class SpriteImage_PreSwingingVine(SLib.SpriteImage_Static):  # 444
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['PreSwingVine'],
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('PreSwingVine', 'swing_vine.png')


class SpriteImage_CagePeachReal(SLib.SpriteImage_Static):  # 445
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['CagePeachReal'],
            (-18, -106),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('CagePeachReal', 'cage_peach_real.png')


class SpriteImage_MetalBar(SLib.SpriteImage_Static):  # 448
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['MetalBar'],
            (0, -32),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('MetalBar', 'metal_bar.png')


class SpriteImage_ScaredyRatDespawner(SLib.SpriteImage_Static):  # 451
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['ScaredyRatDespawner'],
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('ScaredyRatDespawner', 'scaredy_rat_despawner.png')


class SpriteImage_BowserDoor(SLib.SpriteImage_Static):  # 452
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['BowserDoor'],
            (-53, -130),
        )
        self.aux.append(SLib.AuxiliaryRectOutline(parent, 24, 24))
        self.aux[0].setIsBehindSprite(False)
        self.aux[0].setPos(91, 243)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('BowserDoor', 'bowser_door.png')


class SpriteImage_LavaIronBlock(SLib.SpriteImage_Static):  # 466
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['LavaIronBlock'],
            (-1, -1),
        )

        self.aux.append(SLib.AuxiliaryTrackObject(parent, 16, 16, SLib.AuxiliaryTrackObject.Horizontal))

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('LavaIronBlock', 'lava_iron_block.png')

    def dataChanged(self):
        direction = self.parent.spritedata[2] & 3
        distance = (self.parent.spritedata[4] & 0xF0) >> 4

        if direction <= 1: # horizontal
            self.aux[0].direction = 1
            self.aux[0].setSize((distance * 16) + 16, 16)
        else: # vertical
            self.aux[0].direction = 2
            self.aux[0].setSize(16, (distance * 16) + 16)

        if direction == 0: # right
            self.aux[0].setPos(self.width + 48, self.height / 2)
        elif direction == 1: # left
            self.aux[0].setPos((-distance * 24) + 2, self.height / 2)
        elif direction == 2: # up
            self.aux[0].setPos((self.width * 0.75) - 12, (-distance * 24))
        else: # down
            self.aux[0].setPos((self.width * 0.75) - 12, self.height)

        super().dataChanged()


class SpriteImage_MovingGemBlock(SLib.SpriteImage_Static):  # 467
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['MovingGemBlock'],
        )

        self.aux.append(SLib.AuxiliaryTrackObject(parent, 16, 16, SLib.AuxiliaryTrackObject.Vertical))

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('MovingGemBlock', 'moving_gem_block.png')

    def dataChanged(self):
        direction = self.parent.spritedata[2] & 1
        distance = (self.parent.spritedata[4] & 0xF0) >> 4

        self.aux[0].setSize(16, (distance * 16) + 16)
        if direction == 0: # up
            self.aux[0].setPos(self.width / 2, -distance * 24)
        else: # down
            self.aux[0].setPos(self.width / 2, self.height - 8)

        super().dataChanged()


class SpriteImage_BoltPlatformWire(SLib.SpriteImage_Static):  # 470
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['BoltPlatformWire'],
            (5, -240),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('BoltPlatformWire', 'bolt_platform_wire.png')


class SpriteImage_PotPlatform(SLib.SpriteImage_Static):  # 471
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['PotPlatform'],
            (-9, -3),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('PotPlatform', 'pot_platform.png')


class SpriteImage_FlyingWrench(SLib.SpriteImage_Static):  # 476
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['Wrench'],
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Wrench', 'wrench.png')


class SpriteImage_SuperGuideBlock(SLib.SpriteImage_Static):  # 477
    def __init__(self, parent):
        super().__init__(
            parent,
            1.5,
            ImageCache['SuperGuide'],
            (-4, -4),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('SuperGuide', 'superguide_block.png')
