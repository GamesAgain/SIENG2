"""Tabbed MP3 metadata host shared by popup and inline step shells."""

from PyQt6.QtCore import QSize, pyqtSignal
from PyQt6.QtWidgets import QFrame, QScrollArea, QTabWidget, QVBoxLayout, QWidget

from config_prototype.gui.components.technique_forms.metadata.mp3_apic_drafts import (
    ApicImageDraft,
)
from config_prototype.gui.components.technique_forms.metadata.mp3_apic_form import (
    MP3ApicImagesForm,
)
from config_prototype.gui.components.technique_forms.metadata.mp3_frame_drafts import (
    MP3FrameDraft,
)
from config_prototype.gui.components.technique_forms.metadata.mp3_text_frames_form import (
    MP3TextFramesForm,
)
from config_prototype.gui.paths import ICON_DIR
from src.gui.components.gui_utils import create_icon_state


class MP3MetadataForm(QFrame):
    """Combine MP3 text frames and APIC images without page coupling."""

    changed = pyqtSignal()

    def __init__(
        self,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("techTabs")
        self.tabs.setIconSize(QSize(16, 16))

        self.text_frames_form = MP3TextFramesForm()
        self.apic_images_form = MP3ApicImagesForm()
        self.text_frames_form.changed.connect(self.changed.emit)
        self.apic_images_form.changed.connect(self._on_apic_changed)

        self.text_scroll = self._make_scroll_area(self.text_frames_form)
        self.apic_scroll = self._make_scroll_area(self.apic_images_form)
        self.tabs.addTab(
            self.text_scroll,
            create_icon_state(str(ICON_DIR / "text-size.svg")),
            "Text Frames",
        )
        self.tabs.addTab(
            self.apic_scroll,
            create_icon_state(str(ICON_DIR / "photo.svg")),
            "Attached Pictures [0]",
        )
        layout.addWidget(self.tabs)

    @staticmethod
    def _make_scroll_area(widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("mp3MetadataScroll")
        scroll.viewport().setObjectName("mp3MetadataViewport")
        scroll.setWidgetResizable(True)
        scroll.setWidget(widget)
        return scroll

    def _on_apic_changed(self) -> None:
        self.refresh_tab_labels()
        self.changed.emit()

    def refresh_tab_labels(self) -> None:
        self.tabs.setTabText(
            1,
            f"Attached Pictures [{self.apic_images_form.image_count()}]",
        )

    def load_draft(
        self,
        frames: list[MP3FrameDraft],
        apic_images: list[ApicImageDraft],
    ) -> None:
        self.text_frames_form.load_draft(frames)
        self.apic_images_form.load_draft(apic_images)
        self.refresh_tab_labels()
        self.tabs.setCurrentIndex(1 if apic_images and not frames else 0)

    def export_text_frames(self) -> list[MP3FrameDraft]:
        return self.text_frames_form.export_draft()

    def export_apic_images(self) -> list[ApicImageDraft]:
        return self.apic_images_form.export_draft()

    def clear_all(self) -> None:
        self.text_frames_form.clear_all()
        self.apic_images_form.clear_all()
        self.refresh_tab_labels()


__all__ = ["MP3MetadataForm"]
