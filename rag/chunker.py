"""Fragmentación consciente del código. Python: por AST (funciones, clases, métodos). Markdown: por encabezados.
Otros lenguajes: por declaraciones de nivel superior (heurística). Respaldo: ventanas de líneas con solape.
Los números de línea son 1-based e inclusivos."""
import ast
import re
from dataclasses import dataclass

MAX_CHARS = 1500
OVERLAP_LINES = 2
HARD_LINE_CAP = 6000


@dataclass(frozen=True)
class Chunk:
    idx: int
    start_line: int
    end_line: int
    symbol: str | None
    kind: str
    text: str


Unit = tuple[int, int, str | None, str]   # (inicio, fin, símbolo, tipo)
DECL = re.compile(r"^(?:export\s+|default\s+|pub(?:\([^)]*\))?\s+|public\s+|private\s+|protected\s+|static\s+|async\s+|abstract\s+|final\s+)*"
                  r"(?:function\*?|class|def|func|fn|interface|contract|struct|enum|impl|type|trait|module)\s+([A-Za-z_$][\w$]*)")
HEADING = re.compile(r"^#{1,6}\s+(.*\S)\s*$")


def _size(lines: list[str], s: int, e: int) -> int:
    return sum(min(len(l), HARD_LINE_CAP) + 1 for l in lines[s - 1:e])


def _blank(lines: list[str], s: int, e: int) -> bool:
    return all(not l.strip() for l in lines[s - 1:e])


def _windows(lines: list[str], s: int, e: int, max_chars: int, overlap: int) -> list[tuple[int, int]]:
    out, i = [], s
    while i <= e:
        j, acc = i, 0
        while j <= e and (j == i or acc + min(len(lines[j - 1]), HARD_LINE_CAP) + 1 <= max_chars):
            acc += min(len(lines[j - 1]), HARD_LINE_CAP) + 1
            j += 1
        out.append((i, j - 1))
        if j > e:
            break
        i = max(j - overlap, i + 1)
    return out


def _py_units(nodes, lines: list[str], lo: int, hi: int, max_chars: int, prefix: str = "") -> list[Unit]:
    units: list[Unit] = []
    prev = lo - 1

    def gap(a: int, b: int, kind: str):
        if a <= b and not _blank(lines, a, b):
            units.append((a, b, None, kind))

    for n in nodes:
        start = min([n.lineno] + [d.lineno for d in getattr(n, "decorator_list", [])])
        gap(prev + 1, start - 1, "module" if not prefix else "class_body")
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            units.append((start, n.end_lineno, prefix + n.name, "method" if prefix else "function"))
        elif isinstance(n, ast.ClassDef):
            if _size(lines, start, n.end_lineno) <= max_chars:
                units.append((start, n.end_lineno, prefix + n.name, "class"))
            else:
                members = [m for m in n.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))]
                if not members:
                    units.append((start, n.end_lineno, prefix + n.name, "class"))
                else:
                    first = min([members[0].lineno] + [d.lineno for d in members[0].decorator_list])
                    units.append((start, first - 1, prefix + n.name, "class"))
                    units += _py_units(n.body, lines, first, n.end_lineno, max_chars, prefix + n.name + ".")
        else:
            units.append((start, n.end_lineno, None, "module" if not prefix else "class_body"))
        prev = n.end_lineno
    gap(prev + 1, hi, "module" if not prefix else "class_body")
    return units


def _decl_units(lines: list[str]) -> list[Unit]:
    starts = [(i + 1, m.group(1)) for i, l in enumerate(lines) if (m := DECL.match(l))]
    if not starts:
        return []
    units: list[Unit] = []
    if starts[0][0] > 1 and not _blank(lines, 1, starts[0][0] - 1):
        units.append((1, starts[0][0] - 1, None, "module"))
    for k, (ln, name) in enumerate(starts):
        end = (starts[k + 1][0] - 1) if k + 1 < len(starts) else len(lines)
        units.append((ln, end, name, "declaration"))
    return units


def _md_units(lines: list[str]) -> list[Unit]:
    starts = [(i + 1, m.group(1)) for i, l in enumerate(lines) if (m := HEADING.match(l))]
    if not starts:
        return []
    units: list[Unit] = []
    if starts[0][0] > 1 and not _blank(lines, 1, starts[0][0] - 1):
        units.append((1, starts[0][0] - 1, None, "doc"))
    for k, (ln, title) in enumerate(starts):
        end = (starts[k + 1][0] - 1) if k + 1 < len(starts) else len(lines)
        units.append((ln, end, title, "doc"))
    return units


def chunk_file(rel: str, text: str, max_chars: int = MAX_CHARS, overlap: int = OVERLAP_LINES) -> list[Chunk]:
    lines = text.splitlines()
    if not lines or not text.strip():
        return []
    ext = rel.rsplit(".", 1)[-1].lower() if "." in rel.rsplit("/", 1)[-1] else ""
    units: list[Unit] = []
    if ext == "py":
        try:
            units = _py_units(ast.parse(text).body, lines, 1, len(lines), max_chars)
        except (SyntaxError, ValueError):
            units = []
    elif ext in ("md", "rst", "markdown"):
        units = _md_units(lines)
    elif ext in ("js", "jsx", "ts", "tsx", "mjs", "go", "rs", "java", "c", "h", "cpp", "cc", "hpp", "cs", "php", "sol", "kt", "rb"):
        units = _decl_units(lines)
    if not units:
        units = [(1, len(lines), None, "text")]

    # empaquetado: une unidades pequeñas contiguas y divide las grandes en ventanas
    packed: list[list] = []   # [start, end, [símbolos], kind]
    cur: list | None = None
    for s, e, sym, kind in units:
        if _size(lines, s, e) > max_chars:
            if cur: packed.append(cur); cur = None
            for ws_, we_ in _windows(lines, s, e, max_chars, overlap):
                packed.append([ws_, we_, [sym] if sym else [], kind])
            continue
        if cur and _size(lines, cur[0], e) <= max_chars and s > cur[1]:
            cur[1] = e
            if sym: cur[2].append(sym)
            if kind != cur[3]: cur[3] = "mixed"
        else:
            if cur: packed.append(cur)
            cur = [s, e, [sym] if sym else [], kind]
    if cur:
        packed.append(cur)
    out = []
    for i, (s, e, syms, kind) in enumerate(packed):
        body = "\n".join(l[:HARD_LINE_CAP] for l in lines[s - 1:e])
        out.append(Chunk(i, s, e, ", ".join(syms[:3]) or None, kind, body))
    return out
