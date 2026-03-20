import json
import logging
import re
import sys
import unicodedata
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Utilities.app_logging import setup_logging

COMBINATOR_DIR = PROJECT_ROOT / "Combinator"
RESULTS_DIR = COMBINATOR_DIR / "results"
OUTPUT_DIR = COMBINATOR_DIR / "output"

SOURCE_FILES = {
    "crossref": PROJECT_ROOT / "CrossRef" / "results",
    "webscraper": PROJECT_ROOT / "Webscraper" / "results",
    "llm": PROJECT_ROOT / "LLM" / "results",
}

SOURCE_PRIORITY = ["crossref", "webscraper", "llm"]
TOP_LEVEL_FIELDS = ["journalName", "title", "volume", "date"]
PAGE_FIELDS = ["id", "native", "section"]
SECTION_FIELDS = [
    "page",
    "startFile",
    "endFile",
    "title",
    "citation",
    "description",
    "doi",
    "external_url",
    "authors",
]
FINAL_SECTION_FIELDS = [
    "title",
    "citation",
    "description",
    "doi",
    "external_url",
    "authors",
]


def ensure_dirs():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path):
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def write_json(path, payload):
    with path.open("w", encoding="utf-8") as file_obj:
        json.dump(payload, file_obj, indent=2, ensure_ascii=False)


def strip_accents(value):
    normalized = unicodedata.normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii")


def normalize_text(value):
    if value is None:
        return ""

    text = strip_accents(str(value)).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def normalize_author(value):
    tokens = normalize_text(value).split()
    return " ".join(sorted(tokens))


def normalize_authors(values):
    if not values:
        return []

    normalized = [normalize_author(value) for value in values if normalize_author(value)]
    return sorted(normalized)


def canonical_value(field_name, value):
    if field_name == "authors":
        return tuple(normalize_authors(value))

    if isinstance(value, list):
        normalized = [normalize_text(item) for item in value if normalize_text(item)]
        return tuple(sorted(normalized))

    if value is None:
        return ""

    if isinstance(value, (int, float)):
        return str(value).strip()

    return normalize_text(value)


def has_value(value):
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(has_value(item) for item in value)
    return True


def values_equal(field_name, left, right):
    return canonical_value(field_name, left) == canonical_value(field_name, right)


def compare_titles(left, right):
    left_normalized = normalize_text(left)
    right_normalized = normalize_text(right)

    if not left_normalized or not right_normalized:
        return False

    if left_normalized == right_normalized:
        return True

    ratio = SequenceMatcher(None, left_normalized, right_normalized).ratio()
    return ratio >= 0.88


def compare_section_records(left, right):
    left_doi = canonical_value("doi", left.get("doi"))
    right_doi = canonical_value("doi", right.get("doi"))

    if left_doi and right_doi and left_doi == right_doi:
        return True

    if compare_titles(left.get("title"), right.get("title")):
        return True

    left_authors = left.get("authors") or []
    right_authors = right.get("authors") or []
    if left_authors and right_authors:
        left_set = set(normalize_authors(left_authors))
        right_set = set(normalize_authors(right_authors))
        if left_set == right_set and left_set:
            return True

    return False


def source_sections(payload):
    sections = payload.get("sections", {}) if isinstance(payload, dict) else {}
    ordered = []
    for section_id, section_data in sections.items():
        ordered.append(
            {
                "source_section_id": str(section_id),
                "data": deepcopy(section_data or {}),
            }
        )
    return ordered


def source_pages(payload):
    pages = payload.get("pages", []) if isinstance(payload, dict) else []
    ordered = []
    for page_data in pages:
        ordered.append(deepcopy(page_data or {}))
    return ordered


def empty_section():
    return {field: [] if field == "authors" else None for field in SECTION_FIELDS}


def empty_group():
    return {
        "crossref": None,
        "webscraper": None,
        "llm": None,
    }


def empty_page_group():
    return {
        "crossref": None,
        "webscraper": None,
        "llm": None,
    }


def compare_page_records(left, right):
    left_id = canonical_value("id", left.get("id"))
    right_id = canonical_value("id", right.get("id"))
    if left_id and right_id and left_id == right_id:
        return True

    left_native = canonical_value("native", left.get("native"))
    right_native = canonical_value("native", right.get("native"))
    if left_native and right_native and left_native == right_native:
        left_section = canonical_value("section", left.get("section"))
        right_section = canonical_value("section", right.get("section"))
        if left_section == right_section:
            return True

    return False


def match_page_group(groups, record):
    for group in groups:
        for source_name in SOURCE_PRIORITY:
            candidate = group.get(source_name)
            if candidate and compare_page_records(candidate, record):
                return group
    return None


def merge_page_groups(payloads):
    groups = []

    for source_name in SOURCE_PRIORITY:
        for page_record in source_pages(payloads[source_name]):
            group = match_page_group(groups, page_record)
            if group is None:
                group = empty_page_group()
                groups.append(group)
            group[source_name] = deepcopy(page_record)

    return groups


def match_group(groups, record):
    for group in groups:
        for source_name in SOURCE_PRIORITY:
            candidate = group.get(source_name)
            if candidate and compare_section_records(candidate, record):
                return group
    return None


def merge_groups(payloads):
    groups = []

    for source_name in SOURCE_PRIORITY:
        for section_record in source_sections(payloads[source_name]):
            record = section_record["data"]
            group = match_group(groups, record)
            if group is None:
                group = empty_group()
                groups.append(group)
            group[source_name] = deepcopy(record)

    return groups


def choose_value(field_name, values_by_source):
    for source_name in SOURCE_PRIORITY:
        value = values_by_source.get(source_name)
        if has_value(value):
            return deepcopy(value), source_name

    return ([] if field_name == "authors" else ""), None


def build_field_audit(field_name, values_by_source):
    distinct_values = []
    seen = set()

    for source_name in SOURCE_PRIORITY:
        value = values_by_source.get(source_name)
        if not has_value(value):
            continue

        canonical = canonical_value(field_name, value)
        if canonical not in seen:
            seen.add(canonical)
            distinct_values.append(source_name)

    chosen_value, chosen_source = choose_value(field_name, values_by_source)
    all_three_present = all(has_value(values_by_source.get(source_name)) for source_name in SOURCE_PRIORITY)

    return {
        "chosen_source": chosen_source,
        "values": deepcopy(values_by_source),
        "conflict": len(distinct_values) > 1,
        "all_three_different": all_three_present and len(distinct_values) == 3,
    }, chosen_value


def build_top_level(payloads):
    top_level = {}
    audit = {}

    for field_name in TOP_LEVEL_FIELDS:
        values_by_source = {
            source_name: payloads[source_name].get(field_name)
            for source_name in SOURCE_PRIORITY
        }
        field_audit, chosen_value = build_field_audit(field_name, values_by_source)
        top_level[field_name] = chosen_value
        audit[field_name] = field_audit

    return top_level, audit


def page_sort_key(page_item):
    page_id = page_item.get("id")
    native = page_item.get("native") or ""

    if isinstance(page_id, int):
        return (0, page_id, normalize_text(native))

    if isinstance(page_id, str) and page_id.isdigit():
        return (0, int(page_id), normalize_text(native))

    return (1, normalize_text(str(page_id)), normalize_text(native))


def build_pages(page_groups):
    merged_pages = []
    page_output = {}

    for index, group in enumerate(page_groups, start=1):
        merged_page = {}
        field_audit = {}

        for field_name in PAGE_FIELDS:
            values_by_source = {
                source_name: (group[source_name] or {}).get(field_name)
                for source_name in SOURCE_PRIORITY
            }
            field_details, chosen_value = build_field_audit(field_name, values_by_source)
            merged_page[field_name] = chosen_value
            field_audit[field_name] = field_details

        if not any(has_value(merged_page.get(field_name)) for field_name in PAGE_FIELDS):
            continue

        merged_pages.append(merged_page)
        page_output[str(index)] = {
            "sources": deepcopy(group),
            "field_audit": field_audit,
            "flags": {
                "has_conflict": any(details["conflict"] for details in field_audit.values()),
                "all_three_different_fields": [
                    field_name
                    for field_name, details in field_audit.items()
                    if details["all_three_different"]
                ],
            },
        }

    merged_pages.sort(key=page_sort_key)
    return merged_pages, page_output


def build_sections(groups):
    merged_sections = {}
    section_output = {}

    for index, group in enumerate(groups, start=1):
        merged_section = {}
        field_audit = {}

        for field_name in SECTION_FIELDS:
            values_by_source = {
                source_name: (group[source_name] or {}).get(field_name)
                for source_name in SOURCE_PRIORITY
            }
            field_details, chosen_value = build_field_audit(field_name, values_by_source)
            merged_section[field_name] = chosen_value
            field_audit[field_name] = field_details

        if not any(has_value(merged_section.get(field_name)) for field_name in SECTION_FIELDS):
            continue

        section_key = str(index)
        merged_sections[section_key] = {
            field_name: deepcopy(merged_section[field_name])
            for field_name in FINAL_SECTION_FIELDS
        }
        section_output[section_key] = {
            "sources": deepcopy(group),
            "field_audit": field_audit,
            "flags": {
                "has_conflict": any(details["conflict"] for details in field_audit.values()),
                "all_three_different_fields": [
                    field_name
                    for field_name, details in field_audit.items()
                    if details["all_three_different"]
                ],
            },
        }

    return merged_sections, section_output


def combine_folder(folder_name):
    payloads = {
        source_name: load_json(source_dir / f"{folder_name}.json")
        for source_name, source_dir in SOURCE_FILES.items()
    }

    top_level, top_level_audit = build_top_level(payloads)
    page_groups = merge_page_groups(payloads)
    merged_pages, page_output = build_pages(page_groups)
    groups = merge_groups(payloads)
    merged_sections, section_output = build_sections(groups)

    combined_payload = {
        key: value
        for key, value in top_level.items()
        if has_value(value)
    }
    if merged_pages:
        combined_payload["pages"] = merged_pages
    combined_payload["sections"] = merged_sections

    output_payload = {
        "folder": folder_name,
        "sources_present": {
            source_name: bool(payloads[source_name])
            for source_name in SOURCE_PRIORITY
        },
        "top_level_audit": top_level_audit,
        "pages": page_output,
        "sections": section_output,
        "flags": {
            "has_any_conflict": any(
                details["conflict"] for details in top_level_audit.values()
            ) or any(
                page_data["flags"]["has_conflict"]
                for page_data in page_output.values()
            ) or any(
                section_data["flags"]["has_conflict"]
                for section_data in section_output.values()
            ),
            "all_three_different_fields": {
                "top_level": [
                    field_name
                    for field_name, details in top_level_audit.items()
                    if details["all_three_different"]
                ],
                "pages": {
                    page_key: page_data["flags"]["all_three_different_fields"]
                    for page_key, page_data in page_output.items()
                    if page_data["flags"]["all_three_different_fields"]
                },
                "sections": {
                    section_key: section_data["flags"]["all_three_different_fields"]
                    for section_key, section_data in section_output.items()
                    if section_data["flags"]["all_three_different_fields"]
                },
            },
        },
    }

    write_json(RESULTS_DIR / f"{folder_name}.json", combined_payload)
    write_json(OUTPUT_DIR / f"{folder_name}.json", output_payload)

    logging.info(
        "Combinator merged folder=%s sources_present=%s section_count=%s",
        folder_name,
        output_payload["sources_present"],
        len(merged_sections),
    )


def discover_folder_names():
    folder_names = set()
    for source_dir in SOURCE_FILES.values():
        if not source_dir.exists():
            continue
        folder_names.update(path.stem for path in source_dir.glob("*.json"))
    return sorted(folder_names)


def main():
    log_file = setup_logging()
    ensure_dirs()
    logging.info("Combinator started")
    print(f"Logging to {log_file}")

    for folder_name in discover_folder_names():
        combine_folder(folder_name)


if __name__ == "__main__":
    main()
