"""Math rendering, report paths, and optional Chromium PDF tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from pharos.orchestration import render as R

_MD = """# The contraction estimate: a progress report

Some prose with math: let $a_{i} \\le b_{j}^{*}$ and consider
$$\\int_0^1 f(x)\\,dx = \\sum_{n \\ge 1} c_n.$$

## Key theorems

| route | status |
|---|---|
| weighted energy | proved |
"""


def test_math_survives_markdown():
    html = R.build_html(_MD)
    # underscores/asterisks inside math must NOT become <em>/<strong>
    assert r"\(a_{i} \le b_{j}^{*}\)" in html
    assert r"\int_0^1" in html and "<em>" not in html.split("math-display")[1][:80]
    assert "<title>The contraction estimate: a progress report</title>" in html
    assert "<table>" in html                        # tables enabled for reports
    assert "MathJax" in html
    assert 'packages: ["base", "ams", "newcommand", "noundefined"]' in html


def test_model_html_and_images_are_inert():
    payload = '# safe title\n\n<script>alert("unsafe")</script>\n\n![track](https://example.invalid/track.png)\n'
    html = R.build_html(payload)
    assert '<script>alert("unsafe")</script>' not in html
    assert "&lt;script&gt;" in html
    assert "<img" not in html


def test_default_pdf_pairing(tmp_path: Path):
    md = tmp_path / "human_report" / "md" / "2026-09-01T12.md"
    assert R.default_pdf_path(md) == tmp_path / "human_report" / "pdf" / "2026-09-01T12.pdf"
    loose = tmp_path / "note.md"
    assert R.default_pdf_path(loose) == tmp_path / "note.pdf"


@pytest.mark.skipif(not R.chrome_bin() or not R.mathjax_src().startswith("file:"),
                    reason="Chrome and local MathJax required for resource-boundary check")
def test_mathjax_cannot_load_model_resources(tmp_path, monkeypatch):
    import http.server
    import subprocess
    import threading
    from urllib.parse import unquote, urlparse

    local_js = Path(unquote(urlparse(R.mathjax_src()).path)).read_bytes()
    requests = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(200 if self.path == "/tex-svg.js" else 204)
            self.send_header("Content-Type", "application/javascript")
            self.end_headers()
            if self.path == "/tex-svg.js":
                self.wfile.write(local_js)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"
    monkeypatch.setattr(R, "mathjax_src", lambda: origin + "/tex-svg.js")
    payload = ("# Host resource boundary\n\n$1+1=2$\n\n"
               + rf"$\style{{background-image:url({origin}/forbidden-style)}}{{x}}$" + "\n\n"
               + rf"$\require{{html}}\style{{background:url({origin}/forbidden-require)}}{{y}}$" + "\n\n"
               + r"$\href{javascript:alert(1)}{z}$" + "\n\n"
               + f"![model image]({origin}/forbidden-image)\n")
    page = tmp_path / "boundary.html"
    page.write_text(R.build_html(payload), encoding="utf-8")
    try:
        done = subprocess.run(
            [R.chrome_bin(), "--headless", "--disable-gpu", "--no-first-run",
             "--no-default-browser-check", f"--user-data-dir={tmp_path / 'profile'}",
             "--virtual-time-budget=20000", "--dump-dom", page.as_uri()],
            capture_output=True, text=True, timeout=40, check=True,
        )
        assert "<mjx-container" in done.stdout  # the real MathJax executed
        assert set(requests) == {"/tex-svg.js"}
        assert 'href="javascript:' not in done.stdout
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


@pytest.mark.skipif(not R.chrome_bin(), reason="no chromium/chrome on host")
def test_render_end_to_end(tmp_path: Path):
    md = tmp_path / "human_report" / "md" / "r1.md"
    md.parent.mkdir(parents=True)
    md.write_text(_MD, encoding="utf-8")
    out = R.render(md)
    assert out == tmp_path / "human_report" / "pdf" / "r1.pdf"
    assert out.stat().st_size > 10_000               # a real PDF, not an error page
    assert out.read_bytes()[:5] == b"%PDF-"
