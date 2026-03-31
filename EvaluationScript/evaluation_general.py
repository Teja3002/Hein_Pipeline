import yaml
import argparse
from rapidfuzz import fuzz
from pathlib import Path


# ── helpers ──────────────────────────────────────────────────────────────────

def fuzzy_score(a: str, b: str) -> float:
    """Returns 0.0–1.0 similarity between two strings."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return fuzz.token_sort_ratio(str(a), str(b)) / 100.0


def exact_score(a, b) -> float:
    return 1.0 if str(a).strip() == str(b).strip() else 0.0


def bool_score(a, b) -> float:
    return 1.0 if bool(a) == bool(b) else 0.0


# ── section helpers ───────────────────────────────────────────────────────────

def get_issue_section(yml: dict) -> dict:
    """Returns the section with type='issue'."""
    for sec in yml.get("sections", {}).values():
        if sec.get("type") == "issue":
            return sec
    return {}


def has_toc_section(yml: dict) -> bool:
    """Returns True if any section has type='contents'."""
    return any(
        sec.get("type") == "contents"
        for sec in yml.get("sections", {}).values()
    )


def get_article_section_count(yml: dict) -> int:
    """Count sections that are articles (not volume/issue/contents)."""
    structural_types = {"volume", "issue", "contents"}
    return sum(
        1 for sec in yml.get("sections", {}).values()
        if sec.get("type") not in structural_types
    )


# ── general score ─────────────────────────────────────────────────────────────

def score_general(candidate: dict, ground_truth: dict) -> tuple[dict, dict]:
    results = {}

    # Journal title (fuzzy)
    title_raw = fuzzy_score(
        candidate.get("title", ""),
        ground_truth.get("title", "")
    )
    # 95%+ title similarity treated as 100 — typos are acceptable
    results["title"] = 1.0 if title_raw >= 0.95 else title_raw 

    # Identifier (fuzzy)
    results["identifier"] = fuzzy_score(
        candidate.get("identifier", ""),
        ground_truth.get("identifier", "")
    )

    # Max page count (exact)
    results["max"] = exact_score(
        candidate.get("max", ""),
        ground_truth.get("max", "")
    )

    # Top-level type field (exact)
    results["type"] = exact_score(
        candidate.get("type", ""),
        ground_truth.get("type", "")
    )

    # Series
    gt_series = ground_truth.get("series", None)
    cand_series = candidate.get("series", None)

    if gt_series is None and cand_series is None:
        results["series"] = 1.0
    elif gt_series is None:
        results["series"] = 0.5
    else:
        results["series"] = exact_score(cand_series, gt_series)

    # ── compute final score ──
    weights = {
        "title":      0.30,
        "identifier": 0.20,
        "max":        0.20,
        "type":       0.15,
        "series":     0.15,
    }

    final_score = sum(results[k] * weights[k] for k in weights) * 100

    # ── score result ──
    score_result = {
        "details": {k: round(v * 100, 1) for k, v in results.items()},
        "general_score": round(final_score, 2)
    }

    # ── comparison JSON ──
    comparison_json = {
        "title":      {"candidate": candidate.get("title", ""),      "ground_truth": ground_truth.get("title", ""),      "score": round(results["title"] * 100, 1)},
        "identifier": {"candidate": candidate.get("identifier", ""), "ground_truth": ground_truth.get("identifier", ""), "score": round(results["identifier"] * 100, 1)},
        "max":        {"candidate": candidate.get("max", ""),        "ground_truth": ground_truth.get("max", ""),        "score": round(results["max"] * 100, 1)},
        "type":       {"candidate": candidate.get("type", ""),       "ground_truth": ground_truth.get("type", ""),       "score": round(results["type"] * 100, 1)},
        "series":     {"candidate": cand_series,                     "ground_truth": gt_series,                          "score": round(results["series"] * 100, 1)},
        "general_score": round(final_score, 2)
    }

    return score_result, comparison_json


# ── standalone entry point ────────────────────────────────────────────────────

def _load_pair(output_yml_path: str) -> tuple[dict, dict]:
    output_path = Path(output_yml_path).resolve()
    folder_name = output_path.stem
    project_root = output_path.parent.parent
    structure_path = project_root / "Input" / folder_name / "structure.yml"

    with open(output_path, encoding="utf-8") as f:
        candidate = yaml.safe_load(f)
    with open(structure_path, encoding="utf-8") as f:
        ground_truth = yaml.safe_load(f)

    return candidate, ground_truth


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="General Score Evaluator")
    parser.add_argument("output_yml", help="Path to Output/<name>.yml")
    args = parser.parse_args()

    candidate, ground_truth = _load_pair(args.output_yml)
    result = score_general(candidate, ground_truth) 

    print("\n── General Score ─────────────────────────")
    for field, score in result["details"].items():
        bar = "█" * int(score / 5)
        print(f"  {field:<18} {score:>5.1f}  {bar}")
    print(f"\n  GENERAL SCORE:    {result['general_score']:.2f} / 100")
    print("──────────────────────────────────────────\n")