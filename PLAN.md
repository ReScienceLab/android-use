# android-use — Integration Plan

Package Android-phone control (over adb) as an installable agent skill, modeled on how
**EgoBrowser (ego lite)** packages browser control for AI agents. Any skill-capable host
(Claude Code first) becomes the brain; this repo ships only the eyes and hands.

This plan synthesizes three investigations: (a) how ego lite is actually built, (b) what is
reusable in **LightGUIAgent** (our grid-overlay adb agent), and (c) an integration
architecture for this repo. A working first draft of the skill already exists at
`LightGUIAgent/skills/android-use/` (uncommitted there) and migrates here as v0.1.

---

## 1. The two systems in one paragraph each

**ego lite** is a Chromium fork. `ego-browser` on PATH is a thin native CLI that forwards a
heredoc script over Mach/Mojo IPC to a Node runtime compiled *into the browser*; helper
functions (`snapshotText`, `click`, …) are injected as `AsyncFunction` parameters around the
script. The browser process owns all state (task spaces, tabs, login sessions). The skill
directory ships read-only inside the app bundle and reaches `~/.claude/skills/ego-browser`
through a chain of symlinks (`~/.local/share/ego/active_version_dir` pins the CLI+skill to
the browser build that last completed onboarding). Errors carry stable codes
(`EGO_TASK_SPACE_USER_IN_CONTROL`, …) and docs say "branch on the code, not the wording".
A `learnings/` subsystem (per-site `manifest.json` + notes + host-side/page-side tools)
ships fully wired.

**LightGUIAgent** is a standalone autonomous agent: screenshot → chess-grid overlay (PIL) →
Claude Opus picks a cell like `"E5"` → `adb shell input tap`. It carries its own LLM loop,
prompt, cost tracking, and logging — exactly the layer a host agent replaces. Its draft
skill `skills/android-use/` (stdlib-only `cli.py`: `devices / snapshot / tap / scroll /
swipe / type / key / screenshot / app`, refmap cached per-serial, yadb pushed lazily for CJK
input) is already a superset of the old agent's action surface.

---

## 2. What we take from EgoBrowser

| ego concept | Verdict | Why |
|---|---|---|
| Semantic-first, visual-fallback doctrine (+ "write-probe then verify") | **Adopt** (already in SKILL.md) | `uiautomator dump` is our semantic tier; screenshot + `tap x y` the visual tier |
| Observe-after-every-action; refs invalidated per snapshot | **Adopt** (already in SKILL.md) | Same staleness physics as `@N` refs |
| Stable error-code contract | **Adopt (v0.2)** | `cli.py` exits with `AU_NO_DEVICE`, `AU_UNAUTHORIZED`, `AU_MULTIPLE_DEVICES`, `AU_KEYGUARD_LOCKED`, `AU_STALE_REF`, `AU_DUMP_FAILED`; SKILL.md tells the agent to branch on the code |
| Idempotent `install.sh`, verify-at-end, "return to the original task" framing | **Adopt** | Far simpler payload: no DMG/Gatekeeper — check adb → symlink → selftest → `adb devices` |
| `learnings/` per-target knowledge | **Adopt simplified (v0.3)** | `learnings/<package>/notes.md`, markdown only. No manifest/tool-injection: there is no runtime to load tools into. ego's own SKILL.md never mentions its learnings system — ship ours documented from day one |
| Control handoff / ownership | **Adapt** | A phone has one screen, so agent/user isolation is time-slicing. Prose policy (lock screen, payments, FLAG_SECURE → stop and ask) + one mechanical guard: refuse actions while the keyguard is up (v0.2) |
| Persistent runtime daemon | **Reject** | The adb server is already a daemon and the phone holds all UI state; a daemon adds lifecycle/version-skew/debugging cost and buys nothing. See §4 |
| Heredoc Node scripting surface | **Reject** | adb actions are atomic; there is no in-process object graph. A subcommand CLI is the right grain |
| Task spaces | **Reject permanently** | One physical foreground screen; isolation is impossible. Analog of `completeTaskSpace` is `key home` — a convention, not an API |
| Symlink version-pinning (`active_version_dir`), Omaha updater | **Reject** | The repo is the payload; `git pull` is the updater |
| `help()` introspection | **Reject** | 9 subcommands fit in one SKILL.md table + argparse `--help` |

## 3. What we take from LightGUIAgent

| Asset | Verdict |
|---|---|
| adb action recipes (`agent.py:163-293`) | Already ported into `cli.py`, improved (exec-out screencap, override-aware `wm size`) |
| yadb binary + push protocol | Port as-is. Also exposes unused `-layout` (accessibility UI dump — fallback when `uiautomator dump` fails) and clipboard read/write (third text-entry route) |
| Grid overlay + converter (`grid_overlay.py`, `grid_converter.py`) | Drop for v0.x. The host reads raw screenshots and emits pixels directly. If coordinate taps prove unreliable, rewrite as an optional ~60-line `grid.py` behind a Pillow import guard — do not port (import-time adb calls, hardcoded macOS font, square-resize distortion) |
| Settings auto-detect (`settings.py`) | Drop. `cli.py`'s `wm size` handling is already better (override beats physical; hard error over silent 1080×2400 fallback) |
| Stuck-detection heuristics (`claude_client.py:320-336`) | Drop the code, port the wording into SKILL.md: "same screen twice → `key back` or re-enter from home". Lift the common-package table (WeChat/Taobao/Alipay/Meituan) into `references/apps.md` |
| Logger, LLM loop, cost tracking | Drop entirely — that layer *is* the host agent |

**Relationship going forward**: two products, one substrate. LightGUIAgent stays the
autonomous-agent research artifact in its own repo. android-use is the tool surface for host
agents. The draft skill was never committed to LightGUIAgent, so migration is a clean copy
here (initial commit), delete the draft there, retarget `~/.claude/skills/android-use`.
yadb (13 KB) is vendored independently in both repos — a shared submodule is pure overhead.

## 4. Architecture decision: stateless CLI, no daemon

Every piece of state a daemon would hold already has a home:

| State | Where it lives |
|---|---|
| Device connection (USB/Wi-Fi) | adb server — already a daemon |
| UI state | the phone itself |
| Refmap from last snapshot | `~/.cache/android-use/refs-<serial>.json` |
| yadb-pushed flag | checked on-device (~50 ms) |
| Device selection | `ANDROID_SERIAL` env (adb-native) + `-d` override |
| scrcpy live view | the one true daemon candidate — deferred to a v1.0 decision point |

Per-invocation overhead is one adb round trip (~100–200 ms), dwarfed by `uiautomator dump`
(~1 s) which no daemon can avoid.

## 5. Repo layout

```
android-use/
├── README.md                     # humans: what/why, install one-liner, demo
├── PLAN.md                       # this plan
├── LICENSE                       # Apache-2.0 (see §8)
├── NOTICE                        # yadb attribution (upstream ysbing/YADB, license, version)
├── install.sh                    # idempotent: adb check → symlink skill → selftest → verify
├── skills/android-use/           # ← the distributable payload; symlink target
│   ├── SKILL.md                  # agent-facing manual
│   ├── scripts/cli.py            # the entire runtime, stdlib-only, any python3
│   ├── bin/yadb                  # vendored CJK-input dex (13 KB)
│   ├── references/setup.md       # USB/wireless onboarding + troubleshooting
│   ├── references/apps.md        # common package names (from LightGUIAgent prompt)
│   └── learnings/                # v0.3: per-app notes keyed by package name
└── tests/test_cli.py             # parse_tree/refmap unit tests, no device needed
```

Nesting under `skills/` (not SKILL.md at repo root) keeps the agent-readable payload minimal
and is exactly the layout a Claude Code plugin (`.claude-plugin/plugin.json` + `skills/`)
requires at v1.0 — no breaking `git mv` later. **No Python packaging**: `cli.py` is invoked
by path; pyproject/pip would add install steps and version skew for zero benefit.

## 6. Install & distribution

Primary (v0.1): `git clone` + `sh install.sh`, matching how every skill on this machine is
already installed (symlinks into `~/.claude/skills/`). `install.sh` is POSIX sh:

1. `command -v adb` — missing → print `brew install android-platform-tools` / apt line.
2. `ln -sfn "$repo/skills/android-use" ~/.claude/skills/android-use` (`--target <dir>` for other hosts).
3. Verify: `python3 …/cli.py selftest`; then `adb devices` — no authorized device → point at
   `references/setup.md`, exit 0 (device onboarding is the user's GUI step, like ego's).

Versioning: `metadata.version` in SKILL.md frontmatter + git tags; update = `git pull`.
MCP server: not in v1 — the CLI is the universal adapter; wrap it only if a bash-less host
actually appears.

## 7. Roadmap

**v0.1 — it exists as a repo** (days)
- Copy the draft skill here with the §9 defect fixes; initial commit; README/LICENSE/NOTICE/install.sh/tests.
- Retarget local symlink; delete the draft from LightGUIAgent.
- Milestone: fresh machine → clone → `install.sh` → Claude Code taps through a real app.

**v0.2 — round-trip and safety ergonomics**
- `tap --text "Login"` / `tap --id send_btn`: dump+match+tap in one invocation (kills the stale-ref problem for the common case).
- Global `--snapshot-after` (act → settle ~800 ms → print fresh snapshot): action + observation in one Bash call.
- Keyguard guard: any action while locked → `AU_KEYGUARD_LOCKED` hard error → hand back to user.
- Stable error codes throughout (§2); `connect` subcommand wrapping `adb pair`/`adb connect`.
- `--clear` fallback for Android ≤10 (`MOVE_END` + N×DEL); yadb `-layout` as dump fallback.
- Milestone: a 10-step task completes in ≤10 Bash invocations with no stale-ref retries.

**v0.3 — learnings**
- `learnings/<package>/notes.md` convention + SKILL.md write-back protocol (agent appends discovered navigation paths after tasks).
- Seed 2–3 apps already exercised in LightGUIAgent demos (WeChat, Xiaohongshu).

**v1.0 — distribution polish**
- `.claude-plugin/plugin.json` (plugin/marketplace install); `curl | sh` bootstrap; CI (pytest + shellcheck); tagged releases.
- Decision point, not commitment: scrcpy live-view as an optional background process — only if screenshot polling proves insufficient.

**Explicitly not building**: a daemon/session runtime; heredoc scripting; task spaces; MCP
server (until needed); scrcpy streaming in v0.x; on-device accessibility-service APK
(uiautomator is slower but zero-install); emulator lifecycle; iOS; any autonomous LLM loop
(that's LightGUIAgent's job).

## 8. Licensing & attribution

- **Apache-2.0** for this repo — matches LightGUIAgent's LICENSE file (its pyproject
  declares MIT; that conflict should be fixed there) and provides the NOTICE mechanism.
- `NOTICE` names yadb: upstream **ysbing/YADB**, its license, and the pinned version the
  vendored dex was built from (currently recorded nowhere — extract `VERSION_NAME` from the
  dex or pin the upstream release). Mention provenance in `references/setup.md`.

## 9. Known defects to fix during migration (before the copy)

1. **yadb multi-word text bug** (`cli.py` type path): payload passed unquoted — device-side
   shell re-splits, only the first word is typed. Quote it (as `agent.py:205` did) and add
   `\n`/`\t`→space preprocessing (`agent.py:196`).
2. **`ensure_yadb` staleness**: presence-only `ls` check trusts any pre-existing
   `/data/local/tmp/yadb`. Push once per process, or compare `md5sum`.
3. `--clear` silently no-ops on Android ≤10 (`input keycombination` doesn't exist) → v0.2 fallback.
4. Cosmetic: `snapshot` leaves `/sdcard/au-dump.xml` behind.

Upstream LightGUIAgent bugs found along the way (fix there, not here): `agent.py:310` looks
for yadb at the wrong path so it never installs; `agent.py:529` logs a dict where
`logger.py` expects a float.
