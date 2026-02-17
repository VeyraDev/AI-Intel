"""
Generate unique IDs for update content (e.g. SHA256 of title+url).
"""
import hashlib


def generate_id(content: str) -> str:
    """Generate a unique ID from content string (SHA256 hex)."""
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()
