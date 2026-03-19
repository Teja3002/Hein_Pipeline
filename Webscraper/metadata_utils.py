import re
from collections import defaultdict


# ======================================
# Extract ONLY citation-related metadata
# ======================================
def extract_citation_metadata(soup):

    meta_data = defaultdict(list)

    for tag in soup.find_all("meta"):

        key = tag.get("name") or tag.get("property")
        value = tag.get("content")

        if not key or not value:
            continue

        key_lower = key.lower()

        # accept citation OR dc.*
        if re.search(r"citation", key_lower) or key_lower.startswith("dc."):
            meta_data[key_lower].append(value)

    cleaned = {}
    for k, v in meta_data.items():
        cleaned[k] = v if len(v) > 1 else v[0]

    return cleaned


# ======================================
# Article detector
# ======================================
def is_article(meta):
    return len(meta) > 0


# ======================================
# Priority regex matcher
# ======================================
def find_priority(meta, patterns):

    for pattern in patterns:
        for key, value in meta.items():
            if re.search(pattern, key, re.IGNORECASE):
                return value
    return None


# ======================================
# Normalize metadata
# ======================================
def normalize_metadata(meta, journal_name):

    authors = []
    affiliations = []

    for key, value in meta.items():

        if re.search(r"author$", key):
            if isinstance(value, list):
                authors.extend(value)
            else:
                authors.append(value)

        if re.search(r"author_institution|affiliation", key):
            if isinstance(value, list):
                affiliations.extend(value)
            else:
                affiliations.append(value)

    return {
        "journal": journal_name,
        "journal_title": find_priority(meta, [r"journal_title"]),

        "title": find_priority(meta, [
            r"citation_title$",
            r"_citation_title$",
        ]),

        "authors": authors if authors else None,
        "author_affiliation": affiliations if affiliations else None,

        "doi": find_priority(meta, [
            r"citation_doi",
            r"doi",
            r"dc.identifier"
        ]),

        "issn": find_priority(meta, [r"issn"]),

        "volume": find_priority(meta, [r"volume"]),
        "issue": find_priority(meta, [r"issue"]),
        "first_page": find_priority(meta, [r"firstpage"]),
        "last_page": find_priority(meta, [r"lastpage"]),

        "publication_date": find_priority(meta, [r"publication_date"]),
        "online_date": find_priority(meta, [r"online_date"]),
        "year": find_priority(meta, [r"year", r"date"]),

        "publisher": find_priority(meta, [r"publisher"]),

        "abstract": find_priority(meta, [r"abstract"]),
        "keywords": find_priority(meta, [r"keyword"]),

        "pdf_url": find_priority(meta, [r"pdf_url"]),
        "article_url": find_priority(meta, [r"abstract_html_url"]),

        "is_cover_page": find_priority(meta, [r"cover_page"]),
    }


# ======================================
# Weighted scoring
# ======================================
def metadata_score(meta):

    weights = {
        "doi": 5,
        "title": 4,
        "authors": 4,
        "abstract": 3,
        "journal_title": 2,
        "volume": 2,
        "issue": 2,
        "first_page": 2,
        "publication_date": 2,
        "keywords": 1,
        "pdf_url": 1,
    }

    score = 0

    for field, w in weights.items():
        if meta.get(field):
            score += w

    return score