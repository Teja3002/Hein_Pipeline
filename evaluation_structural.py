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
    """
    Returns (score, detail) where detail includes count comparison.
    Handles empty string entries — both all-empty lists count as a match.
    """
    count_a = len(list_a) if list_a else 0
    count_b = len(list_b) if list_b else 0
    count_match = count_a == count_b

    if not list_a and not list_b:
        return 1.0, {"gt_count": 0, "candidate_count": 0, "count_match": True}
    if not list_a or not list_b:
        return 0.0, {"gt_count": count_a, "candidate_count": count_b, "count_match": count_match}

    set_a = {s.lower().strip() for s in list_a if s}
    set_b = {s.lower().strip() for s in list_b if s}

    # Both exist but contain only empty strings — counts as a match
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

    subject_score,   subject_detail   = set_overlap_score(gt_sec.get("subject", []),   cand_sec.get("subject", []))
    countries_score, countries_detail = set_overlap_score(gt_sec.get("countries", []), cand_sec.get("countries", []))

    fields = {
        "type":        exact_score(gt_sec.get("type", ""),           cand_sec.get("type", "")),
        "date":        fuzzy_score(gt_sec.get("date", ""),           cand_sec.get("date", "")),
        "citation":    fuzzy_score(gt_sec.get("citation", ""),       cand_sec.get("citation", "")),
        "description": fuzzy_score(gt_sec.get("description", ""),    cand_sec.get("description", "")),
        "insection":   exact_score(str(gt_sec.get("insection", "")), str(cand_sec.get("insection", ""))),
        "subject":     subject_score,
        "countries":   countries_score,
    }

    weights = {
        "type":        0.20,
        "date":        0.30,
        "citation":    0.15,
        "description": 0.15,
        "insection":   0.05,
        "subject":     0.08,
        "countries":   0.07,
    }

    score = sum(fields[f] * weights[f] for f in weights) * 100

    detail = {
        "present": True,
        "score":       round(score, 2),
        "type":        {"gt": gt_sec.get("type", ""),        "candidate": cand_sec.get("type", ""),        "score": round(fields["type"] * 100, 1)},
        "date":        {"gt": gt_sec.get("date", ""),        "candidate": cand_sec.get("date", ""),        "score": round(fields["date"] * 100, 1)},
        "citation":    {"gt": gt_sec.get("citation", ""),    "candidate": cand_sec.get("citation", ""),    "score": round(fields["citation"] * 100, 1)},
        "description": {"gt": gt_sec.get("description", ""), "candidate": cand_sec.get("description", ""), "score": round(fields["description"] * 100, 1)},
        "insection":   {"gt": gt_sec.get("insection", ""),   "candidate": cand_sec.get("insection", ""),   "score": round(fields["insection"] * 100, 1)},
        "subject": {
            "gt":             gt_sec.get("subject", []),
            "candidate":      cand_sec.get("subject", []),
            "score":          round(subject_score * 100, 1),
            "gt_count":       subject_detail["gt_count"],
            "candidate_count": subject_detail["candidate_count"],
            "count_match":    subject_detail["count_match"],
        },
        "countries": {
            "gt":             gt_sec.get("countries", []),
            "candidate":      cand_sec.get("countries", []),
            "score":          round(countries_score * 100, 1),
            "gt_count":       countries_detail["gt_count"],
            "candidate_count": countries_detail["candidate_count"],
            "count_match":    countries_detail["count_match"],
        },
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
        "title":       fuzzy_score(gt_sec.get("title", ""),          cand_sec.get("title", "")),
        "citation":    fuzzy_score(gt_sec.get("citation", ""),       cand_sec.get("citation", "")),
        "description": fuzzy_score(gt_sec.get("description", ""),    cand_sec.get("description", "")),
        "insection":   exact_score(str(gt_sec.get("insection", "")), str(cand_sec.get("insection", ""))),
    }

    weights = {
        "type":        0.30,
        "title":       0.25,
        "citation":    0.20,
        "description": 0.15,
        "insection":   0.10,
    }

    score = sum(fields[f] * weights[f] for f in weights) * 100

    detail = {
        "present": True, "expected": True,
        "score":       round(score, 2),
        "type":        {"gt": gt_sec.get("type", ""),        "candidate": cand_sec.get("type", ""),        "score": round(fields["type"] * 100, 1)},
        "title":       {"gt": gt_sec.get("title", ""),       "candidate": cand_sec.get("title", ""),       "score": round(fields["title"] * 100, 1)},
        "citation":    {"gt": gt_sec.get("citation", ""),    "candidate": cand_sec.get("citation", ""),    "score": round(fields["citation"] * 100, 1)},
        "description": {"gt": gt_sec.get("description", ""), "candidate": cand_sec.get("description", ""), "score": round(fields["description"] * 100, 1)},
        "insection":   {"gt": gt_sec.get("insection", ""),   "candidate": cand_sec.get("insection", ""),   "score": round(fields["insection"] * 100, 1)},
    }

    return {"score": round(score, 2), "fields": fields}, detail


# ── main structural score ─────────────────────────────────────────────────────

def score_structural(candidate: dict, ground_truth: dict) -> tuple[dict, dict]:
    gt_volume   = get_structural_section(ground_truth, "volume")
    gt_issue    = get_structural_section(ground_truth, "issue")
    gt_contents = get_structural_section(ground_truth, "contents")

    cand_volume   = get_structural_section(candidate, "volume")
    cand_issue    = get_structural_section(candidate, "issue")
    cand_contents = get_structural_section(candidate, "contents")

    volume_result,   volume_detail   = score_volume(gt_volume, cand_volume)
    issue_result,    issue_detail    = score_issue(gt_issue, cand_issue)
    contents_result, contents_detail = score_contents(gt_contents, cand_contents)

    volume_score   = volume_result.get("score", 0.0)
    issue_score    = issue_result.get("score", 0.0)
    contents_score = contents_result.get("score", 0.0)

    final_score = (volume_score + issue_score + contents_score) / 3

    score_result = {
        "structural_score": round(final_score, 2),
        "volume_score":     round(volume_score, 2),
        "issue_score":      round(issue_score, 2),
        "contents_score":   round(contents_score, 2),
    }

    comparison_json = {
        "summary":  score_result,
        "volume":   volume_detail,
        "issue":    issue_detail,
        "contents": contents_detail,
    }

    return score_result, comparison_json


# ── print report ──────────────────────────────────────────────────────────────

def print_structural_report(score_result: dict, comparison_json: dict) -> None:
    print("\n══════════════════════════════════════════════════════")
    print("  STRUCTURAL SECTIONS EVALUATION REPORT")
    print("══════════════════════════════════════════════════════")
    print("""
  Evaluates the 3 non-article sections present in every journal:
  volume, issue, and contents (TOC). These hold journal-level
  metadata rather than article content.

  volume   — identifies this as a volume-level container
  issue    — holds the issue date, citation, description, subject, and countries
  contents — the Table of Contents section (may not always exist)
""")

    def tag(score):
        return "✓" if score == 100.0 else "~" if score > 0 else "✗"

    def count_tag(detail):
        """Returns a count mismatch warning if counts differ."""
        if not detail.get("count_match", True):
            return f"  ⚠ count mismatch: gt={detail['gt_count']}  candidate={detail['candidate_count']}"
        return f"  count: {detail.get('gt_count', '?')} entries — match"

    # Volume
    print("── Volume ────────────────────────────────────────────")
    vol = comparison_json["volume"]
    print(f"  {'✓ present' if vol.get('present') else '✗ missing'}")
    if vol.get("present"):
        t = vol["type"]
        print(f"  type:         {tag(t['score'])}  gt='{t['gt']}'  candidate='{t['candidate']}'")
    print(f"  Score: {score_result['volume_score']:>6.2f} / 100")

    # Issue
    print("\n── Issue ─────────────────────────────────────────────")
    iss = comparison_json["issue"]
    print(f"  {'✓ present' if iss.get('present') else '✗ missing'}")
    if iss.get("present"):
        for field in ["type", "date", "citation", "description", "insection"]:
            if field in iss:
                f = iss[field]
                print(f"  {field:<12}  {tag(f['score'])}  gt='{f['gt']}'  candidate='{f['candidate']}'  score={f['score']}")
        # subject and countries with count info
        for field in ["subject", "countries"]:
            if field in iss:
                f = iss[field]
                print(f"  {field:<12}  {tag(f['score'])}  score={f['score']}")
                print(f"  {count_tag(f)}")
    print(f"  Score: {score_result['issue_score']:>6.2f} / 100")

    # Contents
    print("\n── Contents (TOC) ────────────────────────────────────")
    con = comparison_json["contents"]
    if not con.get("expected") and not con.get("present"):
        print("  Not expected and not present — full score")
    elif not con.get("expected") and con.get("present"):
        print("  ⚠ Candidate has TOC but GT does not — small penalty")
    elif con.get("expected") and not con.get("present"):
        print("  ✗ GT expects TOC but candidate is missing it")
    else:
        for field in ["type", "title", "citation", "description", "insection"]:
            if field in con:
                f = con[field]
                print(f"  {field:<12}  {tag(f['score'])}  gt='{f['gt']}'  candidate='{f['candidate']}'  score={f['score']}")
    if "note" in con:
        print(f"  note: {con['note']}")
    print(f"  Score: {score_result['contents_score']:>6.2f} / 100")

    print("\n── Summary ───────────────────────────────────────────")
    print(f"  Volume:   {score_result['volume_score']:>6.2f} / 100")
    print(f"  Issue:    {score_result['issue_score']:>6.2f} / 100")
    print(f"  Contents: {score_result['contents_score']:>6.2f} / 100")
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
    parser.add_argument("output_yml", help="Path to Output/<name>.yml")
    args = parser.parse_args()

    candidate, ground_truth = _load_pair(args.output_yml)
    score_result, comparison_json = score_structural(candidate, ground_truth)

    print_structural_report(score_result, comparison_json)

    print("── Comparison JSON ───────────────────────────────────")
    print(json.dumps(comparison_json, indent=4))
    print("══════════════════════════════════════════════════════\n")