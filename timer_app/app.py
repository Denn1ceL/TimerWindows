import math
import time
from datetime import datetime, timedelta
import tkinter as tk
import customtkinter as ctk

from .settings import load_config
from .sound import SoundPlayer
from .notify import send_notification
from .settings_window import SettingsWindow, rgb_to_hex
from .vibration import GamepadVibration, load_pattern


def _clamp(v, lo, hi): return max(lo, min(hi, v))


class TimerApp(ctk.CTk):
    def __init__(self):
        ctk.set_default_color_theme("blue")
        super().__init__()
        self.cfg = load_config()

        self.title("Timer")
        self.geometry("500x650")
        self.resizable(False, False)

        self.player = SoundPlayer()

        self.remaining = 0
        self.total = 0
        self.running = False
        self._alarm_target = None
        self._timer_deadline = None
        self._countdown_after_id = None
        self._clock_after_id = None
        self._run_comment = ""
        self._active_vibration = None
        self._ticker_after_id = None
        self._ticker_window = None
        self._ticker_position = 0

        self._apply_appearance()
        self._build_ui()
        self._restyle()
        self._set_clock_style()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._update_clock()

    #Appearance
    def _apply_appearance(self):
        theme = self.cfg.get("theme", "dark")
        if theme not in ("dark", "light"):
            theme = "dark"
            self.cfg["theme"] = theme
        ctk.set_appearance_mode(theme)

    def _primary(self): return rgb_to_hex(self.cfg["color_primary"])
    def _accent(self):  return rgb_to_hex(self.cfg["color_accent"])
    def _success(self): return rgb_to_hex(self.cfg["color_success"])
    def _bg(self):      return rgb_to_hex(self.cfg["color_bg"])
    def _text(self):    return rgb_to_hex(self.cfg["color_text"])

    @staticmethod
    def _darken(hex_color, factor=0.8):
        hex_color = hex_color.lstrip("#")
        r, g, b = (int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        return "#{:02x}{:02x}{:02x}".format(int(r*factor), int(g*factor), int(b*factor))

    def _restyle(self):
        """Apply the configured colors to the main window widgets"""
        try:
            self.configure(fg_color=self._bg())
        except Exception:
            pass

        for w in (self.clock_label, self.timer_label, self.status_label):
            try: w.configure(text_color=self._text())
            except Exception: pass
        try:
            self.clock_label.configure(text_color=self._primary())
            self.clock_canvas.configure(bg=self._bg())
        except Exception:
            pass

        for lbl in getattr(self, "_misc_labels", []):
            try: lbl.configure(text_color=self._text())
            except Exception: pass

        for entry in getattr(self, "_misc_entries", []):
            try:
                entry.configure(
                    fg_color=("#ffffff", "#2b2b2b"),
                    text_color=self._text(),
                )
            except Exception: pass

        for button in getattr(self, "_step_buttons", []):
            button.configure(
                fg_color=self._primary(),
                hover_color=self._darken(self._primary()),
            )

        try:
            self.start_btn.configure(
                fg_color=self._success(),
                hover_color=self._darken(self._success()))
            self.stop_btn.configure(
                fg_color=self._accent(),
                hover_color=self._darken(self._accent()))
            self.settings_btn.configure(
                fg_color=self._primary(),
                hover_color=self._darken(self._primary()))
        except Exception:
            pass

    #UI
    def _build_ui(self):
        self._misc_labels = []
        self._misc_entries = []
        self._step_buttons = []

        self.clock_label = ctk.CTkLabel(
            self, text="--:--:--", font=("Segoe UI", 28, "bold"))
        self.clock_label.pack(pady=(14, 0))
        self.clock_canvas = tk.Canvas(
            self, width=144, height=144, bg=self._bg(),
            highlightthickness=0, borderwidth=0,
        )
        self.clock_caption = ctk.CTkLabel(
            self, text="Current time", font=("Segoe UI", 11))
        self.clock_caption.pack()
        self._misc_labels.append(self.clock_caption)

        self.timer_label = ctk.CTkLabel(self, text="00:00:00",
                                        font=("Segoe UI", 52, "bold"))
        self.timer_label.pack(pady=(10, 4))

        self.status_label = ctk.CTkLabel(self, text="Ready",
                                         font=("Segoe UI", 14))
        self.status_label.pack(pady=(0, 12))

        self.mode_selector = ctk.CTkSegmentedButton(
            self, values=["Countdown", "Alarm"], command=self._on_mode_changed)
        self.mode_selector.set("Countdown")
        self.mode_selector.pack(pady=(0, 8))

        inputs = ctk.CTkFrame(self, fg_color="transparent")
        inputs.pack(pady=6)

        self.h_var = ctk.StringVar(value="0")
        self.m_var = ctk.StringVar(value="5")
        self.s_var = ctk.StringVar(value="0")

        self.time_labels = []
        self.seconds_entry = None
        for text, var, mx in [("Hours", self.h_var, 23),
                              ("Minutes", self.m_var, 59),
                              ("Seconds", self.s_var, 59)]:
            col = ctk.CTkFrame(inputs, fg_color="transparent")
            col.pack(side="left", padx=8)

            lbl = ctk.CTkLabel(col, text=text, font=("Segoe UI", 12))
            lbl.pack()
            self._misc_labels.append(lbl)
            self.time_labels.append(lbl)

            entry = ctk.CTkEntry(col, textvariable=var, width=70,
                                 justify="center", font=("Segoe UI", 18))
            entry.pack(pady=2)
            # Allow an empty field while editing; validate its value on start
            vcmd = (self.register(lambda s: s == "" or (s.isdigit() and len(s) <= 4)), "%P")
            entry.configure(validate="key", validatecommand=vcmd)
            self._misc_entries.append(entry)
            if var is self.s_var:
                self.seconds_entry = entry

            btns = ctk.CTkFrame(col, fg_color="transparent")
            btns.pack()
            for symbol, delta in (("−", -1), ("+", 1)):
                button = ctk.CTkButton(
                    btns, text=symbol, width=30,
                    command=lambda v=var, d=delta, m=mx: self._step(v, d, 0, m))
                button.pack(side="left", padx=1)
                self._step_buttons.append(button)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=18)

        self.start_btn = ctk.CTkButton(btns, text="▶ Start", width=130, height=42,
                                       font=("Segoe UI", 15, "bold"),
                                       command=self.start_timer)
        self.start_btn.pack(side="left", padx=6)

        self.stop_btn = ctk.CTkButton(btns, text="■ Stop", width=130, height=42,
                                      font=("Segoe UI", 15, "bold"),
                                      command=self.stop_timer, state="disabled")
        self.stop_btn.pack(side="left", padx=6)

        self.comment_var = ctk.StringVar()
        ctk.CTkLabel(
            self, text="Optional note shown in the notification and alarm window:",
            font=("Segoe UI", 11),
        ).pack(pady=(2, 2))
        self.comment_entry = ctk.CTkEntry(
            self, textvariable=self.comment_var, width=330,
            placeholder_text="e.g. Take the cake out of the oven")
        self.comment_entry.pack(pady=(2, 12))
        self._misc_entries.append(self.comment_entry)

        self.settings_btn = ctk.CTkButton(self, text="⚙ Settings",
                                          width=280, height=38,
                                          command=self.open_settings)
        self.settings_btn.pack(pady=(0, 12))

    def _on_mode_changed(self, mode):
        alarm_mode = mode == "Alarm"
        for label, text in zip(self.time_labels, ("Hour", "Minute", "Second")):
            label.configure(text=text if alarm_mode else f"{text}s")
        self.seconds_entry.configure(state="disabled" if alarm_mode else "normal")
        self.status_label.configure(text="Set the alarm time" if alarm_mode else "Ready")

    def _update_clock(self):
        now = datetime.now()
        self.clock_label.configure(text=now.strftime("%H:%M:%S"))
        if self.cfg.get("clock_style") == "analog":
            self._draw_analog_clock(now)
        self._clock_after_id = self.after(1000, self._update_clock)

    def _set_clock_style(self):
        if self.cfg.get("clock_style") == "analog":
            self.clock_label.pack_forget()
            self.clock_canvas.pack(pady=(14, 0), before=self.clock_caption)
        else:
            self.clock_canvas.pack_forget()
            self.clock_label.pack(pady=(14, 0), before=self.clock_caption)
        self._draw_analog_clock(datetime.now())

    def _draw_analog_clock(self, now):
        canvas = self.clock_canvas
        canvas.delete("all")
        cx = cy = 72
        radius = 64
        canvas.create_oval(
            cx - radius, cy - radius, cx + radius, cy + radius,
            outline=self._primary(), width=2,
        )
        for minute in range(60):
            angle = math.radians(minute * 6 - 90)
            major = minute % 5 == 0
            inner = radius - (12 if major else 5)
            canvas.create_line(
                cx + inner * math.cos(angle), cy + inner * math.sin(angle),
                cx + (radius - 2) * math.cos(angle),
                cy + (radius - 2) * math.sin(angle),
                fill=self._text(), width=2 if major else 1,
            )
            if major:
                label_radius = radius - 22
                number = 12 if minute == 0 else minute // 5
                canvas.create_text(
                    cx + label_radius * math.cos(angle),
                    cy + label_radius * math.sin(angle),
                    text=str(number), fill=self._text(),
                    font=("Segoe UI", 8, "bold"),
                )

        second = now.second + now.microsecond / 1_000_000
        minute = now.minute + second / 60
        hour = now.hour % 12 + minute / 60
        for value, unit, length, color, width in (
            (hour, 12, 30, self._text(), 4),
            (minute, 60, 43, self._primary(), 3),
            (second, 60, 52, self._accent(), 1),
        ):
            angle = math.radians(value * 360 / unit - 90)
            canvas.create_line(
                cx, cy,
                cx + length * math.cos(angle),
                cy + length * math.sin(angle),
                fill=color, width=width, capstyle=tk.ROUND,
            )
        canvas.create_oval(cx - 3, cy - 3, cx + 3, cy + 3,
                           fill=self._accent(), outline="")

    @staticmethod
    def _step(var: ctk.StringVar, delta: int, lo: int, hi: int):
        try:
            v = int(var.get())
        except (ValueError, TypeError):
            v = 0
        v = _clamp(v + delta, lo, hi)
        var.set(str(v))

    def _parse_int(self, var: ctk.StringVar, default: int, lo: int, hi: int) -> int:
        try:
            v = int(var.get())
        except (ValueError, TypeError):
            v = default
        v = _clamp(v, lo, hi)
        #Show the clamped value in the input field.
        var.set(str(v))
        return v

    #Timer
    def start_timer(self):
        if self.running:
            return

        h = self._parse_int(self.h_var, 0, 0, 23)
        m = self._parse_int(self.m_var, 0, 0, 59)
        s = self._parse_int(self.s_var, 0, 0, 59)

        alarm_mode = self.mode_selector.get() == "Alarm"
        now = datetime.now()
        alarm_tomorrow = False
        if alarm_mode:
            self._alarm_target = now.replace(
                hour=h, minute=m, second=0, microsecond=0)
            if self._alarm_target <= now:
                self._alarm_target += timedelta(days=1)
                alarm_tomorrow = True
            total = max(1, math.ceil((self._alarm_target - now).total_seconds()))
        else:
            self._alarm_target = None
            total = h * 3600 + m * 60 + s
        if total <= 0:
            self.status_label.configure(text="Enter a time greater than zero.")
            return

        self.total = total
        self.remaining = total
        self.running = True
        self._timer_deadline = None if alarm_mode else time.monotonic() + total
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self._run_comment = self.comment_var.get().strip()
        self.status_label.configure(
            text=(f"Alarm set for {h:02d}:{m:02d}"
                  f"{' tomorrow' if alarm_tomorrow else ''}")
            if alarm_mode else "Counting down...")
        self.mode_selector.configure(state="disabled")
        self._update_display()
        self._countdown_after_id = self.after(0, self._countdown)

    def _countdown(self):
        self._countdown_after_id = None
        if self._alarm_target is not None:
            seconds_left = (self._alarm_target - datetime.now()).total_seconds()
        else:
            seconds_left = self._timer_deadline - time.monotonic()
        self.remaining = max(0, math.ceil(seconds_left))
        self._update_display()

        if seconds_left <= 0:
            self._on_finished()
            return
        delay_ms = max(20, min(1000, math.ceil(seconds_left * 1000)))
        self._countdown_after_id = self.after(delay_ms, self._countdown)

    def _update_display(self):
        h, r = divmod(self.remaining, 3600)
        m, s = divmod(r, 60)
        self.timer_label.configure(text=f"{h:02d}:{m:02d}:{s:02d}")

    def _on_finished(self):
        self.running = False
        self._alarm_target = None
        self._timer_deadline = None
        self.timer_label.configure(text="00:00:00")
        self.status_label.configure(text="🔔 Time is up!")
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.mode_selector.configure(state="normal")

        message = f"Time is up ({self._fmt(self.total)})"
        if self._run_comment:
            message = f"{message}\n{self._run_comment}"
        try:
            send_notification("Timer", message)
        except Exception as e:
            print("Notification error:", e)

        ok = self.player.play(
            self.cfg.get("sound_file", ""),
            auto_off_seconds=int(self.cfg.get("auto_off_seconds", 30)),
            fade_in=bool(self.cfg.get("fade_in", True)),
            fade_in_seconds=float(self.cfg.get("fade_in_seconds", 5)),
            max_volume=float(self.cfg.get("max_volume", 1.0)),
            loop_if_short=bool(self.cfg.get("loop_if_short", True)),
        )
        if not ok:
            self.status_label.configure(text=f"Sound: {self.player.last_error}")

        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(1500, lambda: self.attributes("-topmost", False))
        self.after(200, self._ask_snooze)

    def _ask_snooze(self):
        top = ctk.CTkToplevel(self)
        top.title("Time is up")
        comment_lines = max(1, math.ceil(len(self._run_comment) / 48))
        top.geometry(f"440x{320 + min(180, (comment_lines - 1) * 18)}")
        top.attributes("-topmost", True)
        top.transient(self)
        top.grab_set()

        ctk.CTkLabel(top, text="🔔 Timer finished",
                     font=("Segoe UI", 18, "bold")).pack(pady=(20, 6))
        if self._run_comment:
            ctk.CTkLabel(
                top, text=self._run_comment, wraplength=390,
                justify="center", font=("Segoe UI", 13),
            ).pack(padx=14, pady=(2, 8))

        default_min = int(self.cfg.get("snooze_minutes", 5))
        ctk.CTkLabel(top, text=f"Snooze (default: {default_min} min)").pack()

        custom_var = ctk.StringVar(value=str(default_min))
        row = ctk.CTkFrame(top, fg_color="transparent")
        row.pack(pady=8)
        ctk.CTkLabel(row, text="Custom duration (min):").pack(side="left", padx=4)
        entry = ctk.CTkEntry(row, textvariable=custom_var, width=70, justify="center")
        entry.pack(side="left")
        vcmd = (self.register(lambda s: s == "" or (s.isdigit() and len(s) <= 4)), "%P")
        entry.configure(validate="key", validatecommand=vcmd)

        self.vibration_status = ctk.CTkLabel(
            top, text="", font=("Segoe UI", 11), wraplength=400)
        self.vibration_status.pack(padx=12, pady=(2, 4))
        self._start_alarm_feedback(top)

        btns = ctk.CTkFrame(top, fg_color="transparent")
        btns.pack(pady=12)

        def close_and_stop():
            self._stop_alarm_feedback()
            self.player.stop()
            top.destroy()

        def snooze():
            try:
                minutes = int(custom_var.get() or default_min)
            except (ValueError, TypeError):
                minutes = default_min
            minutes = _clamp(minutes, 1, 240)
            self._stop_alarm_feedback()
            self.player.stop()
            self.mode_selector.set("Countdown")
            self._on_mode_changed("Countdown")
            self.h_var.set("0")
            self.m_var.set(str(minutes))
            self.s_var.set("0")
            top.destroy()
            self.status_label.configure(text=f"Snoozed for {minutes} min")
            self.after(300, self.start_timer)

        ctk.CTkButton(btns, text="Snooze", command=snooze, width=120).pack(side="left", padx=6)
        ctk.CTkButton(btns, text="Stop", command=close_and_stop, width=120,
                      fg_color="gray40").pack(side="left", padx=6)

        top.protocol("WM_DELETE_WINDOW", close_and_stop)

    def _start_alarm_feedback(self, dialog):
        vibration_enabled = bool(self.cfg.get("vibration_enabled", False))
        ticker_enabled = bool(self.cfg.get("show_vibration_ticker", False))
        if not vibration_enabled and not ticker_enabled:
            return
        try:
            pattern = load_pattern()
        except (OSError, ValueError) as error:
            self.vibration_status.configure(
                text=f"Could not load vibration pattern: {error}")
            return

        if vibration_enabled:
            self._active_vibration = GamepadVibration(
                self, pattern, on_status=self._show_vibration_status)
            self._active_vibration.start()
        elif ticker_enabled:
            self.vibration_status.configure(
                text="Gamepad vibration is off; visual pattern ticker is enabled.")

        if ticker_enabled:
            ticker = ctk.CTkLabel(
                dialog, text="", width=400, anchor="w",
                font=("Consolas", 11),
            )
            ticker.pack(fill="x", padx=18, pady=(4, 8))
            pulses = "  |  ".join(
                f"ON {pulse['on']:.2f}s  /  OFF {pulse['off']:.2f}s"
                for pulse in pattern
            )
            self._ticker_message = f"   VIBRATION PATTERN   |   {pulses}   |   REPEATING   "
            self._ticker_position = 0
            self._ticker_window = dialog
            self._animate_ticker(dialog, ticker)

    def _show_vibration_status(self, message):
        if hasattr(self, "vibration_status") and self.vibration_status.winfo_exists():
            self.vibration_status.configure(text=message)

    def _animate_ticker(self, dialog, ticker):
        if not dialog.winfo_exists():
            return
        message = self._ticker_message
        visible_width = 58
        start = self._ticker_position % len(message)
        wrapped = message + message
        ticker.configure(text=wrapped[start:start + visible_width])
        self._ticker_position += 1
        self._ticker_after_id = dialog.after(
            150, lambda: self._animate_ticker(dialog, ticker))

    def _stop_alarm_feedback(self):
        if self._ticker_after_id is not None:
            self._ticker_window.after_cancel(self._ticker_after_id)
            self._ticker_after_id = None
            self._ticker_window = None
        if self._active_vibration is not None:
            self._active_vibration.stop()
            self._active_vibration = None

    def _on_stopped(self):
        self.running = False
        self._alarm_target = None
        self._timer_deadline = None
        self.status_label.configure(text="Stopped")
        self.start_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.mode_selector.configure(state="normal")
        self.player.stop()
        self._update_display()

    def stop_timer(self):
        if self._countdown_after_id is not None:
            self.after_cancel(self._countdown_after_id)
            self._countdown_after_id = None
        if self.running:
            self._on_stopped()
        else:
            self.player.stop()
            self.status_label.configure(text="Ready")
            self._update_display()

    def _fmt(self, secs):
        h, r = divmod(secs, 3600)
        m, s = divmod(r, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _close(self):
        if self._countdown_after_id is not None:
            self.after_cancel(self._countdown_after_id)
            self._countdown_after_id = None
        if self._clock_after_id is not None:
            self.after_cancel(self._clock_after_id)
            self._clock_after_id = None
        self._stop_alarm_feedback()
        self.player.close()
        self.destroy()

    #settings
    def open_settings(self):
        SettingsWindow(self, self.cfg, on_save=self._on_settings_saved)

    def _on_settings_saved(self, new_cfg):
        self.cfg = new_cfg
        self._apply_appearance()
        self._restyle()
        self._set_clock_style()