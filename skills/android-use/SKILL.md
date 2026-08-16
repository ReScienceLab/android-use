---
name: android-use
description: Control an Android phone or emulator connected to this computer via adb (USB or wireless). Use this skill whenever the user wants to operate, automate, test, or inspect an Android device — opening apps, tapping buttons, filling in text (including Chinese/emoji), scrolling, taking screenshots, reading what is on the phone screen, sending messages in mobile apps, or any other on-device GUI task. Triggers include "control my phone", "on my Android", "open <app> on the phone", "send a WeChat message", "test this app on the device", "screenshot my phone", or any task requiring programmatic interaction with a connected Android device.
metadata:
  version: "0.1.0"
---

# android-use

A single CLI wraps everything: `python3 <this-skill-dir>/scripts/cli.py <command>`.
Each Bash call runs in a fresh shell, so aliases/exported variables do NOT persist between
calls (and `$AU`-style unquoted expansion breaks under zsh anyway) — write the full
`python3 …/cli.py` command every time. Abbreviated to `cli.py <command>` below.

## Quick start

```bash
cli.py devices             # confirm a device shows state "device" (not "unauthorized")
cli.py snapshot            # semantic UI tree with [ref=N] and element centers
cli.py tap 12              # tap element ref 12 (from the latest snapshot)
cli.py type "text" --clear  # clear field, type text (CJK/emoji handled automatically)
cli.py snapshot            # re-observe to verify the action worked
```

If `devices` shows nothing or `unauthorized`, read `references/setup.md` and walk the user through enabling USB debugging — then return to the task.

## Commands

| Command | Effect |
|---|---|
| `devices` | list connected devices; pass `-d <serial>` to every call when several are attached |
| `snapshot` | dump the current screen's UI tree: one line per interactive/labeled element with `[ref]`, class, text, flags (`click/long/scroll/check/edit/focused/disabled`), resource-id, center coords; header shows app, screen size, foreground activity. `--settle` re-dumps until the tree is stable — use it right after navigation or on loading/animated screens |
| `tap <ref>` / `tap <x> <y>` | tap an element or a raw coordinate; `--long` for long-press |
| `scroll up\|down\|left\|right` | `down` reveals content further down the page |
| `swipe x1 y1 x2 y2 [--ms N]` | raw gesture (drag, custom swipes) |
| `type "text"` | type into the focused field; `--clear` empties it first (needs Android 12+); non-ASCII goes through the bundled yadb automatically |
| `key back\|home\|enter\|recents\|...` | keyevent by name or raw keycode |
| `screenshot [out.png]` | save a PNG and print its path — Read the file to see the screen |
| `app <package>` | launch an app and verify it reached the foreground (`--stop` to cold-restart); `app --list wechat` to find package names (launchable apps only) |
| `mirror [--off]` | optional: open a live scrcpy window on the computer mirroring the phone, with the system touch indicator enabled so the user can watch every tap/swipe in real time; needs scrcpy installed (macOS: `brew install scrcpy`); `--off` closes it and hides the indicator. Offer this when the user wants to observe the automation |

## Workflow

1. **Semantic first.** `snapshot` → find the target by text/id → `tap <ref>`. This is faster and cheaper than vision; prefer it for all normal app UIs.
2. **Observe after every action.** Refs go stale the moment the UI changes — never reuse refs across actions; re-run `snapshot` and check the result before the next step. Right after navigation or on loading/animated screens, use `snapshot --settle`: an early dump can return a plausible-but-wrong bare tree (a skeleton screen and an error page can look identical).
3. **Visual fallback.** If the snapshot is empty or unhelpful (WebView, Flutter, games, maps, canvas UIs), use `screenshot`, Read the image, and act with `tap <x> <y>` at coordinates you judge from the image. This applies inside "native" apps too: e.g. shopping-app result pages may expose only bare clickable FrameLayouts or a WebView shell with no text — the screenshot is the reliable reader there. The snapshot header prints the true `screen=WxH` — coordinates are in that space.
4. **Verify text input.** After `type`, snapshot and confirm the text landed in the right field (the focused field carries the `focused` flag). If a stray IME autocomplete bar interfered, fix it before moving on.
5. **Evidence for reports.** When the task ends in a research report or write-up, save a screenshot of every meaningful state to a distinct descriptive path in a working directory (`step-01-search.png`, `step-02-results.png`, …) — the no-argument default path overwrites on every call. Compose the report yourself afterwards (HTML/Markdown with the screenshots embedded); the skill deliberately has no report generator.

## In-app errors vs automation errors

If the app repeatedly shows its own error page ("system error" / "network error" /
"try again later") after actions that look correct:

- **Screenshot first** — a server-side rejection is indistinguishable from a mis-tap in the tree.
- **Suspect device-wide network state.** A VPN/proxy app on the phone affects every app, and
  shopping/payment apps often risk-control proxy or overseas exit IPs into generic errors.
  Ask the user before touching their VPN app — changing it alters the whole phone's connectivity.
- Don't burn retries on the identical action; vary the query or route once to tell a global
  failure from a specific one, then stop and report.

## Hand back to the user

Stop and ask the user to act on the phone themselves — never try to work around these:

- Lock screen, PIN/biometric prompts, payment confirmations.
- Permission dialogs granting sensitive access, unless tapping "allow" is clearly part of the requested task.
- Black screenshots / empty snapshots on banking-style apps (`FLAG_SECURE`) — the platform blocks capture; tell the user which steps they must do by hand.

## Known limits

- One foreground screen at a time — there is no isolated "task space" like a browser; you are driving the user's real phone. Leave it in a sensible state (e.g., `key home`) when done.
- `snapshot` reflects the moment of the dump; system animations can shift coordinates for ~0.5s after transitions.
- Device rotation changes the coordinate space — the snapshot header's `screen=WxH` is always current, so re-snapshot after rotating.
