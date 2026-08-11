import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLineEdit

from src.core.crypto.key_management import (
    generate_and_save_keypair,
    inspect_private_key_file,
    inspect_public_key_file,
)
from src.gui.components.key_source import KeySourceWidget
from src.gui.dialogs.key_dialogs import GenerateKeyDialog, KeyPickerDialog
from src.gui.pages.key_management_page import KeyListItemWidget, KeyManagementPage
from src.gui.services.key_registry import KeyRegistry


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture()
def registry_with_pair(tmp_path):
    private_path, public_path = generate_and_save_keypair(
        tmp_path,
        "gui_pair",
        key_size=2048,
        password="GUI-Test-Password",
    )
    registry = KeyRegistry(tmp_path / "registry.json")
    private_record = registry.add(
        "GUI private",
        inspect_private_key_file(private_path, "GUI-Test-Password"),
    )
    public_record = registry.add("GUI public", inspect_public_key_file(public_path))
    return registry, private_record, public_record


def test_key_picker_filters_keys_by_role(app, registry_with_pair):
    registry, _private_record, public_record = registry_with_pair
    dialog = KeyPickerDialog(registry, "public")

    assert dialog.key_list.count() == 1
    item = dialog.key_list.item(0)
    assert item.data(Qt.ItemDataRole.UserRole) == public_record.path


def test_key_source_selects_saved_file_without_copying_it(app, registry_with_pair):
    registry, _private_record, public_record = registry_with_pair
    widget = KeySourceWidget("public", registry)
    selected_paths = []
    widget.key_selected.connect(selected_paths.append)

    widget.select_path(public_record.path)

    assert widget.drop_zone.file_path == public_record.path
    assert selected_paths == [public_record.path]
    assert widget.choose_button.objectName() == "KeyLibraryBtn"
    assert not widget.choose_button.icon().isNull()


def test_key_management_page_shows_real_metadata(app, registry_with_pair):
    registry, _private_record, _public_record = registry_with_pair
    page = KeyManagementPage(registry)
    page.key_list.setCurrentRow(0)
    page.show_details()

    assert page.title_label.text() == "Key Management"
    assert page.import_button.size() == page.generate_button.size()
    assert page.key_list.count() == 2
    row_widgets = [
        page.key_list.itemWidget(page.key_list.item(index))
        for index in range(page.key_list.count())
    ]
    assert all(isinstance(widget, KeyListItemWidget) for widget in row_widgets)
    list_details = {widget.detail_label.text() for widget in row_widgets}
    assert list_details == {"Private Key [RSA-2048]", "Public Key [RSA-2048]"}
    assert {widget.name_label.text() for widget in row_widgets} == {
        "GUI private",
        "GUI public",
    }
    assert "RSA-2048" in page.detail_values["Algorithm"].text()
    assert page.detail_values["Fingerprint"].text() != "—"
    assert page.edit_name_button.text() == "Edit Display Name"


def test_key_list_selection_updates_label_properties(app, registry_with_pair):
    previous_style = app.styleSheet()
    app.setStyleSheet(Path("src/gui/styles/default.qss").read_text(encoding="utf-8"))
    try:
        registry, _private_record, _public_record = registry_with_pair
        page = KeyManagementPage(registry)
        first_item = page.key_list.item(0)
        second_item = page.key_list.item(1)
        first_widget = page.key_list.itemWidget(first_item)
        second_widget = page.key_list.itemWidget(second_item)

        page.key_list.setCurrentItem(first_item)
        app.processEvents()
        assert first_widget.name_label.property("selected") is True
        assert first_widget.detail_label.property("selected") is True
        assert first_widget.name_label.palette().color(first_widget.name_label.foregroundRole()).name() == "#7dd3fc"

        page.key_list.setCurrentItem(second_item)
        app.processEvents()
        assert first_widget.name_label.property("selected") is False
        assert first_widget.detail_label.property("selected") is False
        assert second_widget.name_label.property("selected") is True
        assert second_widget.detail_label.property("selected") is True
        assert first_widget.name_label.palette().color(first_widget.name_label.foregroundRole()).name() == "#e2e8f0"
        assert second_widget.name_label.palette().color(second_widget.name_label.foregroundRole()).name() == "#7dd3fc"
    finally:
        app.setStyleSheet(previous_style)


def test_generate_dialog_uses_secure_recommended_defaults(app, tmp_path):
    dialog = GenerateKeyDialog(KeyRegistry(tmp_path / "registry.json"))

    assert dialog.size_combo.currentData() == 3072
    assert dialog.encoding_combo.currentText() == "PEM"
    assert dialog.protect_checkbox.isChecked()
    assert dialog.password_edit.isEnabled()


def test_generate_dialog_password_visibility_toggle(app, tmp_path):
    dialog = GenerateKeyDialog(KeyRegistry(tmp_path / "registry.json"))
    password_action = next(
        action
        for action in dialog.password_edit.actions()
        if action.objectName() == "passwordVisibilityAction"
    )
    confirm_action = next(
        action
        for action in dialog.confirm_edit.actions()
        if action.objectName() == "passwordVisibilityAction"
    )

    assert dialog.password_edit.echoMode() == QLineEdit.EchoMode.Password
    assert dialog.confirm_edit.echoMode() == QLineEdit.EchoMode.Password
    assert password_action.toolTip() == "Show password"
    assert confirm_action.toolTip() == "Show password"

    password_action.trigger()
    assert dialog.password_edit.echoMode() == QLineEdit.EchoMode.Normal
    assert dialog.confirm_edit.echoMode() == QLineEdit.EchoMode.Normal
    assert password_action.toolTip() == "Hide password"
    assert confirm_action.toolTip() == "Hide password"

    confirm_action.trigger()
    assert dialog.password_edit.echoMode() == QLineEdit.EchoMode.Password
    assert dialog.confirm_edit.echoMode() == QLineEdit.EchoMode.Password


def test_generate_dialog_disables_password_fields_when_unprotected(app, tmp_path):
    dialog = GenerateKeyDialog(KeyRegistry(tmp_path / "registry.json"))

    dialog.protect_checkbox.setChecked(False)

    assert not dialog.password_edit.isEnabled()
    assert not dialog.confirm_edit.isEnabled()


def test_removing_registry_item_does_not_delete_key_file(app, registry_with_pair):
    registry, _private_record, public_record = registry_with_pair

    assert registry.remove(public_record.id)
    assert os.path.isfile(public_record.path)
