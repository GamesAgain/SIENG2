import json

import pytest
from cryptography.hazmat.primitives import serialization

from src.core.crypto.asym_encrypt import generate_rsa_keypair
from src.core.crypto.key_management import (
    generate_and_save_keypair,
    inspect_key_file,
    inspect_private_key_file,
    inspect_public_key_file,
    verify_key_pair,
)
from src.gui.services.key_registry import KeyRegistry


PRIVATE_PASSWORD = "Registry-Test-Password-2026!"


@pytest.mark.parametrize("encoding", ["PEM", "DER"])
def test_generate_and_inspect_keypair(tmp_path, encoding):
    private_path, public_path = generate_and_save_keypair(
        tmp_path,
        f"test_{encoding.lower()}",
        key_size=2048,
        password=PRIVATE_PASSWORD,
        encoding=encoding,
    )

    private_info = inspect_private_key_file(private_path, PRIVATE_PASSWORD)
    public_info = inspect_public_key_file(public_path)

    assert private_info.role == "private"
    assert public_info.role == "public"
    assert private_info.key_size == public_info.key_size == 2048
    assert private_info.encoding == public_info.encoding == encoding
    assert private_info.fingerprint == public_info.fingerprint
    assert verify_key_pair(public_path, private_path, PRIVATE_PASSWORD)


def test_encrypted_private_key_can_be_registered_without_password(tmp_path):
    private_path, _ = generate_and_save_keypair(
        tmp_path,
        "pending_private",
        key_size=2048,
        password=PRIVATE_PASSWORD,
    )

    info = inspect_key_file(private_path)

    assert info.role == "private"
    assert info.encrypted
    assert info.key_size is None
    assert info.fingerprint is None


def test_inspect_openssh_public_key_reports_its_real_format(tmp_path):
    _, public_key = generate_rsa_keypair(2048)
    public_path = tmp_path / "external.pub"
    public_path.write_bytes(
        public_key.public_bytes(
            serialization.Encoding.OpenSSH,
            serialization.PublicFormat.OpenSSH,
        )
    )

    info = inspect_public_key_file(public_path)

    assert info.encoding == "OpenSSH"
    assert info.container == "OpenSSH"


def test_generation_never_overwrites_existing_key_files(tmp_path):
    generate_and_save_keypair(tmp_path, "no_overwrite", key_size=2048)

    with pytest.raises(FileExistsError, match="already exists"):
        generate_and_save_keypair(tmp_path, "no_overwrite", key_size=2048)


def test_verify_key_pair_rejects_different_pairs(tmp_path):
    private_a, _ = generate_and_save_keypair(tmp_path, "pair_a", key_size=2048)
    _, public_b = generate_and_save_keypair(tmp_path, "pair_b", key_size=2048)

    assert not verify_key_pair(public_b, private_a)


def test_registry_persists_only_key_references_and_metadata(tmp_path):
    storage_path = tmp_path / "registry.json"
    private_path, public_path = generate_and_save_keypair(
        tmp_path,
        "registry_pair",
        key_size=2048,
        password=PRIVATE_PASSWORD,
    )
    registry = KeyRegistry(storage_path)
    registry.add("Test private", inspect_private_key_file(private_path, PRIVATE_PASSWORD))
    registry.add("Test public", inspect_public_key_file(public_path))

    restored = KeyRegistry(storage_path)
    stored_text = storage_path.read_text(encoding="utf-8")
    stored_json = json.loads(stored_text)

    assert len(restored.records()) == 2
    assert len(restored.records("public")) == 1
    assert len(restored.records("private")) == 1
    assert PRIVATE_PASSWORD not in stored_text
    assert "BEGIN PRIVATE KEY" not in stored_text
    assert stored_json["version"] == 1


def test_registry_updates_duplicate_path_instead_of_adding_it_twice(tmp_path):
    storage_path = tmp_path / "registry.json"
    _, public_path = generate_and_save_keypair(tmp_path, "duplicate", key_size=2048)
    info = inspect_public_key_file(public_path)
    registry = KeyRegistry(storage_path)

    first = registry.add("Old label", info)
    second = registry.add("New label", info)

    assert first.id == second.id
    assert len(registry.records()) == 1
    assert registry.records()[0].label == "New label"


def test_registry_renames_display_name_and_persists_it(tmp_path):
    storage_path = tmp_path / "registry.json"
    _, public_path = generate_and_save_keypair(tmp_path, "rename", key_size=2048)
    registry = KeyRegistry(storage_path)
    record = registry.add("Old display name", inspect_public_key_file(public_path))

    renamed = registry.rename(record.id, "New display name")
    restored = KeyRegistry(storage_path)

    assert renamed.id == record.id
    assert renamed.label == "New display name"
    assert restored.get(record.id).label == "New display name"

    with pytest.raises(ValueError, match="cannot be empty"):
        registry.rename(record.id, "   ")


def test_registry_can_relocate_a_missing_key_reference(tmp_path):
    storage_path = tmp_path / "registry.json"
    _, old_public_path = generate_and_save_keypair(tmp_path, "old_location", key_size=2048)
    _, new_public_path = generate_and_save_keypair(tmp_path, "new_location", key_size=2048)
    registry = KeyRegistry(storage_path)
    record = registry.add("Relocated public", inspect_public_key_file(old_public_path))
    old_public_path.unlink()

    updated = registry.update_path(record.id, inspect_public_key_file(new_public_path))

    assert updated.id == record.id
    assert updated.label == record.label
    assert updated.path == str(new_public_path.resolve())
