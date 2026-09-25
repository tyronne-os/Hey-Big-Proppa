#!/usr/bin/env python3
"""
The Utility Room CLI -- inspect, health-check, and manage every data source in
sources.yaml without touching any ingest script's internals.

Usage:
    python3 scripts/sources.py list
    python3 scripts/sources.py list --status active
    python3 scripts/sources.py show rotowire_props
    python3 scripts/sources.py check rotowire_props      # live reachability check
    python3 scripts/sources.py check --all
    python3 scripts/sources.py disable espn_news         # flip status in the file
    python3 scripts/sources.py enable espn_news
    python3 scripts/sources.py run rotowire_props         # run its ingest_script
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import urllib.error
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
MANIFEST = REPO / "sources.yaml"


def load_sources() -> list[dict]:
    try:
        import yaml
    except ImportError:
        print("ERROR: pyyaml not importable.\n"
              "  pip install --target=.pylibs pyyaml\n"
              "  PYTHONPATH=.pylibs python3 scripts/sources.py ...",
              file=sys.stderr)
        sys.exit(2)
    data = yaml.safe_load(MANIFEST.read_text())
    return data.get("sources", [])


def save_sources(sources: list[dict]) -> None:
    import yaml
    data = {"sources": sources}
    header = MANIFEST.read_text().split("\nsources:")[0]  # keep the top comment block
    with MANIFEST.open("w") as fh:
        fh.write(header + "\n")
        yaml.safe_dump(data, fh, sort_keys=False, default_flow_style=False, width=88)


def find(sources: list[dict], source_id: str) -> dict:
    for s in sources:
        if s["id"] == source_id:
            return s
    print(f"ERROR: no source with id '{source_id}'. Run 'list' to see valid ids.",
          file=sys.stderr)
    sys.exit(1)


def cmd_list(args) -> int:
    sources = load_sources()
    if args.status:
        sources = [s for s in sources if s["status"] == args.status]
    print(f"{'ID':26s} {'STATUS':11s} {'KIND':12s} {'CADENCE'}")
    print("-" * 90)
    for s in sources:
        print(f"{s['id']:26s} {s['status']:11s} {s['kind']:12s} {s.get('cadence', '')}")
    return 0


def cmd_show(args) -> int:
    sources = load_sources()
    s = find(sources, args.source_id)
    for k, v in s.items():
        if isinstance(v, list):
            print(f"{k}:")
            for item in v:
                print(f"  - {item}")
        else:
            print(f"{k}: {v}")
    return 0


def cmd_check(args) -> int:
    sources = load_sources()
    targets = sources if args.all else [find(sources, args.source_id)]
    ok = failed = skipped = 0
    for s in targets:
        if not s.get("base_url"):
            print(f"{s['id']:26s} SKIP (no base_url to check)")
            skipped += 1
            continue
        url = s["base_url"]
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (frontal-lobe2 health-check)"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                code = r.status
        except urllib.error.HTTPError as e:
            code = e.code
        except urllib.error.URLError as e:
            print(f"{s['id']:26s} UNREACHABLE  ({e.reason})")
            failed += 1
            continue
        tag = "OK" if code < 400 else "FAIL"
        print(f"{s['id']:26s} HTTP {code}  {tag}  [{url}]")
        if code < 400:
            ok += 1
        else:
            failed += 1
    print(f"\n{ok} ok, {failed} failed, {skipped} skipped")
    return 1 if failed else 0


def cmd_enable(args) -> int:
    sources = load_sources()
    s = find(sources, args.source_id)
    s["status"] = "active"
    save_sources(sources)
    print(f"{args.source_id} -> active")
    return 0


def cmd_disable(args) -> int:
    sources = load_sources()
    s = find(sources, args.source_id)
    s["status"] = "disabled"
    save_sources(sources)
    print(f"{args.source_id} -> disabled")
    return 0


def cmd_run(args) -> int:
    sources = load_sources()
    s = find(sources, args.source_id)
    script = s.get("ingest_script")
    if not script:
        print(f"ERROR: {args.source_id} has no ingest_script configured "
              f"(status: {s['status']}).", file=sys.stderr)
        return 1
    if s["status"] != "active":
        print(f"WARNING: {args.source_id} status is '{s['status']}', not 'active'. "
              f"Running anyway since you asked explicitly.")
    script_path = REPO / script
    if not script_path.exists():
        print(f"ERROR: {script_path} not found.", file=sys.stderr)
        return 1
    print(f"Running {script_path} ...")
    result = subprocess.run(
        [sys.executable, str(script_path), *args.script_args],
        cwd=str(REPO),
    )
    return result.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="The Utility Room -- manage data sources")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="list all sources")
    p_list.add_argument("--status", help="filter by status")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="show full detail for one source")
    p_show.add_argument("source_id")
    p_show.set_defaults(func=cmd_show)

    p_check = sub.add_parser("check", help="live reachability check (HTTP HEAD-ish GET)")
    p_check.add_argument("source_id", nargs="?")
    p_check.add_argument("--all", action="store_true")
    p_check.set_defaults(func=cmd_check)

    p_enable = sub.add_parser("enable", help="mark a source active")
    p_enable.add_argument("source_id")
    p_enable.set_defaults(func=cmd_enable)

    p_disable = sub.add_parser("disable", help="mark a source disabled")
    p_disable.add_argument("source_id")
    p_disable.set_defaults(func=cmd_disable)

    p_run = sub.add_parser("run", help="run a source's ingest script")
    p_run.add_argument("source_id")
    p_run.add_argument("script_args", nargs=argparse.REMAINDER)
    p_run.set_defaults(func=cmd_run)

    args = ap.parse_args()
    if args.cmd == "check" and not args.all and not args.source_id:
        ap.error("check requires a source_id or --all")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
