import os
import json
import re
import yaml
import argparse
import logging
from copy import deepcopy


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
RESULTS_DIR = os.path.join(PROJECT_ROOT, "Combinator", "results")
INPUT_BASE_DIR = os.path.join(PROJECT_ROOT, "Input")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "Output")
ERROR_FILE = os.path.join(BASE_DIR, "error.txt")

VOLUME_SECTION_ID = 1


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
            indent=2
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


def is_integer_native(native):
    native = normalize_text(native)
    return bool(re.fullmatch(r"\d+", native))


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


def build_volume_section():
    return {
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
        "type": "volume",
        "type_num": ""
    }


def build_issue_section(issue_key, input_json, volume_section_id):
    """
    Build one Issue section for a given issue_key (e.g. "1" or "2").
    
    Looks up the date from input_json["issue_date"][issue_key] if present,
    otherwise falls back to input_json["date"].
    """
    issue_dates = input_json.get("issue_date", {})
    date_value = normalize_text(
        issue_dates.get(issue_key, input_json.get("date", ""))
    )
    return {
        "citation": "",
        "countries": ["", "", ""],
        "country_code": " ",
        "creator": [],
        "date": date_value,
        "description": f"Issue {issue_key}",
        "docket_num": "",
        "doi": "",
        "external_url": "",
        "insection": volume_section_id,
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
        "type_num": ""
    }


def build_toc_section(issue_section_id):
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
        "insection": issue_section_id,
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
        "type_num": ""
    }


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


def detect_new_json_format(input_json):
    """
    Returns True if sections carry their own first_page/issue fields
    (new multi-issue format), False if a parallel pages array is used.
    """
    sections = input_json.get("sections", {})
    for sec in sections.values():
        if "first_page" in sec or "issue" in sec:
            return True
    return False


def collect_unique_issues(input_json):
    """
    Returns a sorted list of unique issue keys found across all sections.
    Falls back to ["1"] if no issue field is present anywhere.
    """
    sections = input_json.get("sections", {})
    seen = set()
    for sec in sections.values():
        issue_key = normalize_text(sec.get("issue", ""))
        if issue_key:
            seen.add(issue_key)

    if not seen:
        return ["1"]

    # Sort numerically where possible, lexicographically otherwise
    def sort_key(k):
        try:
            return (0, int(k))
        except ValueError:
            return (1, k)

    return sorted(seen, key=sort_key)


def build_article_records_from_json(input_json, skip_probable_matter=True):
    """
    Supports both JSON formats:

    NEW FORMAT: sections carry first_page and issue directly.
      - start_native comes from section["first_page"]
      - issue_key comes from section["issue"]

    OLD FORMAT: a parallel pages array maps section order to native values.
      - start_native comes from pages[idx]["native"]
      - issue_key defaults to "1"
    """
    use_new_format = detect_new_json_format(input_json)

    json_sections = input_json.get("sections", {})
    ordered_section_items = sorted(json_sections.items(), key=lambda kv: int(kv[0]))

    records = []

    if use_new_format:
        for old_sid_str, sec in ordered_section_items:
            title_raw = normalize_text(sec.get("title", ""))
            if skip_probable_matter and is_probably_noncontent(title_raw):
                continue

            start_native = normalize_text(sec.get("first_page", ""))
            if not start_native:
                continue

            issue_key = normalize_text(sec.get("issue", "1"))
            creators = build_creator_list(sec)
            doi = normalize_text(sec.get("doi", ""))
            external_url = normalize_text(sec.get("external_url", sec.get("url", "")))
            citation = normalize_text(sec.get("citation", ""))
            description = normalize_text(sec.get("description", ""))
            sec_type = normalize_text(sec.get("type", ""))
            sec_date = normalize_text(sec.get("date", ""))
            release_date = normalize_text(sec.get("release_date", ""))
            subject = normalize_text_list(sec.get("subject", []))
            orcid = normalize_text_list(sec.get("orcid", []))

            records.append({
                "old_sid": int(old_sid_str),
                "start_native": start_native,
                "issue_key": issue_key,
                "title": title_raw,
                "creator": creators,
                "doi": doi,
                "external_url": external_url,
                "citation": citation,
                "description": description,
                "subject": subject,
                "type": sec_type,
                "date": sec_date,
                "release_date": release_date,
                "orcid": orcid,
            })

    else:
        # Old format: use parallel pages array
        json_pages = input_json.get("pages", [])
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
            citation = normalize_text(sec.get("citation", ""))
            description = normalize_text(sec.get("description", ""))
            sec_type = normalize_text(sec.get("type", ""))
            sec_date = normalize_text(sec.get("date", ""))
            release_date = normalize_text(sec.get("release_date", ""))
            subject = normalize_text_list(sec.get("subject", []))
            orcid = normalize_text_list(sec.get("orcid", []))

            records.append({
                "old_sid": int(old_sid_str),
                "start_native": start_native,
                "issue_key": "1",  # old format: single issue
                "title": title_raw,
                "creator": creators,
                "doi": doi,
                "external_url": external_url,
                "citation": citation,
                "description": description,
                "subject": subject,
                "type": sec_type,
                "date": sec_date,
                "release_date": release_date,
                "orcid": orcid,
            })

    return records


def get_page_chain(page_obj):
    chain = page_obj.get("section", [])
    if isinstance(chain, list):
        cleaned = []
        for x in chain:
            try:
                cleaned.append(int(x))
            except Exception:
                continue
        return cleaned
    return []


def build_native_to_first_page_id_map(structure_pages):
    native_to_page_id = {}
    for p in structure_pages:
        native = normalize_text(p.get("native", ""))
        if native and native not in native_to_page_id:
            native_to_page_id[native] = p["id"]
    return native_to_page_id


def build_native_to_all_page_ids_map(structure_pages):
    native_to_page_ids = {}
    for p in structure_pages:
        native = normalize_text(p.get("native", ""))
        if not native:
            continue
        native_to_page_ids.setdefault(native, []).append(p["id"])
    return native_to_page_ids


def should_use_repeating_one_logic(article_records):
    if not article_records:
        return False

    start_natives = [rec["start_native"] for rec in article_records]
    one_count = sum(1 for x in start_natives if x == "1")
    return one_count >= 2


def assign_article_start_pages_normal(article_records, structure_pages):
    native_to_page_id = build_native_to_first_page_id_map(structure_pages)

    usable_articles = []
    for rec in article_records:
        start_native = rec["start_native"]
        start_page_id = native_to_page_id.get(start_native)

        if start_page_id is None:
            log_error(
                f"[WARN] Could not map article start native '{start_native}' "
                f"for title '{rec['title']}'"
            )
            continue

        new_rec = deepcopy(rec)
        new_rec["start_structure_id"] = start_page_id
        usable_articles.append(new_rec)

    usable_articles.sort(key=lambda x: x["start_structure_id"])
    return usable_articles


def assign_article_start_pages_repeating_one(article_records, structure_pages):
    native_to_page_ids = build_native_to_all_page_ids_map(structure_pages)
    one_occurrences = native_to_page_ids.get("1", [])

    usable_articles = []
    one_index = 0

    for rec in article_records:
        start_native = rec["start_native"]

        if start_native == "1":
            if one_index >= len(one_occurrences):
                log_error(
                    f"[WARN] Not enough occurrences of native '1' in structure.yml "
                    f"for title '{rec['title']}'"
                )
                continue

            start_page_id = one_occurrences[one_index]
            one_index += 1
        else:
            all_occurrences = native_to_page_ids.get(start_native, [])
            if not all_occurrences:
                log_error(
                    f"[WARN] Could not map article start native '{start_native}' "
                    f"for title '{rec['title']}'"
                )
                continue
            start_page_id = all_occurrences[0]

        new_rec = deepcopy(rec)
        new_rec["start_structure_id"] = start_page_id
        usable_articles.append(new_rec)

    usable_articles.sort(key=lambda x: x["start_structure_id"])
    return usable_articles


def assign_article_start_pages(article_records, structure_pages):
    if should_use_repeating_one_logic(article_records):
        logging.info("Using repeating-native=1 anomaly mapping logic")
        return assign_article_start_pages_repeating_one(article_records, structure_pages)

    return assign_article_start_pages_normal(article_records, structure_pages)


def build_sections(article_records, input_json):
    """
    Builds the full sections dict for the output YAML.

    Section ID layout:
      1            → volume
      2 … 2+N-1   → one issue section per unique issue key (N issues total)
      2+N          → TOC (if enabled), else first article
      2+N+1 …     → articles (or 2+N … if no TOC)

    Returns (new_sections dict, issue_key_to_sid mapping, toc_sid or None, article_start_sid).
    """
    toc_enabled = is_toc_enabled(input_json)
    unique_issues = collect_unique_issues(input_json)

    volume_sid = VOLUME_SECTION_ID

    # Assign one section ID per issue, in sorted order
    issue_key_to_sid = {}
    next_sid = volume_sid + 1
    for issue_key in unique_issues:
        issue_key_to_sid[issue_key] = next_sid
        next_sid += 1

    toc_sid = None
    if toc_enabled:
        # TOC goes after all issue sections; it points to the first issue by convention
        first_issue_sid = issue_key_to_sid[unique_issues[0]]
        toc_sid = next_sid
        next_sid += 1

    article_start_sid = next_sid

    # --- Build sections dict ---
    new_sections = {volume_sid: build_volume_section()}

    for issue_key in unique_issues:
        sid = issue_key_to_sid[issue_key]
        new_sections[sid] = build_issue_section(issue_key, input_json, volume_sid)

    if toc_sid is not None:
        new_sections[toc_sid] = build_toc_section(first_issue_sid)

    # Build article sections
    next_sid = article_start_sid
    for rec in article_records:
        rec["new_sid"] = next_sid

        # Wire insection to the correct issue section ID
        article_issue_key = rec.get("issue_key", unique_issues[0])
        article_issue_sid = issue_key_to_sid.get(
            article_issue_key,
            issue_key_to_sid[unique_issues[0]]  # fallback to first issue
        )

        new_sec = build_empty_section()
        new_sec["type"] = rec["type"]
        new_sec["title"] = rec["title"]
        new_sec["creator"] = rec["creator"]
        new_sec["doi"] = rec["doi"]
        new_sec["external_url"] = rec["external_url"]
        new_sec["subject"] = rec["subject"]
        new_sec["description"] = rec["description"]
        new_sec["orcid"] = rec["orcid"]
        new_sec["citation"] = rec["citation"]
        new_sec["insection"] = article_issue_sid

        if rec["date"]:
            new_sec["date"] = rec["date"]
        if rec["release_date"]:
            new_sec["release_date"] = rec["release_date"]

        new_sections[next_sid] = new_sec
        next_sid += 1

    section_meta = {
        "volume": volume_sid,
        "issue_key_to_sid": issue_key_to_sid,
        "toc": toc_sid,
        "article_start": article_start_sid,
        "unique_issues": unique_issues,
    }

    return new_sections, section_meta


def build_page_to_article_sid_map(usable_articles, structure_pages):
    page_to_article_sid = {}

    for idx, rec in enumerate(usable_articles):
        start_id = rec["start_structure_id"]

        if idx < len(usable_articles) - 1:
            end_id = usable_articles[idx + 1]["start_structure_id"] - 1
        else:
            end_id = structure_pages[-1]["id"]

        for pid in range(start_id, end_id + 1):
            page_to_article_sid[pid] = rec["new_sid"]

    return page_to_article_sid


def build_front_matter_chain(section_meta):
    """
    Front-matter chain for non-integer pages (roman numerals etc.).
    Points through TOC (if any) → first issue → volume.
    """
    toc_sid = section_meta["toc"]
    first_issue_sid = section_meta["issue_key_to_sid"][section_meta["unique_issues"][0]]
    volume_sid = section_meta["volume"]

    if toc_sid is not None:
        return [toc_sid, first_issue_sid, volume_sid]

    return [first_issue_sid, volume_sid]


def build_article_chain(article_sid, article_issue_sid, section_meta):
    volume_sid = section_meta["volume"]
    return [article_sid, article_issue_sid, volume_sid]


def build_output(input_json, structure_yml, skip_probable_matter=True):
    output = deepcopy(structure_yml)

    structure_pages = output.get("pages", [])
    if not structure_pages:
        raise ValueError("structure.yml does not contain pages.")

    article_records = build_article_records_from_json(
        input_json=input_json,
        skip_probable_matter=skip_probable_matter
    )

    # Detect if any native is '0' (non-mappable placeholder)
    has_zero_native = any(
        normalize_text(rec.get("start_native", "")) == "0"
        for rec in article_records
    ) if article_records else False

    if has_zero_native:
        usable_articles = article_records
        new_sections, section_meta = build_sections(usable_articles, input_json)
        page_to_article_sid = {}
    else:
        usable_articles = assign_article_start_pages(article_records, structure_pages)
        new_sections, section_meta = build_sections(usable_articles, input_json)
        page_to_article_sid = build_page_to_article_sid_map(usable_articles, structure_pages)

    toc_enabled = section_meta["toc"] is not None
    front_matter_chain = build_front_matter_chain(section_meta)

    # Build a lookup: new_sid → article_issue_sid for page chain construction
    sid_to_issue_sid = {}
    for rec in usable_articles:
        if "new_sid" not in rec:
            continue
        issue_key = rec.get("issue_key", section_meta["unique_issues"][0])
        article_issue_sid = section_meta["issue_key_to_sid"].get(
            issue_key,
            section_meta["issue_key_to_sid"][section_meta["unique_issues"][0]]
        )
        sid_to_issue_sid[rec["new_sid"]] = article_issue_sid

    new_pages = []
    for p in structure_pages:
        pid = p["id"]
        native = p["native"]
        original_chain = get_page_chain(p)
        native_text = normalize_text(native)

        if toc_enabled and not is_integer_native(native_text):
            section_chain = front_matter_chain
        elif pid in page_to_article_sid:
            article_sid = page_to_article_sid[pid]
            article_issue_sid = sid_to_issue_sid.get(article_sid, section_meta["volume"])
            section_chain = build_article_chain(article_sid, article_issue_sid, section_meta)
        else:
            section_chain = original_chain if original_chain else [VOLUME_SECTION_ID]

        new_pages.append({
            "id": pid,
            "native": native,
            "section": section_chain
        })

    output["sections"] = dict(sorted(new_sections.items(), key=lambda kv: int(kv[0])))
    output["pages"] = new_pages

    output["series"] = normalize_text(input_json.get("volume", ""))
    output["title"] = normalize_text(input_json.get("title", output.get("title", "")))
    output["type"] = "default"

    return output


def get_matching_structure_path(journal_name):
    return os.path.join(INPUT_BASE_DIR, journal_name, "structure.yml")


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

        output = build_output(
            input_json=input_json,
            structure_yml=structure_yml,
            skip_probable_matter=not keep_probable_matter,
        )

        save_yaml(output, output_path)
        return output_path

    except Exception as e:
        msg = f"[ERROR] {journal_name}: {e}"
        print(msg)
        log_error(msg)
        logging.exception("yml_manager failed for journal=%s", journal_name)
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