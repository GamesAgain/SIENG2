"""Focused tests for the prototype MP3 text-frame collection."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from config_prototype.gui.components.technique_forms.metadata import (
    ComplexFrameField,
    MP3ComplexFrameDraft,
    MP3ComplexFrameInstanceDraft,
    MP3SimpleFrameDraft,
    MP3TextFramesForm,
    TextFrameField,
)
from src.core.stego.metadata_handlers.mp3_handler import STANDARD_FRAMES


_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_mp3_text_frames_form_builds_the_production_standard_sections() -> None:
    _app()
    parent = QWidget()
    form = MP3TextFramesForm(parent=parent)

    assert form.parent() is parent
    assert list(form.standard_fields) == STANDARD_FRAMES
    assert all(
        isinstance(form.standard_fields[frame_id], TextFrameField)
        for frame_id in STANDARD_FRAMES
        if frame_id != "COMM"
    )
    assert isinstance(form.standard_fields["COMM"], ComplexFrameField)
    assert form.standard_frames_card.objectName() == "card"
    assert form.other_frames_card.objectName() == "card"
    assert form.add_frame_card.objectName() == "card"
    assert form.other_fields == []
    assert form.other_count_badge.text() == "0"


def test_add_frame_options_include_editable_other_frames_only() -> None:
    _app()
    form = MP3TextFramesForm()
    addable_ids = form.addable_frame_ids()

    assert "TSRC" in addable_ids
    assert "WOAR" in addable_ids
    assert "TXXX" in addable_ids
    assert "WXXX" in addable_ids
    assert "USLT" in addable_ids
    assert "USER" in addable_ids
    assert "APIC" not in addable_ids
    assert "POPM" not in addable_ids
    assert not set(STANDARD_FRAMES).intersection(addable_ids)
    assert form.add_frame_combo.count() == len(addable_ids)
    assert form.add_frame_button.isEnabled()


def test_add_selected_simple_frame_updates_collection_and_picker() -> None:
    _app()
    form = MP3TextFramesForm()
    changes: list[bool] = []
    form.changed.connect(lambda: changes.append(True))
    option_index = form.add_frame_combo.findData("TSRC")
    form.add_frame_combo.setCurrentIndex(option_index)

    form.add_frame_button.click()

    assert len(form.other_fields) == 1
    field = form.other_fields[0]
    assert isinstance(field, TextFrameField)
    assert field.frame_id == "TSRC"
    assert field.delete_button is not None
    assert form.other_count_badge.text() == "1"
    assert form.add_frame_combo.findData("TSRC") == -1
    assert "TSRC" not in form.addable_frame_ids()
    assert changes == [True]


def test_add_complex_frame_groups_instances_in_one_collection_field() -> None:
    _app()
    form = MP3TextFramesForm()

    field = form.add_other_frame("TXXX")

    assert isinstance(field, ComplexFrameField)
    assert field.frame_id == "TXXX"
    assert len(field.rows) == 1
    assert field.delete_button is not None
    field.add_instance_button.click()
    assert len(field.rows) == 2
    assert len(form.other_fields) == 1
    assert form.other_count_badge.text() == "1"
    assert "TXXX" not in form.addable_frame_ids()


def test_collection_rejects_duplicates_and_non_editable_frames() -> None:
    _app()
    form = MP3TextFramesForm()
    form.add_other_frame("TXXX")

    with pytest.raises(ValueError, match="already present"):
        form.add_other_frame("TXXX")

    for frame_id in ("TIT2", "COMM", "APIC", "POPM", "TZZZ"):
        with pytest.raises(ValueError, match="not an addable MP3"):
            form.add_other_frame(frame_id)


def test_remove_signal_returns_frame_to_picker_and_updates_count() -> None:
    _app()
    form = MP3TextFramesForm()
    changes: list[bool] = []
    form.changed.connect(lambda: changes.append(True))
    first = form.add_other_frame("TSRC")
    second = form.add_other_frame("TXXX")

    assert first.delete_button is not None
    first.delete_button.click()

    assert form.other_fields == [second]
    assert form.other_count_badge.text() == "1"
    assert "TSRC" in form.addable_frame_ids()
    assert form.add_frame_combo.findData("TSRC") >= 0
    assert changes == [True, True, True]


def test_remove_unknown_field_does_not_change_the_collection() -> None:
    _app()
    form = MP3TextFramesForm()
    kept = form.add_other_frame("TSRC")
    unknown = TextFrameField("WOAR", removable=True)
    changes: list[bool] = []
    form.changed.connect(lambda: changes.append(True))

    form.remove_other_frame(unknown)

    assert form.other_fields == [kept]
    assert form.other_count_badge.text() == "1"
    assert changes == []


def test_clear_all_resets_standard_values_and_other_collection() -> None:
    _app()
    form = MP3TextFramesForm()
    form.standard_fields["TIT2"].set_value("Hidden title")
    comment = form.standard_fields["COMM"]
    assert isinstance(comment, ComplexFrameField)
    comment.rows[0].set_value("text", "Hidden comment")
    form.add_other_frame("TSRC").set_value("Secret code")
    form.add_other_frame("TXXX")
    changes: list[bool] = []
    form.changed.connect(lambda: changes.append(True))

    form.clear_all()

    assert all(field.is_empty() for field in form.standard_fields.values())
    assert len(comment.rows) == 1
    assert form.other_fields == []
    assert form.other_count_badge.text() == "0"
    assert "TSRC" in form.addable_frame_ids()
    assert "TXXX" in form.addable_frame_ids()
    assert changes == [True]


def test_empty_text_frame_form_exports_an_empty_draft() -> None:
    _app()
    form = MP3TextFramesForm()

    assert form.export_draft() == []


def test_load_and_export_route_standard_and_other_frame_drafts() -> None:
    _app()
    form = MP3TextFramesForm()
    source = [
        MP3SimpleFrameDraft("TSRC", "TH-S2-26-00001"),
        MP3SimpleFrameDraft("TIT2", "Hidden title"),
        MP3ComplexFrameDraft(
            "TXXX",
            [
                MP3ComplexFrameInstanceDraft(
                    desc="Secret",
                    text="TEST",
                ),
                MP3ComplexFrameInstanceDraft(
                    desc="Project",
                    text="SIENG2",
                ),
            ],
        ),
        MP3ComplexFrameDraft(
            "COMM",
            [
                MP3ComplexFrameInstanceDraft(
                    lang="eng",
                    desc="note",
                    text="Hidden comment",
                )
            ],
        ),
    ]

    form.load_draft(source)

    assert form.standard_fields["TIT2"].get_value() == "Hidden title"
    comment = form.standard_fields["COMM"]
    assert isinstance(comment, ComplexFrameField)
    assert comment.rows[0].get_value("text") == "Hidden comment"
    assert [field.frame_id for field in form.other_fields] == [
        "TSRC",
        "TXXX",
    ]
    assert form.other_count_badge.text() == "2"
    assert form.export_draft() == [
        MP3SimpleFrameDraft("TIT2", "Hidden title"),
        MP3ComplexFrameDraft(
            "COMM",
            [
                MP3ComplexFrameInstanceDraft(
                    lang="eng",
                    desc="note",
                    text="Hidden comment",
                )
            ],
        ),
        MP3SimpleFrameDraft("TSRC", "TH-S2-26-00001"),
        MP3ComplexFrameDraft(
            "TXXX",
            [
                MP3ComplexFrameInstanceDraft(
                    desc="Secret",
                    text="TEST",
                ),
                MP3ComplexFrameInstanceDraft(
                    desc="Project",
                    text="SIENG2",
                ),
            ],
        ),
    ]


def test_load_and_export_are_detached_from_caller_state() -> None:
    _app()
    form = MP3TextFramesForm()
    source = [
        MP3SimpleFrameDraft("TIT2", "Original title"),
        MP3ComplexFrameDraft(
            "TXXX",
            [MP3ComplexFrameInstanceDraft(desc="Secret", text="TEST")],
        ),
    ]

    form.load_draft(source)
    source[0].value = "Changed title"
    source[1].instances[0].text = "Changed secret"

    exported = form.export_draft()
    assert exported[0].value == "Original title"
    assert exported[1].instances[0].text == "TEST"

    exported[0].value = "Changed export"
    exported[1].instances[0].text = "Changed export"
    next_export = form.export_draft()
    assert next_export[0].value == "Original title"
    assert next_export[1].instances[0].text == "TEST"


def test_loading_a_new_draft_replaces_previous_frame_controls() -> None:
    _app()
    form = MP3TextFramesForm()
    form.load_draft(
        [
            MP3SimpleFrameDraft("TIT2", "First"),
            MP3SimpleFrameDraft("TSRC", "First code"),
        ]
    )

    form.load_draft([MP3SimpleFrameDraft("TPE1", "Second artist")])

    assert form.standard_fields["TIT2"].is_empty()
    assert form.standard_fields["TPE1"].get_value() == "Second artist"
    assert form.other_fields == []
    assert form.other_count_badge.text() == "0"


@pytest.mark.parametrize(
    ("frames", "message"),
    [
        (
            [
                MP3SimpleFrameDraft("TIT2", "One"),
                MP3SimpleFrameDraft("TIT2", "Two"),
            ],
            "configured more than once",
        ),
        (
            [MP3SimpleFrameDraft("COMM", "Wrong shape")],
            "requires a complex draft",
        ),
        (
            [MP3ComplexFrameDraft("TIT2")],
            "requires a simple draft",
        ),
        (
            [MP3SimpleFrameDraft("APIC", "Wrong collection")],
            "not editable in this form",
        ),
        (
            [MP3SimpleFrameDraft("TZZZ", "Unknown")],
            "not editable in this form",
        ),
        (
            [
                MP3ComplexFrameDraft(
                    "TXXX",
                    [MP3ComplexFrameInstanceDraft(lang="eng", text="x")],
                )
            ],
            "does not use field 'lang'",
        ),
    ],
)
def test_load_rejects_invalid_structure_without_clearing_current_state(
    frames: list,
    message: str,
) -> None:
    _app()
    form = MP3TextFramesForm()
    form.standard_fields["TIT2"].set_value("Keep me")

    with pytest.raises(ValueError, match=message):
        form.load_draft(frames)

    assert form.standard_fields["TIT2"].get_value() == "Keep me"


def test_validation_allows_empty_text_frames_for_future_apic_only_draft(
    monkeypatch,
) -> None:
    _app()
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *_args: pytest.fail("empty text form is structurally valid"),
    )
    form = MP3TextFramesForm()

    assert form.validate_draft()


def test_validation_rejects_an_empty_other_frame(monkeypatch) -> None:
    _app()
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    form = MP3TextFramesForm()
    form.add_other_frame("TSRC")

    assert not form.validate_draft()
    assert warnings == [
        "Please enter a value for frame 'TSRC' or remove it."
    ]


def test_validation_rejects_missing_and_invalid_language(monkeypatch) -> None:
    _app()
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    form = MP3TextFramesForm()
    comment = form.standard_fields["COMM"]
    assert isinstance(comment, ComplexFrameField)
    comment.rows[0].set_value("text", "Hidden comment")

    assert not form.validate_draft()
    assert warnings == ["Frame 'COMM' requires 'lang'."]

    warnings.clear()
    comment.rows[0].set_value("lang", "en")
    assert not form.validate_draft()
    assert warnings == [
        "Frame 'COMM' language must be a 3-letter code such as 'eng' or 'tha'."
    ]


def test_validation_rejects_orphan_and_empty_complex_instances(
    monkeypatch,
) -> None:
    _app()
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    form = MP3TextFramesForm()
    comment = form.standard_fields["COMM"]
    assert isinstance(comment, ComplexFrameField)
    comment.rows[0].set_value("lang", "eng")

    assert not form.validate_draft()
    assert warnings == ["Please enter text for frame 'COMM'."]

    warnings.clear()
    comment.rows[0].set_value("text", "Hidden")
    comment.add_instance()
    assert not form.validate_draft()
    assert warnings == [
        "Remove the empty 'COMM' instance or enter a value."
    ]


@pytest.mark.parametrize(
    ("frame_id", "instances"),
    [
        (
            "COMM",
            [
                MP3ComplexFrameInstanceDraft(
                    lang="eng", desc="note", text="One"
                ),
                MP3ComplexFrameInstanceDraft(
                    lang="eng", desc="note", text="Two"
                ),
            ],
        ),
        (
            "TXXX",
            [
                MP3ComplexFrameInstanceDraft(desc="Secret", text="One"),
                MP3ComplexFrameInstanceDraft(desc="Secret", text="Two"),
            ],
        ),
        (
            "USER",
            [
                MP3ComplexFrameInstanceDraft(lang="eng", text="One"),
                MP3ComplexFrameInstanceDraft(lang="eng", text="Two"),
            ],
        ),
    ],
)
def test_validation_rejects_duplicate_complex_instance_identity(
    monkeypatch,
    frame_id: str,
    instances: list[MP3ComplexFrameInstanceDraft],
) -> None:
    _app()
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    form = MP3TextFramesForm()
    field = form.standard_fields.get(frame_id)
    if field is None:
        field = form.add_other_frame(frame_id)
    assert isinstance(field, ComplexFrameField)
    field.load_draft(MP3ComplexFrameDraft(frame_id, instances))

    assert not form.validate_draft()
    assert warnings == [
        f"Frame '{frame_id}' has duplicate instance identity values."
    ]


def test_validation_accepts_complete_simple_and_complex_frames(
    monkeypatch,
) -> None:
    _app()
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *_args: pytest.fail("valid frame draft must not warn"),
    )
    form = MP3TextFramesForm()
    form.load_draft(
        [
            MP3SimpleFrameDraft("TIT2", "Hidden title"),
            MP3SimpleFrameDraft("WOAR", "https://example.test/artist"),
            MP3ComplexFrameDraft(
                "COMM",
                [
                    MP3ComplexFrameInstanceDraft(
                        lang="eng",
                        desc="note",
                        text="Hidden comment",
                    )
                ],
            ),
            MP3ComplexFrameDraft(
                "TXXX",
                [
                    MP3ComplexFrameInstanceDraft(
                        desc="Secret",
                        text="TEST",
                    )
                ],
            ),
            MP3ComplexFrameDraft(
                "USLT",
                [
                    MP3ComplexFrameInstanceDraft(
                        lang="tha",
                        desc="lyrics",
                        text="Hidden lyrics",
                    )
                ],
            ),
        ]
    )

    assert form.validate_draft()
