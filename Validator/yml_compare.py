#!/usr/bin/env python3
"""
Validate generated YML files in the root Output folder against
HeinData/After/<journal>/structure.yml and save comparison reports
into Validator/results.
"""

from __future__ import annotations

import json
from pathlib import Path
import unicodedata

import yaml


PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "Output"
AFTER_DIR = PROJECT_ROOT / "HeinData" / "After"
RESULTS_DIR = PROJECT_ROOT / "Validator" / "results"

ARTICLE_TYPES = {"article", "notes", "reviews"}


def load_articles(filepath: Path) -> dict[str, dict[str, object]]:
    with filepath.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}

    sections = data.get("sections") or {}
    articles: dict[str, dict[str, object]] = {}

    for section_id, section in sections.items():
        section_type = section.get("type")
        if section_type and section_type not in ARTICLE_TYPES:
            continue

        articles[str(section_id)] = {
            "title": (section.get("title") or "").strip(),
            "authors": [str(author).strip() for author in (section.get("creator") or []) if str(author).strip()],
            "type": section_type,
            "doi": str(section.get("doi") or "").strip(),
        }

    return articles


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.lower().split())


def normalize_author(value: object) -> str:
    normalized = normalize_text(value)
    parts = [part for part in normalized.replace(",", " ").split() if part]
    return " ".join(sorted(parts))


def compare_pair(reference_path: Path, generated_path: Path) -> dict[str, object]:
    reference_articles = load_articles(reference_path)
    generated_articles = load_articles(generated_path)

    reference_titles = {
        normalize_text(article["title"]): section_id
        for section_id, article in reference_articles.items()
        if normalize_text(article["title"])
    }
    generated_titles = {
        normalize_text(article["title"]): section_id
        for section_id, article in generated_articles.items()
        if normalize_text(article["title"])
    }

    matched_titles = sorted(set(reference_titles) & set(generated_titles))
    missing_titles = sorted(set(reference_titles) - set(generated_titles))
    extra_titles = sorted(set(generated_titles) - set(reference_titles))

    author_mismatches: list[dict[str, object]] = []
    doi_mismatches: list[dict[str, object]] = []

    for normalized_title in matched_titles:
        reference_section_id = reference_titles[normalized_title]
        generated_section_id = generated_titles[normalized_title]

        reference_article = reference_articles[reference_section_id]
        generated_article = generated_articles[generated_section_id]

        reference_authors = [normalize_author(author) for author in reference_article["authors"]]
        generated_authors = [normalize_author(author) for author in generated_article["authors"]]

        if sorted(reference_authors) != sorted(generated_authors):
            author_mismatches.append(
                {
                    "title": reference_article["title"],
                    "reference": reference_article["authors"],
                    "generated": generated_article["authors"],
                }
            )

        if normalize_text(reference_article["doi"]) != normalize_text(generated_article["doi"]):
            doi_mismatches.append(
                {
                    "title": reference_article["title"],
                    "reference": reference_article["doi"],
                    "generated": generated_article["doi"],
                }
            )

    total_issues = (
        len(missing_titles)
        + len(extra_titles)
        + len(author_mismatches)
        + len(doi_mismatches)
    )

    if len(reference_articles) != len(generated_articles):
        total_issues += 1

    return {
        "reference_file": str(reference_path),
        "generated_file": str(generated_path),
        "reference_count": len(reference_articles),
        "generated_count": len(generated_articles),
        "matched_title_count": len(matched_titles),
        "missing_titles": [
            {
                "section_id": reference_titles[title],
                "title": reference_articles[reference_titles[title]]["title"],
            }
            for title in missing_titles
        ],
        "extra_titles": [
            {
                "section_id": generated_titles[title],
                "title": generated_articles[generated_titles[title]]["title"],
            }
            for title in extra_titles
        ],
        "author_mismatches": author_mismatches,
        "doi_mismatches": doi_mismatches,
        "result": "PASS" if total_issues == 0 else "FAIL",
        "issue_count": total_issues,
    }


def validate_output_folder() -> dict[str, object]:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    summary: dict[str, object] = {
        "output_dir": str(OUTPUT_DIR),
        "after_dir": str(AFTER_DIR),
        "results_dir": str(RESULTS_DIR),
        "processed": 0,
        "passed": 0,
        "failed": 0,
        "missing_reference": [],
        "reports": [],
    }

    for generated_path in sorted(OUTPUT_DIR.glob("*.yml")):
        journal_name = generated_path.stem
        reference_path = AFTER_DIR / journal_name / "structure.yml"
        report_path = RESULTS_DIR / f"{journal_name}.json"

        if not reference_path.exists():
            missing_entry = {
                "journal": journal_name,
                "generated_file": str(generated_path),
                "expected_reference": str(reference_path),
                "result": "MISSING_REFERENCE",
            }
            summary["missing_reference"].append(missing_entry)
            report_path.write_text(json.dumps(missing_entry, indent=2), encoding="utf-8")
            summary["reports"].append(str(report_path))
            continue

        comparison = compare_pair(reference_path, generated_path)
        comparison["journal"] = journal_name

        report_path.write_text(json.dumps(comparison, indent=2), encoding="utf-8")

        summary["processed"] += 1
        summary["reports"].append(str(report_path))

        if comparison["result"] == "PASS":
            summary["passed"] += 1
        else:
            summary["failed"] += 1

    summary_path = RESULTS_DIR / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return summary


def main() -> None:
    summary = validate_output_folder()
    print(f"Processed: {summary['processed']}")
    print(f"Passed   : {summary['passed']}")
    print(f"Failed   : {summary['failed']}")
    print(f"Missing  : {len(summary['missing_reference'])}")
    print(f"Results  : {RESULTS_DIR}")


if __name__ == "__main__":
    main()
