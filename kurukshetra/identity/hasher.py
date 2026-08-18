from hashlib import sha256
from pathlib import Path

BUFFER_SIZE = 1024 * 1024  # 1 MB


def generate_sha256(path: Path) -> str:
    """
    Generate the SHA-256 hash of a file using streaming reads.

    Args:
        path: Path to the target file.

    Returns:
        Hexadecimal SHA-256 digest.
    """
    digest = sha256()

    with path.open("rb") as file:
        while chunk := file.read(BUFFER_SIZE):
            digest.update(chunk)

    return digest.hexdigest()