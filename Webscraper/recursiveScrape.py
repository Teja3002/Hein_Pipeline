import logging
import os
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
    from .scraper import write_raw_output, write_results_output
except ImportError:
    from journals import JOURNALS
    from metadata_utils import (
        extract_citation_metadata,
        is_article,
        normalize_metadata,
        metadata_score,
    )
    from scraper import write_raw_output, write_results_output

HEADERS = {"User-Agent": "Mozilla/5.0"}
MAX_DEPTH = 5
logger = logging.getLogger(__name__)

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

    logger.info("recursiveScrape visiting journal=%s depth=%s url=%s", journal_name, depth, url)
    print("  " * depth + f"Visiting: {url}")

    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            logger.warning(
                "recursiveScrape received non-200 response journal=%s url=%s status=%s",
                journal_name,
                url,
                r.status_code,
            )
            return
    except Exception as e:
        logger.exception("recursiveScrape request failed journal=%s url=%s", journal_name, url)
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
                "recursiveScrape article found journal=%s url=%s score=%s",
                journal_name,
                url,
                score,
            )
            print("  " * depth + f"ARTICLE FOUND (score={score})")
        else:
            logger.info(
                "recursiveScrape skipped low-score page journal=%s url=%s score=%s",
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


def scrape_from_database_url(folder_name, start_url, output_dir=None, results_dir=None):
    logger.info("recursiveScrape started for folder=%s start_url=%s", folder_name, start_url)

    visited = set()
    articles = {}

    parsed = urlparse(start_url)
    domain = parsed.netloc

    if is_domain_only(start_url):
        base_path = None
        logger.info("recursiveScrape using full-site crawl journal=%s domain=%s", folder_name, domain)
    else:
        base_path = parsed.path
        logger.info(
            "recursiveScrape using path-scoped crawl journal=%s domain=%s base_path=%s",
            folder_name,
            domain,
            base_path,
        )

    crawl(start_url, domain, base_path, folder_name, visited, articles)

    if not articles:
        logger.warning("recursiveScrape found no articles for folder=%s start_url=%s", folder_name, start_url)
        return None

    raw_output_file = write_raw_output(folder_name, articles, output_dir=output_dir)
    results_output_file = write_results_output(folder_name, articles, results_dir=results_dir)
    logger.info(
        "recursiveScrape completed for folder=%s raw_output=%s results_output=%s article_count=%s",
        folder_name,
        raw_output_file,
        results_output_file,
        len(articles),
    )
    return {
        "raw_output_file": raw_output_file,
        "results_output_file": results_output_file,
    }


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

        output_file = write_raw_output(journal_name, articles)
        results_file = write_results_output(journal_name, articles)

        print(f"\nSaved → {output_file}")
        print(f"Saved results → {results_file}")
        print(f"Pages visited : {len(visited)}")
        print(f"Articles found: {len(articles)}")
