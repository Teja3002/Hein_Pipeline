import os
import re
import json
import logging
import requests
from tempfile import NamedTemporaryFile

script_dir = os.path.dirname(os.path.abspath(__file__))
results_folder = os.path.join(script_dir, "results")
logger = logging.getLogger(__name__)

journal_issn_dict = {
    "ajil": "0002-9300",
    "blj": "0005-5506",
    "direlaw": "2317-6172",
    "geojlap": "1536-5077",
    "gvnanlj": "1468-0491",
    "intsocwk": "1461-7234",
    "mijoeqv": "2375-7523",
    "modlr": "1468-2230",
    "polic": "1363-951X",
    "rvadctoao": "2238-3840"
}

BASE_URL = "https://api.crossref.org/works"
ROWS = 1000
pattern = re.compile(r'^([a-zA-Z]+)(\d+)(?:no(\d+))?$')

os.makedirs(results_folder, exist_ok=True)


def normalize_text(value):
    if value is None:
        return ""
    value = str(value)
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"\s+", " ", value).strip()
    value = value.replace("’", "'").replace("“", '"').replace("”", '"')
    return value


def fetch_all_results_cursor(issn):
    all_items = []
    cursor = "*"

    while True:
        params = {
            "filter": f"issn:{issn}",
            "rows": ROWS,
            "cursor": cursor,
            "select": ",".join([
                "DOI", "title", "page", "volume", "issue", "author", "abstract"
            ])
        }

        response = requests.get(BASE_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        message = data.get("message", {})
        items = message.get("items", [])

        if not items:
            break

        all_items.extend(items)

        cursor = message.get("next-cursor")
        if not cursor:
            break

    return all_items


def is_container_doi(doi):
    doi = normalize_text(doi)
    return bool(re.search(r'\.v\d+\.\d+$', doi, flags=re.IGNORECASE))


def is_non_article_title(title):
    title = normalize_text(title).lower()

    blocked_patterns = [
        r'\bcover\b',
        r'\bfront matter\b',
        r'\bback matter\b',
        r'\bfront cover\b',
        r'\bback cover\b',
        r'\bmasthead\b',
        r'\btable of contents\b',
        r'\bcontents\b',
        r'\bindex\b',
        r'\beditorial board\b',
    ]

    return any(re.search(p, title) for p in blocked_patterns)


def is_valid_article_record(item):
    titles = item.get("title", [])
    title = normalize_text(titles[0]) if titles else ""
    doi = normalize_text(item.get("DOI", ""))

    if not title or not doi:
        return False

    if is_container_doi(doi):
        return False

    if is_non_article_title(title):
        return False

    return True


def filter_items(items, volume, issue=None):
    filtered = []

    for item in items:
        if not is_valid_article_record(item):
            continue

        item_volume = normalize_text(item.get("volume", ""))
        item_issue = normalize_text(item.get("issue", ""))

        if item_volume != str(volume):
            continue

        if issue is not None and item_issue != str(issue):
            continue

        filtered.append(item)

    return filtered


def get_start_page(page_range):
    page_range = normalize_text(page_range)
    return page_range.split("-")[0].strip() if page_range else ""


def page_sort_key(item):
    page_range = normalize_text(item.get("page", ""))
    title = normalize_text(item.get("title", [""])[0])
    doi = normalize_text(item.get("DOI", ""))

    if page_range:
        num = re.search(r"\d+", page_range)
        return (0, int(num.group()) if num else 0, title.lower(), doi.lower())

    return (1, float("inf"), title.lower(), doi.lower())


def get_final_url(doi):
    doi = normalize_text(doi)
    if not doi:
        return ""

    try:
        return requests.head(f"https://doi.org/{doi}", allow_redirects=True, timeout=30).url
    except Exception:
        return f"https://doi.org/{doi}"


def extract_creators(item):
    creators = []
    for author in item.get("author", []):
        name = ", ".join(filter(None, [
            normalize_text(author.get("family", "")),
            normalize_text(author.get("given", ""))
        ]))
        if name:
            creators.append(name)
    return creators


def build_section_data(item):
    doi = normalize_text(item.get("DOI", ""))
    authors = extract_creators(item)[:50]

    data = {
        "title": normalize_text(item.get("title", [""])[0]),
        "citation": "",
        "description": normalize_text(item.get("abstract", "")),
        "doi": doi,
        "external_url": get_final_url(doi),
        "authors": authors,
    }

    return data


def build_json_structure(filtered_items, volume, issue):
    pages = []
    sections = {}

    for i, item in enumerate(sorted(filtered_items, key=page_sort_key), 1):
        start_page = get_start_page(item.get("page", "")) or "0"

        section_id = [int(volume)]
        if issue:
            section_id.append(int(issue))

        pages.append({
            "id": i,
            "native": start_page,
            "section": section_id
        })

        sections[str(i)] = build_section_data(item)

    return {"pages": pages, "sections": sections}


def write_json_safely(data, filename):
    with NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        temp_name = tmp.name
    os.replace(temp_name, filename)

def process_folder(folder_name, folder_path):
    if not os.path.isdir(folder_path):
        logger.error("Folder does not exist or is not a directory: %s", folder_path)
        return False

    match = pattern.match(folder_name)
    if not match:
        logger.warning("Skipping folder with unsupported name format: %s", folder_name)
        return False

    journal_key, volume_part, issue_part = match.groups()
    volume = str(int(volume_part))
    issue = issue_part

    if journal_key not in journal_issn_dict:
        logger.warning("Skipping folder with unknown journal key: %s", folder_name)
        return False

    issn = journal_issn_dict[journal_key]
    output_file = os.path.join(results_folder, f"{folder_name}.json")

    logger.info(
        "Running folder=%s path=%s volume=%s issue=%s output=%s",
        folder_name,
        folder_path,
        volume,
        issue or "N/A",
        output_file,
    )
    print(f"\nProcessing {folder_name}, Volume={volume}, Issue={issue or 'N/A'}")

    try:
        all_items = fetch_all_results_cursor(issn)
        filtered_items = filter_items(all_items, volume, issue)

        logger.info(
            "Fetched folder=%s total_items=%s filtered_items=%s",
            folder_name,
            len(all_items),
            len(filtered_items),
        )
        print(f"Fetched: {len(all_items)} to Final: {len(filtered_items)}")

        if not filtered_items:
            logger.warning(
                "No valid articles found for folder=%s; skipping output file creation",
                folder_name,
            )
            print(f"No valid articles found for {folder_name}. Skipping output.")
            return False

        output = build_json_structure(filtered_items, volume, issue)
        write_json_safely(output, output_file)

        logger.info("Saved result for folder=%s to %s", folder_name, output_file)
        print(f"Saved to {output_file}")
        return True

    except Exception:
        logger.exception("Failed while processing folder=%s path=%s", folder_name, folder_path)
        print(f"Error while processing {folder_name}. Check logs for details.")
        return False
