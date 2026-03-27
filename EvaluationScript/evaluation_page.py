import json
from difflib import SequenceMatcher


# ── helpers ───────────────────────────────────────────────────────────────────

def similarity(a, b) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def exact_score(a, b) -> float:
    return 1.0 if str(a).strip().lower() == str(b).strip().lower() else 0.0


# ── section ID → title mapping ────────────────────────────────────────────────

def build_section_title_map(yml: dict) -> dict:
    """
    Returns {section_id_str: title} for all sections.
    Falls back to description if title is empty.
    """
    mapping = {}
    for sec_id, sec_data in yml.get("sections", {}).items():
        title = (sec_data.get("title") or "").strip()
        if not title:
            title = (sec_data.get("description") or "").strip()
        if title:
            mapping[str(sec_id)] = title 
    return mapping


# ── page extraction ───────────────────────────────────────────────────────────

def get_pages(yml: dict) -> dict:
    """
    Returns {id: page_dict} keyed by page id.
    """
    return {str(p["id"]): p for p in yml.get("pages", []) if "id" in p}


# ── per-page scoring ──────────────────────────────────────────────────────────

def resolve_primary_section_title(section_chain: list, title_map: dict) -> str:
    """
    Resolves the primary section ID (first in chain) to its title.
    Returns empty string if not found.
    """
    if not section_chain:
        return ""
    primary_id = str(section_chain[0])
    return title_map.get(primary_id, "")


def score_page_pair(gt_page: dict, cand_page: dict,
                    gt_title_map: dict, cand_title_map: dict) -> dict:
    """
    Scores a single page pair across native, section chain, and primary section.
    """
    gt_native   = str(gt_page.get("native", "")).strip()
    cand_native = str(cand_page.get("native", "")).strip()
    native_score = exact_score(gt_native, cand_native)

    gt_chain   = gt_page.get("section", [])
    cand_chain = cand_page.get("section", [])

    # Chain length match
    chain_length_score = exact_score(len(gt_chain), len(cand_chain))

    # Primary section — resolve to title then compare fuzzy
    gt_primary_title   = resolve_primary_section_title(gt_chain,   gt_title_map)
    cand_primary_title = resolve_primary_section_title(cand_chain, cand_title_map)
    primary_section_score = similarity(gt_primary_title, cand_primary_title)

    weights = {
        "native":          0.50,
        "primary_section": 0.40,
        "chain_length":    0.10,
    }

    fields = {
        "native":          native_score,
        "primary_section": primary_section_score,
        "chain_length":    chain_length_score,
    }

    weighted = sum(fields[f] * weights[f] for f in weights)

    return {
        "page_score":           round(weighted * 100, 2),
        "native": {
            "gt":        gt_native,
            "candidate": cand_native,
            "score":     round(native_score * 100, 1),
            "match":     native_score == 1.0,
        },
        "primary_section": {
            "gt_title":        gt_primary_title,
            "candidate_title": cand_primary_title,
            "gt_id":           str(gt_chain[0]) if gt_chain else "",
            "candidate_id":    str(cand_chain[0]) if cand_chain else "",
            "score":           round(primary_section_score * 100, 1),
            "match":           primary_section_score >= 0.85,
        },
        "chain_length": {
            "gt":        len(gt_chain),
            "candidate": len(cand_chain),
            "score":     round(chain_length_score * 100, 1),
            "match":     chain_length_score == 1.0,
        },
    }


# ── main page score ───────────────────────────────────────────────────────────

def score_pages(candidate: dict, ground_truth: dict) -> tuple[dict, dict]:
    gt_pages   = get_pages(ground_truth)
    cand_pages = get_pages(candidate)

    gt_title_map   = build_section_title_map(ground_truth)
    cand_title_map = build_section_title_map(candidate)

    total_gt   = len(gt_pages)
    total_cand = len(cand_pages)

    if total_gt == 0:
        return {"page_score": 0.0}, {}

    scored_pages     = []
    missing_in_cand  = []   # page IDs in GT but not in candidate
    phantom_in_cand  = []   # page IDs in candidate but not in GT

    for page_id, gt_page in gt_pages.items():
        if page_id not in cand_pages:
            missing_in_cand.append(page_id)
            continue
        cand_page  = cand_pages[page_id]
        page_score = score_page_pair(gt_page, cand_page, gt_title_map, cand_title_map)
        scored_pages.append({"id": page_id, **page_score})

    for page_id in cand_pages:
        if page_id not in gt_pages:
            phantom_in_cand.append(page_id)

    # ── aggregate stats ──
    matched_count = len(scored_pages)

    avg_score = (
        sum(p["page_score"] for p in scored_pages) / matched_count
        if matched_count else 0.0
    )

    native_match_count = sum(
        1 for p in scored_pages if p["native"]["match"]
    )
    section_match_count = sum(
        1 for p in scored_pages if p["primary_section"]["match"]
    )
    chain_length_match_count = sum(
        1 for p in scored_pages if p["chain_length"]["match"]
    )

    missing_penalty = (len(missing_in_cand) / total_gt) * 100
    final_score     = max(0.0, avg_score - missing_penalty)

    score_result = {
        "page_score":              round(final_score, 2),
        "avg_matched_score":       round(avg_score, 2),
        "missing_penalty":         round(missing_penalty, 2),
        "total_gt":                total_gt,
        "total_cand":              total_cand,
        "matched_count":           matched_count,
        "missing_count":           len(missing_in_cand),
        "phantom_count":           len(phantom_in_cand),
        "native_match_count":      native_match_count,
        "native_match_rate":       round(native_match_count / matched_count * 100, 1) if matched_count else 0.0,
        "section_match_count":     section_match_count,
        "section_match_rate":      round(section_match_count / matched_count * 100, 1) if matched_count else 0.0,
        "chain_length_match_count": chain_length_match_count,
        "chain_length_match_rate": round(chain_length_match_count / matched_count * 100, 1) if matched_count else 0.0,
    }

    comparison_json = {
        "summary":       score_result,
        "pages":         scored_pages,
        "missing_pages": missing_in_cand,
        "phantom_pages": phantom_in_cand,
    }

    return score_result, comparison_json


# ── print report ──────────────────────────────────────────────────────────────

def print_page_report(score_result: dict, comparison_json: dict) -> None:
    print("\n══════════════════════════════════════════════════════")
    print("  PAGE EVALUATION REPORT")
    print("══════════════════════════════════════════════════════")
    print("""
  This report compares pages between the pipeline output and
  the human-edited ground truth. Pages are matched by ID.

  Each page is scored on:
    native          — the printed page number label (e.g. 1, [i])
    primary_section — which article the page belongs to (by title)
    chain_length    — depth of the section hierarchy chain
""")

    print("── Coverage ──────────────────────────────────────────")
    print(f"  Ground truth pages:      {score_result['total_gt']}")
    print(f"  Candidate pages:         {score_result['total_cand']}")
    print(f"  Matched:                 {score_result['matched_count']}")
    print(f"  Missing in candidate:    {score_result['missing_count']}")
    print(f"  Phantom in candidate:    {score_result['phantom_count']}")

    print("\n── Match Rates ───────────────────────────────────────")
    print("""  These rates show how often each field matched exactly
  across all matched pages.\n""")

    def bar(rate):
        return "█" * int(rate / 5)

    print(f"  native          {score_result['native_match_rate']:>5.1f}%  {bar(score_result['native_match_rate'])}")
    print(f"  primary_section {score_result['section_match_rate']:>5.1f}%  {bar(score_result['section_match_rate'])}")
    print(f"  chain_length    {score_result['chain_length_match_rate']:>5.1f}%  {bar(score_result['chain_length_match_rate'])}")

    print("\n── Score Breakdown ───────────────────────────────────")
    print(f"  Avg Matched Score:  {score_result['avg_matched_score']:>6.2f} / 100")
    print(f"  Missing Penalty:   -{score_result['missing_penalty']:>6.2f}")
    print(f"\n  PAGE SCORE:         {score_result['page_score']:>6.2f} / 100")

    # ── show mismatched pages ──
    mismatched_native   = [p for p in comparison_json["pages"] if not p["native"]["match"]]
    mismatched_section  = [p for p in comparison_json["pages"] if not p["primary_section"]["match"]]
    mismatched_chain    = [p for p in comparison_json["pages"] if not p["chain_length"]["match"]]

    if mismatched_native:
        print(f"\n── Native Mismatches ({len(mismatched_native)} pages) ────────────────")
        print("  Pages where the printed page number label differs.\n")
        for p in mismatched_native[:20]:   # cap at 20 to avoid flooding
            print(f"  page_id={p['id']}  gt='{p['native']['gt']}'  candidate='{p['native']['candidate']}'")
        if len(mismatched_native) > 20:
            print(f"  ... and {len(mismatched_native) - 20} more")

    if mismatched_section:
        print(f"\n── Section Mismatches ({len(mismatched_section)} pages) ──────────────")
        print("  Pages assigned to wrong article by the pipeline.\n")
        for p in mismatched_section[:20]:
            print(f"  page_id={p['id']}  gt='{p['primary_section']['gt_title'][:45]}'")
            print(f"           cand='{p['primary_section']['candidate_title'][:45]}'  score={p['primary_section']['score']}")
        if len(mismatched_section) > 20:
            print(f"  ... and {len(mismatched_section) - 20} more")

    if mismatched_chain:
        print(f"\n── Chain Length Mismatches ({len(mismatched_chain)} pages) ───────────")
        print("  Pages where the section hierarchy depth differs.\n")
        for p in mismatched_chain[:20]:
            print(f"  page_id={p['id']}  gt_depth={p['chain_length']['gt']}  candidate_depth={p['chain_length']['candidate']}")
        if len(mismatched_chain) > 20:
            print(f"  ... and {len(mismatched_chain) - 20} more")

    if comparison_json["missing_pages"]:
        print(f"\n── Missing Pages ─────────────────────────────────────")
        print("  Page IDs present in GT but absent in candidate.\n")
        print(f"  {comparison_json['missing_pages']}")

    if comparison_json["phantom_pages"]:
        print(f"\n── Phantom Pages ─────────────────────────────────────")
        print("  Page IDs in candidate that do not exist in GT.\n")
        print(f"  {comparison_json['phantom_pages']}")

    print("\n══════════════════════════════════════════════════════\n")


# ── standalone entry point ────────────────────────────────────────────────────

def _load_pair(output_yml_path: str) -> tuple[dict, dict]:
    import yaml
    from pathlib import Path

    output_path    = Path(output_yml_path).resolve()
    folder_name    = output_path.stem
    project_root   = output_path.parent.parent
    structure_path = project_root / "Input" / folder_name / "structure.yml"

    with open(output_path, encoding="utf-8") as f:
        candidate = yaml.safe_load(f)
    with open(structure_path, encoding="utf-8") as f:
        ground_truth = yaml.safe_load(f)

    return candidate, ground_truth


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Page Score Evaluator")
    parser.add_argument("output_yml", help="Path to Output/<name>.yml")
    args = parser.parse_args()

    candidate, ground_truth = _load_pair(args.output_yml)
    score_result, comparison_json = score_pages(candidate, ground_truth)

    print_page_report(score_result, comparison_json)

    print("── Comparison JSON ───────────────────────────────────")
    print(json.dumps(comparison_json, indent=4))
    print("══════════════════════════════════════════════════════\n")