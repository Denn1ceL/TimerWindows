# Timer App

A lightweight Windows timer with a modern UI, customizable themes, alarm sounds, desktop notifications, and optional gamepad vibration.

Version: 0.1.0-alpha

### Features:
1. Digital countdown timer
2. Dark / light themes with fully customizable colors
3. Alarm sound playback (pygame) with fade-in, volume control, and snooze
4. Windows toast notifications
5. Gamepad vibration support (when available)
6. Optional autostart with Windows
7. Settings and sound files stored next to the executable

### Requirements

Windows

Python 3.10+ (3.11 or 3.12 recommended) if running from source

### Run from source
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Pre-built release

Download the latest Windows build from the [Releases](https://github.com/Denn1ceL/TimerWindows/releases) page.

Unpack the zip and run the .exe. The _internal folder must stay next to the executable.

### Building the executable (PyInstaller)
```
pip install pyinstaller
pyinstaller --noconsole --name "Timer Windows" main.py
```

### Dependencies:

See requirements.txt:

1. customtkinter — UI



2. pygame — audio and gamepad vibration



3. plyer — cross-backend notifications (with optional win10toast fallback)
