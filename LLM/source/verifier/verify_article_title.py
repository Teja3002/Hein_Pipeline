import re


def verify_article_title(value):
    """
    Verify that the extracted article title is valid.

    Checks:
      - Not None or empty
      - Minimum length (at least 5 characters)
      - Maximum length (not exceeding 500 characters)
      - Contains at least one alphabetic word
      - Not purely numeric
      - Not a URL or file path

    Returns:
        (bool, str): (is_valid, reason)
    """

    if value is None:
        return False, "Article title is None"

    value_str = str(value).strip().strip("\"'")

    if not value_str:
        return False, "Article title is empty"

    if len(value_str) < 5:
        return False, f"Article title too short ({len(value_str)} chars): '{value_str}'"

    if len(value_str) > 500:
        return False, f"Article title too long ({len(value_str)} chars)"

    if not re.search(r"[a-zA-Z]", value_str):
        return False, f"Article title contains no alphabetic characters: '{value_str}'"

    if value_str.startswith(("http://", "https://", "www.")):
        return False, f"Article title appears to be a URL: '{value_str}'"

    words = value_str.split()
    alpha_words = [w for w in words if re.match(r"^[a-zA-Z]{2,}", w)]
    if not alpha_words:
        return False, f"Article title has no recognizable words: '{value_str}'"

    return True, "Valid"
