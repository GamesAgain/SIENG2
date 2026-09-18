"""Focused tests for the prototype LSB++ linked-cover workflow."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QImage
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QLabel

from config_prototype.core.configurable import StepOutput, StepOutputInfo
from config_prototype.gui.components.step_config_shell import (
    StepConfigShellDialog,
    StepConfigShellPanel,
)
from config_prototype.gui.components.step_output_picker import (
    StepOutputPicker,
)
from config_prototype.gui.components.technique_forms import (
    LSBEmbedInputs,
    LSBInputsDraft,
    MetadataInputsDraft,
    MP3MetadataDraft,
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


def _write_png(path: Path, color: str = "#38BDF8") -> None:
    image = QImage(320, 180, QImage.Format.Format_ARGB32)
    image.fill(QColor(color))
    assert image.save(str(path), "PNG")


def _linked_page(
    cover_path: Path,
) -> tuple[QApplication, EmbedConfigurablePage, StepOutput]:
    app = _app()
    page = EmbedConfigurablePage()
    page.resize(1100, 720)
    page.add_pipeline_step("lsbpp")
    page.add_pipeline_step("lsbpp")
    producer = page.pipeline_steps[0]
    producer.technique_inputs = LSBInputsDraft(
        cover=str(cover_path),
        payload_text="First layer",
        encryption_enabled=False,
    )
    reference = StepOutput(producer.key, "result")
    page.render_step_cards()
    page.show()
    _process_events(app)
    return app, page, reference


def _select_first_linked_output(form: LSBEmbedInputs) -> None:
    form.cover_mode_toggle.linked_button.click()
    assert form.cover_output_picker._rows
    QTest.mouseClick(
        form.cover_output_picker._rows[0],
        Qt.MouseButton.LeftButton,
    )


def test_step_output_picker_empty_and_selected_preview(tmp_path) -> None:
    app = _app()
    preview_path = tmp_path / "carrier-preview.png"
    _write_png(preview_path)
    reference = StepOutput("step_a12f3", "result")
    info = StepOutputInfo(
        reference=reference,
        step_number=1,
        technique="lsbpp",
        media_type="png",
        preview_path=str(preview_path),
    )

    picker = StepOutputPicker()
    picker.resize(560, 320)
    picker.show()
    _process_events(app)

    assert picker.candidates() == []
    assert picker.empty_label.isVisible()
    assert not picker.header.isVisible()

    picker.set_candidates([info])
    _process_events(app)
    signal = QSignalSpy(picker.selection_changed)
    QTest.mouseClick(picker._rows[0], Qt.MouseButton.LeftButton)
    _process_events(app)

    assert picker.selected_output() == reference
    assert len(signal) == 1
    assert picker.preview_frame.isVisible()
    assert picker.preview_image.pixmap() is not None
    assert not picker.preview_image.pixmap().isNull()
    assert picker.preview_caption.text() == (
        "Source preview: carrier-preview.png"
    )
    assert "step_a12f3" not in picker._rows[0].toolTip()
    assert "carrier-preview.png" in picker._rows[0].toolTip()
    picker._rows[0].setFocus()
    QTest.keyClick(picker._rows[0], Qt.Key.Key_Space)
    assert len(signal) == 2
    header_labels = picker.header.findChildren(QLabel, "stepOutputHeaderCell")
    assert all(
        label.alignment() & Qt.AlignmentFlag.AlignHCenter
        for label in header_labels
    )


def test_lsb_form_switches_manual_and_linked_source(tmp_path) -> None:
    app = _app()
    preview_path = tmp_path / "source.png"
    _write_png(preview_path)
    reference = StepOutput("step_b23f4", "result")
    form = LSBEmbedInputs(
        output_catalog=[
            StepOutputInfo(
                reference=reference,
                step_number=1,
                technique="lsbpp",
                media_type="png",
                preview_path=str(preview_path),
            )
        ]
    )
    form.show()
    _process_events(app)

    assert form.cover_mode_toggle.mode() == "manual"
    assert form.cover_source_stack.currentIndex() == 0

    _select_first_linked_output(form)
    form.payload_text_area.setPlainText("Second layer")
    form.encrypt_toggle_switch.setChecked(False)
    _process_events(app)

    assert form.cover_mode_toggle.mode() == "linked"
    assert form.cover_source_stack.currentIndex() == 1
    assert form.cover_source == reference
    assert form.validate_draft()
    assert form.export_draft().cover == reference
    assert "pipeline runs" in form.capacity_label.toolTip()


def test_lsb_linked_inline_save_reopen_cancel_and_summary(tmp_path) -> None:
    cover_path = tmp_path / "inline-source.png"
    _write_png(cover_path)
    app, page, reference = _linked_page(cover_path)
    page.set_config_variant("inline")
    page.open_step_config_inline(1)

    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    form = panel.shell.content_widget
    assert isinstance(form, LSBEmbedInputs)
    assert form.cover_output_picker.candidates()[0].preview_path == str(
        cover_path
    )

    _select_first_linked_output(form)
    form.payload_text_area.setPlainText("Linked inline payload")
    form.encrypt_toggle_switch.setChecked(False)
    panel.save_button.click()
    _process_events(app)

    saved = page.pipeline_steps[1].technique_inputs
    assert isinstance(saved, LSBInputsDraft)
    assert saved.cover == reference
    assert page.step_cards[1].summary_text("cover") == (
        "From STEP 1, Output 1"
    )
    assert page.step_cards[1].summary_tooltip("cover") == (
        "From STEP 1, Output 1\nSource: inline-source.png"
    )

    page.open_step_config_inline(1)
    reopened = page.active_step_panel
    assert isinstance(reopened, StepConfigShellPanel)
    reopened_form = reopened.shell.content_widget
    assert isinstance(reopened_form, LSBEmbedInputs)
    assert reopened_form.cover_mode_toggle.mode() == "linked"
    assert reopened_form.cover_output_picker.selected_output() == reference
    assert reopened_form.cover_output_picker.preview_frame.isVisible()

    reopened_form.cover_mode_toggle.manual_button.click()
    reopened_form.payload_text_area.setPlainText("Discard this")
    reopened.cancel_button.click()
    _process_events(app)

    assert page.pipeline_steps[1].technique_inputs == saved


def test_lsb_linked_popup_save(tmp_path) -> None:
    cover_path = tmp_path / "popup-source.png"
    _write_png(cover_path, "#A78BFA")
    app, page, reference = _linked_page(cover_path)

    def configure_and_save() -> None:
        dialog = page.active_step_dialog
        assert isinstance(dialog, StepConfigShellDialog)
        form = dialog.shell.content_widget
        assert isinstance(form, LSBEmbedInputs)
        _select_first_linked_output(form)
        form.payload_text_area.setPlainText("Linked popup payload")
        form.encrypt_toggle_switch.setChecked(False)
        dialog.save_button.click()

    QTimer.singleShot(0, configure_and_save)
    page.open_step_config_popup(1)

    saved = page.pipeline_steps[1].technique_inputs
    assert isinstance(saved, LSBInputsDraft)
    assert saved.cover == reference


def test_lsb_picker_filters_used_output_media_and_resolves_chained_preview(
    tmp_path,
) -> None:
    cover_path = tmp_path / "root-cover.png"
    _write_png(cover_path, "#F59E0F")
    app = _app()
    page = EmbedConfigurablePage()
    for technique in ("lsbpp", "lsbpp", "metadata", "metadata", "lsbpp"):
        page.add_pipeline_step(technique)

    first = page.pipeline_steps[0]
    second = page.pipeline_steps[1]
    first.technique_inputs = LSBInputsDraft(
        cover=str(cover_path),
        payload_text="Layer one",
        encryption_enabled=False,
    )
    second.technique_inputs = LSBInputsDraft(
        cover=StepOutput(first.key, "result"),
        payload_text="Layer two",
        encryption_enabled=False,
    )
    page.pipeline_steps[2].technique_inputs = MetadataInputsDraft(
        cover=str(cover_path),
        payload=MP3MetadataDraft(),
    )
    page.pipeline_steps[3].technique_inputs = MetadataInputsDraft(
        cover=str(cover_path),
        payload=PNGMetadataDraft(entries={"Comment": "Layer three"}),
    )

    form = page.create_step_technique_form(page.pipeline_steps[4], 4)
    assert isinstance(form, LSBEmbedInputs)
    candidates = form.cover_output_picker.candidates()

    assert [candidate.step_number for candidate in candidates] == [2, 4]
    assert all(candidate.media_type == "png" for candidate in candidates)
    assert all(candidate.preview_path == str(cover_path) for candidate in candidates)
    _process_events(app)
