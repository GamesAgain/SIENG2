from PyQt6.QtWidgets import QVBoxLayout, QWidget


class VisibilityStack(QWidget):
    """Minimal drop-in replacement for QStackedWidget — only addWidget()/
    setCurrentIndex() are supported, matching what the Manual Upload / Linked
    from Step toggle actually needs.

    QStackedWidget always sizes itself to its TALLEST child regardless of
    which page is visible (its internal QStackedLayout reserves space for
    every page, hidden or not). That silently inflates any card pairing a
    tall FileDropWidget with a compact StepOutputPicker — the picker's
    container stays drop-zone-sized even when it only has one short row to
    show. This widget instead hides all but the current page outright, so a
    plain QVBoxLayout only ever reserves space for what's actually visible."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pages: list[QWidget] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

    def addWidget(self, widget: QWidget):
        widget.setVisible(len(self._pages) == 0)
        self._layout.addWidget(widget)
        self._pages.append(widget)
        return len(self._pages) - 1

    def setCurrentIndex(self, index: int):
        for i, page in enumerate(self._pages):
            page.setVisible(i == index)
