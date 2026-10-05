from PyQt6.QtWidgets import QVBoxLayout, QWidget


class VisibilityStack(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pages: list[QWidget] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

    def addWidget(self, widget: QWidget):
        self._layout.addWidget(widget)
        # Parent the page before showing it to avoid a temporary top-level window.
        widget.setVisible(len(self._pages) == 0)
        self._pages.append(widget)
        return len(self._pages) - 1

    def setCurrentIndex(self, index: int):
        for i, page in enumerate(self._pages):
            page.setVisible(i == index)
