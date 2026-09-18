from collections.abc import Iterable
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from config_prototype.core.configurable import StepOutput, StepOutputInfo
from config_prototype.gui.components.step_card import TECHNIQUE_DISPLAY


STEP_COLUMN_WIDTH = 64
TECHNIQUE_COLUMN_WIDTH = 120
OUTPUT_ROW_MIN_HEIGHT = 34
OUTPUT_LIST_MAX_HEIGHT = 300


def output_display_name(output_key: str) -> str:
    if output_key == "result":
        return "Output 1"
    if output_key.startswith("output_"):
        suffix = output_key.removeprefix("output_")
        if suffix.isdigit():
            return f"Output {suffix}"
        return "Output"
    return output_key.replace("_", " ").title()


def output_info_display_name(output_info: StepOutputInfo) -> str:
    return output_info.display_name or output_display_name(
        output_info.reference.output_key
    )


class StepOutputRow(QFrame):
    clicked = pyqtSignal(object)

    def __init__(
        self,
        output_info: StepOutputInfo,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.output_info = output_info
        presentation = TECHNIQUE_DISPLAY[output_info.technique]

        self.setObjectName("stepOutputRow")
        self.setProperty("accentColor", presentation["accent"])
        self.setProperty("selected", False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumHeight(OUTPUT_ROW_MIN_HEIGHT)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(8)

        step_label = QLabel(f"Step {output_info.step_number}")
        step_label.setObjectName("stepOutputCellStep")
        step_label.setFixedWidth(STEP_COLUMN_WIDTH)

        technique_label = QLabel(presentation["label"])
        technique_label.setObjectName("stepOutputCellModule")
        technique_label.setProperty(
            "accentColor",
            presentation["accent"],
        )
        technique_label.setFixedWidth(TECHNIQUE_COLUMN_WIDTH)

        output_text = output_info_display_name(output_info)
        if output_info.media_type:
            output_text += f"  [{output_info.media_type.upper()}]"
        output_label = QLabel(output_text)
        output_label.setObjectName("stepOutputCellOutput")

        layout.addWidget(step_label)
        layout.addWidget(technique_label)
        layout.addWidget(output_label, 1)

        source_name = (
            Path(output_info.preview_path).name
            if output_info.preview_path
            else "Preview unavailable"
        )
        self.setToolTip(
            f"Source cover: {source_name}\n"
            f"Produced by Step {output_info.step_number} · "
            f"{presentation['label']}"
        )
        self.setAccessibleName(
            f"Step {output_info.step_number}, {presentation['label']}, "
            f"{output_info_display_name(output_info)}"
        )

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.output_info.reference)
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space}:
            self.clicked.emit(self.output_info.reference)
            event.accept()
            return
        super().keyPressEvent(event)


class StepOutputPicker(QFrame):
    """Select one typed output reference from an earlier pipeline step."""

    selection_changed = pyqtSignal(object)
    selections_changed = pyqtSignal(object)
    minimum_height_changed = pyqtSignal(int)

    def __init__(
        self,
        candidates: Iterable[StepOutputInfo] = (),
        *,
        multiple: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.multiple = multiple
        self.setObjectName("stepOutputPicker")
        self._candidates: list[StepOutputInfo] = []
        self._rows: list[StepOutputRow] = []
        self._selected_output: StepOutput | None = None
        self._selected_outputs: list[StepOutput] = []
        self._unavailable_reason: str | None = None
        self._unavailable_reasons: dict[StepOutput, str] = {}

        self.content_layout = QVBoxLayout(self)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(4)

        self.header = self._build_header()
        self.empty_label = QLabel(
            "No compatible previous output is available yet."
        )
        self.empty_label.setObjectName("hintLabel")
        self.empty_label.setWordWrap(True)

        self.content_layout.addWidget(self.header)

        self.output_scroll = QScrollArea()
        self.output_scroll.setObjectName("stepOutputScroll")
        self.output_scroll.setWidgetResizable(True)
        self.output_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.output_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.output_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.output_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self.output_scroll_content = QWidget()
        self.output_scroll_content.setObjectName("stepOutputScrollContent")
        self.output_layout = QVBoxLayout(self.output_scroll_content)
        self.output_layout.setContentsMargins(0, 0, 0, 0)
        self.output_layout.setSpacing(4)
        self.output_layout.setSizeConstraint(
            QLayout.SizeConstraint.SetMinAndMaxSize
        )

        self.output_layout.addWidget(self.empty_label)
        self.unavailable_frame = self._build_unavailable_state()
        self.output_layout.addWidget(self.unavailable_frame)
        self.preview_frame = self._build_preview()
        self.output_layout.addWidget(self.preview_frame)
        self.output_scroll.setWidget(self.output_scroll_content)
        self.content_layout.addWidget(self.output_scroll)
        self.content_layout.addStretch()
        self.set_candidates(candidates)

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("stepOutputHeader")
        header.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        layout = QHBoxLayout(header)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)
        for text, width in (
            ("STEP", STEP_COLUMN_WIDTH),
            ("TECHNIQUE", TECHNIQUE_COLUMN_WIDTH),
            ("OUTPUT", None),
        ):
            label = QLabel(text)
            label.setObjectName("stepOutputHeaderCell")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if width is None:
                layout.addWidget(label, 1)
            else:
                label.setFixedWidth(width)
                layout.addWidget(label)
        return header

    def _build_unavailable_state(self) -> QFrame:
        unavailable = QFrame()
        unavailable.setObjectName("stepOutputUnavailable")
        layout = QVBoxLayout(unavailable)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)

        self.unavailable_title = QLabel("Linked source unavailable")
        self.unavailable_title.setObjectName("stepOutputUnavailableTitle")

        self.unavailable_detail = QLabel()
        self.unavailable_detail.setObjectName("stepOutputUnavailableDetail")
        self.unavailable_detail.setWordWrap(True)

        layout.addWidget(self.unavailable_title)
        layout.addWidget(self.unavailable_detail)
        unavailable.hide()
        return unavailable

    def _build_preview(self) -> QFrame:
        preview = QFrame()
        preview.setObjectName("stepOutputPreview")
        layout = QVBoxLayout(preview)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)

        self.preview_image = QLabel()
        self.preview_image.setObjectName("stepOutputPreviewImage")
        self.preview_image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_image.setMinimumHeight(150)

        self.preview_caption = QLabel()
        self.preview_caption.setObjectName("stepOutputPreviewCaption")
        self.preview_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.preview_note = QLabel(
            "Actual output is created when the pipeline runs."
        )
        self.preview_note.setObjectName("stepOutputPreviewNote")
        self.preview_note.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.preview_image)
        layout.addWidget(self.preview_caption)
        layout.addWidget(self.preview_note)
        preview.hide()
        return preview

    def set_candidates(
        self,
        candidates: Iterable[StepOutputInfo],
    ) -> None:
        for row in self._rows:
            self.output_layout.removeWidget(row)
            row.deleteLater()
        self._rows.clear()
        self._candidates = list(candidates)

        for output_info in self._candidates:
            row = StepOutputRow(output_info, self.output_scroll_content)
            row.set_selected(
                output_info.reference == self._selected_output
            )
            row.clicked.connect(self._select_from_click)
            self.output_layout.insertWidget(
                self.output_layout.indexOf(self.preview_frame),
                row,
            )
            self._rows.append(row)

        has_candidates = bool(self._candidates)
        self.header.setVisible(has_candidates)
        self._refresh_unavailable_state()
        self._refresh_preview()
        self._refresh_scroll_height()

    def candidates(self) -> list[StepOutputInfo]:
        return list(self._candidates)

    def selected_output(self) -> StepOutput | None:
        return self._selected_output

    def selected_outputs(self) -> list[StepOutput]:
        return list(self._selected_outputs)

    def set_selected_output(
        self,
        reference: StepOutput | None,
    ) -> None:
        self._selected_output = reference
        self._selected_outputs = [reference] if reference is not None else []
        self._refresh_selection()
        self._refresh_unavailable_state()
        self._refresh_preview()
        self._refresh_scroll_height()

    def set_selected_outputs(
        self,
        references: Iterable[StepOutput],
    ) -> None:
        selected = list(dict.fromkeys(references))
        self._selected_outputs = selected
        self._selected_output = selected[-1] if selected else None
        self._refresh_selection()
        self._refresh_unavailable_state()
        self._refresh_preview()
        self._refresh_scroll_height()

    def clear_selection(self) -> None:
        self.set_selected_output(None)

    def set_unavailable_reason(self, reason: str | None) -> None:
        self._unavailable_reason = reason
        if self._selected_output is not None:
            if reason is None:
                self._unavailable_reasons.pop(self._selected_output, None)
            else:
                self._unavailable_reasons[self._selected_output] = reason
        self._refresh_unavailable_state()
        self._refresh_scroll_height()

    def unavailable_reason(self) -> str | None:
        return self._unavailable_reason

    def set_unavailable_reasons(
        self,
        reasons: dict[StepOutput, str],
    ) -> None:
        self._unavailable_reasons = dict(reasons)
        self._refresh_unavailable_state()
        self._refresh_scroll_height()

    def _select_from_click(self, reference: StepOutput) -> None:
        if self.multiple:
            if reference in self._selected_outputs:
                self._selected_outputs.remove(reference)
                if self._selected_output == reference:
                    self._selected_output = (
                        self._selected_outputs[-1]
                        if self._selected_outputs
                        else None
                    )
            else:
                self._selected_outputs.append(reference)
                self._selected_output = reference
            self._unavailable_reasons.pop(reference, None)
            self._unavailable_reason = None
            self._refresh_selection()
            self._refresh_unavailable_state()
            self._refresh_preview()
            self._refresh_scroll_height()
            self.selections_changed.emit(self.selected_outputs())
            return

        self._selected_output = reference
        self._selected_outputs = [reference]
        self._unavailable_reason = None
        self._refresh_selection()
        self._refresh_unavailable_state()
        self._refresh_preview()
        self._refresh_scroll_height()
        self.selection_changed.emit(reference)

    def _refresh_selection(self) -> None:
        for row in self._rows:
            row.set_selected(
                row.output_info.reference in self._selected_outputs
                if self.multiple
                else row.output_info.reference == self._selected_output
            )

    def _refresh_unavailable_state(self) -> None:
        if self.multiple:
            candidate_references = {
                output.reference for output in self._candidates
            }
            reasons: list[str] = []
            for reference in self._selected_outputs:
                reason = self._unavailable_reasons.get(reference)
                if reason is None and reference not in candidate_references:
                    reason = "A saved output is no longer available."
                if reason and reason not in reasons:
                    reasons.append(reason)

            show_unavailable = bool(reasons)
            self.unavailable_frame.setVisible(show_unavailable)
            if show_unavailable:
                self.unavailable_detail.setText(
                    "\n".join(reasons) + " Select another previous output."
                )
            else:
                self.unavailable_detail.clear()
            self.empty_label.setVisible(
                not self._candidates and not show_unavailable
            )
            return

        selected_is_available = any(
            output.reference == self._selected_output
            for output in self._candidates
        )
        reason = self._unavailable_reason
        if (
            self._selected_output is not None
            and not selected_is_available
            and reason is None
        ):
            reason = "The saved output is no longer available."

        show_unavailable = self._selected_output is not None and bool(reason)
        self.unavailable_frame.setVisible(show_unavailable)
        if show_unavailable:
            self.unavailable_detail.setText(
                f"{reason} Select another previous output."
            )
        else:
            self.unavailable_detail.clear()
        self.empty_label.setVisible(
            not self._candidates and not show_unavailable
        )

    def _refresh_preview(self) -> None:
        selected_info = next(
            (
                output
                for output in self._candidates
                if output.reference == self._selected_output
            ),
            None,
        )
        self.preview_frame.setVisible(selected_info is not None)
        if selected_info is None:
            self.preview_image.clear()
            self.preview_caption.clear()
            return

        selected_row = next(
            row
            for row in self._rows
            if row.output_info.reference == selected_info.reference
        )
        self.output_layout.removeWidget(self.preview_frame)
        self.output_layout.insertWidget(
            self.output_layout.indexOf(selected_row) + 1,
            self.preview_frame,
        )

        preview_path = selected_info.preview_path
        source_name = Path(preview_path).name if preview_path else "Unknown"
        self.preview_caption.setText(f"Source preview: {source_name}")

        pixmap = QPixmap(preview_path) if preview_path else QPixmap()
        if pixmap.isNull():
            self.preview_image.setPixmap(QPixmap())
            self.preview_image.setText("Image preview unavailable")
            return

        self.preview_image.setText("")
        self.preview_image.setPixmap(
            pixmap.scaled(
                300,
                170,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _refresh_scroll_height(self) -> None:
        """Fit short lists and cap long lists without compressing their rows."""
        self.output_layout.activate()
        visible_widgets = [
            item.widget()
            for index in range(self.output_layout.count())
            if (item := self.output_layout.itemAt(index)).widget() is not None
            and not item.widget().isHidden()
        ]
        margins = self.output_layout.contentsMargins()
        content_height = margins.top() + margins.bottom()
        content_height += sum(
            max(widget.minimumHeight(), widget.sizeHint().height())
            for widget in visible_widgets
        )
        if visible_widgets:
            content_height += self.output_layout.spacing() * (
                len(visible_widgets) - 1
            )

        frame_height = self.output_scroll.frameWidth() * 2
        target_height = min(
            max(content_height + frame_height, OUTPUT_ROW_MIN_HEIGHT),
            OUTPUT_LIST_MAX_HEIGHT,
        )
        self.output_scroll.setFixedHeight(target_height)

        layout_margins = self.content_layout.contentsMargins()
        picker_height = (
            layout_margins.top()
            + layout_margins.bottom()
            + target_height
        )
        if not self.header.isHidden():
            picker_height += max(
                self.header.minimumHeight(),
                self.header.sizeHint().height(),
            )
            picker_height += self.content_layout.spacing()

        height_changed = self.minimumHeight() != picker_height
        self.setMinimumHeight(picker_height)
        self.updateGeometry()
        if height_changed:
            self.minimum_height_changed.emit(picker_height)
