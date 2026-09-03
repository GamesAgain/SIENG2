"""Focused tests for the prototype MP3 attached-picture form."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QImage
from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import QApplication, QMessageBox

from config_prototype.gui.components import technique_forms
from config_prototype.gui.components.technique_forms.metadata import (
    APIC_IMAGE_EXTENSIONS,
    ApicImageCard,
    ApicImageDraft,
    MP3ApicImagesForm,
    apic_draft_structure_error,
)


_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def _write_image(path, color: str = "#38BDF8") -> None:
    image = QImage(32, 24, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    image_format = "JPEG" if path.suffix.lower() in {".jpg", ".jpeg"} else "PNG"
    assert image.save(str(path), image_format)


def test_apic_contract_is_public_and_uses_manual_file_references() -> None:
    draft = ApicImageDraft("front.png")

    assert draft.picture_type == 3
    assert draft.description == ""
    assert APIC_IMAGE_EXTENSIONS == frozenset({".jpg", ".jpeg", ".png"})
    assert technique_forms.ApicImageDraft is ApicImageDraft
    assert technique_forms.MP3ApicImagesForm is MP3ApicImagesForm
    assert apic_draft_structure_error([draft]) is None


@pytest.mark.parametrize(
    ("drafts", "message"),
    [
        ("not a list", "must be a list"),
        ([object()], "unsupported item"),
        ([ApicImageDraft("front.png", 99)], "Unsupported APIC picture type"),
        ([ApicImageDraft(12)], "paths must be text"),
    ],
)
def test_apic_contract_rejects_invalid_structure(drafts, message) -> None:
    assert message in apic_draft_structure_error(drafts)


def test_apic_form_starts_empty_with_production_style_controls() -> None:
    _app()
    form = MP3ApicImagesForm()

    assert form.image_count() == 0
    assert form.export_draft() == []
    assert form.count_badge.text() == "0"
    assert not form.cards_section.isVisible()
    assert form.type_combo.currentData() == 3
    assert form.image_drop_zone.file_exts == [".jpeg", ".jpg", ".png"]
    assert form.image_drop_zone.is_single_mode
    assert form.add_button.text() == "+ Add Image"


def test_add_image_exports_type_description_and_builds_card(tmp_path) -> None:
    _app()
    image_path = tmp_path / "front.png"
    _write_image(image_path)
    form = MP3ApicImagesForm()
    changed = QSignalSpy(form.changed)

    form.image_drop_zone.add_files([str(image_path)])
    form.type_combo.setCurrentIndex(form.type_combo.findData(3))
    form.description_input.setText("Front artwork")

    assert form.confirm_add_image()
    assert form.export_draft() == [
        ApicImageDraft(
            image_path=str(image_path),
            picture_type=3,
            description="Front artwork",
        )
    ]
    assert form.image_count() == 1
    assert form.count_badge.text() == "1"
    assert len(form.cards) == 1
    assert isinstance(form.cards[0], ApicImageCard)
    assert form.cards[0].draft.picture_type == 3
    assert form._pending_image_path is None
    assert form.description_input.text() == ""
    assert len(changed) == 1


def test_change_image_preserves_type_and_description(tmp_path) -> None:
    _app()
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.jpg"
    _write_image(first_path)
    _write_image(second_path, "#A78BFA")
    form = MP3ApicImagesForm()
    form.load_draft(
        [ApicImageDraft(str(first_path), 4, "Back artwork")]
    )

    assert form.replace_image(form.cards[0], str(second_path))

    assert form.export_draft() == [
        ApicImageDraft(str(second_path), 4, "Back artwork")
    ]
    assert form.cards[0].draft.image_path == str(second_path)


def test_remove_image_and_clear_restore_empty_collection(tmp_path) -> None:
    _app()
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    _write_image(first_path)
    _write_image(second_path)
    form = MP3ApicImagesForm()
    form.load_draft(
        [
            ApicImageDraft(str(first_path), 3, "Front"),
            ApicImageDraft(str(second_path), 4, "Back"),
        ]
    )

    form.remove_image(form.cards[0])

    assert form.export_draft() == [
        ApicImageDraft(str(second_path), 4, "Back")
    ]
    assert form.count_badge.text() == "1"

    form.clear_all()

    assert form.export_draft() == []
    assert form.cards == []
    assert form.count_badge.text() == "0"


def test_load_and_export_are_detached_from_caller_state(tmp_path) -> None:
    _app()
    image_path = tmp_path / "front.png"
    _write_image(image_path)
    source = [ApicImageDraft(str(image_path), 3, "Front")]
    form = MP3ApicImagesForm()

    form.load_draft(source)
    source[0].description = "Changed outside"
    exported = form.export_draft()
    exported[0].description = "Changed export"

    assert form.export_draft() == [
        ApicImageDraft(str(image_path), 3, "Front")
    ]


def test_validation_rejects_missing_unreadable_and_duplicate_images(
    tmp_path,
    monkeypatch,
) -> None:
    _app()
    valid_image = tmp_path / "valid.png"
    second_image = tmp_path / "second.png"
    unreadable = tmp_path / "broken.png"
    _write_image(valid_image)
    _write_image(second_image)
    unreadable.write_bytes(b"not an image")
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    form = MP3ApicImagesForm()

    invalid_collections = [
        (
            [ApicImageDraft(str(tmp_path / "missing.png"))],
            "APIC image is unavailable: missing.png",
        ),
        (
            [ApicImageDraft(str(unreadable))],
            "APIC image cannot be read: broken.png",
        ),
        (
            [
                ApicImageDraft(str(valid_image), 3, "Same"),
                ApicImageDraft(str(second_image), 4, "Same"),
            ],
            "APIC descriptions must be unique",
        ),
    ]
    for drafts, expected_message in invalid_collections:
        form.load_draft(drafts)
        warnings.clear()
        assert not form.validate_draft()
        assert expected_message in warnings[0]


def test_second_empty_description_is_rejected_without_mutating_collection(
    tmp_path,
    monkeypatch,
) -> None:
    _app()
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    _write_image(first_path)
    _write_image(second_path)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: None)
    form = MP3ApicImagesForm()
    form.load_draft([ApicImageDraft(str(first_path))])
    form.image_drop_zone.add_files([str(second_path)])

    assert not form.confirm_add_image()
    assert form.export_draft() == [ApicImageDraft(str(first_path))]

