from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtWidgets import QAbstractItemView, QFrame, QLabel, QListWidget, QListWidgetItem, QVBoxLayout

from src.core.configurable.step_output import StepOutput, StepOutputInfo


class StepOutputPicker(QFrame):
    """Select expected outputs; these entries are not generated files yet."""

    selection_changed = pyqtSignal(object)
    selections_changed = pyqtSignal(object)

    def __init__(self, parent=None, *, multi_select=False):
        super().__init__(parent)
        self.multi_select = multi_select
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.hint_label = QLabel("No previous outputs available.")
        self.hint_label.setObjectName("hintLabel")
        self.hint_label.setWordWrap(True)
        layout.addWidget(self.hint_label)

        self.output_list = QListWidget()
        self.output_list.setObjectName("stepOutputList")
        self.output_list.setMinimumHeight(120)
        self.output_list.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.output_list, 1)
        if multi_select:
            # Each click toggles a row; selecting several rows does not require Ctrl.
            self.output_list.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
            self.output_list.itemSelectionChanged.connect(self.on_selections_changed)
        else:
            self.output_list.currentItemChanged.connect(self.on_selection_changed)

    def set_outputs(self, outputs: list[StepOutputInfo]):
        previous_selection = self.selection()
        previous_selections = self.selected_outputs()
        technique_names = {
            "lsbpp": "LSB++",
            "locomotive": "Locomotive",
            "metadata": "Metadata",
        }
        # Refresh labels without treating it as a user's selection.
        with QSignalBlocker(self.output_list):
            self.output_list.clear()
            for output in outputs:
                technique = technique_names.get(output.technique, output.technique)
                name = output.display_name or "Result"
                media = (output.media_type or "unknown").upper()
                text = f"Step {output.step_number} · {technique} · {name} [{media}]"
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, output.reference)
                item.setToolTip("Expected output; the pipeline has not generated this file yet.")
                self.output_list.addItem(item)
            self.output_list.setCurrentRow(-1)
        if self.multi_select:
            self.set_selected_outputs(previous_selections)
        else:
            self.set_selection(previous_selection)

        if outputs and self.multi_select:
            self.hint_label.setText("Click outputs to select or deselect. Manual files are kept.")
        elif outputs:
            self.hint_label.setText("Select an output from a preceding step.")
        else:
            self.hint_label.setText("No previous outputs available.")

    def selection(self) -> StepOutput | None:
        item = self.output_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.ItemDataRole.UserRole)

    def set_selection(self, reference: StepOutput | None):
        with QSignalBlocker(self.output_list):
            self.output_list.setCurrentRow(-1)
            for row in range(self.output_list.count()):
                item = self.output_list.item(row)
                if item.data(Qt.ItemDataRole.UserRole) == reference:
                    self.output_list.setCurrentRow(row)
                    break

    def on_selection_changed(self, current, previous):
        self.selection_changed.emit(self.selection())

    def selected_outputs(self) -> list[StepOutput]:
        references = []
        for row in range(self.output_list.count()):
            item = self.output_list.item(row)
            if item.isSelected():
                references.append(item.data(Qt.ItemDataRole.UserRole))
        return references

    def set_selected_outputs(self, references: list[StepOutput]):
        with QSignalBlocker(self.output_list):
            self.output_list.clearSelection()
            for row in range(self.output_list.count()):
                item = self.output_list.item(row)
                if item.data(Qt.ItemDataRole.UserRole) in references:
                    item.setSelected(True)

    def on_selections_changed(self):
        self.selections_changed.emit(self.selected_outputs())
