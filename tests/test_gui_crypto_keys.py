import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from cryptography.hazmat.primitives import serialization
from PyQt6.QtWidgets import QApplication, QLineEdit

from src.core.configurable.config_mode import decrypt_kwargs_from_node, decrypt_kwargs
from src.core.crypto.asym_encrypt import (
    generate_rsa_keypair,
    serialize_private_key,
    serialize_public_key,
)
from src.gui.components.files_drop import FileDropWidget
from src.gui.components.key_validation import (
    KeyValidationLabel,
    inspect_private_key,
    inspect_public_key,
)
from src.gui.pages.sub_pages.extract.configurable_page import ExtractConfigurablePage
from src.gui.tabs.embed.loco_embed import LocoEmbedInputs
from src.gui.tabs.embed.lsb_embed import LSBEmbedInputs
from src.gui.tabs.extract.loco_extract import LocomotiveExtractTab
from src.gui.tabs.extract.lsb_extract import LSBExtractTab


PRIVATE_KEY_PASSWORD = "Private-Key-Password-2026!"


@pytest.fixture(scope="module")
def app():
    application = QApplication.instance() or QApplication([])
    yield application


@pytest.fixture(scope="module")
def rsa_key_files(tmp_path_factory):
    key_dir = tmp_path_factory.mktemp("gui_rsa_keys")
    private_key, public_key = generate_rsa_keypair(2048)

    public_pem = key_dir / "public.pem"
    public_der = key_dir / "public.der"
    private_pem = key_dir / "private.pem"
    private_encrypted = key_dir / "private-encrypted.key"

    public_pem.write_bytes(serialize_public_key(public_key))
    public_der.write_bytes(
        serialize_public_key(public_key, encoding=serialization.Encoding.DER)
    )
    private_pem.write_bytes(serialize_private_key(private_key))
    private_encrypted.write_bytes(
        serialize_private_key(private_key, PRIVATE_KEY_PASSWORD)
    )

    return {
        "public_pem": str(public_pem),
        "public_der": str(public_der),
        "private_pem": str(private_pem),
        "private_encrypted": str(private_encrypted),
    }


def test_file_drop_normalizes_extensions_and_checks_suffix(app):
    widget = FileDropWidget("Drop", "RSA key", allowed_extensions=["pem", ".DER"])

    assert widget.file_exts == [".pem", ".der"]
    assert widget.is_allowed_file("PUBLIC.PEM")
    assert widget.is_allowed_file("public.der")
    assert not widget.is_allowed_file("public.notpem")


@pytest.mark.parametrize("key_name", ["public_pem", "public_der"])
def test_public_key_inspection_accepts_pem_and_der(rsa_key_files, key_name):
    result = inspect_public_key(rsa_key_files[key_name])

    assert result.valid
    assert "RSA-2048" in result.detail
    assert "Public Key" in result.detail


def test_encrypted_private_key_inspection_has_clear_states(rsa_key_files):
    pending = inspect_private_key(rsa_key_files["private_encrypted"])
    valid = inspect_private_key(
        rsa_key_files["private_encrypted"],
        PRIVATE_KEY_PASSWORD,
    )
    invalid = inspect_private_key(rsa_key_files["private_encrypted"], "wrong-password")

    assert pending.state == "pending"
    assert "password required" in pending.message.lower()
    assert valid.valid
    assert "Encrypted" in valid.detail
    assert invalid.state == "error"


def test_key_validation_label_exposes_state(app, rsa_key_files):
    label = KeyValidationLabel()
    label.set_result(inspect_public_key(rsa_key_files["public_pem"]))

    assert label.property("keyState") == "valid"
    assert "RSA-2048" in label.text()


def test_embed_pages_validate_selected_public_key(app, rsa_key_files):
    widgets = [LSBEmbedInputs(), LocoEmbedInputs()]

    for widget in widgets:
        widget.on_public_key_selected(rsa_key_files["public_pem"])
        assert widget.public_key_path == rsa_key_files["public_pem"]
        assert widget.public_key_status.property("keyState") == "valid"
        assert set(widget.public_key_drop_zone.file_exts) == {".pem", ".der", ".pub"}


def test_encryption_options_password_fields_have_visibility_toggles(app):
    widget_fields = [
        (LSBEmbedInputs(), ("password_input", "confirm_input")),
        (LocoEmbedInputs(), ("password_input", "confirm_input")),
        (LSBExtractTab(), ("password_input", "key_password_input")),
        (LocomotiveExtractTab(), ("password_input", "key_password_input")),
    ]

    for widget, field_names in widget_fields:
        for field_name in field_names:
            actions = getattr(widget, field_name).actions()
            assert any(
                action.objectName() == "passwordVisibilityAction"
                for action in actions
            )


def test_embed_password_and_confirmation_visibility_stays_in_sync(app):
    widgets = [LSBEmbedInputs(), LocoEmbedInputs()]

    for widget in widgets:
        password_action = next(
            action
            for action in widget.password_input.actions()
            if action.objectName() == "passwordVisibilityAction"
        )
        confirm_action = next(
            action
            for action in widget.confirm_input.actions()
            if action.objectName() == "passwordVisibilityAction"
        )

        password_action.trigger()
        assert widget.password_input.echoMode() == QLineEdit.EchoMode.Normal
        assert widget.confirm_input.echoMode() == QLineEdit.EchoMode.Normal

        confirm_action.trigger()
        assert widget.password_input.echoMode() == QLineEdit.EchoMode.Password
        assert widget.confirm_input.echoMode() == QLineEdit.EchoMode.Password


def test_extract_password_visibility_toggles_remain_independent(app):
    widget = LSBExtractTab()
    password_action = next(
        action
        for action in widget.password_input.actions()
        if action.objectName() == "passwordVisibilityAction"
    )

    password_action.trigger()

    assert widget.password_input.echoMode() == QLineEdit.EchoMode.Normal
    assert widget.key_password_input.echoMode() == QLineEdit.EchoMode.Password


def test_extract_pages_support_encrypted_private_key_password(app, rsa_key_files):
    widgets = [LSBExtractTab(), LocomotiveExtractTab()]

    for widget in widgets:
        widget.on_private_key_selected(rsa_key_files["private_encrypted"])
        assert widget.private_key_status.property("keyState") == "pending"

        widget.key_password_input.setText(PRIVATE_KEY_PASSWORD)
        result = widget.validate_selected_private_key()
        assert result.valid
        assert widget.private_key_status.property("keyState") == "valid"
        assert set(widget.private_key_drop_zone.file_exts) == {".pem", ".der", ".key"}


def test_configurable_extract_has_private_key_password_and_validation(
    app,
    rsa_key_files,
):
    page = ExtractConfigurablePage()
    node = {
        "step_id": "extract_secret",
        "embed_id": "secret",
        "module": "lsbpp",
        "needs": ["file:secret#0"],
        "provides": ["payload:secret"],
        "decrypt": {"mode": "asymmetric"},
    }
    config = {
        "workflows": {"extract": [node]},
        "resources": {"file:secret#0": "stego.png"},
    }

    page._populate_workflow(config)
    refs = page.workflow_rows["secret"]
    refs["key_path"] = rsa_key_files["private_encrypted"]
    refs["key_password_edit"].setText(PRIVATE_KEY_PASSWORD)

    assert refs["key_password_edit"] is not None
    assert any(
        action.objectName() == "passwordVisibilityAction"
        for action in refs["key_password_edit"].actions()
    )
    assert page._validate_key_for_row(node).valid


def test_configurable_core_forwards_private_key_password():
    encryption = {"mode": "asymmetric"}
    expected = {
        "private_key_path": "private.pem",
        "password": "secret-password",
    }

    assert decrypt_kwargs(encryption, "private.pem", "secret-password") == expected
    assert decrypt_kwargs_from_node(encryption, expected) == expected
