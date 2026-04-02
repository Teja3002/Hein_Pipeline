import re
from datetime import datetime

# Valid month names and abbreviations
MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december"
]
MONTH_ABBREVS = [m[:3] for m in MONTHS]

# Seasonal terms that journals sometimes use
SEASONS = ["spring", "summer", "fall", "autumn", "winter"]

# Common date formats to try parsing
DATE_FORMATS = [
    "%B %Y",        # January 2026
    "%b %Y",        # Jan 2026
    "%B, %Y",       # January, 2026
    "%b, %Y",       # Jan, 2026
    "%m/%Y",        # 01/2026
    "%m-%Y",        # 01-2026
    "%Y",           # 2026
]


def verify_date(value):
    """
    Verify that the extracted date is a valid publication date.
    
    Checks:
      - Not None or empty
      - Matches a recognizable date format (Month Year, Season Year, Year only)
      - Year is within a reasonable range (1800 - 2100)
      - Not a random number or garbage string
      - Not a full datetime with day precision (journals use month/year)
    
    Returns:
        (bool, str): (is_valid, reason)
    """

    if value is None:
        return False, "Date is None"

    value_str = str(value).strip()

    if not value_str:
        return False, "Date is empty"

    value_str = value_str.strip("\"'")

    # Check for Season + Year pattern (e.g. "Spring 2025")
    season_pattern = re.compile(
        r"^(" + "|".join(SEASONS) + r")\s+(\d{4})$", re.IGNORECASE
    )
    season_match = season_pattern.match(value_str)
    if season_match:
        year = int(season_match.group(2))
        if 1800 <= year <= 2100:
            return True, "Valid (season format)"
        return False, f"Year out of range: {year}"

    # Check for Month-range + Year (e.g. "January-March 2025")
    range_pattern = re.compile(
        r"^[A-Za-z]+[-/][A-Za-z]+\s+(\d{4})$"
    )
    range_match = range_pattern.match(value_str)
    if range_match:
        year = int(range_match.group(1))
        if 1800 <= year <= 2100:
            return True, "Valid (month range format)"
        return False, f"Year out of range: {year}"
    
    # Check for Year-range pattern (e.g. "2024-2025", "2025/2026")
    year_range_pattern = re.compile(r"^(\d{4})\s*[-/]\s*(\d{4})$")
    year_range_match = year_range_pattern.match(value_str)
    if year_range_match:
        year1 = int(year_range_match.group(1))
        year2 = int(year_range_match.group(2))
        if 1800 <= year1 <= 2100 and 1800 <= year2 <= 2100:
            return True, "Valid (year range format)"
        return False, f"Year out of range: {year1}-{year2}"

    # Try standard date formats
    for fmt in DATE_FORMATS:
        try:
            parsed = datetime.strptime(value_str, fmt)
            if 1800 <= parsed.year <= 2100:
                return True, f"Valid (format: {fmt})"
            return False, f"Year out of range: {parsed.year}"
        except ValueError:
            continue

    # Check if it's just a 4-digit year
    if re.match(r"^\d{4}$", value_str):
        year = int(value_str)
        if 1800 <= year <= 2100:
            return True, "Valid (year only)"
        return False, f"Year out of range: {year}"

    return False, f"Unrecognized date format: '{value_str}'"
