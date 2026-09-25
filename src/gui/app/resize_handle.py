from PyQt6.QtWidgets import QWidget, QMainWindow
from PyQt6.QtCore import QObject, Qt, QEvent


class WindowResizeHandler(QObject):

    def __init__(self, window: QMainWindow, margin: int = 8):
        super().__init__(window)

        self.window = window
        self.margin = margin

        self.enable_mouse_tracking()

    def enable_mouse_tracking(self):
        """
        Enable mouse tracking for the window and all child widgets
        so the resize cursor can be displayed on hover.
        """
        self.window.setMouseTracking(True)
        self.window.installEventFilter(self)

        for widget in self.window.findChildren(QWidget):
            widget.setMouseTracking(True)
            widget.installEventFilter(self)

    def get_resize_edges(self, pos):
        """
        Detect which edge/corner of the window the mouse is over.
        """
        if self.window.isMaximized():
            return Qt.Edge(0)

        rect = self.window.rect()

        edges = Qt.Edge(0)

        if pos.x() <= self.margin:
            edges |= Qt.Edge.LeftEdge

        if pos.x() >= rect.width() - self.margin:
            edges |= Qt.Edge.RightEdge

        if pos.y() <= self.margin:
            edges |= Qt.Edge.TopEdge

        if pos.y() >= rect.height() - self.margin:
            edges |= Qt.Edge.BottomEdge

        return edges

    def update_cursor(self, pos):
        """
        Change the mouse cursor depending on the resize edge.
        """
        edges = self.get_resize_edges(pos)

        if edges == (
            Qt.Edge.LeftEdge |
            Qt.Edge.TopEdge
        ):
            self.window.setCursor(
                Qt.CursorShape.SizeFDiagCursor
            )

        elif edges == (
            Qt.Edge.RightEdge |
            Qt.Edge.BottomEdge
        ):
            self.window.setCursor(
                Qt.CursorShape.SizeFDiagCursor
            )

        elif edges == (
            Qt.Edge.RightEdge |
            Qt.Edge.TopEdge
        ):
            self.window.setCursor(
                Qt.CursorShape.SizeBDiagCursor
            )

        elif edges == (
            Qt.Edge.LeftEdge |
            Qt.Edge.BottomEdge
        ):
            self.window.setCursor(
                Qt.CursorShape.SizeBDiagCursor
            )

        elif edges & (
            Qt.Edge.LeftEdge |
            Qt.Edge.RightEdge
        ):
            self.window.setCursor(
                Qt.CursorShape.SizeHorCursor
            )

        elif edges & (
            Qt.Edge.TopEdge |
            Qt.Edge.BottomEdge
        ):
            self.window.setCursor(
                Qt.CursorShape.SizeVerCursor
            )

        else:
            self.window.unsetCursor()

    def eventFilter(self, obj, event):

        # --------------------------------
        # Resize Cursor
        # --------------------------------
        if event.type() == QEvent.Type.MouseMove:

            global_pos = event.globalPosition().toPoint()

            pos = self.window.mapFromGlobal(
                global_pos
            )

            self.update_cursor(pos)

        # --------------------------------
        # Start Resize
        # --------------------------------
        elif event.type() == QEvent.Type.MouseButtonPress:

            if event.button() == Qt.MouseButton.LeftButton:

                global_pos = event.globalPosition().toPoint()

                pos = self.window.mapFromGlobal(
                    global_pos
                )

                edges = self.get_resize_edges(pos)

                if edges:
                    handle = self.window.windowHandle()

                    if handle:
                        handle.startSystemResize(edges)

                    return True

        return super().eventFilter(obj, event)