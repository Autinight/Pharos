"""Offline report tests: a stub replaces model inference; PDF runs in the host."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from pharos.execution.scaffold import do_new
from pharos.orchestration import report
from pharos.tests.util import env

_STUB = r'''#!/usr/bin/env python3
import json, os, sys
from pathlib import Path

home = Path.cwd()
with Path(os.environ["STUB_ARGV_LOG"]).open("a", encoding="utf-8") as f:
    f.write(json.dumps(sys.argv) + "\n")
prompt = sys.stdin.read()
print("CODEX_HOME=" + os.environ.get("CODEX_HOME", ""))
print("WRITER_PID=" + str(os.getpid()))
print(prompt)
mode = os.environ.get("STUB_MODE", "normal")
if mode == "fail":
    raise SystemExit(7)
if mode == "missing":
    raise SystemExit(0)
output = json.loads(next(line.split(": ", 1)[1] for line in prompt.splitlines()
                         if line.startswith("Report output: ")))
md = Path(output)
if mode == "other":
    md = md.parent / "unrequested.md"
if mode in ("symlink", "hardlink"):
    target = home / "not-the-requested-report.md"
    target.write_text("# outside the output directory\n")
    if mode == "symlink":
        md.symlink_to(target)
    else:
        os.link(target, md)
else:
    md.write_text("" if mode == "empty" else " \n\t" if mode == "whitespace" else "# stub report\n\nOffline writer; host renders PDF.\n")
'''


def _project(tmp: Path) -> Path:
    contract = tmp / "worker.md"
    contract.write_text("# stub\n")
    (tmp / "skills").mkdir(exist_ok=True)
    with env(PHAROS_AGENTS_ROOT=str(tmp / "agents"),
             PHAROS_WORKER_CONTRACT=str(contract),
             PHAROS_WORKER_SKILLS=str(tmp / "skills"),
             PHAROS_VERIFY_URL=None, VERIFY_PORT=None):
        do_new("P", roles="low:1", model="gpt-6.1-sol")
    return tmp / "agents" / "P"


def _run(tmp, mode="normal"):
    stub = tmp / "codex_stub.py"
    stub.write_text(_STUB, encoding="utf-8")
    stub.chmod(0o755)
    with env(PHAROS_AGENTS_ROOT=str(tmp / "agents"), PHAROS_CODEX_BIN=str(stub),
             PHAROS_CODEX_MODEL="gpt-6.1-sol", PHAROS_CODEX_EFFORT="low",
             STUB_ARGV_LOG=str(tmp / "argv.log"), STUB_MODE=mode):
        return report.run("P")


def test_gateway_config_has_scoped_toml_structure(tmp):
    tomllib = pytest.importorskip("tomllib")
    import sys
    with env(PHAROS_AGENTS_ROOT=str(tmp / 'quoted "root"')):
        config = tomllib.loads(report._gateway_config("P 你好"))
    assert set(config) == {"mcp_servers"}
    assert set(config["mcp_servers"]) == {"pharos"}
    gateway = config["mcp_servers"]["pharos"]
    assert gateway["command"] == sys.executable
    assert gateway["args"] == ["-m", "pharos.gateway"]
    assert gateway["default_tools_approval_mode"] == "approve"
    assert gateway["env"] == {
        "PHAROS_ROLE": "reader", "PHAROS_AUTHOR": "reporter",
        "PHAROS_PROJECT_DIR": str(tmp / 'quoted "root"' / "P 你好"),
    }


def test_report_fresh_session_writes_and_never_resumes(tmp: Path, monkeypatch):
    pdir = _project(tmp)
    renders = []

    def host_render(md, pdf):
        assert os.getpid() == parent_pid
        assert md.is_file()
        renders.append((md, pdf))
        from pypdf import PdfWriter
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.write(pdf)
        return pdf

    parent_pid = os.getpid()
    monkeypatch.setattr(report.pdf_renderer, "render", host_render)
    assert _run(tmp) == 0
    assert _run(tmp) == 0  # unique paths/logs even within the same second
    logs = sorted((pdir / "reporter/logs").glob("*.log"))
    assert len(logs) == 2
    home_marker = "CODEX_HOME=" + str(pdir / "reporter/.codex-home")
    assert all(home_marker in log.read_text() for log in logs)
    assert all("Do not run pharos render" in log.read_text() for log in logs)
    assert all("WRITER_PID=" + str(parent_pid) + "\n" not in log.read_text() for log in logs)
    runs = [json.loads(line) for line in (tmp / "argv.log").read_text().splitlines()]
    assert len(runs) == 2
    for argv in runs:
        assert "resume" not in argv
        assert "--dangerously-bypass-approvals-and-sandbox" not in argv
        assert argv[argv.index("--sandbox") + 1] == "workspace-write"
        assert argv[argv.index("--add-dir") + 1] == str(pdir / "human_report/md")
        wiring = next(arg for arg in argv if arg.startswith("mcp_servers.pharos="))
        assert 'PHAROS_ROLE="reader"' in wiring
        assert 'default_tools_approval_mode="approve"' in wiring
        assert str(pdir) in wiring
    assert len(list((pdir / "human_report/md").glob("*.md"))) == 2
    assert len(list((pdir / "human_report/pdf").glob("*.pdf"))) == 2
    assert len(renders) == 2
    assert all(md.stem == pdf.stem for md, pdf in renders)


@pytest.mark.parametrize("mode", ["fail", "missing", "empty", "whitespace", "other", "symlink", "hardlink"])
def test_writer_failure_or_wrong_artifact_never_renders(tmp, monkeypatch, mode):
    pdir = _project(tmp)
    (pdir / "human_report/md/old.md").write_text("# old report\n")
    (pdir / "human_report/pdf/old.pdf").write_bytes(b"%PDF-old")
    monkeypatch.setattr(report.pdf_renderer, "render", lambda *a: pytest.fail("must not render"))
    assert _run(tmp, mode) == (7 if mode == "fail" else 1)
    assert [p.name for p in (pdir / "human_report/pdf").glob("*.pdf")] == ["old.pdf"]


@pytest.mark.parametrize("error", [SystemExit("Chrome unavailable"),
                                    subprocess.TimeoutExpired("chrome", 180),
                                    OSError("browser could not start")])
def test_render_failure_preserves_markdown_and_fails(tmp, monkeypatch, capsys, error):
    pdir = _project(tmp)

    def broken(*args):
        raise error

    monkeypatch.setattr(report.pdf_renderer, "render", broken)
    assert _run(tmp) == 1
    markdown = list((pdir / "human_report/md").glob("*.md"))
    assert len(markdown) == 1 and markdown[0].stat().st_size > 0
    assert "no new model call is needed" in capsys.readouterr().out


@pytest.mark.parametrize("contents", [b"", b"not a PDF", b"%PDF-", b"%PDF-1.7\n%%EOF\n"])
def test_invalid_pdf_cannot_report_success(tmp, monkeypatch, contents):
    _project(tmp)

    def invalid(md, pdf):
        pdf.write_bytes(contents)
        return pdf

    monkeypatch.setattr(report.pdf_renderer, "render", invalid)
    assert _run(tmp) == 1


def test_hardlinked_pdf_cannot_report_success(tmp, monkeypatch):
    pdir = _project(tmp)
    previous = pdir / "human_report/pdf/previous.pdf"
    from pypdf import PdfWriter
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    writer.write(previous)

    def reuse(md, pdf):
        os.link(previous, pdf)
        return pdf

    monkeypatch.setattr(report.pdf_renderer, "render", reuse)
    assert _run(tmp) == 1


@pytest.mark.parametrize("directory", ["md", "pdf"])
def test_symlinked_output_directory_is_rejected_before_launch(tmp, directory):
    pdir = _project(tmp)
    outside = tmp / "outside"
    outside.mkdir()
    target = pdir / "human_report" / directory
    target.rmdir()
    target.symlink_to(outside, target_is_directory=True)
    assert _run(tmp) == 1
    assert not (tmp / "argv.log").exists()
    assert not list(outside.iterdir())


@pytest.mark.skipif(not report.pdf_renderer.chrome_bin(), reason="Chrome/Chromium not installed")
def test_real_host_chrome_after_offline_writer(tmp, monkeypatch):
    pdir = _project(tmp)
    # No external CDN is needed for this plain-text fixture.
    monkeypatch.setattr(report.pdf_renderer, "mathjax_src", lambda: "data:text/javascript,void(0)")
    assert _run(tmp) == 0
    pdfs = list((pdir / "human_report/pdf").glob("*.pdf"))
    assert len(pdfs) == 1
    assert pdfs[0].read_bytes().startswith(b"%PDF-")
    assert pdfs[0].stat().st_size > 1000
