import re


def verify_issn(value):
    """
    Verify that the extracted ISSN is valid.

    Checks:
      - Not None or empty
      - Matches ISSN format: NNNN-NNNN (last digit can be X) 
      - Validates the check digit using the ISSN algorithm 
    
    Returns:
        (bool, str): (is_valid, reason)
    """

    if value is None:
        return False, "ISSN is None"

    value_str = str(value).strip().strip("\"'")

    if not value_str:
        return False, "ISSN is empty"

    # Must match NNNN-NNNN format (last char can be X)
    pattern = re.compile(r"^\d{4}-\d{3}[\dXx]$")
    if not pattern.match(value_str):
        return False, f"ISSN does not match format NNNN-NNNN: '{value_str}'"

    # Validate check digit
    digits = value_str.replace("-", "")
    total = 0
    for i, char in enumerate(digits[:7]):
        total += int(char) * (8 - i)

    check = digits[7].upper()
    expected = 11 - (total % 11)

    if expected == 10 and check == "X":
        return True, "Valid"
    if expected == 11 and check == "0":
        return True, "Valid"
    if expected < 10 and check == str(expected):
        return True, "Valid"

    return False, f"ISSN check digit invalid: '{value_str}'"
