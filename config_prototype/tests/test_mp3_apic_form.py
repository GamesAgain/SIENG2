"""Focused tests for the prototype MP3 attached-picture form."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QColor, QImage
from PyQt6.QtTest import QSignalSpy
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox

from config_prototype.core.configurable import StepOutput, StepOutputInfo
from config_prototype.gui.components import technique_forms
from config_prototype.gui.components.technique_forms.metadata import (
    APIC_DEFAULT_DESCRIPTIONS,
    APIC_DESCRIPTION_MAX_LENGTH,
    APIC_IMAGE_EXTENSIONS,
    ApicImageCard,
    ApicImageDraft,
    MP3ApicImagesForm,
    apic_draft_structure_error,
    default_apic_description,
)


_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def _write_image(
    path,
    color: str = "#38BDF8",
    *,
    width: int = 32,
    height: int = 24,
) -> None:
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    image_format = "JPEG" if path.suffix.lower() in {".jpg", ".jpeg"} else "PNG"
    assert image.save(str(path), image_format)


def test_apic_contract_is_public_and_uses_file_sources() -> None:
    draft = ApicImageDraft("front.png")

    assert draft.image == "front.png"
    assert draft.picture_type == 3
    assert draft.description == ""
    assert APIC_DESCRIPTION_MAX_LENGTH == 64
    assert len(APIC_DEFAULT_DESCRIPTIONS) == 21
    assert default_apic_description(3) == "Front cover"
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
        ([ApicImageDraft(12)], "must be file paths or step outputs"),
    ],
)
def test_apic_contract_rejects_invalid_structure(drafts, message) -> None:
    assert message in apic_draft_structure_error(drafts)


def test_linked_apic_source_round_trips_without_becoming_a_fake_path() -> None:
    _app()
    reference = StepOutput("step_ab123", "result")
    source = [ApicImageDraft(reference, 3, "Front cover")]
    form = MP3ApicImagesForm()

    form.load_draft(source)

    assert form.export_draft() == source
    assert form.export_draft()[0].image == reference
    assert len(form.cards) == 1
    assert form.draft_validation_error(form.export_draft()) is None
    assert "no longer available" in (form.linked_source_error(reference) or "")


def test_apic_form_starts_empty_with_production_style_controls() -> None:
    _app()
    form = MP3ApicImagesForm()

    assert form.image_count() == 0
    assert form.export_draft() == []
    assert form.count_badge.text() == "0"
    assert not form.cards_section.isVisible()
    assert form.type_combo.currentData() == 3
    assert form.description_input.text() == "Front cover"
    assert form.description_input.maxLength() == 64
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
            image=str(image_path),
            picture_type=3,
            description="Front artwork",
        )
    ]
    assert form.image_count() == 1
    assert form.count_badge.text() == "1"
    assert len(form.cards) == 1
    assert isinstance(form.cards[0], ApicImageCard)
    assert form.cards[0].draft.picture_type == 3
    assert form._pending_image is None
    assert form.type_combo.currentData() == 4
    assert form.description_input.text() == "Back cover"
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
    assert form.cards[0].draft.image == str(second_path)


def test_linked_picker_filters_png_and_adds_source_with_preview(tmp_path) -> None:
    _app()
    preview_path = tmp_path / "producer.png"
    _write_image(preview_path)
    png_reference = StepOutput("step_ab123", "result")
    mp3_reference = StepOutput("step_cd456", "result")
    png_info = StepOutputInfo(
        reference=png_reference,
        step_number=1,
        technique="lsbpp",
        media_type="png",
        preview_path=str(preview_path),
        display_name="Output 1",
    )
    form = MP3ApicImagesForm(
        output_catalog=[
            png_info,
            StepOutputInfo(
                reference=mp3_reference,
                step_number=2,
                technique="metadata",
                media_type="mp3",
            ),
        ]
    )

    form.source_mode_toggle.linked_button.click()
    form.output_picker._select_from_click(png_reference)

    assert form.output_picker.candidates() == [png_info]
    assert form.output_picker.preview_caption.text() == (
        "Source preview: producer.png"
    )
    assert form.confirm_add_image()
    assert form.export_draft() == [
        ApicImageDraft(png_reference, 3, "Front cover")
    ]
    card_text = {
        label.text() for label in form.cards[0].findChildren(QLabel)
    }
    assert "Step 1 · LSB++ · Output 1" in card_text
    assert "PNG - Source: producer.png" in card_text


def test_change_linked_apic_uses_existing_editor_and_preserves_collection() -> None:
    _app()
    first_reference = StepOutput("step_ab123", "result")
    second_reference = StepOutput("step_cd456", "result")
    catalog = [
        StepOutputInfo(first_reference, 1, "lsbpp", "png"),
        StepOutputInfo(second_reference, 2, "locomotive", "png"),
    ]
    form = MP3ApicImagesForm(output_catalog=catalog)
    form.load_draft(
        [ApicImageDraft(first_reference, 4, "Back artwork")]
    )

    form.begin_change_image(form.cards[0])
    form.output_picker._select_from_click(second_reference)

    assert form.add_form_title.text() == "Change Image"
    assert form.add_button.text() == "Save Changes"
    assert form.confirm_add_image()
    assert form.export_draft() == [
        ApicImageDraft(second_reference, 4, "Back artwork")
    ]
    assert form.add_form_title.text() == "Add New Image"

    form.remove_image(form.cards[0])
    assert form.export_draft() == []


def test_broken_linked_apic_is_preserved_and_shown_as_unavailable(
    monkeypatch,
) -> None:
    _app()
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    reference = StepOutput("step_missing", "result")
    draft = ApicImageDraft(reference, 3, "Front cover")
    form = MP3ApicImagesForm(
        dependency_errors={reference: "Source step no longer exists."}
    )

    form.load_draft([draft])
    form.begin_change_image(form.cards[0])

    assert form.export_draft() == [draft]
    assert form.output_picker.selected_output() == reference
    assert form.output_picker.unavailable_reason() == (
        "Source step no longer exists."
    )
    assert not form.validate_draft()
    assert warnings == ["Source step no longer exists."]


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
    form.load_draft([ApicImageDraft(str(first_path), 3, "")])
    form.image_drop_zone.add_files([str(second_path)])
    form.description_input.clear()

    assert not form.confirm_add_image()
    assert form.export_draft() == [
        ApicImageDraft(str(first_path), 3, "")
    ]


def test_picture_type_updates_generated_description_but_preserves_custom_text(
) -> None:
    _app()
    form = MP3ApicImagesForm()

    form.type_combo.setCurrentIndex(form.type_combo.findData(4))
    assert form.description_input.text() == "Back cover"

    form.description_input.setText("Artwork selected by the sender")
    form.type_combo.setCurrentIndex(form.type_combo.findData(7))
    assert form.description_input.text() == "Artwork selected by the sender"

    form.description_input.clear()
    form.type_combo.setCurrentIndex(form.type_combo.findData(8))
    assert form.description_input.text() == "Artist"


def test_used_picture_type_is_disabled_and_duplicate_type_is_rejected(
    tmp_path,
) -> None:
    _app()
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    _write_image(first_path)
    _write_image(second_path)
    form = MP3ApicImagesForm()
    form.load_draft([ApicImageDraft(str(first_path), 3, "Front")])

    type_index = form.type_combo.findData(3)
    type_item = form.type_combo.model().item(type_index)
    assert type_item is not None
    assert not type_item.isEnabled()
    assert form.type_combo.currentData() == 4

    error = form.draft_validation_error(
        [
            ApicImageDraft(str(first_path), 3, "Front"),
            ApicImageDraft(str(second_path), 3, "Another front"),
        ]
    )
    assert error is not None
    assert "picture type can be used only once" in error


def test_loaded_duplicate_types_are_preserved_for_validation(tmp_path) -> None:
    _app()
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    _write_image(first_path)
    _write_image(second_path)
    drafts = [
        ApicImageDraft(str(first_path), 3, "Front one"),
        ApicImageDraft(str(second_path), 3, "Front two"),
    ]
    form = MP3ApicImagesForm()

    form.load_draft(drafts)

    assert form.export_draft() == drafts
    assert form.draft_validation_error(form.export_draft()) is not None


@pytest.mark.parametrize(
    ("descriptions", "message"),
    [
        (("Front cover", " front COVER "), "must be unique"),
        (("A" * 65, "Back cover"), "cannot exceed 64"),
    ],
)
def test_description_rules_are_trimmed_casefolded_and_length_limited(
    tmp_path,
    descriptions,
    message,
) -> None:
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    _write_image(first_path)
    _write_image(second_path)

    error = MP3ApicImagesForm.draft_validation_error(
        [
            ApicImageDraft(str(first_path), 3, descriptions[0]),
            ApicImageDraft(str(second_path), 4, descriptions[1]),
        ]
    )

    assert error is not None
    assert message in error


def test_type_one_requires_real_32_by_32_png(tmp_path) -> None:
    valid_icon = tmp_path / "valid.png"
    wrong_size = tmp_path / "wide.png"
    jpeg_icon = tmp_path / "icon.jpg"
    _write_image(valid_icon, width=32, height=32)
    _write_image(wrong_size, width=32, height=24)
    _write_image(jpeg_icon, width=32, height=32)

    assert (
        MP3ApicImagesForm.draft_validation_error(
            [ApicImageDraft(str(valid_icon), 1, "File icon")]
        )
        is None
    )
    assert "exactly 32 x 32" in (
        MP3ApicImagesForm.draft_validation_error(
            [ApicImageDraft(str(wrong_size), 1, "File icon")]
        )
        or ""
    )
    assert "must use PNG" in (
        MP3ApicImagesForm.draft_validation_error(
            [ApicImageDraft(str(jpeg_icon), 1, "File icon")]
        )
        or ""
    )
