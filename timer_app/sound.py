import os
import threading
import time
import pygame
from pathlib import Path

#Supported SDL_mixer formats; m4a and aac are not supported by SDL_mixer.
AUDIO_EXTS = {".wav", ".ogg", ".mp3", ".flac"}


_mixer_lock = threading.Lock()
_mixer_ready = False
_next_channel = 0
_free_channels = []


def ensure_mixer() -> tuple[bool, str]:
    """Initialize the mixer once and return (success, error)."""
    global _mixer_ready
    with _mixer_lock:
        if _mixer_ready and pygame.mixer.get_init():
            return True, ""
        try:
            if pygame.mixer.get_init():
                _mixer_ready = True
                return True, ""
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            if not pygame.mixer.get_init():
                return False, "The audio device did not initialize."
            _mixer_ready = True
            return True, ""
        except Exception as e:
            _mixer_ready = False
            return False, f"Could not initialize audio: {e}"


def find_default_system_sound() -> str:
    candidates = [
        r"C:\Windows\Media\Alarm01.wav",
        r"C:\Windows\Media\Alarm02.wav",
        r"C:\Windows\Media\notify.wav",
        r"C:\Windows\Media\Windows Notify System Generic.wav",
        r"C:\Windows\Media\chimes.wav",
        r"C:\Windows\Media\ding.wav",
        r"C:\Windows\Media\Windows Ding.wav",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return ""


def get_sound_duration(path: str) -> float:
    ok, _ = ensure_mixer()
    if not ok:
        return -1
    try:
        snd = pygame.mixer.Sound(path)
        return snd.get_length()
    except Exception:
        return -1


def scan_music_files(dirs):
    result = []
    for d in dirs:
        p = Path(d)
        if not p.exists() or not p.is_dir():
            continue
        for f in p.rglob("*"):
            if f.suffix.lower() in AUDIO_EXTS:
                result.append((f"{p.name}/{f.name}", str(f)))

    from .settings import SFX_DIR
    if SFX_DIR.exists():
        for f in SFX_DIR.rglob("*"):
            if f.suffix.lower() in AUDIO_EXTS:
                result.append((f"SFX/{f.name}", str(f)))

    sys_snd = find_default_system_sound()
    if sys_snd:
        result.append((f"System: {os.path.basename(sys_snd)}", sys_snd))
    return result


class SoundPlayer:
    """A player with its own mixer channel and a UI-readable error field."""

    def __init__(self):
        self._thread = None
        self._stop_flag = threading.Event()
        self._paused_flag = threading.Event()
        self._channel = None
        self._channel_index = None
        self.last_error = ""

    def _get_channel(self):
        global _next_channel
        if self._channel is not None:
            return self._channel
        with _mixer_lock:
            if _free_channels:
                self._channel_index = _free_channels.pop()
            else:
                _next_channel = max(_next_channel, pygame.mixer.get_num_channels())
                pygame.mixer.set_num_channels(_next_channel + 1)
                self._channel_index = _next_channel
                _next_channel += 1
            self._channel = pygame.mixer.Channel(self._channel_index)
        return self._channel

    def play(self, path: str,
             auto_off_seconds: int = 30,
             fade_in: bool = False,
             fade_in_seconds: float = 5.0,
             max_volume: float = 1.0,
             loop_if_short: bool = True,
             on_finish=None) -> bool:
        """Return True if playback starts; otherwise set self.last_error."""
        self.last_error = ""

        ok, err = ensure_mixer()
        if not ok:
            self.last_error = err
            return False
        try:
            self._get_channel()
        except Exception as e:
            self.last_error = f"Could not reserve an audio channel: {e}"
            return False

        if not path or not os.path.exists(path):
            path = find_default_system_sound()
        if not path or not os.path.exists(path):
            self.last_error = "Neither the selected file nor a system sound could be found."
            return False

        ext = Path(path).suffix.lower()
        if ext not in AUDIO_EXTS:
            self.last_error = f"Unsupported format {ext}. Supported formats: {', '.join(sorted(AUDIO_EXTS))}."
            return False

        try:
            pygame.mixer.Sound(path)
        except Exception as e:
            self.last_error = f"Could not open the audio file: {e}"
            return False

        self.stop()
        self._stop_flag.clear()
        self._paused_flag.clear()

        self._thread = threading.Thread(
            target=self._play_worker,
            args=(path, auto_off_seconds, fade_in, float(fade_in_seconds),
                  float(max_volume), loop_if_short, on_finish),
            daemon=True,
        )
        self._thread.start()
        return True

    def _play_worker(self, path, auto_off, fade_in, fade_in_seconds,
                     max_vol, loop_if_short, on_finish):
        channel = None
        try:
            sound = pygame.mixer.Sound(path)
            channel = self._channel

            duration = sound.get_length()
            loop = bool(
                loop_if_short and
                (auto_off <= 0 or duration < auto_off)
            )

            start_t = time.time()
            fade_secs = max(0.01, fade_in_seconds)

            sound.set_volume(1.0)
            channel.set_volume(0.0 if fade_in else max_vol)
            channel.play(sound, loops=-1 if loop else 0)

            while channel.get_busy():
                if self._stop_flag.is_set():
                    channel.stop()
                    break

                if auto_off > 0 and (time.time() - start_t) >= auto_off:
                    channel.fadeout(500)
                    fade_deadline = time.monotonic() + 0.5
                    while (channel.get_busy() and
                           time.monotonic() < fade_deadline and
                           not self._stop_flag.is_set()):
                        time.sleep(0.02)
                    break

                if fade_in and max_vol > 0:
                    elapsed = time.time() - start_t
                    vol = min(max_vol, max_vol * (elapsed / fade_secs))
                    channel.set_volume(vol)

                if self._paused_flag.is_set():
                    channel.pause()
                    while self._paused_flag.is_set() and not self._stop_flag.is_set():
                        time.sleep(0.05)
                    if self._stop_flag.is_set():
                        channel.stop()
                        break
                    channel.unpause()

                time.sleep(0.05)

        except Exception as e:
            self.last_error = f"Playback error: {e}"
        finally:
            if channel is not None:
                try:
                    channel.stop()
                except Exception:
                    pass
            if on_finish:
                try:
                    on_finish()
                except Exception:
                    pass

    def pause(self):  self._paused_flag.set()
    def resume(self): self._paused_flag.clear()

    def stop(self):
        self._stop_flag.set()
        if self._channel is not None:
            self._channel.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None

    def close(self):
        self.stop()
        if self._channel_index is not None:
            with _mixer_lock:
                _free_channels.append(self._channel_index)
            self._channel = None
            self._channel_index = None

    def is_playing(self) -> bool:
        return self._thread is not None and self._thread.is_alive()