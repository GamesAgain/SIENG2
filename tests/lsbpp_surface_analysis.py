from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.stego.lsb_pp import LSBPP
DATASET_DIR = ROOT / "datasets" / "img"
OUTPUT_DIR = ROOT / "tests" / "output" / "lsbpp_surface"


def build_config(gradient_enabled: bool, entropy_enabled: bool) -> dict:
    return {
        "default_seed": "Default",
        "pixel_shuffle": True,
        "gradient_analysis": {
            "enabled": gradient_enabled,
            "sobel_kernel": 3,
            "weight": 0.5,
        },
        "local_entropy": {
            "enabled": entropy_enabled,
            "entropy_window": 5,
            "weight": 0.5,
        },
        "capacity_threshold": {
            "3bit": 0.7,
            "2bit": 0.4,
            "1bit": 0.1,
        },
    }


def summarize_surface(surface: np.ndarray) -> Dict[str, float | int | List[int]]:
    surface = np.asarray(surface, dtype=np.float32)
    return {
        "shape": [int(surface.shape[0]), int(surface.shape[1])],
        "min": float(surface.min()),
        "max": float(surface.max()),
        "mean": float(surface.mean()),
        "std": float(surface.std()),
        "p10": float(np.percentile(surface, 10)),
        "p50": float(np.percentile(surface, 50)),
        "p90": float(np.percentile(surface, 90)),
        "count_gt_0_5": int(np.count_nonzero(surface > 0.5)),
        "count_gt_0_8": int(np.count_nonzero(surface > 0.8)),
        "count_zero": int(np.count_nonzero(surface == 0)),
    }


def save_preview(surface: np.ndarray, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    gray = np.clip(surface, 0.0, 1.0)
    gray_u8 = np.uint8(gray * 255)
    Image.fromarray(gray_u8, mode="L").save(output_path)


def save_heatmap(surface: np.ndarray, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 6), dpi=160)
    im = ax.imshow(surface, cmap="viridis", vmin=0.0, vmax=1.0)
    ax.set_title("Texture surface heatmap")
    ax.set_xticks([])
    ax.set_yticks([])
    fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def save_histogram(surface: np.ndarray, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 4), dpi=160)
    ax.hist(surface.ravel(), bins=40, color="#4f46e5", alpha=0.8)
    ax.set_title("Surface value histogram")
    ax.set_xlabel("Texture score")
    ax.set_ylabel("Pixel count")
    fig.tight_layout()
    fig.savefig(output_path, bbox_inches="tight")
    plt.close(fig)


def run_case(image_path: Path, gradient_enabled: bool, entropy_enabled: bool) -> Tuple[dict, np.ndarray]:
    config = build_config(gradient_enabled=gradient_enabled, entropy_enabled=entropy_enabled)
    lsbpp = LSBPP(config)
    cover_image = lsbpp.prepare_image(str(image_path))
    surface = lsbpp.analyze_cover_image(cover_image)
    summary = summarize_surface(surface)
    return summary, surface


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    image_paths = sorted(DATASET_DIR.glob("*.png"))
    if not image_paths:
        raise FileNotFoundError(f"No PNG files found in {DATASET_DIR}")

    cases = [
        ("grad_and_entropy", True, True),
        ("grad_only", True, False),
        ("entropy_only", False, True),
        ("none", False, False),
    ]

    report = {}

    # Run a compact experiment on all images and save summaries.
    for case_name, grad_enabled, ent_enabled in cases:
        case_results = []
        for image_path in image_paths:
            summary, surface = run_case(image_path, grad_enabled, ent_enabled)
            case_results.append(
                {
                    "image": image_path.name,
                    **summary,
                }
            )

        report[case_name] = case_results

        # Save visual outputs for the first image to make the output easy to inspect visually.
        first_image = image_paths[0]
        _, surface = run_case(first_image, grad_enabled, ent_enabled)
        save_preview(surface, OUTPUT_DIR / f"{case_name}_{first_image.stem}_surface.png")
        save_heatmap(surface, OUTPUT_DIR / f"{case_name}_{first_image.stem}_heatmap.png")
        save_histogram(surface, OUTPUT_DIR / f"{case_name}_{first_image.stem}_hist.png")

    # Save the structured report.
    report_path = OUTPUT_DIR / "surface_summary.json"
    with report_path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)

    # Print a concise human-readable summary for the first image.
    print("LSB++ surface analysis experiment")
    print(f"Dataset images: {len(image_paths)}")
    print(f"Saved previews, plots, and JSON report to: {OUTPUT_DIR}")
    print()

    first_image = image_paths[0]
    print(f"Representative image: {first_image.name}")
    for case_name, grad_enabled, ent_enabled in cases:
        summary, _ = run_case(first_image, grad_enabled, ent_enabled)
        print(f"[{case_name}]")
        print(f"  gradient_enabled={grad_enabled}, entropy_enabled={ent_enabled}")
        print(f"  mean={summary['mean']:.4f}, std={summary['std']:.4f}, p90={summary['p90']:.4f}")
        print(f"  count > 0.5 = {summary['count_gt_0_5']}, count > 0.8 = {summary['count_gt_0_8']}")
        print()


if __name__ == "__main__":
    main()
