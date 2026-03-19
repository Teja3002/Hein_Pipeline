import re


def verify_issue(value):
    """
    Verify that the extracted issue number is valid.
    
    Checks:
      - Not None or empty
      - Is a whole positive integer (not float, not negative)
      - Contains only digits (no letters or special characters)
      - Within a reasonable range (1 - 999)
      - Handles combined issue numbers like "1/2" or "1-2" as valid
    
    Returns:
        (bool, str): (is_valid, reason)
    """

    if value is None:
        return False, "Issue number is None"

    value_str = str(value).strip()

    if not value_str:
        return False, "Issue number is empty"

    value_str = value_str.strip("\"'")

    # Handle combined issues like "1/2", "3-4", "1 & 2"
    combined_pattern = re.match(r"^(\d+)\s*[-/&]\s*(\d+)$", value_str)
    if combined_pattern:
        num1 = int(combined_pattern.group(1))
        num2 = int(combined_pattern.group(2))
        if num1 <= 0 or num2 <= 0:
            return False, f"Combined issue numbers must be positive: '{value_str}'"
        if num1 > 999 or num2 > 999:
            return False, f"Issue number exceeds reasonable range: '{value_str}'"
        if num1 >= num2:
            return False, f"Combined issue range is invalid ({num1} >= {num2}): '{value_str}'"
        return True, "Valid (combined issue)"

    # Standard single issue number
    if not value_str.isdigit():
        return False, f"Issue number contains non-digit characters: '{value_str}'"

    num = int(value_str)

    if num <= 0:
        return False, f"Issue number must be positive, got: {num}"

    if num > 999:
        return False, f"Issue number exceeds reasonable range (>999): {num}"

    return True, "Valid"
