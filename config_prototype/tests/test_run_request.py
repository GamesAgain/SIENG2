"""Focused tests for the L8.1 Draft-to-Run-Request boundary."""

import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from config_prototype.core.configurable import (
    ApicImageRequest,
    EncryptionRequest,
    LSBRunInputs,
    LocomotiveRunInputs,
    MP3ComplexFrameInstanceRequest,
    MP3ComplexFrameRequest,
    MP3MetadataRunPayload,
    MP3SimpleFrameRequest,
    MetadataRunInputs,
    PipelineRunRequest,
    PNGMetadataRunPayload,
    StepOutput,
)
from config_prototype.gui.components.technique_forms import (
    ApicImageDraft,
    LSBInputsDraft,
    LocomotiveCoverDraft,
    LocomotiveInputsDraft,
    MP3ComplexFrameDraft,
    MP3ComplexFrameInstanceDraft,
    MP3MetadataDraft,
    MP3SimpleFrameDraft,
    MetadataInputsDraft,
    PNGMetadataDraft,
)
from config_prototype.gui.pages.sub_pages.embed.configurable_page import (
    EmbedConfigurablePage,
    PipelineStepDraft,
    build_pipeline_run_request,
)


def test_run_request_models_are_immutable_and_hide_password() -> None:
    encryption = EncryptionRequest(
        mode="password",
        password="do-not-print-this",
    )
    request = PipelineRunRequest()

    assert "do-not-print-this" not in repr(encryption)
    assert isinstance(request.steps, tuple)
    with pytest.raises(FrozenInstanceError):
        request.steps = ()


def test_run_request_models_import_without_pyqt() -> None:
    project_root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import config_prototype.core.configurable.run_request; "
                "assert not any(name.startswith('PyQt6') "
                "for name in sys.modules)"
            ),
        ],
        cwd=project_root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_converter_accepts_an_empty_pipeline() -> None:
    assert build_pipeline_run_request([]) == PipelineRunRequest()


def test_converter_snapshots_main_three_step_pipeline() -> None:
    first_output = StepOutput("step_loco", "output_a4f91c2e")
    second_output = StepOutput("step_loco", "output_12bd770a")
    locomotive_draft = LocomotiveInputsDraft(
        covers=[
            LocomotiveCoverDraft(
                source="D:/demo/carrier-a.png",
                output_key=first_output.output_key,
            ),
            LocomotiveCoverDraft(
                source="D:/demo/carrier-b.png",
                output_key=second_output.output_key,
            ),
        ],
        payload_mode="files",
        payload_files=["D:/demo/secret.pdf"],
        encryption_enabled=False,
    )
    lsb_draft = LSBInputsDraft(
        cover=first_output,
        payload_text="123",
        encryption_enabled=False,
    )
    png_payload = PNGMetadataDraft(entries={"Comment": "456"})
    metadata_draft = MetadataInputsDraft(
        cover=second_output,
        payload=png_payload,
    )
    steps = [
        PipelineStepDraft(
            key="step_loco",
            technique="locomotive",
            description="Embed files in PNG",
            technique_inputs=locomotive_draft,
        ),
        PipelineStepDraft(
            key="step_lsb",
            technique="lsbpp",
            description="Embed text in PNG",
            technique_inputs=lsb_draft,
        ),
        PipelineStepDraft(
            key="step_meta",
            technique="metadata",
            description="Hide data in PNG metadata",
            technique_inputs=metadata_draft,
        ),
    ]

    request = build_pipeline_run_request(steps)

    assert [step.step_key for step in request.steps] == [
        "step_loco",
        "step_lsb",
        "step_meta",
    ]
    locomotive_inputs = request.steps[0].inputs
    assert isinstance(locomotive_inputs, LocomotiveRunInputs)
    assert [cover.output_key for cover in locomotive_inputs.covers] == [
        first_output.output_key,
        second_output.output_key,
    ]
    assert locomotive_inputs.payload_files == ("D:/demo/secret.pdf",)
    assert locomotive_inputs.encryption == EncryptionRequest()

    lsb_inputs = request.steps[1].inputs
    assert isinstance(lsb_inputs, LSBRunInputs)
    assert lsb_inputs.cover == first_output
    assert lsb_inputs.payload_text == "123"

    metadata_inputs = request.steps[2].inputs
    assert isinstance(metadata_inputs, MetadataRunInputs)
    assert metadata_inputs.cover == second_output
    assert metadata_inputs.media_type == "png"
    assert metadata_inputs.payload == PNGMetadataRunPayload(
        entries=(("Comment", "456"),),
    )

    locomotive_draft.covers[0].output_key = "changed"
    locomotive_draft.covers.append(
        LocomotiveCoverDraft("D:/demo/carrier-c.png", "output_new")
    )
    locomotive_draft.payload_files.append("D:/demo/other.bin")
    lsb_draft.payload_text = "changed"
    png_payload.entries["Comment"] = "changed"
    steps[0].description = "changed"

    assert request.steps[0].description == "Embed files in PNG"
    assert [cover.output_key for cover in locomotive_inputs.covers] == [
        first_output.output_key,
        second_output.output_key,
    ]
    assert locomotive_inputs.payload_files == ("D:/demo/secret.pdf",)
    assert lsb_inputs.payload_text == "123"
    assert metadata_inputs.payload == PNGMetadataRunPayload(
        entries=(("Comment", "456"),),
    )


def test_converter_preserves_locomotive_linked_sources_and_public_key() -> None:
    linked_cover = StepOutput("step_cover", "result")
    linked_payload = StepOutput("step_payload", "result")
    step = PipelineStepDraft(
        key="step_loco",
        technique="locomotive",
        description="Linked Locomotive inputs",
        technique_inputs=LocomotiveInputsDraft(
            covers=[
                LocomotiveCoverDraft(
                    linked_cover,
                    "output_a4f91c2e",
                )
            ],
            payload_mode="files",
            payload_files=[linked_payload],
            encryption_enabled=True,
            encryption_mode="public_key",
            password="inactive password",
            public_key_path="D:/demo/public.pem",
        ),
    )

    inputs = build_pipeline_run_request([step]).steps[0].inputs

    assert isinstance(inputs, LocomotiveRunInputs)
    assert inputs.covers[0].source == linked_cover
    assert inputs.covers[0].output_key == "output_a4f91c2e"
    assert inputs.payload_files == (linked_payload,)
    assert inputs.encryption == EncryptionRequest(
        mode="public_key",
        public_key_path="D:/demo/public.pem",
    )
    assert "inactive password" not in repr(inputs)


def test_converter_snapshots_mp3_frames_and_manual_or_linked_apic() -> None:
    linked_image = StepOutput("step_image", "result")
    complex_instance = MP3ComplexFrameInstanceDraft(
        lang="eng",
        desc="summary",
        text="Hidden comment",
    )
    mp3_draft = MP3MetadataDraft(
        frames=[
            MP3SimpleFrameDraft("TIT2", "Song title"),
            MP3ComplexFrameDraft("COMM", [complex_instance]),
        ],
        apic_images=[
            ApicImageDraft(
                image="D:/demo/front.png",
                picture_type=3,
                description="Front cover",
            ),
            ApicImageDraft(
                image=linked_image,
                picture_type=4,
                description="Back cover",
            ),
        ],
    )
    step = PipelineStepDraft(
        key="step_meta",
        technique="metadata",
        description="Hide MP3 metadata",
        guidenote="Receiver hint",
        technique_inputs=MetadataInputsDraft(
            cover="D:/demo/sound.mp3",
            payload=mp3_draft,
        ),
    )

    request = build_pipeline_run_request([step])

    assert request.steps[0].guidenote == "Receiver hint"
    inputs = request.steps[0].inputs
    assert isinstance(inputs, MetadataRunInputs)
    assert inputs.media_type == "mp3"
    payload = inputs.payload
    assert isinstance(payload, MP3MetadataRunPayload)
    assert payload.frames == (
        MP3SimpleFrameRequest("TIT2", "Song title"),
        MP3ComplexFrameRequest(
            "COMM",
            instances=(
                MP3ComplexFrameInstanceRequest(
                    lang="eng",
                    desc="summary",
                    text="Hidden comment",
                ),
            ),
        ),
    )
    complex_request = payload.frames[1]
    assert isinstance(complex_request, MP3ComplexFrameRequest)
    assert complex_request.instances[0].lang == "eng"
    assert complex_request.instances[0].desc == "summary"
    assert complex_request.instances[0].text == "Hidden comment"
    assert payload.apic_images == (
        ApicImageRequest(
            image="D:/demo/front.png",
            picture_type=3,
            description="Front cover",
        ),
        ApicImageRequest(
            image=linked_image,
            picture_type=4,
            description="Back cover",
        ),
    )

    complex_instance.text = "changed"
    mp3_draft.frames.clear()
    mp3_draft.apic_images.clear()

    assert len(payload.frames) == 2
    assert complex_request.instances[0].text == "Hidden comment"
    assert len(payload.apic_images) == 2


@pytest.mark.parametrize(
    ("enabled", "mode", "expected"),
    [
        (False, "password", EncryptionRequest()),
        (
            True,
            "password",
            EncryptionRequest(mode="password", password="secret"),
        ),
        (
            True,
            "public_key",
            EncryptionRequest(
                mode="public_key",
                public_key_path="D:/demo/public.pem",
            ),
        ),
    ],
)
def test_converter_keeps_only_active_encryption_values(
    enabled: bool,
    mode: str,
    expected: EncryptionRequest,
) -> None:
    step = PipelineStepDraft(
        key="step_lsb",
        technique="lsbpp",
        description="LSB++",
        technique_inputs=LSBInputsDraft(
            cover="D:/demo/cover.png",
            payload_text="message",
            encryption_enabled=enabled,
            encryption_mode=mode,
            password="secret",
            public_key_path="D:/demo/public.pem",
        ),
    )

    inputs = build_pipeline_run_request([step]).steps[0].inputs

    assert isinstance(inputs, LSBRunInputs)
    assert inputs.encryption == expected
    assert "secret" not in repr(inputs)


def test_converter_keeps_unconfigured_step_for_compiler_validation() -> None:
    request = build_pipeline_run_request(
        [
            PipelineStepDraft(
                key="step_setup",
                technique="metadata",
                description="Not configured",
            )
        ]
    )

    assert request.steps[0].inputs is None


def test_converter_rejects_unsupported_or_mismatched_draft_types() -> None:
    with pytest.raises(ValueError, match="Unsupported technique"):
        build_pipeline_run_request(
            [PipelineStepDraft("step_bad", "unknown", "Unknown")]
        )

    with pytest.raises(TypeError, match="incompatible Draft type"):
        build_pipeline_run_request(
            [
                PipelineStepDraft(
                    "step_bad",
                    "lsbpp",
                    "Wrong Draft",
                    technique_inputs=LocomotiveInputsDraft(),
                )
            ]
        )


def test_page_build_run_request_reads_saved_pipeline_steps_only() -> None:
    app = QApplication.instance() or QApplication([])
    page = EmbedConfigurablePage()
    page.pipeline_steps = [
        PipelineStepDraft(
            key="step_saved",
            technique="lsbpp",
            description="Saved value",
            technique_inputs=LSBInputsDraft(
                cover="D:/demo/cover.png",
                payload_text="saved payload",
                encryption_enabled=False,
            ),
        )
    ]

    request = page.build_run_request()

    assert request.steps[0].description == "Saved value"
    inputs = request.steps[0].inputs
    assert isinstance(inputs, LSBRunInputs)
    assert inputs.payload_text == "saved payload"
    page.deleteLater()
    app.processEvents()
