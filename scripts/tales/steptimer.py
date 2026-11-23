#!/usr/bin/env python3
"""Automatic per-step timing for a tale production.

Writes timing.jsonl in the production dir (one JSON line per event) and a
readable timing-recap.md. Usage:
  steptimer.py PRODUCTION_DIR start STEP [--note TXT]
  steptimer.py PRODUCTION_DIR end STEP [--note TXT]
  steptimer.py PRODUCTION_DIR run STEP -- CMD ARGS...   (start, run, end, keeps exit code)
  steptimer.py PRODUCTION_DIR wait-start STEP / wait-end STEP   (waiting on Malo: review, ComfyUI down)
  steptimer.py PRODUCTION_DIR report
Steps: ecriture, voix, references, images, animations, sous-titres, montage,
relecture, reparations (suffix -vN allowed). Times are UTC ISO; recap shows Paris time.
"""
import argparse, json, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

def now(): return datetime.now(timezone.utc)

def log(prod, event, step, note=''):
    p = Path(prod) / 'timing.jsonl'
    with p.open('a') as f:
        f.write(json.dumps({'ts': now().isoformat(timespec='seconds'), 'event': event, 'step': step, 'note': note}) + '\n')

def fmt(sec):
    sec = int(round(sec)); h, r = divmod(sec, 3600); m, s = divmod(r, 60)
    return f'{h} h {m:02d} min' if h else (f'{m} min {s:02d} s' if m else f'{s} s')

def report(prod):
    p = Path(prod) / 'timing.jsonl'
    ev = [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []
    open_, rows = {}, []
    for e in ev:
        t = datetime.fromisoformat(e['ts'])
        k = e['step']
        if e['event'] in ('start', 'wait-start'):
            open_[(k, e['event'])] = (t, e['note'])
        else:
            key = (k, 'start' if e['event'] == 'end' else 'wait-start')
            if key in open_:
                t0, n0 = open_.pop(key)
                rows.append((k, 'attente' if e['event'] == 'wait-end' else 'travail', t0, t, e['note'] or n0))
    par = ZoneInfo('Europe/Paris')
    out = ['# Suivi des durées', '', '| Étape | Type | Début (Paris) | Fin (Paris) | Durée | Note |', '|---|---|---|---|---|---|']
    tot = {'travail': 0, 'attente': 0}
    for k, typ, a, b, n in rows:
        d = (b - a).total_seconds(); tot[typ] += d
        out.append(f"| {k} | {typ} | {a.astimezone(par):%d/%m %H:%M:%S} | {b.astimezone(par):%d/%m %H:%M:%S} | {fmt(d)} | {n} |")
    for (k, typ), (t0, n) in open_.items():
        out.append(f"| {k} | {typ} (en cours) | {t0.astimezone(par):%d/%m %H:%M:%S} | | | {n} |")
    out += ['', f"Total travail (machine/agent): {fmt(tot['travail'])}", f"Total attente (relecture Malo, blocages): {fmt(tot['attente'])}"]
    txt = '\n'.join(out) + '\n'
    (Path(prod) / 'timing-recap.md').write_text(txt)
    return txt

def main():
    a = sys.argv[1:]
    if len(a) >= 2 and a[1] == 'report': print(report(a[0])); return 0
    ap = argparse.ArgumentParser(); ap.add_argument('prod'); ap.add_argument('cmd', choices=['start', 'end', 'wait-start', 'wait-end', 'run'])
    ap.add_argument('step'); ap.add_argument('--note', default=''); ap.add_argument('rest', nargs=argparse.REMAINDER)
    n = ap.parse_args(a)
    Path(n.prod).mkdir(parents=True, exist_ok=True)
    if n.cmd == 'run':
        cmd = [x for x in n.rest if x != '--']
        log(n.prod, 'start', n.step, n.note)
        rc = subprocess.call(cmd)
        log(n.prod, 'end', n.step, (n.note + ' ' if n.note else '') + f'rc={rc}')
        report(n.prod); return rc
    log(n.prod, n.cmd, n.step, n.note); report(n.prod); return 0

sys.exit(main())
