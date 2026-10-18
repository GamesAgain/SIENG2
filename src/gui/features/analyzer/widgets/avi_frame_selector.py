"""Shared AVI frame navigation for detector detail views."""

from bisect import bisect_left

from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
)


class AVIFrameSelector(QFrame):
    """Navigate analyzed AVI frames without decoding the file again."""

    frame_changed = pyqtSignal(int)

    def __init__(self, frames, selected_frame: int | None, parent=None):
        super().__init__(parent)
        self.frames = tuple(frames)
        if not self.frames:
            raise ValueError("AVIFrameSelector requires at least one frame.")

        self.frame_indexes = tuple(frame.frame_index for frame in self.frames)
        self.setObjectName("analysisFrameSelector")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(9, 7, 9, 7)
        layout.setSpacing(7)

        label = QLabel("Frame:")
        label.setObjectName("analysisFrameLabel")
        self.previous_button = QPushButton("‹")
        self.previous_button.setObjectName("analysisFrameStep")
        self.next_button = QPushButton("›")
        self.next_button.setObjectName("analysisFrameStep")

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName("analysisFrameSlider")
        self.slider.setRange(0, len(self.frames) - 1)
        # Rebuilding a detector view can include hundreds of table rows.
        # Emit once when the user releases the handle instead of on every
        # pixel while dragging through a long video.
        self.slider.setTracking(False)
        self.spinbox = QSpinBox()
        self.spinbox.setObjectName("analysisFrameSpinBox")
        self.spinbox.setRange(
            self.frame_indexes[0],
            self.frame_indexes[-1],
        )
        self.time_label = QLabel()
        self.time_label.setObjectName("analysisFrameTime")

        layout.addWidget(label)
        layout.addWidget(self.previous_button)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.next_button)
        layout.addWidget(self.spinbox)
        layout.addWidget(self.time_label)

        self.previous_button.clicked.connect(
            lambda: self._set_position(self.slider.value() - 1, True)
        )
        self.next_button.clicked.connect(
            lambda: self._set_position(self.slider.value() + 1, True)
        )
        self.slider.valueChanged.connect(
            lambda position: self._set_position(position, True)
        )
        self.spinbox.valueChanged.connect(self._select_frame_number)

        initial = self._nearest_position(
            self.frame_indexes[0]
            if selected_frame is None
            else selected_frame
        )
        self._set_position(initial, False)

    def _nearest_position(self, frame_index: int) -> int:
        position = bisect_left(self.frame_indexes, frame_index)
        if position >= len(self.frame_indexes):
            return len(self.frame_indexes) - 1
        if position > 0:
            before = self.frame_indexes[position - 1]
            after = self.frame_indexes[position]
            if frame_index - before <= after - frame_index:
                return position - 1
        return position

    def _select_frame_number(self, frame_index: int) -> None:
        self._set_position(self._nearest_position(frame_index), True)

    def set_selected_frame(self, frame_index: int) -> None:
        """Synchronize every control without emitting another selection."""
        self._set_position(self._nearest_position(frame_index), False)

    def _set_position(self, position: int, emit: bool) -> None:
        position = max(0, min(position, len(self.frames) - 1))
        frame = self.frames[position]
        with QSignalBlocker(self.slider), QSignalBlocker(self.spinbox):
            self.slider.setValue(position)
            self.spinbox.setValue(frame.frame_index)
        self.time_label.setText(
            f"{frame.timestamp_seconds:.3f} s  •  "
            f"{position + 1}/{len(self.frames)}"
        )
        self.previous_button.setEnabled(position > 0)
        self.next_button.setEnabled(position < len(self.frames) - 1)
        if emit:
            self.frame_changed.emit(frame.frame_index)
