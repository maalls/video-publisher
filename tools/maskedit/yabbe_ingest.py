"""Adds a video file to a project as a NEW asset (never on the timeline).
Usage (run with the editor backend's python, from its backend folder): yabbe_ingest.py SPACE PROJECT FILE NAME
Prints the new asset id on the last line."""
import shutil
import sys
import time

from app import config, storage
from app.api.media import schedule_processing
from app.engine import media
from app.models import Asset, Project, new_id

space, pid, src, name = sys.argv[1:5]
config.CURRENT_SPACE.set(space)
aid = new_id("a_")
stored = aid + ".mp4"
dest = storage.media_dir(pid) / stored
shutil.copyfile(src, dest)
fields = media.analyze(dest)
a = Asset(id=aid, filename=stored, original_name=name, size=dest.stat().st_size, **fields)


def add(p: Project) -> Project:
    p.assets.append(a)
    return p


storage.update(pid, add)
schedule_processing(pid, aid)
for _ in range(120):
    if storage.load(pid).asset(aid).status != "processing":
        break
    time.sleep(1)
print(aid)
