from source.verifier.verify_issn import verify_issn


def verify_eissn(value):
    """
    Verify that the extracted E-ISSN is valid.

    E-ISSN follows the exact same format as ISSN (NNNN-NNNN). 
    This wraps verify_issn and adjusts the messaging. 

    Returns:
        (bool, str): (is_valid, reason)
    """

    is_valid, reason = verify_issn(value)

    # Swap "ISSN" for "E-ISSN" in the reason message 
    reason = reason.replace("ISSN", "E-ISSN") 

    return is_valid, reason 