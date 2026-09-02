"""Focused tests for prototype PNG metadata field widgets."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget

from config_prototype.gui.components.technique_forms.metadata import (
    PNGCustomRow,
    PNGStandardField,
)
from src.core.stego.metadata_handlers.png_handler import MAX_KEYWORD_LENGTH


_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_standard_field_uses_keyword_identity_and_shared_qss_names() -> None:
    _app()
    parent = QWidget()
    field = PNGStandardField("Title", parent=parent)

    assert field.parent() is parent
    assert field.keyword == "Title"
    assert field.name_label.text() == "Title"
    assert field.name_label.objectName() == "formLabel"
    assert field.keyword_badge.text() == "Title"
    assert field.keyword_badge.objectName() == "fileInfoBadge"
    assert field.keyword_badge.property("badgeColor") == "neutral"
    assert field.value_input.objectName() == "formInput"


def test_standard_field_value_api_normalizes_empty_and_trimmed_values() -> None:
    _app()
    field = PNGStandardField("Author")

    assert field.is_empty()
    field.set_value("  Alice  ")
    assert field.value_input.text() == "  Alice  "
    assert field.get_value() == "Alice"
    assert not field.is_empty()

    field.set_value(None)
    assert field.get_value() == ""
    assert field.is_empty()


def test_standard_field_falls_back_to_unknown_keyword_as_its_label() -> None:
    _app()
    field = PNGStandardField("Project Code")

    assert field.name_label.text() == "Project Code"
    assert field.keyword_badge.text() == "Project Code"


def test_custom_row_exposes_editable_keyword_and_value() -> None:
    _app()
    parent = QWidget()
    row = PNGCustomRow(
        "  Secret Key  ",
        "  Secret Value  ",
        parent=parent,
    )

    assert row.parent() is parent
    assert row.objectName() == "fileItemRow"
    assert row.title_label.objectName() == "fileItemName"
    assert row.keyword_input.objectName() == "formInput"
    assert row.value_input.objectName() == "formInput"
    assert row.keyword_input.placeholderText() == "keyword"
    assert row.value_input.placeholderText() == "value"
    assert row.keyword_input.maxLength() == MAX_KEYWORD_LENGTH
    assert row.keyword_input.width() == 220
    assert row.get_keyword() == "Secret Key"
    assert row.get_value() == "Secret Value"
    assert not row.is_empty()


def test_custom_row_without_keyword_is_empty_even_if_value_exists() -> None:
    _app()
    row = PNGCustomRow(value="orphan value")

    assert row.get_keyword() == ""
    assert row.get_value() == "orphan value"
    assert row.is_empty()


def test_custom_keyword_is_limited_to_png_keyword_length() -> None:
    _app()
    row = PNGCustomRow("K" * (MAX_KEYWORD_LENGTH + 20))

    assert len(row.keyword_input.text()) == MAX_KEYWORD_LENGTH
    assert len(row.get_keyword()) == MAX_KEYWORD_LENGTH


def test_custom_row_delete_button_emits_the_row_without_deleting_it() -> None:
    _app()
    row = PNGCustomRow("Secret", "TEST")
    removed_rows: list[object] = []
    row.removed.connect(removed_rows.append)

    row.delete_button.click()

    assert removed_rows == [row]
    assert row.delete_button.objectName() == "btnRemoveFile"
    assert row.delete_button.size().width() == 26
    assert row.delete_button.size().height() == 26
    assert not row.delete_button.icon().isNull()
    assert row.get_keyword() == "Secret"
    assert row.get_value() == "TEST"
