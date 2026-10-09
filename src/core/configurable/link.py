from pathlib import Path

from src.core.configurable.drafts import LocomotiveInputsDraft, LSBInputsDraft, MetadataInputsDraft, StepDraft
from src.core.configurable.step_output import FileSource, StepOutput, StepOutputInfo

Draft = LSBInputsDraft | LocomotiveInputsDraft | MetadataInputsDraft

# technique ที่ซ้อนตัวเองไม่ได้: LSB++ เขียนทับพิกเซลชั้นเดิม / Metadata เขียนทับรายการ field ลับของชั้นเดิม
NO_STACKING = {
    "lsbpp": "Source already has an LSB++ layer; LSB++ cannot be stacked on it.",
    "metadata": "Source already has a Metadata layer; Metadata cannot be stacked on it.",
}

def output_name(cover: FileSource) -> str:
    """Name of the output made from this cover: a file keeps its stem (a.png -> a), a link keeps its name."""
    return cover.output_key if isinstance(cover, StepOutput) else Path(cover).stem

def output_media(step: StepDraft) -> str:
    """'png' or 'mp3': what the step's outputs are. Only a Metadata step on an MP3 file makes an MP3."""
    draft = step.technique_inputs
    if isinstance(draft, MetadataInputsDraft) and isinstance(draft.target, str):
        if Path(draft.target).suffix.lower() == ".mp3":
            return "mp3"
    return "png"

def has_layer(steps: list[StepDraft], reference: StepOutput, technique: str) -> bool:
    """Does the file behind this output already hold a layer of this technique? (follows the Previous Output links back)"""
    by_key = {step.key: step for step in steps}
    for _ in range(len(steps)):  # one hop per step at most, so a broken chain can never loop forever
        step = by_key.get(reference.step_key)
        if step is None or step.technique_inputs is None:
            return False
        if step.technique == technique:
            return True
        # output i is made from cover i, so only that cover's own chain matters
        cover = next((c for c in covers_of(step.technique_inputs) if output_name(c) == reference.output_key), None)
        if cover is None or not is_linked(cover):
            return False
        reference = cover
    return False

def has_lsb_layer(steps: list[StepDraft], reference: StepOutput) -> bool:
    return has_layer(steps, reference, "lsbpp")

def links_of(draft: Draft) -> list[StepOutput]:
    """The Previous Outputs a saved step uses: its covers, and its payload files when the payload is files."""
    sources = covers_of(draft)
    if isinstance(draft, LocomotiveInputsDraft) and draft.payload_mode == "files":
        sources += draft.payload_files
    return [source for source in sources if is_linked(source)]

def used_outputs(steps: list[StepDraft]) -> dict[StepOutput, str]:
    """Previous Outputs that a step uses -> the key of the first step (card order) that uses it (an output can be used once)."""
    users = {}
    for step in steps:
        if step.technique_inputs is not None:
            for link in links_of(step.technique_inputs):
                users.setdefault(link, step.key)
    return users

def step_outputs(step: StepDraft) -> list[StepOutput]:
    """The outputs a saved step makes: one per cover, named after the cover."""
    if step.technique_inputs is None:
        return []
    return [StepOutput(step.key, output_name(cover)) for cover in covers_of(step.technique_inputs)]

def link_problem(steps: list[StepDraft], step: StepDraft) -> str | None:
    """Why a Previous Output of this step cannot be used (-> BLOCKED), or None."""
    if step.technique_inputs is None:
        return None
    numbers = {other.key: number for number, other in enumerate(steps, start=1)}
    by_key = {other.key: other for other in steps}
    users = used_outputs(steps)
    links = links_of(step.technique_inputs)
    cover_links = [cover for cover in covers_of(step.technique_inputs) if is_linked(cover)]

    for link in links:
        source = by_key.get(link.step_key)
        if source is None:
            return "Source step was removed; select the cover again."
        source_number = numbers[link.step_key]
        if source_number >= numbers[step.key]:
            return f"Source: Step {source_number} comes after this step."
        if link not in step_outputs(source):
            return f"Source: Step {source_number} output no longer exists."
        if step.technique in NO_STACKING and has_layer(steps, link, step.technique):
            return NO_STACKING[step.technique]
        if link in cover_links and output_media(source) != "png":
            return f"Source: Step {source_number} output is an MP3; a cover must be a PNG."
        if links.count(link) > 1:
            return f"Source: Step {source_number} output is used more than once in this step."
        if users[link] != step.key:
            return f"Source: Step {source_number} output is also used by Step {numbers[users[link]]}."
    return None

def dependents(steps: list[StepDraft], step_key: str) -> list[int]:
    """Numbers of the steps that use an output of this step (they become BLOCKED when it is removed)."""
    return [
        number for number, step in enumerate(steps, start=1)
        if step.key != step_key and step.technique_inputs is not None
        and any(link.step_key == step_key for link in links_of(step.technique_inputs))
    ]

def root_cover(steps: list[StepDraft], reference: StepOutput) -> str | None:
    """The manual file a chain started from (follows the Previous Output links back), or None if the chain is broken."""
    by_key = {step.key: step for step in steps}
    for _ in range(len(steps)):  # one hop per step at most, so a chain that loops stops
        step = by_key.get(reference.step_key)
        if step is None or step.technique_inputs is None:
            return None
        # Output i is made from cover i, so only that cover's own chain matters
        cover = next((c for c in covers_of(step.technique_inputs) if output_name(c) == reference.output_key), None)
        if cover is None:
            return None
        if not is_linked(cover):
            return cover  # a real file
        reference = cover  # still a link: go one step further back
    return None

def output_choices(steps: list[StepDraft], step_key: str) -> list[StepOutputInfo]:
    """
    Outputs of the saved steps that come before this step (not the ones another step already uses).
    LSB++ and Metadata only see PNG outputs without a layer of their own technique;
    Locomotive sees every free output (its cover picker keeps the PNGs, its payload picker takes MP3 too).
    """
    consumer = next((step for step in steps if step.key == step_key), None)
    technique = consumer.technique if consumer is not None else None
    used = used_outputs(steps)
    choices = []
    for number, step in enumerate(steps, start=1):
        if step.key == step_key:
            break  # stop at this step: only earlier steps can be picked
        if step.technique_inputs is None:
            continue  # not saved yet
        media = output_media(step)
        if technique in NO_STACKING and media != "png":
            continue

        for cover in covers_of(step.technique_inputs):
            filename = output_name(cover)
            reference = StepOutput(step.key, filename)      # (step, name) = which output
            if technique in NO_STACKING and has_layer(steps, reference, technique):
                continue
            if used.get(reference, step_key) != step_key:
                continue  # another step uses it (this step's own pick stays in the list)
            choices.append(StepOutputInfo(
                reference=reference,
                step_number=number,
                technique=step.technique,
                media_type=media,
                # The output file does not exist before the run; its source file (a manual cover) does.
                # LSB++ capacity and the Metadata editor read from it (Locomotive / Metadata do not touch pixels).
                preview_path=root_cover(steps, reference),
                display_name=f"{filename}.{media}",          # the file name it will be saved as
            ))
    return choices

def is_linked(cover: FileSource) -> bool:
    """A cover that is an earlier step's output (it has no file before the run)."""
    return isinstance(cover, StepOutput)

def covers_of(draft: Draft) -> list[FileSource]:
    """The covers of a saved step as a list (LSB++ has one; a Metadata target counts as its cover)."""
    if isinstance(draft, LSBInputsDraft):
        return [draft.cover] if draft.cover else []
    if isinstance(draft, MetadataInputsDraft):
        return [draft.target] if draft.target else []
    return list(draft.covers)

def link_labels(steps: list[StepDraft], draft: Draft | None) -> dict[StepOutput, str]:
    """Card text of the linked covers of this draft, e.g. 'Step 1 output' (the number follows the card order)."""
    if draft is None:
        return {}
    numbers = {step.key: number for number, step in enumerate(steps, start=1)}
    return {
        cover: f"Step {numbers[cover.step_key]} output"
        for cover in links_of(draft)
        if cover.step_key in numbers
    }
