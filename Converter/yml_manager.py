import os
import json
import re
import yaml
import argparse
from copy import deepcopy


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(BASE_DIR, "results")
STRUCTURE_BASE_DIR = os.path.join(BASE_DIR, "HeinOnline", "Before", "Before")
OUTPUT_DIR = os.path.join(BASE_DIR, "final_yml")
ERROR_FILE = os.path.join(BASE_DIR, "error.txt")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml(data, path):
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            data,
            f,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            width=1000
        )


def log_error(message):
    with open(ERROR_FILE, "a", encoding="utf-8") as f:
        f.write(message.rstrip() + "\n")


def normalize_text(value):
    if value is None:
        return ""
    value = str(value)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = value.replace("’", "'").replace("“", '"').replace("”", '"')
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


def parse_token(token):
    token = normalize_text(token)

    if re.fullmatch(r"\d+", token):
        return ("num", int(token))

    m = re.fullmatch(r"([A-Za-z]+)(\d+)", token)
    if m:
        return (m.group(1).lower(), int(m.group(2)))

    if re.fullmatch(r"\[?[ivxlcdmIVXLCDM]+\]?", token):
        return ("roman", token.lower())

    return ("raw", token)


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
        "type_num": ""
    }

    if isinstance(template, dict):
        merged = deepcopy(base)
        merged.update(deepcopy(template))
        return merged

    return deepcopy(base)


def infer_year(structure_yml):
    if isinstance(structure_yml, dict):
        return normalize_text(structure_yml.get("date", ""))
    return ""


def is_probably_noncontent(title):
    t = normalize_text(title).lower()
    patterns = [
        "front matter",
        "back matter",
        "cover and front matter",
        "cover and back matter",
    ]
    return any(p in t for p in patterns)


def is_non_numeric_page_token(token):
    parsed = parse_token(token)
    return parsed[0] not in ("num", "f", "b")


def build_creator_list(sec):
    creators = normalize_text_list(sec.get("creator", []))
    if creators:
        return creators

    author_items = []
    for key, value in sec.items():
        m = re.fullmatch(r"author_(\d+)", str(key))
        if m:
            idx = int(m.group(1))
            author_items.append((idx, normalize_text(value)))

    author_items.sort(key=lambda x: x[0])
    return [value for _, value in author_items if value]


def infer_section_type(sec):
    section_type = normalize_text(sec.get("type", ""))
    if section_type:
        return section_type
    return "article"


def build_article_records_from_json(input_json, skip_probable_matter=True):
    json_pages = input_json.get("pages", [])
    json_sections = input_json.get("sections", {})

    ordered_section_items = sorted(json_sections.items(), key=lambda kv: int(kv[0]))
    records = []

    max_len = min(len(json_pages), len(ordered_section_items))

    for idx in range(max_len):
        page_obj = json_pages[idx]
        old_sid_str, sec = ordered_section_items[idx]

        title_raw = normalize_text(sec.get("title", ""))
        if skip_probable_matter and is_probably_noncontent(title_raw):
            continue

        start_native = normalize_text(page_obj.get("native", ""))
        if not start_native:
            continue

        creators = build_creator_list(sec)
        doi = normalize_text(sec.get("doi", ""))
        external_url = normalize_text(sec.get("external_url", sec.get("url", "")))
        description = normalize_text(sec.get("description", ""))
        subject = normalize_text_list(sec.get("subject", []))
        section_type = infer_section_type(sec)

        records.append({
            "old_sid": int(old_sid_str),
            "start_native": start_native,
            "title": title_raw,
            "creator": creators,
            "doi": doi,
            "external_url": external_url,
            "citation": "",
            "description": description,
            "subject": subject,
            "type": section_type,
            "date": "",
            "release_date": "",
        })

    return records


def get_section_dict(yml_data):
    sections = yml_data.get("sections", {})
    normalized = {}
    for k, v in sections.items():
        try:
            normalized[int(k)] = v
        except Exception:
            continue
    return normalized


def get_max_section_id(sections_dict):
    return max(sections_dict.keys(), default=0)


def get_page_chain(page_obj):
    chain = page_obj.get("section", [])
    if isinstance(chain, list):
        return [int(x) for x in chain]
    return []


def get_parent_chain_for_article_start(page_obj):
    """
    For a structure page whose current chain may be like [3,1] or [1],
    use its existing ancestry as the parent chain for the new article node.

    If the page has no chain, return [].
    """
    chain = get_page_chain(page_obj)
    if not chain:
        return []

    return chain[:]


def build_output(input_json, structure_yml, skip_probable_matter=True):
    output = deepcopy(structure_yml)

    year = infer_year(structure_yml)
    if year:
        output["date"] = year

    structure_pages = output.get("pages", [])
    if not structure_pages:
        raise ValueError("structure.yml does not contain pages.")

    old_sections = get_section_dict(structure_yml)
    new_sections = deepcopy(old_sections)

    article_records = build_article_records_from_json(
        input_json=input_json,
        skip_probable_matter=skip_probable_matter
    )

    next_sid = get_max_section_id(new_sections) + 1

    for rec in article_records:
        rec["new_sid"] = next_sid
        next_sid += 1

    for rec in article_records:
        new_sec = build_empty_section()
        new_sec["type"] = rec["type"]
        new_sec["title"] = rec["title"]
        new_sec["creator"] = rec["creator"]
        new_sec["doi"] = rec["doi"]
        new_sec["external_url"] = rec["external_url"]
        new_sec["subject"] = rec["subject"]
        new_sec["description"] = rec["description"]
        new_sec["orcid"] = []

        if rec["date"]:
            new_sec["date"] = rec["date"]
        if rec["release_date"]:
            new_sec["release_date"] = rec["release_date"]

        new_sec["citation"] = rec["citation"] or ""

        new_sections[rec["new_sid"]] = new_sec

    native_to_page_ids = {}
    for p in structure_pages:
        native = normalize_text(p.get("native", ""))
        native_to_page_ids.setdefault(native, []).append(p["id"])

    usable_articles = []
    for rec in article_records:
        candidates = native_to_page_ids.get(rec["start_native"], [])
        if candidates:
            rec["start_structure_id"] = candidates[0]
            usable_articles.append(rec)
        else:
            log_error(
                f"[WARN] Could not map article start native '{rec['start_native']}' "
                f"for title '{rec['title']}'"
            )

    usable_articles.sort(key=lambda x: x["start_structure_id"])

    page_id_to_obj = {p["id"]: p for p in structure_pages}
    page_to_article_sid = {}

    for idx, rec in enumerate(usable_articles):
        start_id = rec["start_structure_id"]
        if idx < len(usable_articles) - 1:
            end_id = usable_articles[idx + 1]["start_structure_id"] - 1
        else:
            end_id = structure_pages[-1]["id"]

        start_page_obj = page_id_to_obj[start_id]
        rec["parent_chain"] = get_parent_chain_for_article_start(start_page_obj)

        for pid in range(start_id, end_id + 1):
            page_to_article_sid[pid] = rec["new_sid"]

    start_id_by_sid = {rec["new_sid"]: rec["start_structure_id"] for rec in usable_articles}

    new_pages = []
    for p in structure_pages:
        pid = p["id"]
        native = p["native"]
        original_chain = get_page_chain(p)

        if pid in page_to_article_sid:
            article_sid = page_to_article_sid[pid]

            article_rec = next((r for r in usable_articles if r["new_sid"] == article_sid), None)
            parent_chain = article_rec["parent_chain"] if article_rec else original_chain

            section_chain = [article_sid] + parent_chain
        else:
            section_chain = original_chain

        new_pages.append({
            "id": pid,
            "native": native,
            "section": section_chain
        })

    output["sections"] = dict(sorted(new_sections.items(), key=lambda kv: int(kv[0])))
    output["pages"] = new_pages
    return output


def get_matching_structure_path(journal_name):
    return os.path.join(STRUCTURE_BASE_DIR, journal_name, "structure.yml")


def get_json_files(journal_name=None):
    if not os.path.isdir(RESULTS_DIR):
        raise FileNotFoundError(f"results directory not found: {RESULTS_DIR}")

    if journal_name:
        json_filename = f"{journal_name}.json"
        json_path = os.path.join(RESULTS_DIR, json_filename)
        if not os.path.exists(json_path):
            raise FileNotFoundError(f"JSON file not found: {json_path}")
        return [json_filename]

    return sorted(
        f for f in os.listdir(RESULTS_DIR)
        if f.lower().endswith(".json")
    )


def process_one_json(json_filename, keep_probable_matter=False):
    journal_name = os.path.splitext(json_filename)[0]

    json_path = os.path.join(RESULTS_DIR, json_filename)
    structure_path = get_matching_structure_path(journal_name)
    output_path = os.path.join(OUTPUT_DIR, f"{journal_name}.yml")

    if not os.path.exists(structure_path):
        msg = f"[SKIP] structure.yml not found for {journal_name}: {structure_path}"
        print(msg)
        log_error(msg)
        return

    try:
        input_json = load_json(json_path)
        structure_yml = load_yaml(structure_path)

        output = build_output(
            input_json=input_json,
            structure_yml=structure_yml,
            skip_probable_matter=not keep_probable_matter
        )

        save_yaml(output, output_path)
        print(f"[OK] {journal_name} -> {output_path}")

    except Exception as e:
        msg = f"[ERROR] {journal_name}: {e}"
        print(msg)
        log_error(msg)


def main():
    parser = argparse.ArgumentParser(
        description="Auto-convert JSON files in results/ using matching HeinOnline structure.yml files"
    )
    parser.add_argument(
        "--journal",
        help="Process only one journal name, for example: ajil0120no1"
    )
    parser.add_argument(
        "--keep-probable-matter",
        action="store_true",
        help="Keep probable front/back matter instead of skipping it"
    )
    args = parser.parse_args()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    try:
        json_files = get_json_files(args.journal)
    except Exception as e:
        print(f"[ERROR] {e}")
        return

    if not json_files:
        print("[INFO] No JSON files found in results/")
        return

    for json_filename in json_files:
        process_one_json(
            json_filename=json_filename,
            keep_probable_matter=args.keep_probable_matter
        )


if __name__ == "__main__":
    main()