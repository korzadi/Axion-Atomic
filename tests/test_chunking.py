import pytest
from rag.chunking import chunk_text

def test_empty():
    assert chunk_text("  ") == []

def test_chunks():
    value = "abcdefghij" * 100
    parts = chunk_text(value, size=100, overlap=10)
    assert parts[0].startswith("abcdefghij")
    assert parts[-1]
    assert all(len(x) <= 100 for x in parts)

def test_invalid_overlap():
    with pytest.raises(ValueError):
        chunk_text("x", size=10, overlap=10)
