import json
import os
import time

from .settings import CONFIG_DIR, ensure_dirs


DEFAULT_PATTERN = [{"on": 0.1, "off": 0.9}]
PATTERN_FILE = CONFIG_DIR / "vibration_pattern.json"


def validate_pattern(pattern):
    if not isinstance(pattern, list) or not pattern:
        raise ValueError("The vibration pattern must contain at least one pulse.")
    if len(pattern) > 120:
        raise ValueError("A vibration pattern can contain at most 120 pulses.")

    validated = []
    for pulse in pattern:
        if not isinstance(pulse, dict):
            raise ValueError("Each vibration pulse must have on and off durations.")
        on = float(pulse.get("on", 0))
        off = float(pulse.get("off", 0))
        if not 0.05 <= on <= 10 or not 0 <= off <= 60:
            raise ValueError("Pulse durations must be 0.05-10 seconds on and 0-60 seconds off.")
        validated.append({"on": round(on, 3), "off": round(off, 3)})
    return validated


def load_pattern():
    if not PATTERN_FILE.exists():
        return [pulse.copy() for pulse in DEFAULT_PATTERN]
    with open(PATTERN_FILE, "r", encoding="utf-8") as pattern_file:
        return validate_pattern(json.load(pattern_file))


def save_pattern(pattern):
    validated = validate_pattern(pattern)
    ensure_dirs()
    with open(PATTERN_FILE, "w", encoding="utf-8") as pattern_file:
        json.dump(validated, pattern_file, separators=(",", ":"))


class MousePatternRecorder:
    """Record global left-button hold and release durations on Windows."""

    def __init__(self):
        if os.name != "nt":
            raise OSError("Global mouse-button recording is only supported on Windows.")
        import ctypes

        self._get_async_key_state = ctypes.windll.user32.GetAsyncKeyState
        self._was_down = False
        self._pressed_at = None
        self._last_release_at = None
        self._pulses = []

    def poll(self):
        now = time.monotonic()
        is_down = bool(self._get_async_key_state(0x01) & 0x8000)
        if is_down and not self._was_down:
            self._pressed_at = now
        elif self._was_down and not is_down and self._pressed_at is not None:
            self._pulses.append({
                "start": self._pressed_at,
                "end": now,
            })
            self._last_release_at = now
            self._pressed_at = None
        self._was_down = is_down

    def finish(self):
        now = time.monotonic()
        if self._pressed_at is not None:
            self._pulses.append({"start": self._pressed_at, "end": now})
            self._pressed_at = None
        if not self._pulses:
            raise ValueError("No left mouse-button presses were recorded.")

        pattern = []
        for index, pulse in enumerate(self._pulses):
            next_start = (
                self._pulses[index + 1]["start"]
                if index + 1 < len(self._pulses)
                else pulse["end"] + 1.0
            )
            pattern.append({
                "on": max(0.05, pulse["end"] - pulse["start"]),
                "off": max(0.0, next_start - pulse["end"]),
            })
        return validate_pattern(pattern)


class GamepadVibration:
    """Play a looping pattern on an SDL-recognized rumble-capable gamepad."""

    def __init__(self, root, pattern, on_status=None):
        self.root = root
        self.pattern = validate_pattern(pattern)
        self.on_status = on_status
        self._controller = None
        self._after_id = None
        self._stopped = False
        self._index = 0

    @staticmethod
    def _open_controller():
        try:
            from pygame._sdl2 import controller
        except ImportError:
            return None, "Gamepad vibration is unavailable in this pygame build."

        try:
            controller.init()
            device_count = controller.get_count()
        except RuntimeError as error:
            return None, f"Could not initialize gamepad support: {error}"
        for index in range(device_count):
            try:
                if not controller.is_controller(index):
                    continue
                device = controller.Controller(index)
                if device.rumble(0.0, 0.0, 1):
                    return device, ""
                device.quit()
            except (AttributeError, RuntimeError, OSError):
                continue
        return None, "No connected gamepad with vibration support was found."

    def start(self):
        self._controller, error = self._open_controller()
        if self._controller is None:
            self._report(error)
            return False
        self._stopped = False
        self._play_pulse()
        return True

    def _play_pulse(self):
        if self._stopped or self._controller is None:
            return
        pulse = self.pattern[self._index]
        duration_ms = max(1, round(pulse["on"] * 1000))
        try:
            rumble_started = self._controller.rumble(1.0, 1.0, duration_ms)
        except (RuntimeError, OSError) as error:
            self._report(f"Gamepad vibration failed: {error}")
            self.stop()
            return
        if not rumble_started:
            self._report("The connected gamepad rejected the vibration request.")
            self.stop()
            return
        self._report(f"Gamepad vibration: {pulse['on']:.2f}s pulse")
        self._after_id = self.root.after(duration_ms, self._finish_pulse)

    def _finish_pulse(self):
        self._after_id = None
        if self._stopped or self._controller is None:
            return
        try:
            self._controller.stop_rumble()
        except (RuntimeError, OSError) as error:
            self._report(f"Gamepad vibration stopped: {error}")
            self.stop()
            return
        pause_ms = round(self.pattern[self._index]["off"] * 1000)
        self._index = (self._index + 1) % len(self.pattern)
        if pause_ms:
            self._after_id = self.root.after(pause_ms, self._play_pulse)
        else:
            self._play_pulse()

    def _report(self, message):
        if self.on_status:
            self.on_status(message)

    def stop(self):
        self._stopped = True
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        if self._controller is not None:
            try:
                self._controller.stop_rumble()
            except (RuntimeError, OSError) as error:
                self._report(f"Could not stop gamepad vibration cleanly: {error}")
            try:
                self._controller.quit()
            except (RuntimeError, OSError) as error:
                self._report(f"Could not close the gamepad cleanly: {error}")
            self._controller = None
