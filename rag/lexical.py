"""Búsqueda léxica (BM25 simplificado) para el componente híbrido del RAG."""
import math
import re
from collections import Counter

STOP = {"the", "and", "for", "con", "los", "las", "una", "que", "del", "por", "para", "este", "esta", "from", "import", "return", "self"}
_SPLIT = re.compile(r"[^A-Za-z0-9]+")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def tokenize(text: str) -> list[str]:
    out = []
    for word in _SPLIT.split(text):
        if not word:
            continue
        parts = _CAMEL.split(word)
        pieces = [word.lower()] + ([p.lower() for p in parts] if len(parts) > 1 else [])
        out += [p for p in pieces if len(p) >= 2 and p not in STOP]
    return out


def query_terms(query: str, max_terms: int = 8) -> list[str]:
    seen, out = set(), []
    for t in tokenize(query):
        if t not in seen:
            seen.add(t); out.append(t)
    return out[:max_terms]


def bm25_rank(terms: list[str], docs: list[tuple[str, str]], k1: float = 1.5, b: float = 0.75) -> list[tuple[str, float]]:
    """docs: [(id, texto)]. El IDF se calcula sobre el conjunto candidato (aproximación documentada)."""
    if not terms or not docs:
        return []
    toks = {i: Counter(tokenize(t)) for i, t in docs}
    lens = {i: sum(c.values()) or 1 for i, c in toks.items()}
    avg = sum(lens.values()) / len(lens)
    n = len(docs)
    df = {t: sum(1 for c in toks.values() if t in c) for t in terms}
    scored = []
    for i, c in toks.items():
        s = 0.0
        for t in terms:
            f = c.get(t, 0)
            if f:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                s += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * lens[i] / avg))
        if s > 0:
            scored.append((i, s))
    return sorted(scored, key=lambda x: -x[1])
