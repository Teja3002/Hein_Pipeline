from difflib import SequenceMatcher
from unidecode import unidecode 

SOURCE_PRIORITY = ["crossref", "webscraper", "llm"]

# Fuzzy matching: Use Python's built-in difflib.SequenceMatcher — no extra dependency needed 
# This handles OCR errors well — "Dystopian International Law" vs "Dystopian Lnternational Law" would still score ~0.93. 
def similarity(a, b):
    """Returns 0.0 to 1.0 similarity score between two strings."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()

# Refine text
# >>> unidecode('kožušček')
# 'kozuscek'
def refine_text(text: str) -> str:
    """Converts unicode/accented characters to plain ASCII."""
    if not text:
        return text
    return unidecode(text.strip())

# Creates a copy of the section data 
def collect_all_sections(sources):
    """
    Extracts sections from each source into a flat list with source tags.

    Returns:
        list of dicts: [{source, key, data}, ...]
    """
    all_sections = []

    for source_name in SOURCE_PRIORITY:
        if source_name not in sources:
            continue
        sections = sources[source_name].get("sections", {})
        for key, data in sections.items():
            all_sections.append({
                "source": source_name,
                "key": key,
                "data": data
            })

    return all_sections

# Match with DOI's directly first and then do a similarity check 
def match_by_doi(all_sections):
    """
    Groups sections that share the exact same DOI.
    Each group has at most one entry per source.
    """
    matched_groups = []
    used = set()

    for i, section_a in enumerate(all_sections):
        if i in used:
            continue

        doi_a = section_a["data"].get("doi", "")
        if not doi_a:
            continue

        group = [section_a]
        used.add(i)

        for j, section_b in enumerate(all_sections):
            if j in used:
                continue

            if section_b["source"] in [g["source"] for g in group]:
                continue

            doi_b = section_b["data"].get("doi", "")
            if not doi_b:
                continue

            if doi_a.lower().strip() == doi_b.lower().strip():
                group.append(section_b)
                used.add(j)

        if len(group) > 1:
            matched_groups.append(group)
        elif len(group) == 1:
            used.discard(i)

    unmatched = [s for i, s in enumerate(all_sections) if i not in used]

    return matched_groups, unmatched


def merge_single_section(group):
    """
    Merges a group of matched sections by priority.
    Crossref > Webscraper > LLM.

    Args:
        group: list of {source, key, data} dicts

    Returns:
        dict: merged section
    """
    # Sort group by priority
    priority_order = {s: i for i, s in enumerate(SOURCE_PRIORITY)}
    group.sort(key=lambda x: priority_order.get(x["source"], 99))

    section = {
        "title": "",
        "type": "",
        "citation": "",
        "description": "",
        # "doi": "",
        # "external_url": "",
        "authors": []
    }

    # # For each field, take first non-empty by priority
    # for field in ["title", "type", "citation", "description", "doi", "external_url"]:
    #     for entry in group:
    #         value = entry["data"].get(field, "")
    #         if value:
    #             section[field] = value
    #             break

    # doi — no refinement needed
    for entry in group:
        value = entry["data"].get("doi", "")
        if value:
            section["doi"] = value
            break

    # title — refine to ASCII
    for entry in group:
        value = entry["data"].get("title", "")
        if value:
            section["title"] = refine_text(value)
            break

    # Take authors from highest priority source that has them
    section["authors"] = []
    for entry in group:  # group is already sorted by priority
        authors = entry["data"].get("authors", []) or []
        if authors:
            section["authors"] = [refine_text(a) for a in authors if a]
            break  # stop at first non-empty — highest priority wins 

    return section


def fill_empty_fields(base_section, new_section, source_name):
    """
    Fills empty fields in base_section from new_section.
    Also adds new fields that don't exist in base.
    For authors, takes the longest list.
    """
    # KNOWN_FIELDS = ["title", "type", "citation", "description", "doi", "external_url"]

    # Fill known empty fields
    # for field in KNOWN_FIELDS:
    #     if not base_section.get(field, "") and new_section.get(field, ""):
    #         base_section[field] = new_section[field]

    # Add any extra fields from new_section that base doesn't have
    # for field, value in new_section.items():
    #     if field not in base_section and value:
    #         base_section[field] = value
    #         print(f"        + Added new field '{field}' from {source_name}")

    # title — fill if empty, refine to ASCII
    if not base_section.get("title", "") and new_section.get("title", ""):
        base_section["title"] = refine_text(new_section["title"])

    # doi — fill if empty, no refinement needed
    if not base_section.get("doi", "") and new_section.get("doi", ""):
        base_section["doi"] = new_section["doi"]

    # For authors, take longest list
    base_authors = base_section.get("authors", []) or []
    new_authors = new_section.get("authors", []) or []
    if not base_authors and new_authors:
        base_section["authors"] = [refine_text(a) for a in new_authors if a]


def match_and_merge(base, new_sections, source_name):
    """
    Matches new_sections against base by exact DOI.
    Merges matched ones into base, returns unmatched.
    """
    unmatched = []

    for key, new_section in new_sections.items():
        new_doi = new_section.get("doi", "").lower().strip()

        matched = False

        if new_doi:
            for base_key, base_section in base.items():
                base_doi = base_section.get("doi", "").lower().strip()
                if base_doi and new_doi == base_doi:
                    fill_empty_fields(base_section, new_section, source_name)
                    matched = True
                    print(f"      ✓ DOI match: \"{(base_section.get('title') or 'N/A')[:50]}...\" ({source_name})")
                    break

        if not matched:
            unmatched.append(new_section)
            print(f"      - Unmatched: \"{(new_section.get('title') or 'N/A')[:50]}...\" ({source_name})")

    return unmatched

# Check similarity and if once title is fully contained in the other title 
def match_unmatched_by_title(merged, unmatched_sections, source_name, threshold=0.85):
    still_unmatched = []

    for section in unmatched_sections:
        new_title = (section.get("title") or "").strip()

        if not new_title:
            print(f"      ✗ Skipped: no title ({source_name})")
            continue

        matched = False

        for base_key, base_section in merged.items():
            base_title = (base_section.get("title") or "").strip()
            if not base_title:
                continue

            score = similarity(new_title, base_title)

            # Also check if one title contains the other
            contains = (new_title.lower() in base_title.lower()) or (base_title.lower() in new_title.lower())

            if score >= threshold or contains:
                fill_empty_fields(base_section, section, source_name)
                matched = True
                match_type = "contains" if contains and score < threshold else f"{score:.0%}"
                print(f"      ✓ Title match ({match_type}): \"{new_title[:50]}...\" → \"{base_title[:50]}...\" ({source_name})")
                break

        if not matched:
            still_unmatched.append(section)
            print(f"      - No match: \"{new_title[:50]}...\" ({source_name})")

    return still_unmatched


def _find_original_key(sections, target_section):
    """Finds the original key of a section in its source."""
    target_title = (target_section.get("title") or "").lower()
    target_doi = (target_section.get("doi") or "").lower()

    for key, section in sections.items():
        if target_doi and (section.get("doi") or "").lower() == target_doi:
            return key
        if target_title and (section.get("title") or "").lower() == target_title:
            return key
    return None

def deduplicate_unmatched(sections, threshold=0.85):
    """Removes duplicates within unmatched sections."""
    unique = []

    for section in sections:
        title = (section.get("title") or "").strip()
        if not title:
            continue

        is_duplicate = False
        for existing in unique:
            existing_title = (existing.get("title") or "").strip()
            score = similarity(title, existing_title)
            contains = (title.lower() in existing_title.lower()) or (existing_title.lower() in title.lower())

            if score >= threshold or contains:
                is_duplicate = True
                print(f"      ✗ Duplicate removed: \"{title[:50]}...\"")
                break

        if not is_duplicate:
            unique.append(section)

    return unique


def merge_sections(sources):
    crossref_sections = sources.get("crossref", {}).get("sections", {})
    webscraper_sections = sources.get("webscraper", {}).get("sections", {})
    llm_sections = sources.get("llm", {}).get("sections", {})

    print(f"    crossref: {len(crossref_sections)} sections")
    print(f"    webscraper: {len(webscraper_sections)} sections")
    print(f"    llm: {len(llm_sections)} sections")

    # Step 1: Start with crossref as base
    merged = {}
    for key, section in crossref_sections.items():
        refined = dict(section)
        if refined.get("title"):
            refined["title"] = refine_text(refined["title"])
        if refined.get("authors"):
            refined["authors"] = [refine_text(a) for a in refined["authors"] if a]
        merged[key] = refined

    # Step 2: Match webscraper by DOI
    print(f"\n    Matching webscraper by DOI...")
    unmatched_webscraper = match_and_merge(merged, webscraper_sections, "webscraper")
    print(f"    Unmatched webscraper after DOI: {len(unmatched_webscraper)}")

    # Step 3: Match webscraper leftovers by title
    if unmatched_webscraper:
        print(f"\n    Matching webscraper by title...")
        unmatched_webscraper = match_unmatched_by_title(merged, unmatched_webscraper, "webscraper")
        print(f"    Unmatched webscraper after title: {len(unmatched_webscraper)}")

    # Step 4: Match llm by DOI
    print(f"\n    Matching llm by DOI...")
    unmatched_llm = match_and_merge(merged, llm_sections, "llm")
    print(f"    Unmatched llm after DOI: {len(unmatched_llm)}")

    # Step 5: Match llm leftovers by title
    if unmatched_llm:
        print(f"\n    Matching llm by title...")
        unmatched_llm = match_unmatched_by_title(merged, unmatched_llm, "llm")
        print(f"    Unmatched llm after title: {len(unmatched_llm)}")

    # Step 6: Deduplicate, add unmatched, and track their origin
    unmatched_all = deduplicate_unmatched(unmatched_webscraper + unmatched_llm)

    unmatched_map = {}
    next_key = len(merged) + 1

    for section in unmatched_all:
        title = (section.get("title") or "").strip()
        if title:
            original_key = _find_original_key(webscraper_sections, section)
            source = "webscraper"
            if not original_key:
                original_key = _find_original_key(llm_sections, section)
                source = "llm"

            merged[str(next_key)] = section
            unmatched_map[str(next_key)] = (source, original_key)
            print(f"      + New section: \"{title[:50]}...\" ({source})")
            next_key += 1

    print(f"\n    Final merged sections: {len(merged)}")

    return merged, unmatched_map