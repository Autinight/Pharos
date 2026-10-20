# macOS preview (Autinight fork)

This fork adds native macOS support while retaining the Linux path. This is a
command-line research system, not a signed `.app`. Upstream is
[frenzymath/Pharos](https://github.com/frenzymath/Pharos).

## Install

Use a **dedicated macOS account or VM**, not a personal account containing
sensitive files. Autonomous research still disables Codex approvals and sandbox
checks. This port does not change that trust boundary.

Requirements: macOS, Git, Bash (the included `/bin/bash` 3.2 is sufficient), curl,
tar and **Python 3.10+**. Apple's `/usr/bin/python3` may be too old. For example:

```bash
brew install python@3.12 tmux tectonic
brew install --cask google-chrome
```

Homebrew is optional if equivalent dependencies are already installed. Chrome
and TeX are needed for PDF workflows; tmux is needed for the resident main
session. The installer never runs Homebrew automatically.

Keep the checkout/extracted installer folder in a persistent location. The
runtime and the user CLI link reference that folder; do not move or delete it
after installation.

```bash
git clone --branch feat/macos-support https://github.com/Autinight/Pharos.git
cd Pharos
bash scripts/bootstrap.sh --print-plan  # read-only, no downloads or writes
bash scripts/bootstrap.sh
source scripts/env.sh                  # works in Bash and macOS's default zsh
pharos doctor --offline                # no model/literature backend requests
```

The downloadable installer bundle also provides **Install Pharos.command**;
it invokes the same bootstrap. Installation downloads a matching Node runtime,
the pinned Codex CLI, Python dependencies and MathJax. It installs an editable
Python package under `runtime/venv` and links only `pharos` into `~/.local/bin`.
It does **not** replace your global `codex`, configure a login unless supplied
settings request it, install a launch agent, or start research. Set
`PHAROS_LOCAL_BIN` to choose a different CLI-link directory, or
`PHAROS_BOOTSTRAP_PYTHON` to choose an explicit Python interpreter.

Configure credentials separately using [getting started](getting-started.md).
`pharos doctor` and `pharos doctor --probe` may make billable model API requests;
`--probe` also tests PDF, TeX and literature retrieval. `--offline` cannot be
combined with `--probe`. Missing tools/configuration still appear as failures;
"offline" does not mean "everything passed".

## Platform behavior

| Component | macOS behavior |
| --- | --- |
| Node bootstrap | Selects `darwin-arm64` or `darwin-x64`, checks SHA-256 before extraction |
| Python | Rejects Python older than 3.10; searches versioned interpreters |
| Shell paths | Quoted runtime paths; Bash/zsh source-file detection |
| Directory usage | Python traversal, no GNU `du -b`; external symlink targets are not followed |
| Computation memory | `psutil` samples total process-group RSS every ~0.1 s; exit 137 on excess |
| Computation timeout | New process group; timeout returns 124 and cleans up that group's descendants |
| CPU / total RAM | Low CPU priority only; **no systemd/cgroup CPU quota or collective RAM cap** |
| Process liveness | `ps` fallback recognizes unreaped zombies without consuming another caller's wait status |
| Monitoring | Linux-only PSI/disk/process-I/O fields remain `null` when unavailable |
| Missing tmux | Main-session status is `unknown`; local monitoring continues |
| PDF reports | Finds Chrome/Chromium in `/Applications` and `~/Applications`; isolated temporary browser profile |
| Worker names | Rejects duplicate/case-folding name collisions before creating directories |

RSS enforcement is **best effort**, not a hard kernel memory boundary: brief
allocation spikes between samples, shared pages counted multiple times, and
processes deliberately leaving the group are limitations. Start with one worker,
a short deadline and a small round limit on a machine with adequate headroom.
`PHAROS_MAX_ROUNDS=0` still means unlimited. These limits only apply to scripts
launched through `pharos compute`, not arbitrary commands run by agents.

## Remaining inherited limitations

- LLM verification is not a formal proof certificate; use human mathematical review.
- Agents retain the account's filesystem/network permissions. This is not an OS sandbox.
- Long-lived service/worker PID files do not authenticate process start identity;
  stale/reused PIDs can still be hazardous. Inspect processes before stopping old deployments.
- Main tmux sessions still use short tags. Do not run two deployments/projects with
  the same tag on the same tmux server. Session lookups use exact matching but
  identical tags still collide.
- Services default to loopback and do not provide public-network authentication.

## Development / validation

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest pharos/ -q
bash -n scripts/bootstrap.sh scripts/platform.sh scripts/env.sh
```

Model calls in the test suite use local stubs. The native macOS watchdog test
runs a small, local sleeping process; it does not call a model. Chrome PDF
integration is conditional on an installed browser. An optional GitHub Actions
template for Linux and macOS is provided at `docs/ci-tests.yml`; it is not
activated automatically. Remote CI and Linux hardware runs are separate checks,
not implied by the local macOS results.

The initial local port is validated on Apple Silicon with Python 3.12. Intel
macOS archive selection is covered by tests, but this is not a claim of an
Intel hardware end-to-end run. Real backend login and autonomous research are
separate checks and require the user's explicit configuration.
