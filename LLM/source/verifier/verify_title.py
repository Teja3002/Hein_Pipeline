import re


def verify_title(value):
    """
    Verify that the extracted title is a valid journal title.
    
    Checks:
      - Not None or empty
      - Minimum length (at least 3 characters)
      - Maximum length (not exceeding 200 characters)
      - Not purely numeric (a title should contain letters)
      - Contains at least one alphabetic word
      - Not a URL or file path
      - Not an article title disguised as journal title (heuristic: too long usually)
    
    Returns:
        (bool, str): (is_valid, reason)
    """

    if value is None:
        return False, "Title is None"

    value_str = str(value).strip()

    if not value_str:
        return False, "Title is empty"

    value_str = value_str.strip("\"'")

    # Minimum length
    if len(value_str) < 3:
        return False, f"Title too short ({len(value_str)} chars): '{value_str}'"

    # Maximum length - journal titles rarely exceed 100 chars
    # But some are long, so we use 200 as a generous upper bound
    if len(value_str) > 200:
        return False, f"Title too long ({len(value_str)} chars), likely an article title"

    # Must contain at least one alphabetic character
    if not re.search(r"[a-zA-Z]", value_str):
        return False, f"Title contains no alphabetic characters: '{value_str}'"

    # Should not be a URL
    if value_str.startswith(("http://", "https://", "www.")):
        return False, f"Title appears to be a URL: '{value_str}'"

    # Should not be a file path
    if "/" in value_str or "\\" in value_str:
        return False, f"Title appears to be a file path: '{value_str}'"

    # Should have at least one word with 2+ letters
    words = value_str.split()
    alpha_words = [w for w in words if re.match(r"^[a-zA-Z]{2,}", w)]
    if not alpha_words:
        return False, f"Title has no recognizable words: '{value_str}'"

    # Heuristic: too many words likely means it's an article title, not a journal name
    if len(words) > 15:
        return False, f"Title has too many words ({len(words)}), likely an article title"

    return True, "Valid"
