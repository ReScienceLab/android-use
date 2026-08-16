#!/usr/bin/env python3
"""android-use: minimal adb helper CLI for GUI agents.

Semantic-first: `snapshot` prints a ref-annotated UI tree from uiautomator;
`tap <ref>` taps that element's center. Visual fallback: `screenshot` + `tap x y`.
Stdlib only. State between invocations: a refmap JSON under ~/.cache/android-use.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

CACHE = Path.home() / ".cache" / "android-use"
SKILL_DIR = Path(__file__).resolve().parent.parent
YADB_LOCAL = SKILL_DIR / "bin" / "yadb"
YADB_REMOTE = "/data/local/tmp/yadb"
KEYS = {"back": 4, "home": 3, "enter": 66, "recents": 187, "delete": 67,
        "power": 26, "volume_up": 24, "volume_down": 25, "wake": 224, "tab": 61}
# zero-width chars some apps interleave in labels (U+200B between every CJK char on Taobao)
ZW = dict.fromkeys([0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF])


def adb(dev, *args, binary=False, fatal=True):
    cmd = ["adb"] + (["-s", dev] if dev else []) + list(args)
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        if not fatal:
            return None
        sys.exit(f"adb failed: {' '.join(cmd)}\n{r.stderr.decode(errors='replace').strip()}")
    return r.stdout if binary else r.stdout.decode(errors="replace")


def screen_size(dev):
    out = adb(dev, "shell", "wm", "size")
    m = re.findall(r"(\d+)x(\d+)", out)  # last match wins: Override size beats Physical
    if not m:
        sys.exit(f"cannot parse `wm size`: {out.strip()}")
    return int(m[-1][0]), int(m[-1][1])


def refmap_path(dev):
    CACHE.mkdir(parents=True, exist_ok=True)
    return CACHE / f"refs-{dev or 'default'}.json"


# ---------- snapshot ----------

def node_line(a, ref, depth):
    cls = a.get("class", "").rsplit(".", 1)[-1]
    label = (a.get("text") or a.get("content-desc") or "").translate(ZW)
    rid = a.get("resource-id", "").rsplit("/", 1)[-1]
    x1, y1, x2, y2 = map(int, re.findall(r"-?\d+", a.get("bounds", "[0,0][0,0]")))
    parts = [f"[{ref}]", cls]
    if label:
        parts.append(json.dumps(label, ensure_ascii=False))
    flags = node_flags(a)
    if flags:
        parts.append("{" + ",".join(flags) + "}")
    if rid:
        parts.append(f"id={rid}")
    cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
    parts.append(f"({cx},{cy})")
    return "  " * min(depth, 6) + " ".join(parts), (cx, cy)


def node_flags(a):
    flags = []
    if a.get("clickable") == "true":
        flags.append("click")
    if a.get("long-clickable") == "true":
        flags.append("long")
    if a.get("scrollable") == "true":
        flags.append("scroll")
    if a.get("checkable") == "true":
        flags.append("checked" if a.get("checked") == "true" else "check")
    if "EditText" in a.get("class", ""):
        flags.append("edit")
    if a.get("focused") == "true":
        flags.append("focused")
    if a.get("enabled") == "false":
        flags.append("disabled")
    return flags


def parse_tree(xml_text):
    """Returns (lines, refmap). Emits nodes that are interactive or carry text."""
    root = ET.fromstring(xml_text)
    lines, refs = [], {}
    pkg = None

    def walk(node, depth):
        nonlocal pkg
        a = node.attrib
        if pkg is None and a.get("package"):
            pkg = a["package"]
        emitted = False
        if a.get("bounds") and a.get("bounds") != "[0,0][0,0]":
            if node_flags(a) or a.get("text") or a.get("content-desc"):
                ref = len(refs) + 1
                line, center = node_line(a, ref, depth)
                lines.append(line)
                refs[str(ref)] = center
                emitted = True
        for child in node:
            walk(child, depth + 1 if emitted else depth)

    walk(root, 0)
    return lines, refs, pkg


def dump_xml(dev):
    out = adb(dev, "shell", "uiautomator", "dump", "/sdcard/au-dump.xml", fatal=False)
    if out is None or "dumped" not in out:
        # busy/animating screens can fail the idle wait; --compressed skips it (lossier tree)
        adb(dev, "shell", "uiautomator", "dump", "--compressed", "/sdcard/au-dump.xml")
    return adb(dev, "exec-out", "cat", "/sdcard/au-dump.xml")


def foreground(dev):
    out = adb(dev, "shell", "dumpsys window | grep mCurrentFocus", fatal=False) or ""
    m = re.search(r"mCurrentFocus=\S+ (?:\S+ )?([\w.]+)/([\w.$]+)", out)
    return m.groups() if m else None


def cmd_snapshot(dev, settle=False):
    lines, refs, pkg = parse_tree(dump_xml(dev))
    note = ""
    if settle:  # early dumps mid-load return plausible-but-wrong bare trees — re-dump until stable
        deadline = time.time() + 6
        stable = False
        while time.time() < deadline and not stable:
            time.sleep(0.8)
            nxt = parse_tree(dump_xml(dev))
            stable = nxt[0] == lines
            lines, refs, pkg = nxt
        note = " settle=stable" if stable else " settle=timeout"
    w, h = screen_size(dev)
    refmap_path(dev).write_text(json.dumps(refs))
    fg = foreground(dev)
    focus = f" focus={fg[1].rsplit('.', 1)[-1]}" if fg else ""
    print(f"# app={pkg} screen={w}x{h} refs={len(refs)}{focus}{note}")
    print("\n".join(lines))


# ---------- actions ----------

def resolve_target(dev, target):
    if len(target) == 2:
        return int(target[0]), int(target[1])
    p = refmap_path(dev)
    if not p.exists():
        sys.exit("no refmap — run `snapshot` first")
    refs = json.loads(p.read_text())
    if target[0] not in refs:
        sys.exit(f"unknown ref {target[0]} — re-run `snapshot` (refs go stale after UI changes)")
    return refs[target[0]]


def cmd_tap(dev, target, long_press=False):
    x, y = resolve_target(dev, target)
    if long_press:
        adb(dev, "shell", "input", "swipe", str(x), str(y), str(x), str(y), "600")
    else:
        adb(dev, "shell", "input", "tap", str(x), str(y))
    print(f"{'long-press' if long_press else 'tap'} ({x},{y})")


def cmd_scroll(dev, direction):
    w, h = screen_size(dev)
    cx, cy = w // 2, h // 2
    # "down" = reveal content further down (finger moves up)
    moves = {"down": (cx, int(h * .7), cx, int(h * .3)),
             "up": (cx, int(h * .3), cx, int(h * .7)),
             "left": (int(w * .8), cy, int(w * .2), cy),
             "right": (int(w * .2), cy, int(w * .8), cy)}
    x1, y1, x2, y2 = moves[direction]
    adb(dev, "shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), "300")
    print(f"scroll {direction}")


def cmd_swipe(dev, coords, ms):
    adb(dev, "shell", "input", "swipe", *[str(c) for c in coords], str(ms))
    print("swipe done")


def ensure_yadb(dev):
    if adb(dev, "shell", "ls", YADB_REMOTE, fatal=False) is None:
        adb(dev, "push", str(YADB_LOCAL), YADB_REMOTE)


def cmd_type(dev, text, clear):
    text = text.replace("\n", " ").replace("\t", " ")
    if clear:  # Ctrl+A then DEL; keycombination needs Android 12+
        adb(dev, "shell", "input", "keycombination", "113", "29")
        adb(dev, "shell", "input", "keyevent", "67")
    if text.isascii():
        escaped = re.sub(r"([()<>|;&*~\"'$`\\])", r"\\\1", text).replace(" ", "%s")
        adb(dev, "shell", "input", "text", escaped)
    else:  # input text can't do CJK/emoji — use yadb
        ensure_yadb(dev)
        # quote for the device-side shell, or multi-word text arrives as separate args
        payload = (text.replace("\\", "\\\\").replace("`", "\\`")
                   .replace("$", "\\$").replace('"', '\\"'))
        adb(dev, "shell", "app_process", f"-Djava.class.path={YADB_REMOTE}",
            "/data/local/tmp", "com.ysbing.yadb.Main", "-keyboard", f'"{payload}"')
    print(f"typed {len(text)} chars")


def cmd_key(dev, name):
    code = KEYS.get(name.lower(), name if name.isdigit() else None)
    if code is None:
        sys.exit(f"unknown key {name!r}; names: {', '.join(KEYS)} or a raw keycode")
    adb(dev, "shell", "input", "keyevent", str(code))
    print(f"key {name}")


def cmd_screenshot(dev, out):
    data = adb(dev, "exec-out", "screencap", "-p", binary=True)
    path = Path(out) if out else refmap_path(dev).with_name(f"screen-{dev or 'default'}.png")
    path.write_bytes(data)
    print(path.resolve())


def cmd_app(dev, package, list_filter, stop):
    if list_filter is not None:
        out = adb(dev, "shell", "cmd", "package", "query-activities", "--brief",
                  "-a", "android.intent.action.MAIN",
                  "-c", "android.intent.category.LAUNCHER", fatal=False)
        if out and "/" in out:  # launchable apps only
            pkgs = sorted({l.strip().split("/")[0] for l in out.splitlines() if "/" in l})
        else:  # pre-Android-8 fallback: every package, overlays included
            out = adb(dev, "shell", "pm", "list", "packages")
            pkgs = sorted(l.replace("package:", "").strip() for l in out.splitlines() if l.strip())
        for pkg in pkgs:
            if list_filter.lower() in pkg.lower():
                print(pkg)
        return
    if stop:
        adb(dev, "shell", "am", "force-stop", package)
    adb(dev, "shell", "monkey", "-p", package, "-c",
        "android.intent.category.LAUNCHER", "1")
    t0 = time.time()
    fg = None
    while time.time() - t0 < 3:
        fg = foreground(dev)
        if fg and fg[0] == package:
            print(f"launched {package}, foreground after {time.time() - t0:.1f}s")
            return
        time.sleep(0.5)
    print(f"launched {package}, but foreground is {fg[0] if fg else 'unknown'} — "
          "verify with snapshot or screenshot")


def cmd_mirror(dev, off):
    if off:
        adb(dev, "shell", "settings", "put", "system", "show_touches", "0")
        # ponytail: pkill hits any scrcpy on the host; pid-file it if that ever matters
        subprocess.run(["pkill", "-f", "scrcpy"], capture_output=True)
        print("mirror closed, touch indicator off")
        return
    if not shutil.which("scrcpy"):
        sys.exit("scrcpy not found — install it first (macOS: brew install scrcpy)")
    # show_touches draws the standard white dot for every tap/swipe, injected ones included
    adb(dev, "shell", "settings", "put", "system", "show_touches", "1")
    args = ["scrcpy", "--no-audio", "--window-title", "android-use mirror"]
    if dev:
        args += ["-s", dev]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    print("mirror window opening — actions now show a touch dot; `mirror --off` when done")


# ---------- selftest ----------

SAMPLE_XML = """<hierarchy rotation="0">
 <node bounds="[0,0][1080,2400]" class="android.widget.FrameLayout" package="com.example" text="" content-desc="">
  <node bounds="[100,200][300,300]" class="android.widget.Button" text="Log&#8203;in" clickable="true"/>
  <node bounds="[100,400][900,500]" class="android.widget.EditText" text="" content-desc="username"/>
  <node bounds="[0,0][0,0]" class="android.view.View" text="ghost" clickable="true"/>
 </node>
</hierarchy>"""


def cmd_selftest():
    lines, refs, pkg = parse_tree(SAMPLE_XML)
    assert pkg == "com.example", pkg
    assert len(refs) == 2, refs  # root has no text/flags; zero-bounds ghost skipped
    assert refs["1"] == (200, 250), refs
    assert 'Button "Login" {click}' in lines[0], lines[0]  # U+200B stripped from label
    assert "edit" in lines[1] and '"username"' in lines[1], lines[1]
    print("selftest ok")


def main():
    p = argparse.ArgumentParser(prog="android-use")
    p.add_argument("-d", "--device", help="adb serial (needed when several devices attached)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("devices")
    sn = sub.add_parser("snapshot")
    sn.add_argument("--settle", action="store_true",
                    help="re-dump until the tree is stable (loading/animated screens)")
    t = sub.add_parser("tap")
    t.add_argument("target", nargs="+", help="<ref> or <x> <y>")
    t.add_argument("--long", action="store_true")
    s = sub.add_parser("scroll")
    s.add_argument("direction", choices=["up", "down", "left", "right"])
    sw = sub.add_parser("swipe")
    sw.add_argument("coords", nargs=4, type=int, metavar=("X1", "Y1", "X2", "Y2"))
    sw.add_argument("--ms", type=int, default=300)
    ty = sub.add_parser("type")
    ty.add_argument("text")
    ty.add_argument("--clear", action="store_true", help="clear the field first")
    k = sub.add_parser("key")
    k.add_argument("name")
    sc = sub.add_parser("screenshot")
    sc.add_argument("out", nargs="?")
    ap = sub.add_parser("app")
    ap.add_argument("package", nargs="?")
    ap.add_argument("--list", dest="list_filter", metavar="FILTER",
                    help="list installed packages matching FILTER")
    ap.add_argument("--stop", action="store_true", help="force-stop before launching")
    mi = sub.add_parser("mirror")
    mi.add_argument("--off", action="store_true",
                    help="close the mirror window and hide the touch indicator")
    sub.add_parser("selftest")
    a = p.parse_args()

    if a.cmd == "devices":
        print(adb(None, "devices", "-l").strip())
    elif a.cmd == "snapshot":
        cmd_snapshot(a.device, a.settle)
    elif a.cmd == "tap":
        cmd_tap(a.device, a.target, a.long)
    elif a.cmd == "scroll":
        cmd_scroll(a.device, a.direction)
    elif a.cmd == "swipe":
        cmd_swipe(a.device, a.coords, a.ms)
    elif a.cmd == "type":
        cmd_type(a.device, a.text, a.clear)
    elif a.cmd == "key":
        cmd_key(a.device, a.name)
    elif a.cmd == "screenshot":
        cmd_screenshot(a.device, a.out)
    elif a.cmd == "app":
        if not a.package and a.list_filter is None:
            sys.exit("app: give a package name, or --list FILTER")
        cmd_app(a.device, a.package, a.list_filter, a.stop)
    elif a.cmd == "mirror":
        cmd_mirror(a.device, a.off)
    elif a.cmd == "selftest":
        cmd_selftest()


if __name__ == "__main__":
    main()
