"""Zoom controls extracted from ``ReggieWindow`` (Phase 2 refactor).

Second extraction of the ``ReggieWindow`` breakup and the first one that passes
window *state* across the composition boundary (see
_docs/plan/REFACTORING_ANALYSIS.md). The handlers read/write ``self.win.<attr>``
where they previously used ``self.<attr>``:

* ``win.ZoomLevels`` (the list of steps) stays a window attribute. ``ZoomLevel``
  (the current one) became a **property forwarding to the active session** in
  D-c.4, so zooming one area no longer changes what another reports; the
  controller still reads and writes it through ``self.win``, unchanged.
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
        # Since D-c.4 this writes the *active session's* zoom, and win.view is
        # that session's view - so zooming one area leaves the others alone.
        self.win.ZoomLevel = z
        self.win.view.setTransform(tr)

        if towardsCursor:
            # (reset back to original transformation anchor)
            self.win.view.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorViewCenter)

        # The status widget, the slider, the five zoom actions and the overview
        # scale, all from the value just stored. Shared with the tab switch,
        # which has to do exactly the same work from the other direction - two
        # copies of this list is how the switch came to disagree with the zoom.
        self.win.SyncZoomToSession()

        # Update the zone grabber rects, to resize for the new zoom level
        for zone in globals_.Area.zones:
            zone.UpdateRects()

        self.win.scene.update()
