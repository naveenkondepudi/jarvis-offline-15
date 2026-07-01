import json
import os
import queue
import re
import subprocess
import threading
import time

import keyboard
import numpy as np
import pyttsx3
import sounddevice as sd
import win32api

from faster_whisper import WhisperModel


ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(ROOT, "config.json")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_text(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[\t\n\r]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


class JarvisOffline:
    def __init__(self, config: dict):
        self.cfg = config
        self.model = WhisperModel(
            self.cfg["stt"]["model_size"],
            device="cpu",
            compute_type=self.cfg["stt"].get("compute_type", "int8"),
        )

        self.tts_engine = pyttsx3.init()
        self.tts_engine.setProperty("rate", int(self.cfg["tts"].get("rate", 175)))
        self.tts_engine.setProperty("volume", float(self.cfg["tts"].get("volume", 1.0)))

        self.listening = False
        self.audio_q: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=10)
        self.stop_event = threading.Event()

        self.speech_lock = threading.Lock()

        self.audio_samplerate = 16000
        self.channels = 1

        # Build a small router
        self.app_map = self.cfg.get("apps", {})
        self.google_base = self.cfg.get("urls", {}).get(
            "google_search_base", "https://www.google.com/search?q="
        )

        # Simple state
        self.last_transcript = ""

    def speak(self, text: str):
        text = text.strip()
        if not text:
            return
        with self.speech_lock:
            self.tts_engine.say(text)
            self.tts_engine.runAndWait()

    def _record_for_seconds(self, seconds: float = 6.0):
        # Records from default mic; push-to-talk triggers this.
        frames = []
        n_samples = int(self.audio_samplerate * seconds)
        # We block for speed and simplicity.
        audio = sd.rec(
            frames=n_samples,
            samplerate=self.audio_samplerate,
            channels=self.channels,
            dtype="float32",
        )
        sd.wait()
        audio = np.squeeze(audio)
        return audio

    def listen_once(self):
        # Push-to-talk: record fixed short window for speed.
        # You can tune seconds to be smaller for faster responsiveness.
        audio = self._record_for_seconds(seconds=5.0)

        # Normalize audio
        if np.max(np.abs(audio)) > 0:
            audio = audio / np.max(np.abs(audio))

        segments, info = self.model.transcribe(
            audio,
            language=self.cfg["stt"].get("language"),
            vad_filter=self.cfg["stt"].get("vad", True),
        )

        text = "".join([seg.text for seg in segments]).strip()
        self.last_transcript = text
        return text

    def run_command(self, transcript: str) -> str:
        t = normalize_text(transcript)
        if not t:
            return "I did not catch that."

        # Generic utility commands
        if re.search(r"\bstop listening\b|\bstop\b|\bexit\b", t):
            self.stop_event.set()
            return "Stopping."

        if re.search(r"\bwhat time\b|\btime\b", t):
            tm = time.strftime("%H:%M")
            return f"Current time is {tm}."

        if re.search(r"\bwhat date\b|\bdate\b", t):
            dt = time.strftime("%Y-%m-%d")
            return f"Today's date is {dt}."

        if "volume up" in t or re.search(r"\bvolume\b.*\bup\b", t):
            self._volume_up()
            return "Volume up."

        if "volume down" in t or re.search(r"\bvolume\b.*\bdown\b", t):
            self._volume_down()
            return "Volume down."

        if "mute" in t:
            self._mute_toggle(mute=True)
            return "Muted."

        if "unmute" in t:
            self._mute_toggle(mute=False)
            return "Unmuted."

        # Open apps
        m = re.search(r"\bopen\s+(?P<app>[a-z0-9_\-\s]+)\b", t)
        if m:
            app = m.group("app").strip()
            # map spoken app aliases to keys
            app_key = self._resolve_app_key(app)
            if app_key and app_key in self.app_map:
                self._open_app(app_key)
                return f"Opening {app_key}."
            # if not whitelisted
            return "That app is not allowed in this offline version."

        # Search on web
        m = re.search(r"\bsearch\s+(for\s+)?(?P<q>.+)", t)
        if m:
            q = m.group("q").strip()
            if q:
                url = self.google_base + self._url_encode(q)
                self._open_url(url)
                return "Searching."

        return "Command not recognized. Try: open chrome, search cats, volume up, what time."

    def _resolve_app_key(self, spoken: str):
        s = normalize_text(spoken)
        alias_map = {
            "chrome": "chrome",
            "google chrome": "chrome",
            "ms edge": "edge",
            "edge": "edge",
            "notepad": "notepad",
            "calculator": "calculator",
            "calc": "calculator",
            "command prompt": "command_prompt",
            "cmd": "command_prompt",
        }
        # direct contains match
        for k, v in alias_map.items():
            if k in s:
                return v
        return None

    def _open_app(self, key: str):
        spec = self.app_map[key]
        path = spec["path"]
        args = spec.get("args", [])
        subprocess.Popen([path, *args], shell=False)

    def _open_url(self, url: str):
        # Use default browser; offline and safe.
        os.startfile(url)

    def _url_encode(self, s: str) -> str:
        # Minimal encoding without extra deps
        return s.replace(" ", "+")

    def _volume_up(self):
        self._key_send_volume("volume_up")

    def _volume_down(self):
        self._key_send_volume("volume_down")

    def _mute_toggle(self, mute: bool):
        # toggling is easiest; map to mute key.
        self._key_send_volume("volume_mute")
        # We do not query current mute state (keep fast + simple).

    def _key_send_volume(self, action: str):
        # VK_VOLUME_UP, etc.
        if action == "volume_up":
            win32api.keybd_event(0xAF, 0, 0, 0)  # VK_VOLUME_UP
        elif action == "volume_down":
            win32api.keybd_event(0xAE, 0, 0, 0)  # VK_VOLUME_DOWN
        elif action == "volume_mute":
            win32api.keybd_event(0xAD, 0, 0, 0)  # VK_VOLUME_MUTE

    def loop(self):
        print("Jarvis Offline v15 running.")
        print("Press hotkey to speak, say a command, I will respond.")
        print("Say 'stop' to exit.")

        hk = self.cfg["hotkey"]["push_to_talk_key"]
        print(f"Push-to-talk hotkey: {hk}")

        def on_hotkey():
            if self.stop_event.is_set():
                return
            if self.listening:
                return
            self.listening = True
            try:
                transcript = self.listen_once()
                print(f"You said: {transcript}")
                response = self.run_command(transcript)
                print(f"Jarvis: {response}")
                self.speak(response)
            except Exception as e:
                err = f"Error: {e}"
                print(err)
                self.speak("I encountered an error.")
            finally:
                self.listening = False

        keyboard.add_hotkey(hk, on_hotkey)

        while not self.stop_event.is_set():
            time.sleep(0.2)

        print("Exiting.")


def main():
    cfg = load_config()
    bot = JarvisOffline(cfg)
    bot.loop()


if __name__ == "__main__":
    main()

