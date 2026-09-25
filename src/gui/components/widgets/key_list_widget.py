from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel

class KeyListItemWidget(QFrame):
    def __init__(self, display_name: str, detail: str):
        super().__init__()
        self.setObjectName("keyListItemContent")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 3, 2, 3)
        layout.setSpacing(3)

        self.name_label = QLabel(display_name)
        self.name_label.setObjectName("keyListDisplayName")
        self.detail_label = QLabel(detail)
        self.detail_label.setObjectName("keyListSummary")
        self.name_label.setProperty("selected", False)
        self.detail_label.setProperty("selected", False)

        layout.addWidget(self.name_label)
        layout.addWidget(self.detail_label)

    def set_selected(self, selected: bool) -> None:
        for label in (self.name_label, self.detail_label):
            label.setProperty("selected", selected)
            label.style().unpolish(label)
            label.style().polish(label)