from timer_app.settings import ensure_dirs
from timer_app.app import TimerApp

def main():
    ensure_dirs()  # Create config/ and SFX/ beside the executable.
    app = TimerApp()
    app.mainloop()

if __name__ == "__main__":
    main()