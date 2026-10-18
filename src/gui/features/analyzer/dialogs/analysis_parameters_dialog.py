"""Dialog for editing bit-statistics analysis parameters."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.core.analyzer.parameters import AnalysisParameters


class AnalysisParametersDialog(QDialog):
    """Edit parameters and publish them only after a valid save."""

    def __init__(self, parameters: AnalysisParameters, parent=None):
        super().__init__(parent)
        self.setObjectName("analysisParametersDialog")
        self.setWindowTitle("Analysis Parameters")
        self.setModal(True)
        self.setMinimumWidth(650)
        self._parameters = parameters
        self._setup_ui(parameters)

    @property
    def parameters(self) -> AnalysisParameters:
        """Return the original values or the last successfully saved values."""
        return self._parameters

    def _setup_ui(self, parameters: AnalysisParameters) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 10, 22, 16)
        layout.setSpacing(14)

        title_label = QLabel("Analysis Parameters")
        title_label.setObjectName("analysisParameterTitle")
        layout.addWidget(title_label)

        description_label = QLabel(
            "Applied to the next analysis. Existing results keep the settings "
            "used when they were generated."
        )
        description_label.setObjectName("analysisParameterDescription")
        description_label.setWordWrap(True)
        layout.addWidget(description_label)

        form = QGridLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)

        self.min_expected_input = QDoubleSpinBox()
        self.min_expected_input.setRange(5.0, 1_000_000.0)
        self.min_expected_input.setDecimals(2)
        self.min_expected_input.setValue(parameters.min_expected)

        self.prefix_step_input = QSpinBox()
        self.prefix_step_input.setRange(1, 100)
        self.prefix_step_input.setValue(parameters.prefix_step)

        self.segment_percent_input = QSpinBox()
        self.segment_percent_input.setRange(1, 100)
        self.segment_percent_input.setValue(parameters.segment_percent)

        self.segment_step_input = QSpinBox()
        self.segment_step_input.setRange(1, 100)
        self.segment_step_input.setValue(parameters.segment_step)

        self.spa_j_input = QSpinBox()
        self.spa_j_input.setRange(0, 126)
        self.spa_j_input.setValue(parameters.spa_j)
        self.spa_j_input.setToolTip(
            "Pool SPA trace sets from m = 0 through j."
        )

        self.spa_min_pairs_input = QSpinBox()
        self.spa_min_pairs_input.setRange(1, 10_000_000)
        self.spa_min_pairs_input.setValue(parameters.spa_min_pairs)
        self.spa_min_pairs_input.setToolTip(
            "Minimum pair count required before SPA estimates a payload."
        )

        fields = (
            ("Chi-square min expected", self.min_expected_input, 0, 0),
            ("Prefix step (%)", self.prefix_step_input, 0, 1),
            ("Segment length (%)", self.segment_percent_input, 1, 0),
            ("Segment step (%)", self.segment_step_input, 1, 1),
            ("SPA pooling j", self.spa_j_input, 2, 0),
            ("SPA min-pair guard", self.spa_min_pairs_input, 2, 1),
        )
        for label_text, input_widget, row, column in fields:
            form.addWidget(
                self._build_field(label_text, input_widget),
                row,
                column,
            )

        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 1)
        layout.addLayout(form)

        note_label = QLabel(
            "RS uses the fixed mask (0, 1, 1, 0). "
            "WAV RS currently analyzes mono PCM16 audio."
        )
        note_label.setObjectName("analysisParameterNote")
        note_label.setWordWrap(True)
        layout.addWidget(note_label)

        self.error_label = QLabel()
        self.error_label.setObjectName("analysisParameterError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("SecondaryBtn")
        cancel_button.clicked.connect(self.reject)

        self.save_button = QPushButton("Save Parameters")
        self.save_button.setObjectName("PrimaryActionBtn")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._save_parameters)

        for button in (cancel_button, self.save_button):
            button.setFixedHeight(36)

        button_layout.addWidget(cancel_button)
        button_layout.addWidget(self.save_button)
        layout.addLayout(button_layout)

    @staticmethod
    def _build_field(
        label_text: str,
        input_widget: QAbstractSpinBox,
    ) -> QWidget:
        field = QWidget()
        field.setObjectName("analysisParameterField")
        field_layout = QVBoxLayout(field)
        field_layout.setContentsMargins(0, 0, 0, 0)
        field_layout.setSpacing(5)

        label = QLabel(label_text)
        label.setObjectName("analysisParameterLabel")
        input_widget.setObjectName("analysisParameterInput")
        input_widget.setButtonSymbols(
            QAbstractSpinBox.ButtonSymbols.NoButtons
        )

        field_layout.addWidget(label)
        field_layout.addWidget(input_widget)
        return field

    def _save_parameters(self) -> None:
        parameters = AnalysisParameters(
            min_expected=self.min_expected_input.value(),
            prefix_step=self.prefix_step_input.value(),
            segment_percent=self.segment_percent_input.value(),
            segment_step=self.segment_step_input.value(),
            spa_j=self.spa_j_input.value(),
            spa_min_pairs=self.spa_min_pairs_input.value(),
        )

        try:
            parameters.validate()
        except ValueError as exc:
            self.error_label.setText(str(exc))
            self.error_label.show()
            if parameters.segment_step > parameters.segment_percent:
                self.segment_step_input.setFocus(
                    Qt.FocusReason.OtherFocusReason
                )
            return

        self.error_label.hide()
        self._parameters = parameters
        self.accept()
