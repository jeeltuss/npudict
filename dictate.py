"""npudict — push-to-talk voice dictation via lemonade-server."""

import argparse
import configparser
import os
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import requests
from pynput import keyboard

__version__ = "0.1.0"

CONFIG_PATH = Path.home() / ".config" / "npudict" / "config.ini"

DEFAULTS = {
    "endpoint": "http://localhost:8000",
    "model": "whisper-v3-turbo-FLM",
    "language": "auto",
    "key": "f12",
    "auto_type": "true",
    "notifications": "true",
}


def load_config() -> dict:
    config = configparser.ConfigParser()
    if CONFIG_PATH.exists():
        config.read(CONFIG_PATH)
    return {
        "endpoint": config.get("whisper", "endpoint", fallback=DEFAULTS["endpoint"]),
        "model": config.get("whisper", "model", fallback=DEFAULTS["model"]),
        "language": config.get("whisper", "language", fallback=DEFAULTS["language"]),
        "key": config.get("hotkey", "key", fallback=DEFAULTS["key"]),
        "auto_type": config.getboolean("behavior", "auto_type", fallback=True),
        "notifications": config.getboolean("behavior", "notifications", fallback=True),
    }


def get_hotkey(key_name: str) -> keyboard.Key | keyboard.KeyCode:
    key_name = key_name.lower()
    if hasattr(keyboard.Key, key_name):
        return getattr(keyboard.Key, key_name)
    if len(key_name) == 1:
        return keyboard.KeyCode.from_char(key_name)
    print(f"Unknown key: {key_name}, defaulting to f12")
    return keyboard.Key.f12


def _copy_to_clipboard(text: str) -> None:
    if subprocess.run(["which", "wl-copy"], capture_output=True).returncode == 0:
        subprocess.Popen(["wl-copy"], stdin=subprocess.PIPE).communicate(input=text.encode())
    else:
        subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE).communicate(input=text.encode())


def check_dependencies(auto_type: bool) -> None:
    missing: list[tuple[str, str]] = []
    if subprocess.run(["which", "arecord"], capture_output=True).returncode != 0:
        missing.append(("arecord", "alsa-utils"))
    is_wayland = os.environ.get("XDG_SESSION_TYPE") == "wayland"
    has_wl_copy = subprocess.run(["which", "wl-copy"], capture_output=True).returncode == 0
    has_xclip = subprocess.run(["which", "xclip"], capture_output=True).returncode == 0
    if is_wayland and not has_wl_copy:
        missing.append(("wl-copy", "wl-clipboard"))
    elif not is_wayland and not has_xclip:
        missing.append(("xclip", "xclip"))
    if auto_type:
        has_ydotool = subprocess.run(["which", "ydotool"], capture_output=True).returncode == 0
        has_xdotool = subprocess.run(["which", "xdotool"], capture_output=True).returncode == 0
        if not has_ydotool and not has_xdotool:
            missing.append(("ydotool or xdotool", "ydotool"))
    if missing:
        print("Missing dependencies:")
        for cmd, pkg in missing:
            print(f"  {cmd} — install: sudo pacman -S {pkg}")
        sys.exit(1)


class Dictation:
    def __init__(self, endpoint: str, model_name: str, language: str, auto_type: bool, notifications: bool) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model_name = model_name
        self.language = language
        self.auto_type = auto_type
        self.notifications = notifications
        self.recording = False
        self.record_process: subprocess.Popen | None = None
        self.temp_file: str | None = None

    def notify(self, title: str, message: str = "", icon: str = "dialog-information", timeout: int = 2000) -> None:
        if not self.notifications:
            return
        subprocess.run(
            ["notify-send", "-a", "npudict", "-i", icon, "-t", str(timeout),
             "-h", "string:x-canonical-private-synchronous:npudict", title, message],
            capture_output=True,
        )

    def start_recording(self) -> None:
        if self.recording:
            return
        self.recording = True

        fd, self.temp_file = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

        self.record_process = subprocess.Popen(
            ["arecord", "-f", "S16_LE", "-r", "16000", "-c", "1", "-t", "wav", self.temp_file],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("Recording...")
        self.notify("Recording...", "Release key when done", "audio-input-microphone", 30000)

    def stop_recording(self) -> None:
        if not self.recording:
            return
        self.recording = False

        if self.record_process:
            self.record_process.terminate()
            self.record_process.wait()
            self.record_process = None

        print("Transcribing...")
        self.notify("Transcribing...", "Processing your speech", "emblem-synchronizing", 30000)

        try:
            text = self._transcribe(self.temp_file)
        except requests.ConnectionError:
            print(f"Error: cannot reach lemonade-server at {self.endpoint}", file=sys.stderr)
            self.notify("Error", f"Server not reachable at {self.endpoint}", "dialog-error", 3000)
            return
        except requests.HTTPError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            self.notify("Error", str(exc)[:50], "dialog-error", 3000)
            return
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            self.notify("Error", str(exc)[:50], "dialog-error", 3000)
            return
        finally:
            if self.temp_file and os.path.exists(self.temp_file):
                os.unlink(self.temp_file)

        if not text:
            print("No speech detected")
            self.notify("No speech detected", "Try speaking louder", "dialog-warning", 2000)
            return

        _copy_to_clipboard(text)

        if self.auto_type:
            if subprocess.run(["which", "ydotool"], capture_output=True).returncode == 0:
                subprocess.run(["ydotool", "type", "--", text])
            else:
                subprocess.run(["xdotool", "type", "--clearmodifiers", "--delay", "30", text])

        print(f"Copied: {text}")
        self.notify("Copied!", text[:100] + ("..." if len(text) > 100 else ""), "emblem-ok-symbolic", 3000)

    def _transcribe(self, audio_path: str) -> str:
        url = f"{self.endpoint}/api/v1/audio/transcriptions"
        data: dict[str, str] = {"model": self.model_name}
        if self.language != "auto":
            data["language"] = self.language
        with open(audio_path, "rb") as f:
            resp = requests.post(url, files={"file": f}, data=data, timeout=60)
        resp.raise_for_status()
        return resp.json()["text"].strip()

    def on_press(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if key == self.hotkey:
            self.start_recording()

    def on_release(self, key: keyboard.Key | keyboard.KeyCode | None) -> None:
        if key == self.hotkey:
            threading.Thread(target=self.stop_recording, daemon=True).start()

    def run(self, hotkey: keyboard.Key | keyboard.KeyCode) -> None:
        self.hotkey = hotkey
        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            listener.join()

    def stop(self) -> None:
        print("\nExiting...")
        os._exit(0)


def bootstrap_config() -> None:
    if CONFIG_PATH.exists():
        return
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    example = Path(__file__).parent / "config.example.ini"
    if example.exists():
        import shutil
        shutil.copy(example, CONFIG_PATH)
        print(f"Config created at {CONFIG_PATH}")
    else:
        CONFIG_PATH.write_text(
            "[whisper]\nendpoint = http://localhost:8000\nmodel = whisper-v3-turbo-FLM\n\n"
            "[hotkey]\nkey = f12\n\n[behavior]\nauto_type = true\nnotifications = true\n"
        )
        print(f"Config created at {CONFIG_PATH} (defaults)")


def main() -> None:
    parser = argparse.ArgumentParser(description="npudict — push-to-talk voice dictation")
    parser.add_argument("-v", "--version", action="version", version=f"npudict {__version__}")
    parser.parse_args()

    bootstrap_config()
    cfg = load_config()

    print(f"npudict v{__version__}")
    print(f"Config: {CONFIG_PATH}")
    print(f"Endpoint: {cfg['endpoint']}, Model: {cfg['model']}")

    check_dependencies(cfg["auto_type"])

    hotkey = get_hotkey(cfg["key"])
    hotkey_name = hotkey.name if hasattr(hotkey, "name") else hotkey.char

    dictation = Dictation(cfg["endpoint"], cfg["model"], cfg["language"], cfg["auto_type"], cfg["notifications"])

    signal.signal(signal.SIGINT, lambda s, f: dictation.stop())

    print(f"Hold [{hotkey_name}] to record, release to transcribe. Ctrl+C to quit.")
    dictation.run(hotkey)


if __name__ == "__main__":
    main()
