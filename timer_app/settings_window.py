import copy
import customtkinter as ctk
from tkinter import colorchooser, filedialog, messagebox

from .settings import save_config, set_autostart, THEME_PRESETS
from .sound import scan_music_files
from .vibration import (
    DEFAULT_PATTERN,
    MousePatternRecorder,
    load_pattern,
    save_pattern,
)


def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _clamp(v, lo, hi): return max(lo, min(hi, v))


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, master, config: dict, on_save=None):
        super().__init__(master)
        self.title("Settings")
        self.geometry("740x660")
        self.minsize(740, 660)

        self.original = copy.deepcopy(config)
        self.draft = copy.deepcopy(config)
        try:
            self.draft["vibration_pattern"] = load_pattern()
        except (OSError, ValueError) as error:
            messagebox.showerror("Could not load vibration pattern", str(error), parent=self)
            self.draft["vibration_pattern"] = [pulse.copy() for pulse in DEFAULT_PATTERN]
        self.original["vibration_pattern"] = copy.deepcopy(
            self.draft["vibration_pattern"])
        self.on_save = on_save

        self.transient(master)
        self.grab_set()

        self._loading = True
        self._test_player = None
        self._recorder = None
        self._recording_after_id = None
        self._build()
        self._loading = False

        self._bind_dirty_tracking()
        self._update_save_button()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Destroy>", self._on_destroy, add="+")

    #UI
    def _build(self):
        ctk.CTkLabel(self, text="Settings",
                     font=("Segoe UI", 20, "bold")).pack(pady=(14, 4))

        self.tabs = ctk.CTkTabview(self, width=700, height=520)
        self.tabs.pack(fill="both", expand=True, padx=14, pady=8)

        self._build_sound_tab(self.tabs.add("🔊 Sound"))
        self._build_general_tab(self.tabs.add("⚙ General"))
        self._build_customization_tab(self.tabs.add("🎨 Customization"))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(fill="x", padx=14, pady=(0, 12))

        self.save_btn = ctk.CTkButton(
            btns, text="Save", width=110, height=36,
            font=("Segoe UI", 14, "bold"),
            command=self._save,
        )
        self.save_btn.pack(side="right")

        self.apply_btn = ctk.CTkButton(
            btns, text="Apply", width=110, height=36,
            command=self._apply,
        )
        self.apply_btn.pack(side="right", padx=8)

        ctk.CTkButton(btns, text="Cancel", width=110, height=36,
                      fg_color="gray40", hover_color="gray30",
                      command=self._cancel).pack(side="right")

        self.test_status = ctk.CTkLabel(self, text="", font=("Segoe UI", 12))
        self.test_status.pack(pady=(0, 4))

    #SOUND TAB
    def _build_sound_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        #Sound file
        f1 = ctk.CTkFrame(scroll)
        f1.pack(fill="x", padx=6, pady=6)
        ctk.CTkLabel(f1, text="Alarm sound",
                     font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=12, pady=(8, 4))

        row = ctk.CTkFrame(f1, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=4)
        self.sound_path_var = ctk.StringVar(value=self.draft.get("sound_file", ""))
        ctk.CTkEntry(row, textvariable=self.sound_path_var).pack(
            side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(row, text="Browse", width=80,
                      command=self._pick_sound_file).pack(side="left")

        row2 = ctk.CTkFrame(f1, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkButton(row2, text="From library", width=140,
                      command=self._pick_from_library).pack(side="left")
        ctk.CTkButton(row2, text="▶ Test", width=90,
                      fg_color="#15803d", hover_color="#166534",
                      command=self._test_sound).pack(side="left", padx=8)

        #Music folders
        f2 = ctk.CTkFrame(scroll)
        f2.pack(fill="x", padx=6, pady=6)
        ctk.CTkLabel(f2, text="Music folders",
                     font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=12, pady=(8, 4))

        self.dirs_box = ctk.CTkTextbox(f2, height=90)
        self.dirs_box.pack(fill="x", padx=12, pady=4)
        self._refresh_dirs_box()

        drow = ctk.CTkFrame(f2, fg_color="transparent")
        drow.pack(fill="x", padx=12, pady=(0, 10))
        ctk.CTkButton(drow, text="+ Add", width=120,
                      command=self._add_music_dir).pack(side="left")
        ctk.CTkButton(drow, text="− Remove", width=120,
                      fg_color="#b91c1c", hover_color="#991b1b",
                      command=self._remove_music_dir).pack(side="left", padx=8)

        #Playback options
        f3 = ctk.CTkFrame(scroll)
        f3.pack(fill="x", padx=6, pady=6)
        ctk.CTkLabel(f3, text="Playback options",
                     font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=12, pady=(8, 4))

        self.auto_off_var = ctk.StringVar(value=str(self.draft.get("auto_off_seconds", 30)))
        self._entry_row(f3, "Stop playback after (sec, 0 = never)",
                        self.auto_off_var, 0, 3600,
                        hint="How long the alarm sound plays")

        self.fade_in_var = ctk.BooleanVar(value=bool(self.draft.get("fade_in", True)))
        ctk.CTkSwitch(f3, text="Fade in volume",
                      variable=self.fade_in_var).pack(anchor="w", padx=12, pady=6)

        self.fade_secs_var = ctk.StringVar(value=str(self.draft.get("fade_in_seconds", 5)))
        self._entry_row(f3, "Fade-in duration (sec)",
                        self.fade_secs_var, 1, 60,
                        hint="Time until the sound reaches maximum volume")

        vol_row = ctk.CTkFrame(f3, fg_color="transparent")
        vol_row.pack(fill="x", padx=12, pady=(6, 2))
        ctk.CTkLabel(vol_row, text="Maximum volume",
                     width=280, anchor="w").pack(side="left")
        self.max_vol_var = ctk.DoubleVar(value=float(self.draft.get("max_volume", 1.0)))
        self.vol_label = ctk.CTkLabel(vol_row,
                                      text=f"{int(self.max_vol_var.get()*100)}%",
                                      width=50)
        self.vol_label.pack(side="right")
        ctk.CTkSlider(f3, from_=0.05, to=1.0, variable=self.max_vol_var,
                      command=lambda v: self.vol_label.configure(
                          text=f"{int(float(v)*100)}%")
                      ).pack(fill="x", padx=12, pady=(0, 10))

        self.loop_var = ctk.BooleanVar(value=bool(self.draft.get("loop_if_short", True)))
        self.loop_label_var = ctk.StringVar()
        ctk.CTkSwitch(f3, textvariable=self.loop_label_var,
                      variable=self.loop_var).pack(anchor="w", padx=12, pady=(0, 10))
        self.auto_off_var.trace_add("write", self._update_loop_label)
        self._update_loop_label()

    #GENERAL TAB
    def _build_general_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        #Snooze
        f1 = ctk.CTkFrame(scroll)
        f1.pack(fill="x", padx=6, pady=6)
        ctk.CTkLabel(f1, text="Snooze",
                     font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=12, pady=(8, 4))
        self.snooze_var = ctk.StringVar(value=str(self.draft.get("snooze_minutes", 5)))
        self._entry_row(f1, "Default snooze duration (min)",
                        self.snooze_var, 1, 240,
                        hint="Suggested duration shown when the alarm goes off")

        f_autostart = ctk.CTkFrame(scroll)
        f_autostart.pack(fill="x", padx=6, pady=6)
        ctk.CTkLabel(f_autostart, text="Startup",
                     font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=12, pady=(8, 4))
        self.autostart_var = ctk.BooleanVar(
            value=bool(self.draft.get("autostart", False)))
        ctk.CTkSwitch(
            f_autostart, text="Start automatically when Windows starts",
            variable=self.autostart_var,
        ).pack(anchor="w", padx=12, pady=(2, 10))

        f_vibration = ctk.CTkFrame(scroll)
        f_vibration.pack(fill="x", padx=6, pady=6)
        ctk.CTkLabel(f_vibration, text="Vibration and visual feedback",
                     font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=12, pady=(8, 4))
        self.vibration_var = ctk.BooleanVar(
            value=bool(self.draft.get("vibration_enabled", False)))
        ctk.CTkSwitch(
            f_vibration, text="Vibrate a supported gamepad when the timer ends",
            variable=self.vibration_var,
        ).pack(anchor="w", padx=12, pady=4)
        self.ticker_var = ctk.BooleanVar(
            value=bool(self.draft.get("show_vibration_ticker", False)))
        ctk.CTkSwitch(
            f_vibration, text="Show a scrolling vibration-pattern ticker",
            variable=self.ticker_var,
        ).pack(anchor="w", padx=12, pady=4)
        ctk.CTkLabel(
            f_vibration,
            text="Ordinary mice do not expose a standard vibration API. Left-click recording creates a gamepad pattern; the scrolling ticker is a visual alternative.",
            font=("Segoe UI", 11), wraplength=650, justify="left",
        ).pack(anchor="w", padx=12, pady=4)
        ctk.CTkButton(
            f_vibration, text="Record pattern from left mouse clicks",
            command=self._open_pattern_recorder,
        ).pack(anchor="w", padx=12, pady=(4, 10))

    def _build_customization_tab(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        appearance = ctk.CTkFrame(scroll)
        appearance.pack(fill="x", padx=6, pady=6)
        ctk.CTkLabel(appearance, text="Appearance",
                     font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=12, pady=(8, 4))
        theme_row = ctk.CTkFrame(appearance, fg_color="transparent")
        theme_row.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(theme_row, text="Theme:", width=140, anchor="w").pack(side="left")
        self.theme_var = ctk.StringVar(value=self.draft.get("theme", "dark"))
        ctk.CTkOptionMenu(
            theme_row, values=["dark", "light"], variable=self.theme_var, width=160,
        ).pack(side="left")
        self.theme_var.trace_add("write", self._on_theme_changed)

        clock_row = ctk.CTkFrame(appearance, fg_color="transparent")
        clock_row.pack(fill="x", padx=12, pady=(4, 10))
        ctk.CTkLabel(clock_row, text="Clock style:", width=140, anchor="w").pack(side="left")
        self.clock_style_var = ctk.StringVar(
            value=self.draft.get("clock_style", "digital"))
        ctk.CTkOptionMenu(
            clock_row, values=["digital", "analog"], variable=self.clock_style_var,
            width=160,
        ).pack(side="left")

        colors = ctk.CTkFrame(scroll)
        colors.pack(fill="x", padx=6, pady=6)
        ctk.CTkLabel(colors, text="Interface colors",
                     font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=12, pady=(8, 4))
        ctk.CTkLabel(
            colors,
            text="Edit RGB values from 0 to 255, use Choose color to open the system palette, or reset to the selected theme.",
            font=("Segoe UI", 11), wraplength=650, justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 6))

        self._color_vars = {}
        self._color_previews = {}
        for key, label in [
            ("color_primary", "Primary actions"),
            ("color_accent", "Accent / stop"),
            ("color_success", "Success / start"),
            ("color_bg", "Window background"),
            ("color_text", "Text"),
        ]:
            self._make_color_row(colors, key, label)
        ctk.CTkButton(
            colors, text="Reset colors to theme palette",
            command=self._reset_colors_to_theme,
        ).pack(anchor="w", padx=12, pady=(4, 12))

    #helpers
    def _entry_row(self, parent, label, var, lo, hi, hint=""):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=4)

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(left, text=label, anchor="w").pack(anchor="w")
        if hint:
            ctk.CTkLabel(left, text=hint, anchor="w",
                         font=("Segoe UI", 11),
                         text_color=("gray40", "gray60")).pack(anchor="w")

        entry = ctk.CTkEntry(row, textvariable=var, width=80, justify="center")
        entry.pack(side="right", padx=(8, 0))

        #Allow an empty field while editing; validate its value on save.
        vcmd = (self.register(lambda s: s == "" or (s.isdigit() and len(s) <= 4)), "%P")
        entry.configure(validate="key", validatecommand=vcmd)

        def inc(): self._step(var, +1, lo, hi)
        def dec(): self._step(var, -1, lo, hi)

        btn_box = ctk.CTkFrame(row, fg_color="transparent")
        btn_box.pack(side="right")
        ctk.CTkButton(btn_box, text="−", width=30, command=dec).pack(side="left")
        ctk.CTkButton(btn_box, text="+", width=30, command=inc).pack(side="left", padx=2)
        return entry

    @staticmethod
    def _step(var, delta, lo, hi):
        try:
            v = int(var.get())
        except (ValueError, TypeError):
            v = lo
        var.set(str(_clamp(v + delta, lo, hi)))

    def _update_loop_label(self, *_):
        try:
            duration = int(self.auto_off_var.get() or 0)
        except ValueError:
            duration = 0
        limit = "the full playback duration" if duration == 0 else f"{duration} seconds"
        self.loop_label_var.set(f"Loop sound files shorter than {limit}")

    def _make_color_row(self, parent, key, label):
        rgb = self.draft.get(key, [128, 128, 128])

        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=3)

        ctk.CTkLabel(row, text=label, width=160, anchor="w").pack(side="left")

        preview = ctk.CTkLabel(row, text="      ", fg_color=rgb_to_hex(rgb),
                               corner_radius=4, width=50)
        preview.pack(side="right", padx=6)
        color_button = ctk.CTkButton(
            row, text="Choose color", width=100,
            command=lambda color_key=key: self._choose_color(color_key),
        )
        color_button.pack(side="right", padx=4)

        vars_ = []
        for name, val in zip(("R", "G", "B"), rgb):
            ctk.CTkLabel(row, text=name).pack(side="left", padx=(6, 0))
            v = ctk.StringVar(value=str(val))
            entry = ctk.CTkEntry(row, textvariable=v, width=52, justify="center")
            entry.pack(side="left", padx=2)
            vcmd = (self.register(lambda s: s == "" or (s.isdigit() and len(s) <= 3)), "%P")
            entry.configure(validate="key", validatecommand=vcmd)
            vars_.append(v)

        def update_preview(*_):
            try:
                rgb2 = tuple(_clamp(int(v.get() or 0), 0, 255) for v in vars_)
                preview.configure(fg_color=rgb_to_hex(rgb2))
            except Exception:
                pass

        for v in vars_:
            v.trace_add("write", update_preview)

        self._color_vars[key] = vars_
        self._color_previews[key] = preview

    def _choose_color(self, key):
        current = tuple(
            _clamp(int(var.get() or 0), 0, 255)
            for var in self._color_vars[key]
        )
        chosen, _ = colorchooser.askcolor(
            color=rgb_to_hex(current), parent=self, title="Choose interface color")
        if chosen:
            for var, channel in zip(self._color_vars[key], chosen):
                var.set(str(round(channel)))

    def _on_theme_changed(self, *_):
        """Load the suggested palette when a theme is selected."""
        if self._loading:
            return
        theme = self.theme_var.get()
        preset = THEME_PRESETS.get(theme)
        if not preset:
            return

        for key, rgb in preset.items():
            if key in self._color_vars:
                for v, val in zip(self._color_vars[key], rgb):
                    v.set(str(val))

        self._update_save_button()

    def _reset_colors_to_theme(self):
        theme = self.theme_var.get()
        preset = THEME_PRESETS.get(theme, THEME_PRESETS["dark"])
        for key, rgb in preset.items():
            if key in self._color_vars:
                for v, val in zip(self._color_vars[key], rgb):
                    v.set(str(val))
        self._update_save_button()

    def _refresh_dirs_box(self):
        self.dirs_box.configure(state="normal")
        self.dirs_box.delete("1.0", "end")
        for d in self.draft.get("music_dirs", []):
            self.dirs_box.insert("end", d + "\n")
        self.dirs_box.configure(state="disabled")

    def _add_music_dir(self):
        d = filedialog.askdirectory(title="Select music folder")
        if d:
            self.draft.setdefault("music_dirs", []).append(d)
            self._refresh_dirs_box()
            self._update_save_button()

    def _remove_music_dir(self):
        dirs = self.draft.get("music_dirs", [])
        if not dirs:
            return
        top = ctk.CTkToplevel(self)
        top.title("Remove folder")
        top.geometry("500x220")
        top.transient(self)
        top.grab_set()

        ctk.CTkLabel(top, text="Select a folder to remove").pack(pady=10)
        var = ctk.StringVar(value=dirs[0])
        ctk.CTkOptionMenu(top, values=dirs, variable=var, width=440).pack(pady=6)

        def do_remove():
            val = var.get()
            if val in dirs:
                dirs.remove(val)
                self._refresh_dirs_box()
                self._update_save_button()
            top.destroy()

        ctk.CTkButton(top, text="Remove", fg_color="#b91c1c",
                      hover_color="#991b1b", command=do_remove).pack(pady=12)

    def _pick_sound_file(self):
        f = filedialog.askopenfilename(
            title="Select alarm sound",
            filetypes=[("Audio files", "*.wav *.ogg *.mp3 *.flac"), ("All files", "*.*")]
        )
        if f:
            self.sound_path_var.set(f)
            self._update_save_button()

    def _pick_from_library(self):
        files = scan_music_files(self.draft.get("music_dirs", []))
        if not files:
            self.test_status.configure(text="The library is empty. Add a music folder first.",
                                       text_color="#b45309")
            return
        top = ctk.CTkToplevel(self)
        top.title("Sound library")
        top.geometry("600x440")
        top.transient(self)
        top.grab_set()

        ctk.CTkLabel(top, text="Click a file to select it",
                     font=("Segoe UI", 13, "bold")).pack(pady=8)

        scroll = ctk.CTkScrollableFrame(top)
        scroll.pack(fill="both", expand=True, padx=10, pady=6)

        def choose(path):
            self.sound_path_var.set(path)
            top.destroy()
            self._update_save_button()

        for label, path in files:
            ctk.CTkButton(scroll, text=label, anchor="w",
                          fg_color="transparent",
                          text_color=("black", "white"),
                          hover_color=("gray80", "gray25"),
                          command=lambda p=path: choose(p)).pack(fill="x", pady=1)

    def _test_sound(self):
        """Play a short test using the currently edited options."""
        from .sound import SoundPlayer

        #Read the values being edited, not the saved configuration.
        try:    auto_off = int(self.auto_off_var.get() or 0)
        except ValueError: auto_off = 0
        try:    fade_secs = int(self.fade_secs_var.get() or 5)
        except ValueError: fade_secs = 5

        if self._test_player is None:
            self._test_player = SoundPlayer()
        else:
            self._test_player.stop()

        path = self.sound_path_var.get()

        ok = self._test_player.play(
            path,
            auto_off_seconds=min(auto_off, 10) if auto_off > 0 else 10,
            fade_in=bool(self.fade_in_var.get()),
            fade_in_seconds=fade_secs,
            max_volume=float(self.max_vol_var.get()),
            loop_if_short=bool(self.loop_var.get()),
        )
        if ok:
            self.test_status.configure(text="▶ Playing…", text_color="#15803d")
            self.after(10500, lambda: self.test_status.configure(text=""))
        else:
            self.test_status.configure(
                text=f"⚠ {self._test_player.last_error or 'Playback failed.'}",
                text_color="#b91c1c",
            )

    #dirty tracking
    def _collect_draft(self):
        self.draft["sound_file"] = self.sound_path_var.get()

        def safe_int(var, default, lo, hi):
            try: v = int(var.get())
            except (ValueError, TypeError): v = default
            return _clamp(v, lo, hi)

        self.draft["auto_off_seconds"] = safe_int(self.auto_off_var, 0, 0, 3600)
        self.draft["fade_in"] = bool(self.fade_in_var.get())
        self.draft["fade_in_seconds"] = safe_int(self.fade_secs_var, 5, 1, 60)
        self.draft["max_volume"] = float(self.max_vol_var.get())
        self.draft["loop_if_short"] = bool(self.loop_var.get())
        self.draft["snooze_minutes"] = safe_int(self.snooze_var, 5, 1, 240)
        self.draft["theme"] = self.theme_var.get()
        self.draft["clock_style"] = self.clock_style_var.get()
        self.draft["autostart"] = bool(self.autostart_var.get())
        self.draft["vibration_enabled"] = bool(self.vibration_var.get())
        self.draft["show_vibration_ticker"] = bool(self.ticker_var.get())

        for key, vars_ in self._color_vars.items():
            self.draft[key] = [
                _clamp(int(v.get() or 0), 0, 255) for v in vars_
            ]

    def _bind_dirty_tracking(self):
        def _mark(*_):
            if self._loading:
                return
            self._update_save_button()

        for var in [
            self.sound_path_var, self.auto_off_var, self.fade_in_var,
            self.fade_secs_var, self.max_vol_var, self.loop_var,
            self.snooze_var, self.theme_var, self.clock_style_var,
            self.autostart_var, self.vibration_var, self.ticker_var,
        ]:
            var.trace_add("write", _mark)
        for vars_ in self._color_vars.values():
            for v in vars_:
                v.trace_add("write", _mark)

    def _update_save_button(self):
        if self._loading:
            return
        self._collect_draft()
        changed = any(self.draft.get(k) != self.original.get(k) for k in self.draft)
        self.save_btn.configure(state="normal")
        self.apply_btn.configure(state="normal" if changed else "disabled")

    def _save(self):
        if self._persist():
            self.destroy()

    def _apply(self):
        self._persist()

    def _persist(self):
        self._collect_draft()
        try:
            set_autostart(bool(self.draft.get("autostart", False)))
            save_pattern(self.draft["vibration_pattern"])
            config = {
                key: value for key, value in self.draft.items()
                if key != "vibration_pattern"
            }
            save_config(config)
        except Exception as e:
            messagebox.showerror("Could not save settings", str(e), parent=self)
            return False
        self._stop_test_playback()
        self.original = copy.deepcopy(self.draft)
        if self.on_save:
            config = {
                key: value for key, value in self.draft.items()
                if key != "vibration_pattern"
            }
            self.on_save(copy.deepcopy(config))
        self._update_save_button()
        return True

    def _cancel(self):
        self._collect_draft()
        changed = any(self.draft.get(k) != self.original.get(k) for k in self.draft)
        if changed and not messagebox.askyesno(
            "Discard changes?",
            "You have unsaved changes. Do you want to discard them?",
            parent=self,
        ):
            return
        self._stop_test_playback()
        self.destroy()

    def _stop_test_playback(self):
        if self._test_player is not None:
            self._test_player.close()
        self._stop_pattern_recording()

    def _on_destroy(self, event):
        if event.widget is self:
            self._stop_test_playback()

    def _open_pattern_recorder(self):
        if self._recorder is not None:
            return
        try:
            self._recorder = MousePatternRecorder()
        except OSError as error:
            messagebox.showerror("Mouse recording unavailable", str(error), parent=self)
            return

        window = ctk.CTkToplevel(self)
        window.title("Record vibration pattern")
        window.geometry("470x210")
        window.transient(self)
        ctk.CTkLabel(
            window,
            text="Recording starts immediately. Hold and release the left mouse button; hold times become vibration pulses and pauses between clicks become gaps.",
            wraplength=420, justify="left",
        ).pack(padx=18, pady=(18, 8))
        self._record_status = ctk.CTkLabel(window, text="Recording left mouse clicks…")
        self._record_status.pack(pady=4)
        buttons = ctk.CTkFrame(window, fg_color="transparent")
        buttons.pack(pady=12)
        ctk.CTkButton(
            buttons, text="Finish and use pattern",
            command=lambda: self._finish_pattern_recording(window),
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            buttons, text="Cancel", fg_color="gray40",
            command=lambda: self._cancel_pattern_recording(window),
        ).pack(side="left", padx=6)
        window.protocol("WM_DELETE_WINDOW", lambda: self._cancel_pattern_recording(window))
        self._recording_window = window
        self._poll_pattern_recording()

    def _poll_pattern_recording(self):
        if self._recorder is None:
            return
        self._recorder.poll()
        self._recording_after_id = self.after(15, self._poll_pattern_recording)

    def _finish_pattern_recording(self, window):
        try:
            pattern = self._recorder.finish()
        except ValueError as error:
            self._record_status.configure(text=str(error))
            return
        self._stop_pattern_recording()
        self.draft["vibration_pattern"] = pattern
        self.test_status.configure(
            text=f"Recorded {len(pattern)} vibration pulse(s). Save settings to keep the pattern.",
            text_color="#15803d",
        )
        window.destroy()
        self._update_save_button()

    def _cancel_pattern_recording(self, window):
        self._stop_pattern_recording()
        window.destroy()

    def _stop_pattern_recording(self):
        if self._recording_after_id is not None:
            self.after_cancel(self._recording_after_id)
            self._recording_after_id = None
        self._recorder = None