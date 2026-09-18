"""Final GUI/Draft acceptance for the main configurable pipeline flow."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QPoint, QTimer
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtWidgets import QApplication

from config_prototype.core.configurable import StepOutput
from config_prototype.gui.components.step_config_shell import (
    StepConfigShellDialog,
    StepConfigShellPanel,
)
from config_prototype.gui.components.technique_forms import (
    LSBEmbedInputs,
    LSBInputsDraft,
    LocomotiveCoverDraft,
    LocomotiveInputsDraft,
    MetadataEmbedInputs,
    MetadataInputsDraft,
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
    for _ in range(5):
        app.processEvents()


def _write_png(path: Path, color: str) -> None:
    image = QImage(96, 64, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    assert image.save(str(path), "PNG")


def _main_flow(
    tmp_path,
) -> tuple[
    QApplication,
    EmbedConfigurablePage,
    StepOutput,
    StepOutput,
]:
    first_cover = tmp_path / "carrier-a.png"
    second_cover = tmp_path / "carrier-b.png"
    payload = tmp_path / "secret.pdf"
    _write_png(first_cover, "#38BDF8")
    _write_png(second_cover, "#A78BFA")
    payload.write_bytes(b"prototype secret pdf")

    app = _app()
    page = EmbedConfigurablePage()
    for technique in ("locomotive", "lsbpp", "metadata"):
        page.add_pipeline_step(technique)

    locomotive = page.pipeline_steps[0]
    first_key = "output_a4f91c2e"
    second_key = "output_12bd770a"
    locomotive.technique_inputs = LocomotiveInputsDraft(
        covers=[
            LocomotiveCoverDraft(str(first_cover), first_key),
            LocomotiveCoverDraft(str(second_cover), second_key),
        ],
        payload_mode="files",
        payload_files=[str(payload)],
        encryption_enabled=False,
    )
    first_output = StepOutput(locomotive.key, first_key)
    second_output = StepOutput(locomotive.key, second_key)
    page.pipeline_steps[1].technique_inputs = LSBInputsDraft(
        cover=first_output,
        payload_text="123",
        encryption_enabled=False,
    )
    page.pipeline_steps[2].technique_inputs = MetadataInputsDraft(
        cover=second_output,
        payload=PNGMetadataDraft(entries={"Comment": "456"}),
    )
    page.render_step_cards()
    _process_events(app)
    return app, page, first_output, second_output


def test_main_three_step_flow_saves_reopens_and_renders_both_shells(
    tmp_path,
) -> None:
    app, page, first_output, second_output = _main_flow(tmp_path)

    assert page.step_output_consumer_indices(first_output) == [1]
    assert page.step_output_consumer_indices(second_output) == [2]
    assert [page.step_dependency_error(index) for index in range(3)] == [
        None,
        None,
        None,
    ]
    assert [card.status for card in page.step_cards] == [
        "ready",
        "ready",
        "ready",
    ]
    assert page.step_cards[0].summary_text("cover") == "PNG ×2"
    assert page.step_cards[0].summary_text("output") == "PNG ×2"
    assert page.step_cards[1].summary_text("cover") == (
        "From STEP 1, Output 1"
    )
    assert page.step_cards[1].summary_text("payload") == "Text (3 B)"
    assert page.step_cards[2].summary_text("cover") == (
        "From STEP 1, Output 2"
    )
    assert page.step_cards[2].summary_text("payload") == "Text fields ×1"

    page.set_config_variant("inline")
    page.open_step_config_inline(1)
    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    lsb_form = panel.shell.content_widget
    assert isinstance(lsb_form, LSBEmbedInputs)
    assert lsb_form.cover_output_picker.selected_output() == first_output
    assert [
        output.reference for output in lsb_form.cover_output_picker.candidates()
    ] == [first_output]
    panel.save_button.click()
    _process_events(app)
    assert page.pipeline_steps[1].technique_inputs.cover == first_output

    page.open_step_config_inline(1)
    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    lsb_form = panel.shell.content_widget
    lsb_form.payload_text_area.setPlainText("discarded")
    panel.cancel_button.click()
    _process_events(app)
    assert page.pipeline_steps[1].technique_inputs.payload_text == "123"

    page.set_config_variant("popup")
    popup_errors: list[BaseException] = []
    popup_observations: dict[str, object] = {}
    lsb_result = StepOutput(page.pipeline_steps[1].key, "result")

    def inspect_and_save_metadata() -> None:
        try:
            dialog = page.active_step_dialog
            if not isinstance(dialog, StepConfigShellDialog):
                raise AssertionError("Metadata popup was not opened")
            form = dialog.shell.content_widget
            if not isinstance(form, MetadataEmbedInputs):
                raise AssertionError("Metadata form was not mounted")
            popup_observations["selected"] = (
                form.cover_output_picker.selected_output()
            )
            popup_observations["catalog"] = [
                output.reference for output in form.output_catalog
            ]
            popup_observations["comment"] = {
                row.get_keyword(): row.get_value()
                for row in form.png_form.custom_rows
            }
            dialog.save_button.click()
        except BaseException as error:
            popup_errors.append(error)
            if page.active_step_dialog is not None:
                page.active_step_dialog.reject()

    QTimer.singleShot(0, inspect_and_save_metadata)
    page.open_step_config_popup(2)
    _process_events(app)
    assert popup_errors == []
    assert popup_observations == {
        "selected": second_output,
        "catalog": [second_output, lsb_result],
        "comment": {"Comment": "456"},
    }
    assert page.pipeline_steps[2].technique_inputs.cover == second_output

    def inspect_and_cancel_metadata() -> None:
        try:
            dialog = page.active_step_dialog
            if not isinstance(dialog, StepConfigShellDialog):
                raise AssertionError("Metadata popup was not reopened")
            form = dialog.shell.content_widget
            if not isinstance(form, MetadataEmbedInputs):
                raise AssertionError("Metadata form was not mounted")
            form.png_form.custom_rows[0].value_input.setText("discarded")
            dialog.cancel_button.click()
        except BaseException as error:
            popup_errors.append(error)
            if page.active_step_dialog is not None:
                page.active_step_dialog.reject()

    QTimer.singleShot(0, inspect_and_cancel_metadata)
    page.open_step_config_popup(2)
    _process_events(app)
    assert popup_errors == []
    saved = page.pipeline_steps[2].technique_inputs
    assert saved.payload.entries == {"Comment": "456"}


def test_main_flow_delete_producer_preserves_both_broken_branches(
    tmp_path,
) -> None:
    _app_instance, page, first_output, second_output = _main_flow(tmp_path)
    lsb_key = page.pipeline_steps[1].key
    metadata_key = page.pipeline_steps[2].key

    page.remove_pipeline_step(0)

    assert [step.key for step in page.pipeline_steps] == [
        lsb_key,
        metadata_key,
    ]
    assert page.pipeline_steps[0].technique_inputs.cover == first_output
    assert page.pipeline_steps[1].technique_inputs.cover == second_output
    assert [card.step_number for card in page.step_cards] == [1, 2]
    assert [card.status for card in page.step_cards] == [
        "blocked",
        "blocked",
    ]
    assert all(
        card.status_label.toolTip() == "Source step no longer exists."
        for card in page.step_cards
    )


def test_delete_consumers_releases_outputs_and_clear_resets_pipeline(
    tmp_path,
) -> None:
    _app_instance, page, first_output, second_output = _main_flow(tmp_path)

    page.remove_pipeline_step(1)
    assert page.step_output_consumer_indices(first_output) == []
    assert page.step_output_consumer_indices(second_output) == [1]
    metadata_form = page.create_step_technique_form(
        page.pipeline_steps[1],
        1,
    )
    assert isinstance(metadata_form, MetadataEmbedInputs)
    assert [output.reference for output in metadata_form.output_catalog] == [
        first_output,
        second_output,
    ]

    page.remove_pipeline_step(1)
    assert page.step_output_consumer_indices(first_output) == []
    assert page.step_output_consumer_indices(second_output) == []
    assert len(page.pipeline_steps) == 1

    page.clear_pipeline()
    assert page.pipeline_steps == []
    assert page.step_cards == []
    assert page.flow_layout.count() == 0
    assert page.canvas_scroll.verticalScrollBar().maximum() == 0


def test_metadata_linked_picker_rows_are_not_clipped_by_cover_card(
    tmp_path,
) -> None:
    app, page, _first_output, _second_output = _main_flow(tmp_path)
    page.set_config_variant("inline")
    page.open_step_config_inline(2)
    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    panel.resize(1320, 780)
    panel.show()
    _process_events(app)

    form = panel.shell.content_widget
    assert isinstance(form, MetadataEmbedInputs)
    picker = form.cover_output_picker
    assert len(picker._rows) == 2
    content_top = form.content_stack.mapTo(form, QPoint(0, 0)).y()
    row_bottoms = [
        row.mapTo(form, QPoint(0, row.height())).y()
        for row in picker._rows
    ]

    assert max(row_bottoms) <= content_top
