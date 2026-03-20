import re
import sys
import os
import logging
from pathlib import Path

# Import journal config from the same directory
import json

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from Utilities.app_logging import setup_logging

KNOWN_JOURNALS_PATH = SCRIPT_DIR / "known_journals.json"
logger = logging.getLogger(__name__)

with KNOWN_JOURNALS_PATH.open(encoding="utf-8") as f:
    JOURNALS = json.load(f)


def parse_input(input_str: str) -> dict:
    """
    Parse input string like 'mijoeqv0015no1' into components.

    Format: <journal_name><4-digit-volume>[no<issue_number>]
      - journal_name : alphabetic prefix (variable length)
      - volume       : exactly 4 digits following the journal name
      - issue_no     : digits after 'no' (optional)

    Returns a dict with keys: journal, volume, issue_no
    """
    pattern = r'^([a-zA-Z]+)(\d{4})(?:no(\d+))?$'
    match = re.match(pattern, input_str.strip())

    if not match:
        raise ValueError(
            f"Input '{input_str}' does not match expected format "
            f"(e.g. 'mijoeqv0015no1' or 'mijoeqv0015')."
        )

    journal  = match.group(1)    # alphabetic prefix
    volume   = match.group(2)    # always 4 digits
    issue_no = match.group(3)    # None if not present

    return {
        "journal":  journal,
        "volume":   volume,
        "issue_no": issue_no,
    }


def find_journal_config(journal_name: str) -> tuple[str, dict] | None:
    """
    Search JOURNALS dict for an entry whose 'journal_name' field matches journal_name.
    Returns (base_url, config_dict) or None if not found.
    """
    for base_url, config in JOURNALS.items():
        if config.get("journal_name") == journal_name:
            return base_url, config
    return None


def build_url(base_url: str, pattern: str, volume: str, issue_no: str | None) -> str:
    """
    Build the final URL from base_url + pattern, filling in volume and issue.

    Placeholder positions in a 3-slot pattern: vol{} / iss{} / article{}
      Slot 1 = volume  (always filled)
      Slot 2 = issue   (filled if issue_no present, otherwise dropped)
      Slot 3 = article (always dropped — we have no article data)

    For a 2-slot pattern: vol{} / iss{}
      Slot 1 = volume
      Slot 2 = issue (filled if present, otherwise dropped)

    base_url is used for scheme + host only.
    """
    from urllib.parse import urlparse

    vol = int(volume)  # strip leading zeros
    domain = f"{urlparse(base_url).scheme}://{urlparse(base_url).netloc}"

    # Split pattern into segments on '/' so we can drop slots cleanly
    # e.g. "/mbelr/vol{}/iss{}/{}/" → ['', 'mbelr', 'vol{}', 'iss{}', '{}', '']
    segments = pattern.split("/")

    # Identify which segments contain a placeholder
    slot_indices = [i for i, s in enumerate(segments) if "{}" in s]
    # slot_indices[0] = volume, slot_indices[1] = issue, slot_indices[2] = article (if 3 slots)

    if len(slot_indices) == 3:
        vol_idx, iss_idx, art_idx = slot_indices
        segments[vol_idx] = segments[vol_idx].replace("{}", str(vol))
        if issue_no is not None:
            segments[iss_idx] = segments[iss_idx].replace("{}", str(issue_no))
        else:
            segments[iss_idx] = None
        # Always drop article slot — we have no article data
        segments[art_idx] = None

    elif len(slot_indices) == 2:
        vol_idx, iss_idx = slot_indices
        segments[vol_idx] = segments[vol_idx].replace("{}", str(vol))
        if issue_no is not None:
            segments[iss_idx] = segments[iss_idx].replace("{}", str(issue_no))
        else:
            segments[iss_idx] = None

    else:
        # Single slot — just fill volume
        segments[slot_indices[0]] = segments[slot_indices[0]].replace("{}", str(vol))

    # Rebuild path, skipping dropped segments
    filled = "/".join(s for s in segments if s is not None)
    if not filled.startswith("/"):
        filled = "/" + filled
    if not filled.endswith("/"):
        filled += "/"

    return domain + filled


def process(input_str: str) -> dict:
    logger.info("databaseScrape started for input=%s", input_str)

    # Step 1 – parse
    try:
        parsed = parse_input(input_str)
    except ValueError as error:
        logger.warning(
            "Skipping databaseScrape for input=%s because name format is invalid: %s",
            input_str,
            error,
        )
        print(f"\n[!] Skipping '{input_str}': {error}")
        return {
            "status": "invalid_input",
            "journal": "",
            "url": "",
            "error": str(error),
        }

    logger.info(
        "Parsed input journal=%s volume_raw=%s issue=%s",
        parsed["journal"],
        parsed["volume"],
        parsed["issue_no"],
    )
    print(f"\nParsed input '{input_str}':")
    print(f"  Journal  : {parsed['journal']}")
    print(f"  Volume   : {parsed['volume']} (raw) -> {int(parsed['volume'])} (numeric)")
    print(f"  Issue #  : {parsed['issue_no'] if parsed['issue_no'] is not None else '(not provided)'}")

    # Step 2 – look up config
    result = find_journal_config(parsed["journal"])

    if result is None:
        fallback_url = f"https://www.google.com/search?q={parsed['journal']}+journal+volume+{int(parsed['volume'])}"
        logger.warning(
            "No journal config found for journal=%s; fallback_search_url=%s",
            parsed["journal"],
            fallback_url,
        )
        print(f"\n[!] No journal config found for journal name '{parsed['journal']}'.")
        print(f"Fallback search : {fallback_url}")
        return {
            "status": "fallback_search",
            "journal": parsed["journal"],
            "url": fallback_url,
        }

    base_url, config = result
    logger.info("Matched journal config for journal=%s base_url=%s", parsed["journal"], base_url)
    print(f"\nMatched journal config (base URL: {base_url}):")
    for key, value in config.items():
        print(f"  {key:15}: {value}")

    # Step 3 – build and print the final URL
    final_url = build_url(base_url, config["pattern"], parsed["volume"], parsed["issue_no"])
    logger.info("Built final URL for journal=%s url=%s", parsed["journal"], final_url)
    print(f"\nFinal URL        : {final_url}")
    return {
        "status": "matched",
        "journal": parsed["journal"],
        "url": final_url,
    }


if __name__ == "__main__":
    log_file = setup_logging()
    logger.info("databaseScrape process started pid=%s log_file=%s", os.getpid(), log_file)
    if len(sys.argv) < 2:
        input_str = input("Enter journal string (e.g. mijoeqv0015no1): ").strip()
    else:
        input_str = sys.argv[1]
    process(input_str)
