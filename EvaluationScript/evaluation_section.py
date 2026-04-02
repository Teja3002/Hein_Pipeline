import json
from difflib import SequenceMatcher
from EvaluationScript.evaluation_structural import score_structural, print_structural_report


# ── constants ─────────────────────────────────────────────────────────────────

STRUCTURAL_TYPES = {"volume", "issue", "contents"}
MATCH_THRESHOLD  = 0.85


# ── helpers ───────────────────────────────────────────────────────────────────

def similarity(a, b) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def fuzzy_score(a: str, b: str) -> float:
    return similarity(a, b)


def exact_score(a, b) -> float:
    return 1.0 if str(a).strip().lower() == str(b).strip().lower() else 0.0


def set_overlap_score(list_a: list, list_b: list) -> float:
    if not list_a and not list_b:
        return 1.0
    if not list_a or not list_b:
        return 0.0
    set_a = {s.lower().strip() for s in list_a if s}
    set_b = {s.lower().strip() for s in list_b if s}
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


def fuzzy_set_overlap_score(list_a: list, list_b: list) -> float:
    """
    Fuzzy overlap between two lists of creator names.
    Each name in list_a is matched to the best scoring name in list_b.
    """
    if not list_a and not list_b:
        return 1.0
    if not list_a or not list_b:
        return 0.0

    clean_a = [s.lower().strip() for s in list_a if s]
    clean_b = [s.lower().strip() for s in list_b if s]

    if not clean_a and not clean_b:
        return 1.0
    if not clean_a or not clean_b:
        return 0.0

    total_score = 0.0
    for name_a in clean_a:
        best = max(similarity(name_a, name_b) for name_b in clean_b)
        total_score += best

    return total_score / max(len(clean_a), len(clean_b))


# ── section extraction ────────────────────────────────────────────────────────

def get_article_sections(yml: dict) -> dict:
    """Returns all non-structural sections keyed by section ID."""
    return {
        k: v for k, v in yml.get("sections", {}).items()
        if v.get("type") not in STRUCTURAL_TYPES
    }


def get_issue_ids(yml: dict) -> list[str]:
    """Returns all section IDs that are of type issue, in order."""
    return [
        k for k, v in yml.get("sections", {}).items()
        if v.get("type") == "issue"
    ]


def get_articles_by_issue(yml: dict) -> dict:
    """
    Groups article sections by their insection value (issue ID).
    Returns {issue_id: {sec_id: section_data}}.
    Falls back to a single "_all" group if no insection fields found.
    """
    all_articles = get_article_sections(yml)

    # Check if insection is available
    has_insection = any(
        v.get("insection") is not None
        for v in all_articles.values()
    )

    if not has_insection:
        return {"_all": all_articles}

    grouped = {}
    for sec_id, sec in all_articles.items():
        issue_id = str(sec.get("insection", "_unknown"))
        if issue_id not in grouped:
            grouped[issue_id] = {}
        grouped[issue_id][sec_id] = sec

    return grouped


# ══════════════════════════════════════════════════════
# PART 1 — ARTICLE MATCHING & SCORING
# ══════════════════════════════════════════════════════

def match_sections(gt_sections: dict, cand_sections: dict):
    """
    Matches GT sections to candidate sections by DOI then title.
    Returns (matched list, phantom keys list).
    """
    matched = []
    used_cand_keys = set()

    # Pass 1 — DOI exact match
    for gt_key, gt_sec in gt_sections.items():
        gt_doi = (gt_sec.get("doi") or "").lower().strip()
        if not gt_doi:
            continue
        for cand_key, cand_sec in cand_sections.items():
            if cand_key in used_cand_keys:
                continue
            cand_doi = (cand_sec.get("doi") or "").lower().strip()
            if gt_doi and gt_doi == cand_doi:
                matched.append({
                    "gt_key":           gt_key,
                    "gt_section":       gt_sec,
                    "cand_key":         cand_key,
                    "cand_section":     cand_sec,
                    "match_type":       "doi",
                    "title_similarity": round(similarity(
                        gt_sec.get("title", ""),
                        cand_sec.get("title", "")
                    ), 3)
                })
                used_cand_keys.add(cand_key)
                break

    matched_gt_keys = {m["gt_key"] for m in matched}

    # Pass 2 — Title fuzzy match for remaining
    for gt_key, gt_sec in gt_sections.items():
        if gt_key in matched_gt_keys:
            continue
        gt_title = (gt_sec.get("title") or "").strip()
        if not gt_title:
            continue

        best_score    = 0.0
        best_cand_key = None
        best_cand_sec = None

        for cand_key, cand_sec in cand_sections.items():
            if cand_key in used_cand_keys:
                continue
            cand_title      = (cand_sec.get("title") or "").strip()
            score           = similarity(gt_title, cand_title)
            contains        = (gt_title.lower() in cand_title.lower()) or (cand_title.lower() in gt_title.lower())
            effective_score = max(score, 0.90 if contains else 0.0)

            if effective_score > best_score:
                best_score    = effective_score
                best_cand_key = cand_key
                best_cand_sec = cand_sec

        if best_score >= MATCH_THRESHOLD and best_cand_key:
            matched.append({
                "gt_key":           gt_key,
                "gt_section":       gt_sec,
                "cand_key":         best_cand_key,
                "cand_section":     best_cand_sec,
                "match_type":       "title",
                "title_similarity": round(best_score, 3)
            })
            used_cand_keys.add(best_cand_key)
            matched_gt_keys.add(gt_key)
        else:
            matched.append({
                "gt_key":           gt_key,
                "gt_section":       gt_sec,
                "cand_key":         None,
                "cand_section":     None,
                "match_type":       "unmatched",
                "title_similarity": round(best_score, 3)
            })

    phantom_keys = [k for k in cand_sections if k not in used_cand_keys]
    return matched, phantom_keys


FIELD_WEIGHTS = {
    "title":   0.40,
    "creator": 0.40,
    "doi":     0.20,
}


def score_section_pair(gt_sec: dict, cand_sec: dict) -> dict:
    title_raw = fuzzy_score(gt_sec.get("title", ""), cand_sec.get("title", ""))

    # 95%+ title similarity treated as 100 — typos are acceptable
    title_score = 1.0 if title_raw >= 0.95 else title_raw

    fields = {
        "title":   title_score,
        "creator": fuzzy_set_overlap_score(gt_sec.get("creator", []), cand_sec.get("creator", [])),
        "doi":     exact_score(gt_sec.get("doi", ""),          cand_sec.get("doi", "")),
    }

    weighted = sum(fields[f] * FIELD_WEIGHTS[f] for f in FIELD_WEIGHTS)

    return {
        "fields":        {k: round(v * 100, 1) for k, v in fields.items()},
        "section_score": round(weighted * 100, 2)
    }


# ══════════════════════════════════════════════════════
# PART 2 — ARTICLE SCORING WITH PER-ISSUE BREAKDOWN
# ══════════════════════════════════════════════════════

def score_articles(candidate: dict, ground_truth: dict) -> tuple[dict, dict]:
    """
    Scores articles with per-issue breakdown.
    Final score is based on total articles, not average of issue scores.
    Falls back to global matching if insection not available in candidate.
    """
    gt_by_issue   = get_articles_by_issue(ground_truth)
    cand_by_issue = get_articles_by_issue(candidate)

    gt_all_articles   = get_article_sections(ground_truth)
    cand_all_articles = get_article_sections(candidate)

    gt_total   = len(gt_all_articles)
    cand_total = len(cand_all_articles)

    if gt_total == 0:
        return {"section_score": 0.0}, {}

    # Check if per-issue matching is possible
    cand_has_insection = "_all" not in cand_by_issue
    gt_has_insection   = "_all" not in gt_by_issue

    per_issue_results = []
    all_scored_pairs  = []
    all_unmatched     = []
    all_phantom_keys  = []

    if gt_has_insection and cand_has_insection:
        # ── Per-issue matching ──
        gt_issue_ids = list(gt_by_issue.keys())

        for issue_id in gt_issue_ids:
            gt_issue_articles   = gt_by_issue.get(issue_id, {})
            cand_issue_articles = cand_by_issue.get(issue_id, {})

            matches, phantom_keys = match_sections(gt_issue_articles, cand_issue_articles)

            matched_pairs = [m for m in matches if m["match_type"] != "unmatched"]
            unmatched     = [m for m in matches if m["match_type"] == "unmatched"]

            scored_pairs = []
            for m in matched_pairs:
                pair_score = score_section_pair(m["gt_section"], m["cand_section"])
                scored_pairs.append({**m, **pair_score})

            all_scored_pairs.extend(scored_pairs)
            all_unmatched.extend(unmatched)
            all_phantom_keys.extend(phantom_keys)

            # Per-issue summary
            issue_matched_score = (
                sum(p["section_score"] for p in scored_pairs) / len(scored_pairs)
                if scored_pairs else 0.0
            )

            per_issue_results.append({
                "issue_id":      issue_id,
                "total_gt":      len(gt_issue_articles),
                "total_cand":    len(cand_issue_articles),
                "matched_count": len(matched_pairs),
                "unmatched_count": len(unmatched),
                "phantom_count": len(phantom_keys),
                "matched_score": round(issue_matched_score, 2),
                "articles":      scored_pairs,
                "unmatched_gt":  unmatched,
                "phantom":       phantom_keys,
            })

    else:
        # ── Global fallback matching ──
        matches, phantom_keys = match_sections(gt_all_articles, cand_all_articles)

        matched_pairs = [m for m in matches if m["match_type"] != "unmatched"]
        unmatched     = [m for m in matches if m["match_type"] == "unmatched"]

        for m in matched_pairs:
            pair_score = score_section_pair(m["gt_section"], m["cand_section"])
            all_scored_pairs.append({**m, **pair_score})

        all_unmatched.extend(unmatched)
        all_phantom_keys.extend(phantom_keys)

        per_issue_results.append({
            "issue_id":        "_all",
            "note":            "insection not available — global matching used",
            "total_gt":        gt_total,
            "total_cand":      cand_total,
            "matched_count":   len(matched_pairs),
            "unmatched_count": len(unmatched),
            "phantom_count":   len(phantom_keys),
            "matched_score":   round(
                sum(p["section_score"] for p in all_scored_pairs) / len(all_scored_pairs)
                if all_scored_pairs else 0.0, 2
            ),
            "articles":        all_scored_pairs,
            "unmatched_gt":    unmatched,
            "phantom":         phantom_keys,
        })

    # ── Final score based on ALL articles, not average of issue scores ──
    total_matched  = len(all_scored_pairs)
    total_unmatched = len(all_unmatched)
    total_phantom  = len(all_phantom_keys)

    matched_score = (
        sum(p["section_score"] for p in all_scored_pairs) / total_matched
        if total_matched else 0.0
    )

    missed_penalty  = (total_unmatched / gt_total) * 100
    phantom_penalty = (total_phantom   / gt_total) * 50
    final_score     = max(0.0, matched_score - missed_penalty - phantom_penalty)

    score_result = {
        "section_score":        round(final_score, 2),
        "matched_score":        round(matched_score, 2),
        "missed_penalty":       round(missed_penalty, 2),
        "phantom_penalty":      round(phantom_penalty, 2),
        "total_gt":             gt_total,
        "total_cand":           cand_total,
        "matched_count":        total_matched,
        "unmatched_count":      total_unmatched,
        "phantom_count":        total_phantom,
        "per_issue_available":  cand_has_insection and gt_has_insection,
        "total_issues":         len(per_issue_results),
    }

    comparison_json = {
        "summary":      score_result,
        "per_issue":    per_issue_results,
        "matched":      [
            {
                "gt_key":           m["gt_key"],
                "cand_key":         m["cand_key"],
                "match_type":       m["match_type"],
                "title_similarity": m["title_similarity"],
                "order_match":      m["gt_key"] == m["cand_key"],
                "score":            m["section_score"],
                "fields":           m["fields"],
                "gt": {
                    "title":   m["gt_section"].get("title", ""),
                    "creator": m["gt_section"].get("creator", []),
                    "doi":     m["gt_section"].get("doi", ""),
                    "insection": m["gt_section"].get("insection", None),
                },
                "candidate": {
                    "title":   m["cand_section"].get("title", ""),
                    "creator": m["cand_section"].get("creator", []),
                    "doi":     m["cand_section"].get("doi", ""),
                    "insection": m["cand_section"].get("insection", None), 
                },
            }
            for m in all_scored_pairs
        ],
        "unmatched_gt": [
            {
                "gt_key":          m["gt_key"],
                "title":           m["gt_section"].get("title", ""),
                "doi":             m["gt_section"].get("doi", ""),
                "best_similarity": m["title_similarity"],
            }
            for m in all_unmatched
        ],
        "phantom_candidate": [
            {
                "cand_key": k,
                "title":    cand_all_articles[k].get("title", "") if k in cand_all_articles else "",
                "doi":      cand_all_articles[k].get("doi", "")   if k in cand_all_articles else "",
            }
            for k in all_phantom_keys
        ]
    }

    return score_result, comparison_json


# ══════════════════════════════════════════════════════
# PART 3 — COMBINED SECTION SCORE
# ══════════════════════════════════════════════════════

def score_sections(candidate: dict, ground_truth: dict) -> tuple[dict, dict]:
    structural_result, structural_json = score_structural(candidate, ground_truth)
    articles_result,   articles_json   = score_articles(candidate, ground_truth)

    combined = (
        structural_result["structural_score"] * 0.10 +
        articles_result["section_score"]      * 0.90
    )

    score_result = {
        "section_score":    round(combined, 2),
        "structural_score": structural_result["structural_score"],
        "articles_score":   articles_result["section_score"],
    }

    comparison_json = {
        "summary":    score_result,
        "structural": structural_json,
        "articles":   articles_json,
    }

    return score_result, comparison_json


# ══════════════════════════════════════════════════════
# PRINT REPORTS
# ══════════════════════════════════════════════════════

def print_articles_report(articles_json: dict, score_result: dict) -> None:
    print("\n══════════════════════════════════════════════════════")
    print("  ARTICLE SECTIONS REPORT")
    print("══════════════════════════════════════════════════════")
    print("""
  Compares pipeline-generated article sections against the
  human-edited ground truth. Matched first by DOI (exact),
  then by title similarity. Scored on: title, creators, DOI.

  Final score is based on all articles combined, not per-issue average.
""")

    s = articles_json["summary"]

    # ── Per-issue breakdown ──
    if s.get("per_issue_available") and s.get("total_issues", 0) > 1:
        print("── Per-Issue Breakdown ───────────────────────────────\n")
        for iss in articles_json["per_issue"]:
            label = iss["issue_id"] if iss["issue_id"] != "_all" else "All Issues"
            note  = f"  ({iss['note']})" if iss.get("note") else ""
            print(f"  Issue {label}{note}")
            print(f"    GT articles:   {iss['total_gt']}")
            print(f"    Matched:       {iss['matched_count']}")
            print(f"    Unmatched:     {iss['unmatched_count']}")
            print(f"    Phantom:       {iss['phantom_count']}")
            print(f"    Matched Score: {iss['matched_score']:>6.2f} / 100\n")
    elif not s.get("per_issue_available"):
        print("  ⚠ Per-issue breakdown not available — insection field missing in candidate")
        print("    Using global matching across all articles.\n")

    # ── Overall coverage ──
    print("── Coverage (All Articles) ───────────────────────────")
    print(f"  Ground truth articles:   {s['total_gt']}")
    print(f"  Candidate articles:      {s['total_cand']}")
    print(f"  Successfully matched:    {s['matched_count']}  (articles found in both)")
    print(f"  Unmatched (missed):      {s['unmatched_count']}  (in GT but not in candidate)")
    print(f"  Phantom (extra):         {s['phantom_count']}  (in candidate but not in GT)")

    print("\n── Score Breakdown ───────────────────────────────────")
    print("""  Matched Score   — average field accuracy across all matched pairs
  Missed Penalty  — deducted for each GT article the pipeline missed
  Phantom Penalty — lightly deducted for invented articles (half weight)
""")
    print(f"  Matched Score:    {s['matched_score']:>6.2f} / 100")
    print(f"  Missed Penalty:  -{s['missed_penalty']:>6.2f}")
    print(f"  Phantom Penalty: -{s['phantom_penalty']:>6.2f}")
    print(f"\n  ARTICLES SCORE:   {score_result['articles_score']:>6.2f} / 100")

    print("\n── Matched Articles ──────────────────────────────────")
    print("  Format: [match type]  score  title")
    print("  Match type: 'doi' = matched by DOI, 'title' = matched by title similarity")
    print("  ⚠ order diff = section exists but appears at a different position\n")
    for m in articles_json["matched"]:
        order_tag = "          " if m["order_match"] else "⚠ order diff"
        print(f"  [{m['match_type']:<5}] {order_tag}  {m['score']:>5.1f}/100  {m['gt']['title'][:55]}")

    if articles_json["unmatched_gt"]:
        print("\n── Missed Articles (in GT, not found in candidate) ───")
        print("  These are real articles the pipeline failed to detect.\n")
        for u in articles_json["unmatched_gt"]:
            print(f"  ✗ {u['title'][:60]}")
            print(f"      best similarity: {u['best_similarity']:.0%}")

    if articles_json["phantom_candidate"]:
        print("\n── Phantom Articles (in candidate, not in GT) ────────")
        print("  These sections were generated by the pipeline but have")
        print("  no corresponding article in the ground truth.\n")
        for p in articles_json["phantom_candidate"]:
            print(f"  ? {p['title'][:60]}")

    print("\n══════════════════════════════════════════════════════\n")


def print_section_report(score_result: dict, comparison_json: dict) -> None:
    print_structural_report(comparison_json["structural"]["summary"], comparison_json["structural"])
    print_articles_report(comparison_json["articles"], score_result)

    print("══════════════════════════════════════════════════════")
    print("  SECTION SCORE SUMMARY")
    print("══════════════════════════════════════════════════════")
    print(f"  Structural Score (10%):  {score_result['structural_score']:>6.2f} / 100")
    print(f"  Articles Score   (90%):  {score_result['articles_score']:>6.2f} / 100")
    print(f"\n  SECTION SCORE:           {score_result['section_score']:>6.2f} / 100")
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

    parser = argparse.ArgumentParser(description="Section Score Evaluator")
    parser.add_argument("output_yml", help="Path to Output/<n>.yml")
    args = parser.parse_args()

    candidate, ground_truth = _load_pair(args.output_yml)
    score_result, comparison_json = score_sections(candidate, ground_truth)

    print_section_report(score_result, comparison_json)

    print("── Comparison JSON ───────────────────────────────────")
    print(json.dumps(comparison_json, indent=4))
    print("══════════════════════════════════════════════════════\n")