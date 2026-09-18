"""Focused tests for Locomotive multi-output catalog and linked covers."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

from config_prototype.core.configurable import StepOutput, StepOutputInfo
from config_prototype.gui.components.step_config_shell import (
    StepConfigShellDialog,
    StepConfigShellPanel,
)
from config_prototype.gui.components.step_output_picker import (
    OUTPUT_LIST_MAX_HEIGHT,
    OUTPUT_ROW_MIN_HEIGHT,
    StepOutputPicker,
    output_info_display_name,
)
from config_prototype.gui.components.technique_forms import (
    LSBInputsDraft,
    LocomotiveCoverDraft,
    LocomotiveEmbedInputs,
    LocomotiveInputsDraft,
)
from config_prototype.gui.pages.sub_pages.embed.configurable_page import (
    EmbedConfigurablePage,
)


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _process_events(app: QApplication) -> None:
    for _ in range(4):
        app.processEvents()


def _configured_lsb(cover_path: Path, payload: str) -> LSBInputsDraft:
    return LSBInputsDraft(
        cover=str(cover_path),
        payload_text=payload,
        encryption_enabled=False,
    )


def test_locomotive_catalog_uses_stable_keys_and_cover_order(
    tmp_path,
) -> None:
    app = _app()
    first_path = tmp_path / "first.png"
    second_path = tmp_path / "second.png"
    first_path.write_bytes(b"first preview")
    second_path.write_bytes(b"second preview")

    page = EmbedConfigurablePage()
    page.add_pipeline_step("locomotive")
    page.add_pipeline_step("lsbpp")
    producer = page.pipeline_steps[0]
    first = LocomotiveCoverDraft(
        str(first_path),
        "output_a4f91c2e",
    )
    second = LocomotiveCoverDraft(
        str(second_path),
        "output_12bd770a",
    )
    producer.technique_inputs = LocomotiveInputsDraft(
        covers=[first, second],
        payload_mode="text",
        payload_text="payload",
        encryption_enabled=False,
    )

    catalog = page.build_output_catalog(1)
    assert [item.reference.output_key for item in catalog] == [
        first.output_key,
        second.output_key,
    ]
    assert [item.display_name for item in catalog] == [
        "Output 1",
        "Output 2",
    ]
    assert [item.preview_path for item in catalog] == [
        str(first_path),
        str(second_path),
    ]

    producer.technique_inputs.covers = [second, first]
    reordered = page.build_output_catalog(1)
    assert [item.reference.output_key for item in reordered] == [
        second.output_key,
        first.output_key,
    ]
    assert [item.display_name for item in reordered] == [
        "Output 1",
        "Output 2",
    ]
    _process_events(app)


def test_step_output_picker_supports_multiple_selections() -> None:
    app = _app()
    references = [
        StepOutput("step_a31f8", "output_a4f91c2e"),
        StepOutput("step_a31f8", "output_12bd770a"),
    ]
    picker = StepOutputPicker(
        [
            StepOutputInfo(
                reference=reference,
                step_number=1,
                technique="locomotive",
                media_type="png",
                display_name=f"Output {index}",
            )
            for index, reference in enumerate(references, start=1)
        ],
        multiple=True,
    )
    picker.show()
    _process_events(app)
    signal = QSignalSpy(picker.selections_changed)

    QTest.mouseClick(picker._rows[0], Qt.MouseButton.LeftButton)
    QTest.mouseClick(picker._rows[1], Qt.MouseButton.LeftButton)
    assert picker.selected_outputs() == references
    assert all(row.property("selected") for row in picker._rows)

    QTest.mouseClick(picker._rows[0], Qt.MouseButton.LeftButton)
    assert picker.selected_outputs() == [references[1]]
    assert len(signal) == 3


def test_step_output_picker_scrolls_long_catalog_without_compressing_rows() -> None:
    app = _app()
    candidates = [
        StepOutputInfo(
            reference=StepOutput(
                f"step_{index:05x}",
                f"output_{index:08x}",
            ),
            step_number=(index // 4) + 1,
            technique="locomotive",
            media_type="png",
            display_name=f"Output {(index % 4) + 1}",
        )
        for index in range(16)
    ]

    short_picker = StepOutputPicker(candidates[:3], multiple=True)
    short_picker.resize(700, 500)
    short_picker.show()
    long_picker = StepOutputPicker(candidates, multiple=True)
    long_picker.resize(700, 500)
    long_picker.show()
    _process_events(app)

    assert short_picker.output_scroll.height() < OUTPUT_LIST_MAX_HEIGHT
    assert short_picker.output_scroll.verticalScrollBar().maximum() == 0
    assert short_picker.header.y() == 0
    assert short_picker.output_scroll.y() == (
        short_picker.header.height() + short_picker.content_layout.spacing()
    )
    assert long_picker.output_scroll.height() == OUTPUT_LIST_MAX_HEIGHT
    assert long_picker.output_scroll.verticalScrollBar().maximum() > 0
    assert all(
        row.height() >= OUTPUT_ROW_MIN_HEIGHT
        for row in long_picker._rows
    )


def test_locomotive_linked_covers_save_reopen_and_update_card(
    tmp_path,
) -> None:
    app = _app()
    root_cover = tmp_path / "root.png"
    second_cover = tmp_path / "second.png"
    root_cover.write_bytes(b"root")
    second_cover.write_bytes(b"second")

    page = EmbedConfigurablePage()
    for technique in ("lsbpp", "lsbpp", "locomotive"):
        page.add_pipeline_step(technique)
    page.pipeline_steps[0].technique_inputs = _configured_lsb(
        root_cover,
        "first",
    )
    page.pipeline_steps[1].technique_inputs = _configured_lsb(
        second_cover,
        "second",
    )
    page.render_step_cards()

    page.set_config_variant("inline")
    page.open_step_config_inline(2)
    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    form = panel.shell.content_widget
    assert isinstance(form, LocomotiveEmbedInputs)
    assert [
        output_info_display_name(item)
        for item in form.cover_output_picker.candidates()
    ] == ["Output 1", "Output 1"]

    form.cover_mode_toggle.linked_button.click()
    QTest.mouseClick(
        form.cover_output_picker._rows[0],
        Qt.MouseButton.LeftButton,
    )
    QTest.mouseClick(
        form.cover_output_picker._rows[1],
        Qt.MouseButton.LeftButton,
    )
    form.payload_tabs.setCurrentIndex(1)
    form.payload_text_area.setPlainText("Linked covers")
    form.encrypt_toggle_switch.setChecked(False)
    panel.save_button.click()
    _process_events(app)

    saved = page.pipeline_steps[2].technique_inputs
    assert isinstance(saved, LocomotiveInputsDraft)
    source_references = [cover.source for cover in saved.covers]
    assert source_references == [
        StepOutput(page.pipeline_steps[0].key, "result"),
        StepOutput(page.pipeline_steps[1].key, "result"),
    ]
    assert len({cover.output_key for cover in saved.covers}) == 2
    assert page.step_cards[2].summary_text("cover") == "PNG ×2"
    assert page.step_cards[2].summary_tooltip("cover") == (
        "Cover PNGs (2):\n"
        "1. From STEP 1, Output 1\n"
        "2. From STEP 2, Output 1"
    )

    page.open_step_config_inline(2)
    reopened = page.active_step_panel
    assert isinstance(reopened, StepConfigShellPanel)
    reopened_form = reopened.shell.content_widget
    assert isinstance(reopened_form, LocomotiveEmbedInputs)
    assert reopened_form.cover_mode_toggle.mode() == "linked"
    assert reopened_form.cover_output_picker.selected_outputs() == (
        source_references
    )
    assert reopened_form.locomotive_covers == saved.covers


def test_lsb_picker_lists_each_locomotive_output(tmp_path) -> None:
    app = _app()
    covers = [tmp_path / "one.png", tmp_path / "two.png"]
    for cover in covers:
        cover.write_bytes(b"preview")

    page = EmbedConfigurablePage()
    page.add_pipeline_step("locomotive")
    page.add_pipeline_step("lsbpp")
    producer = page.pipeline_steps[0]
    producer.technique_inputs = LocomotiveInputsDraft(
        covers=[
            LocomotiveCoverDraft(str(covers[0]), "output_a4f91c2e"),
            LocomotiveCoverDraft(str(covers[1]), "output_12bd770a"),
        ],
        payload_mode="text",
        payload_text="payload",
        encryption_enabled=False,
    )

    form = page.create_step_technique_form(page.pipeline_steps[1], 1)
    candidates = form.cover_output_picker.candidates()
    assert [output_info_display_name(candidate) for candidate in candidates] == [
        "Output 1",
        "Output 2",
    ]
    assert all(candidate.technique == "locomotive" for candidate in candidates)
    assert all("a4f91c2e" not in row.accessibleName() for row in form.cover_output_picker._rows)
    _process_events(app)


def test_locomotive_linked_payload_save_reopen_and_update_card(
    tmp_path,
) -> None:
    app = _app()
    producer_cover = tmp_path / "producer.png"
    consumer_cover = tmp_path / "consumer.png"
    producer_cover.write_bytes(b"producer")
    consumer_cover.write_bytes(b"consumer")

    page = EmbedConfigurablePage()
    page.add_pipeline_step("lsbpp")
    page.add_pipeline_step("locomotive")
    producer = page.pipeline_steps[0]
    producer.technique_inputs = _configured_lsb(
        producer_cover,
        "nested payload",
    )
    reference = StepOutput(producer.key, "result")

    page.set_config_variant("inline")
    page.open_step_config_inline(1)
    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    form = panel.shell.content_widget
    assert isinstance(form, LocomotiveEmbedInputs)
    form.cover_drop_zone.add_files([str(consumer_cover)])
    form.payload_mode_toggle.linked_button.click()
    QTest.mouseClick(
        form.payload_output_picker._rows[0],
        Qt.MouseButton.LeftButton,
    )
    form.encrypt_toggle_switch.setChecked(False)
    panel.save_button.click()
    _process_events(app)

    saved = page.pipeline_steps[1].technique_inputs
    assert isinstance(saved, LocomotiveInputsDraft)
    assert saved.payload_files == [reference]
    assert page.step_cards[1].summary_text("payload") == "Files ×1 (at run)"
    assert page.step_cards[1].summary_tooltip("payload") == (
        "Payload files (1):\n1. From STEP 1, Output 1"
    )

    page.open_step_config_inline(1)
    reopened = page.active_step_panel
    assert isinstance(reopened, StepConfigShellPanel)
    reopened_form = reopened.shell.content_widget
    assert isinstance(reopened_form, LocomotiveEmbedInputs)
    assert reopened_form.payload_mode_toggle.mode() == "linked"
    assert reopened_form.payload_output_picker.selected_outputs() == [
        reference
    ]
    assert reopened_form.payload_files == [reference]


def test_locomotive_claim_is_visible_only_in_its_saved_input_role(
    tmp_path,
) -> None:
    app = _app()
    producer_cover = tmp_path / "producer.png"
    consumer_cover = tmp_path / "consumer.png"
    producer_cover.write_bytes(b"producer")
    consumer_cover.write_bytes(b"consumer")

    page = EmbedConfigurablePage()
    for technique in ("lsbpp", "locomotive", "locomotive"):
        page.add_pipeline_step(technique)
    producer = page.pipeline_steps[0]
    producer.technique_inputs = _configured_lsb(producer_cover, "payload")
    reference = StepOutput(producer.key, "result")
    page.pipeline_steps[1].technique_inputs = LocomotiveInputsDraft(
        covers=[LocomotiveCoverDraft(reference, "output_a4f91c2e")],
        payload_mode="text",
        payload_text="consumer",
        encryption_enabled=False,
    )

    owner_form = page.create_step_technique_form(page.pipeline_steps[1], 1)
    assert isinstance(owner_form, LocomotiveEmbedInputs)
    assert [
        item.reference for item in owner_form.cover_output_picker.candidates()
    ] == [reference]
    assert owner_form.payload_output_picker.candidates() == []

    later_form = page.create_step_technique_form(page.pipeline_steps[2], 2)
    assert isinstance(later_form, LocomotiveEmbedInputs)
    assert reference not in {
        item.reference for item in later_form.cover_output_picker.candidates()
    }
    assert reference not in {
        item.reference
        for item in later_form.payload_output_picker.candidates()
    }

    page.pipeline_steps[1].technique_inputs = LocomotiveInputsDraft(
        covers=[LocomotiveCoverDraft(str(consumer_cover))],
        payload_mode="text",
        payload_text="manual replacement",
        encryption_enabled=False,
    )
    released_form = page.create_step_technique_form(
        page.pipeline_steps[2],
        2,
    )
    assert isinstance(released_form, LocomotiveEmbedInputs)
    assert reference in {
        item.reference
        for item in released_form.payload_output_picker.candidates()
    }
    _process_events(app)


def test_same_output_cannot_be_used_as_cover_and_payload(
    tmp_path,
    monkeypatch,
) -> None:
    app = _app()
    producer_cover = tmp_path / "producer.png"
    producer_cover.write_bytes(b"producer")
    page = EmbedConfigurablePage()
    page.add_pipeline_step("lsbpp")
    page.add_pipeline_step("locomotive")
    producer = page.pipeline_steps[0]
    producer.technique_inputs = _configured_lsb(producer_cover, "payload")
    reference = StepOutput(producer.key, "result")

    form = LocomotiveEmbedInputs()
    form.locomotive_covers = [
        LocomotiveCoverDraft(reference, "output_a4f91c2e")
    ]
    form.payload_files = [reference]
    form.encrypt_toggle_switch.setChecked(False)
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )

    assert page.save_step_draft(
        page.pipeline_steps[1].key,
        "Duplicate source",
        "",
        form,
    ) is False
    assert page.pipeline_steps[1].technique_inputs is None
    assert warnings == [
        (
            "Linked Output Already Used",
            "The same previous output cannot be used more than once in a "
            "Locomotive step.",
        )
    ]
    _process_events(app)


def test_removed_producer_keeps_locomotive_reference_blocked_and_visible(
    tmp_path,
) -> None:
    app = _app()
    producer_cover = tmp_path / "producer.png"
    consumer_cover = tmp_path / "consumer.png"
    producer_cover.write_bytes(b"producer")
    consumer_cover.write_bytes(b"consumer")
    page = EmbedConfigurablePage()
    page.add_pipeline_step("lsbpp")
    page.add_pipeline_step("locomotive")
    producer = page.pipeline_steps[0]
    producer.technique_inputs = _configured_lsb(producer_cover, "payload")
    reference = StepOutput(producer.key, "result")
    consumer = page.pipeline_steps[1]
    consumer.technique_inputs = LocomotiveInputsDraft(
        covers=[LocomotiveCoverDraft(str(consumer_cover))],
        payload_files=[reference],
        encryption_enabled=False,
    )

    page.remove_pipeline_step(0)
    assert page.pipeline_steps[0].technique_inputs.payload_files == [reference]
    assert page.step_cards[0].status == "blocked"
    assert page.step_cards[0].status_label.toolTip() == (
        "Source step no longer exists."
    )

    form = page.create_step_technique_form(page.pipeline_steps[0], 0)
    assert isinstance(form, LocomotiveEmbedInputs)
    assert form.payload_output_picker.selected_outputs() == [reference]
    assert form.payload_output_picker.unavailable_frame.isVisible() is False
    form.show()
    _process_events(app)
    assert form.payload_output_picker.unavailable_frame.isVisible()
    assert "Source step no longer exists" in (
        form.payload_output_picker.unavailable_detail.text()
    )


def test_locomotive_dependency_error_propagates_through_nested_outputs(
    tmp_path,
) -> None:
    app = _app()
    root_path = tmp_path / "root.png"
    middle_path = tmp_path / "middle.png"
    root_path.write_bytes(b"root")
    middle_path.write_bytes(b"middle")
    page = EmbedConfigurablePage()
    for technique in ("lsbpp", "locomotive", "locomotive"):
        page.add_pipeline_step(technique)

    root = page.pipeline_steps[0]
    middle = page.pipeline_steps[1]
    leaf = page.pipeline_steps[2]
    root.technique_inputs = _configured_lsb(root_path, "root")
    root_reference = StepOutput(root.key, "result")
    middle_output_key = "output_a4f91c2e"
    middle.technique_inputs = LocomotiveInputsDraft(
        covers=[
            LocomotiveCoverDraft(root_reference, middle_output_key)
        ],
        payload_mode="text",
        payload_text="middle",
        encryption_enabled=False,
    )
    leaf.technique_inputs = LocomotiveInputsDraft(
        covers=[LocomotiveCoverDraft(str(middle_path))],
        payload_files=[StepOutput(middle.key, middle_output_key)],
        encryption_enabled=False,
    )

    page.remove_pipeline_step(0)
    assert page.step_cards[0].status == "blocked"
    assert page.step_cards[1].status == "blocked"
    assert page.step_cards[1].status_label.toolTip() == (
        "Step 1 is blocked by an earlier dependency."
    )


def test_locomotive_duplicate_consumer_is_blocked_by_first_owner(
    tmp_path,
) -> None:
    app = _app()
    root_path = tmp_path / "root.png"
    first_cover = tmp_path / "first.png"
    second_cover = tmp_path / "second.png"
    for path in (root_path, first_cover, second_cover):
        path.write_bytes(b"png")

    page = EmbedConfigurablePage()
    for technique in ("lsbpp", "locomotive", "locomotive"):
        page.add_pipeline_step(technique)
    root = page.pipeline_steps[0]
    root.technique_inputs = _configured_lsb(root_path, "payload")
    reference = StepOutput(root.key, "result")
    page.pipeline_steps[1].technique_inputs = LocomotiveInputsDraft(
        covers=[LocomotiveCoverDraft(reference)],
        payload_mode="text",
        payload_text="first owner",
        encryption_enabled=False,
    )
    page.pipeline_steps[2].technique_inputs = LocomotiveInputsDraft(
        covers=[LocomotiveCoverDraft(str(second_cover))],
        payload_files=[reference],
        encryption_enabled=False,
    )

    page.render_step_cards()
    assert page.step_cards[1].status == "ready"
    assert page.step_cards[2].status == "blocked"
    assert page.step_cards[2].status_label.toolTip() == (
        "Output 1 from Step 1 is already used by Step 2."
    )
    _process_events(app)


def test_locomotive_references_participate_in_cycle_detection() -> None:
    app = _app()
    page = EmbedConfigurablePage()
    page.add_pipeline_step("locomotive")
    page.add_pipeline_step("locomotive")
    first = page.pipeline_steps[0]
    second = page.pipeline_steps[1]
    first_output_key = "output_a4f91c2e"
    second_output_key = "output_12bd770a"
    first.technique_inputs = LocomotiveInputsDraft(
        covers=[
            LocomotiveCoverDraft(
                StepOutput(second.key, second_output_key),
                first_output_key,
            )
        ],
        payload_mode="text",
        payload_text="first",
        encryption_enabled=False,
    )
    second.technique_inputs = LocomotiveInputsDraft(
        covers=[
            LocomotiveCoverDraft(
                StepOutput(first.key, first_output_key),
                second_output_key,
            )
        ],
        payload_mode="text",
        payload_text="second",
        encryption_enabled=False,
    )

    page.render_step_cards()
    assert page.step_dependency_error(0) == "Circular dependency detected."
    assert page.step_dependency_error(1) == "Circular dependency detected."
    assert page.step_cards[0].status == "blocked"
    assert page.step_cards[1].status == "blocked"
    _process_events(app)


def test_linked_locomotive_popup_save_reopens_inline_and_cancel_isolated(
    tmp_path,
) -> None:
    app = _app()
    first_cover = tmp_path / "first.png"
    second_cover = tmp_path / "second.png"
    manual_cover = tmp_path / "manual.png"
    manual_payload = tmp_path / "manual.bin"
    for path in (first_cover, second_cover, manual_cover, manual_payload):
        path.write_bytes(b"prototype")

    page = EmbedConfigurablePage()
    for technique in ("lsbpp", "lsbpp", "locomotive"):
        page.add_pipeline_step(technique)
    page.pipeline_steps[0].technique_inputs = _configured_lsb(
        first_cover,
        "first",
    )
    page.pipeline_steps[1].technique_inputs = _configured_lsb(
        second_cover,
        "second",
    )
    first_reference = StepOutput(page.pipeline_steps[0].key, "result")
    second_reference = StepOutput(page.pipeline_steps[1].key, "result")
    page.render_step_cards()

    def save_popup() -> None:
        dialog = page.active_step_dialog
        assert isinstance(dialog, StepConfigShellDialog)
        form = dialog.shell.content_widget
        assert isinstance(form, LocomotiveEmbedInputs)
        form.cover_mode_toggle.linked_button.click()
        QTest.mouseClick(
            form.cover_output_picker._rows[0],
            Qt.MouseButton.LeftButton,
        )
        form.payload_mode_toggle.linked_button.click()
        payload_row = next(
            row
            for row in form.payload_output_picker._rows
            if row.output_info.reference == second_reference
        )
        QTest.mouseClick(payload_row, Qt.MouseButton.LeftButton)
        form.encrypt_toggle_switch.setChecked(False)
        dialog.save_button.click()

    QTimer.singleShot(0, save_popup)
    page.open_step_config_popup(2)

    saved = page.pipeline_steps[2].technique_inputs
    assert isinstance(saved, LocomotiveInputsDraft)
    assert [cover.source for cover in saved.covers] == [first_reference]
    assert saved.payload_files == [second_reference]
    saved_output_keys = [cover.output_key for cover in saved.covers]
    assert page.step_cards[2].status == "ready"
    assert page.step_cards[2].summary_text("cover") == (
        "From STEP 1, Output 1"
    )
    assert page.step_cards[2].summary_text("payload") == "Files ×1 (at run)"

    page.set_config_variant("inline")
    page.open_step_config_inline(2)
    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    form = panel.shell.content_widget
    assert isinstance(form, LocomotiveEmbedInputs)
    assert form.cover_output_picker.selected_outputs() == [first_reference]
    assert form.payload_output_picker.selected_outputs() == [second_reference]

    form.cover_mode_toggle.manual_button.click()
    form.cover_drop_zone.add_files([str(manual_cover)])
    form.payload_mode_toggle.manual_button.click()
    form.payload_file_drop_zone.add_files([str(manual_payload)])
    panel.cancel_button.click()
    _process_events(app)

    unchanged = page.pipeline_steps[2].technique_inputs
    assert isinstance(unchanged, LocomotiveInputsDraft)
    assert [cover.source for cover in unchanged.covers] == [first_reference]
    assert [cover.output_key for cover in unchanged.covers] == saved_output_keys
    assert unchanged.payload_files == [second_reference]


def test_locomotive_cover_reorder_preserves_link_and_remove_blocks_consumer(
    tmp_path,
) -> None:
    app = _app()
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    third = tmp_path / "third.png"
    consumer_cover = tmp_path / "consumer.png"
    for path in (first, second, third, consumer_cover):
        path.write_bytes(b"png")

    page = EmbedConfigurablePage()
    page.add_pipeline_step("locomotive")
    page.add_pipeline_step("locomotive")
    producer = page.pipeline_steps[0]
    producer.technique_inputs = LocomotiveInputsDraft(
        covers=[
            LocomotiveCoverDraft(str(first), "output_a1111111"),
            LocomotiveCoverDraft(str(second), "output_b2222222"),
            LocomotiveCoverDraft(str(third), "output_c3333333"),
        ],
        payload_mode="text",
        payload_text="producer",
        encryption_enabled=False,
    )
    second_reference = StepOutput(producer.key, "output_b2222222")
    page.pipeline_steps[1].technique_inputs = LocomotiveInputsDraft(
        covers=[LocomotiveCoverDraft(str(consumer_cover))],
        payload_files=[second_reference],
        encryption_enabled=False,
    )
    page.render_step_cards()

    page.set_config_variant("inline")
    page.open_step_config_inline(0)
    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    form = panel.shell.content_widget
    assert isinstance(form, LocomotiveEmbedInputs)
    form.on_locomotive_file_selected(
        [str(second), str(third), str(first)]
    )
    panel.save_button.click()
    _process_events(app)

    reordered = page.pipeline_steps[0].technique_inputs
    assert isinstance(reordered, LocomotiveInputsDraft)
    assert [cover.output_key for cover in reordered.covers] == [
        "output_b2222222",
        "output_c3333333",
        "output_a1111111",
    ]
    assert page.step_cards[1].status == "ready"
    assert page.step_cards[1].summary_text("payload") == "Files ×1 (at run)"
    assert "From STEP 1, Output 1" in (
        page.step_cards[1].summary_tooltip("payload")
    )

    page.open_step_config_inline(0)
    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    form = panel.shell.content_widget
    assert isinstance(form, LocomotiveEmbedInputs)
    form.on_locomotive_file_selected([str(third), str(first)])
    panel.save_button.click()
    _process_events(app)

    assert page.pipeline_steps[1].technique_inputs.payload_files == [
        second_reference
    ]
    assert page.step_cards[1].status == "blocked"
    assert page.step_cards[1].status_label.toolTip() == (
        "Output is not available from Step 1."
    )

    blocked_form = page.create_step_technique_form(
        page.pipeline_steps[1],
        1,
    )
    assert isinstance(blocked_form, LocomotiveEmbedInputs)
    assert blocked_form.payload_output_picker.selected_outputs() == [
        second_reference
    ]
    blocked_form.show()
    _process_events(app)
    assert blocked_form.payload_output_picker.unavailable_frame.isVisible()
    assert "Output is not available from Step 1" in (
        blocked_form.payload_output_picker.unavailable_detail.text()
    )


def test_switching_linked_payload_to_manual_releases_single_consumer(
    tmp_path,
) -> None:
    app = _app()
    producer_cover = tmp_path / "producer.png"
    owner_cover = tmp_path / "owner.png"
    later_cover = tmp_path / "later.png"
    manual_payload = tmp_path / "manual.bin"
    for path in (producer_cover, owner_cover, later_cover, manual_payload):
        path.write_bytes(b"prototype")

    page = EmbedConfigurablePage()
    for technique in ("lsbpp", "locomotive", "locomotive"):
        page.add_pipeline_step(technique)
    producer = page.pipeline_steps[0]
    producer.technique_inputs = _configured_lsb(producer_cover, "payload")
    reference = StepOutput(producer.key, "result")
    page.pipeline_steps[1].technique_inputs = LocomotiveInputsDraft(
        covers=[LocomotiveCoverDraft(str(owner_cover))],
        payload_files=[reference],
        encryption_enabled=False,
    )
    page.pipeline_steps[2].technique_inputs = LocomotiveInputsDraft(
        covers=[LocomotiveCoverDraft(str(later_cover))],
        payload_mode="text",
        payload_text="later",
        encryption_enabled=False,
    )
    page.render_step_cards()

    before_release = page.create_step_technique_form(
        page.pipeline_steps[2],
        2,
    )
    assert isinstance(before_release, LocomotiveEmbedInputs)
    assert reference not in {
        item.reference
        for item in before_release.payload_output_picker.candidates()
    }

    page.set_config_variant("inline")
    page.open_step_config_inline(1)
    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    form = panel.shell.content_widget
    assert isinstance(form, LocomotiveEmbedInputs)
    form.payload_mode_toggle.manual_button.click()
    form.payload_file_drop_zone.add_files([str(manual_payload)])
    panel.save_button.click()
    _process_events(app)

    released = page.pipeline_steps[1].technique_inputs
    assert isinstance(released, LocomotiveInputsDraft)
    assert released.payload_files == [str(manual_payload)]
    assert page.step_output_consumer_indices(reference) == []
    assert page.step_cards[1].summary_text("payload") == "Files ×1 (9 B)"

    after_release = page.create_step_technique_form(
        page.pipeline_steps[2],
        2,
    )
    assert isinstance(after_release, LocomotiveEmbedInputs)
    assert reference in {
        item.reference
        for item in after_release.payload_output_picker.candidates()
    }
    _process_events(app)
