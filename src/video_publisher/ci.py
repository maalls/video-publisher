"""Explicit CI modes. Manual runs never schedule a public video."""
from datetime import date


def ci_arguments(event, mode, day, enable_daily=False, enable_youtube=False):
    day = date.fromisoformat(day).isoformat()
    if event == "schedule":
        if not enable_daily:
            raise ValueError("Cron désactivé : ENABLE_DAILY doit être true")
        mode = "scheduled" if enable_youtube else "render"
    elif event == "workflow_dispatch":
        if mode not in ("demo", "render", "private-test"):
            raise ValueError("Mode manuel invalide : demo, render ou private-test")
    else:
        raise ValueError("Événement CI non autorisé")
    arguments = ["--date", day]
    if mode == "demo":
        arguments.append("--demo")
    elif mode == "private-test":
        arguments.extend(["--publish-youtube", "--private-test"])
    elif mode == "scheduled":
        arguments.append("--publish-youtube")
    return arguments
