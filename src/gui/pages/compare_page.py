from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QColor
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QStackedWidget,
    QTabWidget, QVBoxLayout, QWidget, QPushButton
)
from src.gui.components.files_drop import FileDropWidget
from src.gui.components.gui_utils import create_icon_pixmap, format_file_size, truncate_text_middle
from src.gui.tabs.metadata_shared import FileInfoBar
from src.gui.tabs.compare.meta_diff_tab import MetaDiffTab
from src.gui.tabs.compare.struct_diff_tab import StructDiffTab
from src.gui.tabs.compare.stat_diff_tab import StatDiffTab
from src.gui.pages.analyzer_page import get_analyzer_file_display_info
from src.gui.components.worker import FunctionWorker

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "svg"
ICON_SIZE = 16

class ComparePage(QFrame):

    def __init__(self):
        super().__init__()
        self.file_orig_path = None
        self.file_stego_path = None
        self._compare_worker = None
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)

        # -- Input Section --
        self.input_stack = QStackedWidget()
        self.input_stack.setFixedHeight(160)
        self.input_stack.addWidget(self.build_drop_zones())
        self.input_stack.addWidget(self.build_selected_zones())
        main_layout.addWidget(self.input_stack)

        # -- Compare Button --
        self.btn_compare = QPushButton("Run Comparison")
        self.btn_compare.setObjectName("primaryButton")
        self.btn_compare.setFixedHeight(40)
        self.btn_compare.setEnabled(False) # Enabled only when both files are selected
        self.btn_compare.clicked.connect(self.on_compare_clicked)
        main_layout.addWidget(self.btn_compare)

        # -- Overall verdict banner (synthesizes all three diffs into one conclusion) --
        self.verdict_banner = QLabel("")
        self.verdict_banner.setWordWrap(True)
        self.verdict_banner.hide()
        main_layout.addWidget(self.verdict_banner)

        # -- Results Tabs --
        self.tab_struct = StructDiffTab()
        self.tab_meta = MetaDiffTab()
        self.tab_stat = StatDiffTab()

        self.tab = QTabWidget()
        self.tab.addTab(self.tab_struct, self.create_state_icon(ICON_DIR / "file-search.svg", ICON_SIZE), "Structure Diff")
        self.tab.addTab(self.tab_meta, self.create_state_icon(ICON_DIR / "tags.svg", ICON_SIZE), "Metadata Diff")
        self.tab.addTab(self.tab_stat, self.create_state_icon(ICON_DIR / "chart-histogram.svg", ICON_SIZE), "Statistical Diff")

        main_layout.addWidget(self.tab)  

    def build_drop_zones(self):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0,0,0,0)
        
        self.drop_orig = FileDropWidget(
            "Original File (Cover)", 
            "Drop cover file here", 
            icon_path=str(ICON_DIR / "file.svg")
        )
        self.drop_orig.file_selected.connect(self.on_file_orig_selected)
        
        self.drop_stego = FileDropWidget(
            "Suspicious File (Stego)", 
            "Drop suspicious file here", 
            icon_path=str(ICON_DIR / "file-dots.svg")
        )
        self.drop_stego.file_selected.connect(self.on_file_stego_selected)
        
        layout.addWidget(self.drop_orig)
        layout.addWidget(self.drop_stego)
        
        return container

    def build_selected_zones(self):
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0,0,0,0)
        
        # Left Info Bar
        self.info_orig = FileInfoBar()
        self.info_orig.change_file_requested.connect(self.reset_files)
        
        # Right Info Bar
        self.info_stego = FileInfoBar()
        self.info_stego.change_file_requested.connect(self.reset_files)
        
        layout.addWidget(self.info_orig)
        layout.addWidget(self.info_stego)
        
        return container

    def on_file_orig_selected(self, file_path: str):
        if not file_path:
            self.file_orig_path = None
            self.check_files_ready()
            return
        self.file_orig_path = file_path
        self.check_files_ready()

    def on_file_stego_selected(self, file_path: str):
        if not file_path:
            self.file_stego_path = None
            self.check_files_ready()
            return
        self.file_stego_path = file_path
        self.check_files_ready()
        
    def check_files_ready(self):
        if self.file_orig_path and self.file_stego_path:
            # Update Info Bars
            self.info_orig.update_info(get_analyzer_file_display_info(self.file_orig_path))
            self.info_stego.update_info(get_analyzer_file_display_info(self.file_stego_path))
            
            self.input_stack.setCurrentIndex(1)
            self.btn_compare.setEnabled(True)

    def reset_files(self):
        self.file_orig_path = None
        self.file_stego_path = None
        self.drop_orig.clear_file()
        self.drop_stego.clear_file()
        self.input_stack.setCurrentIndex(0)
        self.btn_compare.setEnabled(False)
        self.verdict_banner.hide()

        # Clear Tabs
        self.tab_struct.load_data({})
        self.tab_meta.load_data({})
        self.tab_stat.load_data({})

    def on_compare_clicked(self):
        # Two Docker analyze() calls back-to-back - run them off the UI thread so the window
        # doesn't freeze, with the button showing a busy state.
        if not (self.file_orig_path and self.file_stego_path):
            return
        if self._compare_worker and self._compare_worker.isRunning():
            return
        from src.core.analyzer.docker_bridge import analyze
        orig, stego = self.file_orig_path, self.file_stego_path
        self._set_comparing(True)
        self._compare_worker = FunctionWorker(lambda: {"orig": analyze(orig), "stego": analyze(stego)})
        self._compare_worker.done.connect(self._on_compare_done)
        self._compare_worker.start()

    def _set_comparing(self, busy: bool):
        self.btn_compare.setEnabled(not busy)
        self.btn_compare.setText("Comparing…" if busy else "Run Comparison")

    def _on_compare_done(self, res: dict):
        self._set_comparing(False)
        if not isinstance(res, dict) or res.get("error"):
            QMessageBox.critical(self, "Comparison Failed",
                                 res.get("error", "Unknown error") if isinstance(res, dict) else "Unknown error")
            return
        res_orig, res_stego = res.get("orig", {}), res.get("stego", {})
        if res_orig.get("error") or res_stego.get("error"):
            QMessageBox.critical(self, "Comparison Failed", res_orig.get("error") or res_stego.get("error"))
            return

        from src.core.analyzer.compare_logic import compare_results
        diff = compare_results(res_orig, res_stego, self.file_orig_path, self.file_stego_path)

        self.tab_meta.load_data(diff.get("metadata_diff", {}))
        self.tab_struct.load_data(diff.get("structure_diff", {}))
        self.tab_stat.load_data(diff.get("statistical_diff", {}))

        self._set_verdict(self._compute_verdict(diff))

    # ----- Overall verdict synthesis -----
    def _compute_verdict(self, diff: dict) -> list:
        """Turn the raw diffs into a short list of concrete detections (which technique,
        appended data, metadata changes) so the user gets a conclusion, not just numbers."""
        signals = []

        # --- Statistical / spatial-domain LSB ---
        # RS is the authoritative replacement detector (tight clean baseline; blind it cleanly
        # separates replacement from matching/PVD). SPA/WS have noisy baselines whose small
        # differential jumps cross-talk with other techniques, so they inform the table but not
        # the headline attribution - a >10% RS rise is what names the file "LSB replacement".
        stat = diff.get("statistical_diff", {})
        cover, stego = stat.get("original", {}), stat.get("stego", {})
        replacement = False
        rs_o, rs_s = cover.get("rs_analysis"), stego.get("rs_analysis")
        if rs_o and rs_s and (rs_s.get("estimated_embedding_rate", 0) - rs_o.get("estimated_embedding_rate", 0)) > 0.10:
            signals.append(f"LSB replacement (~{rs_s['estimated_embedding_rate'] * 100:.0f}% of capacity)")
            replacement = True
        # HCF-COM's center-of-mass drop signals additive-noise embedding, but LSB replacement
        # drops it too - so it only names "matching" when RS didn't already call replacement
        # (priority cascade: RS > HCF-COM > PDH, each claiming only if the reliabler ones are silent).
        matching = False
        hc_o, hc_s = cover.get("hcf_com"), stego.get("hcf_com")
        if not replacement and hc_o and hc_s and hc_o.get("hcf_com") and \
                (hc_o["hcf_com"] - hc_s["hcf_com"]) / hc_o["hcf_com"] > 0.03:
            signals.append("LSB matching / additive-noise embedding (HCF-COM dropped)")
            matching = True
        # The PDH step artifact also rises for replacement and (sometimes) matching, so PDH only
        # names PVD when the other detectors are silent - PVD is the technique they all miss, so
        # "only PDH fired" is the genuine PVD signature.
        pd_o, pd_s = cover.get("pdh"), stego.get("pdh")
        if not replacement and not matching and pd_o and pd_s and pd_o.get("pdh_step", 0) > 0 and \
                (pd_s.get("pdh_step", 0) - pd_o["pdh_step"]) / pd_o["pdh_step"] > 0.10:
            signals.append("PVD embedding (difference-histogram step artifact)")

        # --- Structure: appended data / integrity anomalies gained by the stego file ---
        struct = diff.get("structure_diff", {})
        st_stego, st_cover = struct.get("stego", {}), struct.get("original", {})
        ov = st_stego.get("overlay_analysis", {})
        if ov.get("has_overlay") and not st_cover.get("overlay_analysis", {}).get("has_overlay"):
            signals.append(f"data appended after the file's real end ({ov.get('overlay_size_bytes', 0)} bytes)")
        for anomaly in st_stego.get("integrity_anomalies", []):
            signals.append(anomaly.get("detail", "structural integrity anomaly"))

        # --- Metadata: only genuine embedded fields, not file-system attributes (File:* /
        #     System:* / Composite:* - size, dates, permissions always change on a re-save
        #     and aren't where data is hidden) ---
        def is_content_key(k: str) -> bool:
            k = k.lower()
            return not (k.startswith(("file:", "system:", "composite:")) or k in ("sourcefile", "directory"))
        meta = diff.get("metadata_diff", {})
        n_added = sum(1 for k in meta.get("added", {}) if is_content_key(k))
        n_changed = sum(1 for k in meta.get("changed", {}) if is_content_key(k))
        if n_added or n_changed:
            signals.append(f"metadata fields changed ({n_added} added, {n_changed} modified)")

        return signals

    def _set_verdict(self, signals: list):
        self.verdict_banner.show()
        if signals:
            items = "".join(f"<li>{s}</li>" for s in signals)
            self.verdict_banner.setText(f"<b>Hidden data likely — the suspicious file differs from the original:</b>"
                                        f"<ul style='margin:4px 0 0 0;'>{items}</ul>")
            color = "#f43f5e"
        else:
            self.verdict_banner.setText("<b>No differences suggesting steganography</b> — the two files match "
                                        "across structure, metadata, and statistical tests.")
            color = "#10B981"
        r, g, b = QColor(color).red(), QColor(color).green(), QColor(color).blue()
        self.verdict_banner.setStyleSheet(
            f"padding: 10px 12px; border-radius: 6px; background: rgba({r},{g},{b},0.12); color: {color};")

    # ----- Icon Helper -----
    def create_state_icon(self, icon_path: str, icon_size: int) -> QIcon:
        color_normal = "#64748B"
        color_checked = "#38BDF8"
        color_hover = "#E2E8F0"
        icon = QIcon()
        
        pix_normal = create_icon_pixmap(icon_path, color_normal, size=icon_size)
        icon.addPixmap(pix_normal, QIcon.Mode.Normal, QIcon.State.Off)
        
        pix_hover = create_icon_pixmap(icon_path, color_hover, size=icon_size)
        icon.addPixmap(pix_hover, QIcon.Mode.Active, QIcon.State.Off)
        
        pix_checked = create_icon_pixmap(icon_path, color_checked, size=icon_size)
        icon.addPixmap(pix_checked, QIcon.Mode.Normal, QIcon.State.On)
        icon.addPixmap(pix_checked, QIcon.Mode.Active, QIcon.State.On)
        
        return icon
