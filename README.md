# npudict

Push-to-talk voice dictation for Linux, powered by [lemonade-server](https://github.com/lemonade-sdk/lemonade) and Whisper on NPU.

Hold a key → speak → release. The transcribed text is typed into the focused window and copied to clipboard.

Inspired by [soupawhisper](https://github.com/ksred/soupawhisper). npudict adapts the same idea for Linux: instead of running whisper.cpp locally, it sends audio to a local HTTP server (lemonade-server) that uses AMD NPU acceleration for fast transcription.

---

## Requirements

- Linux with X11
- Python 3.10+
- [uv](https://github.com/astral-sh/uv)
- [lemonade-server](https://github.com/lemonade-sdk/lemonade) running locally
- System packages: `alsa-utils`, `wl-clipboard` (Wayland) or `xclip` (X11), `xdotool`, `libnotify`

---

## Install

```bash
git clone <repo>
cd npudict
bash install.sh
```

`install.sh` will:
1. Install system dependencies (supports apt, dnf, pacman, zypper)
2. Install Python dependencies via `uv sync`
3. Copy `config.example.ini` to `~/.config/npudict/config.ini`
4. Optionally install a systemd user service

**Manual install:**
```bash
uv sync
uv run npudict
```

---

## Configuration

Config file: `~/.config/npudict/config.ini`  
Created automatically on first run if it doesn't exist.

```ini
[whisper]
# lemonade-server base URL
endpoint = http://localhost:8000
# Whisper model served by lemonade-server
model = whisper-v3-turbo-FLM
# ISO-639-1 language code, or "auto"
language = it

[hotkey]
# Key to hold for recording (f12, ctrl_r, etc.)
key = ctrl_r

[behavior]
# Type transcribed text into the focused window
auto_type = true
# Show desktop notifications
notifications = false
```

---

## Usage

```bash
uv run npudict
```

Hold the configured key to record, release to transcribe. Ctrl+C to quit.

---

## Systemd service

If you chose to install the service during setup:

```bash
systemctl --user start npudict    # start
systemctl --user stop npudict     # stop
systemctl --user status npudict   # status
journalctl --user -u npudict -f   # logs
```

To reinstall the service (e.g. after moving the directory):
```bash
bash install.sh
```
