import yaml
import argparse
import json
import io
import sys
from pathlib import Path
from datetime import datetime

from EvaluationScript.evaluation_general import score_general
from EvaluationScript.evaluation_section import score_sections, print_section_report
from EvaluationScript.evaluation_page import score_pages, print_page_report


# ── file loading ──────────────────────────────────────────────────────────────

def load_evaluation_pair(output_yml_path: str) -> tuple[dict, dict]:
    """
    Given a path like Output/ajil0120no1.yml,
    returns (candidate, ground_truth) as parsed dicts.
    """
    output_path = Path(output_yml_path).resolve()
    folder_name = output_path.stem
    project_root = output_path.parent.parent
    structure_path = project_root / "Input_Eval" / folder_name / "structure.yml"

    if not output_path.exists():
        raise FileNotFoundError(f"Output file not found: {output_path}")
    if not structure_path.exists():
        raise FileNotFoundError(f"Structure file not found: {structure_path}")

    with open(output_path, encoding="utf-8") as f:
        candidate = yaml.safe_load(f)
    with open(structure_path, encoding="utf-8") as f:
        ground_truth = yaml.safe_load(f)

    return candidate, ground_truth


# ── individual score runners ──────────────────────────────────────────────────

def run_general(candidate: dict, ground_truth: dict) -> tuple[dict, dict]:
    result_general, result_general_json = score_general(candidate, ground_truth)

    print("\n── General Score ─────────────────────────")
    for field, score in result_general["details"].items():
        bar = "█" * int(score / 5)
        print(f"  {field:<18} {score:>5.1f}  {bar}")
    print(f"\n  GENERAL SCORE:    {result_general['general_score']:.2f} / 100")
    print("──────────────────────────────────────────\n")

    return result_general, result_general_json


def run_sections(candidate: dict, ground_truth: dict) -> tuple[dict, dict]:
    score_result, comparison_json = score_sections(candidate, ground_truth)

    # Expose individual structural scores for the overall summary
    structural_summary = comparison_json.get("structural", {}).get("summary", {})
    score_result["volume_score"]   = structural_summary.get("volume_score", 0.0)
    score_result["issue_score"]    = structural_summary.get("issue_score", 0.0)
    score_result["contents_score"] = structural_summary.get("contents_score", 0.0)

    print_section_report(score_result, comparison_json)
    return score_result, comparison_json


def run_pages(candidate: dict, ground_truth: dict) -> tuple[dict, dict]:
    score_result_pages, comparison_json_pages = score_pages(candidate, ground_truth)
    print_page_report(score_result_pages, comparison_json_pages)
    return score_result_pages, comparison_json_pages


def run_overall(result_general: dict, score_result: dict, score_result_pages: dict) -> float:
    overall_score = round(
        (score_result["section_score"]    * 0.70) +
        (score_result_pages["page_score"] * 0.20) +
        (result_general["general_score"]  * 0.10),
        2
    )

    print("══════════════════════════════════════════════════════")
    print("  OVERALL EVALUATION SUMMARY")
    print("══════════════════════════════════════════════════════")
    print("""
  This score reflects the total pipeline accuracy for this journal
  compared against the human-edited ground truth (structure.yml).

  Weights:
    Section Score  — 70%  (article metadata, authors, DOI, URL, type)
    Page Score     — 20%  (page-to-article assignment, native labels)
    General Score  — 10%  (journal title, identifier, max, type, series)
""")
    print(f"  Section Score  (70%):    {score_result['section_score']:>6.2f} / 100")
    print(f"    ├─ Volume Score   (3.33%): {score_result['volume_score']:>6.2f} / 100")
    print(f"    ├─ Issue Score    (3.33%): {score_result['issue_score']:>6.2f} / 100")
    print(f"    ├─ TOC Score      (3.34%): {score_result['contents_score']:>6.2f} / 100") 
    print(f"    └─ Articles Score(90%): {score_result['articles_score']:>6.2f} / 100")
    print(f"  Page Score     (20%):    {score_result_pages['page_score']:>6.2f} / 100")
    print(f"  General Score  (10%):    {result_general['general_score']:>6.2f} / 100")
    print(f"\n  OVERALL SCORE:           {overall_score:>6.2f} / 100")
    print("══════════════════════════════════════════════════════\n")

    return overall_score


# ── save outputs ──────────────────────────────────────────────────────────────

def save_json(folder_name: str, datetime_str: str, eval_dir: Path,
              overall_score: float, result_general: dict, result_general_json: dict,
              score_result: dict, comparison_json: dict,
              score_result_pages: dict, comparison_json_pages: dict) -> Path:

    combined_json = {
        "meta": {
            "folder":        folder_name,
            "timestamp":     datetime_str,
            "overall_score": overall_score,
            "section_score": score_result["section_score"],
            "page_score":    score_result_pages["page_score"],
            "general_score": result_general["general_score"],
        },
        "general":  result_general_json,
        "sections": comparison_json,
        "pages":    comparison_json_pages,
    }

    json_path = eval_dir / f"{folder_name}_{datetime_str}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(combined_json, f, indent=4, ensure_ascii=False)

    return json_path


def save_report(folder_name: str, datetime_str: str, eval_dir: Path,
                result_general: dict, score_result: dict, comparison_json: dict,
                score_result_pages: dict, comparison_json_pages: dict,
                overall_score: float) -> Path:

    buffer = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buffer

    print("\n── General Score ─────────────────────────")
    for field, score in result_general["details"].items():
        bar = "█" * int(score / 5)
        print(f"  {field:<18} {score:>5.1f}  {bar}")
    print(f"\n  GENERAL SCORE:    {result_general['general_score']:.2f} / 100")
    print("──────────────────────────────────────────\n")

    print_section_report(score_result, comparison_json)
    print_page_report(score_result_pages, comparison_json_pages)

    print("══════════════════════════════════════════════════════")
    print("  OVERALL EVALUATION SUMMARY")
    print("══════════════════════════════════════════════════════")
    print("""
  Weights:
    Section Score  — 70%  (article metadata, authors, DOI, URL, type)
    Page Score     — 20%  (page-to-article assignment, native labels)
    General Score  — 10%  (journal title, identifier, max, type, series)
""")
    print(f"  Section Score  (70%):    {score_result['section_score']:>6.2f} / 100")
    print(f"    ├─ Volume Score   (3.33%): {score_result['volume_score']:>6.2f} / 100")
    print(f"    ├─ Issue Score    (3.33%): {score_result['issue_score']:>6.2f} / 100")
    print(f"    ├─ TOC Score      (3.34%): {score_result['contents_score']:>6.2f} / 100")
    print(f"    └─ Articles Score(90%): {score_result['articles_score']:>6.2f} / 100")
    print(f"  Page Score     (20%):    {score_result_pages['page_score']:>6.2f} / 100")
    print(f"  General Score  (10%):    {result_general['general_score']:>6.2f} / 100")
    print(f"\n  OVERALL SCORE:           {overall_score:>6.2f} / 100")

    sys.stdout = old_stdout
    report_text = buffer.getvalue()

    txt_path = eval_dir / f"{folder_name}_{datetime_str}.txt"
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    return txt_path


# ── main entry point ──────────────────────────────────────────────────────────

def evaluationScore(file: str) -> None:
    candidate, ground_truth = load_evaluation_pair(file)

    # Run all scores
    result_general, result_general_json = run_general(candidate, ground_truth)
    score_result,   comparison_json     = run_sections(candidate, ground_truth)
    score_result_pages, comparison_json_pages = run_pages(candidate, ground_truth)
    overall_score = run_overall(result_general, score_result, score_result_pages)

    # Save outputs
    folder_name  = Path(file).stem
    datetime_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    eval_dir     = Path(__file__).resolve().parent / "Evaluation" / folder_name
    eval_dir.mkdir(parents=True, exist_ok=True)

    json_path = save_json(
        folder_name, datetime_str, eval_dir,
        overall_score, result_general, result_general_json,
        score_result, comparison_json,
        score_result_pages, comparison_json_pages
    )

    txt_path = save_report(
        folder_name, datetime_str, eval_dir,
        result_general, score_result, comparison_json,
        score_result_pages, comparison_json_pages,
        overall_score
    )

    print(f"  JSON saved to:   {json_path}")
    print(f"  Report saved to: {txt_path}")
    print("══════════════════════════════════════════════════════\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output_yml", help="Path to Output/<name>.yml")
    args = parser.parse_args()

    evaluationScore(args.output_yml)