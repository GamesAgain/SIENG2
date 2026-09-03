"""Focused tests for the prototype MP3 frame draft contracts."""

from dataclasses import FrozenInstanceError, fields

import pytest

from config_prototype.gui.components import technique_forms
from config_prototype.gui.components.technique_forms.metadata import (
    MP3_COMPLEX_FRAME_CONTRACTS,
    MP3ComplexFrameContract,
    MP3ComplexFrameDraft,
    MP3ComplexFrameInstanceDraft,
    MP3SimpleFrameDraft,
)


def test_complex_frame_contracts_match_the_editable_mp3_shapes() -> None:
    assert {
        frame_id: contract.fields
        for frame_id, contract in MP3_COMPLEX_FRAME_CONTRACTS.items()
    } == {
        "COMM": ("lang", "desc", "text"),
        "USLT": ("lang", "desc", "text"),
        "USER": ("lang", "text"),
        "TXXX": ("desc", "text"),
        "WXXX": ("desc", "url"),
    }
    assert MP3_COMPLEX_FRAME_CONTRACTS["USLT"].multiline
    assert all(
        contract.allows_multiple
        for contract in MP3_COMPLEX_FRAME_CONTRACTS.values()
    )
    assert not MP3_COMPLEX_FRAME_CONTRACTS["COMM"].multiline
    assert MP3_COMPLEX_FRAME_CONTRACTS["COMM"].required_fields == (
        "lang",
        "text",
    )
    assert MP3_COMPLEX_FRAME_CONTRACTS["COMM"].identity_fields == (
        "lang",
        "desc",
    )
    assert MP3_COMPLEX_FRAME_CONTRACTS["TXXX"].required_fields == (
        "text",
    )
    assert MP3_COMPLEX_FRAME_CONTRACTS["TXXX"].identity_fields == (
        "desc",
    )
    assert MP3_COMPLEX_FRAME_CONTRACTS["USER"].identity_fields == (
        "lang",
    )


def test_complex_frame_contract_is_immutable() -> None:
    contract = MP3ComplexFrameContract(("desc", "text"))

    with pytest.raises(FrozenInstanceError):
        contract.multiline = True


def test_simple_frame_draft_keeps_only_scalar_payload_data() -> None:
    draft = MP3SimpleFrameDraft(frame_id="TIT2", value="Hidden title")

    assert draft == MP3SimpleFrameDraft("TIT2", "Hidden title")
    assert {item.name for item in fields(MP3SimpleFrameDraft)} == {
        "frame_id",
        "value",
    }


def test_complex_frame_draft_keeps_ordered_structured_instances() -> None:
    first = MP3ComplexFrameInstanceDraft(
        lang="eng",
        desc="public note",
        text="first hidden message",
    )
    second = MP3ComplexFrameInstanceDraft(
        lang="tha",
        desc="private note",
        text="second hidden message",
    )
    draft = MP3ComplexFrameDraft("COMM", [first, second])

    assert draft.frame_id == "COMM"
    assert draft.instances == [first, second]
    assert draft.instances[0].text == "first hidden message"
    assert draft.instances[1].lang == "tha"


def test_complex_frame_instance_can_represent_each_supported_shape() -> None:
    values = {
        "COMM": MP3ComplexFrameInstanceDraft(
            lang="eng",
            desc="note",
            text="message",
        ),
        "USLT": MP3ComplexFrameInstanceDraft(
            lang="eng",
            desc="lyrics",
            text="line one\nline two",
        ),
        "USER": MP3ComplexFrameInstanceDraft(
            lang="eng",
            text="terms",
        ),
        "TXXX": MP3ComplexFrameInstanceDraft(
            desc="Secret",
            text="message",
        ),
        "WXXX": MP3ComplexFrameInstanceDraft(
            desc="Project",
            url="https://example.test",
        ),
    }

    for frame_id, value in values.items():
        for field_name in MP3_COMPLEX_FRAME_CONTRACTS[frame_id].fields:
            assert getattr(value, field_name) is not None


def test_complex_frame_instance_lists_have_isolated_defaults() -> None:
    first = MP3ComplexFrameDraft("TXXX")
    second = MP3ComplexFrameDraft("TXXX")

    first.instances.append(
        MP3ComplexFrameInstanceDraft(desc="Secret", text="TEST")
    )

    assert len(first.instances) == 1
    assert second.instances == []


def test_mp3_frame_contracts_are_public_technique_form_types() -> None:
    assert technique_forms.MP3_COMPLEX_FRAME_CONTRACTS is (
        MP3_COMPLEX_FRAME_CONTRACTS
    )
    assert technique_forms.MP3ComplexFrameContract is MP3ComplexFrameContract
    assert technique_forms.MP3ComplexFrameDraft is MP3ComplexFrameDraft
    assert technique_forms.MP3ComplexFrameInstanceDraft is (
        MP3ComplexFrameInstanceDraft
    )
    assert technique_forms.MP3SimpleFrameDraft is MP3SimpleFrameDraft
