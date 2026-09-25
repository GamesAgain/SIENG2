from PyQt6.QtWidgets import QInputDialog, QLineEdit, QMessageBox

from src.core.crypto.key_management import inspect_key_file, inspect_private_key_file


def inspect_key_with_password_prompt(parent, path: str):
    try:
        info = inspect_key_file(path)
    except (OSError, TypeError, ValueError) as error:
        QMessageBox.warning(parent, "Invalid RSA Key", str(error))
        return None

    if info.fingerprint:
        return info

    password, accepted = QInputDialog.getText(
        parent, "Encrypted Private Key", "Private key password:",
        QLineEdit.EchoMode.Password
    )
    if not accepted:
        return None

    try:
        return inspect_private_key_file(path, password)
    except (OSError, TypeError, ValueError) as error:
        QMessageBox.warning(parent, "Invalid Password", str(error))
        return None
