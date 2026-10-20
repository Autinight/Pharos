# macOS preview validation: 3.1.1a1

Date: 2026-10-20. Host: Apple Silicon (arm64), Darwin 25.5.0,
Python 3.12.14. No real model credentials or autonomous research jobs were used.

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
