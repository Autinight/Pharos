"""Run computation with Linux cgroups or portable per-job time limits.

macOS has no systemd/cgroups and RLIMIT_AS is not a reliable memory cap there.
It uses sampled process-group RSS instead. This is a best-effort guard, not a
sandbox or a deployment-wide CPU/RAM quota; short allocation spikes can escape
between samples. Scripts must remain in the project's computation directory.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

_SLICE = "pharos-compute.slice"


def _tier(heavy: bool) -> dict:
    e = os.environ.get
    if heavy:
        return {"mem": e("PHAROS_COMPUTE_HEAVY_MEM", "16G"),
                "cpu": e("PHAROS_COMPUTE_HEAVY_CPU", "400%"),
                "seconds": int(e("PHAROS_COMPUTE_HEAVY_SECONDS", "7200"))}
    return {"mem": e("PHAROS_COMPUTE_MEM", "2G"),
            "cpu": e("PHAROS_COMPUTE_CPU", "100%"),
            "seconds": int(e("PHAROS_COMPUTE_SECONDS", "600"))}


def resolve_computation_dir(script: Path) -> Path:
    script = script.resolve()
    for parent in script.parents:
        if (parent / "project.json").is_file() and (parent / "workers").is_dir():
            comp = parent / "computation"
            if comp in script.parents:
                return comp
            raise SystemExit(
                f"computation scripts live in {comp} (move {script.name} there — "
                "scripts and their outputs stay in the one capped folder)")
    raise SystemExit(f"{script} is not inside a Pharos project")


def _dir_size_gb(path: Path) -> float:
    """Apparent file bytes, without GNU du or following symlinks outside root.

    Fail closed on unreadable directories instead of treating a failed `du`
    invocation as a zero-byte directory. Concurrently removed files are benign.
    """
    total = 0
    pending = [path]
    try:
        while pending:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(Path(entry.path))
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                    except FileNotFoundError:
                        continue
    except OSError as exc:
        raise SystemExit(f"cannot measure computation directory {path}: {exc}") from exc
    return total / 2**30


def _check_dir_cap(comp: Path) -> None:
    cap = float(os.environ.get("PHAROS_COMPUTE_DIR_CAP_GB", "20"))
    size = _dir_size_gb(comp)
    if size >= cap:
        raise SystemExit(
            f"{comp} holds {size:.1f}G, over its {cap:g}G cap — delete stale "
            "scripts/results before computing again (the cap protects the host)")


def _systemd_available() -> bool:
    if sys.platform != "linux" or os.environ.get("PHAROS_COMPUTE_NO_SYSTEMD"):
        return False
    if not shutil.which("systemd-run"):
        return False
    probe = subprocess.run(["systemd-run", "--user", "--scope", "--quiet",
                            "--collect", "--", "/bin/true"],
                           capture_output=True, timeout=10)
    return probe.returncode == 0


def _mem_bytes(spec: str) -> int:
    mult = {"K": 2**10, "M": 2**20, "G": 2**30}
    if spec and spec[-1].upper() in mult:
        return int(float(spec[:-1]) * mult[spec[-1].upper()])
    return int(spec)


def _interpreter(script: Path) -> List[str]:
    if script.suffix == ".sage":
        sage = shutil.which("sage")
        if not sage:
            raise SystemExit("*.sage needs SageMath on PATH (not installed)")
        return [sage]
    return [os.environ.get("PHAROS_COMPUTE_PYTHON") or sys.executable]


def _group_rss(pgid: int) -> int:
    """Sum RSS in our newly created process group (macOS-only dependency)."""
    import psutil

    total = 0
    for proc in psutil.process_iter(["pid"]):
        try:
            member = os.getpgid(proc.pid) == pgid
        except (ProcessLookupError, PermissionError, psutil.NoSuchProcess):
            continue  # unrelated/inaccessible processes need not be inspected
        if not member:
            continue
        try:
            total += proc.memory_info().rss
        except psutil.NoSuchProcess:
            continue
        except (PermissionError, psutil.AccessDenied) as exc:
            # Membership is known. Never silently turn a failed RSS read into 0.
            raise SystemExit(f"cannot enforce RSS cap: cannot read job PID {proc.pid}") from exc
    return total


def _kill_job(proc: subprocess.Popen) -> None:
    """Kill only this job's new process group, including surviving descendants."""
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.wait()


def _run_job(cmd: List[str], comp: Path, seconds: int, preexec,
             rss_limit: Optional[int] = None) -> int:
    if rss_limit is not None:
        try:
            import psutil  # noqa: F401 — fail before spawning, never run uncapped
        except ImportError as exc:
            raise SystemExit("macOS compute requires psutil; re-run bootstrap") from exc
    started = time.monotonic()
    proc = subprocess.Popen(cmd, cwd=str(comp), preexec_fn=preexec,
                            start_new_session=True)
    try:
        while proc.poll() is None:
            if time.monotonic() - started >= seconds:
                print(f"[pharos compute] killed: exceeded the {seconds}s time cap", file=sys.stderr)
                return 124
            if rss_limit is not None and _group_rss(proc.pid) > rss_limit:
                print("[pharos compute] killed: exceeded the sampled process-group RSS cap",
                      file=sys.stderr)
                return 137
            time.sleep(0.1)
        return proc.returncode
    finally:
        # Also clean up background children after the script leader exits.
        _kill_job(proc)


def run(script: str, args: Optional[List[str]] = None, heavy: bool = False) -> int:
    spath = Path(script)
    comp = resolve_computation_dir(spath)
    _check_dir_cap(comp)
    tier = _tier(heavy)
    limit = _mem_bytes(tier["mem"])
    if limit <= 0 or tier["seconds"] <= 0:
        raise SystemExit("computation memory and time limits must be positive")
    payload = [*_interpreter(spath), str(spath.resolve()), *(args or [])]
    rss_limit = None

    if _systemd_available():
        cmd = ["systemd-run", "--user", "--scope", "--quiet", "--collect",
               f"--slice={_SLICE}", "-p", f"MemoryMax={tier['mem']}",
               "-p", "MemorySwapMax=0", "-p", f"CPUQuota={tier['cpu']}",
               "-p", "TasksMax=128", "--", *payload]
        preexec = None
    else:
        macos = sys.platform == "darwin"
        print("[pharos compute] WARNING: no collective CPU/RAM cap; "
              + ("macOS uses sampled per-job process-group RSS + wall-time limits"
                 if macos else "per-job RLIMIT_AS + wall-time limits only"), file=sys.stderr)

        def preexec():
            if not macos:
                import resource
                resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
            os.nice(19)

        if macos:
            rss_limit = limit
        cmd = payload

    rc = _run_job(cmd, comp, tier["seconds"], preexec, rss_limit)
    if rc != 0:
        print(f"[pharos compute] exit code {rc}", file=sys.stderr)
    return rc
