"""Focused workflow tests for linked Metadata cover sources."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication

from config_prototype.core.configurable import StepOutput
from config_prototype.gui.components.step_config_shell import (
    StepConfigShellDialog,
    StepConfigShellPanel,
)
from config_prototype.gui.components.technique_forms import (
    ApicImageDraft,
    LSBInputsDraft,
    LocomotiveCoverDraft,
    LocomotiveInputsDraft,
    MetadataEmbedInputs,
    MetadataInputsDraft,
    MP3MetadataDraft,
    MP3SimpleFrameDraft,
    PNGMetadataDraft,
)
from config_prototype.gui.pages.sub_pages.embed.configurable_page import (
    EmbedConfigurablePage,
)


def _app() -> QApplication:
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(
        Path("src/gui/styles/default.qss").read_text(encoding="utf-8")
    )
    return app


def _process_events(app: QApplication) -> None:
    for _ in range(4):
        app.processEvents()


def _write_png(path) -> None:
    image = QImage(48, 32, QImage.Format.Format_ARGB32)
    image.fill(QColor("#38BDF8"))
    assert image.save(str(path), "PNG")


def _page_with_steps(*techniques: str) -> tuple[QApplication, EmbedConfigurablePage]:
    app = _app()
    page = EmbedConfigurablePage()
    for technique in techniques:
        page.add_pipeline_step(technique)
    _process_events(app)
    return app, page


def _select_linked_cover(
    form: MetadataEmbedInputs,
    reference: StepOutput,
) -> None:
    form.cover_mode_toggle.set_mode("linked")
    form.on_cover_mode_changed("linked")
    form.cover_output_picker._select_from_click(reference)


def test_inline_png_link_save_cancel_reopen_and_broken_reference(
    tmp_path,
) -> None:
    cover = tmp_path / "producer.png"
    cover.write_bytes(b"prototype png")
    app, page = _page_with_steps("lsbpp", "metadata")
    producer = page.pipeline_steps[0]
    producer.technique_inputs = LSBInputsDraft(
        cover=str(cover),
        payload_text="producer payload",
        encryption_enabled=False,
    )
    reference = StepOutput(producer.key, "result")
    page.render_step_cards()

    page.set_config_variant("inline")
    page.open_step_config_inline(1)
    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    form = panel.shell.content_widget
    assert isinstance(form, MetadataEmbedInputs)
    assert [item.reference for item in form.output_catalog] == [reference]

    _select_linked_cover(form, reference)
    assert form.cover_media_type == "png"
    assert form.content_stack.currentWidget() is form.png_form
    form.png_form.standard_fields["Title"].set_value("Linked PNG")
    panel.save_button.click()
    _process_events(app)

    saved = page.pipeline_steps[1].technique_inputs
    assert saved == MetadataInputsDraft(
        cover=reference,
        payload=PNGMetadataDraft(entries={"Title": "Linked PNG"}),
    )
    card = page.step_cards[1]
    assert card.status == "ready"
    assert card.summary_text("cover") == "From STEP 1, Output 1"
    assert card.summary_text("output") == "PNG ×1"

    page.open_step_config_inline(1)
    reopened_panel = page.active_step_panel
    assert isinstance(reopened_panel, StepConfigShellPanel)
    reopened_form = reopened_panel.shell.content_widget
    assert isinstance(reopened_form, MetadataEmbedInputs)
    assert reopened_form.cover_output_picker.selected_output() == reference
    assert reopened_form.cover_media_type == "png"
    reopened_form.png_form.standard_fields["Title"].set_value("Discarded")
    reopened_panel.cancel_button.click()
    _process_events(app)
    assert page.pipeline_steps[1].technique_inputs == saved

    page.remove_pipeline_step(0)
    _process_events(app)
    assert page.pipeline_steps[0].technique_inputs == saved
    assert page.step_cards[0].status == "blocked"
    assert "Source step no longer exists" in page.step_cards[0].status_label.toolTip()

    page.open_step_config_inline(0)
    broken_panel = page.active_step_panel
    assert isinstance(broken_panel, StepConfigShellPanel)
    broken_form = broken_panel.shell.content_widget
    assert isinstance(broken_form, MetadataEmbedInputs)
    assert broken_form.cover_output_picker.selected_output() == reference
    assert broken_form.cover_output_picker.unavailable_reason() == (
        "Source step no longer exists."
    )
    assert broken_form.cover_drop_zone.get_selected_files() == []
    assert broken_form.cover_media_type == "png"
    assert broken_form.content_stack.currentWidget() is broken_form.png_form
    broken_panel.cancel_button.click()


def test_popup_mp3_link_save_and_reopen_preserves_draft(tmp_path) -> None:
    cover = tmp_path / "producer.mp3"
    cover.write_bytes(b"prototype mp3")
    app, page = _page_with_steps("metadata", "metadata")
    producer = page.pipeline_steps[0]
    producer.technique_inputs = MetadataInputsDraft(
        cover=str(cover),
        payload=MP3MetadataDraft(
            frames=[MP3SimpleFrameDraft("TIT2", "Producer")]
        ),
    )
    reference = StepOutput(producer.key, "result")
    page.render_step_cards()

    def configure_and_save() -> None:
        dialog = page.active_step_dialog
        assert isinstance(dialog, StepConfigShellDialog)
        form = dialog.shell.content_widget
        assert isinstance(form, MetadataEmbedInputs)
        _select_linked_cover(form, reference)
        assert form.cover_media_type == "mp3"
        assert form.content_stack.currentWidget() is form.mp3_form
        form.mp3_form.text_frames_form.standard_fields["TIT2"].set_value(
            "Linked MP3"
        )
        dialog.save_button.click()

    QTimer.singleShot(0, configure_and_save)
    page.open_step_config_popup(1)
    _process_events(app)

    saved = page.pipeline_steps[1].technique_inputs
    assert saved == MetadataInputsDraft(
        cover=reference,
        payload=MP3MetadataDraft(
            frames=[MP3SimpleFrameDraft("TIT2", "Linked MP3")]
        ),
    )
    assert page.step_cards[1].status == "ready"
    assert page.step_cards[1].summary_text("cover") == (
        "From STEP 1, Output 1"
    )
    assert page.step_cards[1].summary_text("output") == "MP3 ×1"

    def inspect_and_cancel() -> None:
        dialog = page.active_step_dialog
        assert isinstance(dialog, StepConfigShellDialog)
        form = dialog.shell.content_widget
        assert isinstance(form, MetadataEmbedInputs)
        assert form.cover_output_picker.selected_output() == reference
        assert form.cover_media_type == "mp3"
        form.mp3_form.text_frames_form.standard_fields["TIT2"].set_value(
            "Discarded"
        )
        dialog.cancel_button.click()

    QTimer.singleShot(0, inspect_and_cancel)
    page.open_step_config_popup(1)
    _process_events(app)
    assert page.pipeline_steps[1].technique_inputs == saved


def test_used_metadata_cover_output_is_hidden_from_later_picker(tmp_path) -> None:
    cover = tmp_path / "producer.png"
    cover.write_bytes(b"prototype png")
    _app_instance, page = _page_with_steps(
        "lsbpp",
        "metadata",
        "metadata",
    )
    producer = page.pipeline_steps[0]
    producer.technique_inputs = LSBInputsDraft(
        cover=str(cover),
        payload_text="producer payload",
        encryption_enabled=False,
    )
    reference = StepOutput(producer.key, "result")
    page.pipeline_steps[1].technique_inputs = MetadataInputsDraft(
        cover=reference,
        payload=PNGMetadataDraft(entries={"Title": "Consumer"}),
    )

    owner_form = page.create_step_technique_form(page.pipeline_steps[1], 1)
    later_form = page.create_step_technique_form(page.pipeline_steps[2], 2)

    assert isinstance(owner_form, MetadataEmbedInputs)
    assert isinstance(later_form, MetadataEmbedInputs)
    assert reference in [item.reference for item in owner_form.output_catalog]
    assert reference not in [item.reference for item in later_form.output_catalog]


def test_linked_apic_save_reopen_and_broken_reference_are_lossless(
    tmp_path,
) -> None:
    producer_cover = tmp_path / "producer.png"
    consumer_cover = tmp_path / "carrier.mp3"
    _write_png(producer_cover)
    consumer_cover.write_bytes(b"prototype mp3")
    app, page = _page_with_steps("lsbpp", "metadata")
    producer = page.pipeline_steps[0]
    producer.technique_inputs = LSBInputsDraft(
        cover=str(producer_cover),
        payload_text="producer payload",
        encryption_enabled=False,
    )
    reference = StepOutput(producer.key, "result")
    page.pipeline_steps[1].technique_inputs = MetadataInputsDraft(
        cover=str(consumer_cover),
        payload=MP3MetadataDraft(
            frames=[MP3SimpleFrameDraft("TIT2", "Consumer")]
        ),
    )
    page.render_step_cards()

    page.set_config_variant("inline")
    page.open_step_config_inline(1)
    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    form = panel.shell.content_widget
    assert isinstance(form, MetadataEmbedInputs)
    apic_form = form.mp3_form.apic_images_form
    assert [
        output.reference for output in apic_form.output_catalog
    ] == [reference]

    apic_form.source_mode_toggle.linked_button.click()
    apic_form.output_picker._select_from_click(reference)
    assert apic_form.confirm_add_image()
    panel.save_button.click()
    _process_events(app)

    saved = page.pipeline_steps[1].technique_inputs
    assert isinstance(saved, MetadataInputsDraft)
    assert isinstance(saved.payload, MP3MetadataDraft)
    assert saved.payload.apic_images == [
        ApicImageDraft(reference, 3, "Front cover")
    ]
    assert page.step_cards[1].summary_text("payload") == (
        "Text ×1 + APIC ×1"
    )

    page.open_step_config_inline(1)
    reopened_panel = page.active_step_panel
    assert isinstance(reopened_panel, StepConfigShellPanel)
    reopened_form = reopened_panel.shell.content_widget
    assert isinstance(reopened_form, MetadataEmbedInputs)
    reopened_apic = reopened_form.mp3_form.apic_images_form
    assert reopened_apic.export_draft() == saved.payload.apic_images
    assert len(reopened_apic.cards) == 1
    reopened_panel.cancel_button.click()

    page.remove_pipeline_step(0)
    _process_events(app)
    assert page.pipeline_steps[0].technique_inputs == saved

    page.open_step_config_inline(0)
    broken_panel = page.active_step_panel
    assert isinstance(broken_panel, StepConfigShellPanel)
    broken_form = broken_panel.shell.content_widget
    assert isinstance(broken_form, MetadataEmbedInputs)
    broken_apic = broken_form.mp3_form.apic_images_form
    assert broken_apic.export_draft() == saved.payload.apic_images
    broken_apic.begin_change_image(broken_apic.cards[0])
    assert broken_apic.output_picker.selected_output() == reference
    assert broken_apic.output_picker.unavailable_reason() == (
        "Source step no longer exists."
    )
    broken_panel.cancel_button.click()


def test_apic_output_has_one_consumer_and_later_picker_is_unavailable(
    tmp_path,
) -> None:
    producer_cover = tmp_path / "producer.png"
    first_cover = tmp_path / "first.mp3"
    second_cover = tmp_path / "second.mp3"
    _write_png(producer_cover)
    first_cover.write_bytes(b"prototype mp3")
    second_cover.write_bytes(b"prototype mp3")
    _app_instance, page = _page_with_steps(
        "lsbpp",
        "metadata",
        "metadata",
    )
    page.pipeline_steps[0].technique_inputs = LSBInputsDraft(
        cover=str(producer_cover),
        payload_text="producer payload",
        encryption_enabled=False,
    )
    reference = StepOutput(page.pipeline_steps[0].key, "result")
    for index, cover in ((1, first_cover), (2, second_cover)):
        page.pipeline_steps[index].technique_inputs = MetadataInputsDraft(
            cover=str(cover),
            payload=MP3MetadataDraft(
                apic_images=[
                    ApicImageDraft(reference, 3, "Front cover")
                ]
            ),
        )

    page.render_step_cards()

    assert page.step_output_consumer_indices(reference) == [1, 2]
    assert page.step_cards[1].status == "ready"
    assert page.step_cards[2].status == "blocked"
    assert page.step_cards[2].status_label.toolTip() == (
        "Output 1 from Step 1 is already used by Step 2."
    )

    owner_form = page.create_step_technique_form(page.pipeline_steps[1], 1)
    later_form = page.create_step_technique_form(page.pipeline_steps[2], 2)
    assert isinstance(owner_form, MetadataEmbedInputs)
    assert isinstance(later_form, MetadataEmbedInputs)
    assert reference in [
        output.reference
        for output in owner_form.mp3_form.apic_images_form.output_catalog
    ]
    later_apic = later_form.mp3_form.apic_images_form
    assert reference not in [
        output.reference for output in later_apic.output_catalog
    ]
    later_apic.begin_change_image(later_apic.cards[0])
    assert later_apic.output_picker.selected_output() == reference
    assert later_apic.output_picker.unavailable_reason() == (
        "Output 1 from Step 1 is already used by Step 2."
    )


def test_metadata_cover_and_apic_cannot_consume_the_same_output(
    tmp_path,
    monkeypatch,
) -> None:
    producer_cover = tmp_path / "producer.png"
    _write_png(producer_cover)
    _app_instance, page = _page_with_steps("lsbpp", "metadata")
    page.pipeline_steps[0].technique_inputs = LSBInputsDraft(
        cover=str(producer_cover),
        payload_text="producer payload",
        encryption_enabled=False,
    )
    reference = StepOutput(page.pipeline_steps[0].key, "result")
    consumer = page.pipeline_steps[1]
    consumer.technique_inputs = MetadataInputsDraft(
        cover=reference,
        payload=MP3MetadataDraft(
            apic_images=[ApicImageDraft(reference, 3, "Front cover")]
        ),
    )
    form = page.create_step_technique_form(consumer, 1)
    assert isinstance(form, MetadataEmbedInputs)
    warnings: list[tuple[str, str]] = []

    monkeypatch.setattr(form, "validate_draft", lambda: True)
    monkeypatch.setattr(
        form,
        "show_validation_warning",
        lambda message, *, title="": warnings.append((title, message))
        or False,
    )

    assert not page.save_step_draft(
        consumer.key,
        consumer.description,
        consumer.guidenote,
        form,
    )
    assert warnings == [
        (
            "Linked Output Already Used",
            "The same previous output cannot be used more than once in a "
            "Metadata step.",
        )
    ]
    page.render_step_cards()
    assert page.step_cards[1].status == "blocked"
    assert "used more than once" in page.step_cards[1].status_label.toolTip()


def test_apic_rejects_self_and_forward_references(tmp_path) -> None:
    first_cover = tmp_path / "first.mp3"
    first_cover.write_bytes(b"prototype mp3")
    _app_instance, page = _page_with_steps("metadata", "lsbpp")
    self_reference = StepOutput(page.pipeline_steps[0].key, "result")
    forward_reference = StepOutput(page.pipeline_steps[1].key, "result")

    page.pipeline_steps[0].technique_inputs = MetadataInputsDraft(
        cover=str(first_cover),
        payload=MP3MetadataDraft(
            apic_images=[
                ApicImageDraft(self_reference, 3, "Front cover")
            ]
        ),
    )
    assert page.step_dependency_error(0) == (
        "A step cannot use its own output."
    )

    page.pipeline_steps[0].technique_inputs.payload.apic_images = [
        ApicImageDraft(forward_reference, 3, "Front cover")
    ]
    assert page.step_dependency_error(0) == (
        "A step cannot use output from a later step."
    )


def test_deleted_apic_producer_blocks_recursive_chain_without_rewriting(
    tmp_path,
) -> None:
    producer_cover = tmp_path / "producer.png"
    middle_cover = tmp_path / "middle.mp3"
    _write_png(producer_cover)
    middle_cover.write_bytes(b"prototype mp3")
    _app_instance, page = _page_with_steps(
        "lsbpp",
        "metadata",
        "metadata",
    )
    root_key = page.pipeline_steps[0].key
    middle_key = page.pipeline_steps[1].key
    root_reference = StepOutput(root_key, "result")
    middle_reference = StepOutput(middle_key, "result")
    page.pipeline_steps[0].technique_inputs = LSBInputsDraft(
        cover=str(producer_cover),
        payload_text="root payload",
        encryption_enabled=False,
    )
    page.pipeline_steps[1].technique_inputs = MetadataInputsDraft(
        cover=str(middle_cover),
        payload=MP3MetadataDraft(
            apic_images=[
                ApicImageDraft(root_reference, 3, "Front cover")
            ]
        ),
    )
    page.pipeline_steps[2].technique_inputs = MetadataInputsDraft(
        cover=middle_reference,
        payload=MP3MetadataDraft(
            frames=[MP3SimpleFrameDraft("TIT2", "Downstream")]
        ),
    )
    page.render_step_cards()
    assert [card.status for card in page.step_cards] == [
        "ready",
        "ready",
        "ready",
    ]

    page.remove_pipeline_step(0)

    middle_draft = page.pipeline_steps[0].technique_inputs
    downstream_draft = page.pipeline_steps[1].technique_inputs
    assert middle_draft.payload.apic_images[0].image == root_reference
    assert downstream_draft.cover == middle_reference
    assert [step.key for step in page.pipeline_steps] == [
        middle_key,
        page.pipeline_steps[1].key,
    ]
    assert [card.step_number for card in page.step_cards] == [1, 2]
    assert page.step_cards[0].status_label.toolTip() == (
        "Source step no longer exists."
    )
    assert page.step_cards[1].status_label.toolTip() == (
        "Step 1 is blocked by an earlier dependency."
    )


def test_removed_locomotive_output_keeps_apic_reference_and_blocks_card(
    tmp_path,
) -> None:
    locomotive_cover = tmp_path / "locomotive.png"
    metadata_cover = tmp_path / "metadata.mp3"
    _write_png(locomotive_cover)
    metadata_cover.write_bytes(b"prototype mp3")
    _app_instance, page = _page_with_steps("locomotive", "metadata")
    output_key = "output_a4f91c2e"
    reference = StepOutput(page.pipeline_steps[0].key, output_key)
    page.pipeline_steps[0].technique_inputs = LocomotiveInputsDraft(
        covers=[LocomotiveCoverDraft(str(locomotive_cover), output_key)],
        payload_files=[str(tmp_path / "payload.bin")],
        encryption_enabled=False,
    )
    page.pipeline_steps[1].technique_inputs = MetadataInputsDraft(
        cover=str(metadata_cover),
        payload=MP3MetadataDraft(
            apic_images=[ApicImageDraft(reference, 3, "Front cover")]
        ),
    )
    page.render_step_cards()
    assert page.step_cards[1].status == "ready"

    page.pipeline_steps[0].technique_inputs.covers.clear()
    page.render_step_cards()

    saved = page.pipeline_steps[1].technique_inputs.payload.apic_images[0]
    assert saved.image == reference
    assert page.step_cards[1].status == "blocked"
    assert page.step_cards[1].status_label.toolTip() == (
        "Output is not available from Step 1."
    )


def test_apic_reference_survives_renumber_and_blocks_on_media_change(
    tmp_path,
) -> None:
    producer_png = tmp_path / "producer.png"
    producer_mp3 = tmp_path / "producer.mp3"
    consumer_mp3 = tmp_path / "consumer.mp3"
    _write_png(producer_png)
    producer_mp3.write_bytes(b"prototype mp3")
    consumer_mp3.write_bytes(b"prototype mp3")
    _app_instance, page = _page_with_steps(
        "lsbpp",
        "metadata",
        "metadata",
    )
    producer = page.pipeline_steps[1]
    consumer = page.pipeline_steps[2]
    producer.technique_inputs = MetadataInputsDraft(
        cover=str(producer_png),
        payload=PNGMetadataDraft(entries={"Title": "Producer"}),
    )
    reference = StepOutput(producer.key, "result")
    consumer.technique_inputs = MetadataInputsDraft(
        cover=str(consumer_mp3),
        payload=MP3MetadataDraft(
            apic_images=[ApicImageDraft(reference, 3, "Front cover")]
        ),
    )
    page.render_step_cards()
    assert page.step_cards[2].status == "ready"

    producer_key = producer.key
    consumer_key = consumer.key
    page.remove_pipeline_step(0)

    assert [step.key for step in page.pipeline_steps] == [
        producer_key,
        consumer_key,
    ]
    assert page.pipeline_steps[1].technique_inputs.payload.apic_images[
        0
    ].image == reference
    assert page.step_cards[1].status == "ready"

    page.pipeline_steps[0].technique_inputs = MetadataInputsDraft(
        cover=str(producer_mp3),
        payload=MP3MetadataDraft(
            frames=[MP3SimpleFrameDraft("TIT2", "Changed producer")]
        ),
    )
    page.render_step_cards()

    assert page.pipeline_steps[1].technique_inputs.payload.apic_images[
        0
    ].image == reference
    assert page.step_cards[1].status == "blocked"
    assert page.step_cards[1].status_label.toolTip() == (
        "MP3 output from Step 1 cannot be used here. Expected: PNG."
    )


def test_stale_apic_picker_selection_is_rechecked_when_saving(
    tmp_path,
    monkeypatch,
) -> None:
    producer_cover = tmp_path / "producer.png"
    owner_cover = tmp_path / "owner.mp3"
    target_cover = tmp_path / "target.mp3"
    _write_png(producer_cover)
    owner_cover.write_bytes(b"prototype mp3")
    target_cover.write_bytes(b"prototype mp3")
    _app_instance, page = _page_with_steps(
        "lsbpp",
        "metadata",
        "metadata",
    )
    page.pipeline_steps[0].technique_inputs = LSBInputsDraft(
        cover=str(producer_cover),
        payload_text="producer payload",
        encryption_enabled=False,
    )
    reference = StepOutput(page.pipeline_steps[0].key, "result")
    page.pipeline_steps[1].technique_inputs = MetadataInputsDraft(
        cover=str(owner_cover),
        payload=MP3MetadataDraft(),
    )
    target = page.pipeline_steps[2]
    target.technique_inputs = MetadataInputsDraft(
        cover=str(target_cover),
        payload=MP3MetadataDraft(),
    )
    form = page.create_step_technique_form(target, 2)
    assert isinstance(form, MetadataEmbedInputs)
    apic_form = form.mp3_form.apic_images_form
    apic_form.source_mode_toggle.set_mode("linked")
    apic_form.output_picker._select_from_click(reference)
    assert apic_form.confirm_add_image()

    page.pipeline_steps[1].technique_inputs.payload.apic_images = [
        ApicImageDraft(reference, 3, "Front cover")
    ]
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        form,
        "show_validation_warning",
        lambda message, *, title="": warnings.append((title, message))
        or False,
    )

    assert not page.save_step_draft(
        target.key,
        target.description,
        target.guidenote,
        form,
    )
    assert warnings == [
        (
            "Linked APIC Source Unavailable",
            "Output 1 from Step 1 is already used by Step 2.",
        )
    ]
    assert apic_form.cards[0].source_error == (
        "Output 1 from Step 1 is already used by Step 2."
    )
    assert reference not in [
        output.reference for output in apic_form.output_catalog
    ]
    apic_form.begin_change_image(apic_form.cards[0])
    assert apic_form.output_picker.selected_output() == reference
    assert apic_form.output_picker.unavailable_reason() == (
        "Output 1 from Step 1 is already used by Step 2."
    )
