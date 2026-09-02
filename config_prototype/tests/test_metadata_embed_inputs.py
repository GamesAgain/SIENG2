"""Focused tests for the prototype Metadata draft models."""

from dataclasses import fields
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from config_prototype.gui.components import technique_forms
from config_prototype.gui.components.technique_forms.metadata import (
    ApicImageDraft,
    MetadataEmbedInputs,
    MetadataInputsDraft,
    MetadataPayloadDraft,
    MP3MetadataDraft,
    PNGMetadataDraft,
)


_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_metadata_draft_defaults_are_isolated() -> None:
    first_png = PNGMetadataDraft()
    second_png = PNGMetadataDraft()
    first_png.entries["Title"] = "First image"

    first_mp3 = MP3MetadataDraft()
    second_mp3 = MP3MetadataDraft()
    first_mp3.frames["TIT2"] = "First track"
    first_mp3.apic_images.append(ApicImageDraft("front.png"))

    assert second_png.entries == {}
    assert second_mp3.frames == {}
    assert second_mp3.apic_images == []
    assert MetadataInputsDraft() == MetadataInputsDraft(
        cover_path=None,
        payload=None,
    )


def test_metadata_types_are_available_from_the_public_technique_package() -> None:
    assert technique_forms.ApicImageDraft is ApicImageDraft
    assert technique_forms.MetadataEmbedInputs is MetadataEmbedInputs
    assert technique_forms.MetadataInputsDraft is MetadataInputsDraft
    assert technique_forms.MetadataPayloadDraft is MetadataPayloadDraft
    assert technique_forms.MP3MetadataDraft is MP3MetadataDraft
    assert technique_forms.PNGMetadataDraft is PNGMetadataDraft


def test_apic_draft_keeps_a_file_reference_instead_of_raw_bytes() -> None:
    draft = ApicImageDraft(
        image_path="album-cover.png",
        picture_type=4,
        description="back",
    )

    assert draft.image_path == "album-cover.png"
    assert draft.picture_type == 4
    assert draft.description == "back"
    assert {item.name for item in fields(ApicImageDraft)} == {
        "image_path",
        "picture_type",
        "description",
    }


def test_metadata_inputs_accept_png_or_mp3_payload_drafts() -> None:
    png_inputs = MetadataInputsDraft(
        cover_path="carrier.png",
        payload=PNGMetadataDraft(entries={"Secret": "TEST"}),
    )
    mp3_inputs = MetadataInputsDraft(
        cover_path="carrier.mp3",
        payload=MP3MetadataDraft(
            frames={"TXXX": [{"desc": "Secret", "text": "TEST"}]},
            apic_images=[
                ApicImageDraft(
                    image_path="hidden.png",
                    picture_type=3,
                    description="front",
                )
            ],
        ),
    )

    assert isinstance(png_inputs.payload, PNGMetadataDraft)
    assert png_inputs.payload.entries == {"Secret": "TEST"}
    assert isinstance(mp3_inputs.payload, MP3MetadataDraft)
    assert mp3_inputs.payload.frames["TXXX"][0]["text"] == "TEST"
    assert mp3_inputs.payload.apic_images[0].image_path == "hidden.png"


def test_metadata_host_starts_with_an_empty_draft_and_view() -> None:
    _app()
    parent = QWidget()
    form = MetadataEmbedInputs(parent=parent)

    assert form.parent() is parent
    assert form._draft == MetadataInputsDraft()
    assert form.layout().getContentsMargins() == (0, 0, 0, 0)
    assert form.cover_file_stack.count() == 2
    assert form.cover_file_stack.currentWidget() is form.cover_card
    assert (
        form.cover_file_stack.currentIndex()
        == form.COVER_DROP_STATE_INDEX
    )
    assert form.content_stack.count() == 3
    assert form.content_stack.currentWidget() is form.empty_state_label
    assert form.content_stack.currentIndex() == form.EMPTY_STATE_INDEX
    assert form.cover_media_type is None
    assert form.empty_state_label.objectName() == "pipelineEmpty"
    assert form.empty_state_label.wordWrap()
    assert form.cover_card.objectName() == "card"
    assert form.cover_drop_zone.file_exts == [".png", ".mp3"]
    assert form.cover_drop_zone.is_single_mode
    assert not hasattr(form, "pipeline_mode")
    assert not hasattr(form, "key_registry")
    assert not hasattr(form, "linked_cover_index")


def test_manual_cover_select_replace_and_clear_updates_the_draft(
    tmp_path,
) -> None:
    _app()
    png_cover = tmp_path / "first.png"
    mp3_cover = tmp_path / "second.MP3"
    png_cover.write_bytes(b"prototype png")
    mp3_cover.write_bytes(b"prototype mp3")
    payload = PNGMetadataDraft(entries={"Secret": "TEST"})
    form = MetadataEmbedInputs()
    form._draft.payload = payload

    form.cover_drop_zone.add_files([str(png_cover)])

    assert form.cover_drop_zone.get_selected_files() == [str(png_cover)]
    assert form.export_draft().cover_path == str(png_cover)
    assert form.cover_media_type == "png"
    assert form.cover_file_stack.currentWidget() is form.selected_cover_widget
    assert form.file_info_bar.file_info_name.text() == png_cover.name
    assert form.content_stack.currentWidget() is form.png_state_widget

    form.cover_drop_zone.add_files([str(mp3_cover)])

    assert form.cover_drop_zone.get_selected_files() == [str(mp3_cover)]
    assert form.export_draft().cover_path == str(mp3_cover)
    assert form.export_draft().payload == payload
    assert form.cover_media_type == "mp3"
    assert form.cover_file_stack.currentWidget() is form.selected_cover_widget
    assert form.file_info_bar.file_info_name.text() == mp3_cover.name
    assert form.content_stack.currentWidget() is form.mp3_state_widget

    form.clear_cover()

    assert form.cover_drop_zone.get_selected_files() == []
    assert form.export_draft().cover_path is None
    assert form.export_draft().payload == payload
    assert form.cover_media_type is None
    assert form.cover_file_stack.currentWidget() is form.cover_card
    assert form.content_stack.currentWidget() is form.empty_state_label


def test_change_file_request_returns_to_drop_state_and_keeps_payload(
    tmp_path,
) -> None:
    _app()
    cover = tmp_path / "carrier.png"
    cover.write_bytes(b"prototype png")
    payload = PNGMetadataDraft(entries={"Secret": "TEST"})
    form = MetadataEmbedInputs()
    form._draft.payload = payload
    form.cover_drop_zone.add_files([str(cover)])

    form.file_info_bar._change_file_btn.click()

    assert form.cover_drop_zone.get_selected_files() == []
    assert form.export_draft() == MetadataInputsDraft(payload=payload)
    assert form.cover_media_type is None
    assert form.cover_file_stack.currentWidget() is form.cover_card
    assert form.content_stack.currentWidget() is form.empty_state_label


def test_manual_cover_ignores_unsupported_files(tmp_path) -> None:
    _app()
    unsupported = tmp_path / "carrier.txt"
    unsupported.write_text("not a metadata target", encoding="utf-8")
    form = MetadataEmbedInputs()

    form.cover_drop_zone.add_files([str(unsupported)])

    assert form.cover_drop_zone.get_selected_files() == []
    assert form.export_draft() == MetadataInputsDraft()
    assert form.content_stack.currentIndex() == form.EMPTY_STATE_INDEX


def test_cover_media_detection_requires_an_available_supported_file(
    tmp_path,
) -> None:
    png_cover = tmp_path / "carrier.PNG"
    mp3_cover = tmp_path / "carrier.Mp3"
    unsupported = tmp_path / "carrier.wav"
    for path in (png_cover, mp3_cover, unsupported):
        path.write_bytes(b"prototype cover")

    assert MetadataEmbedInputs.detect_cover_media(str(png_cover)) == "png"
    assert MetadataEmbedInputs.detect_cover_media(str(mp3_cover)) == "mp3"
    assert MetadataEmbedInputs.detect_cover_media(str(unsupported)) is None
    assert MetadataEmbedInputs.detect_cover_media(
        str(tmp_path / "missing.png")
    ) is None
    assert MetadataEmbedInputs.detect_cover_media(None) is None


def test_load_draft_restores_available_cover_widget_and_media_state(
    tmp_path,
) -> None:
    _app()
    cover = tmp_path / "carrier.png"
    cover.write_bytes(b"prototype png")
    source = MetadataInputsDraft(
        cover_path=str(cover),
        payload=PNGMetadataDraft(entries={"Secret": "TEST"}),
    )
    form = MetadataEmbedInputs()

    form.load_draft(source)

    assert form.cover_drop_zone.get_selected_files() == [str(cover)]
    assert form.cover_media_type == "png"
    assert form.cover_file_stack.currentWidget() is form.selected_cover_widget
    assert form.file_info_bar.file_info_name.text() == cover.name
    assert form.content_stack.currentWidget() is form.png_state_widget
    assert form.export_draft() == source

    source.cover_path = "changed.png"
    source.payload.entries["Secret"] = "changed"
    assert form.export_draft() == MetadataInputsDraft(
        cover_path=str(cover),
        payload=PNGMetadataDraft(entries={"Secret": "TEST"}),
    )


def test_load_draft_with_no_cover_resets_widget_and_media_state(
    tmp_path,
) -> None:
    _app()
    cover = tmp_path / "carrier.mp3"
    cover.write_bytes(b"prototype mp3")
    form = MetadataEmbedInputs()
    form.cover_drop_zone.add_files([str(cover)])

    form.load_draft(MetadataInputsDraft())

    assert form.cover_drop_zone.get_selected_files() == []
    assert form.cover_media_type is None
    assert form.cover_file_stack.currentWidget() is form.cover_card
    assert form.content_stack.currentWidget() is form.empty_state_label
    assert form.export_draft() == MetadataInputsDraft()


def test_png_load_and_export_are_detached_from_caller_state() -> None:
    _app()
    source = MetadataInputsDraft(
        cover_path="carrier.png",
        payload=PNGMetadataDraft(entries={"Secret": "TEST"}),
    )
    form = MetadataEmbedInputs()

    form.load_draft(source)
    source.cover_path = "changed.png"
    source.payload.entries["Secret"] = "changed"

    exported = form.export_draft()
    assert exported == MetadataInputsDraft(
        cover_path="carrier.png",
        payload=PNGMetadataDraft(entries={"Secret": "TEST"}),
    )

    exported.payload.entries["Secret"] = "changed again"
    assert form.export_draft().payload.entries == {"Secret": "TEST"}


def test_mp3_load_and_export_copy_nested_frames_and_apic_items() -> None:
    _app()
    source = MetadataInputsDraft(
        cover_path="carrier.mp3",
        payload=MP3MetadataDraft(
            frames={"TXXX": [{"desc": "Secret", "text": "TEST"}]},
            apic_images=[
                ApicImageDraft(
                    image_path="front.png",
                    picture_type=3,
                    description="front",
                )
            ],
        ),
    )
    form = MetadataEmbedInputs()

    form.load_draft(source)
    source.payload.frames["TXXX"][0]["text"] = "changed"
    source.payload.apic_images[0].image_path = "changed.png"

    exported = form.export_draft()
    assert exported.payload.frames["TXXX"][0]["text"] == "TEST"
    assert exported.payload.apic_images[0].image_path == "front.png"

    exported.payload.frames["TXXX"][0]["text"] = "changed again"
    exported.payload.apic_images.clear()
    next_export = form.export_draft()
    assert next_export.payload.frames["TXXX"][0]["text"] == "TEST"
    assert len(next_export.payload.apic_images) == 1


def test_loading_a_new_draft_replaces_the_previous_payload_type() -> None:
    _app()
    form = MetadataEmbedInputs()
    form.load_draft(
        MetadataInputsDraft(
            cover_path="first.png",
            payload=PNGMetadataDraft(entries={"Title": "First"}),
        )
    )

    replacement = MetadataInputsDraft(
        cover_path="second.mp3",
        payload=MP3MetadataDraft(frames={"TIT2": "Second"}),
    )
    form.load_draft(replacement)

    assert form.export_draft() == replacement
    assert isinstance(form.export_draft().payload, MP3MetadataDraft)


def test_baseline_validation_reports_missing_and_mismatched_inputs(
    tmp_path,
    monkeypatch,
) -> None:
    _app()
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    png_cover = tmp_path / "carrier.PNG"
    mp3_cover = tmp_path / "carrier.mp3"
    unsupported_cover = tmp_path / "carrier.txt"
    for path in (png_cover, mp3_cover, unsupported_cover):
        path.write_bytes(b"prototype metadata cover")

    cases = [
        (
            MetadataInputsDraft(),
            "Please select a target PNG or MP3 file.",
        ),
        (
            MetadataInputsDraft(
                cover_path=str(tmp_path / "missing.png"),
                payload=PNGMetadataDraft(entries={"Title": "Hidden"}),
            ),
            "The selected target file is unavailable.",
        ),
        (
            MetadataInputsDraft(
                cover_path=str(unsupported_cover),
                payload=PNGMetadataDraft(entries={"Title": "Hidden"}),
            ),
            "Metadata supports PNG and MP3 target files only.",
        ),
        (
            MetadataInputsDraft(cover_path=str(png_cover)),
            "Please add at least one metadata field.",
        ),
        (
            MetadataInputsDraft(
                cover_path=str(png_cover),
                payload=MP3MetadataDraft(frames={"TIT2": "Hidden"}),
            ),
            "The metadata payload does not match the PNG target file.",
        ),
        (
            MetadataInputsDraft(
                cover_path=str(mp3_cover),
                payload=PNGMetadataDraft(entries={"Title": "Hidden"}),
            ),
            "The metadata payload does not match the MP3 target file.",
        ),
        (
            MetadataInputsDraft(
                cover_path=str(png_cover),
                payload=PNGMetadataDraft(),
            ),
            "Please add at least one PNG metadata field.",
        ),
        (
            MetadataInputsDraft(
                cover_path=str(mp3_cover),
                payload=MP3MetadataDraft(),
            ),
            "Please add at least one MP3 text frame or APIC image.",
        ),
    ]

    form = MetadataEmbedInputs()
    for draft, expected_warning in cases:
        form.load_draft(draft)
        warnings.clear()
        assert not form.validate_draft()
        assert warnings == [expected_warning]


def test_baseline_validation_accepts_structural_png_and_mp3_drafts(
    tmp_path,
    monkeypatch,
) -> None:
    _app()

    def fail_if_warning_is_shown(*_args) -> None:
        raise AssertionError("valid draft must not show a warning")

    monkeypatch.setattr(QMessageBox, "warning", fail_if_warning_is_shown)
    png_cover = tmp_path / "carrier.png"
    mp3_cover = tmp_path / "carrier.MP3"
    png_cover.write_bytes(b"prototype png")
    mp3_cover.write_bytes(b"prototype mp3")

    valid_drafts = [
        MetadataInputsDraft(
            cover_path=str(png_cover),
            payload=PNGMetadataDraft(entries={"Secret": "TEST"}),
        ),
        MetadataInputsDraft(
            cover_path=str(mp3_cover),
            payload=MP3MetadataDraft(frames={"TIT2": "Hidden"}),
        ),
        MetadataInputsDraft(
            cover_path=str(mp3_cover),
            payload=MP3MetadataDraft(
                apic_images=[ApicImageDraft("hidden.png")]
            ),
        ),
    ]

    form = MetadataEmbedInputs()
    for draft in valid_drafts:
        form.load_draft(draft)
        assert form.validate_draft()
