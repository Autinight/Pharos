# macOS preview validation

## 3.1.1a3 — sandboxed Markdown, host-rendered PDF

Validated 2026-10-21 on Apple Silicon, Darwin 25.5.0, Python 3.12.14.
This validation used offline writer stubs, native Codex **0.163.0** sandboxing,
and real Chrome. **No Pharos/Codex model inference was requested.**

| Check | Result |
| --- | --- |
| Final full regression | **218 passed**, 67.32 seconds, no skips |
| Bash syntax / Python compilation / diff whitespace | Passed |
| Native Codex sandbox writer | Markdown written to the explicitly writable output directory |
| Write outside reporter home and Markdown directory | Denied with `PermissionError`; probe file absent |
| Calling-host Chrome rendering | Passed; distinct host/writer PIDs; **49,971-byte, one-page PDF** |
| PDF structure | Strict `pypdf` parsing, unencrypted, nonzero pages |
| Fresh output identity | Exact UUID-named Markdown/PDF pair; old or unrequested reports rejected |
| Bad output regressions | Empty/whitespace Markdown, symbolic/hard links, bad/truncated PDFs rejected |
| Writer/render failure | Nonzero result; Markdown retained for render-only retry |
| Host content boundary | Raw HTML and Markdown images disabled; MathJax packages explicitly limited |
| Real-browser resource check | MathJax ran; only the fixed local-server `tex-svg.js` was requested; no model-supplied URL/style/image requests |
| Dependency installation | `pypdf>=6` in core dependencies and bootstrap health check; validated with 6.21.1 |
| Live model end-to-end rerun | **Not performed** for a3; a2's historical results below remain unchanged |
| Intel macOS / Linux hardware | Not exercised |

The reporter now runs with `workspace-write`, adds only `human_report/md` as
an extra writable directory, and pins the project's Pharos **reader** gateway.
It finishes after Markdown self-check. The invoking host renders the exact
requested file only after a successful writer exit, and validates the PDF.
This removes the reporter's browser/retry loop without weakening its sandbox.

The native offline check used `codex sandbox -c 'sandbox_mode="workspace-write"'`
and explicit Markdown writable roots with an isolated, empty shared Codex home.
The native CLI's `sandbox` command directly accepts command arguments; it has
no `macos` subcommand. Its `--cd` flag is reserved for named permission-profile
invocations, so the legacy-policy check inherits the reporter's cwd instead.
This tests the actual filesystem/process boundary, not model compliance or
new OAuth/network inference. The full suite used an installed local MathJax
asset via `PHAROS_MATHJAX_JS`, so the browser resource test needed no CDN.

An initial full run failed to obtain the existing cleanup stub's PID before
its one-second deadline. That fixture now uses pytest's current interpreter
instead of PATH-based Python lookup. Neither production nor test timeouts were
increased; full process-tree cleanup assertions pass in the final run.

Moving rendering to a caller does not remove an outer sandbox inherited by
that caller. Invoke the report from a browser-capable host terminal/runner;
if needed, retry only `pharos render <saved-md>` there. No macOS privacy
permissions, HanaAgent signing, credentials, or global Codex settings changed.

## 3.1.1a2 — Codex 0.163.0 and headless MCP compatibility

Validated 2026-10-20; report PDF recovered on the host 2026-10-21.
Host: Apple Silicon (arm64), Darwin 25.5.0, Python 3.12.14.

| Check | Result |
| --- | --- |
| Final regression suite | **197 passed**, 66.70 seconds, no skips |
| Bash syntax / Python compilation / diff whitespace | Passed |
| Bootstrap plan | Default Codex **0.163.0** and explicit override covered |
| Broken native CLI despite matching package metadata | Fails closed; regression passed |
| Isolated installer upgrade | Passed in a path with spaces, temporary HOME and CLI-link directory |
| Native Codex | **codex-cli 0.163.0** |
| Existing ChatGPT OAuth, gpt-6.1-sol | Live probe returned **PHAROS_OAUTH_61_OK**, exit 0 |
| Headless Pharos MCP | Explicit approval scoped to the local Pharos server; role/project restrictions retained |
| Real worker and fresh-session verifier | **Passed**, gpt-6.1-sol / low; verdict **correct**, no critical errors or gaps |
| Fact graph | Accepted fact **0d5cc08a111e25e7** for the elementary prime-square divisibility theorem |
| Reporter Markdown | Generated using gpt-6.1-sol; checked against the accepted fact |
| PDF regression | Passed with installed Chrome |
| Demo PDF recovery | Host rendering passed; PDF signature checked, **265,035 bytes** |
| Fully unattended report inside the demo Codex sandbox | **Not passed**; browser abort followed by the report-stage timeout |
| Intel macOS / Linux hardware | Not exercised |

The real demonstration used one worker and one round, the existing OAuth,
no literature searches, and only **gpt-6.1-sol** after the user's model choice.
No credentials or global Codex configuration were changed. No model fallback
was permitted. Earlier failed demo attempts are not counted as successful runs.

The first new-CLI demo exposed a separate headless MCP approval requirement.
Generated actor configs and the verifier's inline config now set
`default_tools_approval_mode="approve"` only on `mcp_servers.pharos`, using the
field and enum in the official `rust-v0.163.0` configuration schema. Other MCP
servers and sandbox settings are unchanged. Existing main configs require the
migration documented in [macos.md](macos.md); old CLI overrides are unvalidated.

The demo-only adapter retained **workspace-write**, unlike upstream Pharos's
usual bypass mode. Its reporter wrote Markdown, but Chrome/Edge aborted inside
that nested Codex sandbox; the bounded report process was stopped at its time
limit and the verifier was shut down. The original receipt correctly remains
`success: false`. A separate host-side render of that existing Markdown then
produced the checked PDF, without another model call or relaxing the model's
sandbox. This is a documented recovery, **not** a claim that the fully
unattended sandboxed report step succeeded.

The upgrade's regression, installer, native CLI, OAuth and Pharos MCP checks
passed. The installable preview contains source only and downloads dependencies
on installation. Credentials, private config, generated runtimes and demo
projects are excluded. Installation does not start research or inference.

## Historical validation: 3.1.1a1

Date: 2026-10-20. Host: Apple Silicon (arm64), Darwin 25.5.0,
Python 3.12.14. The historical checks below used no real model credentials
or autonomous research jobs.

## Results

| Check | Result |
| --- | --- |
| Upstream baseline on this Mac | 143 passed, 13 failed, 1 skipped |
| Final full regression suite | **192 passed, 1 skipped**, 63.89 seconds |
| Python compilation | Passed |
| Bash syntax (bootstrap/platform/env/installer) | Passed |
| Node archive platform matrix | Darwin arm64/x64 and Linux arm64/x64 selection covered |
| Bash and zsh environment sourcing | Passed, including a checkout with spaces |
| Full isolated bootstrap | **Passed**, including actual Node + Python + Codex downloads/install |
| Native Codex CLI | `codex-cli 0.153.4`, launched before sourcing environment settings |
| Native installed CLI scaffold | Passed; one test worker created, not started |
| Native installed computation | Passed, with 64 MiB RSS guard and 5-second timeout |
| RSS excess / sampling failure / child timeout cleanup | Covered by passing regressions |
| Human-report PDF integration | **Skipped**: Chrome/Chromium absent on host |
| Real model login, API calls and mathematical research | **Not performed** |
| Intel macOS hardware and Linux runtime | **Not exercised**; archive selection / portable code only |

The complete installer ran in a disposable source directory **with spaces**,
a temporary HOME and a temporary CLI-link directory. It did not replace the
user's global Codex or install a persistent main-agent session. Generated
runtime state, downloads, logs and test projects are excluded from the bundle.

`doctor --offline` was also executed using the installed runtime. It correctly
reported the absent Codex configuration, tmux and Chrome as failures. These are
unconfigured/optional-workflow prerequisites, not a claim that the full research
stack is ready. Backend status was explicitly skipped; no model request was made.
Codex's first `--version` emitted a warning that the unconfigured shared home
was absent, then exited successfully and reported the expected native version.

## Scope and limitations

This is a native macOS **preview**, not a signed desktop app. The installer
bundle downloads dependencies on first use; it does not bundle a model or
supply credentials. Read [macos.md](macos.md) before enabling research.

The port preserves the upstream trust boundary: autonomous agents can bypass
Codex approvals/sandbox checks. The macOS RSS watchdog is sampled, has no
collective RAM/CPU quota, and only covers `pharos compute`. Existing numeric-PID
identity and short-tag tmux collision limitations remain documented. A dedicated
account or VM is still recommended.
