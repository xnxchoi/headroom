# Local macOS Headroom overlay
> A temporary fix for `grok-cli`
Grok 4.6, ChatGPT.app / Codex, and Claude CLI share one Headroom checkout. Official `headroom wrap grok-build` only routes the `grok-build` model, so this overlay does the rest.

## What runs

| Port | Job                         | Traffic                                             |
| ---- | --------------------------- | --------------------------------------------------- |
| 8787 | `com.headroom.proxy.openai` | ChatGPT.app, Codex, Claude ( `ANTHROPIC_BASE_URL`)  |
| 8789 | `com.headroom.proxy.grok`   | Grok 4.6 → `cli-chat-proxy.grok.com` (session auth) |
| 8788 | `com.headroom.mcp.http`     | `http://127.0.0.1:8788/mcp`                         |

`com.headroom.lifecycle` starts those three when **this user** is running a **codesigned** client from `providers.json` (xAI, OpenAI, Anthropic). Match is the inventory executable path (resolved), not a sibling in the same directory and not a substring of the process name. After the last matched client exits it waits **90 seconds** (configurable). Pause with `touch ~/.headroom/lifecycle/paused`.

Inventory refresh (`refresh-clients.py`):

- daily at 06:20 (`com.headroom.clients-refresh`)
- when `/Applications`, `~/.local/bin`, `~/.grok/{bin,downloads}`, Homebrew bin/cask change (throttled to 5 minutes)
- on `install.sh` / `update.sh`

Result: `~/.headroom/overlay/clients.json`.

Not used: Serena, torch extras, `headroom wrap grok-build`, `GROK_MODELS_BASE_URL`. Upstream `headroom/` stays stock except the grok bandage.

## Commands

| Command                                          | Description                                                                                             |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| `./local-macos/scripts/install.sh`               | First-time: Python 3.13 venv, editable extras, LaunchAgents, client routing.                            |
| `./local-macos/scripts/update.sh`                | Update the Headroom library \\(merge origin/main into macos-overlay, reinstall venv, reload proxies \\) |
| `./local-macos/scripts/update.sh --drop-bandage` | Same, skip patches/grok-bandage.patch                                                                   |
| `./local-macos/scripts/refresh-clients.py`       | Rebuild signed-client inventory                                                                         |
| `headroom overlay stop`, `headroom-stop`         | Stop overlay jobs if no listed clients are running                                                      |
| `headroom overlay status`                        | Idle grace, listening ports, matched clients                                                            |
| `headroom overlay grace 90`                      | Seconds after last client exits                                                                         |
| `./local-macos/scripts/verify.sh`                | Ports, Grok/Codex/Claude routing, dashboard inject                                                      |
| `./local-macos/scripts/uninstall.sh`             | Restore previous LaunchAgents + client configs                                                          |

```bash
source ~/.headroom/overlay/aliases.zsh   # optional: alias headroom-stop
```

`headroom overlay stop` / `headroom-stop` first lists named inventory clients. If any are running it **notifies and exits** (does not kill Headroom). If none are running it SIGTERM/SIGKILL only the overlay jobs on 8787/8788/8789 plus leftover overlay `mcp serve` / `proxy` processes owned by this user. LaunchAgents stay registered so lifecycle can start them again when a listed client appears.

Dashboards are **per proxy** (separate processes and savings files):

| URL                             | Traffic                    |
| ------------------------------- | -------------------------- |
| http://127.0.0.1:8787/dashboard | ChatGPT.app, Codex, Claude |
| http://127.0.0.1:8789/dashboard | Grok 4.6                   |

The overlay panel (idle grace + Stop) is injected on both — no upstream HTML edits. Default idle grace is **90 seconds**. Change it there, or with `headroom overlay grace <seconds>`. Grok request rows and prefix-cache reads are on **8789**, not 8787.

Savings/CCR/memory under `~/.headroom/` are never deleted. Config backups: `~/.headroom/overlay-backup/`.

After install or update: **fully quit ChatGPT.app** (tray too) so it reloads `~/.codex/config.toml`.

## How to update

Quit Grok / ChatGPT / Claude / Codex first. The new library is only loaded after the proxies restart. `update.sh` refuses to run while those clients are up unless you pass `--force`.

```bash
cd ~/Projects/headroom-ai
git checkout macos-overlay
./local-macos/scripts/update.sh
```

Do not run `headroom update` and do not `pip install -U headroom-ai`. This is a git checkout plus an editable venv at `~/.headroom/venv` (Python 3.13). `headroom update` detects that and refuses.

`update.sh` then:

1. Merges `origin/main` into `macos-overlay` (does **not** reverse the grok bandage first — that dirties `headroom/` and breaks the merge)
2. Re-applies `patches/grok-bandage.patch` if it is not already on the tree (pass `--drop-bandage` when calling `update.sh` to skip)
3. `uv pip install -e ".[proxy,code,relevance,mcp,reports]"` into `~/.headroom/venv`
4. Installs our `overlay` package
5. Rewrites LaunchAgents
   1. Retargets Grok / Codex / Claude by replacing relevant URLs for deduplication
6. Reloads completely waits for `/readyz`
   1. `lifecycle`
   2. the 3 processes - `8787` / `8788` / `8789`
7. Runs `verify.sh` on the discovered processes

```bash
./local-macos/scripts/update.sh --force          # restart proxies even if a listed client is running
./local-macos/scripts/update.sh --drop-bandage   # after upstream ships grok-4.6 model-list support
```

Binary: `~/.headroom/venv/bin/headroom`, also `~/.local/bin/headroom`. Overlay helpers use that venv, not Homebrew `python3` (3.14) and not `/usr/bin/python3` (3.9).

## When to throw the bandage away

Drop `patches/grok-bandage.patch` when origin/main already aliases xAI `context_length` → `context_window` (or wrap routes grok-4.6 with session auth). Keep this overlay until official wrap/install does **grok-4.6** (not only `[model.grok-build]`) and ChatGPT desktop websockets.

Then either keep the lifecycle overlay as-is, or `./local-macos/scripts/uninstall.sh` and use stock `headroom install` / `headroom wrap`.
