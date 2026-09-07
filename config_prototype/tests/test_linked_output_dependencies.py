"""Focused tests for direct linked-output dependency validation."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from config_prototype.core.configurable import StepOutput
from config_prototype.gui.components.step_config_shell import (
    StepConfigShellPanel,
)
from config_prototype.gui.components.technique_forms import (
    LSBEmbedInputs,
    LSBInputsDraft,
    MetadataInputsDraft,
    MP3MetadataDraft,
)
from config_prototype.gui.pages.sub_pages.embed.configurable_page import (
    EmbedConfigurablePage,
)


_APP: QApplication | None = None


def _application() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def _page(*techniques: str) -> EmbedConfigurablePage:
    _application()
    page = EmbedConfigurablePage()
    for technique in techniques:
        page.add_pipeline_step(technique)
    return page


def _configure_lsb(page: EmbedConfigurablePage, index: int) -> None:
    page.pipeline_steps[index].technique_inputs = LSBInputsDraft(
        cover="D:/demo/cover.png",
        payload_text="Configured payload",
        encryption_enabled=False,
    )


def test_step_lookup_uses_stable_key_after_renumber() -> None:
    page = _page("metadata", "lsbpp", "lsbpp")
    producer_key = page.pipeline_steps[1].key
    producer = page.pipeline_steps[1]

    assert page.step_index_for_key(producer_key) == 1
    assert page.step_draft_for_key(producer_key) is producer
    assert page.step_index_for_key("step_missing") is None
    assert page.step_draft_for_key("step_missing") is None

    page.remove_pipeline_step(0)

    assert page.step_index_for_key(producer_key) == 0
    assert page.step_draft_for_key(producer_key) is producer


def test_step_output_info_declares_current_single_outputs() -> None:
    page = _page("lsbpp", "metadata", "locomotive")

    lsb_output = page.step_output_info(0, "result")
    assert lsb_output is not None
    assert lsb_output.reference == StepOutput(
        page.pipeline_steps[0].key,
        "result",
    )
    assert lsb_output.step_number == 1
    assert lsb_output.media_type == "png"

    assert page.step_output_info(0, "output_2") is None
    assert page.step_output_info(2, "result") is None
    with pytest.raises(IndexError, match="outside the pipeline"):
        page.step_output_info(3, "result")


def test_linked_output_accepts_configured_previous_png() -> None:
    page = _page("lsbpp", "lsbpp")
    _configure_lsb(page, 0)
    reference = StepOutput(page.pipeline_steps[0].key, "result")

    assert page.linked_output_error(reference, 1, {"PNG"}) is None


def test_linked_output_reports_missing_or_unconfigured_producer() -> None:
    page = _page("lsbpp", "lsbpp")
    source_key = page.pipeline_steps[0].key
    reference = StepOutput(source_key, "result")

    assert page.linked_output_error(reference, 1, {"png"}) == (
        "Step 1 is not configured yet."
    )

    page.remove_pipeline_step(0)

    assert page.linked_output_error(reference, 0, {"png"}) == (
        "Source step no longer exists."
    )


def test_linked_output_rejects_self_and_forward_references() -> None:
    page = _page("lsbpp", "lsbpp")
    _configure_lsb(page, 0)
    _configure_lsb(page, 1)

    self_reference = StepOutput(page.pipeline_steps[0].key, "result")
    future_reference = StepOutput(page.pipeline_steps[1].key, "result")

    assert page.linked_output_error(self_reference, 0, {"png"}) == (
        "A step cannot use its own output."
    )
    assert page.linked_output_error(future_reference, 0, {"png"}) == (
        "A step cannot use output from a later step."
    )


def test_linked_output_reports_removed_output_key() -> None:
    page = _page("lsbpp", "lsbpp")
    _configure_lsb(page, 0)
    reference = StepOutput(page.pipeline_steps[0].key, "output_2")

    assert page.linked_output_error(reference, 1, {"png"}) == (
        "Output 2 is not available from Step 1."
    )


def test_linked_output_reports_unknown_and_incompatible_media() -> None:
    page = _page("metadata", "metadata", "lsbpp")
    page.pipeline_steps[0].technique_inputs = MetadataInputsDraft()
    page.pipeline_steps[1].technique_inputs = MetadataInputsDraft(
        cover_path="D:/demo/audio.mp3",
        payload=MP3MetadataDraft(),
    )

    unknown = StepOutput(page.pipeline_steps[0].key, "result")
    mp3 = StepOutput(page.pipeline_steps[1].key, "result")

    assert page.linked_output_error(unknown, 2, {"png"}) == (
        "Step 1 output type is unknown."
    )
    assert page.linked_output_error(mp3, 2, {"png"}) == (
        "MP3 output from Step 2 cannot be used here. Expected: PNG."
    )


def test_linked_output_stays_valid_when_an_earlier_step_is_deleted() -> None:
    page = _page("metadata", "lsbpp", "lsbpp")
    _configure_lsb(page, 1)
    producer_key = page.pipeline_steps[1].key
    reference = StepOutput(producer_key, "result")

    assert page.linked_output_error(reference, 2, {"png"}) is None

    page.remove_pipeline_step(0)

    assert page.step_index_for_key(producer_key) == 0
    assert page.linked_output_error(reference, 1, {"png"}) is None


def test_linked_output_rejects_invalid_consumer_index() -> None:
    page = _page("lsbpp")
    reference = StepOutput(page.pipeline_steps[0].key, "result")

    with pytest.raises(IndexError, match="Consumer index"):
        page.linked_output_error(reference, 1, {"png"})


def test_linked_lsb_step_card_is_blocked_until_producer_is_configured() -> None:
    page = _page("lsbpp", "lsbpp")
    reference = StepOutput(page.pipeline_steps[0].key, "result")
    page.pipeline_steps[1].technique_inputs = LSBInputsDraft(
        cover=reference,
        payload_text="Dependent payload",
        encryption_enabled=False,
    )

    page.render_step_cards()

    consumer_card = page.step_cards[1]
    assert consumer_card.status == "blocked"
    assert consumer_card.status_label.toolTip() == (
        "Step 1 is not configured yet."
    )

    _configure_lsb(page, 0)
    page.render_step_cards()

    assert page.step_cards[1].status == "ready"


def test_deleting_producer_preserves_reference_and_blocks_step_card() -> None:
    page = _page("lsbpp", "lsbpp")
    _configure_lsb(page, 0)
    reference = StepOutput(page.pipeline_steps[0].key, "result")
    consumer_draft = LSBInputsDraft(
        cover=reference,
        payload_text="Dependent payload",
        encryption_enabled=False,
    )
    page.pipeline_steps[1].technique_inputs = consumer_draft
    page.render_step_cards()
    assert page.step_cards[1].status == "ready"

    page.remove_pipeline_step(0)

    assert page.pipeline_steps[0].technique_inputs is consumer_draft
    assert consumer_draft.cover == reference
    assert page.step_cards[0].status == "blocked"
    assert page.step_cards[0].summary_text("cover") == "Source unavailable"
    assert page.step_cards[0].summary_tooltip("cover") == (
        "Source step no longer exists."
    )
    assert page.step_cards[0].status_label.toolTip() == (
        "Source step no longer exists."
    )


def test_incompatible_link_blocks_lsb_step_card() -> None:
    page = _page("metadata", "lsbpp")
    page.pipeline_steps[0].technique_inputs = MetadataInputsDraft(
        cover_path="D:/demo/audio.mp3",
        payload=MP3MetadataDraft(),
    )
    page.pipeline_steps[1].technique_inputs = LSBInputsDraft(
        cover=StepOutput(page.pipeline_steps[0].key, "result"),
        payload_text="Dependent payload",
        encryption_enabled=False,
    )

    page.render_step_cards()

    assert page.step_cards[1].status == "blocked"
    assert page.step_cards[1].status_label.toolTip() == (
        "MP3 output from Step 1 cannot be used here. Expected: PNG."
    )


def test_broken_saved_reference_is_visible_in_lsb_picker() -> None:
    page = _page("lsbpp", "lsbpp")
    _configure_lsb(page, 0)
    missing_reference = StepOutput("step_missing", "result")
    page.pipeline_steps[1].technique_inputs = LSBInputsDraft(
        cover=missing_reference,
        payload_text="Saved payload",
        encryption_enabled=False,
    )

    form = page.create_step_technique_form(page.pipeline_steps[1], 1)
    assert isinstance(form, LSBEmbedInputs)
    form.show()
    _application().processEvents()

    picker = form.cover_output_picker
    assert form.cover_mode_toggle.mode() == "linked"
    assert picker.selected_output() == missing_reference
    assert picker.unavailable_reason() == "Source step no longer exists."
    assert picker.unavailable_frame.isVisible()
    assert "Source step no longer exists." in picker.unavailable_detail.text()
    assert "step_missing" not in picker.unavailable_detail.text()
    assert not picker.preview_frame.isVisible()
    assert len(picker.candidates()) == 1


def test_broken_link_cannot_save_until_replaced(monkeypatch) -> None:
    page = _page("lsbpp", "lsbpp")
    _configure_lsb(page, 0)
    replacement = StepOutput(page.pipeline_steps[0].key, "result")
    missing_reference = StepOutput("step_missing", "result")
    original_draft = LSBInputsDraft(
        cover=missing_reference,
        payload_text="Saved payload",
        encryption_enabled=False,
    )
    consumer = page.pipeline_steps[1]
    consumer.technique_inputs = original_draft
    form = page.create_step_technique_form(consumer, 1)
    assert isinstance(form, LSBEmbedInputs)
    form.show()
    _application().processEvents()
    warnings: list[tuple[str, str]] = []

    def capture_warning(message: str, *, title: str = "") -> bool:
        warnings.append((title, message))
        return False

    monkeypatch.setattr(form, "show_validation_warning", capture_warning)

    assert not page.save_step_draft(
        consumer.key,
        consumer.description,
        consumer.guidenote,
        form,
    )
    assert consumer.technique_inputs is original_draft
    assert warnings == [
        ("Linked Output Unavailable", "Source step no longer exists.")
    ]
    assert form.cover_output_picker.unavailable_frame.isVisible()
    assert form.cover_output_picker.unavailable_reason() == (
        "Source step no longer exists."
    )

    QTest.mouseClick(
        form.cover_output_picker._rows[0],
        Qt.MouseButton.LeftButton,
    )
    assert form.cover_source == replacement
    assert form.cover_output_picker.unavailable_reason() is None
    assert page.save_step_draft(
        consumer.key,
        consumer.description,
        consumer.guidenote,
        form,
    )

    saved = consumer.technique_inputs
    assert isinstance(saved, LSBInputsDraft)
    assert saved.cover == replacement
    page.render_step_cards()
    assert page.step_cards[1].status == "ready"


def test_cancel_after_selecting_replacement_keeps_broken_draft() -> None:
    page = _page("lsbpp", "lsbpp")
    _configure_lsb(page, 0)
    missing_reference = StepOutput("step_missing", "result")
    original_draft = LSBInputsDraft(
        cover=missing_reference,
        payload_text="Saved payload",
        encryption_enabled=False,
    )
    page.pipeline_steps[1].technique_inputs = original_draft
    page.render_step_cards()
    page.set_config_variant("inline")
    page.open_step_config_inline(1)

    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    form = panel.shell.content_widget
    assert isinstance(form, LSBEmbedInputs)
    QTest.mouseClick(
        form.cover_output_picker._rows[0],
        Qt.MouseButton.LeftButton,
    )
    assert form.cover_source == StepOutput(
        page.pipeline_steps[0].key,
        "result",
    )

    panel.cancel_button.click()
    _application().processEvents()

    assert page.active_step_panel is None
    assert page.pipeline_steps[1].technique_inputs is original_draft
    assert original_draft.cover == missing_reference
    assert page.step_cards[1].status == "blocked"


def test_delete_before_producer_renumbers_display_without_breaking_link() -> None:
    page = _page("metadata", "lsbpp", "lsbpp")
    _configure_lsb(page, 1)
    producer_key = page.pipeline_steps[1].key
    consumer_key = page.pipeline_steps[2].key
    reference = StepOutput(producer_key, "result")
    page.pipeline_steps[2].technique_inputs = LSBInputsDraft(
        cover=reference,
        payload_text="Dependent payload",
        encryption_enabled=False,
    )
    page.render_step_cards()

    page.remove_pipeline_step(0)

    assert [step.key for step in page.pipeline_steps] == [
        producer_key,
        consumer_key,
    ]
    assert page.pipeline_steps[1].technique_inputs.cover == reference
    assert [card.step_number for card in page.step_cards] == [1, 2]
    assert page.flow_layout.count() - len(page.step_cards) == 1
    assert page.step_cards[1].summary_text("cover") == (
        "From STEP 1, Output 1"
    )
    assert page.step_cards[1].status == "ready"


def test_deleted_root_producer_blocks_the_whole_dependency_chain() -> None:
    page = _page("lsbpp", "lsbpp", "lsbpp")
    _configure_lsb(page, 0)
    first_reference = StepOutput(page.pipeline_steps[0].key, "result")
    second_reference = StepOutput(page.pipeline_steps[1].key, "result")
    page.pipeline_steps[1].technique_inputs = LSBInputsDraft(
        cover=first_reference,
        payload_text="Middle payload",
        encryption_enabled=False,
    )
    page.pipeline_steps[2].technique_inputs = LSBInputsDraft(
        cover=second_reference,
        payload_text="Final payload",
        encryption_enabled=False,
    )
    page.render_step_cards()
    assert [card.status for card in page.step_cards] == [
        "ready",
        "ready",
        "ready",
    ]

    page.remove_pipeline_step(0)

    middle_draft = page.pipeline_steps[0].technique_inputs
    final_draft = page.pipeline_steps[1].technique_inputs
    assert middle_draft.cover == first_reference
    assert final_draft.cover == second_reference
    assert [card.step_number for card in page.step_cards] == [1, 2]
    assert page.flow_layout.count() - len(page.step_cards) == 1
    assert page.step_cards[0].status_label.toolTip() == (
        "Source step no longer exists."
    )
    assert page.step_cards[1].status_label.toolTip() == (
        "Step 1 is blocked by an earlier dependency."
    )
    assert [card.status for card in page.step_cards] == [
        "blocked",
        "blocked",
    ]


def test_dependency_chain_recovers_without_rewriting_downstream_reference() -> None:
    page = _page("lsbpp", "lsbpp")
    missing_reference = StepOutput("step_missing", "result")
    producer_key = page.pipeline_steps[0].key
    downstream_reference = StepOutput(producer_key, "result")
    page.pipeline_steps[0].technique_inputs = LSBInputsDraft(
        cover=missing_reference,
        payload_text="Producer payload",
        encryption_enabled=False,
    )
    page.pipeline_steps[1].technique_inputs = LSBInputsDraft(
        cover=downstream_reference,
        payload_text="Consumer payload",
        encryption_enabled=False,
    )
    page.render_step_cards()
    assert [card.status for card in page.step_cards] == [
        "blocked",
        "blocked",
    ]

    _configure_lsb(page, 0)
    page.render_step_cards()

    assert page.pipeline_steps[1].technique_inputs.cover == downstream_reference
    assert [card.status for card in page.step_cards] == ["ready", "ready"]


def test_recursive_error_is_shown_in_picker_and_rejected_on_save(
    monkeypatch,
) -> None:
    page = _page("lsbpp", "lsbpp")
    page.pipeline_steps[0].technique_inputs = LSBInputsDraft(
        cover=StepOutput("step_missing", "result"),
        payload_text="Producer payload",
        encryption_enabled=False,
    )
    reference = StepOutput(page.pipeline_steps[0].key, "result")
    consumer = page.pipeline_steps[1]
    original_draft = LSBInputsDraft(
        cover=reference,
        payload_text="Consumer payload",
        encryption_enabled=False,
    )
    consumer.technique_inputs = original_draft

    form = page.create_step_technique_form(consumer, 1)
    assert isinstance(form, LSBEmbedInputs)
    form.show()
    _application().processEvents()
    assert form.cover_output_picker.unavailable_reason() == (
        "Step 1 is blocked by an earlier dependency."
    )

    warnings: list[tuple[str, str]] = []

    def capture_warning(message: str, *, title: str = "") -> bool:
        warnings.append((title, message))
        return False

    monkeypatch.setattr(form, "show_validation_warning", capture_warning)

    assert not page.save_step_draft(
        consumer.key,
        consumer.description,
        consumer.guidenote,
        form,
    )
    assert consumer.technique_inputs is original_draft
    assert warnings == [
        (
            "Linked Output Unavailable",
            "Step 1 is blocked by an earlier dependency.",
        )
    ]


def test_recursive_validation_guards_circular_imported_drafts() -> None:
    page = _page("lsbpp", "lsbpp")
    first_key = page.pipeline_steps[0].key
    second_key = page.pipeline_steps[1].key
    page.pipeline_steps[0].technique_inputs = LSBInputsDraft(
        cover=StepOutput(second_key, "result"),
        payload_text="First payload",
        encryption_enabled=False,
    )
    page.pipeline_steps[1].technique_inputs = LSBInputsDraft(
        cover=StepOutput(first_key, "result"),
        payload_text="Second payload",
        encryption_enabled=False,
    )

    page.render_step_cards()

    assert page.step_dependency_error(0) == "Circular dependency detected."
    assert page.step_dependency_error(1) == "Circular dependency detected."
    assert [card.status for card in page.step_cards] == [
        "blocked",
        "blocked",
    ]
    assert all(
        card.status_label.toolTip() == "Circular dependency detected."
        for card in page.step_cards
    )


def test_chain_picker_only_lists_the_latest_unused_output() -> None:
    page = _page("lsbpp", "lsbpp", "lsbpp")
    _configure_lsb(page, 0)
    first_reference = StepOutput(page.pipeline_steps[0].key, "result")
    second_reference = StepOutput(page.pipeline_steps[1].key, "result")
    page.pipeline_steps[1].technique_inputs = LSBInputsDraft(
        cover=first_reference,
        payload_text="Middle payload",
        encryption_enabled=False,
    )
    page.pipeline_steps[2].technique_inputs = LSBInputsDraft(
        cover=second_reference,
        payload_text="Final payload",
        encryption_enabled=False,
    )

    middle_form = page.create_step_technique_form(
        page.pipeline_steps[1],
        1,
    )
    final_form = page.create_step_technique_form(
        page.pipeline_steps[2],
        2,
    )

    assert isinstance(middle_form, LSBEmbedInputs)
    assert isinstance(final_form, LSBEmbedInputs)
    assert [
        output.reference
        for output in middle_form.cover_output_picker.candidates()
    ] == [first_reference]
    assert [
        output.reference
        for output in final_form.cover_output_picker.candidates()
    ] == [second_reference]


def test_saved_consumer_owns_output_and_later_duplicate_is_blocked() -> None:
    page = _page("lsbpp", "lsbpp", "lsbpp")
    _configure_lsb(page, 0)
    reference = StepOutput(page.pipeline_steps[0].key, "result")
    page.pipeline_steps[1].technique_inputs = LSBInputsDraft(
        cover=reference,
        payload_text="Owner payload",
        encryption_enabled=False,
    )
    duplicate_draft = LSBInputsDraft(
        cover=reference,
        payload_text="Duplicate payload",
        encryption_enabled=False,
    )
    page.pipeline_steps[2].technique_inputs = duplicate_draft

    page.render_step_cards()

    assert page.step_output_consumer_indices(reference) == [1, 2]
    assert page.step_output_usage_error(reference, 1) is None
    assert page.step_output_usage_error(reference, 2) == (
        "Output 1 from Step 1 is already used by Step 2."
    )
    assert [card.status for card in page.step_cards] == [
        "ready",
        "ready",
        "blocked",
    ]
    assert page.step_cards[2].status_label.toolTip() == (
        "Output 1 from Step 1 is already used by Step 2."
    )

    page.remove_pipeline_step(1)

    assert page.pipeline_steps[1].technique_inputs is duplicate_draft
    assert page.step_output_consumer_indices(reference) == [1]
    assert page.step_cards[1].status == "ready"


def test_deleting_consumer_releases_output_for_another_step() -> None:
    page = _page("lsbpp", "lsbpp", "lsbpp")
    _configure_lsb(page, 0)
    reference = StepOutput(page.pipeline_steps[0].key, "result")
    page.pipeline_steps[1].technique_inputs = LSBInputsDraft(
        cover=reference,
        payload_text="Owner payload",
        encryption_enabled=False,
    )
    owner_output = StepOutput(page.pipeline_steps[1].key, "result")

    before_delete_form = page.create_step_technique_form(
        page.pipeline_steps[2],
        2,
    )
    assert isinstance(before_delete_form, LSBEmbedInputs)
    assert [
        output.reference
        for output in before_delete_form.cover_output_picker.candidates()
    ] == [owner_output]

    page.remove_pipeline_step(1)
    released_form = page.create_step_technique_form(
        page.pipeline_steps[1],
        1,
    )

    assert isinstance(released_form, LSBEmbedInputs)
    assert [
        output.reference
        for output in released_form.cover_output_picker.candidates()
    ] == [reference]


def test_changing_consumer_to_manual_releases_output() -> None:
    page = _page("lsbpp", "lsbpp", "lsbpp")
    _configure_lsb(page, 0)
    reference = StepOutput(page.pipeline_steps[0].key, "result")
    page.pipeline_steps[1].technique_inputs = LSBInputsDraft(
        cover=reference,
        payload_text="Owner payload",
        encryption_enabled=False,
    )
    assert page.step_output_consumer_indices(reference) == [1]

    _configure_lsb(page, 1)

    assert page.step_output_consumer_indices(reference) == []
    form = page.create_step_technique_form(page.pipeline_steps[2], 2)
    assert isinstance(form, LSBEmbedInputs)
    assert [
        output.reference
        for output in form.cover_output_picker.candidates()
    ] == [
        reference,
        StepOutput(page.pipeline_steps[1].key, "result"),
    ]


def test_stale_form_cannot_save_output_claimed_after_it_opened(
    monkeypatch,
) -> None:
    page = _page("lsbpp", "lsbpp", "lsbpp")
    _configure_lsb(page, 0)
    reference = StepOutput(page.pipeline_steps[0].key, "result")
    contender = page.pipeline_steps[2]
    form = page.create_step_technique_form(contender, 2)
    assert isinstance(form, LSBEmbedInputs)
    form.load_draft(
        LSBInputsDraft(
            cover=reference,
            payload_text="Contender payload",
            encryption_enabled=False,
        )
    )

    page.pipeline_steps[1].technique_inputs = LSBInputsDraft(
        cover=reference,
        payload_text="Owner payload",
        encryption_enabled=False,
    )
    warnings: list[tuple[str, str]] = []

    def capture_warning(message: str, *, title: str = "") -> bool:
        warnings.append((title, message))
        return False

    monkeypatch.setattr(form, "show_validation_warning", capture_warning)

    assert not page.save_step_draft(
        contender.key,
        contender.description,
        contender.guidenote,
        form,
    )
    assert contender.technique_inputs is None
    assert warnings == [
        (
            "Linked Output Unavailable",
            "Output 1 from Step 1 is already used by Step 2.",
        )
    ]
