# macOS preview validation

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
