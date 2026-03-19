import re


def verify_article_authors(value):
    """
    Verify that the extracted authors list is valid.

    Checks:
      - Not None
      - Is a list
      - Has at least one author
      - Each author is a non-empty string
      - Each author contains at least one alphabetic character
      - No author is unreasonably long (>100 chars)
      - No author looks like a URL, number, or garbage

    Returns:
        (bool, str): (is_valid, reason)
    """

    if value is None:
        return False, "Authors is None"

    if not isinstance(value, list):
        return False, f"Authors is not a list: {type(value)}"

    if len(value) == 0:
        return False, "Authors list is empty"

    for i, author in enumerate(value):
        if not isinstance(author, str):
            return False, f"Author {i + 1} is not a string: {type(author)}"

        author = author.strip()

        if not author:
            return False, f"Author {i + 1} is empty"

        if len(author) > 100:
            return False, f"Author {i + 1} is too long ({len(author)} chars)"

        if not re.search(r"[a-zA-Z]", author):
            return False, f"Author {i + 1} has no alphabetic characters: '{author}'"

        if author.startswith(("http://", "https://", "www.")):
            return False, f"Author {i + 1} appears to be a URL: '{author}'"

        # Author name should have at least 2 characters
        if len(author) < 2:
            return False, f"Author {i + 1} is too short: '{author}'"

    return True, "Valid"
