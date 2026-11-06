"""Debugging Engine (análisis, no ejecución): convierte la salida de compiladores, tests y trazas en datos estructurados
para que el modelo corrija causas reales. Formatos: Python (traceback), gcc/clang, tsc, go, rustc, javac, unittest/pytest/go/cargo."""
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Diagnostic:
    kind: str
    file: str | None
    line: int | None
    col: int | None
    severity: str
    code: str | None
    message: str


@dataclass
class TestSummary:
    framework: str
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors + self.skipped

    @property
    def ok(self) -> bool:
        return self.failed == 0 and self.errors == 0 and self.total > 0


GCC = re.compile(r"^(?P<file>[^\s:()]+):(?P<line>\d+):(?:(?P<col>\d+):)? (?P<sev>fatal error|error|warning): (?P<msg>.*)$")
TSC = re.compile(r"^(?P<file>[^\s(]+)\((?P<line>\d+),(?P<col>\d+)\): (?P<sev>error|warning) (?P<code>TS\d+): (?P<msg>.*)$")
GO = re.compile(r"^(?P<file>[^\s:]+\.go):(?P<line>\d+):(?P<col>\d+): (?P<msg>.*)$")
JAVAC = re.compile(r"^(?P<file>[^\s:]+\.java):(?P<line>\d+): (?P<sev>error|warning): (?P<msg>.*)$")
RUST_HEAD = re.compile(r"^(?P<sev>error|warning)(?:\[(?P<code>E\d+)\])?: (?P<msg>.*)$")
RUST_LOC = re.compile(r"^\s*--> (?P<file>[^:]+):(?P<line>\d+):(?P<col>\d+)")
PY_FRAME = re.compile(r'^\s*File "(?P<file>[^"]+)", line (?P<line>\d+)(?:, in (?P<fn>.*))?$')
PY_EXC = re.compile(r"^(?P<exc>[A-Za-z_][\w.]*(?:Error|Exception|Exit|Interrupt|Warning)?): ?(?P<msg>.*)$")
THIRD_PARTY = ("site-packages", "dist-packages", "/usr/lib/python", "/usr/local/lib/python", "<frozen", "<string>")


def normalize_path(p: str | None, roots: tuple[str, ...] = ("/workspace/",)) -> str | None:
    if p is None:
        return None
    for r in roots:
        if p.startswith(r):
            p = p[len(r):]
    return p[2:] if p.startswith("./") else p


def parse_diagnostics(text: str, roots: tuple[str, ...] = ("/workspace/",), limit: int = 50) -> list[Diagnostic]:
    lines, out, seen = text.splitlines(), [], set()

    def add(d: Diagnostic):
        key = (d.file, d.line, d.message)
        if key not in seen and len(out) < limit:
            seen.add(key); out.append(d)

    i = 0
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("Traceback (most recent call last)"):
            frames, j = [], i + 1
            while j < len(lines):
                m = PY_FRAME.match(lines[j])
                if m:
                    frames.append(m); j += 2 if j + 1 < len(lines) and lines[j + 1].startswith("    ") else 1
                elif lines[j].startswith(("    ", "  ")) or not lines[j].strip():
                    j += 1
                else:
                    break
            if j < len(lines) and (em := PY_EXC.match(lines[j])):
                mine = [f for f in frames if not any(t in f["file"] for t in THIRD_PARTY)] or frames
                f = mine[-1] if mine else None
                add(Diagnostic("python_traceback", normalize_path(f["file"], roots) if f else None, int(f["line"]) if f else None,
                               None, "error", em["exc"], em["msg"] or em["exc"]))
            i = j
            continue
        if (m := PY_FRAME.match(ln)) and not any(t in m["file"] for t in THIRD_PARTY):           # SyntaxError sin "Traceback"
            for k in range(i + 1, min(i + 5, len(lines))):
                if (em := re.match(r"^(\w*(?:SyntaxError|IndentationError|TabError)): (.*)$", lines[k])):
                    add(Diagnostic("python_syntax", normalize_path(m["file"], roots), int(m["line"]), None, "error", em[1], em[2]))
                    i = k; break
        elif (m := TSC.match(ln)):
            add(Diagnostic("tsc", normalize_path(m["file"], roots), int(m["line"]), int(m["col"]), m["sev"], m["code"], m["msg"]))
        elif (m := JAVAC.match(ln)):
            add(Diagnostic("javac", normalize_path(m["file"], roots), int(m["line"]), None, m["sev"], None, m["msg"]))
        elif (m := GCC.match(ln)):
            add(Diagnostic("gcc", normalize_path(m["file"], roots), int(m["line"]), int(m["col"]) if m["col"] else None,
                           "error" if "error" in m["sev"] else "warning", None, m["msg"]))
        elif (m := GO.match(ln)):
            add(Diagnostic("go", normalize_path(m["file"], roots), int(m["line"]), int(m["col"]), "error", None, m["msg"]))
        elif (m := RUST_HEAD.match(ln)) and not ln.startswith(("error: aborting", "error: could not compile", "warning: unused")):
            for k in range(i + 1, min(i + 4, len(lines))):
                if (loc := RUST_LOC.match(lines[k])):
                    add(Diagnostic("rustc", normalize_path(loc["file"], roots), int(loc["line"]), int(loc["col"]), m["sev"], m["code"], m["msg"]))
                    break
        i += 1
    return out


def render_diagnostics(diags: list[Diagnostic]) -> str:
    return "\n".join(f"- {d.severity} {d.file or '?'}:{d.line or '?'}" + (f" [{d.code}]" if d.code else "") + f" {d.message}" for d in diags)


# ---------------- resultados de pruebas
UT_RAN = re.compile(r"^Ran (\d+) tests? in ")
UT_RES = re.compile(r"^(OK|FAILED)(?: \((.*)\))?")
UT_FAIL = re.compile(r"^(FAIL|ERROR): (\S+) \((.*?)\)")
PYTEST_LINE = re.compile(r"=+ (.*?) in [\d.]+s.*=+$|^(\d+ (?:passed|failed|error|skipped).*) in [\d.]+s")
PYTEST_FAIL = re.compile(r"^(FAILED|ERROR) (\S+)")
GO_FAIL = re.compile(r"^--- FAIL: (\S+)")
CARGO = re.compile(r"^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored")
CARGO_FAIL = re.compile(r"^test (\S+) \.\.\. FAILED")


def _counts(s: str) -> dict[str, int]:
    return {k: int(n) for n, k in re.findall(r"(\d+) (passed|failed|errors?|skipped|failures)", s)}


def parse_test_output(framework: str, output: str) -> TestSummary:
    s = TestSummary(framework)
    lines = output.splitlines()
    if framework == "unittest":
        for ln in lines:
            if m := UT_RAN.match(ln): total = int(m[1]); s.passed = total
            if m := UT_RES.match(ln):
                c = _counts((m[2] or "").replace("failures", "failed").replace("errors", "errors"))
                kv = dict(re.findall(r"(\w+)=(\d+)", m[2] or ""))
                s.failed, s.errors, s.skipped = int(kv.get("failures", 0)), int(kv.get("errors", 0)), int(kv.get("skipped", 0))
                s.passed = max(s.passed - s.failed - s.errors - s.skipped, 0)
            if m := UT_FAIL.match(ln): s.failures.append(f"{m[3]}")
    elif framework == "pytest":
        for ln in reversed(lines):
            if (m := PYTEST_LINE.search(ln)):
                c = _counts(m[1] or m[2] or "")
                s.passed, s.failed, s.errors, s.skipped = c.get("passed", 0), c.get("failed", 0), c.get("error", 0) + c.get("errors", 0), c.get("skipped", 0)
                break
        s.failures = [m[2] for ln in lines if (m := PYTEST_FAIL.match(ln))]
    elif framework == "go":
        s.failures = [m[1] for ln in lines if (m := GO_FAIL.match(ln))]
        s.failed = len(s.failures)
        s.passed = sum(1 for ln in lines if ln.startswith("ok ")) + sum(1 for ln in lines if ln.startswith("--- PASS"))
    elif framework == "cargo":
        for ln in lines:
            if m := CARGO.match(ln): s.passed += int(m[2]); s.failed += int(m[3]); s.skipped += int(m[4])
            if m := CARGO_FAIL.match(ln): s.failures.append(m[1])
    else:
        raise ValueError(f"Framework de pruebas no soportado: {framework}")
    return s
