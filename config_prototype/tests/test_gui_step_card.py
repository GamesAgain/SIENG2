"""Focused GUI tests for the prototype StepCard collection."""

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPoint, QPointF, QSize, Qt, QTimer
from PyQt6.QtGui import QEnterEvent
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox, QPushButton, QWidget

from config_prototype.gui.components.step_card import (
    CARD_HEIGHT,
    CARD_WIDTH,
    CLOSE_BUTTON_SIZE,
    StepCard,
)
from config_prototype.gui.components.step_config_shell import (
    STEP_CONFIG_MIN_HEIGHT,
    STEP_CONFIG_MIN_WIDTH,
    StepConfigShellDialog,
    StepConfigShellPanel,
)
from config_prototype.gui.components.technique_forms import (
    LSBEmbedInputs,
    LSBInputsDraft,
    LocomotiveEmbedInputs,
    LocomotiveInputsDraft,
)
from config_prototype.gui.components.technique_forms import lsb_embed_inputs
from config_prototype.gui.pages.sub_pages.embed.configurable_page import (
    CANVAS_MARGIN,
    EmbedConfigurablePage,
    MAX_VISIBLE_FLOW_HEIGHT,
    PipelineStepDraft,
)
from config_prototype.main import PrototypeWindow
from src.core.crypto.key_management import (
    generate_and_save_keypair,
    inspect_public_key_file,
)
from src.gui.components.key_validation import KeyValidationResult
from src.gui.services.key_registry import KeyRegistry


def _app() -> QApplication:
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(
        Path("src/gui/styles/default.qss").read_text(encoding="utf-8")
    )
    return app


def _process_events(app: QApplication) -> None:
    for _ in range(4):
        app.processEvents()


def _page(
    key_registry: KeyRegistry | None = None,
) -> tuple[QApplication, EmbedConfigurablePage]:
    app = _app()
    page = EmbedConfigurablePage(key_registry=key_registry)
    page.resize(1100, 720)
    page.show()
    _process_events(app)
    return app, page


def _add_steps(
    page: EmbedConfigurablePage,
    app: QApplication,
    techniques: list[str],
) -> None:
    for technique in techniques:
        page.add_pipeline_step(technique)
    _process_events(app)


def _arrow_count(page: EmbedConfigurablePage) -> int:
    return page.flow_layout.count() - len(page.step_cards)


def _step_numbers(page: EmbedConfigurablePage) -> list[str]:
    numbers = []
    for card in page.step_cards:
        label = card.findChild(QLabel, "prototypeStepCardNumber")
        numbers.append(label.text())
    return numbers


def _techniques(page: EmbedConfigurablePage) -> list[str]:
    return [step.technique for step in page.pipeline_steps]


def test_pipeline_step_drafts_have_unique_stable_keys_and_defaults() -> None:
    app, page = _page()
    _add_steps(page, app, ["lsbpp", "locomotive", "metadata"])

    assert all(isinstance(step, PipelineStepDraft) for step in page.pipeline_steps)
    assert [step.key for step in page.pipeline_steps] == [
        "prototype_step_1",
        "prototype_step_2",
        "prototype_step_3",
    ]
    assert [step.description for step in page.pipeline_steps] == [
        "Embed text in PNG",
        "Embed files in PNG",
        "Hide data in PNG or MP3 metadata",
    ]
    assert all(step.guidenote == "" for step in page.pipeline_steps)
    assert all(step.technique_inputs is None for step in page.pipeline_steps)

    locomotive = page.pipeline_steps[1]
    locomotive.description = "Hide contract across three covers"
    locomotive.guidenote = "Attach every carrier before extraction"
    page.remove_pipeline_step(0)

    assert page.pipeline_steps[0] is locomotive
    assert locomotive.key == "prototype_step_2"
    assert locomotive.description == "Hide contract across three covers"
    assert locomotive.guidenote == "Attach every carrier before extraction"
    assert page.step_cards[0].description == locomotive.description

    page.clear_pipeline()
    page.add_pipeline_step("lsbpp")
    assert page.pipeline_steps[0].key == "prototype_step_4"


def test_step_card_overlay_geometry_hover_and_header_fonts() -> None:
    app = _app()
    card = StepCard(1, "lsbpp")
    assert card.close_button.isHidden()
    card.show()
    _process_events(app)

    assert card.size() == QSize(CARD_WIDTH, CARD_HEIGHT)
    assert card.close_button.size() == QSize(
        CLOSE_BUTTON_SIZE,
        CLOSE_BUTTON_SIZE,
    )
    assert card.rect().contains(card.close_button.geometry())
    QApplication.sendEvent(card, QEvent(QEvent.Type.Leave))
    assert not card.close_button.isVisible()

    enter = QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1))
    QApplication.sendEvent(card, enter)
    assert card.close_button.isVisible()

    status_top_left = card.status_label.mapTo(card, QPoint(0, 0))
    status_rect = card.status_label.rect().translated(status_top_left)
    assert not status_rect.intersects(card.close_button.geometry())

    QApplication.sendEvent(card, QEvent(QEvent.Type.Leave))
    assert not card.close_button.isVisible()

    step_label = card.findChild(QLabel, "prototypeStepCardNumber")
    title_label = card.findChild(QLabel, "prototypeStepCardTitle")
    assert step_label.font().pixelSize() == 11
    assert title_label.font().pixelSize() == 14
    assert card.status_label.font().pixelSize() == 9
    assert card.status_label.height() >= card.status_label.sizeHint().height()


def test_step_card_click_emits_clicked_but_delete_does_not() -> None:
    app = _app()
    card = StepCard(1, "lsbpp")
    card.show()
    _process_events(app)
    clicked_spy = QSignalSpy(card.clicked)
    remove_spy = QSignalSpy(card.remove_requested)

    QApplication.sendEvent(card, QEvent(QEvent.Type.Leave))
    QTest.mouseClick(
        card.card,
        Qt.MouseButton.LeftButton,
        pos=QPoint(CARD_WIDTH // 2, CARD_HEIGHT // 2),
    )
    assert len(clicked_spy) == 1
    assert len(remove_spy) == 0

    QApplication.sendEvent(
        card,
        QEnterEvent(QPointF(1, 1), QPointF(1, 1), QPointF(1, 1)),
    )
    QTest.mouseClick(card.close_button, Qt.MouseButton.LeftButton)
    assert len(clicked_spy) == 1
    assert len(remove_spy) == 1


def test_card_click_opens_popup_and_cancel_resets_active_step(capsys) -> None:
    app, page = _page()
    _add_steps(page, app, ["lsbpp", "locomotive", "metadata"])
    page.pipeline_steps[1].description = "Hide contract across three covers"
    page.pipeline_steps[1].guidenote = "Attach every carrier before extraction"
    observed = {}

    def inspect_and_close_dialog() -> None:
        dialog = page.active_step_dialog
        assert isinstance(dialog, StepConfigShellDialog)
        observed["active_step_index"] = page.active_step_index
        observed["active_step_key"] = page.active_step_key
        observed["step_number"] = dialog.step_number
        observed["technique"] = dialog.technique_label_text
        observed["description"] = dialog.shell.description()
        observed["guidenote"] = dialog.shell.guidenote()
        dialog.cancel_button.click()

    QTimer.singleShot(0, inspect_and_close_dialog)
    QTest.mouseClick(
        page.step_cards[1].card,
        Qt.MouseButton.LeftButton,
        pos=QPoint(CARD_WIDTH // 2, CARD_HEIGHT // 2),
    )

    assert observed == {
        "active_step_index": 1,
        "active_step_key": "prototype_step_2",
        "step_number": 2,
        "technique": "Locomotive",
        "description": "Hide contract across three covers",
        "guidenote": "Attach every carrier before extraction",
    }
    assert page.active_step_index is None
    assert page.active_step_key is None
    assert page.active_step_dialog is None
    assert capsys.readouterr().out == "Step 2 clicked: technique=locomotive\n"


def test_delete_active_step_closes_popup_and_renders_remaining_steps() -> None:
    app, page = _page()
    _add_steps(page, app, ["lsbpp", "locomotive", "metadata"])

    def delete_active_step() -> None:
        assert page.active_step_index == 1
        assert isinstance(page.active_step_dialog, StepConfigShellDialog)
        page.remove_pipeline_step(1)

    QTimer.singleShot(0, delete_active_step)
    QTest.mouseClick(
        page.step_cards[1].card,
        Qt.MouseButton.LeftButton,
        pos=QPoint(CARD_WIDTH // 2, CARD_HEIGHT // 2),
    )
    _process_events(app)

    assert page.active_step_index is None
    assert page.active_step_dialog is None
    assert _techniques(page) == ["lsbpp", "metadata"]
    assert _step_numbers(page) == ["STEP 1", "STEP 2"]
    assert _arrow_count(page) == 1


def test_clear_with_active_step_closes_popup_and_restores_empty_state() -> None:
    app, page = _page()
    initial_canvas_height = page.pipeline_canvas.height()
    _add_steps(page, app, ["lsbpp", "locomotive", "metadata"])

    def clear_active_pipeline() -> None:
        assert page.active_step_index == 0
        assert isinstance(page.active_step_dialog, StepConfigShellDialog)
        page.clear_pipeline()

    QTimer.singleShot(0, clear_active_pipeline)
    QTest.mouseClick(
        page.step_cards[0].card,
        Qt.MouseButton.LeftButton,
        pos=QPoint(CARD_WIDTH // 2, CARD_HEIGHT // 2),
    )
    _process_events(app)

    assert page.active_step_index is None
    assert page.active_step_dialog is None
    assert page.pipeline_steps == []
    assert len(page.step_cards) == 0
    assert _arrow_count(page) == 0
    assert page.pipeline_canvas.height() == initial_canvas_height
    assert page.canvas_scroll.verticalScrollBar().maximum() == 0


def test_inline_variant_reuses_shell_and_cancel_resets_active_step() -> None:
    app, page = _page()
    _add_steps(page, app, ["lsbpp", "locomotive", "metadata"])

    page.btn_inline.click()
    QTest.mouseClick(
        page.step_cards[2].card,
        Qt.MouseButton.LeftButton,
        pos=QPoint(CARD_WIDTH // 2, CARD_HEIGHT // 2),
    )
    _process_events(app)

    panel = page.active_step_panel
    assert page.config_variant == "inline"
    assert page.active_step_index == 2
    assert page.active_step_key == "prototype_step_3"
    assert page.active_step_dialog is None
    assert isinstance(panel, StepConfigShellPanel)
    assert panel.step_number == 3
    assert panel.technique_label_text == "Metadata"
    assert panel.shell.description() == "Hide data in PNG or MP3 metadata"
    assert panel.shell.guidenote() == ""
    assert panel.shell.placeholder_label is not None
    assert panel.shell.placeholder_label.text() == (
        "Technique configuration form will appear here."
    )
    assert page.inline_slot.count() == 1

    panel.cancel_button.click()
    _process_events(app)

    assert page.active_step_index is None
    assert page.active_step_key is None
    assert page.active_step_panel is None
    assert page.inline_slot.count() == 0


def test_step_config_shell_exposes_description_and_guidenote() -> None:
    app = _app()
    panel = StepConfigShellPanel(
        step_number=1,
        technique_label="LSB++",
        description="Embed text in PNG",
        guidenote="Use the supplied carrier",
        accent="blue",
    )
    panel.show()
    _process_events(app)

    assert panel.shell.description() == "Embed text in PNG"
    assert panel.shell.guidenote() == "Use the supplied carrier"
    assert panel.shell.technique_label.property("accentColor") == "blue"

    panel.shell.description_edit.selectAll()
    QTest.keyClicks(panel.shell.description_edit, "Hide project note in cover")
    assert panel.shell.description() == "Hide project note in cover"


def test_step_config_shell_accepts_future_technique_content_widget() -> None:
    app = _app()
    content = QWidget()
    content.setObjectName("testTechniqueForm")
    dialog = StepConfigShellDialog(
        step_number=2,
        technique_label="Locomotive",
        description="Embed files in PNG",
        accent="purple",
        content_widget=content,
    )
    dialog.show()
    _process_events(app)

    assert dialog.shell.content_widget is content
    assert dialog.shell.placeholder_label is None
    assert content.parent() is dialog.shell.content_frame
    assert dialog.minimumWidth() == STEP_CONFIG_MIN_WIDTH
    assert dialog.minimumHeight() == STEP_CONFIG_MIN_HEIGHT


def test_inline_step_config_uses_dialog_height_without_fixed_width() -> None:
    app = _app()
    panel = StepConfigShellPanel(
        step_number=1,
        technique_label="LSB++",
        description="Embed text in PNG",
        accent="blue",
    )
    panel.show()
    _process_events(app)

    assert panel.minimumWidth() < STEP_CONFIG_MIN_WIDTH
    assert panel.minimumHeight() == STEP_CONFIG_MIN_HEIGHT


def test_lsbpp_popup_uses_real_technique_form() -> None:
    app, page = _page()
    _add_steps(page, app, ["lsbpp"])
    observed = {}

    def inspect_and_close_dialog() -> None:
        dialog = page.active_step_dialog
        assert isinstance(dialog, StepConfigShellDialog)
        observed["content"] = dialog.shell.content_widget
        observed["placeholder"] = dialog.shell.placeholder_label
        dialog.cancel_button.click()

    QTimer.singleShot(0, inspect_and_close_dialog)
    page.open_step_config_popup(0)

    assert isinstance(observed["content"], LSBEmbedInputs)
    assert observed["placeholder"] is None


def test_prototype_window_injects_key_registry_into_page(tmp_path) -> None:
    app = _app()
    registry = KeyRegistry(tmp_path / "keys.json")
    window = PrototypeWindow(key_registry=registry)

    assert window.key_registry is registry
    assert window.page.key_registry is registry

    window.close()
    _process_events(app)


def test_lsb_form_receives_page_key_registry(tmp_path) -> None:
    registry = KeyRegistry(tmp_path / "keys.json")
    app, page = _page(key_registry=registry)
    _add_steps(page, app, ["lsbpp"])
    page.set_config_variant("inline")
    page.open_step_config_inline(0)

    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    form = panel.shell.content_widget
    assert isinstance(form, LSBEmbedInputs)
    assert form.key_registry is registry
    assert form.public_key_source.registry is registry
    assert form.public_key_source.choose_button.isEnabled()

    page.close_active_step_config()
    _process_events(app)


def test_inline_technique_forms_keep_metadata_placeholder() -> None:
    app, page = _page()
    _add_steps(page, app, ["lsbpp", "locomotive", "metadata"])
    page.set_config_variant("inline")

    page.open_step_config_inline(0)
    lsb_panel = page.active_step_panel
    assert isinstance(lsb_panel, StepConfigShellPanel)
    assert isinstance(lsb_panel.shell.content_widget, LSBEmbedInputs)
    assert lsb_panel.shell.placeholder_label is None
    assert lsb_panel.shell.content_widget.cover_drop_zone.parent() is not None
    page.close_active_step_config()

    page.open_step_config_inline(1)
    locomotive_panel = page.active_step_panel
    assert isinstance(locomotive_panel, StepConfigShellPanel)
    assert isinstance(
        locomotive_panel.shell.content_widget,
        LocomotiveEmbedInputs,
    )
    assert locomotive_panel.shell.placeholder_label is None
    page.close_active_step_config()

    page.open_step_config_inline(2)
    placeholder_panel = page.active_step_panel
    assert isinstance(placeholder_panel, StepConfigShellPanel)
    assert placeholder_panel.shell.content_widget is None
    assert placeholder_panel.shell.placeholder_label is not None
    assert placeholder_panel.shell.placeholder_label.text() == (
        "Technique configuration form will appear here."
    )
    page.close_active_step_config()


def test_popup_save_persists_draft_and_rerenders_step_card() -> None:
    app, page = _page()
    _add_steps(page, app, ["metadata"])

    def edit_and_save() -> None:
        dialog = page.active_step_dialog
        assert isinstance(dialog, StepConfigShellDialog)
        dialog.shell.description_edit.setText("Hide the release note")
        dialog.shell.guidenote_edit.setText("  Extract this step last  ")
        dialog.save_button.click()

    QTimer.singleShot(0, edit_and_save)
    page.open_step_config_popup(0)
    _process_events(app)

    step = page.pipeline_steps[0]
    assert step.description == "Hide the release note"
    assert step.guidenote == "Extract this step last"
    assert page.step_cards[0].description == "Hide the release note"
    assert page.active_step_index is None
    assert page.active_step_key is None
    assert page.active_step_dialog is None


def test_popup_cancel_discards_edited_draft() -> None:
    app, page = _page()
    _add_steps(page, app, ["metadata"])
    original = page.pipeline_steps[0]

    def edit_and_cancel() -> None:
        dialog = page.active_step_dialog
        assert isinstance(dialog, StepConfigShellDialog)
        dialog.shell.description_edit.setText("Do not persist this")
        dialog.shell.guidenote_edit.setText("Discard this note")
        dialog.cancel_button.click()

    QTimer.singleShot(0, edit_and_cancel)
    page.open_step_config_popup(0)

    assert original.description == "Hide data in PNG or MP3 metadata"
    assert original.guidenote == ""


def test_inline_save_persists_and_cancel_discards_edits() -> None:
    app, page = _page()
    _add_steps(page, app, ["metadata"])
    page.set_config_variant("inline")
    page.open_step_config_inline(0)

    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    panel.shell.description_edit.setText("Bundle three payload files")
    panel.shell.guidenote_edit.setText("Provide all carrier images")
    panel.save_button.click()
    _process_events(app)

    step = page.pipeline_steps[0]
    assert step.description == "Bundle three payload files"
    assert step.guidenote == "Provide all carrier images"
    assert page.step_cards[0].description == "Bundle three payload files"
    assert page.active_step_panel is None

    page.open_step_config_inline(0)
    reopened = page.active_step_panel
    assert isinstance(reopened, StepConfigShellPanel)
    assert reopened.shell.description() == "Bundle three payload files"
    assert reopened.shell.guidenote() == "Provide all carrier images"
    reopened.shell.description_edit.setText("Discarded edit")
    reopened.cancel_button.click()
    _process_events(app)

    assert step.description == "Bundle three payload files"
    assert step.guidenote == "Provide all carrier images"


def test_saved_values_reopen_across_popup_and_inline_variants() -> None:
    app, page = _page()
    _add_steps(page, app, ["metadata"])

    def save_popup() -> None:
        dialog = page.active_step_dialog
        assert isinstance(dialog, StepConfigShellDialog)
        dialog.shell.description_edit.setText("Persist between shell variants")
        dialog.shell.guidenote_edit.setText("Receiver hint")
        dialog.save_button.click()

    QTimer.singleShot(0, save_popup)
    page.open_step_config_popup(0)
    page.set_config_variant("inline")
    page.open_step_config_inline(0)

    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    assert panel.shell.description() == "Persist between shell variants"
    assert panel.shell.guidenote() == "Receiver hint"
    panel.cancel_button.click()
    _process_events(app)


def _configure_valid_lsb_form(
    form: LSBEmbedInputs,
    cover_path: Path,
    *,
    payload: str = "Project Phoenix launch code",
    password: str = "correct horse battery staple",
) -> None:
    form.cover_file_path = str(cover_path)
    form.payload_text_area.setPlainText(payload)
    form.encrypt_toggle_switch.setChecked(True)
    form.btn_symmetric.setChecked(True)
    form.encrypt_stack.setCurrentIndex(0)
    form.password_input.setText(password)
    form.confirm_input.setText(password)


def test_lsb_inline_save_persists_inputs_and_updates_step_card(tmp_path) -> None:
    cover_path = tmp_path / "carrier.png"
    cover_path.write_bytes(b"prototype cover")
    app, page = _page()
    _add_steps(page, app, ["lsbpp"])
    page.set_config_variant("inline")
    page.open_step_config_inline(0)

    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    form = panel.shell.content_widget
    assert isinstance(form, LSBEmbedInputs)
    _configure_valid_lsb_form(form, cover_path)
    panel.save_button.click()
    _process_events(app)

    draft = page.pipeline_steps[0].technique_inputs
    assert isinstance(draft, LSBInputsDraft)
    assert draft.cover_path == str(cover_path)
    assert draft.payload_text == "Project Phoenix launch code"
    assert draft.encryption_enabled is True
    assert draft.encryption_mode == "password"
    assert draft.password == "correct horse battery staple"
    assert draft.public_key_path is None

    card = page.step_cards[0]
    assert card.status == "ready"
    assert card.summary_text("cover") == "carrier.png"
    assert card.summary_text("payload") == "Text (27 B)"
    assert card.summary_text("output") == "PNG ×1"
    assert card.summary_text("encryption") == "Password"
    assert page.active_step_panel is None


def test_lsb_popup_save_persists_inputs_and_updates_step_card(tmp_path) -> None:
    cover_path = tmp_path / "popup-carrier.png"
    cover_path.write_bytes(b"prototype cover")
    app, page = _page()
    _add_steps(page, app, ["lsbpp"])

    def configure_and_save_popup() -> None:
        dialog = page.active_step_dialog
        assert isinstance(dialog, StepConfigShellDialog)
        form = dialog.shell.content_widget
        assert isinstance(form, LSBEmbedInputs)
        _configure_valid_lsb_form(
            form,
            cover_path,
            payload="Popup payload",
            password="popup passphrase",
        )
        dialog.shell.description_edit.setText("Save LSB through popup")
        dialog.shell.guidenote_edit.setText("Popup receiver hint")
        dialog.save_button.click()

    QTimer.singleShot(0, configure_and_save_popup)
    page.open_step_config_popup(0)

    draft = page.pipeline_steps[0].technique_inputs
    assert isinstance(draft, LSBInputsDraft)
    assert draft.cover_path == str(cover_path)
    assert draft.payload_text == "Popup payload"
    assert draft.encryption_mode == "password"
    assert draft.password == "popup passphrase"
    assert page.pipeline_steps[0].description == "Save LSB through popup"
    assert page.pipeline_steps[0].guidenote == "Popup receiver hint"
    assert page.step_cards[0].status == "ready"
    assert page.step_cards[0].summary_text("encryption") == "Password"
    assert page.active_step_dialog is None


def test_lsb_no_encryption_save_reopens_without_secrets(tmp_path) -> None:
    cover_path = tmp_path / "plain-carrier.png"
    cover_path.write_bytes(b"prototype cover")
    app, page = _page()
    _add_steps(page, app, ["lsbpp"])
    page.set_config_variant("inline")
    page.open_step_config_inline(0)

    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    form = panel.shell.content_widget
    assert isinstance(form, LSBEmbedInputs)
    form.cover_file_path = str(cover_path)
    form.payload_text_area.setPlainText("Plain payload")
    form.password_input.setText("must not persist")
    form.confirm_input.setText("must not persist")
    form.encrypt_toggle_switch.setChecked(False)
    panel.save_button.click()
    _process_events(app)

    draft = page.pipeline_steps[0].technique_inputs
    assert isinstance(draft, LSBInputsDraft)
    assert draft.encryption_enabled is False
    assert draft.password == ""
    assert draft.public_key_path is None
    assert page.step_cards[0].status == "ready"
    assert page.step_cards[0].summary_text("encryption") == "None"

    page.open_step_config_inline(0)
    reopened_panel = page.active_step_panel
    assert isinstance(reopened_panel, StepConfigShellPanel)
    reopened_form = reopened_panel.shell.content_widget
    assert isinstance(reopened_form, LSBEmbedInputs)
    assert reopened_form.encrypt_toggle_switch.isChecked() is False
    assert reopened_form.password_input.text() == ""
    assert reopened_form.confirm_input.text() == ""
    assert reopened_form.public_key_path is None
    reopened_panel.cancel_button.click()
    _process_events(app)


def test_lsb_public_key_save_reopens_valid_registry_key(tmp_path) -> None:
    cover_path = tmp_path / "public-key-carrier.png"
    cover_path.write_bytes(b"prototype cover")
    _private_path, public_path = generate_and_save_keypair(
        tmp_path,
        "lsb_public_key_roundtrip",
        key_size=2048,
    )
    registry = KeyRegistry(tmp_path / "keys.json")
    public_record = registry.add(
        "LSB receiver public key",
        inspect_public_key_file(public_path),
    )
    app, page = _page(key_registry=registry)
    _add_steps(page, app, ["lsbpp"])
    page.set_config_variant("inline")
    page.open_step_config_inline(0)

    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    form = panel.shell.content_widget
    assert isinstance(form, LSBEmbedInputs)
    form.cover_file_path = str(cover_path)
    form.payload_text_area.setPlainText("Public key payload")
    form.btn_asymmetric.setChecked(True)
    form.encrypt_stack.setCurrentIndex(1)
    form.public_key_source.select_path(public_record.path)
    panel.save_button.click()
    _process_events(app)

    draft = page.pipeline_steps[0].technique_inputs
    assert isinstance(draft, LSBInputsDraft)
    assert draft.encryption_enabled is True
    assert draft.encryption_mode == "public_key"
    assert draft.password == ""
    assert draft.public_key_path == public_record.path
    assert page.step_cards[0].status == "ready"
    assert page.step_cards[0].summary_text("encryption") == "Public Key"

    page.open_step_config_inline(0)
    reopened_panel = page.active_step_panel
    assert isinstance(reopened_panel, StepConfigShellPanel)
    reopened_form = reopened_panel.shell.content_widget
    assert isinstance(reopened_form, LSBEmbedInputs)
    assert reopened_form.key_registry is registry
    assert reopened_form.btn_asymmetric.isChecked()
    symmetric_mode = reopened_form.findChild(QWidget, "symmetricMode")
    asymmetric_mode = reopened_form.findChild(QWidget, "asymmetricMode")
    assert symmetric_mode is not None and not symmetric_mode.isVisible()
    assert asymmetric_mode is not None and asymmetric_mode.isVisible()
    assert reopened_form.public_key_path == public_record.path
    assert reopened_form.public_key_drop_zone.selected_files == [
        public_record.path
    ]
    assert reopened_form.password_input.text() == ""
    reopened_panel.cancel_button.click()
    _process_events(app)


def test_lsb_saved_inputs_reopen_and_cancel_does_not_mutate_draft(
    tmp_path,
) -> None:
    cover_path = tmp_path / "saved-cover.png"
    cover_path.write_bytes(b"prototype cover")
    app, page = _page()
    _add_steps(page, app, ["lsbpp"])
    page.set_config_variant("inline")
    page.open_step_config_inline(0)

    first_panel = page.active_step_panel
    assert isinstance(first_panel, StepConfigShellPanel)
    first_form = first_panel.shell.content_widget
    assert isinstance(first_form, LSBEmbedInputs)
    _configure_valid_lsb_form(first_form, cover_path, payload="Saved payload")
    first_panel.save_button.click()
    _process_events(app)

    saved_draft = page.pipeline_steps[0].technique_inputs
    assert isinstance(saved_draft, LSBInputsDraft)

    page.open_step_config_inline(0)
    reopened_panel = page.active_step_panel
    assert isinstance(reopened_panel, StepConfigShellPanel)
    reopened_form = reopened_panel.shell.content_widget
    assert isinstance(reopened_form, LSBEmbedInputs)
    assert reopened_form.cover_file_path == str(cover_path)
    assert reopened_form.payload_text_area.toPlainText() == "Saved payload"
    assert reopened_form.password_input.text() == saved_draft.password

    reopened_form.payload_text_area.setPlainText("Discarded payload")
    reopened_form.password_input.setText("discarded password")
    reopened_panel.cancel_button.click()
    _process_events(app)

    assert page.pipeline_steps[0].technique_inputs == saved_draft
    assert page.step_cards[0].summary_text("payload") == "Text (13 B)"


def _configure_valid_locomotive_file_form(
    form: LocomotiveEmbedInputs,
    cover_paths: list[Path],
    payload_paths: list[Path],
    *,
    password: str = "locomotive passphrase",
) -> None:
    form.cover_drop_zone.add_files([str(path) for path in cover_paths])
    form.payload_tabs.setCurrentIndex(0)
    form.payload_file_drop_zone.add_files(
        [str(path) for path in payload_paths]
    )
    form.encrypt_toggle_switch.setChecked(True)
    form.btn_symmetric.setChecked(True)
    form.encrypt_stack.setCurrentIndex(0)
    form.password_input.setText(password)
    form.confirm_input.setText(password)


def test_locomotive_inline_save_reopens_and_updates_step_card(tmp_path) -> None:
    cover_paths = [tmp_path / "cover-1.png", tmp_path / "cover-2.png"]
    for cover_path in cover_paths:
        cover_path.write_bytes(b"prototype cover")
    payload_paths = [tmp_path / "one.bin", tmp_path / "two.txt"]
    payload_paths[0].write_bytes(b"a" * 1024)
    payload_paths[1].write_bytes(b"b" * 512)

    app, page = _page()
    _add_steps(page, app, ["locomotive"])
    assert page.step_cards[0].status == "setup"

    page.set_config_variant("inline")
    page.open_step_config_inline(0)
    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    form = panel.shell.content_widget
    assert isinstance(form, LocomotiveEmbedInputs)
    _configure_valid_locomotive_file_form(form, cover_paths, payload_paths)
    panel.shell.description_edit.setText("Bundle two files across two covers")
    panel.shell.guidenote_edit.setText("Attach both PNG carriers")
    panel.save_button.click()
    _process_events(app)

    draft = page.pipeline_steps[0].technique_inputs
    assert isinstance(draft, LocomotiveInputsDraft)
    assert draft.cover_paths == [str(path) for path in cover_paths]
    assert draft.payload_mode == "files"
    assert draft.payload_paths == [str(path) for path in payload_paths]
    assert draft.payload_text == ""
    assert draft.encryption_mode == "password"
    assert draft.password == "locomotive passphrase"
    assert draft.public_key_path is None

    card = page.step_cards[0]
    assert card.status == "ready"
    assert card.summary_text("cover") == "PNG ×2"
    assert card.summary_text("payload") == "Files ×2 (1.50 KB)"
    assert card.summary_text("output") == "PNG ×2"
    assert card.summary_text("encryption") == "Password"
    assert card.summary_tooltip("cover") == (
        "Cover PNGs (2):\n"
        "1. cover-1.png\n"
        "2. cover-2.png"
    )
    assert card.summary_tooltip("payload") == (
        "Payload files (2):\n"
        "1. one.bin — 1.00 KB\n"
        "2. two.txt — 512 B\n"
        "Total: 1.50 KB"
    )

    saved_draft = draft
    page.open_step_config_inline(0)
    reopened_panel = page.active_step_panel
    assert isinstance(reopened_panel, StepConfigShellPanel)
    reopened_form = reopened_panel.shell.content_widget
    assert isinstance(reopened_form, LocomotiveEmbedInputs)
    assert reopened_form.cover_drop_zone.selected_files == [
        str(path) for path in cover_paths
    ]
    assert reopened_form.payload_file_drop_zone.selected_files == [
        str(path) for path in payload_paths
    ]
    assert reopened_form.password_input.text() == "locomotive passphrase"

    reopened_form.payload_file_drop_zone.clear_all()
    reopened_form.payload_tabs.setCurrentIndex(1)
    reopened_form.payload_text_area.setPlainText("Discarded text")
    reopened_panel.cancel_button.click()
    _process_events(app)

    assert page.pipeline_steps[0].technique_inputs == saved_draft
    assert page.step_cards[0].summary_text("payload") == (
        "Files ×2 (1.50 KB)"
    )


def test_locomotive_popup_text_no_encryption_persists_across_shells(
    tmp_path,
) -> None:
    cover_path = tmp_path / "single-cover.png"
    cover_path.write_bytes(b"prototype cover")
    app, page = _page()
    _add_steps(page, app, ["locomotive"])

    def configure_and_save_popup() -> None:
        dialog = page.active_step_dialog
        assert isinstance(dialog, StepConfigShellDialog)
        form = dialog.shell.content_widget
        assert isinstance(form, LocomotiveEmbedInputs)
        form.cover_drop_zone.add_files([str(cover_path)])
        form.payload_tabs.setCurrentIndex(1)
        form.payload_text_area.setPlainText("Secret timetable")
        form.password_input.setText("must not persist")
        form.confirm_input.setText("must not persist")
        form.encrypt_toggle_switch.setChecked(False)
        dialog.shell.description_edit.setText("Hide a timetable in one PNG")
        dialog.save_button.click()

    QTimer.singleShot(0, configure_and_save_popup)
    page.open_step_config_popup(0)

    draft = page.pipeline_steps[0].technique_inputs
    assert isinstance(draft, LocomotiveInputsDraft)
    assert draft.cover_paths == [str(cover_path)]
    assert draft.payload_mode == "text"
    assert draft.payload_paths == []
    assert draft.payload_text == "Secret timetable"
    assert draft.encryption_enabled is False
    assert draft.password == ""
    assert draft.public_key_path is None

    card = page.step_cards[0]
    assert card.status == "ready"
    assert card.summary_text("cover") == "single-cover.png"
    assert card.summary_text("payload") == "Text (16 B)"
    assert card.summary_text("output") == "PNG ×1"
    assert card.summary_text("encryption") == "None"

    page.set_config_variant("inline")
    page.open_step_config_inline(0)
    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    form = panel.shell.content_widget
    assert isinstance(form, LocomotiveEmbedInputs)
    assert form.payload_tabs.currentIndex() == 1
    assert form.payload_text_area.toPlainText() == "Secret timetable"
    assert form.encrypt_toggle_switch.isChecked() is False
    assert form.password_input.text() == ""
    assert form.btn_symmetric.isEnabled() is False
    assert form.btn_asymmetric.isEnabled() is False
    panel.cancel_button.click()
    _process_events(app)


def test_locomotive_public_key_roundtrip_uses_page_registry(tmp_path) -> None:
    cover_path = tmp_path / "public-cover.png"
    cover_path.write_bytes(b"prototype cover")
    payload_path = tmp_path / "public-payload.bin"
    payload_path.write_bytes(b"payload")
    _private_path, public_path = generate_and_save_keypair(
        tmp_path,
        "locomotive_public_key_roundtrip",
        key_size=2048,
    )
    registry = KeyRegistry(tmp_path / "keys.json")
    public_record = registry.add(
        "Locomotive receiver public key",
        inspect_public_key_file(public_path),
    )

    app, page = _page(key_registry=registry)
    _add_steps(page, app, ["locomotive"])
    page.set_config_variant("inline")
    page.open_step_config_inline(0)
    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    form = panel.shell.content_widget
    assert isinstance(form, LocomotiveEmbedInputs)
    assert form.key_registry is registry
    _configure_valid_locomotive_file_form(
        form,
        [cover_path],
        [payload_path],
    )
    form.btn_asymmetric.setChecked(True)
    form.encrypt_stack.setCurrentIndex(1)
    form.public_key_source.select_path(public_record.path)
    panel.save_button.click()
    _process_events(app)

    draft = page.pipeline_steps[0].technique_inputs
    assert isinstance(draft, LocomotiveInputsDraft)
    assert draft.encryption_mode == "public_key"
    assert draft.password == ""
    assert draft.public_key_path == public_record.path
    assert page.step_cards[0].summary_text("encryption") == "Public Key"

    page.open_step_config_inline(0)
    reopened_panel = page.active_step_panel
    assert isinstance(reopened_panel, StepConfigShellPanel)
    reopened_form = reopened_panel.shell.content_widget
    assert isinstance(reopened_form, LocomotiveEmbedInputs)
    assert reopened_form.key_registry is registry
    assert reopened_form.btn_asymmetric.isChecked()
    assert reopened_form.public_key_path == public_record.path
    assert reopened_form.public_key_drop_zone.selected_files == [
        public_record.path
    ]
    reopened_panel.cancel_button.click()
    _process_events(app)


def test_locomotive_invalid_save_stays_setup_and_keeps_panel_open(
    monkeypatch,
) -> None:
    app, page = _page()
    _add_steps(page, app, ["locomotive"])
    page.set_config_variant("inline")
    page.open_step_config_inline(0)
    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    assert isinstance(panel.shell.content_widget, LocomotiveEmbedInputs)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: None)

    panel.shell.description_edit.setText("Must not be committed")
    panel.save_button.click()
    _process_events(app)

    step = page.pipeline_steps[0]
    assert step.description == "Embed files in PNG"
    assert step.technique_inputs is None
    assert page.active_step_panel is panel
    assert page.step_cards[0].status == "setup"


def test_lsb_validation_covers_required_inputs_and_encryption_modes(
    tmp_path,
    monkeypatch,
) -> None:
    app = _app()
    form = LSBEmbedInputs()
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )

    assert form.validate_draft() is False

    cover_path = tmp_path / "validation-cover.png"
    cover_path.write_bytes(b"prototype cover")
    form.cover_file_path = str(cover_path)
    assert form.validate_draft() is False

    form.payload_text_area.setPlainText("Secret")
    assert form.validate_draft() is False

    form.password_input.setText("one")
    form.confirm_input.setText("two")
    assert form.validate_draft() is False

    form.encrypt_toggle_switch.setChecked(False)
    assert form.validate_draft() is True

    form.encrypt_toggle_switch.setChecked(True)
    form.btn_asymmetric.setChecked(True)
    form.encrypt_stack.setCurrentIndex(1)
    assert form.validate_draft() is False

    form.public_key_path = str(tmp_path / "invalid.pem")
    monkeypatch.setattr(
        lsb_embed_inputs,
        "inspect_public_key",
        lambda _path: KeyValidationResult("error", "Invalid test key"),
    )
    assert form.validate_draft() is False

    assert [message for _title, message in warnings] == [
        "Please select an available cover image file.",
        "Please enter a secret message or drop a text file.",
        "Please enter a password for encryption.",
        "Passwords do not match. Please confirm your passphrase.",
        "Please select a public key for encryption.",
        "Invalid test key",
    ]


def test_lsb_invalid_save_keeps_original_draft_and_panel_open(
    monkeypatch,
) -> None:
    app, page = _page()
    _add_steps(page, app, ["lsbpp"])
    page.set_config_variant("inline")
    page.open_step_config_inline(0)
    panel = page.active_step_panel
    assert isinstance(panel, StepConfigShellPanel)
    form = panel.shell.content_widget
    assert isinstance(form, LSBEmbedInputs)
    monkeypatch.setattr(QMessageBox, "warning", lambda *_args: None)

    panel.shell.description_edit.setText("Must not be saved")
    form.payload_text_area.setPlainText("Payload without a cover")
    panel.save_button.click()
    _process_events(app)

    step = page.pipeline_steps[0]
    assert step.description == "Embed text in PNG"
    assert step.technique_inputs is None
    assert page.active_step_panel is panel
    assert page.step_cards[0].status == "setup"


def test_save_uses_stable_key_after_step_renumber() -> None:
    app, page = _page()
    _add_steps(page, app, ["lsbpp", "locomotive", "metadata"])
    target_key = page.pipeline_steps[1].key

    page.remove_pipeline_step(0)
    saved = page.save_step_draft(
        target_key,
        "Renumbered locomotive draft",
        "Still targets the same step",
    )

    assert saved is True
    assert page.pipeline_steps[0].key == target_key
    assert page.pipeline_steps[0].description == "Renumbered locomotive draft"
    assert page.pipeline_steps[1].description == "Hide data in PNG or MP3 metadata"


def test_blank_description_is_rejected_without_mutating_draft(monkeypatch) -> None:
    app, page = _page()
    _add_steps(page, app, ["metadata"])
    step = page.pipeline_steps[0]
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: warnings.append(args[2]),
    )

    saved = page.save_step_draft(step.key, "   ", "Do not persist")

    assert saved is False
    assert warnings == ["Enter a description before saving this step."]
    assert step.description == "Hide data in PNG or MP3 metadata"
    assert step.guidenote == ""


def test_inline_active_step_closes_on_delete_clear_and_variant_switch() -> None:
    app, page = _page()
    _add_steps(page, app, ["lsbpp", "locomotive", "metadata"])
    page.btn_inline.click()

    QTest.mouseClick(
        page.step_cards[1].card,
        Qt.MouseButton.LeftButton,
        pos=QPoint(CARD_WIDTH // 2, CARD_HEIGHT // 2),
    )
    page.remove_pipeline_step(1)
    _process_events(app)
    assert _techniques(page) == ["lsbpp", "metadata"]
    assert page.active_step_index is None
    assert page.active_step_panel is None
    assert page.inline_slot.count() == 0

    QTest.mouseClick(
        page.step_cards[0].card,
        Qt.MouseButton.LeftButton,
        pos=QPoint(CARD_WIDTH // 2, CARD_HEIGHT // 2),
    )
    page.btn_popup.click()
    _process_events(app)
    assert page.config_variant == "popup"
    assert page.active_step_index is None
    assert page.active_step_panel is None
    assert page.inline_slot.count() == 0

    page.btn_inline.click()
    QTest.mouseClick(
        page.step_cards[0].card,
        Qt.MouseButton.LeftButton,
        pos=QPoint(CARD_WIDTH // 2, CARD_HEIGHT // 2),
    )
    page.clear_pipeline()
    _process_events(app)
    assert page.pipeline_steps == []
    assert page.active_step_index is None
    assert page.active_step_panel is None
    assert page.inline_slot.count() == 0


def test_delete_middle_renumbers_and_rebuilds_arrows() -> None:
    app, page = _page()
    _add_steps(page, app, ["lsbpp", "locomotive", "metadata"])

    page.step_cards[1].close_button.click()
    _process_events(app)

    assert _techniques(page) == ["lsbpp", "metadata"]
    assert len(page.step_cards) == 2
    assert _arrow_count(page) == 1
    assert _step_numbers(page) == ["STEP 1", "STEP 2"]


def test_delete_first_renumbers_remaining_steps() -> None:
    app, page = _page()
    _add_steps(page, app, ["lsbpp", "locomotive", "metadata"])

    page.step_cards[0].close_button.click()
    _process_events(app)

    assert _techniques(page) == ["locomotive", "metadata"]
    assert _step_numbers(page) == ["STEP 1", "STEP 2"]
    assert _arrow_count(page) == 1


def test_delete_last_removes_trailing_arrow() -> None:
    app, page = _page()
    _add_steps(page, app, ["lsbpp", "locomotive", "metadata"])

    page.step_cards[-1].close_button.click()
    _process_events(app)

    assert _techniques(page) == ["lsbpp", "locomotive"]
    assert len(page.step_cards) == 2
    assert _arrow_count(page) == 1


def test_delete_to_empty_restores_initial_canvas() -> None:
    app, page = _page()
    initial_canvas_height = page.pipeline_canvas.height()
    _add_steps(page, app, ["lsbpp", "locomotive", "metadata"])

    while page.step_cards:
        page.step_cards[0].close_button.click()
        _process_events(app)

    assert page.pipeline_steps == []
    assert len(page.step_cards) == 0
    assert _arrow_count(page) == 0
    assert page.pipeline_canvas.height() == initial_canvas_height
    assert page.canvas_scroll.verticalScrollBar().maximum() == 0


def test_canvas_contract_survives_add_and_delete() -> None:
    app, page = _page()
    outer_scroll = page.findChild(
        type(page.canvas_scroll),
        "pipelineScroll",
    )
    initial_outer_maximum = outer_scroll.verticalScrollBar().maximum()

    _add_steps(page, app, ["lsbpp"])
    assert page.pipeline_canvas.height() == CARD_HEIGHT + CANVAS_MARGIN * 2
    assert page.canvas_scroll.verticalScrollBar().maximum() == 0

    _add_steps(page, app, ["locomotive", "metadata", "lsbpp"])
    assert page.pipeline_canvas.height() == MAX_VISIBLE_FLOW_HEIGHT + CANVAS_MARGIN * 2
    assert page.canvas_scroll.verticalScrollBar().maximum() == 0

    _add_steps(
        page,
        app,
        ["locomotive", "metadata", "lsbpp", "locomotive", "metadata"],
    )

    assert all(card.size() == QSize(CARD_WIDTH, CARD_HEIGHT) for card in page.step_cards)
    assert page.pipeline_canvas.height() == MAX_VISIBLE_FLOW_HEIGHT + CANVAS_MARGIN * 2
    assert page.canvas_scroll.verticalScrollBar().maximum() > 0
    assert outer_scroll.verticalScrollBar().maximum() == initial_outer_maximum

    while len(page.pipeline_steps) > 3:
        page.step_cards[-1].close_button.click()
        _process_events(app)

    assert page.pipeline_canvas.height() < MAX_VISIBLE_FLOW_HEIGHT + CANVAS_MARGIN * 2
    assert page.canvas_scroll.verticalScrollBar().maximum() == 0
    assert _arrow_count(page) == 2


def _click_clear_dialog_button(object_name: str) -> None:
    dialog = QApplication.activeModalWidget()
    assert isinstance(dialog, QMessageBox)
    button = dialog.findChild(QPushButton, object_name)
    assert button is not None
    button.click()


def test_clear_confirmation_cancel_preserves_pipeline() -> None:
    app, page = _page()
    _add_steps(page, app, ["lsbpp", "locomotive", "metadata"])

    QTimer.singleShot(
        0,
        lambda: _click_clear_dialog_button("SecondaryBtn"),
    )
    page.confirm_clear_pipeline()
    _process_events(app)

    assert _techniques(page) == ["lsbpp", "locomotive", "metadata"]
    assert len(page.step_cards) == 3
    assert _arrow_count(page) == 2


def test_clear_confirmation_accepts_and_restores_empty_canvas() -> None:
    app, page = _page()
    initial_canvas_height = page.pipeline_canvas.height()
    _add_steps(page, app, ["lsbpp", "locomotive", "metadata"])

    QTimer.singleShot(
        0,
        lambda: _click_clear_dialog_button("DangerBtn"),
    )
    page.confirm_clear_pipeline()
    _process_events(app)

    assert page.pipeline_steps == []
    assert len(page.step_cards) == 0
    assert _arrow_count(page) == 0
    assert page.pipeline_canvas.height() == initial_canvas_height
    assert page.canvas_scroll.verticalScrollBar().maximum() == 0


def test_clear_confirmation_does_nothing_for_empty_pipeline() -> None:
    app, page = _page()

    page.confirm_clear_pipeline()
    _process_events(app)

    assert page.pipeline_steps == []
    assert QApplication.activeModalWidget() is None
