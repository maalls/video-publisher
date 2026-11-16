import os
from datetime import datetime
from video_publisher.core import PARIS, schedule_due

scheduled = os.environ.get("GITHUB_EVENT_NAME") == "schedule"
due = not scheduled or schedule_due(datetime.now(PARIS))
with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as stream:
    stream.write(f"due={str(due).lower()}\n")
    stream.write(f"date={datetime.now(PARIS).date().isoformat()}\n")
print("Fenêtre de génération active" if due else "Cron d'autre saison ignoré")
