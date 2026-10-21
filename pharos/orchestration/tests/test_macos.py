"""macOS portability regressions; no credentials or real model calls required."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from pharos.execution import layout as L
from pharos.execution.scaffold import do_new
from pharos.orchestration import cli, compute, health, monitor, render, services, usage
from pharos.tests.util import env

ROOT = Path(__file__).resolve().parents[3]


def _bash(code, **extra):
    return subprocess.run(["/bin/bash", "-c", code], env={**os.environ, **extra},
                          capture_output=True, text=True, timeout=15)


@pytest.mark.parametrize("host,arch,suffix", [
    ("Darwin", "arm64", "darwin-arm64.tar.gz"),
    ("Darwin", "x86_64", "darwin-x64.tar.gz"),
    ("Linux", "aarch64", "linux-arm64.tar.xz"),
    ("Linux", "x86_64", "linux-x64.tar.xz"),
])
def test_node_archive_platform_matrix(host, arch, suffix):
    row = _bash(f'source "{ROOT}/scripts/platform.sh"; pharos_node_archive v22.14.0 {host} {arch}')
    assert row.returncode == 0
    assert row.stdout.strip() == f"node-v22.14.0-{suffix}"


@pytest.mark.parametrize("host,arch", [("FreeBSD", "arm64"), ("Darwin", "mips")])
def test_unsupported_platform_fails_before_install(host, arch):
    row = _bash(f'source "{ROOT}/scripts/platform.sh"; pharos_node_archive v22.14.0 {host} {arch}')
    assert row.returncode != 0 and "unsupported" in row.stderr


def test_bootstrap_print_plan_has_no_side_effects(tmp_path):
    root = tmp_path / "checkout with spaces"
    (root / "scripts").mkdir(parents=True)
    for name in ("bootstrap.sh", "platform.sh"):
        shutil.copyfile(ROOT / "scripts" / name, root / "scripts" / name)
    row = _bash(f'bash "{root}/scripts/bootstrap.sh" --print-plan',
                PHAROS_BOOTSTRAP_PYTHON=sys.executable)
    assert row.returncode == 0, row.stderr
    assert f"runtime={root}/runtime" in row.stdout
    assert not (root / "runtime").exists()


@pytest.mark.parametrize("override,expected", [("", "0.163.0"), ("0.162.0", "0.162.0")])
def test_bootstrap_reports_pinned_codex_or_explicit_override(tmp_path, override, expected):
    root = tmp_path / "checkout with spaces"
    (root / "scripts").mkdir(parents=True)
    for name in ("bootstrap.sh", "platform.sh"):
        shutil.copyfile(ROOT / "scripts" / name, root / "scripts" / name)
    row = _bash(f'bash "{root}/scripts/bootstrap.sh" --print-plan',
                PHAROS_BOOTSTRAP_PYTHON=sys.executable,
                PHAROS_CODEX_SOURCE_VERSION=override)
    assert row.returncode == 0, row.stderr
    assert f"codex_npm_version={expected}" in row.stdout.splitlines()
    assert not (root / "runtime").exists()


def test_matching_codex_package_still_requires_a_working_native_binary(tmp_path):
    root = tmp_path / "checkout with spaces"
    (root / "scripts").mkdir(parents=True)
    for name in ("bootstrap.sh", "platform.sh"):
        shutil.copyfile(ROOT / "scripts" / name, root / "scripts" / name)
    node = root / "runtime/node22/bin/node"
    node.parent.mkdir(parents=True)
    node.write_text('#!/bin/sh\n'
                    'case "$1" in\n'
                    '  --version) echo v22.14.0;;\n'
                    '  -p) echo 0.163.0;;\n'
                    '  *) echo "native CLI failed" >&2; exit 23;;\n'
                    'esac\n')
    node.chmod(0o755)
    venv = root / "runtime/venv/bin"
    venv.mkdir(parents=True)
    for name in ("python", "pip"):
        stub = venv / name
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)
    package = root / "runtime/codex-npm/lib/node_modules/@openai/codex"
    (package / "bin").mkdir(parents=True)
    (package / "package.json").write_text('{"version":"0.163.0"}')
    (package / "bin/codex.js").write_text("// native launch is stubbed\n")
    row = _bash(f'bash "{root}/scripts/bootstrap.sh"',
                PHAROS_BOOTSTRAP_PYTHON=sys.executable,
                PHAROS_CODEX_SOURCE_VERSION="0.163.0",
                PHAROS_LOCAL_BIN=str(tmp_path / "local-bin"))
    assert row.returncode != 0
    assert "matching codex 0.163.0 present" in row.stdout
    assert "FATAL: the installed native Codex CLI cannot start" in row.stdout
    assert "Installed. No research" not in row.stdout
    assert not (root / "runtime/runtime.env").exists()
    assert not (tmp_path / "local-bin/pharos").exists()


def test_python_override_is_validated(tmp_path):
    script = f'source "{ROOT}/scripts/platform.sh"; pharos_find_python'
    good = _bash(script, PHAROS_BOOTSTRAP_PYTHON=sys.executable)
    assert good.returncode == 0 and good.stdout.strip() == sys.executable
    bad = _bash(script, PHAROS_BOOTSTRAP_PYTHON=str(tmp_path / "missing"))
    assert bad.returncode != 0 and "3.10+" in bad.stderr


@pytest.mark.parametrize("shell", ["bash", "zsh"])
def test_env_script_can_be_sourced_from_another_directory(shell, tmp_path):
    if not shutil.which(shell):
        pytest.skip(f"{shell} not installed")
    root = tmp_path / "checkout with spaces"
    (root / "scripts").mkdir(parents=True)
    shutil.copyfile(ROOT / "scripts/env.sh", root / "scripts/env.sh")
    row = subprocess.run([shell, "-c", f'source "{root}/scripts/env.sh"; printf "%s" "$PHAROS_ROOT"'],
                         cwd=tmp_path, capture_output=True, text=True, timeout=10)
    assert row.returncode == 0, row.stderr
    assert Path(row.stdout) == root.resolve()


def test_directory_size_counts_files_without_following_external_links(tmp_path):
    comp = tmp_path / "comp"
    (comp / "nested").mkdir(parents=True)
    (comp / "one").write_bytes(b"x" * 100)
    (comp / "nested/two").write_bytes(b"y" * 200)
    external = tmp_path / "outside"
    external.mkdir()
    (external / "large").write_bytes(b"z" * 10_000)
    link = comp / "external"
    link.symlink_to(external, target_is_directory=True)
    assert compute._dir_size_gb(comp) * 2**30 == 300 + link.lstat().st_size


def test_directory_measurement_failure_is_not_zero(tmp_path):
    with pytest.raises(SystemExit, match="cannot measure"):
        compute._dir_size_gb(tmp_path / "missing")


def test_systemd_is_not_probed_on_macos(monkeypatch):
    monkeypatch.setattr(compute.sys, "platform", "darwin")
    monkeypatch.setattr(compute.subprocess, "run", lambda *a, **k: pytest.fail("systemd on macOS"))
    assert compute._systemd_available() is False


def test_chrome_in_user_applications_is_discovered(monkeypatch, tmp_path):
    binary = tmp_path / "Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.delenv("PHAROS_CHROME_BIN", raising=False)
    monkeypatch.setattr(render.shutil, "which", lambda _: None)
    monkeypatch.setattr(render.Path, "home", lambda: tmp_path)
    # Ignore any real system Chrome so the user-app path is exercised on all hosts.
    original = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda p: False if str(p).startswith("/Applications/") else original(p))
    assert render.chrome_bin() == str(binary)


def test_missing_proc_does_not_break_active_worker_sampling(monkeypatch, tmp_path):
    with env(PHAROS_AGENTS_ROOT=str(tmp_path), VERIFY_PORT=None):
        do_new("P", roles="xhigh:1")
        monkeypatch.setattr(cli, "worker_status", lambda _: {
            "worker": "xhigh", "alive": True, "state": "running", "round": 1,
            "label": "test", "active_at": None, "pid": os.getpid()})
        monkeypatch.setattr(services, "main_status", lambda _: [{"running": None}])
        original = Path.is_dir
        monkeypatch.setattr(Path, "is_dir", lambda p: False if str(p) == "/proc" else original(p))
        row = monitor.sample("P")
    assert row["main_up"] is None
    assert row["workers"][0]["alive"] is True
    assert row["workers"][0]["io_read_mb"] is None
    assert row["workers"][0]["io_write_mb"] is None


def test_disappearing_disk_counters_remain_unknown(monkeypatch):
    values = iter([(100, 200), None])
    monkeypatch.setattr(monitor, "_disk_bytes", lambda: next(values))
    monkeypatch.setattr(monitor.time, "sleep", lambda _: None)
    assert monitor._io_rate() == {"io_read_mbps": None, "io_write_mbps": None}


def test_missing_tmux_status_is_unknown(monkeypatch, tmp_path):
    def missing(*a, **kw):
        raise FileNotFoundError("tmux")
    with env(PHAROS_AGENTS_ROOT=str(tmp_path), VERIFY_PORT=None):
        do_new("P", roles="xhigh:1")
        monkeypatch.setattr(services.subprocess, "run", missing)
        row = services.main_status(["P"])[0]
    assert row["running"] is None and "unavailable" in row["detail"]


def test_unknown_liveness_is_not_a_death(tmp_path):
    with env(PHAROS_AGENTS_ROOT=str(tmp_path), VERIFY_PORT=None):
        do_new("P", roles="xhigh:1")
        rows = [{"ts": n, "workers": [{"worker": "xhigh", "alive": alive}]}
                for n, alive in enumerate([True, None, False, True, False])]
        (L.project_dir("P") / "monitor.jsonl").write_text("\n".join(map(json.dumps, rows)))
        assert usage._monitor_summary("P")["worker_deaths"] == {"xhigh": 1}


@pytest.mark.parametrize("spec", ["max:1,MAX:1", "xhigh:1,xhigh:1", "max:2,max2:1"])
def test_case_insensitive_worker_collisions_are_rejected(spec):
    with pytest.raises(ValueError, match="worker name"):
        L.parse_roles(spec)


def test_offline_doctor_never_checks_backend(monkeypatch, tmp_path):
    stub = tmp_path / "codex"
    stub.write_text("#!/bin/sh\necho codex-stub\n")
    stub.chmod(0o755)
    monkeypatch.setattr(health, "check_codex", lambda: pytest.fail("live model check"))
    with env(PHAROS_CODEX_BIN=str(stub), PHAROS_AGENTS_ROOT=str(tmp_path / "projects"),
             PHAROS_RUNTIME=str(tmp_path / "runtime")):
        rows = health.doctor(offline=True)
    backend = next(row for row in rows if row["label"] == "codex backend")
    assert backend["state"] == "warn" and "NOT tested" in backend["detail"]


def test_doctor_reports_missing_codex_instead_of_crashing(monkeypatch, tmp_path):
    with env(PHAROS_CODEX_BIN=str(tmp_path / "no-codex"),
             PHAROS_AGENTS_ROOT=str(tmp_path / "projects")):
        rows = health.doctor(offline=True)
    assert next(row for row in rows if row["label"] == "codex")["state"] == "FAIL"


def test_offline_and_probe_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["doctor", "--offline", "--probe"])


@pytest.mark.parametrize("pid", [0, -1, -100])
def test_nonpositive_pids_are_never_signalled(monkeypatch, pid):
    monkeypatch.setattr(services.os, "killpg", lambda *a: pytest.fail("unsafe signal"))
    monkeypatch.setattr(services.os, "kill", lambda *a: pytest.fail("unsafe signal"))
    assert services.is_alive(pid) is False
    assert services.kill_group(pid) is False


def test_ps_zombie_fallback(monkeypatch):
    monkeypatch.setattr(services.os, "kill", lambda *a: None)
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError()))
    monkeypatch.setattr(services.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="Z+\n"))
    assert services.is_alive(12345) is False


@pytest.mark.parametrize("output,alive", [("12345 S\n", True), ("12345 Z\n", False), ("999 S\n", False)])
def test_group_probe_permission_race_uses_ps(monkeypatch, output, alive):
    def denied(*args):
        raise PermissionError()
    monkeypatch.setattr(services.os, "killpg", denied)
    monkeypatch.setattr(services.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout=output))
    assert services.process_group_alive(12345) is alive


@pytest.mark.skipif(sys.platform != "darwin", reason="native macOS RSS watchdog")
def test_native_rss_limit_kills_job_without_rlimit_as(tmp_path):
    comp = tmp_path / "computation"
    comp.mkdir()
    # A tiny cap deterministically catches the interpreter, without large allocations.
    rc = compute._run_job([sys.executable, "-c", "import time; time.sleep(10)"],
                          comp, seconds=5, preexec=None, rss_limit=1024 * 1024)
    assert rc == 137


def test_runtime_paths_with_spaces_work_without_sourcing_env(monkeypatch, tmp_path):
    import shlex
    from pharos import codex
    root = tmp_path / "install with spaces and 'quotes'"
    root.mkdir()
    node = root / "node"
    node.write_text("#!/bin/sh\nexit 0\n")
    node.chmod(0o755)
    entry = root / "codex.js"
    entry.write_text("// stub")
    settings = {"PHAROS_NODE": str(node), "PHAROS_CODEX_JS": str(entry)}
    (root / "runtime.env").write_text("".join(
        f"export {key}={shlex.quote(value)}\n" for key, value in settings.items()))
    monkeypatch.setenv("PHAROS_RUNTIME", str(root))
    for key in settings:
        monkeypatch.delenv(key, raising=False)
    assert codex._runtime_env() == settings
    captured = []
    def capture(executable, argv, environment):
        captured.append((executable, argv))
        raise RuntimeError("exec-captured")
    monkeypatch.setattr(codex.os, "execve", capture)
    with pytest.raises(RuntimeError, match="exec-captured"):
        codex.main(["--version"])
    assert captured == [(str(node), [str(node), str(entry), "--version"])]


def test_confirmed_group_member_rss_denial_fails_closed(monkeypatch):
    class Denied(Exception):
        pass
    class Gone(Exception):
        pass
    class Process:
        pid = 12345
        def memory_info(self):
            raise Denied()
    fake = SimpleNamespace(AccessDenied=Denied, NoSuchProcess=Gone,
                           process_iter=lambda *a: [Process()])
    monkeypatch.setitem(sys.modules, "psutil", fake)
    monkeypatch.setattr(compute.os, "getpgid", lambda _: 12345)
    with pytest.raises(SystemExit, match="cannot enforce RSS cap"):
        compute._group_rss(12345)


def test_rss_sampling_failure_still_cleans_up_job(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "psutil", SimpleNamespace())
    def denied(*a):
        raise SystemExit("RSS unavailable")
    monkeypatch.setattr(compute, "_group_rss", denied)
    original = subprocess.Popen
    jobs = []
    def spawn(*a, **kw):
        proc = original(*a, **kw)
        jobs.append(proc)
        return proc
    monkeypatch.setattr(compute.subprocess, "Popen", spawn)
    with pytest.raises(SystemExit, match="RSS unavailable"):
        compute._run_job([sys.executable, "-c", "import time; time.sleep(10)"],
                         tmp_path, 5, None, rss_limit=1024)
    assert jobs[0].poll() is not None


def test_timeout_cleans_up_spawned_child_processes(tmp_path):
    script = tmp_path / "tree.py"
    child_file = tmp_path / "child.pid"
    script.write_text("import subprocess,sys,time\nfrom pathlib import Path\n"
                      "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)'])\n"
                      f"Path({str(child_file)!r}).write_text(str(child.pid))\n"
                      "time.sleep(30)\n")
    assert compute._run_job([sys.executable, str(script)], tmp_path, 1, None) == 124
    pid = int(child_file.read_text())
    end = time.monotonic() + 5
    while services.is_alive(pid) and time.monotonic() < end:
        time.sleep(0.05)
    assert not services.is_alive(pid)
