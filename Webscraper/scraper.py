import json
import logging
import os
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

try:
    from .journals import JOURNALS
    from .metadata_utils import (
        extract_citation_metadata,
        is_article,
        normalize_metadata,
        metadata_score,
    )
except ImportError:
    from journals import JOURNALS
    from metadata_utils import (
        extract_citation_metadata,
        is_article,
        normalize_metadata,
        metadata_score,
    )

HEADERS = {"User-Agent": "Mozilla/5.0"}
MAX_DEPTH = 5
logger = logging.getLogger(__name__)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
DEFAULT_RESULTS_DIR = os.path.join(SCRIPT_DIR, "results")

SKIP_PATTERNS = ["login", "contact", "about", "terms", "privacy", "signup", "register"]

SKIP_EXTENSIONS = [".pdf", ".jpg", ".jpeg", ".png", ".zip", ".gif", ".svg", ".css", ".js"]


# ======================================
# Detect if URL is a domain-only URL
# ======================================
def is_domain_only(url):
    path = urlparse(url).path
    return path in ("", "/") or path.lower() in ("/index.html", "/home")


# ======================================
# Recursive crawler
# ======================================
def crawl(url, base_domain, base_path, journal_name, visited, articles, depth=0):

    if depth > MAX_DEPTH:
        return

    if url in visited:
        return

    visited.add(url)

    logger.info("Webscraper visiting journal=%s depth=%s url=%s", journal_name, depth, url)
    print("  " * depth + f"Visiting: {url}")

    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            logger.warning(
                "Webscraper received non-200 response journal=%s url=%s status=%s",
                journal_name,
                url,
                r.status_code,
            )
            return
    except Exception as e:
        logger.exception("Webscraper request failed journal=%s url=%s", journal_name, url)
        print("  " * depth + f"Error: {e}")
        return

    soup = BeautifulSoup(r.text, "html.parser")

    meta = extract_citation_metadata(soup)

    # Check if article and score it
    if is_article(meta):
        clean_meta = normalize_metadata(meta, journal_name)
        score = metadata_score(clean_meta)

        if score >= 8:
            clean_meta["score"] = score
            articles[url] = clean_meta
            logger.info(
                "Webscraper article found journal=%s url=%s score=%s",
                journal_name,
                url,
                score,
            )
            print("  " * depth + f"ARTICLE FOUND (score={score})")
        else:
            logger.info(
                "Webscraper skipped low-score page journal=%s url=%s score=%s",
                journal_name,
                url,
                score,
            )
            print("  " * depth + f"SKIPPED (low score={score})")

    # Follow all links on the page
    for a in soup.find_all("a", href=True):

        next_url = urljoin(url, a["href"])
        next_url = next_url.split("#")[0]  # strip fragments
        next_url = next_url.strip()

        if not next_url.startswith("http"):
            continue

        parsed_next = urlparse(next_url)

        # Guard 1: stay on same domain
        if parsed_next.netloc != base_domain:
            continue

        # Guard 2: if a specific path was given, stay within it
        # if domain-only URL was given, base_path is None so skip this check
        if base_path and not parsed_next.path.startswith(base_path):
            continue

        # Guard 3: skip binary/static files
        if any(next_url.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
            continue

        # Guard 4: skip obviously useless pages
        if any(p in next_url.lower() for p in SKIP_PATTERNS):
            continue

        # Guard 5: already visited
        if next_url in visited:
            continue

        crawl(next_url, base_domain, base_path, journal_name, visited, articles, depth + 1)


def fetch_page(url, journal_name, context):
    logger.info("Webscraper fetching %s journal=%s url=%s", context, journal_name, url)

    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        response.raise_for_status()
        return response
    except Exception:
        logger.exception("Webscraper request failed during %s journal=%s url=%s", context, journal_name, url)
        return None


def inspect_article_url(url, journal_name):
    response = fetch_page(url, journal_name, "article-check")
    if response is None:
        return None, False

    soup = BeautifulSoup(response.text, "html.parser")
    meta = extract_citation_metadata(soup)

    if not is_article(meta):
        logger.warning("Webscraper found non-article page journal=%s url=%s", journal_name, url)
        return None, False

    clean_meta = normalize_metadata(meta, journal_name)
    score = metadata_score(clean_meta)
    clean_meta["score"] = score

    logger.info(
        "Webscraper inspected DOI landing page journal=%s url=%s score=%s",
        journal_name,
        url,
        score,
    )
    return clean_meta, True


def resolve_doi_url(doi):
    doi = doi.strip()
    doi_url = f"https://doi.org/{doi}"

    try:
        response = requests.get(doi_url, headers=HEADERS, timeout=20, allow_redirects=True)
        response.raise_for_status()
        final_url = response.url
        logger.info("Resolved DOI %s to %s", doi, final_url)
        return final_url
    except Exception:
        logger.exception("Failed to resolve DOI %s", doi)
        return None


def load_dois_from_crossref_result(result_file):
    with open(result_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    dois = []
    for section in data.get("sections", {}).values():
        doi = section.get("doi")
        if doi:
            dois.append(doi.strip())

    unique_dois = list(dict.fromkeys(dois))
    logger.info("Loaded %s unique DOI(s) from %s", len(unique_dois), result_file)
    return unique_dois


def article_sort_key(item):
    url, metadata = item
    first_page = metadata.get("first_page")
    title = (metadata.get("title") or "").lower()
    doi = (metadata.get("doi") or "").lower()

    if first_page and str(first_page).isdigit():
        return (0, int(first_page), title, doi, url)

    return (1, float("inf"), title, doi, url)


def extract_page_id_from_url(url):
    match = re.search(r"/(\d+)/?$", urlparse(url).path)
    if match:
        return int(match.group(1))
    return ""


def build_page_entry(url, metadata, page_id):
    volume = metadata.get("volume")
    issue = metadata.get("issue")

    return {
        "id": page_id,
        "native": metadata.get("first_page") or "",
        "section": [
            int(volume) if str(volume).isdigit() else volume or "",
            int(issue) if str(issue).isdigit() else issue or "",
        ],
    }


def format_articles_as_sections(articles, page_id_mode="sequential"):
    pages = []
    sections = {}

    for index, (url, metadata) in enumerate(sorted(articles.items(), key=article_sort_key), 1):
        authors = metadata.get("authors") or []

        if page_id_mode == "url_tail":
            page_id = extract_page_id_from_url(url)
        else:
            page_id = index

        pages.append(build_page_entry(url, metadata, page_id))
        section = {
            "title": metadata.get("title") or "",
            "citation": "",
            "description": metadata.get("abstract") or "",
            "doi": metadata.get("doi") or "",
            "external_url": metadata.get("article_url") or url,
            "authors": authors,
        }

        sections[str(index)] = section

    if page_id_mode == "url_tail":
        pages.sort(
            key=lambda page: (
                0 if isinstance(page["id"], int) else 1,
                page["id"] if isinstance(page["id"], int) else str(page["id"]),
            )
        )

    return {"pages": pages, "sections": sections}


def write_raw_output(folder_name, articles, output_dir=None):
    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_DIR

    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{folder_name}.json")

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(articles, f, indent=4, ensure_ascii=False)

    logger.info("Webscraper saved raw output folder=%s output=%s article_count=%s", folder_name, output_file, len(articles))
    return output_file


def write_results_output(folder_name, articles, results_dir=None, page_id_mode="sequential"):
    if results_dir is None:
        results_dir = DEFAULT_RESULTS_DIR

    os.makedirs(results_dir, exist_ok=True)
    result_file = os.path.join(results_dir, f"{folder_name}.json")
    formatted_output = format_articles_as_sections(articles, page_id_mode=page_id_mode)

    with open(result_file, "w", encoding="utf-8") as f:
        json.dump(formatted_output, f, indent=2, ensure_ascii=False)

    logger.info("Webscraper saved formatted results folder=%s output=%s section_count=%s", folder_name, result_file, len(articles))
    return result_file


def build_null_article_record(folder_name, doi, external_url):
    return {
        "journal": folder_name,
        "journal_title": None,
        "title": None,
        "authors": None,
        "author_affiliation": None,
        "doi": doi,
        "issn": None,
        "volume": None,
        "issue": None,
        "first_page": None,
        "last_page": None,
        "publication_date": None,
        "online_date": None,
        "year": None,
        "publisher": None,
        "abstract": None,
        "keywords": None,
        "pdf_url": None,
        "article_url": external_url,
        "is_cover_page": None,
        "score": None,
    }


def scrape_from_crossref_result(folder_name, result_file, output_dir=None, results_dir=None):
    logger.info("Webscraper started for folder=%s using CrossRef file=%s", folder_name, result_file)

    if not os.path.exists(result_file):
        logger.warning("Webscraper skipped folder=%s because CrossRef result file does not exist", folder_name)
        return None

    dois = load_dois_from_crossref_result(result_file)
    if not dois:
        logger.warning("Webscraper skipped folder=%s because no DOI values were found", folder_name)
        return None

    articles = {}

    for doi in dois:
        logger.info("Webscraper resolving DOI for folder=%s doi=%s", folder_name, doi)
        start_url = resolve_doi_url(doi)
        if not start_url:
            logger.warning("Webscraper could not resolve DOI for folder=%s doi=%s; recording null article", folder_name, doi)
            articles[f"https://doi.org/{doi}"] = build_null_article_record(folder_name, doi, None)
            continue

        article_data, is_article_page = inspect_article_url(start_url, folder_name)
        if is_article_page and article_data is not None:
            article_data["article_url"] = article_data.get("article_url") or start_url
            articles[start_url] = article_data
        else:
            logger.warning(
                "Webscraper DOI landing page is not an article for folder=%s doi=%s; recording null article",
                folder_name,
                doi,
            )
            articles[start_url] = build_null_article_record(folder_name, doi, start_url)

    if not articles:
        logger.warning("Webscraper found no article records for folder=%s after processing DOI list", folder_name)
        return None

    raw_output_file = write_raw_output(folder_name, articles, output_dir=output_dir)
    results_output_file = write_results_output(
        folder_name,
        articles,
        results_dir=results_dir,
        page_id_mode="sequential",
    )
    return {"raw_output_file": raw_output_file, "results_output_file": results_output_file}


def scrape_without_crossref(folder_name):
    logger.info(
        "Webscraper placeholder reached for folder=%s because no CrossRef result is available yet",
        folder_name,
    )
    return None


# ======================================
# MAIN
# ======================================
if __name__ == "__main__":

    os.makedirs("output", exist_ok=True)

    for journal_name, start_url in JOURNALS.items():

        print(f"\n===== Crawling {journal_name} =====")

        visited = set()
        articles = {}

        parsed = urlparse(start_url)
        domain = parsed.netloc

        # If a specific path is given, lock crawl to that path
        # If it's a domain-only URL, base_path = None (crawl everything)
        if is_domain_only(start_url):
            base_path = None
            print(f"Mode: Full site crawl ({domain})")
        else:
            base_path = parsed.path
            print(f"Mode: Path-scoped crawl ({domain}{base_path})")

        crawl(start_url, domain, base_path, journal_name, visited, articles)

        output_file = f"output/{journal_name}.json"

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(articles, f, indent=4, ensure_ascii=False)

        print(f"\nSaved → {output_file}")
        print(f"Pages visited : {len(visited)}")
        print(f"Articles found: {len(articles)}")
