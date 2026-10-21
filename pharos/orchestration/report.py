"""Generate Markdown in a sandboxed fresh Codex session; render PDF in the host.

The reporter never needs to launch a browser. The calling host process renders
only this run's requested Markdown, and returns success only for a valid PDF.
"""

from __future__ import annotations

import json
from pathlib import Path
import stat
import subprocess
import time
import uuid

from pharos import codex
from pharos.execution import layout as L
from pharos.execution.scaffold import ensure_reporter_home
from . import render as pdf_renderer

_PROMPT = """Read AGENTS.md and produce the report now.
Report output: {output}
Write your Markdown report to exactly that path. Complete the contract's fact
and format self-checks, then end the session. Do not run pharos render, start a
browser, generate PDF, or troubleshoot browser permissions. The calling Pharos
host renders and validates the PDF after your session finishes.
"""


def _gateway_config(project: str) -> str:
    """Pin the reporter's reader gateway even without trusted local config."""
    import sys

    quote = lambda value: json.dumps(str(value), ensure_ascii=False)
    return ('mcp_servers.pharos={command=' + quote(sys.executable)
            + ',args=["-m","pharos.gateway"],default_tools_approval_mode="approve",'
            + 'env={PHAROS_ROLE="reader",PHAROS_AUTHOR="reporter",PHAROS_PROJECT_DIR='
            + quote(L.project_dir(project)) + '}}')


def _fresh_file(path: Path, directory: Path) -> bool:
    try:
        info = path.lstat()
        return (stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and path.resolve().parent == directory.resolve()
                and info.st_size > 0)
    except OSError:
        return False


def run(project: str) -> int:
    home = ensure_reporter_home(project)
    reports = L.human_report_dir(project)
    md_dir, pdf_dir = reports / "md", reports / "pdf"
    project_root = L.project_dir(project).resolve()
    if any(path.is_symlink() or not path.resolve().is_relative_to(project_root)
           for path in (reports, md_dir, pdf_dir)):
        print("[pharos report] unsafe report output directory; no session started")
        return 1
    md_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    run_id = f"{L.project_dir(project).name}_{time.strftime('%y%m%d%H%M%S')}_{uuid.uuid4().hex[:12]}"
    md_path, pdf_path = md_dir / (run_id + ".md"), pdf_dir / (run_id + ".pdf")
    # Never accept a previous report or overwrite an unrelated output.
    if md_path.exists() or md_path.is_symlink() or pdf_path.exists() or pdf_path.is_symlink():
        print("[pharos report] output name collision; no session started")
        return 1
    log_path = home / "logs" / (run_id + ".log")

    codex_bin = codex.resolve_bin()
    cmd = codex.exec_cmd(
        codex_bin, codex.model(), codex.effort(),
        "-C", str(home),
        "--skip-git-repo-check",
        "--sandbox", "workspace-write",
        "--add-dir", str(md_dir),
        "-c", _gateway_config(project),
        "-",
    )
    with log_path.open("w", encoding="utf-8") as logf:
        completed = subprocess.run(
            cmd, input=_PROMPT.format(output=json.dumps(str(md_path), ensure_ascii=False)),
            text=True, stdout=logf, stderr=subprocess.STDOUT, cwd=str(home),
            env=codex.subprocess_env(codex_bin, codex_home=home / ".codex-home"),
        )

    print(f"[pharos report] log: {log_path}")
    if completed.returncode:
        print(f"[pharos report] reporter failed (rc={completed.returncode}); PDF not attempted")
        return completed.returncode
    if not _fresh_file(md_path, md_dir):
        print("[pharos report] missing, empty or unsafe Markdown output; PDF not attempted")
        return 1
    try:
        if not md_path.read_text(encoding="utf-8").strip():
            raise ValueError("Markdown contains only whitespace")
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"[pharos report] invalid Markdown: {exc}; PDF not attempted")
        return 1
    print(f"[pharos report] wrote: {md_path}")
    if pdf_path.exists() or pdf_path.is_symlink():
        print("[pharos report] PDF path already exists; refusing to overwrite it")
        return 1
    try:
        # Runs here, in the calling host, never in the reporter's Codex sandbox.
        pdf_renderer.render(md_path, pdf_path)
        if not _fresh_file(pdf_path, pdf_dir):
            raise ValueError("missing, empty or unsafe PDF output")
        from pypdf import PdfReader
        with pdf_path.open("rb") as stream:
            if stream.read(5) != b"%PDF-":
                raise ValueError("output is not a PDF")
            stream.seek(0)
            parsed = PdfReader(stream, strict=True)
            if parsed.is_encrypted or not parsed.pages:
                raise ValueError("PDF must be unencrypted and contain at least one page")
    except (Exception, SystemExit) as exc:
        print(f"[pharos report] host PDF render failed: {exc}")
        print(f"[pharos report] Markdown preserved: {md_path}")
        print("[pharos report] retry only pharos render from the host; no new model call is needed")
        return 1
    print(f"[pharos report] wrote: {pdf_path}")
    return 0
