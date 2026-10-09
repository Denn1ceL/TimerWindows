def send_notification(title: str, message: str):
    """Send a Windows toast using the first available notification backend."""
    try:
        from plyer import notification
        notification.notify(
            title=title,
            message=message,
            app_name="TimerApp",
            timeout=10,
        )
        return True
    except Exception as e:
        print("Plyer notification failed:", e)

    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast(title, message, duration=10, threaded=True)
        return True
    except Exception:
        pass

    print(f"[NOTIFY] {title}: {message}")
    return False