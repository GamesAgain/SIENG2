"""Focused tests for the prototype manual Locomotive input form."""

import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox

from config_prototype.gui.components.technique_forms import (
    LocomotiveCoverDraft,
    LocomotiveEmbedInputs,
    LocomotiveInputsDraft,
    generate_output_key,
    link_sources_to_covers,
)
from config_prototype.core.configurable.step_output import StepOutput
from config_prototype.gui.components.technique_forms import loco_embed_inputs
from src.core.crypto.key_management import generate_and_save_keypair
from src.gui.components.key_validation import KeyValidationResult


_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def _write_png(path: Path) -> Path:
    path.write_bytes(b"prototype png")
    return path


def test_locomotive_output_key_format_and_collision_retry(monkeypatch) -> None:
    generated_uuids = iter(
        [
            SimpleNamespace(hex="a4f91c2e000000000000000000000000"),
            SimpleNamespace(hex="12bd770a000000000000000000000000"),
        ]
    )
    monkeypatch.setattr(
        loco_embed_inputs,
        "uuid4",
        lambda: next(generated_uuids),
    )

    output_key = generate_output_key({"output_a4f91c2e"})

    assert output_key == "output_12bd770a"


def test_reconcile_locomotive_covers_preserves_keys_during_reorder() -> None:
    first = LocomotiveCoverDraft("carrier-a.png", "output_a4f91c2e")
    second = LocomotiveCoverDraft("carrier-b.png", "output_12bd770a")

    reconciled = link_sources_to_covers(
        ["carrier-b.png", "carrier-a.png"],
        [first, second],
    )

    assert reconciled == [second, first]


def test_reconcile_locomotive_covers_removes_and_replaces_identity() -> None:
    removed = LocomotiveCoverDraft("old.png", "output_a4f91c2e")
    preserved = LocomotiveCoverDraft("keep.png", "output_12bd770a")

    reconciled = link_sources_to_covers(
        ["keep.png", "new.png"],
        [removed, preserved],
    )

    assert reconciled[0] is preserved
    assert reconciled[1].source == "new.png"
    assert reconciled[1].output_key not in {
        removed.output_key,
        preserved.output_key,
    }


def test_reconcile_locomotive_covers_supports_linked_sources() -> None:
    linked_source = StepOutput("step_a31f8", "result")
    existing = LocomotiveCoverDraft(linked_source, "output_a4f91c2e")

    assert link_sources_to_covers(
        [linked_source],
        [existing],
    ) == [existing]


def test_draft_lists_are_isolated_and_form_defaults_are_consistent() -> None:
    _app()
    first = LocomotiveInputsDraft()
    second = LocomotiveInputsDraft()
    first.covers.append(LocomotiveCoverDraft("first.png"))
    first.payload_files.append("payload.bin")

    assert second.covers == []
    assert second.payload_files == []

    form = LocomotiveEmbedInputs()
    draft = form.export_draft()
    assert draft == LocomotiveInputsDraft()
    assert form.cover_summary_label.text() == "Selected: 0 PNGs"
    assert form.payload_file_summary_label.text() == (
        "Files: 0 · Total: 0 B"
    )
    assert form.capacity_label.text() == "Size: 0 B"


def test_files_password_load_validate_export_roundtrip(tmp_path) -> None:
    _app()
    covers = [
        _write_png(tmp_path / "cover-1.png"),
        _write_png(tmp_path / "cover-2.PNG"),
    ]
    payloads = [tmp_path / "one.bin", tmp_path / "two.txt"]
    payloads[0].write_bytes(b"a" * 1024)
    payloads[1].write_bytes(b"b" * 512)
    source = LocomotiveInputsDraft(
        covers=[
            LocomotiveCoverDraft(str(covers[0]), "output_a4f91c2e"),
            LocomotiveCoverDraft(str(covers[1]), "output_12bd770a"),
        ],
        payload_mode="files",
        payload_files=[str(path) for path in payloads],
        payload_text="inactive text",
        encryption_enabled=True,
        encryption_mode="password",
        password="manual workflow password",
        public_key_path=str(tmp_path / "inactive.pem"),
    )

    form = LocomotiveEmbedInputs()
    form.load_draft(source)

    assert form.validate_draft() is True
    assert form.cover_drop_zone.selected_files == [
        cover.source for cover in source.covers
    ]
    assert form.payload_file_drop_zone.selected_files == source.payload_files
    assert form.cover_summary_label.text() == "Selected: 2 PNGs"
    assert form.payload_file_summary_label.text() == (
        "Files: 2 · Total: 1.50 KB"
    )
    assert form.export_draft() == LocomotiveInputsDraft(
        covers=source.covers,
        payload_mode="files",
        payload_files=source.payload_files,
        encryption_enabled=True,
        encryption_mode="password",
        password="manual workflow password",
    )


def test_text_no_encryption_load_clears_inactive_secrets(tmp_path) -> None:
    _app()
    cover = _write_png(tmp_path / "cover.png")
    inactive_payload = tmp_path / "inactive.bin"
    inactive_payload.write_bytes(b"inactive")
    source = LocomotiveInputsDraft(
        covers=[LocomotiveCoverDraft(str(cover), "output_a4f91c2e")],
        payload_mode="text",
        payload_files=[str(inactive_payload)],
        payload_text="ทดสอบ",
        encryption_enabled=False,
        encryption_mode="public_key",
        password="must be cleared",
        public_key_path=str(tmp_path / "missing-public.pem"),
    )

    form = LocomotiveEmbedInputs()
    form.load_draft(source)

    assert form.validate_draft() is True
    assert form.payload_tabs.currentIndex() == 1
    assert form.payload_file_paths == []
    assert form.capacity_label.text() == "Size: 15 B"
    assert form.btn_asymmetric.isChecked()
    assert form.btn_symmetric.isEnabled() is False
    assert form.btn_asymmetric.isEnabled() is False
    assert form.export_draft() == LocomotiveInputsDraft(
        covers=source.covers,
        payload_mode="text",
        payload_text="ทดสอบ",
        encryption_enabled=False,
        encryption_mode="public_key",
    )


def test_load_filters_missing_paths_and_replaces_stale_widget_state(
    tmp_path,
) -> None:
    _app()
    old_cover = _write_png(tmp_path / "old.png")
    old_payload = tmp_path / "old.bin"
    old_payload.write_bytes(b"old")
    new_cover = _write_png(tmp_path / "new.png")

    form = LocomotiveEmbedInputs()
    form.load_draft(
        LocomotiveInputsDraft(
            covers=[
                LocomotiveCoverDraft(str(old_cover), "output_a4f91c2e")
            ],
            payload_files=[str(old_payload)],
            password="old password",
        )
    )
    form.load_draft(
        LocomotiveInputsDraft(
            covers=[
                LocomotiveCoverDraft(
                    str(tmp_path / "missing.png"),
                    "output_deadbeef",
                ),
                LocomotiveCoverDraft(str(new_cover), "output_12bd770a"),
            ],
            payload_mode="text",
            payload_text="replacement text",
            encryption_enabled=False,
        )
    )

    assert form.locomotive_file_paths == [str(new_cover)]
    assert form.payload_file_paths == []
    assert form.payload_text_area.toPlainText() == "replacement text"
    assert form.password_input.text() == ""
    assert form.confirm_input.text() == ""
    assert form.public_key_path is None


def test_manual_cover_changes_preserve_only_matching_output_identities() -> None:
    _app()
    form = LocomotiveEmbedInputs()
    form.on_locomotive_file_selected(["first.png", "second.png"])
    first, second = form.locomotive_covers

    form.on_locomotive_file_selected(["second.png", "first.png"])
    assert form.locomotive_covers == [second, first]

    form.on_locomotive_file_selected(["second.png", "replacement.png"])
    preserved, replacement = form.locomotive_covers
    assert preserved is second
    assert replacement.source == "replacement.png"
    assert replacement.output_key not in {
        first.output_key,
        second.output_key,
    }


def test_validation_reports_required_file_and_password_states(
    tmp_path,
    monkeypatch,
) -> None:
    _app()
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )
    form = LocomotiveEmbedInputs()

    assert form.validate_draft() is False

    cover = _write_png(tmp_path / "cover.png")
    form.on_locomotive_file_selected([str(cover)])
    assert form.validate_draft() is False

    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"payload")
    form.on_payload_file_selected([str(payload)])
    assert form.validate_draft() is False

    form.password_input.setText("one")
    form.confirm_input.setText("two")
    assert form.validate_draft() is False

    form.confirm_input.setText("one")
    assert form.validate_draft() is True

    assert [message for _title, message in warnings] == [
        "Please select at least one PNG cover image.",
        "Please select at least one payload file.",
        "Please enter a password for encryption.",
        "Passwords do not match. Please confirm your passphrase.",
    ]


def test_validation_rejects_missing_files_and_blank_text(
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
    form = LocomotiveEmbedInputs()

    form.on_locomotive_file_selected([str(tmp_path / "missing-cover.png")])
    assert form.validate_draft() is False

    cover = _write_png(tmp_path / "cover.png")
    form.on_locomotive_file_selected([str(cover)])
    form.on_payload_file_selected([str(tmp_path / "missing-payload.bin")])
    assert form.validate_draft() is False

    form.payload_tabs.setCurrentIndex(1)
    form.payload_text_area.setPlainText("   ")
    assert form.validate_draft() is False

    assert warnings == [
        "One or more PNG cover images are no longer available.",
        "One or more payload files are no longer available.",
        "Please enter a secret message.",
    ]


def test_public_key_validation_and_roundtrip(
    tmp_path,
    monkeypatch,
) -> None:
    _app()
    cover = _write_png(tmp_path / "cover.png")
    payload = tmp_path / "payload.bin"
    payload.write_bytes(b"payload")
    form = LocomotiveEmbedInputs()
    form.on_locomotive_file_selected([str(cover)])
    form.on_payload_file_selected([str(payload)])
    form.btn_asymmetric.setChecked(True)
    form.encrypt_stack.setCurrentIndex(1)

    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )
    assert form.validate_draft() is False

    invalid_key = tmp_path / "invalid.pem"
    invalid_key.write_bytes(b"not a public key")
    form.public_key_path = str(invalid_key)
    monkeypatch.setattr(
        loco_embed_inputs,
        "inspect_public_key",
        lambda _path: KeyValidationResult("error", "Invalid test public key"),
    )
    assert form.validate_draft() is False
    assert warnings == [
        ("Validation Error", "Please select an available public key for encryption."),
        ("Invalid Public Key", "Invalid test public key"),
    ]

    monkeypatch.undo()
    _private_path, public_path = generate_and_save_keypair(
        tmp_path,
        "locomotive_form_roundtrip",
        key_size=2048,
    )
    form.public_key_source.select_path(str(public_path))
    assert form.validate_draft() is True
    exported = form.export_draft()
    assert exported.encryption_mode == "public_key"
    assert exported.password == ""
    assert exported.public_key_path == str(public_path)
