# Local macOS Headroom overlay

Temporary host setup so **Grok 4.6**, **ChatGPT.app / Codex**, and **Claude CLI** share Headroom without using `headroom wrap grok-build` (that wrap only routes the `grok-build` model).

Upstream `headroom/` stays stock except a small **bandage patch** (xAI model-list `context_window` alias). Everything else lives here or under `~/.headroom` / LaunchAgents.

## What runs

| Port | Job | Traffic |
|------|-----|---------|
| 8787 | `com.headroom.proxy.openai` | ChatGPT.app, Codex, Claude (`ANTHROPIC_BASE_URL`) |
| 8789 | `com.headroom.proxy.grok` | Grok 4.6 → `cli-chat-proxy.grok.com` (session auth) |
| 8788 | `com.headroom.mcp.http` | `http://127.0.0.1:8788/mcp` |

`com.headroom.lifecycle` starts those three when **this user** is running a **codesigned** client from a small inventory (`providers.json`: xAI, OpenAI, Anthropic). Matching is the inventory executable path (resolved), not a sibling in the same directory and not a substring of the process name. After the last matched client exits it waits **90 seconds** (configurable). Pause with `touch ~/.headroom/lifecycle/paused`.

Inventory refresh (`refresh-clients.py`):

- daily at 06:20 (`com.headroom.clients-refresh`)
- when `/Applications`, `~/.local/bin`, `~/.grok/{bin,downloads}`, Homebrew bin/cask change (throttled to 5 minutes)
- on `install.sh` / `update.sh`

Result: `~/.headroom/overlay/clients.json`. `apgujeongrok` / `not-grok-nor-gpt` never match unless they are signed by those vendor Team IDs (they are not).

Binary: `~/.headroom/venv/bin/headroom` (editable install of this git checkout), also linked as `~/.local/bin/headroom`. The venv is **Python 3.13**. Do not point LaunchAgents at `~/.pythogoras` or Homebrew/python.org 3.14 (`python3` on PATH may be 3.14; LiteLLM does not install there).

Not used: Serena, torch extras, `headroom wrap grok-build`, `GROK_MODELS_BASE_URL`. The leftover stock job `com.headroom.proxy` (old `~/.pythogoras` 8787) is disabled and the plist is moved aside so it cannot steal the port.

## Commands

```bash
./local-macos/scripts/install.sh     # first-time
./local-macos/scripts/update.sh      # later: official upgrade path + overlay
./local-macos/scripts/refresh-clients.py  # rebuild signed-client inventory
headroom overlay stop               # or: headroom-stop
headroom overlay status
headroom overlay grace 90           # seconds after last client exits
source ~/.headroom/overlay/aliases.zsh   # optional: alias headroom-stop
./local-macos/scripts/verify.sh
./local-macos/scripts/uninstall.sh   # restore previous LaunchAgents + client configs
```

`headroom overlay stop` / `headroom-stop` first lists named inventory clients. If any are running it **notifies and exits** (does not kill Headroom). If none are running it SIGTERM/SIGKILL only the overlay jobs on 8787/8788/8789 plus leftover overlay `mcp serve` / `proxy` processes owned by this user. LaunchAgents stay registered so lifecycle can start them again when a listed client appears.

Dashboards are **per proxy** (separate processes and savings files):

| URL | Traffic |
|-----|---------|
| http://127.0.0.1:8787/dashboard | ChatGPT.app, Codex, Claude |
| http://127.0.0.1:8789/dashboard | Grok 4.6 |

The overlay panel (idle grace + Stop) is injected on both — no upstream HTML edits. Default idle grace is **90 seconds**. Change it there, or with `headroom overlay grace <seconds>`. Grok request rows and prefix-cache reads are on **8789**, not 8787.

Savings/CCR/memory under `~/.headroom/` are never deleted. Config backups: `~/.headroom/overlay-backup/`.

After install or update: **fully quit ChatGPT.app** (tray too) so it reloads `~/.codex/config.toml`.

## How upgrade works

This install is a **git checkout + editable venv**. Official `headroom update` detects that and **refuses** to pip-upgrade. It tells you to `git pull` (checkout) or reinstall from source (editable).

`update.sh` is that official path, plus the overlay:

1. `headroom update --check` — PyPI notice only
2. Reverse the grok bandage if it is on the tree
3. `git pull --ff-only origin main` — what `headroom update` prints for a checkout
4. Re-apply `patches/grok-bandage.patch` (skipped if upstream already has it, or pass `--drop-bandage`)
5. `uv pip install -e ".[proxy,code,relevance,mcp,reports]"` — editable reinstall
6. Re-write LaunchAgents + Grok/Codex/Claude routing
7. Restart the three jobs and `verify.sh`

```bash
./local-macos/scripts/update.sh
./local-macos/scripts/update.sh --drop-bandage   # after upstream ships grok-4.6 model-list support
```

Do not run bare `headroom update` expecting it to move this venv. Do not `pip install -U headroom-ai` into `~/.pythogoras`.

## When to throw the bandage away

Drop `patches/grok-bandage.patch` when origin/main already aliases xAI `context_length` → `context_window` (or wrap routes grok-4.6 with session auth). Keep this overlay until official wrap/install does **grok-4.6** (not only `[model.grok-build]`) and ChatGPT desktop websockets.

Then either keep the lifecycle overlay as-is, or `./local-macos/scripts/uninstall.sh` and use stock `headroom install` / `headroom wrap`.
