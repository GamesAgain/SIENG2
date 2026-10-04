from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from src.gui.features.embed.configurable.widgets.step_card import STEP_CARD_MIME, StepCard


class DropIndicator(QWidget):
    """Small overlay, so the insertion line stays visible above card edges."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QPen(QColor("#38BDF8"), 3))
        painter.drawLine(self.width() // 2, 0, self.width() // 2, self.height() - 1)


class StepCanvas(QWidget):
    """Receive internal card moves; the page owns and modifies the card list."""
    reorder_requested = pyqtSignal(object, int)

    def __init__(self, cards: list[StepCard], parent=None):
        super().__init__(parent)
        self.cards = cards
        self.setAcceptDrops(True)
        self.drop_indicator = DropIndicator(self)

    def drag_card(self, event) -> StepCard | None:
        source = event.source()
        if event.mimeData().hasFormat(STEP_CARD_MIME) and isinstance(source, StepCard) and source in self.cards:
            return source
        return None

    def insertion_at(self, position):
        """Find a row first, then use each card midpoint for before/after."""
        rows = {}
        for index, card in enumerate(self.cards):
            rows.setdefault(card.y(), []).append((index, card))
        if not rows:
            return None

        # Distance to a row is zero inside it; gaps use the closest row.
        def row_distance(row):
            rect = row[0][1].geometry()
            return max(rect.top() - position.y(), position.y() - rect.bottom(), 0)

        row = min(rows.values(), key=row_distance)
        for index, card in row:
            if position.x() < card.geometry().center().x():
                return index, card.geometry(), True
        index, card = row[-1]
        return index + 1, card.geometry(), False

    def update_drop_indicator(self, position):
        insertion = self.insertion_at(position)
        if insertion is None:
            self.drop_indicator.hide()
            return
        _, rect, before = insertion
        x = rect.left() - 4 if before else rect.right() + 4
        x = max(0, min(x - 1, self.width() - 3))
        self.drop_indicator.setGeometry(x, rect.top(), 3, rect.height())
        self.drop_indicator.show()
        self.drop_indicator.raise_()

    def dragEnterEvent(self, event):
        if self.drag_card(event) is None:
            event.ignore()
            return
        self.update_drop_indicator(event.position().toPoint())
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dragLeaveEvent(self, event):
        self.drop_indicator.hide()
        event.accept()

    def dropEvent(self, event):
        self.drop_indicator.hide()
        card = self.drag_card(event)
        insertion = self.insertion_at(event.position().toPoint())
        if card is None or insertion is None:
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()
        self.reorder_requested.emit(card, insertion[0])
