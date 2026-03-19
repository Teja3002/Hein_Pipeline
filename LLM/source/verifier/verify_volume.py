def verify_volume(value):
    """
    Verify that the extracted volume is a valid volume number.
    
    Checks:
      - Not None or empty
      - Is a whole positive integer (not float, not negative)
      - Contains only digits (no letters or special characters)
      - Within a reasonable range (1 - 9999)
    
    Returns:
        (bool, str): (is_valid, reason)
    """

    if value is None:
        return False, "Volume is None"

    value_str = str(value).strip()

    if not value_str:
        return False, "Volume is empty"

    # Remove any surrounding quotes the LLM might have left
    value_str = value_str.strip("\"'")

    # Check if it contains only digits
    if not value_str.isdigit():
        return False, f"Volume contains non-digit characters: '{value_str}'"

    num = int(value_str)

    # Must be positive
    if num <= 0:
        return False, f"Volume must be positive, got: {num}"

    # Reasonable upper bound for journal volumes
    if num > 9999:
        return False, f"Volume exceeds reasonable range (>9999): {num}"

    return True, "Valid"
