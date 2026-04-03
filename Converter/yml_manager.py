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



def extract_issue_years(input_json):

    issue_dates = input_json.get("issue_date", {})
    years = set()

    for value in issue_dates.values():
        text = normalize_text(value)
        match = re.search(r"\b(\d{4})\b", text)
        if match:
            years.add(int(match.group(1)))

    if not years:
        fallback = normalize_text(input_json.get("date", ""))
        match = re.search(r"\b(\d{4})\b", fallback)
        if match:
            years.add(int(match.group(1)))

    return sorted(years)


def save_yaml(data, path, date_years=None):
    ensure_parent_dir(path)

    # Build an ordered copy with 'date' first
    ordered = {}

    if date_years and len(date_years) == 1:
        ordered["date"] = date_years[0]
    elif date_years and len(date_years) > 1:
        ordered["date"] = date_years
    else:
        ordered["date"] = ""

    for key, value in data.items():
        if key != "date":
            ordered[key] = value

    with open(path, "w", encoding="utf-8") as f:
        f.write("---\n")
        yaml.dump(
            ordered,
            f,
            Dumper=IndentNoAliasDumper,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            width=1000,
            indent=2
        )


def log_error(message):
    print(f"[LOG] {message.rstrip()}")
    logging.warning(message.rstrip())

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
    sections = input_json.get("sections", {})
    seen = set()
    for sec in sections.values():
        issue_key = normalize_text(sec.get("issue", ""))
        if issue_key:
            seen.add(issue_key)

    if not seen:
        return ["1"]

    def sort_key(k):
        try:
            return (0, int(k))
        except ValueError:
            return (1, k)

    return sorted(seen, key=sort_key)


def build_article_records_from_json(input_json, skip_probable_matter=True):
    """
    Supports both JSON formats:

    NEW FORMAT: sections carry first_page, last_page, and issue directly.
      - start_native comes from section["first_page"]
      - end_native   comes from section["last_page"]  (may be null)
      - issue_key    comes from section["issue"]
      - If first_page is null/empty, the record is still included but
        marked as page-unmappable (page_mappable=False). It will still
        appear as a fully-populated section in the output YAML; it just
        won't be assigned to any page range.

    OLD FORMAT: a parallel pages array maps section order to native values.
      - start_native comes from pages[idx]["native"]
      - end_native   is always "" (old format has no last_page field)
      - issue_key    defaults to "1"
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

            # Allow null/missing first_page — record is still included,
            # just flagged as having no page mapping.
            raw_first_page = sec.get("first_page")
            start_native = normalize_text(raw_first_page) if raw_first_page is not None else ""

            # last_page drives overlap detection; null means no overlap check for this article.
            raw_last_page = sec.get("last_page")
            end_native = normalize_text(raw_last_page) if raw_last_page is not None else ""

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
                "end_native": end_native,
                "page_mappable": bool(start_native),  # False when first_page is null
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
                "end_native": "",  # old format has no last_page field
                "page_mappable": True,
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

    # Only consider mappable records for this heuristic
    start_natives = [rec["start_native"] for rec in article_records if rec.get("page_mappable")]
    one_count = sum(1 for x in start_natives if x == "1")
    return one_count >= 2


def assign_article_start_pages_normal(article_records, structure_pages):
    native_to_page_id = build_native_to_first_page_id_map(structure_pages)

    result = []
    for rec in article_records:
        new_rec = deepcopy(rec)

        if not rec.get("page_mappable"):
            # No first_page — include in sections but skip page assignment
            result.append(new_rec)
            continue

        start_native = rec["start_native"]
        start_page_id = native_to_page_id.get(start_native)

        if start_page_id is None:
            log_error(
                f"[WARN] Could not map article start native '{start_native}' "
                f"for title '{rec['title']}'"
            )
            new_rec["page_mappable"] = False
            result.append(new_rec)
            continue

        new_rec["start_structure_id"] = start_page_id
        result.append(new_rec)

    result.sort(key=lambda x: x.get("start_structure_id", float("inf")))
    return result


def assign_article_start_pages_repeating_one(article_records, structure_pages):
    native_to_page_ids = build_native_to_all_page_ids_map(structure_pages)
    one_occurrences = native_to_page_ids.get("1", [])

    result = []
    one_index = 0

    for rec in article_records:
        new_rec = deepcopy(rec)

        if not rec.get("page_mappable"):
            result.append(new_rec)
            continue

        start_native = rec["start_native"]

        if start_native == "1":
            if one_index >= len(one_occurrences):
                log_error(
                    f"[WARN] Not enough occurrences of native '1' in structure.yml "
                    f"for title '{rec['title']}'"
                )
                new_rec["page_mappable"] = False
                result.append(new_rec)
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
                new_rec["page_mappable"] = False
                result.append(new_rec)
                continue
            start_page_id = all_occurrences[0]

        new_rec["start_structure_id"] = start_page_id
        result.append(new_rec)

    result.sort(key=lambda x: x.get("start_structure_id", float("inf")))
    return result


def assign_article_start_pages(article_records, structure_pages):
    if should_use_repeating_one_logic(article_records):
        logging.info("Using repeating-native=1 anomaly mapping logic")
        return assign_article_start_pages_repeating_one(article_records, structure_pages)

    return assign_article_start_pages_normal(article_records, structure_pages)


def build_sections(article_records, input_json):
    """
    Builds the full sections dict for the output YAML.

    All article records — including those with null first_page — receive a
    new_sid and appear in the sections dict with their full metadata.
    Records with no page mapping are wired to their issue section normally;
    the pages array simply won't reference them.
    """
    toc_enabled = is_toc_enabled(input_json)
    unique_issues = collect_unique_issues(input_json)

    volume_sid = VOLUME_SECTION_ID

    issue_key_to_sid = {}
    next_sid = volume_sid + 1
    for issue_key in unique_issues:
        issue_key_to_sid[issue_key] = next_sid
        next_sid += 1

    toc_sid = None
    if toc_enabled:
        first_issue_sid = issue_key_to_sid[unique_issues[0]]
        toc_sid = next_sid
        next_sid += 1

    article_start_sid = next_sid

    new_sections = {volume_sid: build_volume_section()}

    for issue_key in unique_issues:
        sid = issue_key_to_sid[issue_key]
        new_sections[sid] = build_issue_section(issue_key, input_json, volume_sid)

    if toc_sid is not None:
        new_sections[toc_sid] = build_toc_section(first_issue_sid)

    next_sid = article_start_sid
    for rec in article_records:
        rec["new_sid"] = next_sid

        article_issue_key = rec.get("issue_key", unique_issues[0])
        article_issue_sid = issue_key_to_sid.get(
            article_issue_key,
            issue_key_to_sid[unique_issues[0]]
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
    """
    Builds a mapping of page ID -> list of article section IDs.

    Normal pages:  pid -> [article_sid]
    Overlap pages: pid -> [incoming_sid, outgoing_sid]

    Overlap rule: if article A's end_native (last_page) equals article B's
    start_native (first_page), the physical page where they meet gets both
    section IDs in the chain: [B_sid, A_sid] — incoming article first,
    outgoing second. All other pages in A's range receive [A_sid] only.

    Articles with no start_structure_id (null first_page) are excluded from
    page mapping but still appear fully in the sections dict.
    """
    mappable = [rec for rec in usable_articles if rec.get("start_structure_id") is not None]

    # pid -> [sid, ...]; shared/overlap pages have two entries
    page_to_article_sids = {}

    for idx, rec in enumerate(mappable):
        start_id = rec["start_structure_id"]

        if idx < len(mappable) - 1:
            next_rec = mappable[idx + 1]
            end_id = next_rec["start_structure_id"] - 1

            # Overlap check: does this article's last_page native match
            # the next article's first_page native?
            a_end_native = rec.get("end_native", "")
            b_start_native = next_rec.get("start_native", "")
            if a_end_native and b_start_native and a_end_native == b_start_native:
                # Shared page — incoming article (B) first, outgoing (A) second
                shared_pid = next_rec["start_structure_id"]
                page_to_article_sids[shared_pid] = [next_rec["new_sid"], rec["new_sid"]]
        else:
            end_id = structure_pages[-1]["id"]

        # Assign this article's page range, skipping already-marked shared pages
        for pid in range(start_id, end_id + 1):
            if pid not in page_to_article_sids:
                page_to_article_sids[pid] = [rec["new_sid"]]

    return page_to_article_sids


def build_front_matter_chain(section_meta):
    toc_sid = section_meta["toc"]
    first_issue_sid = section_meta["issue_key_to_sid"][section_meta["unique_issues"][0]]
    volume_sid = section_meta["volume"]

    if toc_sid is not None:
        return [toc_sid, first_issue_sid, volume_sid]

    return [first_issue_sid, volume_sid]


def build_article_chain(article_sids, article_issue_sid, section_meta):
    """
    article_sids is a list — normally [single_sid], but [B_sid, A_sid] on
    shared (overlap) pages. Issue and volume are appended after all article sids.
    """
    volume_sid = section_meta["volume"]
    return list(article_sids) + [article_issue_sid, volume_sid]


def build_output(input_json, structure_yml, skip_probable_matter=True):
    output = deepcopy(structure_yml)

    structure_pages = output.get("pages", [])
    if not structure_pages:
        raise ValueError("structure.yml does not contain pages.")

    article_records = build_article_records_from_json(
        input_json=input_json,
        skip_probable_matter=skip_probable_matter
    )

    has_zero_native = any(
        normalize_text(rec.get("start_native", "")) == "0"
        for rec in article_records
        if rec.get("page_mappable")
    ) if article_records else False

    if has_zero_native:
        usable_articles = article_records
        new_sections, section_meta = build_sections(usable_articles, input_json)
        page_to_article_sids = {}
    else:
        usable_articles = assign_article_start_pages(article_records, structure_pages)
        new_sections, section_meta = build_sections(usable_articles, input_json)
        page_to_article_sids = build_page_to_article_sid_map(usable_articles, structure_pages)

    toc_enabled = section_meta["toc"] is not None
    front_matter_chain = build_front_matter_chain(section_meta)

    # Build lookup: new_sid -> article_issue_sid for page chain construction
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
        elif pid in page_to_article_sids:
            article_sids = page_to_article_sids[pid]
            # Use the primary (first/incoming) article's issue for the chain
            primary_issue_sid = sid_to_issue_sid.get(article_sids[0], section_meta["volume"])
            section_chain = build_article_chain(article_sids, primary_issue_sid, section_meta)
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

        date_years = extract_issue_years(input_json)

        output = build_output(
            input_json=input_json,
            structure_yml=structure_yml,
            skip_probable_matter=not keep_probable_matter,
        )

        save_yaml(output, output_path, date_years=date_years)
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