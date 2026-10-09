from PyQt6.QtWidgets import QAbstractItemView, QFrame, QLabel, QListWidget, QListWidgetItem, QStackedWidget, QVBoxLayout
from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal

from src.core.configurable.drafts import TECHNIQUE_LABELS
from src.core.configurable.step_output import StepOutputInfo

class StepOutputPicker(QFrame):
    selection_changed = pyqtSignal(object)   # one pick: the StepOutput the user picked (None = nothing picked)
    selections_changed = pyqtSignal(object)  # multi_select: the list of StepOutputs picked, in list order

    def __init__(self, parent=None, *, multi_select=False):
        super().__init__(parent)
        self.multi_select = multi_select
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Page 0: nothing to pick -> a dark panel with the message in the middle (same look as the empty pipeline canvas)
        self.empty_panel = QFrame()
        self.empty_panel.setObjectName("pipelineCanvas")
        empty_layout = QVBoxLayout(self.empty_panel)
        self.empty_label = QLabel("No previous outputs available.")
        self.empty_label.setObjectName("pipelineEmpty")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        empty_layout.addWidget(self.empty_label)

        # Page 1: the outputs to pick from
        self.output_list = QListWidget()
        self.output_list.setObjectName("stepOutputList")
        self.output_list.setCursor(Qt.CursorShape.PointingHandCursor)
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

    def set_outputs(self, outputs: list[StepOutputInfo]):
        """Show the outputs to pick from (no outputs -> the 'No previous outputs' panel)."""
        with QSignalBlocker(self.output_list):  # refreshing the list is not a pick by the user
            self.output_list.clear()
            for output in outputs:
                technique = TECHNIQUE_LABELS[output.technique]
                item = QListWidgetItem(f"Step {output.step_number} · {technique} · {output.display_name}")
                item.setData(Qt.ItemDataRole.UserRole, output.reference)  # which output this row is
                self.output_list.addItem(item)
        self.pages.setCurrentIndex(1 if outputs else 0)  # 1 = list, 0 = empty panel

    def set_selection(self, reference):
        """Select the row of this output (None = no row) without emitting selection_changed (used when a step is loaded)."""
        with QSignalBlocker(self.output_list):
            self.output_list.setCurrentRow(-1)
            for row in range(self.output_list.count()):
                if self.output_list.item(row).data(Qt.ItemDataRole.UserRole) == reference:
                    self.output_list.setCurrentRow(row)
                    break

    def selection(self):
        """The picked StepOutput, or None."""
        item = self.output_list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item is not None else None

    def on_selection_changed(self, current, previous):
        self.selection_changed.emit(self.selection())

    def selected_outputs(self) -> list:
        """The picked StepOutputs (multi_select), in the order of the list."""
        return [
            self.output_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.output_list.count())
            if self.output_list.item(row).isSelected()
        ]

    def set_selected_outputs(self, references: list):
        """Pick these outputs (multi_select) without emitting selections_changed (used when a step is loaded)."""
        with QSignalBlocker(self.output_list):
            self.output_list.clearSelection()
            for row in range(self.output_list.count()):
                item = self.output_list.item(row)
                if item.data(Qt.ItemDataRole.UserRole) in references:
                    item.setSelected(True)

    def on_selections_changed(self):
        self.selections_changed.emit(self.selected_outputs())
