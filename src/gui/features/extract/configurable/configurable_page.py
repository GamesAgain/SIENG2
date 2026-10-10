from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from PyQt6.QtWidgets import QApplication, QLabel, QFrame, QMessageBox, QScrollArea, QVBoxLayout, QHBoxLayout, QWidget
from PyQt6.QtCore import QEvent, Qt

from src.core.configurable.extract_plan import (
    ExtractPlan, ExtractResult, Need, extract_step, match_files, read_extract_plan, sha256_of,
)
from src.gui.components.gui_utils import add_shadow_effect
from src.gui.features.extract.configurable.widgets.plan_panel import ExtractPlanPanel
from src.gui.features.extract.configurable.widgets.result_dialog import ExtractResultDialog
from src.gui.features.extract.configurable.widgets.step_card import ExtractStepCard
from src.gui.services.key_registry import KeyRegistry
from src.gui.services.worker import FunctionWorker

CANVAS_MARGIN = 10  # same as the embed pipeline canvas


class ExtractConfigurablePage(QFrame):

    def __init__(self, key_registry: KeyRegistry | None = None, parent=None):
        super().__init__(parent)
        self.key_registry = key_registry
        self.plan: ExtractPlan | None = None     # the plan that is open
        self.plan_path = ""
        self.cards: dict[str, ExtractStepCard] = {}  # plan step id -> its card
        self.files: dict[tuple[str, str], str] = {}  # Need.key -> the file the receiver has (final) or got (recovered)
        self.done: set[str] = set()                  # ids of the steps extracted already
        self.failed: dict[str, str] = {}             # step id -> the error of its last try
        self.results: dict[str, ExtractResult] = {}  # step id -> what it gave (View Result shows it)
        self.workspace: TemporaryDirectory | None = None  # recovered files of this plan (removed with the plan / on exit)
        self.extract_worker: FunctionWorker | None = None
        self.extracting: str | None = None           # id of the step in the worker
        self.extract_result = None                   # handed from worker.done to worker.finished

        self.setup_ui()
        self.plan_panel.plan_selected.connect(self.open_plan)
        self.plan_panel.change_plan_requested.connect(self.clear_plan)
        self.plan_panel.final_files_added.connect(self.on_final_files)
        self.plan_panel.remove_file_requested.connect(self.remove_final_file)
        QApplication.instance().aboutToQuit.connect(self.remove_workspace)

    def setup_ui(self):
        page_layout = QVBoxLayout(self)
        page_layout.setContentsMargins(0, 0, 0, 0)

        page_layout.addWidget(self.build_content_section(), 1)  # no status bar: each step card shows its own progress


    def build_content_section(self):
        content = QFrame()
        layout = QHBoxLayout(content)


        extract_plan_card = self.build_extract_plan_card()
        extract_step_card = self.build_extract_steps_card()

        layout.addWidget(extract_plan_card, 33)
        layout.addWidget(extract_step_card, 67)

        return content

    def build_extract_plan_card(self):
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)

        title_container = QFrame()
        title_layout = QHBoxLayout(title_container)
        title = QLabel("Extract Plan")
        title.setObjectName("cardTitle")
        title_layout.addWidget(title)
        title_layout.addStretch()
        layout.addWidget(title_container)
        self.plan_panel = ExtractPlanPanel()
        layout.addWidget(self.plan_panel, 1)

        return card

    def build_extract_steps_card(self):
        card = QFrame()
        card.setObjectName("card")
        add_shadow_effect(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)

        title_container = QFrame()
        title_layout = QHBoxLayout(title_container)
        title = QLabel("Extract Steps")
        title.setObjectName("cardTitle")
        title_layout.addWidget(title)
        title_layout.addStretch()

        # Same canvas as the embed Pipeline Builder: dark frame, a centred text when empty, the cards in a scroll area
        canvas = QFrame()
        canvas.setObjectName("pipelineCanvas")
        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(CANVAS_MARGIN, CANVAS_MARGIN, CANVAS_MARGIN, CANVAS_MARGIN)
        canvas_layout.setSpacing(0)

        self.steps_hint = QLabel("Open an extract plan to see the steps.")
        self.steps_hint.setObjectName("pipelineEmpty")
        self.steps_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.steps_hint.setWordWrap(True)
        canvas_layout.addWidget(self.steps_hint, 1)

        # The step cards go into step_layout; the scroll area keeps a long list inside the canvas
        step_content = QWidget()
        step_content.setObjectName("pipelineCanvasContent")
        self.step_layout = QVBoxLayout(step_content)
        self.step_layout.setContentsMargins(0, 0, 6, 0)  # room for the scrollbar
        self.step_layout.setSpacing(8)
        self.step_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.steps_scroll = QScrollArea()
        self.steps_scroll.setObjectName("pipelineCanvasScroll")
        self.steps_scroll.setWidgetResizable(True)
        self.steps_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.steps_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.steps_scroll.setWidget(step_content)
        self.steps_scroll.hide()
        canvas_layout.addWidget(self.steps_scroll, 1)

        body = QVBoxLayout()
        body.setContentsMargins(16, 4, 16, 16)  # same inset as the Extract Plan card's contents
        body.addWidget(canvas)
        layout.addWidget(title_container)
        layout.addLayout(body, 1)
        return card

    # --- Open / clear an extract plan ---
    def open_plan(self, path: str):
        """Read the plan and build one card per step. A bad file changes nothing that is already open."""
        try:
            plan = read_extract_plan(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, "Cannot Open Extract Plan", str(error))
            self.show_plan_info()  # back to what was there: the open plan, or the empty drop zone
            return
        self.clear_plan()
        self.plan, self.plan_path = plan, path
        self.show_plan_info()
        self.build_step_cards(plan)
        self.refresh()  # nothing is added yet: every final file is missing, so every step waits

    def show_plan_info(self):
        if self.plan is None:
            self.plan_panel.plan_drop.clear_all()
            return
        files = len(self.plan.files)
        self.plan_panel.show_plan(self.plan_path, self.plan.name or Path(self.plan_path).name,
                                  f"YAML · {len(self.plan.steps)} steps · {files} final file{'s' if files != 1 else ''}")

    def clear_plan(self):
        """Change (or a new plan): forget the plan, its cards, the added files and what was extracted."""
        self.plan, self.plan_path = None, ""
        self.files.clear()
        self.done.clear()
        self.failed.clear()
        self.results.clear()
        self.remove_workspace()
        for card in self.cards.values():
            self.step_layout.removeWidget(card)
            card.hide()
            card.deleteLater()
        self.cards.clear()
        self.plan_panel.clear_plan()
        self.steps_scroll.hide()
        self.steps_hint.show()

    def build_step_cards(self, plan: ExtractPlan):
        numbers = {step.id: number for number, step in enumerate(plan.steps, start=1)}  # the extract order the receiver sees
        for number, step in enumerate(plan.steps, start=1):
            card = ExtractStepCard(step, number, numbers, key_registry=self.key_registry)
            card.extract_requested.connect(lambda step_id=step.id: self.on_extract(step_id))
            card.result_requested.connect(lambda step_id=step.id: self.show_result(step_id))
            self.step_layout.addWidget(card)
            self.cards[step.id] = card
        self.steps_hint.setVisible(not self.cards)
        self.steps_scroll.setVisible(bool(self.cards))

    # --- Final files ---
    def on_final_files(self, paths: list[str]):
        """All the files dropped so far (the drop zone sends the whole list): match them to the plan again."""
        if self.plan is None:
            return
        before = {key: path for key, path in self.files.items() if not key[0]}  # the final files that were matched
        matched, _ = match_files(self.plan, paths)
        self.files = {key: path for key, path in self.files.items() if key[0]}  # keep the recovered files only
        self.files.update({Need(name).key: path for name, path in matched.items()})
        # A final file that is gone or now another file: what was extracted from it is not true any more
        changed = {key for key, path in before.items() if self.files.get(key) != path}
        self.reset_steps(self.steps_to_reset(changed))
        for step in self.plan.steps:  # a failed try belongs to the file it had
            if any(need.key in changed for need in step.needs):
                self.failed.pop(step.id, None)
        self.refresh(paths)

    def remove_final_file(self, path: str):
        """The x on a row. Extracted steps that used this file are reset, so ask first when there are any."""
        used = {key for key, value in self.files.items() if not key[0] and value == path}
        affected = self.steps_to_reset(used)
        if affected:
            numbers = ", ".join(f"Step {self.cards[step_id].number}" for step_id in self.step_order(affected))
            answer = QMessageBox.question(
                self, "Remove File", f"{Path(path).name} was used by extracted steps.\n\n"
                f"Removing it resets {numbers}: their results and the files they recovered are discarded.\n\nRemove it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
        self.plan_panel.files_drop.remove_file(path)  # sends files_changed: on_final_files matches again and resets

    def steps_to_reset(self, keys: set) -> set[str]:
        """Ids of the extracted steps that used one of these files, and every extracted step that used what those gave."""
        affected = {step.id for step in self.plan.steps
                    if step.id in self.done and any(need.key in keys for need in step.needs)}
        grew = True
        while grew:  # follow the recovered files down the chain
            grew = False
            for step in self.plan.steps:
                if step.id in self.done and step.id not in affected and any(need.source in affected for need in step.needs):
                    affected.add(step.id)
                    grew = True
        return affected

    def step_order(self, step_ids) -> list[str]:
        return [step.id for step in self.plan.steps if step.id in step_ids]

    def reset_steps(self, step_ids: set[str]):
        """Forget what these steps gave: result, recovered files (also on disk), state and progress."""
        for step_id in step_ids:
            self.done.discard(step_id)
            self.results.pop(step_id, None)
            for key in [key for key in self.files if key[0] == step_id]:
                del self.files[key]
            if self.workspace is not None:
                shutil.rmtree(Path(self.workspace.name) / step_id, ignore_errors=True)
            self.cards[step_id].clear_progress()
        for step in self.plan.steps:  # a failed try belongs to the files it had
            if step.id in step_ids or any(need.source in step_ids for need in step.needs):
                self.failed.pop(step.id, None)

    def refresh(self, paths: list[str] = ()):
        """Show each final file's match and each step's state from the files there are now."""
        rows = []
        for file in self.plan.files:
            path = self.files.get(Need(file.name).key)
            if path is None:
                rows.append((file.name, "missing", "Not added yet", None))
            elif sha256_of(path) != file.sha256:
                rows.append((file.name, "changed", "Matched by name · the content differs from the sender's file", path))
            elif Path(path).name != file.name:
                rows.append((file.name, "renamed", f"Matched by content · added as {Path(path).name}", path))
            else:
                rows.append((file.name, "matched", "Matched by content", path))
        used = set(self.files.values())
        plan_names = {file.name.casefold() for file in self.plan.files}
        for path in paths:
            if str(path) in used:
                continue
            if Path(path).name.casefold() in plan_names:  # it has a plan file's name, but another file is used for it
                rows.append((Path(path).name, "replaced", "Not used \u00b7 a better match was added", str(path)))
            else:
                rows.append((Path(path).name, "unknown", "Not in this plan \u00b7 not used", str(path)))
        self.plan_panel.set_final_files(rows)

        numbers = {step.id: number for number, step in enumerate(self.plan.steps, start=1)}
        missing = {need.key for step in self.plan.steps for need in step.needs
                   if need.source is None and need.key not in self.files}
        for step in self.plan.steps:
            card = self.cards[step.id]
            card.set_missing(missing)
            if step.id in self.done:
                card.set_state("done", "Extracted. View Result shows what it gave.")  # turns View Result on again after set_busy
                continue
            waiting = [need for need in step.needs if need.key not in self.files]
            if waiting:
                card.set_state("waiting", self.waiting_reason(waiting[0], numbers))
            elif step.id in self.failed:
                card.set_state("failed", self.failed[step.id])  # Extract stays on: try again
            else:
                card.set_state("ready", "Every file this step needs is here.")

    @staticmethod
    def waiting_reason(need: Need, numbers: dict[str, int]) -> str:
        """Why a step waits: the first file it still needs."""
        if need.source is None:
            return f"Waiting for {need.file}: add it under Final Files"
        return f"Waiting for {need.file} from Step {numbers[need.source]}"

    # --- Extract one step ---
    def on_extract(self, step_id: str):
        """Check what the card holds, then extract the step in a worker (one step at a time)."""
        if self.extract_worker is not None or self.plan is None:
            return
        step = next(step for step in self.plan.steps if step.id == step_id)
        card = self.cards[step_id]
        password, key_path = card.credentials()
        problem = self.check_inputs(step, card, password, key_path)
        if problem:
            QMessageBox.warning(self, "Extract", problem)
            return

        if self.workspace is None:
            self.workspace = TemporaryDirectory(prefix="SIENG2-extract-")
        paths = [self.files[need.key] for need in step.needs]
        worker = FunctionWorker(extract_step, step, paths, Path(self.workspace.name), password, key_path,
                                report_progress=True)
        worker.setParent(self)
        self.extract_worker, self.extracting, self.extract_result = worker, step_id, None
        worker.progress.connect(card.set_progress)
        worker.done.connect(self.on_extract_done)
        worker.finished.connect(self.release_extract_worker)

        self.failed.pop(step_id, None)
        card.set_progress(0, "Starting...")
        self.set_busy(True)
        self.window().installEventFilter(self)  # the window cannot be closed while a step is extracted
        worker.start()

    def check_inputs(self, step, card: ExtractStepCard, password, key_path) -> str | None:
        """Why this step cannot start (shown to the user), or None."""
        if any(need.key not in self.files for need in step.needs):
            return "A file this step needs is not here yet."
        if step.encryption == "password" and not password:
            card.password_input.setFocus()
            return "Enter the password of this step."
        if step.encryption == "public_key":
            if not key_path:
                return "Choose the private key of this step."
            result = card.check_key()
            if result is not None and not result.valid:
                return result.message
        return None

    def on_extract_done(self, result):
        # Wait for finished before showing a message or starting another step
        self.extract_result = result

    def release_extract_worker(self):
        worker, step_id, result = self.extract_worker, self.extracting, self.extract_result
        self.extract_worker = self.extracting = self.extract_result = None
        if worker is not None:
            worker.deleteLater()
        self.window().removeEventFilter(self)
        self.set_busy(False)
        if self.plan is None or step_id not in self.cards:
            return
        card = self.cards[step_id]

        if isinstance(result, ExtractResult):
            # Done: keep the result, and the files it recovered make the steps that wait for them ready
            self.results[step_id] = result
            self.done.add(step_id)
            for name, path in result.files.items():
                self.files[(step_id, name)] = str(path)
            card.set_state("done", "Extracted. View Result shows what it gave.")
            card.set_progress(100, "Extraction complete.")
        else:
            message = result["error"] if isinstance(result, dict) and "error" in result else "Extraction returned an invalid result."
            self.failed[step_id] = message
            card.set_progress(0, message)
            QMessageBox.warning(self, "Extract", message)
        self.refresh(self.plan_panel.files_drop.selected_files)

    def set_busy(self, busy: bool):
        """One step at a time: lock the plan panel and every card while the worker runs."""
        self.plan_panel.setEnabled(not busy)
        for card in self.cards.values():
            card.set_busy(busy)

    def remove_workspace(self):
        if self.extract_worker is not None:
            self.extract_worker.wait()  # never delete files under a running worker (e.g. on exit)
        if self.workspace is not None:
            self.workspace.cleanup()
            self.workspace = None

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Close and self.extract_worker is not None:
            event.ignore()
            return True
        return super().eventFilter(watched, event)

    # --- View Result ---
    def show_result(self, step_id: str):
        if step_id not in self.results:
            return
        step = next(step for step in self.plan.steps if step.id == step_id)
        dialog = ExtractResultDialog(step, self.cards[step_id].number, self.results[step_id], self.used_by(step_id), self)
        dialog.exec()
        dialog.deleteLater()

    def used_by(self, step_id: str) -> dict[str, str]:
        """Recovered file name -> 'Used by Step N' (the steps that wait for that file)."""
        users = {}
        for step in self.plan.steps:
            for need in step.needs:
                if need.source == step_id:
                    users.setdefault(need.file, []).append(str(self.cards[step.id].number))
        return {name: f"Used by Step {', '.join(numbers)}" for name, numbers in users.items()}
