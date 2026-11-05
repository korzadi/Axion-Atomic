def chunk_text(text: str, size: int = 1200, overlap: int = 150):
    text = text.strip()
    if not text:
        return []
    if size <= overlap or overlap < 0:
        raise ValueError("size must be greater than overlap")
    result, start = [], 0
    while start < len(text):
        end = min(len(text), start + size)
        result.append(text[start:end])
        if end == len(text):
            break
        start = end - overlap
    return result
