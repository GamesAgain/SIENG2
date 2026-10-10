from PyQt6.QtWidgets import QLabel, QFrame, QScrollArea, QVBoxLayout, QHBoxLayout
from PyQt6.QtCore import Qt

from src.core.configurable.extract_plan import Need, PlanStep
from src.gui.components.gui_utils import add_shadow_effect
from src.gui.features.extract.configurable.widgets.plan_panel import ExtractPlanPanel
from src.gui.features.extract.configurable.widgets.step_card import ExtractStepCard
from src.gui.services.key_registry import KeyRegistry

class ExtractConfigurablePage(QFrame):
    
    def __init__(self, key_registry: KeyRegistry | None = None, parent=None):
        super().__init__(parent)
        self.key_registry = key_registry
        
        self.setup_ui()
        self.show_mock_steps()  # MOCK: remove when the plan is read from extract_pipeline.yaml
        self.show_mock_plan()   # MOCK: same

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
        
        # The step cards go into step_layout; the scroll area keeps a long list inside the card
        step_canvas = QFrame()
        step_canvas.setObjectName("transparentScrollContent")
        self.step_layout = QVBoxLayout(step_canvas)
        self.step_layout.setContentsMargins(16, 16, 8, 16)
        self.step_layout.setSpacing(8)
        self.step_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("transparentScroll")
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setWidget(step_canvas)

        layout.addWidget(title_container)
        layout.addWidget(scroll_area, 1)
        return card

        
        
    # --- MOCK data: a plan that is read, with one final file of each state ---
    def show_mock_plan(self):
        self.plan_panel.show_plan("extract_pipeline.yaml", "Nested Concealment & Cross-Media Key Distribution",
                                  "YAML · 5 steps · 4 final files")
        self.plan_panel.set_final_files([
            ("image3.png", "matched", "Matched by content"),
            ("song.mp3", "renamed", "Matched by content · saved as song (1).mp3"),
            ("image2.png", "changed", "Matched by name · the content differs from the sender's file"),
            ("image4.png", "missing", "Not added yet"),
        ])

    # --- MOCK data: one card of each kind, no logic behind them (replaced when the plan is connected) ---
    def show_mock_steps(self):
        steps = [
            (PlanStep("step1", "metadata", description="Hide password fragment 2 in image 3", guidenote="Read Comment with Extract Metadata. Append it after the fragment from image 2.",
                      needs=[Need("image3.png")], gives_fields=True), "done"),
            (PlanStep("step2", "metadata", description="Hide password part 2 in MP3 metadata", guidenote="User Text RecoveryPasswordPart2 is password part 2.",
                      needs=[Need("song.mp3")], gives_fields=True, gives_pictures={"front-cover": "cover.png"}), "ready"),
            (PlanStep("step3", "lsbpp", description="Hide the primary secret in image 1", encryption="password", needs=[Need("image2.png")], gives_text=True), "failed"),
            (PlanStep("step4", "locomotive", description="Distribute image 1 across images 3 and 4", encryption="public_key", guidenote="Select both carrier images. The private key is shared separately.",
                      needs=[Need("image3.png"), Need("image4.png")], gives_files=["image5.png"]), "waiting"),
            (PlanStep("step5", "lsbpp", description="Hide a message inside the recovered image", encryption="password", needs=[Need("image5.png", "step4")], gives_text=True), "waiting"),
        ]
        numbers = {step.id: number for number, (step, _) in enumerate(steps, start=1)}
        for number, (step, state) in enumerate(steps, start=1):
            card = ExtractStepCard(step, number, numbers, missing={Need("image4.png").key}, key_registry=self.key_registry)
            card.set_state(state)
            self.step_layout.addWidget(card)
            if state == "done":
                card.set_progress(100, "Extraction complete.")
            elif state == "failed":
                card.set_progress(0, "Wrong password, or this file has no LSB++ data.")
            elif state == "ready":
                card.set_progress(45, "Reading metadata...")  # MOCK: what a running step looks like
