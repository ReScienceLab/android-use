# Technology-Selection Review of PLAN.md

Independent adversarial review of the plan's technical selections against the Aug-2026
Android agent-tooling ecosystem. Verdict: all seven selections endorsed (four with
caveats); no choice overturned. Corrections that matter are listed at the end.

## 1. Perception: raw `uiautomator dump` — endorse-with-caveat

The choice matches the most-adopted tool in the space: mobile-mcp (mobile-next, ~5.9k
stars) runs `adb exec-out uiautomator dump /dev/tty` and parses the XML —
accessibility-snapshot-first, screenshot fallback. Zero-install is a genuine
differentiator: every richer alternative requires putting software on the user's phone
(uiautomator2's instrumentation server, DroidRun Portal's AccessibilityService APK,
Maestro's instrumentation APK), which Android 15's "restricted settings" actively fights.
atx-agent specifically is dead (archived May 2024); uiautomator2 v3 replaced it.

Strongest argument against: state-of-the-art agents have abandoned raw dump. DroidRun
Portal (91.4% on AndroidWorld, Oct 2025) reads the live accessibility node cache — no idle
wait, event streaming. Raw dump's structural failure modes hit our own target apps:

- **Idle-wait failure**: dump waits for the accessibility event stream to go idle; any
  animating screen (video feeds, spinners) yields `ERROR: could not get idle state`
  (mobile-next/mobilewright #117, May 2026). Xiaohongshu/Douyin feeds are the worst case.
  Known fix: `uiautomator dump --compressed` bypasses the idle requirement (lossier tree)
  — currently absent from the plan and cli.py's retry.
- **Real latency is 1–3s** (mobile-next measured ~3s typical), not ~1s.
- **Compose**: class is always `android.view.View`, `resource-id` empty unless the app
  opts in (`testTagsAsResourceId`) — `tap --id` will be useless on Compose; `tap --text`
  is the one that matters.
- **Flutter**: semantics tree only when the engine believes accessibility is active;
  flaky (flutter #74197). **WebView**: virtual nodes only if accessibility was live when
  the page rendered.
- **Mutual exclusion**: one UiAutomation connection at a time — dump fails while
  Appium/uiautomator2/Maestro runs (openatx/uiautomator2 #298).
- **Android 14 `accessibilityDataSensitive`**: apps can hide subtrees from
  non-a11y-tool automation — dumps silently lose nodes on banking-style apps.

Evidence to settle it: 10 dumps each across WeChat chat, Xiaohongshu feed, Taobao, one
Flutter app; count idle failures and empty trees with and without `--compressed`. Below a
few percent → the choice stands.

## 2. Action: `adb shell input` — endorse

Per-invocation cost is real (~100–300ms; Android ≤11 spawns a Java VM per call, 12+
routes through faster native `cmd input`). scrcpy's control channel (persistent server,
single-digit ms/event) and uiautomator2's HTTP server are the fast alternatives. But the
host is an LLM loop: each action is followed by seconds of inference and a 1–3s dump —
200ms of tap latency is noise. mobile-mcp ships plain `adb shell input` anyway. Real
functional gap: `input swipe` cannot control slow-drag vs fling; Android 11+
`cmd input motionevent DOWN/MOVE/UP` exists if that bites. Revisit trigger: adb time
exceeding ~20% of wall clock on a profiled 10-step task (fix would be an on-device
server, per §4 — not a faster host CLI).

## 3. CJK input: vendored yadb — endorse-with-caveat

Mechanism is right: YADB `-keyboard` is clipboard-set (direct `IClipboard` binder as
shell uid) + injected Ctrl-V — the same clipboard+paste approach scrcpy and uiautomator2
v3 converged on. ADBKeyboard (GPL-2.0) is strictly worse here: APK install, IME switch,
and broken on Android 16 for ~9 months. But the plan understates maintenance facts:

- **YADB is actively maintained** (ysbing/YADB, last push July 2026, tagged releases with
  sha256'd assets since Jan 2026). Don't extract VERSION_NAME from the dex — pin an
  upstream release by tag + checksum.
- **Pin v1.1.1 or later.** v1.1.0 (Mar 2026) switched to a UiAutomation input path that
  hangs `app_process` (issue #59, filed by Midscene.js's maintainer); reverted in v1.1.1.
  The vendored 13KB dex plausibly predates the fix (v1.1.2 asset is 14,299 bytes).
  Re-vendor from a tagged release.
- **License**: YADB is **LGPL-3.0**, not permissive. Aggregation in an Apache-2.0 repo is
  fine, but NOTICE must state LGPL-3.0 and link source.
- **Behavior for SKILL.md**: `-keyboard` silently no-ops without a focused editable field
  (tap the field first), and it clobbers the user's clipboard without restoring it —
  document, or restore via yadb's own `-readClipboard`/`-writeClipboard`.
- Cheap insurance: `chmod 444` after push (Android 14+ writable-dex enforcement).
- Boundary correction: `input keycombination` exists **since Android 12**, not 11 — the
  `--clear` fallback boundary in cli.py's comment and the plan is off by one.

## 4. Stateless CLI, no daemon — endorse-with-caveat

Conclusion right, argument wrong. The plan says the ~1s dump cost is one "no daemon can
avoid" — false: avoiding exactly that is why uiautomator2's on-device server returns
sub-second dumps and DroidRun Portal streams events with no idle wait. What the plan
correctly rejects is a **host-side** daemon (buys only the ~100–200ms adb round trip,
costs lifecycle/version-skew). Fix the reasoning and name the true upgrade path: an
**on-device persistent server** (which also inherits §1's mutual-exclusion tradeoff).
Trigger: v0.2 milestone timing shows observation overhead dominating LLM time, or idle
failures exceed the vision fallback's tolerance.

## 5. Python stdlib-only, invoked by path — endorse

`xml.etree` handles fixed-schema dumps trivially; zero deps means no venv/PEP-668/uv
friction; Node would add a runtime requirement for nothing (ego uses Node because it's
compiled into the browser — no analogous constraint). Anthropic's own "code execution
with MCP" guidance (Nov 2025) endorses the thin-CLI-over-Bash shape. Unstated cost to
write down: Windows is silently out of scope (POSIX install.sh, `python3` on PATH).

## 6. Skill + CLI vs MCP server — endorse

The 2026 landscape clearly favors this: Agent Skills became an open standard (Dec 2025)
adopted by Codex CLI, Cursor, Windsurf, Gemini CLI, Goose, VS Code/Copilot within months;
a skill costs ~100 tokens until invoked vs MCP schemas resident in context. The incumbent
distribution is MCP (mobile-mcp ~5.9k stars; Maestro official MCP, Feb 2026), so the
counterargument is discovery — but the CLI-first design makes an MCP wrapper ~a day of
work when a bash-less host materializes. Confirmed: no well-adopted android-use skill
exists yet (closest: iurysza/android-use, 17 stars) — the niche is validated and
unoccupied.

## 7. Distribution: git clone + symlink install.sh — endorse-with-caveat

Matches how skills are actually installed on real machines, and the layout is already
plugin-shaped. Caveat: deferring `.claude-plugin/plugin.json` to v1.0 defers a ~10-line
file that unlocks `/plugin install` and marketplace discovery — in a race where droidrun
(9.1k stars, funded) ships the same skill shape, discovery is the scarce resource. Pull
plugin.json forward to v0.1–0.2. Keep `curl | sh` out entirely: piping shell into a tool
that controls your phone is a bad look; clone+install.sh is strictly more auditable.

## What the plan missed

1. **Idle-state failure + `--compressed` fallback** — the biggest technical omission;
   belongs in the defect list and cli.py's retry. Bonus: `exec-out uiautomator dump
   /dev/tty` also deletes the sdcard temp file and saves a round trip.
2. **yadb pinning + LGPL** (§3): pin ≥v1.1.1 by checksum; LGPL-3.0 in NOTICE;
   focused-field + clipboard-clobber docs.
3. **`keycombination` is Android 12+**, not 11+.
4. **Competitive fact**: droidrun/mobile-harness (funded, 9.1k-star org) already ships
   SKILL.md-based Android control for Claude Code — validates every bet, compresses the
   v0.1 window.
5. **Deliberate non-use of yadb `-screenshot`**: it can bypass app capture restrictions,
   which would violate the skill's own FLAG_SECURE hand-back policy — record it so a
   future contributor doesn't "helpfully" wire it up.
6. **Android 14 `accessibilityDataSensitive`** belongs in SKILL.md's hand-back section
   alongside FLAG_SECURE.
7. Wireless pairing's pairing-port ≠ connect-port trap → `references/setup.md`; the v0.2
   `connect` subcommand should print both prompts distinctly.

## Summary

| # | Selection | Verdict |
|---|---|---|
| 1 | Raw `uiautomator dump` perception | Endorse-with-caveat |
| 2 | `adb shell input` actions | Endorse |
| 3 | Vendored yadb for CJK | Endorse-with-caveat |
| 4 | Stateless CLI, no daemon | Endorse-with-caveat (fix the reasoning) |
| 5 | Python stdlib-only by path | Endorse |
| 6 | Skill + CLI over MCP | Endorse |
| 7 | git clone + symlink install | Endorse-with-caveat (plugin.json forward) |

## Top 3 risks, ranked

1. **Dump reliability on the target app class** — idle failures on animating feeds,
   id-less Compose trees, empty WebViews are where "semantic-first" degrades to
   vision-every-step. Benchmark before polish; the whole product stands on this bet.
2. **The vendored yadb blob as shipped** — unpinned, plausibly pre-v1.1.1, LGPL inside an
   Apache repo, silently clobbers the clipboard. Cheapest fix; highest
   embarrassment-per-byte if shipped as-is.
3. **Cycle-time ceiling vs on-device-service competitors** — stateless dump loop caps
   observe-act at ~2–4s while DroidRun-class agents perceive sub-second. Adequate only if
   the v0.2 revisit trigger is actually measured.

Bottom line: the architecture is the one the ecosystem's most-adopted zero-install tool
uses internally, packaged in the surface the 2026 host ecosystem rewards. The corrections
that matter are all cheap: `--compressed`/`/dev/tty` dump path, yadb re-vendor + LGPL
notice, the off-by-one `--clear` boundary, plugin.json pulled forward, and an honest
rewrite of the no-daemon justification.

## Addendum: live field test (2026-08-16, Pixel 8a + Taobao)

A sub-agent ran the skill end-to-end (open Taobao, search Nikon cameras, read results).
Outcome: success — 8 happy-path CLI invocations. Predictions vs reality:

- **§1 caveats partially confirmed, partially recalibrated.** The idle-state dump error
  never reproduced, even on an animated shopping feed. What did occur: dumps taken too
  early return structurally valid but wrong bare trees (skeleton screens), so the failure
  mode is *misleading success*, not error output. Fix landed: `snapshot --settle`
  (re-dump until two consecutive trees agree) plus `--compressed` retry.
- **Risk #1 (semantic opacity) confirmed** exactly as predicted: results pages rendered
  as bare clickable FrameLayouts or an empty WebView shell; the same content rendered
  natively minutes earlier had full text. Vision fallback carried the task.
- **§3 (yadb) validated**: CJK input worked flawlessly both times through the clipboard
  path. The multi-word quoting defect is now fixed in the draft.
- **Not predicted**: zero-width characters (U+200B) interleaved in label text (breaks
  substring matching — now stripped), and a device-wide VPN turning the app's search into
  generic "system error" risk-control pages, indistinguishable from automation bugs
  without a screenshot (now documented in SKILL.md with a hands-off-the-VPN rule).
