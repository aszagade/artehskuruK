"""
Document identity registry utilities.

This module generates stable, human-readable document IDs.
"""


def create_document_id(sequence: int) -> str:
    """
    Create a KURUKSHETRA document identifier.

    Example:
        1   -> DOC-000001
        42  -> DOC-000042
        999 -> DOC-000999
    """
    if sequence <= 0:
        raise ValueError("Sequence must be greater than zero.")

    return f"DOC-{sequence:06d}"