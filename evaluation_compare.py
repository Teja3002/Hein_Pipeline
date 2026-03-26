import json
import argparse
from pathlib import Path
from datetime import datetime


# ── constants ─────────────────────────────────────────────────────────────────

THRESHOLD_NOISE      = 1.0   # below this = no change
THRESHOLD_MINOR      = 5.0   # below this = minor change
# above THRESHOLD_MINOR = significant change


# ── helpers ───────────────────────────────────────────────────────────────────

def delta_tag(delta: float) -> str:
    if abs(delta) < THRESHOLD_NOISE:
        return "→ NO CHANGE"
    elif delta > 0:
        if delta >= THRESHOLD_MINOR:
            return f"▲ IMPROVED  (+{delta:.2f})"
        return f"△ improved  (+{delta:.2f})"
    else:
        if abs(delta) >= THRESHOLD_MINOR:
            return f"▼ REGRESSED ({delta:.2f})"
        return f"▽ regressed ({delta:.2f})"


def section_tag(delta: float) -> str:
    if abs(delta) < THRESHOLD_NOISE:
        return "→"
    elif delta > 0:
        return "▲" if delta >= THRESHOLD_MINOR else "△"
    else:
        return "▼" if abs(delta) >= THRESHOLD_MINOR else "▽"


def load_run(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_latest_runs(input_path: str, project_root: Path) -> tuple[str, str]:
    """Returns paths to the two most recent JSON runs for a journal."""
    
    # Accept both "ajil0120no1" and "Evaluation/ajil0120no1"
    input_path = Path(input_path)
    if input_path.is_absolute() or (project_root / input_path).exists():
        eval_dir = project_root / input_path
    else:
        eval_dir = project_root / "Evaluation" / input_path.name

    if not eval_dir.exists():
        raise FileNotFoundError(f"Evaluation folder not found: {eval_dir}")

    folder_name = eval_dir.name
    runs = sorted(eval_dir.glob(f"{folder_name}_*.json"), reverse=True)
    if len(runs) < 2:
        raise ValueError(f"Need at least 2 runs to compare, found {len(runs)}")

    return str(runs[1]), str(runs[0])


# ── section matching helper ───────────────────────────────────────────────────

def build_article_map(sections_json: dict) -> dict:
    """
    Builds {doi_or_title: section_data} from the matched sections
    in a comparison JSON, keyed by DOI if available else title.
    """
    article_map = {}
    for m in sections_json.get("articles", {}).get("matched", []):
        gt = m.get("gt", {})
        key = gt.get("doi") or gt.get("title") or m.get("gt_key")
        if key:
            article_map[key] = m
    return article_map


# ── comparison functions ──────────────────────────────────────────────────────

def compare_overall(run1: dict, run2: dict) -> dict:
    meta1 = run1["meta"]
    meta2 = run2["meta"]

    fields = ["overall_score", "section_score", "page_score", "general_score"]
    result = {}
    for f in fields:
        v1 = meta1.get(f, 0.0)
        v2 = meta2.get(f, 0.0)
        result[f] = {"run1": v1, "run2": v2, "delta": round(v2 - v1, 2)}

    return result


def compare_general(run1: dict, run2: dict) -> dict:
    g1 = run1.get("general", {})
    g2 = run2.get("general", {})

    fields = ["title", "identifier", "max", "type", "series"]
    result = {}
    for f in fields:
        v1 = g1.get(f, {}).get("score", 0.0)
        v2 = g2.get(f, {}).get("score", 0.0)
        result[f] = {
            "run1":       v1,
            "run2":       v2,
            "delta":      round(v2 - v1, 2),
            "run1_value": g1.get(f, {}).get("candidate", ""),
            "run2_value": g2.get(f, {}).get("candidate", ""),
            "gt_value":   g1.get(f, {}).get("ground_truth", ""),
        }

    return result


def compare_structural(run1: dict, run2: dict) -> dict:
    s1 = run1.get("sections", {}).get("structural", {})
    s2 = run2.get("sections", {}).get("structural", {})

    result = {}

    # Summary scores
    for sec_type in ["volume", "issue", "contents"]:
        sc1 = s1.get("summary", {}).get(f"{sec_type}_score", 0.0)
        sc2 = s2.get("summary", {}).get(f"{sec_type}_score", 0.0)
        result[f"{sec_type}_score"] = {"run1": sc1, "run2": sc2, "delta": round(sc2 - sc1, 2)}

    # Issue field detail
    issue_fields = ["type", "date", "citation", "description", "insection", "subject", "countries"]
    result["issue_fields"] = {}
    for f in issue_fields:
        v1 = s1.get("issue", {}).get(f, {}).get("score", 0.0) if isinstance(s1.get("issue", {}).get(f), dict) else 0.0
        v2 = s2.get("issue", {}).get(f, {}).get("score", 0.0) if isinstance(s2.get("issue", {}).get(f), dict) else 0.0
        result["issue_fields"][f] = {"run1": v1, "run2": v2, "delta": round(v2 - v1, 2)}

    # Contents field detail
    contents_fields = ["type", "title", "citation", "description", "insection"]
    result["contents_fields"] = {}
    for f in contents_fields:
        v1 = s1.get("contents", {}).get(f, {}).get("score", 0.0) if isinstance(s1.get("contents", {}).get(f), dict) else 0.0
        v2 = s2.get("contents", {}).get(f, {}).get("score", 0.0) if isinstance(s2.get("contents", {}).get(f), dict) else 0.0
        result["contents_fields"][f] = {"run1": v1, "run2": v2, "delta": round(v2 - v1, 2)}

    return result


def compare_articles(run1: dict, run2: dict) -> dict:
    map1 = build_article_map(run1.get("sections", {}))
    map2 = build_article_map(run2.get("sections", {}))

    # Summary stats
    sum1 = run1.get("sections", {}).get("articles", {}).get("summary", {})
    sum2 = run2.get("sections", {}).get("articles", {}).get("summary", {})

    result = {
        "summary": {
            "section_score":   {"run1": sum1.get("section_score", 0.0),   "run2": sum2.get("section_score", 0.0),   "delta": round(sum2.get("section_score", 0.0)   - sum1.get("section_score", 0.0), 2)},
            "matched_score":   {"run1": sum1.get("matched_score", 0.0),   "run2": sum2.get("matched_score", 0.0),   "delta": round(sum2.get("matched_score", 0.0)   - sum1.get("matched_score", 0.0), 2)},
            "matched_count":   {"run1": sum1.get("matched_count", 0),     "run2": sum2.get("matched_count", 0),     "delta": sum2.get("matched_count", 0)     - sum1.get("matched_count", 0)},
            "unmatched_count": {"run1": sum1.get("unmatched_count", 0),   "run2": sum2.get("unmatched_count", 0),   "delta": sum2.get("unmatched_count", 0)   - sum1.get("unmatched_count", 0)},
            "phantom_count":   {"run1": sum1.get("phantom_count", 0),     "run2": sum2.get("phantom_count", 0),     "delta": sum2.get("phantom_count", 0)     - sum1.get("phantom_count", 0)},
        },
        "per_article": [],
        "new_matches":    [],   # in run2 matched but not in run1
        "lost_matches":   [],   # in run1 matched but not in run2
        "new_phantoms":   [],   # phantom in run2 not in run1
        "resolved_phantoms": [], # was phantom in run1, gone in run2
    }

    all_keys = set(map1.keys()) | set(map2.keys())

    for key in all_keys:
        in1 = key in map1
        in2 = key in map2

        if in1 and in2:
            m1 = map1[key]
            m2 = map2[key]
            sc1 = m1.get("score", 0.0)
            sc2 = m2.get("score", 0.0)
            delta = round(sc2 - sc1, 2)

            field_deltas = {}
            for f in ["title", "creator", "doi", "external_url", "type"]:
                fsc1 = m1.get("fields", {}).get(f, 0.0)
                fsc2 = m2.get("fields", {}).get(f, 0.0)
                field_deltas[f] = {
                    "run1":  fsc1,
                    "run2":  fsc2,
                    "delta": round(fsc2 - fsc1, 2)
                }

            result["per_article"].append({
                "key":          key,
                "title":        m1.get("gt", {}).get("title", key),
                "match_type":   m2.get("match_type", ""),
                "run1_score":   sc1,
                "run2_score":   sc2,
                "delta":        delta,
                "fields":       field_deltas,
                "order_match":  {"run1": m1.get("order_match"), "run2": m2.get("order_match")},
            })

        elif in1 and not in2:
            result["lost_matches"].append({
                "key":   key,
                "title": map1[key].get("gt", {}).get("title", key),
                "score": map1[key].get("score", 0.0),
            })

        elif in2 and not in1:
            result["new_matches"].append({
                "key":   key,
                "title": map2[key].get("gt", {}).get("title", key),
                "score": map2[key].get("score", 0.0),
            })

    # Sort per_article by delta descending
    result["per_article"].sort(key=lambda x: x["delta"], reverse=True)

    return result


def compare_pages(run1: dict, run2: dict) -> dict:
    p1 = run1.get("pages", {}).get("summary", {})
    p2 = run2.get("pages", {}).get("summary", {})

    fields = [
        "page_score", "avg_matched_score",
        "native_match_rate", "section_match_rate", "chain_length_match_rate",
        "missing_count", "phantom_count",
    ]

    result = {"summary": {}}
    for f in fields:
        v1 = p1.get(f, 0.0)
        v2 = p2.get(f, 0.0)
        result["summary"][f] = {"run1": v1, "run2": v2, "delta": round(v2 - v1, 2)}

    # Per-page detail — pages that flipped
    pages1 = {str(p["id"]): p for p in run1.get("pages", {}).get("pages", [])}
    pages2 = {str(p["id"]): p for p in run2.get("pages", {}).get("pages", [])}

    flipped_correct  = []   # wrong in run1, correct in run2
    flipped_wrong    = []   # correct in run1, wrong in run2

    for page_id in set(pages1.keys()) & set(pages2.keys()):
        pg1 = pages1[page_id]
        pg2 = pages2[page_id]

        native_was_correct  = pg1.get("native", {}).get("match", False)
        native_now_correct  = pg2.get("native", {}).get("match", False)
        section_was_correct = pg1.get("primary_section", {}).get("match", False)
        section_now_correct = pg2.get("primary_section", {}).get("match", False)

        if (not native_was_correct and native_now_correct) or (not section_was_correct and section_now_correct):
            flipped_correct.append({
                "id":                  page_id,
                "native_fixed":        not native_was_correct and native_now_correct,
                "section_fixed":       not section_was_correct and section_now_correct,
                "native_run1":         pg1.get("native", {}).get("gt", ""),
                "native_run2":         pg2.get("native", {}).get("candidate", ""),
                "section_title_run2":  pg2.get("primary_section", {}).get("candidate_title", ""),
            })

        if (native_was_correct and not native_now_correct) or (section_was_correct and not section_now_correct):
            flipped_wrong.append({
                "id":                  page_id,
                "native_broken":       native_was_correct and not native_now_correct,
                "section_broken":      section_was_correct and not section_now_correct,
                "native_run1":         pg1.get("native", {}).get("candidate", ""),
                "native_run2":         pg2.get("native", {}).get("candidate", ""),
                "section_title_run1":  pg1.get("primary_section", {}).get("candidate_title", ""),
                "section_title_run2":  pg2.get("primary_section", {}).get("candidate_title", ""),
            })

    result["flipped_correct"] = flipped_correct
    result["flipped_wrong"]   = flipped_wrong

    return result


# ── print report ──────────────────────────────────────────────────────────────

def print_compare_report(run1: dict, run2: dict,
                         overall: dict, general: dict, structural: dict,
                         articles: dict, pages: dict) -> None:

    ts1 = run1["meta"]["timestamp"]
    ts2 = run2["meta"]["timestamp"]
    folder = run1["meta"]["folder"]

    print("\n══════════════════════════════════════════════════════")
    print("  EVALUATION COMPARISON REPORT")
    print("══════════════════════════════════════════════════════")
    print(f"""
  Journal:  {folder}
  Run 1:    {ts1}  (baseline)
  Run 2:    {ts2}  (new)

  Legend:
    ▲ IMPROVED   — score increased by 5+ points
    △ improved   — score increased by 1–5 points
    → NO CHANGE  — score within ±1 point
    ▽ regressed  — score decreased by 1–5 points
    ▼ REGRESSED  — score decreased by 5+ points
""")

    # ── Overall ──
    print("── Overall Scores ────────────────────────────────────\n")
    labels = {
        "overall_score": "Overall",
        "section_score": "Section",
        "page_score":    "Page",
        "general_score": "General",
    }
    for key, label in labels.items():
        o = overall[key]
        print(f"  {label:<10}  {o['run1']:>6.2f} → {o['run2']:>6.2f}   {delta_tag(o['delta'])}")

    # ── General ──
    print("\n── General Score Detail ──────────────────────────────\n")
    for field, data in general.items():
        tag = section_tag(data["delta"])
        changed = "" if abs(data["delta"]) < THRESHOLD_NOISE else f"  (candidate: '{data['run1_value']}' → '{data['run2_value']}')"
        print(f"  {field:<14} {data['run1']:>6.1f} → {data['run2']:>6.1f}  {tag}{changed}")

    # ── Structural ──
    print("\n── Structural Sections ───────────────────────────────\n")
    for sec in ["volume", "issue", "contents"]:
        d = structural[f"{sec}_score"]
        print(f"  {sec:<10}  {d['run1']:>6.2f} → {d['run2']:>6.2f}   {delta_tag(d['delta'])}")

    print("\n  Issue fields:")
    for field, d in structural["issue_fields"].items():
        tag = section_tag(d["delta"])
        print(f"    {field:<14} {d['run1']:>6.1f} → {d['run2']:>6.1f}  {tag}")

    print("\n  Contents fields:")
    for field, d in structural["contents_fields"].items():
        tag = section_tag(d["delta"])
        print(f"    {field:<14} {d['run1']:>6.1f} → {d['run2']:>6.1f}  {tag}")

    # ── Articles Summary ──
    print("\n── Article Sections Summary ──────────────────────────\n")
    s = articles["summary"]
    for key, label in [
        ("section_score",   "Section Score"),
        ("matched_score",   "Matched Score"),
        ("matched_count",   "Matched Count"),
        ("unmatched_count", "Unmatched"),
        ("phantom_count",   "Phantom"),
    ]:
        d = s[key]
        tag = section_tag(d["delta"]) if isinstance(d["delta"], float) else ("▲" if d["delta"] > 0 else "▼" if d["delta"] < 0 else "→")
        print(f"  {label:<18} {str(d['run1']):>6} → {str(d['run2']):>6}   {tag}")

    # ── Per Article ──
    print("\n── Per Article Comparison ────────────────────────────\n")
    print("  Format: [tag]  score_run1 → score_run2  title\n")

    improved   = [a for a in articles["per_article"] if a["delta"] >= THRESHOLD_NOISE]
    regressed  = [a for a in articles["per_article"] if a["delta"] <= -THRESHOLD_NOISE]
    no_change  = [a for a in articles["per_article"] if abs(a["delta"]) < THRESHOLD_NOISE]

    if improved:
        print(f"  ── Improved ({len(improved)}) ──")
        for a in improved:
            tag = "▲" if a["delta"] >= THRESHOLD_MINOR else "△"
            print(f"  [{tag}]  {a['run1_score']:>5.1f} → {a['run2_score']:>5.1f}  (+{a['delta']:.2f})  {a['title'][:55]}")
            for f, fd in a["fields"].items():
                if abs(fd["delta"]) >= THRESHOLD_NOISE:
                    ftag = "▲" if fd["delta"] > 0 else "▼"
                    print(f"         {ftag} {f:<14} {fd['run1']:>5.1f} → {fd['run2']:>5.1f}")

    if regressed:
        print(f"\n  ── Regressed ({len(regressed)}) ──")
        for a in regressed:
            tag = "▼" if a["delta"] <= -THRESHOLD_MINOR else "▽"
            print(f"  [{tag}]  {a['run1_score']:>5.1f} → {a['run2_score']:>5.1f}  ({a['delta']:.2f})  {a['title'][:55]}")
            for f, fd in a["fields"].items():
                if abs(fd["delta"]) >= THRESHOLD_NOISE:
                    ftag = "▲" if fd["delta"] > 0 else "▼"
                    print(f"         {ftag} {f:<14} {fd['run1']:>5.1f} → {fd['run2']:>5.1f}")

    if no_change:
        print(f"\n  ── No Change ({len(no_change)}) ──")
        for a in no_change:
            print(f"  [→]  {a['run1_score']:>5.1f} → {a['run2_score']:>5.1f}   {a['title'][:55]}")

    if articles["new_matches"]:
        print(f"\n  ── Newly Matched ({len(articles['new_matches'])}) ──")
        for a in articles["new_matches"]:
            print(f"  [+]  score={a['score']:.1f}  {a['title'][:55]}")

    if articles["lost_matches"]:
        print(f"\n  ── Lost Matches ({len(articles['lost_matches'])}) ──")
        for a in articles["lost_matches"]:
            print(f"  [-]  score={a['score']:.1f}  {a['title'][:55]}")

    # ── Pages ──
    print("\n── Page Score Detail ─────────────────────────────────\n")
    page_labels = {
        "page_score":              "Page Score",
        "avg_matched_score":       "Avg Matched",
        "native_match_rate":       "Native Match %",
        "section_match_rate":      "Section Match %",
        "chain_length_match_rate": "Chain Match %",
        "missing_count":           "Missing Pages",
        "phantom_count":           "Phantom Pages",
    }
    for key, label in page_labels.items():
        d = pages["summary"][key]
        tag = section_tag(d["delta"])
        print(f"  {label:<22} {str(d['run1']):>7} → {str(d['run2']):>7}   {tag}")

    if pages["flipped_correct"]:
        print(f"\n  ── Pages Fixed ({len(pages['flipped_correct'])}) — wrong in run1, correct in run2 ──")
        for p in pages["flipped_correct"][:15]:
            fixes = []
            if p["native_fixed"]:  fixes.append("native")
            if p["section_fixed"]: fixes.append("section")
            print(f"  page_id={p['id']}  fixed: {', '.join(fixes)}")
        if len(pages["flipped_correct"]) > 15:
            print(f"  ... and {len(pages['flipped_correct']) - 15} more")

    if pages["flipped_wrong"]:
        print(f"\n  ── Pages Broken ({len(pages['flipped_wrong'])}) — correct in run1, wrong in run2 ──")
        for p in pages["flipped_wrong"][:15]:
            breaks = []
            if p["native_broken"]:  breaks.append("native")
            if p["section_broken"]: breaks.append("section")
            print(f"  page_id={p['id']}  broken: {', '.join(breaks)}")
        if len(pages["flipped_wrong"]) > 15:
            print(f"  ... and {len(pages['flipped_wrong']) - 15} more")

    # ── Final Summary ──
    total_improved  = len(improved) + len(articles["new_matches"])
    total_regressed = len(regressed) + len(articles["lost_matches"])
    total_same      = len(no_change)

    print("\n── Summary ───────────────────────────────────────────\n")
    print(f"  Articles improved:   {total_improved}")
    print(f"  Articles no change:  {total_same}")
    print(f"  Articles regressed:  {total_regressed}")

    overall_delta = overall["overall_score"]["delta"]
    print(f"\n  Overall delta:  {'+' if overall_delta >= 0 else ''}{overall_delta:.2f}")

    if overall_delta >= THRESHOLD_MINOR:
        print("  Verdict: ▲ SIGNIFICANT IMPROVEMENT")
    elif overall_delta >= THRESHOLD_NOISE:
        print("  Verdict: △ Minor improvement")
    elif overall_delta <= -THRESHOLD_MINOR:
        print("  Verdict: ▼ SIGNIFICANT REGRESSION")
    elif overall_delta <= -THRESHOLD_NOISE:
        print("  Verdict: ▽ Minor regression")
    else:
        print("  Verdict: → No meaningful change")

    print("\n══════════════════════════════════════════════════════\n")


# ── save outputs ──────────────────────────────────────────────────────────────

def save_compare_outputs(folder_name: str, ts1: str, ts2: str,
                         project_root: Path,
                         overall: dict, general: dict, structural: dict,
                         articles: dict, pages: dict) -> None:

    eval_dir = project_root / "Evaluation" / folder_name
    eval_dir.mkdir(parents=True, exist_ok=True)

    compare_name = f"compare_{ts1}_vs_{ts2}"

    # Save JSON
    combined = {
        "meta": {
            "folder":   folder_name,
            "run1_ts":  ts1,
            "run2_ts":  ts2,
            "generated": datetime.now().strftime("%Y%m%d_%H%M%S"),
        },
        "overall":    overall,
        "general":    general,
        "structural": structural,
        "articles":   articles,
        "pages":      pages,
    }

    json_path = eval_dir / f"{compare_name}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=4, ensure_ascii=False)

    print(f"  Comparison JSON saved to: {json_path}")

    # Save text report by capturing stdout
    import io, sys
    buffer = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buffer

    # Re-run just the print — we already have all data
    run1_mock = {"meta": {"folder": folder_name, "timestamp": ts1}}
    run2_mock = {"meta": {"folder": folder_name, "timestamp": ts2}}
    print_compare_report(run1_mock, run2_mock, overall, general, structural, articles, pages)

    sys.stdout = old_stdout

    txt_path = eval_dir / f"{compare_name}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(buffer.getvalue())

    print(f"  Comparison report saved to: {txt_path}")


# ── main ──────────────────────────────────────────────────────────────────────

def compare(path1: str, path2: str) -> None:
    run1 = load_run(path1)
    run2 = load_run(path2)

    overall    = compare_overall(run1, run2)
    general    = compare_general(run1, run2)
    structural = compare_structural(run1, run2)
    articles   = compare_articles(run1, run2)
    pages      = compare_pages(run1, run2)

    print_compare_report(run1, run2, overall, general, structural, articles, pages)

    project_root = Path(path1).resolve().parent.parent.parent
    folder_name  = run1["meta"]["folder"]
    ts1          = run1["meta"]["timestamp"]
    ts2          = run2["meta"]["timestamp"]

    save_compare_outputs(folder_name, ts1, ts2, project_root,
                         overall, general, structural, articles, pages)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare two evaluation runs")
    parser.add_argument(
        "input",
        help="Either two JSON paths, or a journal folder name with --latest",
        nargs="+"
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Automatically use the 2 most recent runs for the given journal name"
    )
    args = parser.parse_args()

    if args.latest:
        if len(args.input) != 1:
            print("Usage with --latest: python evaluation_compare.py <journal_name> --latest")
            exit(1)
        project_root = Path(__file__).resolve().parent
        path1, path2 = get_latest_runs(args.input[0], project_root)
        print(f"  Comparing:\n    Run 1: {path1}\n    Run 2: {path2}\n")
    else:
        if len(args.input) != 2:
            print("Usage: python evaluation_compare.py <run1.json> <run2.json>")
            exit(1)
        path1, path2 = args.input[0], args.input[1] 

    compare(path1, path2) 


#     # Two specific runs
# python evaluation_compare.py Evaluation/ajil0120no1/run1.json Evaluation/ajil0120no1/run2.json

# # With folder path (tab-completable)
# python evaluation_compare.py Evaluation/ajil0120no1 --latest

# # With just name (also still works)
# python evaluation_compare.py ajil0120no1 --latest

# # Two most recent runs automatically
# python evaluation_compare.py ajil0120no1 --latest
# ```

# Output saved to:
# ```
# Evaluation/ajil0120no1/
#   compare_20260326_040200_vs_20260326_041601.json
#   compare_20260326_040200_vs_20260326_041601.txt