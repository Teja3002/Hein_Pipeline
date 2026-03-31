import os
import json
import re
import yaml
import argparse
import logging
from copy import deepcopy


BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT   = os.path.dirname(BASE_DIR)
RESULTS_DIR    = os.path.join(PROJECT_ROOT, "Combinator", "results")
INPUT_BASE_DIR = os.path.join(PROJECT_ROOT, "Input")
OUTPUT_DIR     = os.path.join(PROJECT_ROOT, "Output")
ERROR_FILE     = os.path.join(BASE_DIR, "error.txt")


class IndentNoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def ensure_parent_dir(path):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml(data, path):
    ensure_parent_dir(path)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            data,
            f,
            Dumper=IndentNoAliasDumper,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            width=1000,
            indent=2,
        )


def log_error(message):
    ensure_parent_dir(ERROR_FILE)
    with open(ERROR_FILE, "a", encoding="utf-8") as f:
        f.write(message.rstrip() + "\n")


def normalize_text(value):
    if value is None:
        return ""
    value = str(value)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = value.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return value


def normalize_text_list(values):
    if not isinstance(values, list):
        return []
    cleaned = []
    for value in values:
        text = normalize_text(value)
        if text:
            cleaned.append(text)
    return cleaned


def is_toc_enabled(input_json):
    toc_value = input_json.get("TOC", False)
    if isinstance(toc_value, str):
        return toc_value.strip().lower() == "true"
    return bool(toc_value)


def build_empty_section(template=None):
    base = {
        "citation": "",
        "countries": [],
        "country_code": " ",
        "creator": [],
        "date": "",
        "description": "",
        "docket_num": "",
        "doi": "",
        "external_url": "",
        "judge": 0,
        "orcid": [],
        "release_date": "",
        "release_date_weekly": "",
        "section_num": "",
        "subject": [],
        "title": "",
        "title_num": "",
        "treaty_noc": "",
        "type": "",
        "type_num": "",
    }
    if isinstance(template, dict):
        merged = deepcopy(base)
        merged.update(deepcopy(template))
        return merged
    return deepcopy(base)


def is_probably_noncontent(title):
    t = normalize_text(title).lower()
    patterns = [
        "front matter",
        "back matter",
        "cover and front matter",
        "cover and back matter",
    ]
    return any(p in t for p in patterns)


def build_creator_list(sec):
    creators = normalize_text_list(sec.get("creator", []))
    if creators:
        return creators

    authors = normalize_text_list(sec.get("authors", []))
    if authors:
        return authors

    author_items = []
    for key, value in sec.items():
        m = re.fullmatch(r"author_(\d+)", str(key))
        if m:
            idx = int(m.group(1))
            author_items.append((idx, normalize_text(value)))

    author_items.sort(key=lambda x: x[0])
    return [value for _, value in author_items if value]


def build_article_records_from_json(input_json, skip_probable_matter=True):
    json_pages    = input_json.get("pages", [])
    json_sections = input_json.get("sections", {})

    ordered_section_items = sorted(json_sections.items(), key=lambda kv: int(kv[0]))
    records = []
    max_len = min(len(json_pages), len(ordered_section_items))

    for idx in range(max_len):
        page_obj         = json_pages[idx]
        old_sid_str, sec = ordered_section_items[idx]

        title_raw = normalize_text(sec.get("title", ""))
        if skip_probable_matter and is_probably_noncontent(title_raw):
            continue

        start_native = normalize_text(page_obj.get("native", ""))
        if not start_native:
            continue

        records.append({
            "old_sid":      int(old_sid_str),
            "start_native": start_native,
            "title":        title_raw,
            "creator":      build_creator_list(sec),
            "doi":          normalize_text(sec.get("doi", "")),
            "external_url": normalize_text(sec.get("external_url", sec.get("url", ""))),
            "citation":     normalize_text(sec.get("citation", "")),
            "description":  normalize_text(sec.get("description", "")),
            "subject":      normalize_text_list(sec.get("subject", [])),
            "type":         normalize_text(sec.get("type", "")),
            "date":         normalize_text(sec.get("date", "")),
            "release_date": normalize_text(sec.get("release_date", "")),
            "orcid":        normalize_text_list(sec.get("orcid", [])),
        })

    return records


def get_matching_structure_path(journal_name):
    return os.path.join(INPUT_BASE_DIR, journal_name, "structure.yml")


def get_json_files(journal_name=None):
    if not os.path.isdir(RESULTS_DIR):
        raise FileNotFoundError(f"results directory not found: {RESULTS_DIR}")

    if journal_name:
        json_filename = f"{journal_name}.json"
        json_path     = os.path.join(RESULTS_DIR, json_filename)
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"JSON file not found: {json_path}")
        return [json_filename]

    return sorted(
        f for f in os.listdir(RESULTS_DIR)
        if f.lower().endswith(".json")
    )


def get_max_section_id(existing_sections: dict) -> int:
    return max(int(k) for k in existing_sections.keys())


def get_volume_section_id(existing_sections: dict) -> int:
    for sid, sec in existing_sections.items():
        if sec.get("type") == "volume":
            return int(sid)
    return 1


def build_new_issue_section(input_json: dict, volume_sid: int) -> dict:
    issue_value = normalize_text(input_json.get("issue", ""))
    return {
        "citation": "",
        "countries": ["", "", ""],
        "country_code": " ",
        "creator": [],
        "date": normalize_text(input_json.get("date", "")),
        "description": f"Issue {issue_value}" if issue_value else "",
        "docket_num": "",
        "doi": "",
        "external_url": "",
        "insection": volume_sid,
        "judge": 0,
        "orcid": [],
        "release_date": "",
        "release_date_weekly": "",
        "section_num": "",
        "subject": ["", ""],
        "title": "",
        "title_num": "",
        "treaty_noc": "",
        "type": "issue",
        "type_num": "",
    }


def build_new_toc_section(new_issue_sid: int) -> dict:
    return {
        "citation": "",
        "countries": [],
        "country_code": " ",
        "creator": [],
        "date": "",
        "description": "Table of Contents",
        "docket_num": "",
        "doi": "",
        "external_url": "",
        "insection": new_issue_sid,
        "judge": 0,
        "orcid": [],
        "release_date": "",
        "release_date_weekly": "",
        "section_num": "",
        "subject": [],
        "title": "",
        "title_num": "",
        "treaty_noc": "",
        "type": "contents",
        "type_num": "",
    }


def build_new_article_section(rec: dict, new_issue_sid: int) -> dict:
    sec = build_empty_section()
    sec["type"]         = rec["type"]
    sec["title"]        = rec["title"]
    sec["creator"]      = rec["creator"]
    sec["doi"]          = rec["doi"]
    sec["external_url"] = rec["external_url"]
    sec["subject"]      = rec["subject"]
    sec["description"]  = rec["description"]
    sec["orcid"]        = rec["orcid"]
    sec["citation"]     = rec["citation"]
    sec["insection"]    = new_issue_sid

    if rec.get("date"):
        sec["date"] = rec["date"]
    if rec.get("release_date"):
        sec["release_date"] = rec["release_date"]

    return sec


def append_issue_sections(
    input_json: dict,
    structure_yml: dict,
    skip_probable_matter: bool = True,
) -> dict:
    output = deepcopy(structure_yml)
    existing_sections: dict = output.get("sections", {})

    if not existing_sections:
        raise ValueError("structure.yml has no existing sections to append to.")

    volume_sid        = get_volume_section_id(existing_sections)
    max_sid           = get_max_section_id(existing_sections)
    toc_enabled       = is_toc_enabled(input_json)

    new_issue_sid     = max_sid + 1
    new_toc_sid       = (max_sid + 2) if toc_enabled else None
    article_start_sid = (max_sid + 3) if toc_enabled else (max_sid + 2)

    new_sections: dict = {
        new_issue_sid: build_new_issue_section(input_json, volume_sid),
    }

    if toc_enabled:
        new_sections[new_toc_sid] = build_new_toc_section(new_issue_sid)

    article_records = build_article_records_from_json(
        input_json=input_json,
        skip_probable_matter=skip_probable_matter,
    )

    next_sid = article_start_sid
    for rec in article_records:
        new_sections[next_sid] = build_new_article_section(rec, new_issue_sid)
        next_sid += 1

    merged = {**existing_sections, **new_sections}
    output["sections"] = dict(sorted(merged.items(), key=lambda kv: int(kv[0])))

    return output


def process_one_json(json_filename: str, keep_probable_matter: bool = False):
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    journal_name   = os.path.splitext(json_filename)[0]
    json_path      = os.path.join(RESULTS_DIR, json_filename)
    structure_path = get_matching_structure_path(journal_name)
    output_path    = os.path.join(OUTPUT_DIR, f"{journal_name}.yml")

    if not os.path.exists(structure_path):
        msg = f"[SKIP] structure.yml not found for {journal_name}: {structure_path}"
        print(msg)
        log_error(msg)
        logging.warning(msg)
        return None

    try:
        input_json    = load_json(json_path)
        structure_yml = load_yaml(structure_path)

        result = append_issue_sections(
            input_json=input_json,
            structure_yml=structure_yml,
            skip_probable_matter=not keep_probable_matter,
        )

        save_yaml(result, output_path)
        print(f"[OK] {journal_name} -> {output_path}")
        logging.info("yml_manager1 appended sections for journal=%s output=%s", journal_name, output_path)
        return output_path

    except Exception as e:
        msg = f"[ERROR] {journal_name}: {e}"
        print(msg)
        log_error(msg)
        logging.exception("yml_manager1 failed for journal=%s", journal_name)
        return None


def process_journal(journal_name: str, keep_probable_matter: bool = False):
    return process_one_json(
        json_filename=f"{journal_name}.json",
        keep_probable_matter=keep_probable_matter,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal", help="Process only one journal, e.g. ajil0120no1")
    parser.add_argument(
        "--keep-probable-matter",
        action="store_true",
        help="Keep probable front/back matter instead of skipping it",
    )
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    try:
        json_files = get_json_files(args.journal)
    except Exception as e:
        print(f"[ERROR] {e}")
        return

    if not json_files:
        print(f"[INFO] No JSON files found in {RESULTS_DIR}")
        return

    for json_filename in json_files:
        process_one_json(
            json_filename=json_filename,
            keep_probable_matter=args.keep_probable_matter,
        )


if __name__ == "__main__":
    main()