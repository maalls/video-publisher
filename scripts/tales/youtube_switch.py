#!/usr/bin/env python3
"""Switch de compte YouTube : lister les comptes, ou envoyer sur un compte choisi explicitement.
Aucune publication sans --upload. Ne choisit jamais de compte par defaut.
  youtube_switch.py list
  youtube_switch.py upload --account NOM VIDEO.mp4 --metadata m.json --journal j.json \
      --visibility private --made-for-kids no --upload"""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, "src"); sys.path.insert(0, "scripts/tales")
from video_publisher.youtube_accounts import AccountError, describe, load_registry, resolve

SECRETS = Path("var/project/tales/secrets")
REGISTRY = SECRETS / "youtube-accounts.json"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    up = sub.add_parser("upload")
    up.add_argument("--account", required=True)
    up.add_argument("video", type=Path); up.add_argument("--metadata", required=True, type=Path)
    up.add_argument("--journal", required=True, type=Path)
    up.add_argument("--visibility", required=True, choices=["public", "private", "unlisted"])
    up.add_argument("--made-for-kids", required=True, choices=["yes", "no"])
    up.add_argument("--publish-at", default=None); up.add_argument("--upload", action="store_true")
    args = p.parse_args(argv)
    try:
        registry = load_registry(REGISTRY)
        if args.cmd == "list":
            print(json.dumps(describe(registry, SECRETS), ensure_ascii=False, indent=2)); return 0
        label, token, channel = resolve(registry, SECRETS, args.account)
        import upload_youtube_scheduled as up_mod
        args.token, args.channel_id = token, channel
        print("compte:", label, "chaine:", channel, flush=True)
        up_mod.run(args)
    except AccountError as e:
        print("Stopped:", e); return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
