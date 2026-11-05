"""Ejecución de procesos acotada: salida limitada (se descarta el exceso sin bloquear), timeout con muerte del
grupo de procesos completo y limpieza de procesos huérfanos."""
import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass


@dataclass
class ExecResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    truncated: bool
    duration_s: float
    backend: str = ""


def run_bounded(argv: list[str], cwd: str | None, env: dict, timeout_s: float, max_bytes: int,
                preexec=None, kill_cmd: list[str] | None = None, backend: str = "") -> ExecResult:
    t0 = time.monotonic()
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True, preexec_fn=preexec)
    bufs = {"out": bytearray(), "err": bytearray()}
    state = {"truncated": False}

    def drain(stream, key):
        while True:
            chunk = stream.read(65536) if not hasattr(stream, "read1") else stream.read1(65536)
            if not chunk:
                return
            room = max_bytes - len(bufs[key])
            if room > 0:
                bufs[key] += chunk[:room]
            if len(chunk) > max(room, 0):
                state["truncated"] = True

    threads = [threading.Thread(target=drain, args=(proc.stdout, "out"), daemon=True),
               threading.Thread(target=drain, args=(proc.stderr, "err"), daemon=True)]
    for t in threads:
        t.start()
    timed_out = False
    try:
        code = proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        timed_out = True
        if kill_cmd:
            subprocess.run(kill_cmd, capture_output=True, timeout=10, check=False)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        code = proc.wait()
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)     # elimina descendientes que sobrevivan al proceso principal
        except (ProcessLookupError, PermissionError):
            pass
    for t in threads:
        t.join(timeout=5)
    for stream in (proc.stdout, proc.stderr):          # evita fugas de descriptores en un servicio de larga duración
        try:
            stream.close()
        except (OSError, ValueError):
            pass
    return ExecResult(None if timed_out else code, bufs["out"].decode("utf-8", "replace"), bufs["err"].decode("utf-8", "replace"),
                      timed_out, state["truncated"], time.monotonic() - t0, backend)
