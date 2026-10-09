from pathlib import Path

from src.core.configurable.drafts import LocomotiveInputsDraft, LSBInputsDraft, StepDraft
from src.core.configurable.step_output import FileSource, StepOutput, StepOutputInfo

def output_name(cover: FileSource) -> str:
    """Name of the output made from this cover: a file keeps its stem (a.png -> a), a link keeps its name."""
    return cover.output_key if isinstance(cover, StepOutput) else Path(cover).stem

def has_lsb_layer(steps: list[StepDraft], reference: StepOutput) -> bool:
    """Does the file behind this output already hold an LSB++ layer? (follows the Previous Output links back)"""
    by_key = {step.key: step for step in steps}
    for _ in range(len(steps)):  # one hop per step at most, so a broken chain can never loop forever
        step = by_key.get(reference.step_key)
        if step is None or step.technique_inputs is None:
            return False
        if step.technique == "lsbpp":
            return True
        # Locomotive: output i is made from cover i, so only that cover's own chain matters
        cover = next((c for c in covers_of(step.technique_inputs) if output_name(c) == reference.output_key), None)
        if cover is None or not is_linked(cover):
            return False
        reference = cover
    return False

def links_of(draft: LSBInputsDraft | LocomotiveInputsDraft) -> list[StepOutput]:
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

    for link in links:
        source = by_key.get(link.step_key)
        if source is None:
            return "Source step was removed; select the cover again."
        source_number = numbers[link.step_key]
        if source_number >= numbers[step.key]:
            return f"Source: Step {source_number} comes after this step."
        if link not in step_outputs(source):
            return f"Source: Step {source_number} output no longer exists."
        if step.technique == "lsbpp" and has_lsb_layer(steps, link):
            return "Source already has an LSB++ layer; LSB++ cannot be stacked on it."
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
    """Outputs of the saved steps that come before this step (not the ones another step already uses)."""
    # LSB++ writes into the pixels, so it would destroy an LSB++ layer that is already in the file
    consumer = next((step for step in steps if step.key == step_key), None)
    skip_lsb = consumer is not None and consumer.technique == "lsbpp"
    used = used_outputs(steps)
    choices = []
    for number, step in enumerate(steps, start=1):
        if step.key == step_key:
            break  # stop at this step: only earlier steps can be picked
        draft = step.technique_inputs
        if isinstance(draft, LSBInputsDraft) and draft.cover:  # saved LSB++ step: 1 output
            covers = [draft.cover]
        elif isinstance(draft, LocomotiveInputsDraft):         # saved Locomotive step: 1 output per cover
            covers = draft.covers
        else:
            continue  # not saved yet, or Metadata

        for cover in covers:
            filename = output_name(cover)
            reference = StepOutput(step.key, filename)      # (step, name) = which output
            if skip_lsb and has_lsb_layer(steps, reference):
                continue
            if used.get(reference, step_key) != step_key:
                continue  # another step uses it (this step's own pick stays in the list)
            choices.append(StepOutputInfo(
                reference=reference,
                step_number=number,
                technique=step.technique,
                media_type="png",
                # The output file does not exist before the run; its source file (a manual cover) does,
                # and Locomotive does not touch pixels, so the form can read the capacity from it.
                preview_path=root_cover(steps, reference),
                display_name=filename + ".png",             # the file name it will be saved as
            ))
    return choices

def is_linked(cover: FileSource) -> bool:
    """A cover that is an earlier step's output (it has no file before the run)."""
    return isinstance(cover, StepOutput)

def covers_of(draft: LSBInputsDraft | LocomotiveInputsDraft) -> list[FileSource]:
    """The covers of a saved LSB++/Locomotive step as a list (LSB++ has one)."""
    if isinstance(draft, LSBInputsDraft):
        return [draft.cover] if draft.cover else []
    return list(draft.covers)

def link_labels(steps: list[StepDraft], draft: LSBInputsDraft | LocomotiveInputsDraft | None) -> dict[StepOutput, str]:
    """Card text of the linked covers of this draft, e.g. 'Step 1 output' (the number follows the card order)."""
    if draft is None:
        return {}
    numbers = {step.key: number for number, step in enumerate(steps, start=1)}
    return {
        cover: f"Step {numbers[cover.step_key]} output"
        for cover in links_of(draft)
        if cover.step_key in numbers
    }
