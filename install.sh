#!/bin/sh
# Install the android-use skill by symlinking it into an agent's skills directory.
# Usage: ./install.sh [skills-dir]   (default: ~/.claude/skills for Claude Code)
set -e
SRC="$(cd "$(dirname "$0")" && pwd)/skills/android-use"
DIR="${1:-$HOME/.claude/skills}"
mkdir -p "$DIR"
ln -sfn "$SRC" "$DIR/android-use"
echo "linked $DIR/android-use -> $SRC"
echo "requires: adb on PATH (macOS: brew install android-platform-tools), python3"
echo "optional: scrcpy for the 'mirror' command (macOS: brew install scrcpy)"
