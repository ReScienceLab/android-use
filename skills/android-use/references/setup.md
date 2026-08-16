# Setup: connecting an Android device

## One-time, on the phone

1. Settings → About phone → tap **Build number** 7 times to unlock Developer options.
2. Settings → System → Developer options → enable **USB debugging**.
3. Plug the phone into the computer with a data-capable USB cable.
4. A dialog appears on the phone: **Allow USB debugging?** — tick "Always allow from this computer" and accept.

## On the computer

- macOS: `brew install android-platform-tools` (provides `adb`).
- Verify: `adb devices` must list the phone with state `device`.
  - `unauthorized` → the dialog in step 4 wasn't accepted; replug and accept.
  - empty list → try another cable/port; some cables are charge-only.

## Wireless (optional, Android 11+)

1. Phone: Developer options → **Wireless debugging** → Pair device with pairing code.
2. Computer: `adb pair <ip>:<pairing-port>` then enter the code, then `adb connect <ip>:<port>`.

## Chinese / emoji input

Handled automatically: the skill pushes the bundled `bin/yadb` helper to
`/data/local/tmp/` on first non-ASCII `type`. No IME needs to be installed.
