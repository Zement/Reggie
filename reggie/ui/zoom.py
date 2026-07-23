"""Zoom controls extracted from ``ReggieWindow`` (Phase 2 refactor).

Second extraction of the ``ReggieWindow`` breakup and the first one that passes
window *state* across the composition boundary (see
_docs/plan/REFACTORING_ANALYSIS.md). The handlers read/write ``self.win.<attr>``
where they previously used ``self.<attr>``:

* ``win.ZoomLevel`` / ``win.ZoomLevels`` stay **window attributes** — other
  clusters (e.g. clipboard's ``getEncodedObjects``) read ``self.ZoomLevel`` — so
  the controller mutates them through ``self.win`` rather than owning them.
* ``win.view``, ``win.levelOverview``, ``win.actions``, ``win.ZoomWidget``,
  ``win.ZoomStatusWidget``, ``win.scene`` are all pre-existing window widgets.

``ReggieWindow`` keeps thin delegators (``HandleZoomIn``, ``ZoomTo``, …) so the
``QAction`` wiring built in ``createMenubar`` and the ``ZoomTo`` calls elsewhere
(``LoadLevel_NSMBW``) resolve unchanged. Controller-internal calls to ``ZoomTo``
stay ``self.ZoomTo`` (same object).
"""

from PyQt6 import QtGui, QtWidgets

from reggie.core import globals_


class ZoomController:
    """Owns the zoom-level transitions for the main editor view."""

    def __init__(self, win):
        self.win = win

    def HandleZoomIn(self, *, towardsCursor=False):
        """
        Handle zooming in
        """
        z = self.win.ZoomLevel
        zi = self.win.ZoomLevels.index(z) + 1
        if zi < len(self.win.ZoomLevels):
            self.ZoomTo(self.win.ZoomLevels[zi], towardsCursor=towardsCursor)

    def HandleZoomOut(self, *, towardsCursor=False):
        """
        Handle zooming out
        """
        z = self.win.ZoomLevel
        zi = self.win.ZoomLevels.index(z) - 1
        if zi >= 0:
            self.ZoomTo(self.win.ZoomLevels[zi], towardsCursor=towardsCursor)

    def HandleZoomActual(self):
        """
        Handle zooming to the actual size
        """
        self.ZoomTo(100.0)

    def HandleZoomMin(self):
        """
        Handle zooming to the minimum size
        """
        self.ZoomTo(self.win.ZoomLevels[0])

    def HandleZoomMax(self):
        """
        Handle zooming to the maximum size
        """
        self.ZoomTo(self.win.ZoomLevels[-1])

    def ZoomTo(self, z, *, towardsCursor=False):
        """
        Zoom to a specific level
        """
        if towardsCursor:
            self.win.view.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        tr = QtGui.QTransform()
        tr.scale(z / 100.0, z / 100.0)
        self.win.ZoomLevel = z
        self.win.view.setTransform(tr)
        self.win.levelOverview.mainWindowScale = z / 100.0

        if towardsCursor:
            # (reset back to original transformation anchor)
            self.win.view.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorViewCenter)

        zi = self.win.ZoomLevels.index(z)
        self.win.actions['zoommax'].setEnabled(zi < len(self.win.ZoomLevels) - 1)
        self.win.actions['zoomin'].setEnabled(zi < len(self.win.ZoomLevels) - 1)
        self.win.actions['zoomactual'].setEnabled(z != 100.0)
        self.win.actions['zoomout'].setEnabled(zi > 0)
        self.win.actions['zoommin'].setEnabled(zi > 0)

        self.win.ZoomWidget.setZoomLevel(z)
        self.win.ZoomStatusWidget.setZoomLevel(z)

        # Update the zone grabber rects, to resize for the new zoom level
        for z in globals_.Area.zones:
            z.UpdateRects()

        self.win.scene.update()
