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


def LoadBasics():
    """
    Loads basic images used in NSMBW
    """
    # Load some coins, because coins are in almost every Mario level ever
    ImageCache['Coin'] = SLib.GetImg('coin.png')
    ImageCache['SpecialCoin'] = SLib.GetImg('special_coin.png')
    ImageCache['PCoin'] = SLib.GetImg('p_coin.png')
    ImageCache['RedCoin'] = SLib.GetImg('redcoin.png')
    ImageCache['StarCoin'] = SLib.GetImg('starcoin.png')

    # Load block contents
    ContentImage = SLib.GetImg('block_contents.png')
    Blocks = []
    count = ContentImage.width() // 24
    for i in range(count):
        Blocks.append(ContentImage.copy(i * 24, 0, 24, 24))
    ImageCache['BlockContents'] = Blocks

    # Load the blocks
    BlockImage = SLib.GetImg('blocks.png')
    Blocks = []
    count = BlockImage.width() // 24
    for i in range(count):
        Blocks.append(BlockImage.copy(i * 24, 0, 24, 24))
    ImageCache['Blocks'] = Blocks

    # Load the characters
    for num in range(4):
        for direction in 'lr':
            ImageCache['Character%d%s' % (num + 1, direction.upper())] = \
                SLib.GetImg('character_%d_%s.png' % (num + 1, direction))

    # Load vines, because these are used by entrances
    SLib.loadIfNotInImageCache('VineTop', 'vine_top.png')
    SLib.loadIfNotInImageCache('VineMid', 'vine_mid.png')
    SLib.loadIfNotInImageCache('VineBtm', 'vine_btm.png')


# ---- Low-Level Classes ----


class SpriteImage_WoodenPlatform(SLib.SpriteImage):  # 23, 31, 50, 103, 106, 122
    def __init__(self, parent, scale=1.5):
        super().__init__(parent, scale)
        self.spritebox.shown = False

    @staticmethod
    def loadImages():
        # Load the two batches separately because another sprite only
        # loads the first three.
        if 'WoodenPlatformL' not in ImageCache:
            ImageCache['WoodenPlatformL'] = SLib.GetImg('wood_platform_left.png')
            ImageCache['WoodenPlatformM'] = SLib.GetImg('wood_platform_middle.png')
            ImageCache['WoodenPlatformR'] = SLib.GetImg('wood_platform_right.png')
        if 'StonePlatformL' not in ImageCache:
            ImageCache['StonePlatformL'] = SLib.GetImg('stone_platform_left.png')
            ImageCache['StonePlatformM'] = SLib.GetImg('stone_platform_middle.png')
            ImageCache['StonePlatformR'] = SLib.GetImg('stone_platform_right.png')
            ImageCache['BonePlatformL'] = SLib.GetImg('bone_platform_left.png')
            ImageCache['BonePlatformM'] = SLib.GetImg('bone_platform_middle.png')
            ImageCache['BonePlatformR'] = SLib.GetImg('bone_platform_right.png')

    def paint(self, painter):
        super().paint(painter)

        if self.color == 0:
            color = 'Wooden'
        elif self.color == 1:
            color = 'Stone'
        elif self.color == 2:
            color = 'Bone'

        if self.width > 32:
            painter.drawTiledPixmap(24, 0, int((self.width * 1.5) - 48), int(self.height * 1.5), ImageCache[color + 'PlatformM'])

        if self.width == 24:
            # replicate glitch effect foRotControlled by sprite 50
            painter.drawPixmap(0, 0, ImageCache[color + 'PlatformR'])
            painter.drawPixmap(8, 0, ImageCache[color + 'PlatformL'])
        else:
            # normal rendering
            painter.drawPixmap(int((self.width - 16) * 1.5), 0, ImageCache[color + 'PlatformR'])
            painter.drawPixmap(0, 0, ImageCache[color + 'PlatformL'])


class SpriteImage_DSStoneBlock(SLib.SpriteImage):  # 27, 28
    def __init__(self, parent, scale=1.5):
        super().__init__(parent, scale)
        self.spritebox.shown = False

    @staticmethod
    def loadImages():
        if 'DSBlockTopLeft' in ImageCache: return
        ImageCache['DSBlockTopLeft'] = SLib.GetImg('dsblock_topleft.png')
        ImageCache['DSBlockTop'] = SLib.GetImg('dsblock_top.png')
        ImageCache['DSBlockTopRight'] = SLib.GetImg('dsblock_topright.png')
        ImageCache['DSBlockLeft'] = SLib.GetImg('dsblock_left.png')
        ImageCache['DSBlockRight'] = SLib.GetImg('dsblock_right.png')
        ImageCache['DSBlockBottomLeft'] = SLib.GetImg('dsblock_bottomleft.png')
        ImageCache['DSBlockBottom'] = SLib.GetImg('dsblock_bottom.png')
        ImageCache['DSBlockBottomRight'] = SLib.GetImg('dsblock_bottomright.png')

    def dataChanged(self):
        super().dataChanged()

        # get size
        width = self.parent.spritedata[5] & 7
        if width == 0: width = 1
        byte5 = self.parent.spritedata[4]
        self.width = (16 + (width << 4))
        self.height = (16 << ((byte5 & 0x30) >> 4)) - 4

    def paint(self, painter):
        super().paint(painter)

        middle_width = int((self.width - 32) * 1.5)
        middle_height = int((self.height * 1.5) - 16)
        bottom_y = int((self.height * 1.5) - 8)
        right_x = int((self.width - 16) * 1.5)

        painter.drawPixmap(0, 0, ImageCache['DSBlockTopLeft'])
        painter.drawTiledPixmap(24, 0, middle_width, 8, ImageCache['DSBlockTop'])
        painter.drawPixmap(right_x, 0, ImageCache['DSBlockTopRight'])

        painter.drawTiledPixmap(0, 8, 24, middle_height, ImageCache['DSBlockLeft'])
        painter.drawTiledPixmap(right_x, 8, 24, middle_height, ImageCache['DSBlockRight'])

        painter.drawPixmap(0, bottom_y, ImageCache['DSBlockBottomLeft'])
        painter.drawTiledPixmap(24, bottom_y, middle_width, 8, ImageCache['DSBlockBottom'])
        painter.drawPixmap(right_x, bottom_y, ImageCache['DSBlockBottomRight'])


class SpriteImage_StarCoin(SLib.SpriteImage_Static):  # 32, 155, 389
    def __init__(self, parent, scale=1.5):
        super().__init__(
            parent,
            scale,
            ImageCache['StarCoin'],
            (0, 3),
        )


class SpriteImage_OldStoneBlock(SLib.SpriteImage):  # 30, 81, 82, 83, 84, 85, 86
    def __init__(self, parent, scale=1.5):
        super().__init__(parent, scale)
        self.spritebox.shown = False

        self.aux.append(SLib.AuxiliaryTrackObject(parent, 16, 16, SLib.AuxiliaryTrackObject.Horizontal))
        self.spikesL = False
        self.spikesR = False
        self.spikesT = False
        self.spikesB = False

        self.hasMovementAux = True

    @staticmethod
    def loadImages():
        if 'OldStoneTL' in ImageCache: return
        ImageCache['OldStoneTL'] = SLib.GetImg('oldstone_tl.png')
        ImageCache['OldStoneT'] = SLib.GetImg('oldstone_t.png')
        ImageCache['OldStoneTR'] = SLib.GetImg('oldstone_tr.png')
        ImageCache['OldStoneL'] = SLib.GetImg('oldstone_l.png')
        ImageCache['OldStoneM'] = SLib.GetImg('oldstone_m.png')
        ImageCache['OldStoneR'] = SLib.GetImg('oldstone_r.png')
        ImageCache['OldStoneBL'] = SLib.GetImg('oldstone_bl.png')
        ImageCache['OldStoneB'] = SLib.GetImg('oldstone_b.png')
        ImageCache['OldStoneBR'] = SLib.GetImg('oldstone_br.png')
        ImageCache['SpikeU'] = SLib.GetImg('spike_up.png')
        ImageCache['SpikeL'] = SLib.GetImg('spike_left.png')
        ImageCache['SpikeR'] = SLib.GetImg('spike_right.png')
        ImageCache['SpikeD'] = SLib.GetImg('spike_down.png')

    def dataChanged(self):
        super().dataChanged()

        size = self.parent.spritedata[5]
        height = (size & 0xF0) >> 4
        width = size & 0xF
        if self.parent.type == 30:
            height = 1 if height == 0 else height
            width = 1 if width == 0 else width
        self.width = width * 16 + 16
        self.height = height * 16 + 16

        if self.spikesL:  # left spikes
            self.xOffset = -16
            self.width += 16
        if self.spikesT:  # top spikes
            self.yOffset = -16
            self.height += 16
        if self.spikesR:  # right spikes
            self.width += 16
        if self.spikesB:  # bottom spikes
            self.height += 16

        # now set up the track
        if self.hasMovementAux:
            direction = self.parent.spritedata[2] & 3
            distance = (self.parent.spritedata[4] & 0xF0) >> 4
            if direction > 3: direction = 0

            if direction <= 1:  # horizontal
                self.aux[0].direction = 1
                self.aux[0].setSize(self.width + (distance * 16), self.height)
            else:  # vertical
                self.aux[0].direction = 2
                self.aux[0].setSize(self.width, self.height + (distance * 16))

            if direction == 0 or direction == 3:  # right, down
                self.aux[0].setPos(0, 0)
            elif direction == 1:  # left
                self.aux[0].setPos(-distance * 24, 0)
            elif direction == 2:  # up
                self.aux[0].setPos(0, -distance * 24)
        else:
            self.aux[0].setSize(0, 0)

    def paint(self, painter):
        super().paint(painter)

        blockX = 0
        blockY = 0
        type = self.parent.type
        width = self.width * 1.5
        height = self.height * 1.5

        if self.spikesL:  # left spikes
            painter.drawTiledPixmap(0, 0, 24, int(height), ImageCache['SpikeL'])
            blockX = 24
            width -= 24
        if self.spikesT:  # top spikes
            painter.drawTiledPixmap(0, 0, int(width), 24, ImageCache['SpikeU'])
            blockY = 24
            height -= 24
        if self.spikesR:  # right spikes
            painter.drawTiledPixmap(int(blockX + width - 24), 0, 24, int(height), ImageCache['SpikeR'])
            width -= 24
        if self.spikesB:  # bottom spikes
            painter.drawTiledPixmap(0, int(blockY + height - 24), int(width), 24, ImageCache['SpikeD'])
            height -= 24

        column2x = blockX + 24
        column3x = int(blockX + width - 24)
        row2y = blockY + 24
        row3y = int(blockY + height - 24)

        painter.drawPixmap(blockX, blockY, ImageCache['OldStoneTL'])
        painter.drawTiledPixmap(column2x, blockY, int(width - 48), 24, ImageCache['OldStoneT'])
        painter.drawPixmap(column3x, blockY, ImageCache['OldStoneTR'])

        painter.drawTiledPixmap(blockX, row2y, 24, int(height - 48), ImageCache['OldStoneL'])
        painter.drawTiledPixmap(column2x, row2y, int(width - 48), int(height - 48), ImageCache['OldStoneM'])
        painter.drawTiledPixmap(column3x, row2y, 24, int(height - 48), ImageCache['OldStoneR'])

        painter.drawPixmap(blockX, row3y, ImageCache['OldStoneBL'])
        painter.drawTiledPixmap(column2x, row3y, int(width - 48), 24, ImageCache['OldStoneB'])
        painter.drawPixmap(column3x, row3y, ImageCache['OldStoneBR'])


class SpriteImage_LiquidOrFog(SLib.SpriteImage):  # 53, 64, 138, 139, 216, 358, 374, 435
    def __init__(self, parent):
        super().__init__(parent)

        self.crest = None
        self.mid = None
        self.rise = None
        self.riseCrestless = None

        self.top = 0

        self.drawCrest = False
        self.risingHeight = 0

        self.locId = 0
        self.findZone()

    def findZone(self):
        self.zoneId = SLib.MapPositionToZoneID(globals_.Area.zones, self.parent.objx, self.parent.objy, True)

    def positionChanged(self):
        self.findZone()
        self.parent.scene().update()
        super().positionChanged()

    def dataChanged(self):
        self.parent.scene().update()
        super().dataChanged()

    def paintZone(self):
        return self.locId == 0 and self.zoneId != -1

    def realViewZone(self, painter, zoneRect):
        """
        Real view zone painter for liquids/fog
        """
        drawRise = self.risingHeight != 0
        drawCrest = self.drawCrest

        crest_rect = QtCore.QRectF()
        rise_rect = QtCore.QRectF()

        # Create the fill_rect (the area where the liquid or fog should be)
        fill_rect = QtCore.QRectF(zoneRect)
        fill_rect.setTop(self.top * 1.5)

        # Translate the fill_rect to be relative to the zone
        fill_rect.translate(-zoneRect.topLeft())

        if fill_rect.isEmpty():
            # the sprite is below the zone; don't draw anything
            return

        if fill_rect.top() <= 0:
            drawCrest = False  # off the top of the zone; no crest

        # Determine where to put the rise image
        if drawRise:
            rise_rect = fill_rect.translated(0, -24 * self.risingHeight)

            # Determine what image to draw for the rise indicator
            rise_img = self.rise
            if not drawCrest or rise_rect.top() <= 0:
                # close enough to the top zone border
                rise_rect.setTop(0)
                rise_img = self.riseCrestless

            # Set the correct height
            rise_rect.setHeight(rise_img.height())

        # If all that fits in the zone is some of the crest, determine how much
        if drawCrest:
            crest_rect = QtCore.QRectF(fill_rect)
            crest_rect.setHeight(self.crest.height())

            # Adjust the fill rect
            fill_rect.setTop(crest_rect.bottom())

        # Draw everything
        if drawCrest:
            painter.drawTiledPixmap(crest_rect, self.crest)

        painter.drawTiledPixmap(fill_rect, self.mid)

        if drawRise:
            painter.drawTiledPixmap(rise_rect, rise_img)

    def realViewLocation(self, painter, location_rect):
        """
        Real view location painter for liquids/fog
        """
        if self.paintZone():
            return

        for zone in globals_.Area.zones:
            if zone.id == self.zoneId:
                break
        else:
            return

        # Only draw in the intersection of the location and the zone. The
        # intersection needs to be translated, because draw offsets are relative
        # to the location.
        draw_rect = location_rect & zone.mapRectToScene(zone.DrawRect)
        draw_rect.translate(QtCore.QPointF(1, 1) - location_rect.topLeft())

        if draw_rect.isEmpty():
            return

        x, y, width, height = draw_rect.getRect()

        drawCrest = False
        crestHeight = 0

        if self.drawCrest:
            crestHeight = self.crest.height()
            drawCrest = y < crestHeight

        if drawCrest:
            if (crestHeight - y) >= height:
                painter.drawTiledPixmap(draw_rect, self.crest, draw_rect.topLeft())
            else:
                draw_rect.setBottom(crestHeight - y)
                painter.drawTiledPixmap(draw_rect, self.crest, draw_rect.topLeft())
                draw_rect.setTop(crestHeight - y)
                draw_rect.setHeight(height - crestHeight + y)
                painter.drawTiledPixmap(draw_rect, self.mid, draw_rect.topLeft())
        else:
            painter.drawTiledPixmap(draw_rect, self.mid, draw_rect.topLeft())


class SpriteImage_UnusedBlockPlatform(SLib.SpriteImage):  # 97, 107, 132, 160
    def __init__(self, parent, scale=1.5):
        super().__init__(parent, scale)
        self.spritebox.shown = False

        self.size = (48, 48)
        self.isDark = False
        self.drawPlatformImage = True

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('UnusedPlatform', 'unused_platform.png')
        SLib.loadIfNotInImageCache('UnusedPlatformDark', 'unused_platform_dark.png')

    def paint(self, painter):
        super().paint(painter)
        if not self.drawPlatformImage: return

        pixmap = ImageCache['UnusedPlatformDark'] if self.isDark else ImageCache['UnusedPlatform']
        pixmap = pixmap.scaled(
            int(self.width * 1.5), int(self.height * 1.5),
            Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(0, 0, pixmap)


class SpriteImage_Amp(SLib.SpriteImage_Static):  # 104, 108
    def __init__(self, parent, scale=1.5):
        super().__init__(
            parent,
            scale,
            ImageCache['Amp'],
            (-8, -8),
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Amp', 'amp.png')


class SpriteImage_SpikedStake(SLib.SpriteImage):  # 137, 140, 141, 142
    def __init__(self, parent, scale=1.5):
        super().__init__(parent, scale)
        self.spritebox.shown = False

        self.HorzSpikeLength = ((36 * 16) + 41) / 1.5
        self.VertSpikeLength = ((36 * 16) + 39) / 1.5
        # (16 mid sections + an end section), accounting for image/sprite size difference
        self.dir = 'down'

    @staticmethod
    def loadImages():
        if 'StakeM0up' not in ImageCache:
            for dir in ['up', 'down', 'left', 'right']:
                ImageCache['StakeM0' + dir] = SLib.GetImg('stake_%s_m_0.png' % dir)
                ImageCache['StakeM1' + dir] = SLib.GetImg('stake_%s_m_1.png' % dir)
                ImageCache['StakeE0' + dir] = SLib.GetImg('stake_%s_e_0.png' % dir)
                ImageCache['StakeE1' + dir] = SLib.GetImg('stake_%s_e_1.png' % dir)

    def dataChanged(self):
        super().dataChanged()

        rawdistance = self.parent.spritedata[3] >> 4
        distance = (
            (16, 7, 14, 10, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 16)
        )[rawdistance]
        distance += 1  # In order to hide one side of the track behind the image.
        speed = (self.parent.spritedata[2] >> 4) & 3

        L = 615
        W = 617  # 16 mid sections + an end section

        if speed == 3:
            self.aux[0].setSize(0, 0)
        else:
            if self.dir == 'up':
                self.aux[0].setPos(36, 24 - (distance * 24))
                self.aux[0].setSize(16, distance * 16)
            elif self.dir == 'down':
                self.aux[0].setPos(36, L - 24)
                self.aux[0].setSize(16, distance * 16)
            elif self.dir == 'left':
                self.aux[0].setPos(24 - (distance * 24), 36)
                self.aux[0].setSize(distance * 16, 16)
            else:
                self.aux[0].setPos(W - 24, 36)
                self.aux[0].setSize(distance * 16, 16)

    def paint(self, painter):
        super().paint(painter)

        color = self.parent.spritedata[3] & 15
        if color == 2 or color == 3 or color == 7:
            mid = ImageCache['StakeM1' + self.dir]
            end = ImageCache['StakeE1' + self.dir]
        else:
            mid = ImageCache['StakeM0' + self.dir]
            end = ImageCache['StakeE0' + self.dir]

        tiles = 16
        tilesize = 36
        endsizeV = 39
        endsizeH = 41
        widthV = 98
        widthH = 99

        if self.dir == 'up':
            painter.drawPixmap(0, 0, end)
            painter.drawTiledPixmap(0, endsizeV, widthV, tilesize * tiles, mid)
        elif self.dir == 'down':
            painter.drawTiledPixmap(0, 0, widthV, tilesize * tiles, mid)
            painter.drawPixmap(0, int((self.height * 1.5) - endsizeV), end)
        elif self.dir == 'left':
            painter.drawPixmap(0, 0, end)
            painter.drawTiledPixmap(endsizeH, 0, tilesize * tiles, widthH, mid)
        elif self.dir == 'right':
            painter.drawTiledPixmap(0, 0, tilesize * tiles, widthH, mid)
            painter.drawPixmap(int((self.width * 1.5) - endsizeH), 0, end)


class SpriteImage_ScrewMushroom(SLib.SpriteImage):  # 172, 382
    def __init__(self, parent, scale=1.5):
        super().__init__(parent, scale)
        self.spritebox.shown = False

        self.hasBolt = False
        self.size = (122, 190)

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('Bolt', 'bolt.png')
        if 'ScrewShroomT' not in ImageCache:
            ImageCache['ScrewShroomT'] = SLib.GetImg('screw_shroom_top.png')
            ImageCache['ScrewShroomM'] = SLib.GetImg('screw_shroom_middle.png')
            ImageCache['ScrewShroomB'] = SLib.GetImg('screw_shroom_bottom.png')

    def dataChanged(self):
        super().dataChanged()

        # I wish I knew what this does
        SomeOffset = self.parent.spritedata[3]
        if SomeOffset == 0 or SomeOffset > 8: SomeOffset = 8

        self.height = 206 if self.hasBolt else 190
        self.yOffset = SomeOffset * -16
        if self.hasBolt:
            self.yOffset -= 16

    def paint(self, painter):
        super().paint(painter)

        y = 0
        if self.hasBolt:
            painter.drawPixmap(70, 0, ImageCache['Bolt'])
            y += 24
        painter.drawPixmap(0, y, ImageCache['ScrewShroomT'])
        painter.drawTiledPixmap(76, y + 93, 31, 172, ImageCache['ScrewShroomM'])
        painter.drawPixmap(76, y + 253, ImageCache['ScrewShroomB'])


class SpriteImage_Door(SLib.SpriteImage):  # 182, 259, 276, 277, 278
    def __init__(self, parent, scale=1.5):
        super().__init__(parent, scale)
        self.spritebox.shown = False

        self.doorName = 'Door'
        self.doorDimensions = (0, 0, 32, 48)
        self.entranceOffset = (0, 48)

        self.aux.append(SLib.AuxiliaryRectOutline(parent, 24, 24))
        self.aux[0].setIsBehindSprite(False)

    @staticmethod
    def loadImages():
        if 'DoorU' in ImageCache: return
        doors = {'Door': 'door', 'GhostDoor': 'ghost_door', 'TowerDoor': 'tower_door', 'CastleDoor': 'castle_door'}
        transform90 = QtGui.QTransform()
        transform180 = QtGui.QTransform()
        transform270 = QtGui.QTransform()
        transform90.rotate(90)
        transform180.rotate(180)
        transform270.rotate(270)

        for door, filename in doors.items():
            image = SLib.GetImg('%s.png' % filename, True)
            ImageCache[door + 'U'] = QtGui.QPixmap.fromImage(image)
            ImageCache[door + 'R'] = QtGui.QPixmap.fromImage(image.transformed(transform90))
            ImageCache[door + 'D'] = QtGui.QPixmap.fromImage(image.transformed(transform180))
            ImageCache[door + 'L'] = QtGui.QPixmap.fromImage(image.transformed(transform270))

    def dataChanged(self):
        super().dataChanged()

        rotstatus = self.parent.spritedata[4]
        if rotstatus & 1 == 0:
            direction = 0
        else:
            direction = (rotstatus & 0x30) >> 4

        if direction > 3: direction = 0
        doorName = self.doorName
        doorSize = self.doorDimensions
        if direction == 0:
            self.image = ImageCache[doorName + 'U']
            self.dimensions = doorSize
            paintEntrancePos = True
        elif direction == 1:
            self.image = ImageCache[doorName + 'L']
            self.dimensions = (
                (doorSize[2] / 2) + doorSize[0] - doorSize[3],
                doorSize[1] + (doorSize[3] - (doorSize[2] / 2)),
                doorSize[3],
                doorSize[2],
            )
            paintEntrancePos = False
        elif direction == 2:
            self.image = ImageCache[doorName + 'D']
            self.dimensions = (
                doorSize[0],
                doorSize[1] + doorSize[3],
                doorSize[2],
                doorSize[3],
            )
            paintEntrancePos = False
        elif direction == 3:
            self.image = ImageCache[doorName + 'R']
            self.dimensions = (
                doorSize[0] + (doorSize[2] / 2),
                doorSize[1] + (doorSize[3] - (doorSize[2] / 2)),
                doorSize[3],
                doorSize[2],
            )
            paintEntrancePos = False

        self.aux[0].setSize(
            *(
                (0, 0, 0, 0),
                (24, 24) + self.entranceOffset,
            )[1 if paintEntrancePos else 0]
        )

    def paint(self, painter):
        super().paint(painter)
        painter.setOpacity(self.alpha)
        painter.drawPixmap(0, 0, self.image)
        painter.setOpacity(1)


class SpriteImage_GiantBubble(SLib.SpriteImage):  # 205, 226
    def __init__(self, parent, scale=1.5):
        super().__init__(parent, scale)
        self.spritebox.shown = False
        self.parent.setZValue(24999)
        self.aux.append(SLib.AuxiliaryTrackObject(parent, 16, 16, SLib.AuxiliaryTrackObject.Horizontal))

    @staticmethod
    def loadImages():
        if 'GiantBubble0' in ImageCache: return
        for shape in range(3):
            ImageCache['GiantBubble%d' % shape] = SLib.GetImg('giant_bubble_%d.png' % shape)

    def dataChanged(self):
        super().dataChanged()

        self.shape = self.parent.spritedata[4] >> 4
        direction = self.parent.spritedata[5] & 15
        distance = (self.parent.spritedata[5] & 0xF0) >> 4

        if self.shape > 3:
            self.shape = 0

        self.size = (
            (122, 137),
            (76, 170),
            (160, 81)
        )[self.shape]

        self.xOffset = -(self.width / 2) + 8
        self.yOffset = -(self.height / 2) + 8

        if distance == 0:
            self.aux[0].setSize(0, 0)
        elif direction == 1:  # horizontal
            self.aux[0].direction = 1
            self.aux[0].setSize((distance * 32) + self.width, 16)
            self.aux[0].setPos((-distance * 24), (self.height * 0.75) - 12)
        else:  # vertical
            self.aux[0].direction = 2
            self.aux[0].setSize(16, (distance * 32) + self.height)
            self.aux[0].setPos((self.width * 0.75) - 12, (-distance * 24))

    def paint(self, painter):
        super().paint(painter)

        painter.drawPixmap(0, 0, ImageCache['GiantBubble%d' % self.shape])


class SpriteImage_Block(SLib.SpriteImage):  # 207, 208, 209, 221, 255, 256, 402, 403, 422, 423
    def __init__(self, parent, scale=1.5):
        super().__init__(parent, scale)
        self.spritebox.shown = False

        self.tilenum = 1315
        self.contentsNybble = 5
        self.contentsOverride = None
        self.eightIsMushroom = False
        self.twelveIsMushroom = False
        self.rotates = False

    def dataChanged(self):
        super().dataChanged()

        # SET CONTENTS
        # In the block_contents.png file:
        # 0 = Empty, 1 = Coin, 2 = Mushroom, 3 = Fire Flower, 4 = Propeller, 5 = Penguin Suit,
        # 6 = Mini Shroom, 7 = Star, 8 = Continuous Star, 9 = Yoshi Egg, 10 = 10 Coins,
        # 11 = 1-up, 12 = Vine, 13 = Spring, 14 = Shroom/Coin, 15 = Ice Flower, 16 = Toad, 17 = Hammer

        if self.contentsOverride is not None:
            contents = self.contentsOverride
        else:
            contents = self.parent.spritedata[self.contentsNybble] & 0xF

        if contents == 2:  # 1 and 2 are always fire flowers
            contents = 3

        if contents == 12 and self.twelveIsMushroom:
            contents = 2  # 12 is a mushroom on some types
        if contents == 8 and self.eightIsMushroom:
            contents = 2  # same as above, but for type 8

        self.image = ImageCache['BlockContents'][contents]

        # SET UP ROTATION
        if self.rotates:
            transform = QtGui.QTransform()
            transform.translate(12, 12)

            angle = (self.parent.spritedata[4] & 0xF0) >> 4
            leftTilt = self.parent.spritedata[3] & 1

            angle *= 45 / 16

            if leftTilt == 0:
                transform.rotate(angle)
            else:
                transform.rotate(360 - angle)

            transform.translate(-12, -12)
            self.parent.setTransform(transform)

    def paint(self, painter):
        super().paint(painter)

        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        if self.tilenum < len(SLib.Tiles):
            painter.drawPixmap(0, 0, SLib.GetTile(self.tilenum))
        painter.drawPixmap(0, 0, self.image)


class SpriteImage_SpecialCoin(SLib.SpriteImage_Static):  # 253, 371, 390
    def __init__(self, parent, scale=1.5):
        super().__init__(
            parent,
            scale,
            ImageCache['SpecialCoin'],
        )


class SpriteImage_Pipe(SLib.SpriteImage):  # 254, 339, 353, 377, 378, 379, 380, 450
    Top = 0
    Bottom = 1

    def __init__(self, parent, scale=1.5):
        super().__init__(parent, scale)
        self.spritebox.shown = False

        self.parent.setZValue(24999)

        self.direction = 'U'
        self.color = 'Green'
        self.length1 = 4
        self.length2 = 4

    @staticmethod
    def loadImages():
        if 'PipeTopGreen' not in ImageCache:
            for color in ('Green', 'Red', 'Yellow', 'Blue'):
                color_l = color.lower()
                ImageCache['PipeTop%s' % color] = SLib.GetImg('pipe_%s_top.png' % color_l)
                ImageCache['PipeMiddleV%s' % color] = SLib.GetImg('pipe_%s_middle.png' % color_l)
                ImageCache['PipeBottom%s' % color] = SLib.GetImg('pipe_%s_bottom.png' % color_l)
                ImageCache['PipeLeft%s' % color] = SLib.GetImg('pipe_%s_left.png' % color_l)
                ImageCache['PipeMiddleH%s' % color] = SLib.GetImg('pipe_%s_center.png' % color_l)
                ImageCache['PipeRight%s' % color] = SLib.GetImg('pipe_%s_right.png' % color_l)

    def dataChanged(self):
        super().dataChanged()
        # sprite types:
        # 339 = Moving Pipe Facing Up
        # 353 = Moving Pipe Facing Down
        # 377 = Pipe Up
        # 378 = Pipe Down
        # 379 = Pipe Right
        # 380 = Pipe Left
        # 450 = Enterable Pipe Up

        size = max(self.length1, self.length2) * 16

        if self.direction in 'LR':  # horizontal
            self.width = size
            self.height = 32
            if self.direction == 'R':  # faces right
                self.xOffset = 0
            else:  # faces left
                self.xOffset = 16 - size
            self.yOffset = 0

        else:  # vertical
            self.width = 32
            self.height = size
            if self.direction == 'D':  # faces down
                self.yOffset = 0
            else:  # faces up
                self.yOffset = 16 - size
            self.xOffset = 0

        if self.direction == 'U':  # facing up
            self.yOffset = 16 - size
        else:  # facing down
            self.yOffset = 0

    def paint(self, painter):
        super().paint(painter)

        color = self.color
        xsize = self.width * 1.5
        ysize = self.height * 1.5

        # Assume moving pipes
        length1 = self.length1 * 24
        length2 = self.length2 * 24
        low = min(length1, length2)
        high = max(length1, length2)

        if self.direction == 'U':
            y1 = ysize - low
            y2 = ysize - high

            if length1 != length2:
                # draw semi-transparent pipe
                painter.save()
                painter.setOpacity(0.5)
                painter.drawPixmap(0, int(y2), ImageCache['PipeTop%s' % color])
                painter.drawTiledPixmap(0, int(y2 + 24), 48, int(high - 24), ImageCache['PipeMiddleV%s' % color])
                painter.restore()

            # draw opaque pipe
            painter.drawPixmap(0, int(y1), ImageCache['PipeTop%s' % color])
            painter.drawTiledPixmap(0, int(y1 + 24), 48, int(low - 24), ImageCache['PipeMiddleV%s' % color])

        elif self.direction == 'D':

            if length1 != length2:
                # draw semi-transparent pipe
                painter.save()
                painter.setOpacity(0.5)
                painter.drawTiledPixmap(0, 0, 48, int(high - 24), ImageCache['PipeMiddleV%s' % color])
                painter.drawPixmap(0, int(high - 24), ImageCache['PipeBottom%s' % color])
                painter.restore()

            # draw opaque pipe
            painter.drawTiledPixmap(0, 0, 48, int(low - 24), ImageCache['PipeMiddleV%s' % color])
            painter.drawPixmap(0, int(low - 24), ImageCache['PipeBottom%s' % color])

        elif self.direction == 'R':

            if length1 != length2:
                # draw semi-transparent pipe
                painter.save()
                painter.setOpacity(0.5)
                painter.drawPixmap(int(high), 0, ImageCache['PipeRight%s' % color])
                painter.drawTiledPixmap(0, 0, int(high - 24), 48, ImageCache['PipeMiddleH%s' % color])
                painter.restore()

            # draw opaque pipe
            painter.drawPixmap(int(low - 24), 0, ImageCache['PipeRight%s' % color])
            painter.drawTiledPixmap(0, 0, int(low - 24), 48, ImageCache['PipeMiddleH%s' % color])

        else:  # left

            if length1 != length2:
                # draw semi-transparent pipe
                painter.save()
                painter.setOpacity(0.5)
                painter.drawTiledPixmap(0, 0, int(high - 24), 48, ImageCache['PipeMiddleH%s' % color])
                painter.drawPixmap(int(high - 24), 0, ImageCache['PipeLeft%s' % color])
                painter.restore()

            # draw opaque pipe
            painter.drawTiledPixmap(24, 0, int(low - 24), 48, ImageCache['PipeMiddleH%s' % color])
            painter.drawPixmap(0, 0, ImageCache['PipeLeft%s' % color])


class SpriteImage_PipeStationary(SpriteImage_Pipe):  # 377, 378, 379, 380, 450
    def __init__(self, parent, scale=1.5):
        super().__init__(parent, scale)
        self.length = 4

    def dataChanged(self):
        self.color = (
            'Green', 'Red', 'Yellow', 'Blue',
        )[(self.parent.spritedata[5] >> 4) & 3]

        self.length1 = self.length
        self.length2 = self.length

        super().dataChanged()


class SpriteImage_UnusedGiantDoor(SLib.SpriteImage_Static):  # 319, 320
    def __init__(self, parent, scale=1.5):
        super().__init__(
            parent,
            scale,
            ImageCache['UnusedGiantDoor'],
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('UnusedGiantDoor', 'unused_giant_door.png')


class SpriteImage_RollingHillWithPipe(SLib.SpriteImage):  # 355, 360
    def __init__(self, parent, scale=1.5):
        super().__init__(parent, scale)
        self.aux.append(SLib.AuxiliaryCircleOutline(parent, 800))


class SpriteImage_LongSpikedStake(SLib.SpriteImage):  # 398, 400
    def __init__(self, parent, scale=1.5):
        super().__init__(parent, scale)
        self.parent.setZValue(24999) # to see sprites behind it easily
        self.spritebox.shown = False

        # 55 mid sections + an end section = 2021
        self.dir = 'left'

    @staticmethod
    def loadImages():
        if 'LongStakeM0left' in ImageCache: return
        for dir in ['left', 'right']:
            ImageCache['LongStakeM0' + dir] = SLib.GetImg('stake_%s_m_0.png' % dir)
            ImageCache['LongStakeM1' + dir] = SLib.GetImg('stake_%s_m_1.png' % dir)
            ImageCache['LongStakeE0' + dir] = SLib.GetImg('stake_%s_e_0.png' % dir)
            ImageCache['LongStakeE1' + dir] = SLib.GetImg('stake_%s_e_1.png' % dir)

    def dataChanged(self):
        super().dataChanged()

        color = self.parent.spritedata[3] & 15
        tiles = 55
        tilesize = 36
        endsize = 41
        width = 99

        pix = QtGui.QPixmap(2021, 99)
        pix.fill(Qt.GlobalColor.transparent)
        paint = QtGui.QPainter(pix)

        if color == 2 or color == 3 or color == 6 or color == 7:
            mid = ImageCache['LongStakeM1' + self.dir]
            end = ImageCache['LongStakeE1' + self.dir]
        else:
            mid = ImageCache['LongStakeM0' + self.dir]
            end = ImageCache['LongStakeE0' + self.dir]

        if self.dir == 'left':
            self.aux[0].setPos(-1896, 36)
            paint.drawPixmap(0, 0, end)
            paint.drawTiledPixmap(endsize, 0, tilesize * tiles, width, mid)
        elif self.dir == 'right':
            self.aux[0].setPos(171, 36)
            self.aux[1].setPos(-1829, 0)
            paint.drawTiledPixmap(0, 0, tilesize * tiles, width, mid)
            paint.drawPixmap(1980, 0, end)

        self.aux[1].image = pix
        self.aux[1].alpha = 0.9


class SpriteImage_MassiveSpikedStake(SLib.SpriteImage):  # 401, 404
    def __init__(self, parent, scale=1.5):
        super().__init__(parent, scale)
        self.parent.setZValue(24999) # to see sprites behind it easily
        self.spritebox.shown = False

        self.SpikeLength = ((72 * 40) + 136) / 1.5
        # (40 mid sections + an end section), accounting for image/sprite size difference
        self.dir = 'down'

    @staticmethod
    def loadImages():
        if 'MassiveStakeM0up' in ImageCache: return
        for dir in ['up', 'down']:
            ImageCache['MassiveStakeM0'] = SLib.GetImg('massive_stake_m_0.png')
            ImageCache['MassiveStakeM1'] = SLib.GetImg('massive_stake_m_1.png')
            ImageCache['MassiveStakeE0' + dir] = SLib.GetImg('massive_stake_%s_e_0.png' % dir)
            ImageCache['MassiveStakeE1' + dir] = SLib.GetImg('massive_stake_%s_e_1.png' % dir)

    def dataChanged(self):
        super().dataChanged()

        color = self.parent.spritedata[3] & 15
        tiles = 40
        tilesize = 72
        endsize = 136
        width = 248

        pix = QtGui.QPixmap(248, 3016)
        pix.fill(Qt.GlobalColor.transparent)
        paint = QtGui.QPainter(pix)

        if color == 2 or color == 3 or color == 6 or color == 7:
            mid = ImageCache['MassiveStakeM1']
            end = ImageCache['MassiveStakeE1' + self.dir]
        else:
            mid = ImageCache['MassiveStakeM0']
            end = ImageCache['MassiveStakeE0' + self.dir]

        if self.dir == 'up':
            self.aux[0].setPos(112, -96)
            self.aux[1].setPos(4, -2592)
            paint.drawPixmap(0, 0, end)
            paint.drawTiledPixmap(0, endsize, width, tilesize * tiles, mid)
        elif self.dir == 'down':
            self.aux[0].setPos(112, 184)
            self.aux[1].setPos(4, 137)
            self.aux[2].setPos(0, -2808)
            paint.drawTiledPixmap(0, 0, width, tilesize * tiles, mid)
            paint.drawPixmap(0, 2880, end)

        paint = None
        self.aux[2].image = pix
        self.aux[2].alpha = 0.9


class SpriteImage_ToadHouseBalloon(SLib.SpriteImage_StaticMultiple):  # 411, 412
    def __init__(self, parent, scale=1.5):
        super().__init__(parent, scale)
        self.hasHandle = False
        self.livesNum = 0
        # self.livesnum: 0 = 1 life, 1 = 2 lives, etc (1 + value)

    @staticmethod
    def loadImages():
        if 'ToadHouseBalloon0' in ImageCache: return
        for handleCacheStr, handleFileStr in (('', ''), ('Handle', 'handle_')):
            for num in range(4):
                ImageCache['ToadHouseBalloon' + handleCacheStr + str(num)] = \
                    SLib.GetImg('mg_house_balloon_' + handleFileStr + str(num) + '.png')

    def dataChanged(self):

        self.image = ImageCache['ToadHouseBalloon' + ('Handle' if self.hasHandle else '') + str(self.livesNum)]

        self.xOffset = 8 - (self.image.width() / 3)

        super().dataChanged()


class SpriteImage_HorzMovingPlatform(SpriteImage_WoodenPlatform):  # 23
    def __init__(self, parent):
        super().__init__(parent, 1.5)

        self.width = ((self.parent.spritedata[5] & 0xF) + 1) << 4
        self.aux.append(SLib.AuxiliaryTrackObject(parent, self.width, 16, SLib.AuxiliaryTrackObject.Horizontal))

    def dataChanged(self):
        super().dataChanged()

        # get width and distance
        self.width = ((self.parent.spritedata[5] & 0xF) + 1) << 4
        if self.width == 16: self.width = 32

        distance = (self.parent.spritedata[4] & 0xF) << 4

        # update the track
        self.aux[0].setSize(self.width + distance, 16)

        if (self.parent.spritedata[3] & 1) == 0:
            # platform goes right
            self.aux[0].setPos(0, 0)
        else:
            # platform goes left
            self.aux[0].setPos(-distance * 1.5, 0)

        # set color, silver is only used for a value of 1
        self.color = (self.parent.spritedata[3] >> 4) == 1

        self.aux[0].update()


class SpriteImage_DSStoneBlock_Vert(SpriteImage_DSStoneBlock):  # 27
    def __init__(self, parent):
        super().__init__(parent, 1.5)

        self.aux.append(SLib.AuxiliaryTrackObject(parent, 32, 16, SLib.AuxiliaryTrackObject.Vertical))
        self.size = (32, 16)

    def dataChanged(self):
        super().dataChanged()

        # get height and distance
        byte5 = self.parent.spritedata[4]
        distance = (byte5 & 0xF) << 4

        # update the track
        self.aux[0].setSize(self.width, distance + self.height)

        if (self.parent.spritedata[3] & 1) == 0:
            # block goes up
            self.aux[0].setPos(0, -distance * 1.5)
        else:
            # block goes down
            self.aux[0].setPos(0, 0)

        self.aux[0].update()


class SpriteImage_DSStoneBlock_Horz(SpriteImage_DSStoneBlock):  # 28
    def __init__(self, parent):
        super().__init__(parent, 1.5)

        self.aux.append(SLib.AuxiliaryTrackObject(parent, 32, 16, SLib.AuxiliaryTrackObject.Horizontal))
        self.size = (32, 16)

    def dataChanged(self):
        super().dataChanged()

        # get height and distance
        byte5 = self.parent.spritedata[4]
        distance = (byte5 & 0xF) << 4

        # update the track
        self.aux[0].setSize(distance + self.width, self.height)

        if (self.parent.spritedata[3] & 1) == 0:
            # block goes right
            self.aux[0].setPos(0, 0)
        else:
            # block goes left
            self.aux[0].setPos(-distance * 1.5, 0)

        self.aux[0].update()


class SpriteImage_OldStoneBlock_NoSpikes(SpriteImage_OldStoneBlock):  # 30
    pass


class SpriteImage_VertMovingPlatform(SpriteImage_WoodenPlatform):  # 31
    def __init__(self, parent):
        super().__init__(parent, 1.5)

        self.width = ((self.parent.spritedata[5] & 0xF) + 1) << 4
        self.aux.append(SLib.AuxiliaryTrackObject(parent, self.width, 16, SLib.AuxiliaryTrackObject.Vertical))

    def dataChanged(self):
        super().dataChanged()

        # get width and distance
        self.width = ((self.parent.spritedata[5] & 0xF) + 1) << 4
        if self.width == 16: self.width = 32

        distance = (self.parent.spritedata[4] & 0xF) << 4

        # update the track
        self.aux[0].setSize(self.width, distance + 16)

        if (self.parent.spritedata[3] & 1) == 0:
            # platform goes up
            self.aux[0].setPos(0, -distance * 1.5)
        else:
            # platform goes down
            self.aux[0].setPos(0, 0)

        # set color, silver is only used for a value of 1
        self.color = (self.parent.spritedata[3] >> 4) == 1

        self.aux[0].update()


class SpriteImage_StarCoinRegular(SpriteImage_StarCoin):  # 32
    pass


class SpriteImage_FallingPlatform(SpriteImage_WoodenPlatform):  # 50
    def __init__(self, parent):
        super().__init__(parent, 1.5)

    def dataChanged(self):
        super().dataChanged()

        # get width
        raw_width = self.parent.spritedata[5] & 0xF
        slow = (self.parent.spritedata[5] >> 4) & 1

        self.width = (raw_width + 1) << 4
        if raw_width == 0:
            # override this for the "glitchy" effect caused by length=0
            self.width = 24
            self.xOffset = -4
        else:
            if slow:
                self.xOffset = 0
            else:
                self.xOffset = -16 * (raw_width >> 1)

        # set color
        color = (self.parent.spritedata[3] >> 4) & 3
        self.height = 16 # reset so the image isn't too big after using the bone platform
        if color == 1:
            self.color = 1
        elif color == 3:
            self.color = 2
            self.height = 20
        else:
            self.color = 0


class SpriteImage_Quicksand(SpriteImage_LiquidOrFog):  # 53
    def __init__(self, parent):
        super().__init__(parent)

        self.crest = ImageCache['LiquidSandCrest']
        self.mid = ImageCache['LiquidSand']

        self.top = self.parent.objy + 8

    @staticmethod
    def loadImages():
        if 'LiquidSand' in ImageCache: return
        ImageCache['LiquidSand'] = SLib.GetImg('liquid_sand.png')
        ImageCache['LiquidSandCrest'] = SLib.GetImg('liquid_sand_crest.png')

    def dataChanged(self):
        self.locId = self.parent.spritedata[5] & 0x7F
        self.drawCrest = self.parent.spritedata[4] & 8 == 0

        if self.drawCrest:
            self.top = self.parent.objy + 8
        else:
            self.top = self.parent.objy

        super().dataChanged()

    def positionChanged(self):
        if self.drawCrest:
            self.top = self.parent.objy + 8
        else:
            self.top = self.parent.objy

        super().positionChanged()


class SpriteImage_OutdoorsFog(SpriteImage_LiquidOrFog):  # 64
    def __init__(self, parent):
        super().__init__(parent)
        self.mid = ImageCache['OutdoorsFog']
        self.top = self.parent.objy

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('OutdoorsFog', 'fog_outdoors.png')

    def dataChanged(self):
        self.locId = self.parent.spritedata[5] & 0x7F
        super().dataChanged()

    def positionChanged(self):
        self.top = self.parent.objy
        super().positionChanged()


class SpriteImage_OldStoneBlock_SpikesLeft(SpriteImage_OldStoneBlock):  # 81
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spikesL = True


class SpriteImage_OldStoneBlock_SpikesRight(SpriteImage_OldStoneBlock):  # 82
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spikesR = True


class SpriteImage_OldStoneBlock_SpikesLeftRight(SpriteImage_OldStoneBlock):  # 83
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spikesL = True
        self.spikesR = True


class SpriteImage_OldStoneBlock_SpikesTop(SpriteImage_OldStoneBlock):  # 84
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spikesT = True


class SpriteImage_OldStoneBlock_SpikesBottom(SpriteImage_OldStoneBlock):  # 85
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spikesB = True


class SpriteImage_OldStoneBlock_SpikesTopBottom(SpriteImage_OldStoneBlock):  # 86
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.spikesT = True
        self.spikesB = True


class SpriteImage_HammerBroNormal(SLib.SpriteImage_Static):  # 95
    def __init__(self, parent, scale=1.5):
        super().__init__(
            parent,
            scale,
            ImageCache['HammerBro'],
            (-4, -21)
        )

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('HammerBro', 'hammerbro.png')


class SpriteImage_RotationControlledSolidBetaPlatform(SpriteImage_UnusedBlockPlatform):  # 97
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.isDark = True

    def dataChanged(self):
        size = self.parent.spritedata[4]
        width = size >> 4
        height = size & 0xF

        if width == 0 or height == 0:
            self.spritebox.shown = True
            self.drawPlatformImage = False
            del self.size
        else:
            self.spritebox.shown = False
            self.drawPlatformImage = True
            self.size = (width * 16, height * 16)

        super().dataChanged()


class SpriteImage_PlatformGenerator(SpriteImage_WoodenPlatform):  # 103
    # TODO: Add arrows
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.yOffset = 16

    def dataChanged(self):
        super().dataChanged()

        # get width
        self.width = self.parent.spritedata[5] & 0xF0

        # length 0 results in the same width as length 4
        if self.width == 0: self.width = 64

        # override the x offset for the "glitchy" effect caused by length 0
        if self.width in {16, 24}:
            self.width = 24
            self.xOffset = -8
        else:
            self.xOffset = 0

        self.color = 0


class SpriteImage_AmpNormal(SpriteImage_Amp):  # 104
    pass


class SpriteImage_LinePlatform(SpriteImage_WoodenPlatform):  # 106
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.yOffset = 8

    def dataChanged(self):
        super().dataChanged()

        # get width
        self.width = (self.parent.spritedata[5] & 0xF) << 4

        # length=0 becomes length=4
        if self.width == 0: self.width = 64

        # override this for the "glitchy" effect caused by length=0
        if self.width == 16: self.width = 24

        # reposition platform
        self.xOffset = 32 - (self.width / 2)

        color = (self.parent.spritedata[4] & 0xF0) >> 4
        if color > 1: color = 0
        self.color = color


class SpriteImage_RotationControlledPassBetaPlatform(SpriteImage_UnusedBlockPlatform):  # 107
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.isDark = True
        self.width = 16

    def dataChanged(self):
        size = self.parent.spritedata[4]
        height = (size & 0xF) + 1

        self.yOffset = -(height - 1) * 8
        self.height = height * 16

        super().dataChanged()


class SpriteImage_AmpLine(SpriteImage_Amp):  # 108
    pass


# TODO: Properly implement 'down & right' track
class SpriteImage_OneWayPlatform(SpriteImage_WoodenPlatform):  # 122
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        width = self.parent.spritedata[5] & 0xF
        if width < 2: width = 1
        self.width = width * 32 + 32

        self.aux.append(SLib.AuxiliaryTrackObject(parent, self.width, 16, SLib.AuxiliaryTrackObject.Horizontal))

    def dataChanged(self):
        super().dataChanged()
        width = self.parent.spritedata[5] & 0xF
        if width < 2: width = 1
        self.width = width * 32 + 32

        self.xOffset = self.width * -0.5

        self.color = ((self.parent.spritedata[4] & 0xF0) >> 4) & 1

        distance = (self.parent.spritedata[3] & 0xF0) >> 4
        direction = self.parent.spritedata[3] & 0xF

        if distance != 0 or direction != 4:
            if distance == 1:
                increment = 14
            else:
                increment = 16

            self.aux[0].setRotation(0)

            if direction <= 1:  # horizontal
                self.aux[0].direction = 2
                self.aux[0].setSize(self.width, self.height + (distance * 16 * increment))
            elif direction <= 3:  # vertical
                self.aux[0].direction = 1
                self.aux[0].setSize(self.width + (distance * 16 * increment), self.height)
            else:  # down & right
                self.aux[0].direction = 1
                self.aux[0].setSize((self.width - (16 * width)) + (distance * 16 * increment), self.height)
                self.aux[0].setRotation(45)

            if direction == 1 or direction == 2:  # right, down
                self.aux[0].setPos(0, 0)
            elif direction == 3:  # left
                self.aux[0].setPos(-(distance * increment) * 24, 0)
            elif direction == 0:  # up
                self.aux[0].setPos(0, -(distance * increment) * 24)
            else: # down & right
                self.aux[0].setPos(self.width + (16 * width), -8)
        else:
            self.aux[0].setSize(0, 0)


class SpriteImage_UnusedBlockPlatform1(SpriteImage_UnusedBlockPlatform):  # 132
    def dataChanged(self):
        self.width = ((self.parent.spritedata[5] & 0xF) + 1) * 16
        self.height = ((self.parent.spritedata[5] >> 4) + 1) * 16
        super().dataChanged()


class SpriteImage_SpikedStakeDown(SpriteImage_SpikedStake):  # 137
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.dir = 'down'
        self.aux.append(SLib.AuxiliaryTrackObject(parent, 16, 64, SLib.AuxiliaryTrackObject.Vertical))

        self.dimensions = (0, 16 - self.VertSpikeLength, 66, self.VertSpikeLength)


class SpriteImage_Water(SpriteImage_LiquidOrFog):  # 138
    def __init__(self, parent):
        super().__init__(parent)

        self.crest = ImageCache['LiquidWaterCrest']
        self.mid = ImageCache['LiquidWater']
        self.rise = ImageCache['LiquidWaterRiseCrest']
        self.riseCrestless = ImageCache['LiquidWaterRise']

        self.top = self.parent.objy

    @staticmethod
    def loadImages():
        if 'LiquidWater' in ImageCache: return
        ImageCache['LiquidWater'] = SLib.GetImg('liquid_water.png')
        ImageCache['LiquidWaterCrest'] = SLib.GetImg('liquid_water_crest.png')
        ImageCache['LiquidWaterRise'] = SLib.GetImg('liquid_water_rise.png')
        ImageCache['LiquidWaterRiseCrest'] = SLib.GetImg('liquid_water_rise_crest.png')

    def dataChanged(self):
        self.locId = self.parent.spritedata[5] & 0x7F
        self.drawCrest = self.parent.spritedata[4] & 8 == 0

        self.risingHeight = (self.parent.spritedata[3] & 0xF) << 4
        self.risingHeight |= self.parent.spritedata[4] >> 4
        if self.parent.spritedata[2] & 15 > 7:  # falling
            self.risingHeight = -self.risingHeight

        if not self.drawCrest and self.locId == 0:
            self.top = self.parent.objy + 20
            self.mid.alpha = 0.1
        else:
            self.top = self.parent.objy
            self.mid.alpha = 1

        super().dataChanged()

    def positionChanged(self):
        self.top = self.parent.objy
        super().positionChanged()


class SpriteImage_Lava(SpriteImage_LiquidOrFog):  # 139
    def __init__(self, parent):
        super().__init__(parent)

        self.crest = ImageCache['LiquidLavaCrest']
        self.mid = ImageCache['LiquidLava']
        self.rise = ImageCache['LiquidLavaRiseCrest']
        self.riseCrestless = ImageCache['LiquidLavaRise']

        self.top = self.parent.objy

    @staticmethod
    def loadImages():
        if 'LiquidLava' in ImageCache: return
        ImageCache['LiquidLava'] = SLib.GetImg('liquid_lava.png')
        ImageCache['LiquidLavaCrest'] = SLib.GetImg('liquid_lava_crest.png')
        ImageCache['LiquidLavaRise'] = SLib.GetImg('liquid_lava_rise.png')
        ImageCache['LiquidLavaRiseCrest'] = SLib.GetImg('liquid_lava_rise_crest.png')

    def dataChanged(self):
        self.locId = self.parent.spritedata[5] & 0x7F
        self.drawCrest = self.parent.spritedata[4] & 8 == 0

        self.risingHeight = (self.parent.spritedata[3] & 0xF) << 4
        self.risingHeight |= self.parent.spritedata[4] >> 4
        if self.parent.spritedata[2] & 15 > 7:  # falling
            self.risingHeight = -self.risingHeight

        super().dataChanged()

    def positionChanged(self):
        self.top = self.parent.objy
        super().positionChanged()


class SpriteImage_SpikedStakeUp(SpriteImage_SpikedStake):  # 140
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.dir = 'up'
        self.aux.append(SLib.AuxiliaryTrackObject(parent, 16, 64, SLib.AuxiliaryTrackObject.Vertical))

        self.dimensions = (0, 0, 66, self.VertSpikeLength)


class SpriteImage_SpikedStakeRight(SpriteImage_SpikedStake):  # 141
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.dir = 'right'
        self.aux.append(SLib.AuxiliaryTrackObject(parent, 64, 16, SLib.AuxiliaryTrackObject.Horizontal))

        self.dimensions = (16 - self.HorzSpikeLength, 0, self.HorzSpikeLength, 66)


class SpriteImage_SpikedStakeLeft(SpriteImage_SpikedStake):  # 142
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.dir = 'left'
        self.aux.append(SLib.AuxiliaryTrackObject(parent, 64, 16, SLib.AuxiliaryTrackObject.Horizontal))

        self.dimensions = (0, 0, self.HorzSpikeLength, 66)


class SpriteImage_StarCoinLineControlled(SpriteImage_StarCoin):  # 155
    pass


class SpriteImage_UnusedBlockPlatform2(SpriteImage_UnusedBlockPlatform):  # 160
    def dataChanged(self):
        self.width = ((self.parent.spritedata[4] & 0xF) + 1) * 16
        self.height = ((self.parent.spritedata[4] >> 4) + 1) * 16
        super().dataChanged()


class SpriteImage_ScrewMushroomWithBolt(SpriteImage_ScrewMushroom):  # 172
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.hasBolt = True


class SpriteImage_EventDoor(SpriteImage_Door):  # 182
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.alpha = 0.5


class SpriteImage_GiantBubbleNormal(SpriteImage_GiantBubble):  # 205
    pass


class SpriteImage_QBlock(SpriteImage_Block):  # 207
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.tilenum = 49


class SpriteImage_QBlockUnused(SpriteImage_Block):  # 208
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.tilenum = 49
        self.eightIsMushroom = True
        self.twelveIsMushroom = True


class SpriteImage_BrickBlock(SpriteImage_Block):  # 209
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.tilenum = 48


class SpriteImage_Poison(SpriteImage_LiquidOrFog):  # 216
    def __init__(self, parent):
        super().__init__(parent)

        self.crest = ImageCache['LiquidPoisonCrest']
        self.mid = ImageCache['LiquidPoison']
        self.rise = ImageCache['LiquidPoisonRiseCrest']
        self.riseCrestless = ImageCache['LiquidPoisonRise']

        self.top = self.parent.objy

    @staticmethod
    def loadImages():
        if 'LiquidPoison' in ImageCache: return
        ImageCache['LiquidPoison'] = SLib.GetImg('liquid_poison.png')
        ImageCache['LiquidPoisonCrest'] = SLib.GetImg('liquid_poison_crest.png')
        ImageCache['LiquidPoisonRise'] = SLib.GetImg('liquid_poison_rise.png')
        ImageCache['LiquidPoisonRiseCrest'] = SLib.GetImg('liquid_poison_rise_crest.png')

    def dataChanged(self):
        self.locId = self.parent.spritedata[5] & 0x7F
        self.drawCrest = self.parent.spritedata[4] & 8 == 0

        self.risingHeight = (self.parent.spritedata[3] & 0xF) << 4
        self.risingHeight |= self.parent.spritedata[4] >> 4
        if self.parent.spritedata[2] & 15 > 7:  # falling
            self.risingHeight = -self.risingHeight

        super().dataChanged()

    def positionChanged(self):
        self.top = self.parent.objy
        super().positionChanged()


class SpriteImage_InvisibleBlock(SpriteImage_Block):  # 221
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.eightIsMushroom = True
        self.tilenum = 0x200 * 4


class SpriteImage_FloatingCoin(SpriteImage_SpecialCoin):  # 225
    pass


class SpriteImage_GiantBubbleUnused(SpriteImage_GiantBubble):  # 226
    pass


class SpriteImage_RotControlledCoin(SpriteImage_SpecialCoin):  # 253
    pass


class SpriteImage_RotControlledPipe(SpriteImage_Pipe):  # 254
    def dataChanged(self):
        self.length1 = self.length2 = (self.parent.spritedata[4] >> 4) + 2
        dir = self.parent.spritedata[4] & 3
        self.direction = 'URDL'[dir]
        super().dataChanged()


class SpriteImage_RotatingQBlock(SpriteImage_Block):  # 255
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.tilenum = 49
        self.contentsNybble = 4
        self.twelveIsMushroom = True
        self.rotates = True


class SpriteImage_RotatingBrickBlock(SpriteImage_Block):  # 256
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.tilenum = 48
        self.contentsNybble = 4
        self.twelveIsMushroom = True
        self.rotates = True


class SpriteImage_RegularDoor(SpriteImage_Door):  # 259
    pass


class SpriteImage_OldStoneBlock_MovementControlled(SpriteImage_OldStoneBlock):  # 261
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.hasMovementAux = False


class SpriteImage_GhostDoor(SpriteImage_Door):  # 276
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.doorName = 'GhostDoor'
        self.doorDimensions = (0, 0, 32, 48)


class SpriteImage_TowerDoor(SpriteImage_Door):  # 277
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.doorName = 'TowerDoor'
        self.doorDimensions = (-2, -13, 53, 61)
        self.entranceOffset = (15, 68)


class SpriteImage_CastleDoor(SpriteImage_Door):  # 278
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.doorName = 'CastleDoor'
        self.doorDimensions = (-2, -13, 53, 61)
        self.entranceOffset = (15, 68)


class SpriteImage_HammerBroPlatform(SpriteImage_HammerBroNormal):  # 308
    pass


class SpriteImage_UnusedWiimoteDoor(SpriteImage_UnusedGiantDoor):  # 319
    pass


class SpriteImage_UnusedSlidingWiimoteDoor(SpriteImage_UnusedGiantDoor):  # 320
    pass


class SpriteImage_Pipe_MovingUp(SpriteImage_Pipe):  # 339
    def dataChanged(self):
        self.length1 = (self.parent.spritedata[5] >> 4) + 2
        self.length2 = (self.parent.spritedata[5] & 0xF) + 2
        self.color = (
            'Green', 'Red', 'Yellow', 'Blue',
        )[self.parent.spritedata[3] & 3]

        super().dataChanged()


class SpriteImage_Pipe_MovingDown(SpriteImage_Pipe):  # 353
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.direction = 'D'

    def dataChanged(self):
        self.length1 = (self.parent.spritedata[5] >> 4) + 2
        self.length2 = (self.parent.spritedata[5] & 0xF) + 2
        self.color = (
            'Green', 'Red', 'Yellow', 'Blue',
        )[self.parent.spritedata[3] & 3]

        super().dataChanged()


class SpriteImage_RollingHillWith1Pipe(SpriteImage_RollingHillWithPipe):  # 355
    pass


class SpriteImage_LavaParticles(SpriteImage_LiquidOrFog):  # 358
    @staticmethod
    def loadImages():
        if 'LavaParticlesA' in ImageCache: return
        ImageCache['LavaParticlesA'] = SLib.GetImg('lava_particles_a.png')
        ImageCache['LavaParticlesB'] = SLib.GetImg('lava_particles_b.png')
        ImageCache['LavaParticlesC'] = SLib.GetImg('lava_particles_c.png')

    def dataChanged(self):
        type = (self.parent.spritedata[5] & 0xF) % 3
        self.mid = (
            ImageCache['LavaParticlesA'],
            ImageCache['LavaParticlesB'],
            ImageCache['LavaParticlesC'],
        )[type]

        super().dataChanged()


class SpriteImage_RollingHillWith8Pipes(SpriteImage_RollingHillWithPipe):  # 360
    pass


class SpriteImage_RollingHillCoin(SpriteImage_SpecialCoin):  # 371
    pass


class SpriteImage_RaftWater(SpriteImage_LiquidOrFog):  # 373
    def __init__(self, parent):
        super().__init__(parent)

        self.crest = ImageCache['RaftWaterCrest']
        self.mid = ImageCache['RaftWater']

        self.top = self.parent.objy
        self.drawCrest = True

    @staticmethod
    def loadImages():
        if 'RaftWaterCrest' in ImageCache: return
        ImageCache['RaftWater'] = SLib.GetImg('liquid_water.png')
        ImageCache['RaftWaterCrest'] = SLib.GetImg('liquid_water_crest.png')

    def positionChanged(self):
        self.top = self.parent.objy
        super().positionChanged()


class SpriteImage_SnowWind(SpriteImage_LiquidOrFog):  # 374
    def __init__(self, parent):
        super().__init__(parent)
        self.mid = ImageCache['SnowEffect']

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('SnowEffect', 'snow.png')

    def paintZone(self):
        # For now, we only paint snow
        return self.parent.spritedata[5] == 0 and self.zoneId != -1


class SpriteImage_Pipe_Up(SpriteImage_PipeStationary):  # 377
    def dataChanged(self):
        self.length = (self.parent.spritedata[5] & 0xF) + 2
        super().dataChanged()


class SpriteImage_Pipe_Down(SpriteImage_PipeStationary):  # 378
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.direction = 'D'

    def dataChanged(self):
        self.length = (self.parent.spritedata[5] & 0xF) + 2
        super().dataChanged()


class SpriteImage_Pipe_Right(SpriteImage_PipeStationary):  # 379
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.direction = 'R'

    def dataChanged(self):
        self.length = (self.parent.spritedata[5] & 0xF) + 2
        super().dataChanged()


class SpriteImage_Pipe_Left(SpriteImage_PipeStationary):  # 380
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.direction = 'L'

    def dataChanged(self):
        self.length = (self.parent.spritedata[5] & 0xF) + 2
        super().dataChanged()


class SpriteImage_ScrewMushroomNoBolt(SpriteImage_ScrewMushroom):  # 382
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.hasBolt = False


class SpriteImage_StarCoinBoltControlled(SpriteImage_StarCoin):  # 389
    pass


class SpriteImage_BoltControlledCoin(SpriteImage_SpecialCoin):  # 390
    pass


class SpriteImage_LongSpikedStakeRight(SpriteImage_LongSpikedStake):  # 398
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.dir = 'right'
        self.aux.append(SLib.AuxiliaryTrackObject(parent, 1296, 16, SLib.AuxiliaryTrackObject.Horizontal))
        self.aux.append(SLib.AuxiliaryImage(parent, 2021, 99))

        self.dimensions = (-112, 0, 128, 66) # 6 mid sections + end section


class SpriteImage_LongSpikedStakeLeft(SpriteImage_LongSpikedStake):  # 400
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.dir = 'left'
        self.aux.append(SLib.AuxiliaryTrackObject(parent, 1296, 16, SLib.AuxiliaryTrackObject.Horizontal))
        self.aux.append(SLib.AuxiliaryImage(parent, 2021, 99))

        self.dimensions = (0, 0, 128, 66)


class SpriteImage_MassiveSpikedStakeDown(SpriteImage_MassiveSpikedStake):  # 401
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.dir = 'down'
        self.aux.append(SLib.AuxiliaryTrackObject(parent, 16, 80, SLib.AuxiliaryTrackObject.Vertical))
        self.aux.append(SLib.AuxiliaryRectOutline(parent, 240, 2664, 4, 2944))
        self.aux.append(SLib.AuxiliaryImage(parent, 248, 3016))

        self.dimensions = (-67, -123, 165, 139)

class SpriteImage_LineQBlock(SpriteImage_Block):  # 402
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.tilenum = 49
        self.twelveIsMushroom = True


class SpriteImage_LineBrickBlock(SpriteImage_Block):  # 403
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.tilenum = 48


class SpriteImage_MassiveSpikedStakeUp(SpriteImage_MassiveSpikedStake):  # 404
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.dir = 'up'
        self.aux.append(SLib.AuxiliaryTrackObject(parent, 16, 80, SLib.AuxiliaryTrackObject.Vertical))
        self.aux.append(SLib.AuxiliaryRectOutline(parent, 240, 2664, 4, -2592))
        self.aux.append(SLib.AuxiliaryImage(parent, 248, 3016))

        self.dimensions = (-67, 0, 165, 139)


class SpriteImage_ToadHouseBalloonUnused(SpriteImage_ToadHouseBalloon):  # 411
    def dataChanged(self):
        self.livesNum = (self.parent.spritedata[4] >> 4) & 3

        super().dataChanged()

        self.yOffset = 8 - (self.image.height() / 3)


class SpriteImage_ToadHouseBalloonUsed(SpriteImage_ToadHouseBalloon):  # 412
    def dataChanged(self):

        self.livesNum = (self.parent.spritedata[4] >> 4) & 3
        self.hasHandle = not ((self.parent.spritedata[5] >> 4) & 1)

        super().dataChanged()

        if self.hasHandle:
            self.yOffset = 12
        else:
            self.yOffset = 16 - (self.image.height() / 3)


class SpriteImage_ToadQBlock(SpriteImage_Block):  # 422
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.tilenum = 49
        self.contentsOverride = 16


class SpriteImage_ToadBrickBlock(SpriteImage_Block):  # 423
    def __init__(self, parent):
        super().__init__(parent, 1.5)
        self.tilenum = 48
        self.contentsOverride = 16


class SpriteImage_GhostFog(SpriteImage_LiquidOrFog):  # 435
    def __init__(self, parent):
        super().__init__(parent)
        self.mid = ImageCache['GhostFog']
        self.top = self.parent.objy

    @staticmethod
    def loadImages():
        SLib.loadIfNotInImageCache('GhostFog', 'fog_ghost.png')

    def dataChanged(self):
        self.locId = self.parent.spritedata[5] & 0x7F
        super().dataChanged()

    def positionChanged(self):
        # This sprite's cutoff works a bit differently. The effect is always
        # fixed to the top of the zone, but only the part below the sprite image
        # is rendered.
        # BUG: This is not recreated.
        self.top = self.parent.objy
        super().positionChanged()


class SpriteImage_Pipe_EnterableUp(SpriteImage_PipeStationary):  # 450
    def dataChanged(self):
        self.length = (self.parent.spritedata[5] & 0xF) + 2
        super().dataChanged()
