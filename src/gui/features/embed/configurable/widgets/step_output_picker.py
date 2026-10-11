from pathlib import Path

from PyQt6.QtCore import QFileInfo, QModelIndex, QRect, QSignalBlocker, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QIcon, QImageReader, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView, QFileIconProvider, QFrame, QLabel, QListWidget, QListWidgetItem, QStackedWidget,
    QStyle, QStyledItemDelegate, QStyleOptionViewItem, QVBoxLayout,
)

from src.core.configurable.step_output import StepOutputInfo
from src.gui.components.gui_utils import create_icon_pixmap
from src.gui.features.embed.configurable.constants import TECHNIQUE_DISPLAY
from src.path import svg_path

# Extra data of a row (the file name is the row's text, the StepOutput is in REFERENCE_ROLE)
REFERENCE_ROLE = Qt.ItemDataRole.UserRole
STEP_ROLE = Qt.ItemDataRole.UserRole + 1      # "Step 2 · Locomotive"
ACCENT_ROLE = Qt.ItemDataRole.UserRole + 2    # hex colour of the technique
MEDIA_ROLE = Qt.ItemDataRole.UserRole + 3     # "PNG" / "MP3"
THUMB_ROLE = Qt.ItemDataRole.UserRole + 4     # QIcon: the cover picture, or the system icon of the file type

ROW_HEIGHT = 52
THUMB_SIZE = 36
EMPTY_TEXT = "No previous outputs available."
PNG_OUTPUT_EMPTY_TEXT = "No previous PNG outputs available.\nSave an earlier step that makes a PNG, then pick it here."

# Same colours as the file rows (fileItemRow in default.qss); a delegate cannot be styled by QSS
ROW_FILL, ROW_BORDER = "#2A2A2D", "#3D3D40"
HOVER_FILL, SELECTED_FILL = "#333336", "#1D3038"
SELECTED_BORDER, FOCUS_BORDER = "#38BDF8", "#64748B"
THUMB_FILL, THUMB_BORDER = "#1F1F1F", "#343434"
NAME_COLOR, DETAIL_COLOR = "#E2E8F0", "#94A3B8"


class OutputRowDelegate(QStyledItemDelegate):
    """Draws one output as a card: picture, file name, then 'Step N · Technique · PNG'. A selected row lights up."""

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        return QSize(0, ROW_HEIGHT)  # the width follows the list

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus)  # the keyboard row, even when it is not picked

        card = QRect(option.rect).adjusted(2, 2, -2, -2)
        fill = SELECTED_FILL if selected else HOVER_FILL if hovered else ROW_FILL
        border = SELECTED_BORDER if selected or hovered else FOCUS_BORDER if focused else ROW_BORDER
        painter.setBrush(QColor(fill))
        painter.setPen(QPen(QColor(border), 1))
        painter.drawRoundedRect(card, 6, 6)

        thumb = QRect(card.left() + 8, card.center().y() - THUMB_SIZE // 2, THUMB_SIZE, THUMB_SIZE)
        painter.setBrush(QColor(THUMB_FILL))
        painter.setPen(QPen(QColor(THUMB_BORDER), 1))
        painter.drawRoundedRect(thumb, 4, 4)
        icon = index.data(THUMB_ROLE)
        if icon is not None:
            icon.paint(painter, thumb.adjusted(3, 3, -3, -3))

        left, width = thumb.right() + 12, card.right() - thumb.right() - 22
        name_font = QFont(option.font)
        name_font.setPixelSize(13)
        name_font.setWeight(QFont.Weight.DemiBold)
        detail_font = QFont(option.font)
        detail_font.setPixelSize(11)

        painter.setFont(name_font)
        painter.setPen(QColor(NAME_COLOR))
        name = QFontMetrics(name_font).elidedText(index.data(Qt.ItemDataRole.DisplayRole) or "",
                                                  Qt.TextElideMode.ElideMiddle, width)  # keep the end: .png / .mp3
        painter.drawText(QRect(left, card.top() + 8, width, 18), Qt.AlignmentFlag.AlignVCenter, name)

        step_text = index.data(STEP_ROLE) or ""
        painter.setFont(detail_font)
        painter.setPen(QColor(index.data(ACCENT_ROLE) or DETAIL_COLOR))
        painter.drawText(QRect(left, card.top() + 27, width, 16), Qt.AlignmentFlag.AlignVCenter, step_text)
        painter.setPen(QColor(DETAIL_COLOR))
        media_left = left + QFontMetrics(detail_font).horizontalAdvance(step_text)
        painter.drawText(QRect(media_left, card.top() + 27, max(0, left + width - media_left), 16),
                         Qt.AlignmentFlag.AlignVCenter, f" · {index.data(MEDIA_ROLE) or ''}")
        painter.restore()


def thumbnail_icon(output: StepOutputInfo) -> QIcon:
    """The picture of a PNG output (read from its source cover, small), otherwise the system icon of its file type."""
    path = output.preview_path
    if output.media_type == "png" and path and Path(path).is_file():
        reader = QImageReader(path)
        size = reader.size()
        if size.isValid():  # decode at a small size: a large cover is never loaded in full
            reader.setScaledSize(size.scaled(THUMB_SIZE * 2, THUMB_SIZE * 2, Qt.AspectRatioMode.KeepAspectRatio))
            image = reader.read()
            if not image.isNull():
                return QIcon(QPixmap.fromImage(image))
    icon = QFileIconProvider().icon(QFileInfo(output.display_name or f"output.{output.media_type}"))
    if icon.isNull():  # no system icon on this machine: the project's own file icon
        return QIcon(create_icon_pixmap(svg_path("file.svg"), DETAIL_COLOR, 24))
    return icon


class StepOutputPicker(QFrame):
    selection_changed = pyqtSignal(object)   # one pick: the StepOutput the user picked (None = nothing picked)
    selections_changed = pyqtSignal(object)  # multi_select: the list of StepOutputs picked, in list order

    def __init__(self, parent=None, *, multi_select: bool = False, empty_text: str = EMPTY_TEXT):
        super().__init__(parent)
        self.multi_select = multi_select
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Page 0: nothing to pick -> a dark panel with the message in the middle (same look as the empty pipeline canvas)
        self.empty_panel = QFrame()
        self.empty_panel.setObjectName("pipelineCanvas")
        empty_layout = QVBoxLayout(self.empty_panel)
        self.empty_label = QLabel(empty_text)  # each form says why its list can be empty
        self.empty_label.setObjectName("pipelineEmpty")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        empty_layout.addWidget(self.empty_label)

        # Page 1: the outputs to pick from
        self.output_list = QListWidget()
        self.output_list.setObjectName("stepOutputList")
        self.output_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.output_list.setItemDelegate(OutputRowDelegate(self.output_list))
        self.output_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.output_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.output_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.output_list.setSpacing(1)
        if multi_select:
            # Each click toggles a row, so several rows can be picked without Ctrl
            self.output_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
            self.output_list.itemSelectionChanged.connect(self.on_selections_changed)
        else:
            self.output_list.currentItemChanged.connect(self.on_selection_changed)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.empty_panel)
        self.pages.addWidget(self.output_list)
        layout.addWidget(self.pages, 1)

    def set_outputs(self, outputs: list[StepOutputInfo]) -> None:
        """Show the outputs to pick from (no outputs -> the empty panel with its message)."""
        with QSignalBlocker(self.output_list):  # refreshing the list is not a pick by the user
            self.output_list.clear()
            for output in outputs:
                technique = TECHNIQUE_DISPLAY[output.technique]
                step_text = f"Step {output.step_number} · {technique['label']}"
                item = QListWidgetItem(output.display_name or "")
                item.setData(REFERENCE_ROLE, output.reference)  # which output this row is
                item.setData(STEP_ROLE, step_text)
                item.setData(ACCENT_ROLE, technique["hex"])
                item.setData(MEDIA_ROLE, (output.media_type or "").upper())
                item.setData(THUMB_ROLE, thumbnail_icon(output))
                item.setToolTip(f"{output.display_name}\n{step_text}")  # the full name when it is cut in the middle
                self.output_list.addItem(item)
        self.pages.setCurrentIndex(1 if outputs else 0)  # 1 = list, 0 = empty panel

    def set_selection(self, reference) -> None:
        """Select the row of this output (None = no row) without emitting selection_changed (used when a step is loaded)."""
        with QSignalBlocker(self.output_list):
            self.output_list.setCurrentRow(-1)
            for row in range(self.output_list.count()):
                if self.output_list.item(row).data(REFERENCE_ROLE) == reference:
                    self.output_list.setCurrentRow(row)
                    break

    def selection(self):
        """The picked StepOutput, or None."""
        item = self.output_list.currentItem()
        return item.data(REFERENCE_ROLE) if item is not None else None

    def on_selection_changed(self, current, previous) -> None:
        self.selection_changed.emit(self.selection())

    def selected_outputs(self) -> list:
        """The picked StepOutputs (multi_select), in the order of the list."""
        return [
            self.output_list.item(row).data(REFERENCE_ROLE)
            for row in range(self.output_list.count())
            if self.output_list.item(row).isSelected()
        ]

    def set_selected_outputs(self, references: list) -> None:
        """Pick these outputs (multi_select) without emitting selections_changed (used when a step is loaded)."""
        with QSignalBlocker(self.output_list):
            self.output_list.clearSelection()
            for row in range(self.output_list.count()):
                item = self.output_list.item(row)
                if item.data(REFERENCE_ROLE) in references:
                    item.setSelected(True)

    def on_selections_changed(self) -> None:
        self.selections_changed.emit(self.selected_outputs())
