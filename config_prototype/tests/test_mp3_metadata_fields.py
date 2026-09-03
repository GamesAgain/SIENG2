"""Focused tests for prototype MP3 metadata field widgets."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QWidget,
)

from config_prototype.gui.components.technique_forms.metadata import (
    ComplexFrameField,
    ComplexInstanceRow,
    MP3ComplexFrameDraft,
    MP3ComplexFrameInstanceDraft,
    MP3SimpleFrameDraft,
    TextFrameField,
)


_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_text_frame_field_uses_frame_identity_and_shared_qss_names() -> None:
    _app()
    parent = QWidget()
    field = TextFrameField("TIT2", parent=parent)

    assert field.parent() is parent
    assert field.frame_id == "TIT2"
    assert field.name_label.text() == "Title"
    assert field.name_label.objectName() == "formLabel"
    assert field.frame_badge.text() == "TIT2"
    assert field.frame_badge.objectName() == "fileInfoBadge"
    assert field.frame_badge.property("badgeColor") == "neutral"
    assert field.value_input.objectName() == "formInput"
    assert field.delete_button is None


def test_url_frame_uses_the_same_scalar_api_with_a_url_hint() -> None:
    _app()
    field = TextFrameField("WOAR")

    assert field.name_label.text() == "Artist URL"
    assert field.value_input.placeholderText() == "https://..."
    field.set_value("  https://example.test/artist  ")
    assert field.get_value() == "https://example.test/artist"
    assert field.export_draft() == MP3SimpleFrameDraft(
        "WOAR",
        "https://example.test/artist",
    )


def test_unknown_simple_frame_falls_back_to_its_frame_id_label() -> None:
    _app()
    field = TextFrameField("TZZZ")

    assert field.name_label.text() == "TZZZ"
    assert field.frame_badge.text() == "TZZZ"


def test_text_frame_value_api_normalizes_empty_and_trimmed_values() -> None:
    _app()
    field = TextFrameField("TPE1")

    assert field.is_empty()
    field.set_value("  Hidden artist  ")
    assert field.value_input.text() == "  Hidden artist  "
    assert field.get_value() == "Hidden artist"
    assert not field.is_empty()

    field.set_value(None)
    assert field.get_value() == ""
    assert field.is_empty()


def test_text_frame_load_and_export_keep_the_bound_frame_identity() -> None:
    _app()
    field = TextFrameField("TALB")

    field.load_draft(MP3SimpleFrameDraft("TALB", "  Hidden album  "))

    assert field.value_input.text() == "  Hidden album  "
    assert field.export_draft() == MP3SimpleFrameDraft(
        "TALB",
        "Hidden album",
    )

    with pytest.raises(ValueError, match="Cannot load frame 'TIT2'"):
        field.load_draft(MP3SimpleFrameDraft("TIT2", "Wrong field"))


def test_text_frame_clear_resets_only_the_value() -> None:
    _app()
    field = TextFrameField("TCON")
    field.set_value("Secret genre")

    field.clear()

    assert field.frame_id == "TCON"
    assert field.is_empty()
    assert field.export_draft() == MP3SimpleFrameDraft("TCON")


@pytest.mark.parametrize(
    "frame_id",
    ["COMM", "USLT", "USER", "TXXX", "WXXX"],
)
def test_text_frame_rejects_complex_frame_ids(frame_id: str) -> None:
    _app()

    with pytest.raises(ValueError, match="not a simple MP3"):
        TextFrameField(frame_id)


@pytest.mark.parametrize("frame_id", ["", "APIC", "PNG", "title"])
def test_text_frame_rejects_non_text_and_non_url_ids(frame_id: str) -> None:
    _app()

    with pytest.raises(ValueError, match="not a simple MP3"):
        TextFrameField(frame_id)


def test_removable_text_frame_emits_itself_without_deleting_state() -> None:
    _app()
    field = TextFrameField("TSRC", removable=True)
    removed_fields: list[object] = []
    field.removed.connect(removed_fields.append)
    field.set_value("TH-S2-26-00001")

    assert field.delete_button is not None
    field.delete_button.click()

    assert removed_fields == [field]
    assert field.delete_button.objectName() == "btnRemoveFile"
    assert field.delete_button.size().width() == 22
    assert field.delete_button.size().height() == 22
    assert not field.delete_button.icon().isNull()
    assert field.get_value() == "TH-S2-26-00001"


@pytest.mark.parametrize(
    ("frame_id", "field_names"),
    [
        ("COMM", ["lang", "desc", "text"]),
        ("USLT", ["lang", "desc", "text"]),
        ("USER", ["lang", "text"]),
        ("TXXX", ["desc", "text"]),
        ("WXXX", ["desc", "url"]),
    ],
)
def test_complex_instance_builds_only_its_contract_fields(
    frame_id: str,
    field_names: list[str],
) -> None:
    _app()
    row = ComplexInstanceRow(frame_id)

    assert row.frame_id == frame_id
    assert list(row.inputs) == field_names
    assert row.delete_button is not None
    assert row.delete_button.size().width() == 26
    assert row.delete_button.size().height() == 26


def test_complex_language_input_matches_the_production_interaction() -> None:
    _app()
    row = ComplexInstanceRow("COMM")
    language_input = row.inputs["lang"]

    assert isinstance(language_input, QComboBox)
    assert language_input.isEditable()
    assert language_input.currentIndex() == -1
    assert language_input.lineEdit().placeholderText() == "eng"
    assert language_input.lineEdit().maxLength() == 3
    assert language_input.width() == 90
    assert [language_input.itemText(index) for index in range(2)] == [
        "eng",
        "tha",
    ]


def test_uslt_uses_multiline_text_while_other_complex_values_are_lines() -> None:
    _app()
    lyrics_row = ComplexInstanceRow("USLT")
    comment_row = ComplexInstanceRow("COMM")
    url_row = ComplexInstanceRow("WXXX")

    assert isinstance(lyrics_row.inputs["text"], QPlainTextEdit)
    assert lyrics_row.inputs["text"].objectName() == "payloadTextArea"
    assert lyrics_row.inputs["text"].height() == 70
    assert lyrics_row.inputs["text"].placeholderText() == "Lyrics..."
    assert isinstance(comment_row.inputs["text"], QLineEdit)
    assert comment_row.inputs["text"].placeholderText() == "Text..."
    assert isinstance(url_row.inputs["url"], QLineEdit)
    assert url_row.inputs["url"].placeholderText() == "https://..."


def test_complex_instance_load_export_and_clear_use_typed_draft() -> None:
    _app()
    row = ComplexInstanceRow("COMM")
    source = MP3ComplexFrameInstanceDraft(
        lang=" eng ",
        desc=" note ",
        text=" hidden message ",
    )

    row.load_draft(source)

    assert row.export_draft() == MP3ComplexFrameInstanceDraft(
        lang="eng",
        desc="note",
        text="hidden message",
    )
    assert not row.is_empty()

    row.clear()

    assert row.is_empty()
    assert row.export_draft() == MP3ComplexFrameInstanceDraft(
        lang="",
        desc="",
        text="",
    )


def test_complex_instance_uses_text_or_url_as_required_content() -> None:
    _app()
    text_row = ComplexInstanceRow("TXXX")
    url_row = ComplexInstanceRow("WXXX")

    text_row.set_value("desc", "orphan description")
    url_row.set_value("desc", "orphan description")
    assert text_row.is_empty()
    assert url_row.is_empty()

    text_row.set_value("text", "secret")
    url_row.set_value("url", "https://example.test")
    assert not text_row.is_empty()
    assert not url_row.is_empty()


def test_complex_instance_delete_emits_the_row_without_deleting_state() -> None:
    _app()
    row = ComplexInstanceRow("TXXX")
    removed_rows: list[object] = []
    row.removed.connect(removed_rows.append)
    row.set_value("desc", "Secret")
    row.set_value("text", "TEST")

    assert row.delete_button is not None
    row.delete_button.click()

    assert removed_rows == [row]
    assert row.export_draft() == MP3ComplexFrameInstanceDraft(
        desc="Secret",
        text="TEST",
    )


@pytest.mark.parametrize("frame_id", ["TIT2", "WOAR", "APIC", ""])
def test_complex_instance_rejects_unsupported_frame_ids(
    frame_id: str,
) -> None:
    _app()

    with pytest.raises(ValueError, match="not a supported complex MP3"):
        ComplexInstanceRow(frame_id)


def test_complex_frame_field_starts_with_one_empty_instance() -> None:
    _app()
    parent = QWidget()
    field = ComplexFrameField("COMM", parent=parent)

    assert field.parent() is parent
    assert field.frame_id == "COMM"
    assert field.name_label.text() == "Comment"
    assert field.name_label.objectName() == "formLabel"
    assert field.frame_badge.text() == "COMM"
    assert field.frame_badge.property("badgeColor") == "neutral"
    assert field.multiple_hint.text() == "Can have multiple instances"
    assert field.multiple_hint.objectName() == "hintLabel"
    assert field.add_instance_button.objectName() == "LinkBtn"
    assert field.add_instance_button.text() == "+ Add COMM instance"
    assert field.delete_button is None
    assert len(field.rows) == 1
    assert field.is_empty()


def test_complex_frame_add_button_creates_another_empty_instance() -> None:
    _app()
    field = ComplexFrameField("TXXX")
    first_row = field.rows[0]

    field.add_instance_button.click()

    assert len(field.rows) == 2
    assert field.rows[0] is first_row
    assert field.rows[1].frame_id == "TXXX"
    assert field.rows[1].is_empty()


def test_complex_frame_export_filters_empty_rows_and_preserves_order() -> None:
    _app()
    field = ComplexFrameField("COMM")
    field.rows[0].load_draft(
        MP3ComplexFrameInstanceDraft(
            lang="eng",
            desc="first",
            text="Message one",
        )
    )
    field.add_instance()
    field.add_instance(
        MP3ComplexFrameInstanceDraft(
            lang="tha",
            desc="second",
            text="Message two",
        )
    )

    assert field.export_draft() == MP3ComplexFrameDraft(
        frame_id="COMM",
        instances=[
            MP3ComplexFrameInstanceDraft(
                lang="eng",
                desc="first",
                text="Message one",
            ),
            MP3ComplexFrameInstanceDraft(
                lang="tha",
                desc="second",
                text="Message two",
            ),
        ],
    )


def test_complex_frame_load_replaces_rows_and_keeps_draft_detached() -> None:
    _app()
    field = ComplexFrameField("WXXX")
    source = MP3ComplexFrameDraft(
        frame_id="WXXX",
        instances=[
            MP3ComplexFrameInstanceDraft(
                desc="Project",
                url="https://example.test/one",
            ),
            MP3ComplexFrameInstanceDraft(
                desc="Docs",
                url="https://example.test/two",
            ),
        ],
    )

    field.load_draft(source)
    source.instances[0].url = "https://changed.test"

    assert len(field.rows) == 2
    assert field.export_draft().instances[0].url == (
        "https://example.test/one"
    )
    assert field.export_draft().instances[1].desc == "Docs"


def test_complex_frame_load_empty_draft_keeps_one_blank_row() -> None:
    _app()
    field = ComplexFrameField("USER")
    field.add_instance(
        MP3ComplexFrameInstanceDraft(lang="eng", text="terms")
    )

    field.load_draft(MP3ComplexFrameDraft("USER"))

    assert len(field.rows) == 1
    assert field.rows[0].is_empty()
    assert field.export_draft() == MP3ComplexFrameDraft("USER")


def test_complex_frame_rejects_a_draft_for_another_frame() -> None:
    _app()
    field = ComplexFrameField("COMM")

    with pytest.raises(ValueError, match="Cannot load frame 'TXXX'"):
        field.load_draft(MP3ComplexFrameDraft("TXXX"))


def test_complex_frame_removing_last_instance_restores_one_blank_row() -> None:
    _app()
    field = ComplexFrameField("TXXX")
    populated_row = field.rows[0]
    populated_row.set_value("text", "secret")

    assert populated_row.delete_button is not None
    populated_row.delete_button.click()

    assert len(field.rows) == 1
    assert field.rows[0] is not populated_row
    assert field.rows[0].is_empty()
    assert field.export_draft() == MP3ComplexFrameDraft("TXXX")


def test_removable_complex_frame_emits_itself_without_removing_rows() -> None:
    _app()
    field = ComplexFrameField("WXXX", removable=True)
    removed_fields: list[object] = []
    field.removed.connect(removed_fields.append)
    field.rows[0].load_draft(
        MP3ComplexFrameInstanceDraft(
            desc="Project",
            url="https://example.test",
        )
    )

    assert field.delete_button is not None
    field.delete_button.click()

    assert removed_fields == [field]
    assert len(field.rows) == 1
    assert field.export_draft().instances[0].desc == "Project"
