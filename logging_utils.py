from datetime import datetime


def log_step(stage, message, **details):
    """
    Simple structured terminal logging for demo visibility.
    Example:
      [2026-05-14 12:34:01] [JIRA] Creating ticket employee="Maya Chen"
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    extra = ""
    if details:
        extra = " " + " ".join(f'{key}="{value}"' for key, value in details.items())
    print(f"[{timestamp}] [{stage}] {message}{extra}", flush=True)
