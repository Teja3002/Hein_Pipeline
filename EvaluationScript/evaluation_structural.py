import json
from difflib import SequenceMatcher


# ── helpers ───────────────────────────────────────────────────────────────────

def similarity(a, b) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def fuzzy_score(a: str, b: str) -> float:
    return similarity(a, b)


def exact_score(a, b) -> float:
    return 1.0 if str(a).strip().lower() == str(b).strip().lower() else 0.0


def set_overlap_score(list_a: list, list_b: list) -> tuple[float, dict]:
    count_a = len(list_a) if list_a else 0
    count_b = len(list_b) if list_b else 0
    count_match = count_a == count_b

    if not list_a and not list_b:
        return 1.0, {"gt_count": 0, "candidate_count": 0, "count_match": True}
    if not list_a or not list_b:
        return 0.0, {"gt_count": count_a, "candidate_count": count_b, "count_match": count_match}

    set_a = {s.lower().strip() for s in list_a if s}
    set_b = {s.lower().strip() for s in list_b if s}

    if not set_a and not set_b:
        return 1.0, {"gt_count": count_a, "candidate_count": count_b, "count_match": count_match}
    if not set_a or not set_b:
        return 0.0, {"gt_count": count_a, "candidate_count": count_b, "count_match": count_match}

    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    score = intersection / union if union else 0.0

    return score, {"gt_count": count_a, "candidate_count": count_b, "count_match": count_match}


# ── section extraction ────────────────────────────────────────────────────────

def get_structural_section(yml: dict, section_type: str) -> dict | None:
    """Returns the first section matching the given type, or None."""
    for sec in yml.get("sections", {}).values():
        if sec.get("type") == section_type:
            return sec
    return None


def get_all_structural_sections(yml: dict, section_type: str) -> list[dict]:
    """
    Returns ALL sections matching the given type, with their section ID included.
    Used for multi-issue journals.
    """
    results = []
    for sec_id, sec in yml.get("sections", {}).items():
        if sec.get("type") == section_type:
            results.append({**sec, "_sec_id": str(sec_id)})
    return results


def get_contents_for_issue(yml: dict, issue_sec_id: str) -> dict | None:
    """
    Finds the contents (TOC) section that belongs to a specific issue
    by matching insection == issue_sec_id.
    """
    for sec in yml.get("sections", {}).values():
        if sec.get("type") == "contents" and str(sec.get("insection", "")) == str(issue_sec_id):
            return sec
    return None


# ── per-type scoring ──────────────────────────────────────────────────────────

def score_volume(gt_sec: dict, cand_sec: dict | None) -> tuple[dict, dict]:
    if cand_sec is None:
        return {"score": 0.0, "fields": {}}, {
            "present": False,
            "score": 0.0,
            "type": {"gt": "volume", "candidate": None, "score": 0.0}
        }

    fields = {
        "type": exact_score(gt_sec.get("type", ""), cand_sec.get("type", ""))
    }
    score = fields["type"] * 100

    detail = {
        "present": True,
        "score": round(score, 2),
        "type": {
            "gt":        gt_sec.get("type", ""),
            "candidate": cand_sec.get("type", ""),
            "score":     round(fields["type"] * 100, 1)
        }
    }

    return {"score": round(score, 2), "fields": fields}, detail


def score_issue(gt_sec: dict, cand_sec: dict | None) -> tuple[dict, dict]:
    if cand_sec is None:
        return {"score": 0.0, "fields": {}}, {"present": False, "score": 0.0}

    fields = {
        "type":        exact_score(gt_sec.get("type", ""),           cand_sec.get("type", "")),
        "date":        fuzzy_score(gt_sec.get("date", ""),           cand_sec.get("date", "")),
        # "citation":    fuzzy_score(gt_sec.get("citation", ""),       cand_sec.get("citation", "")),
        "description": fuzzy_score(gt_sec.get("description", ""),    cand_sec.get("description", "")),
        "insection":   exact_score(str(gt_sec.get("insection", "")), str(cand_sec.get("insection", ""))),
        # "subject":     subject_score,
        # "countries":   countries_score,
    }

    weights = {
        "type":        0.30,
        "date":        0.35,
        # "citation":    0.15,
        "description": 0.30,
        "insection":   0.05,
        # "subject":     0.08,
        # "countries":   0.07,
    }

    score = sum(fields[f] * weights[f] for f in weights) * 100

    detail = {
        "present":     True,
        "score":       round(score, 2),
        "type":        {"gt": gt_sec.get("type", ""),        "candidate": cand_sec.get("type", ""),        "score": round(fields["type"] * 100, 1)},
        "date":        {"gt": gt_sec.get("date", ""),        "candidate": cand_sec.get("date", ""),        "score": round(fields["date"] * 100, 1)},
        # "citation":  {...}
        "description": {"gt": gt_sec.get("description", ""), "candidate": cand_sec.get("description", ""), "score": round(fields["description"] * 100, 1)},
        "insection":   {"gt": gt_sec.get("insection", ""),   "candidate": cand_sec.get("insection", ""),   "score": round(fields["insection"] * 100, 1)},
        # "subject":   {...}
        # "countries": {...}
    }

    return {"score": round(score, 2), "fields": fields}, detail


def score_contents(gt_sec: dict | None, cand_sec: dict | None) -> tuple[dict, dict]:
    if gt_sec is None and cand_sec is None:
        return {"score": 100.0, "fields": {}}, {"present": False, "expected": False, "score": 100.0}

    if gt_sec is None and cand_sec is not None:
        return {"score": 70.0, "fields": {}}, {
            "present": True, "expected": False, "score": 70.0,
            "note": "Candidate has TOC but GT does not"
        }

    if gt_sec is not None and cand_sec is None:
        return {"score": 0.0, "fields": {}}, {
            "present": False, "expected": True, "score": 0.0,
            "note": "GT has TOC but candidate does not"
        }

    fields = {
        "type":        exact_score(gt_sec.get("type", ""),           cand_sec.get("type", "")),
        # "title":       fuzzy_score(...)
        # "citation":    fuzzy_score(...)
        "description": fuzzy_score(gt_sec.get("description", ""),    cand_sec.get("description", "")),
        "insection":   exact_score(str(gt_sec.get("insection", "")), str(cand_sec.get("insection", ""))),
        # "insection":   exact_score(...)
    }

    weights = {
        "type":        0.45,
        # "title":       0.25,
        # "citation":    0.20,
        "description": 0.45,
        "insection":   0.10,
    }

    score = sum(fields[f] * weights[f] for f in weights) * 100

    detail = {
        "present":     True,
        "expected":    True,
        "score":       round(score, 2),
        "type":        {"gt": gt_sec.get("type", ""),        "candidate": cand_sec.get("type", ""),        "score": round(fields["type"] * 100, 1)},
        # "title":     {...}
        # "citation":  {...}
        "description": {"gt": gt_sec.get("description", ""), "candidate": cand_sec.get("description", ""), "score": round(fields["description"] * 100, 1)},
        "insection":   {"gt": gt_sec.get("insection", ""),   "candidate": cand_sec.get("insection", ""),   "score": round(fields["insection"] * 100, 1)},
    }

    return {"score": round(score, 2), "fields": fields}, detail
# ── issue matching ────────────────────────────────────────────────────────────

def match_issues(gt_issues: list[dict], cand_issues: list[dict]) -> list[dict]:
    """
    Matches GT issues to candidate issues by description fuzzy match,
    then date fuzzy match as fallback.

    Returns list of match records:
        {gt, candidate, match_type, similarity}
    where candidate may be None if no match found.
    """
    matched = []
    used_cand_indices = set()

    for gt_issue in gt_issues:
        gt_desc = (gt_issue.get("description") or "").strip()
        gt_date = str(gt_issue.get("date") or "").strip()

        best_score = 0.0
        best_idx   = None
        best_type  = "unmatched"

        for i, cand_issue in enumerate(cand_issues):
            if i in used_cand_indices:
                continue

            cand_desc = (cand_issue.get("description") or "").strip()
            cand_date = str(cand_issue.get("date") or "").strip()

            # Try description match first
            desc_score = similarity(gt_desc, cand_desc) if gt_desc and cand_desc else 0.0
            date_score = similarity(gt_date, cand_date) if gt_date and cand_date else 0.0

            # Description is primary, date is fallback
            effective_score = desc_score if desc_score > 0.5 else date_score
            match_type      = "description" if desc_score > 0.5 else "date"

            if effective_score > best_score:
                best_score = effective_score
                best_idx   = i
                best_type  = match_type

        if best_idx is not None and best_score >= 0.5:
            matched.append({
                "gt":         gt_issue,
                "candidate":  cand_issues[best_idx],
                "match_type": best_type,
                "similarity": round(best_score, 3),
            })
            used_cand_indices.add(best_idx)
        else:
            matched.append({
                "gt":         gt_issue,
                "candidate":  None,
                "match_type": "unmatched",
                "similarity": round(best_score, 3),
            })

    # Phantom candidate issues — not matched to any GT
    phantom = [
        cand_issues[i] for i in range(len(cand_issues))
        if i not in used_cand_indices
    ]

    return matched, phantom


# ── main structural score ─────────────────────────────────────────────────────

def score_structural(candidate: dict, ground_truth: dict) -> tuple[dict, dict]:

    # ── Volume ──
    gt_volume   = get_structural_section(ground_truth, "volume")
    cand_volume = get_structural_section(candidate,    "volume")
    volume_result, volume_detail = score_volume(gt_volume, cand_volume)
    volume_score = volume_result.get("score", 0.0)

    # ── Issues — collect all ──
    gt_issues   = get_all_structural_sections(ground_truth, "issue")
    cand_issues = get_all_structural_sections(candidate,    "issue")

    matched_issues, phantom_issues = match_issues(gt_issues, cand_issues)

    issue_details  = []
    contents_details = []
    issue_scores   = []
    contents_scores = []

    for match in matched_issues:
        gt_issue   = match["gt"]
        cand_issue = match["candidate"]
        gt_issue_id = gt_issue.get("_sec_id")

        # Score the issue itself
        issue_result, issue_detail = score_issue(gt_issue, cand_issue)
        issue_detail["match_type"]  = match["match_type"]
        issue_detail["similarity"]  = match["similarity"]
        issue_detail["gt_desc"]     = gt_issue.get("description", "")
        issue_scores.append(issue_result.get("score", 0.0))
        issue_details.append(issue_detail)

        # Find and score the TOC for this issue
        gt_contents   = get_contents_for_issue(ground_truth, gt_issue_id)
        cand_issue_id = cand_issue.get("_sec_id") if cand_issue else None
        cand_contents = get_contents_for_issue(candidate, cand_issue_id) if cand_issue_id else None

        contents_result, contents_detail = score_contents(gt_contents, cand_contents)
        contents_detail["for_issue"] = gt_issue.get("description", gt_issue_id)
        contents_scores.append(contents_result.get("score", 0.0))
        contents_details.append(contents_detail)

    # Average across all issues
    avg_issue_score    = round(sum(issue_scores)    / len(issue_scores)    if issue_scores    else 0.0, 2)
    avg_contents_score = round(sum(contents_scores) / len(contents_scores) if contents_scores else 0.0, 2)

    # Weighted structural score: volume 0.02, issue 0.04, toc 0.04 — normalized within structural
    # Within structural block: volume=2/10, issue=4/10, toc=4/10
    structural_score = round(
        (volume_score      * 0.20) +
        (avg_issue_score   * 0.40) +
        (avg_contents_score * 0.40),
        2
    )

    score_result = {
        "structural_score":  structural_score,
        "volume_score":      round(volume_score, 2),
        "issue_score":       avg_issue_score,
        "contents_score":    avg_contents_score,
        "total_gt_issues":   len(gt_issues),
        "total_cand_issues": len(cand_issues),
        "matched_issues":    len([m for m in matched_issues if m["candidate"] is not None]),
        "unmatched_issues":  len([m for m in matched_issues if m["candidate"] is None]),
        "phantom_issues":    len(phantom_issues),
    }

    comparison_json = {
        "summary":          score_result,
        "volume":           volume_detail,
        "issues":           issue_details,
        "contents":         contents_details,
        "phantom_issues":   [p.get("description", "") for p in phantom_issues],
    }

    return score_result, comparison_json


# ── print report ──────────────────────────────────────────────────────────────

def print_structural_report(score_result: dict, comparison_json: dict) -> None:
    print("\n══════════════════════════════════════════════════════")
    print("  STRUCTURAL SECTIONS EVALUATION REPORT")
    print("══════════════════════════════════════════════════════")
    print("""
  Evaluates structural sections: one volume, one or more issues,
  and optionally a TOC per issue. These hold journal-level metadata.

  volume   — identifies this as a volume-level container
  issue    — holds the issue date and description (one per issue)
  contents — the Table of Contents section (one per issue, optional)
""")

    def tag(score):
        return "✓" if score == 100.0 else "~" if score > 0 else "✗"

    # ── Volume ──
    print("── Volume ────────────────────────────────────────────")
    vol = comparison_json["volume"]
    print(f"  {'✓ present' if vol.get('present') else '✗ missing'}")
    if vol.get("present"):
        t = vol["type"]
        print(f"  type:  {tag(t['score'])}  gt='{t['gt']}'  candidate='{t['candidate']}'")
    print(f"  Score: {score_result['volume_score']:>6.2f} / 100")

    # ── Issues ──
    print(f"\n── Issues ({score_result['total_gt_issues']} in GT, {score_result['total_cand_issues']} in candidate) ─────────────")
    print(f"  Matched:   {score_result['matched_issues']}")
    print(f"  Unmatched: {score_result['unmatched_issues']}  (GT issues not found in candidate)")
    print(f"  Phantom:   {score_result['phantom_issues']}  (candidate issues not in GT)\n")

    for i, iss in enumerate(comparison_json["issues"]):
        label = iss.get("gt_desc") or f"Issue {i+1}"
        print(f"  ── {label} ──")
        print(f"  {'✓ present' if iss.get('present') else '✗ missing'}  [{iss.get('match_type', '')}  sim={iss.get('similarity', 0):.0%}]")
        if iss.get("present"):
            for field in ["type", "date", "description", "insection"]:
                if field in iss:
                    f = iss[field]
                    print(f"    {field:<12}  {tag(f['score'])}  gt='{f['gt']}'  candidate='{f['candidate']}'  score={f['score']}")
        print(f"    Score: {iss.get('score', 0.0):>6.2f} / 100\n")

    print(f"  AVG ISSUE SCORE:  {score_result['issue_score']:>6.2f} / 100")

    # ── Contents ──
    print(f"\n── Contents / TOC (one per issue) ────────────────────")
    for i, con in enumerate(comparison_json["contents"]):
        label = con.get("for_issue") or f"Issue {i+1}"
        print(f"  ── TOC for: {label} ──")
        if not con.get("expected") and not con.get("present"):
            print("    Not expected and not present — full score")
        elif not con.get("expected") and con.get("present"):
            print("    ⚠ Candidate has TOC but GT does not — small penalty")
        elif con.get("expected") and not con.get("present"):
            print("    ✗ GT expects TOC but candidate is missing it")
        else:
            for field in ["type", "description", "insection"]:
                if field in con:
                    f = con[field]
                    print(f"    {field:<12}  {tag(f['score'])}  gt='{f['gt']}'  candidate='{f['candidate']}'  score={f['score']}")
        if "note" in con:
            print(f"    note: {con['note']}")
        print(f"    Score: {con.get('score', 0.0):>6.2f} / 100\n")

    print(f"  AVG TOC SCORE:    {score_result['contents_score']:>6.2f} / 100")

    # ── Summary ──
    print("\n── Summary ───────────────────────────────────────────")
    print(f"  Volume:   {score_result['volume_score']:>6.2f} / 100")
    print(f"  Issue:    {score_result['issue_score']:>6.2f} / 100  (avg across {score_result['total_gt_issues']} issue(s))")
    print(f"  Contents: {score_result['contents_score']:>6.2f} / 100  (avg across {score_result['total_gt_issues']} issue(s))")
    print(f"\n  STRUCTURAL SCORE:  {score_result['structural_score']:>6.2f} / 100")
    print("══════════════════════════════════════════════════════\n")


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

    parser = argparse.ArgumentParser(description="Structural Section Evaluator")
    parser.add_argument("output_yml", help="Path to Output/<n>.yml")
    args = parser.parse_args()

    candidate, ground_truth = _load_pair(args.output_yml)
    score_result, comparison_json = score_structural(candidate, ground_truth)

    print_structural_report(score_result, comparison_json)

    print("── Comparison JSON ───────────────────────────────────")
    print(json.dumps(comparison_json, indent=4))
    print("══════════════════════════════════════════════════════\n")