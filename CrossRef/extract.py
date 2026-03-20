import os
import re
import json
import html
import time
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
    "rvadctoao": "2238-3840",

    "annrbfl": "1933-3927",
    "aulr": "2161-1897",
    "cllpj": "2819-2567",
    "ecomflr": "1613-2548",
    "gslr": "1934-1652",
    "ilr": "0021-0552",
    "jlbsc": "2053-9711",
    "umblr": "1939-859X"
}

SPECIAL_CHAR_MAP = str.maketrans({
    "à": "a", "á": "a", "â": "a", "ä": "a", "æ": "a", "ã": "a", "å": "a", "ā": "a",
    "ç": "c", "ć": "c",
    "è": "e", "é": "e", "ê": "e", "ë": "e", "ē": "e", "ę": "e",
    "ì": "i", "í": "i", "î": "i", "ï": "i", "ī": "i", "į": "i",
    "ñ": "n", "ń": "n",
    "ò": "o", "ó": "o", "ô": "o", "ö": "o", "œ": "o", "ø": "o", "ō": "o",
    "ß": "ss",
    "ù": "u", "ú": "u", "û": "u", "ü": "u", "ū": "u",
    "ÿ": "y",
    "ž": "z", "ź": "z", "ż": "z",
    "§": "sec."
})

BASE_URL = "https://api.crossref.org/works"
JOURNAL_BASE_URL = "https://api.crossref.org/journals"

ROWS = 1000
THROTTLE_SECONDS = 0.25
REQUEST_TIMEOUT = 30
MAX_RETRIES = 6
BACKOFF_BASE_SECONDS = 2

pattern = re.compile(r'^([a-zA-Z]+)(\d+)(?:no(\d+))?$')

NON_ARTICLE_TYPE_KEYWORDS = [
    "cover",
    "front matter",
    "back matter",
    "front cover",
    "back cover",
    "masthead",
    "table of contents",
    "contents",
    "index",
    "editorial board",
    "issue information",
    "issue cover",
    "cover and front matter",
    "ofc",
    "ifc",
    "obc",
    "ibc",
]

MONTH_NAMES = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}

CROSSREF_MAILTO = os.getenv("CROSSREF_MAILTO", "").strip()

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        f"JournalIndexing/1.0"
        f"{' (mailto:' + CROSSREF_MAILTO + ')' if CROSSREF_MAILTO else ''}"
    )
})

os.makedirs(results_folder, exist_ok=True)


def normalize_text(value):
    if value is None:
        return ""

    value = str(value)
    value = html.unescape(value)
    value = value.replace('\\"', '"')
    value = value.replace("\\/", "/")
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("’", "'").replace("“", '"').replace("”", '"')
    value = value.translate(SPECIAL_CHAR_MAP)
    value = re.sub(r"\s+", " ", value).strip()

    return value


def parse_folder_name(folder_name):
    match = pattern.match(folder_name)
    if not match:
        return None

    journal_key, volume_part, issue_start, issue_end = match.groups()
    volume = str(int(volume_part))

    issues = None
    if issue_start:
        if issue_end:
            start_num = int(issue_start)
            end_num = int(issue_end)
            if end_num < start_num:
                start_num, end_num = end_num, start_num
            issues = [str(i) for i in range(start_num, end_num + 1)]
        else:
            issues = [str(int(issue_start))]

    return {
        "journal_key": journal_key,
        "volume": volume,
        "issues": issues
    }


def request_with_retry(url, params=None, allow_redirects=True, method="get", timeout=REQUEST_TIMEOUT):
    for attempt in range(MAX_RETRIES):
        try:
            if method.lower() == "head":
                response = SESSION.head(
                    url,
                    params=params,
                    allow_redirects=allow_redirects,
                    timeout=timeout
                )
            else:
                response = SESSION.get(
                    url,
                    params=params,
                    allow_redirects=allow_redirects,
                    timeout=timeout
                )

            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        sleep_time = max(float(retry_after), THROTTLE_SECONDS)
                    except ValueError:
                        sleep_time = BACKOFF_BASE_SECONDS * (2 ** attempt)
                else:
                    sleep_time = BACKOFF_BASE_SECONDS * (2 ** attempt)

                print(f"429 Too Many Requests. Sleeping for {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
                continue

            response.raise_for_status()
            return response

        except requests.exceptions.RequestException as e:
            if attempt == MAX_RETRIES - 1:
                raise e

            sleep_time = BACKOFF_BASE_SECONDS * (2 ** attempt)
            print(f"Request failed ({e}). Retrying in {sleep_time:.2f} seconds...")
            time.sleep(sleep_time)

    raise RuntimeError("Request failed after maximum retries")


def fetch_all_results_cursor(issn):
    all_items = []
    cursor = "*"

    while True:
        params = {
            "filter": f"issn:{issn}",
            "rows": ROWS,
            "cursor": cursor,
            "select": ",".join([
                "DOI",
                "title",
                "page",
                "volume",
                "issue",
                "author",
                "container-title",
                "published-online",
                "issued"
            ])
        }

        if CROSSREF_MAILTO:
            params["mailto"] = CROSSREF_MAILTO

        response = request_with_retry(BASE_URL, params=params, method="get", timeout=REQUEST_TIMEOUT)
        data = response.json()

        message = data.get("message", {})
        items = message.get("items", [])

        if not items:
            break

        all_items.extend(items)

        cursor = message.get("next-cursor")
        if not cursor:
            break

        time.sleep(THROTTLE_SECONDS)

    return all_items


def fetch_journal_title_from_crossref(issn):
    issn = normalize_text(issn)
    if not issn:
        return ""

    params = {}
    if CROSSREF_MAILTO:
        params["mailto"] = CROSSREF_MAILTO

    try:
        response = request_with_retry(
            f"{JOURNAL_BASE_URL}/{issn}",
            params=params,
            method="get",
            timeout=REQUEST_TIMEOUT
        )
        data = response.json()
        return normalize_text(data.get("message", {}).get("title", ""))
    except Exception:
        return ""


def is_container_doi(doi):
    doi = normalize_text(doi)
    return bool(re.search(r"\.v\d+\.\d+$", doi, flags=re.IGNORECASE))


def contains_non_article_keyword(text):
    text = normalize_text(text).lower()
    if not text:
        return False

    for keyword in NON_ARTICLE_TYPE_KEYWORDS:
        if keyword in text:
            return True

    return False


def is_non_article_title(title):
    title = normalize_text(title).lower()

    blocked_patterns = [
        r"^cover$",
        r"^front matter$",
        r"^back matter$",
        r"^front cover$",
        r"^back cover$",
        r"^masthead$",
        r"^table of contents$",
        r"^index$",
        r"^editorial board$",
        r"^cover and front matter$",
        r"^.*cover and front matter$",
        r"^.*front matter$",
        r"^.*back matter$",

    ]

    return any(re.search(p, title) for p in blocked_patterns)


def get_start_page(page_range):
    page_range = normalize_text(page_range)
    return page_range.split("-")[0].strip() if page_range else ""


def page_sort_key(item):
    page_range = normalize_text(item.get("page", ""))
    title_list = item.get("title", [])
    title = normalize_text(title_list[0]) if title_list else ""
    doi = normalize_text(item.get("DOI", ""))

    if page_range:
        num = re.search(r"\d+", page_range)
        return (0, int(num.group()) if num else 0, title.lower(), doi.lower())

    return (1, float("inf"), title.lower(), doi.lower())


def extract_creators(item):
    creators = []

    for author in item.get("author", []):
        family = normalize_text(author.get("family", ""))
        given = normalize_text(author.get("given", ""))
        literal = normalize_text(author.get("literal", ""))

        if literal:
            name = literal
        else:
            name = ", ".join(filter(None, [family, given]))

        if name:
            creators.append(name)

    return creators


def build_external_url(doi):
    doi = normalize_text(doi)
    if not doi:
        return ""

    doi_url = f"https://doi.org/{doi}"

    try:
        response = SESSION.head(
            doi_url,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT
        )
        final_url = normalize_text(response.url)
        if final_url:
            return final_url.rstrip("/")
    except Exception:
        pass

    try:
        response = SESSION.get(
            doi_url,
            allow_redirects=True,
            timeout=REQUEST_TIMEOUT
        )
        final_url = normalize_text(response.url)
        if final_url:
            return final_url.rstrip("/")
    except Exception:
        pass

    return doi_url


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


def filter_items(items, volume, issues=None):
    filtered = []

    allowed_issues = None
    if issues:
        allowed_issues = {str(int(issue)) for issue in issues}

    for item in items:
        if not is_valid_article_record(item):
            continue

        item_volume = normalize_text(item.get("volume", ""))
        item_issue = normalize_text(item.get("issue", ""))

        if item_volume != str(volume):
            continue

        if allowed_issues is not None:
            normalized_item_issue = None
            if item_issue.isdigit():
                normalized_item_issue = str(int(item_issue))
            elif item_issue:
                issue_match = re.search(r"\d+", item_issue)
                if issue_match:
                    normalized_item_issue = str(int(issue_match.group()))

            if normalized_item_issue not in allowed_issues:
                continue

        filtered.append(item)

    return filtered


def extract_date_parts(item):
    for field_name in ("published-online", "issued"):
        date_part = item.get(field_name, {})
        date_parts = date_part.get("date-parts", [])

        if (
            isinstance(date_parts, list)
            and date_parts
            and isinstance(date_parts[0], list)
            and date_parts[0]
        ):
            parts = date_parts[0]
            year = parts[0] if len(parts) >= 1 else None
            month = parts[1] if len(parts) >= 2 else None
            day = parts[2] if len(parts) >= 3 else None
            return year, month, day

    return None, None, None


def format_date_parts(year, month):
    if year and month in MONTH_NAMES:
        return f"{MONTH_NAMES[month]} {year}"
    if year:
        return str(year)
    return ""


def derive_output_date(filtered_items):
    if not filtered_items:
        return ""

    dated_items = []
    for item in filtered_items:
        year, month, _ = extract_date_parts(item)
        if year:
            dated_items.append((year, month))

    if not dated_items:
        return ""

    dated_items.sort(key=lambda x: (x[0], x[1] or 0), reverse=True)
    year, month = dated_items[0]
    return format_date_parts(year, month)


def derive_journal_title(filtered_items, issn):
    title = fetch_journal_title_from_crossref(issn)
    if title:
        return title

    for item in filtered_items:
        container_titles = item.get("container-title", [])
        if container_titles:
            container_title = normalize_text(container_titles[0])
            if container_title:
                return container_title

    return ""


def build_section_data(item):
    doi = normalize_text(item.get("DOI", ""))
    title_list = item.get("title", [])
    article_title = normalize_text(title_list[0]) if title_list else ""

    return {
        "title": article_title,
        "type": "",
        "citation": "",
        "description": "",
        "doi": doi,
        "external_url": build_external_url(doi),
        "authors": extract_creators(item)
    }


def build_json_structure(filtered_items, volume, issn, issues=None):
    pages = []
    sections = {}

    for i, item in enumerate(sorted(filtered_items, key=page_sort_key), 1):
        start_page = get_start_page(item.get("page", "")) or "0"

        pages.append({
            "id": i,
            "native": start_page,
        })

        sections[str(i)] = build_section_data(item)

    journal_title = derive_journal_title(filtered_items, issn)

    output = {
        "title": journal_title,
        "volume": str(volume),
        "date": derive_output_date(filtered_items),
        "pages": pages,
        "sections": sections
    }

    if issues:
        output["issue"] = issues[0] if len(issues) == 1 else issues

    return output


def write_json_safely(data, filename):
    with NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
        json.dump(data, tmp, ensure_ascii=False, indent=2)
        temp_name = tmp.name
    os.replace(temp_name, filename)

def process_folder(folder_name, folder_path):
    if not os.path.isdir(folder_path):
        logger.error("Folder does not exist or is not a directory: %s", folder_path)
        return False

    parsed = parse_folder_name(folder_name)
    if not parsed:
        logger.warning("Skipping folder with unsupported name format: %s", folder_name)
        return False

    journal_key = parsed["journal_key"]
    volume = parsed["volume"]
    issues = parsed["issues"]

    if journal_key not in journal_issn_dict:
        logger.warning("Skipping folder with unknown journal key: %s", folder_name)
        return False

    issn = journal_issn_dict[journal_key]
    output_file = os.path.join(results_folder, f"{folder_name}.json")

    issue_display = ", ".join(issues) if issues else "N/A"

    logger.info(
        "Running folder=%s path=%s volume=%s issue=%s output=%s",
        folder_name,
        folder_path,
        volume,
        issue_display,
        output_file,
    )
    print(f"\nProcessing {folder_name}, Volume={volume}, Issue={issue_display}")

    try:
        all_items = fetch_all_results_cursor(issn)
        filtered_items = filter_items(all_items, volume, issues)

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

        output = build_json_structure(filtered_items, volume, issn, issues)
        write_json_safely(output, output_file)

        logger.info("Saved result for folder=%s to %s", folder_name, output_file)
        print(f"Saved to {output_file}")
        return True

    except Exception:
        logger.exception("Failed while processing folder=%s path=%s", folder_name, folder_path)
        print(f"Error while processing {folder_name}. Check logs for details.")
        return False