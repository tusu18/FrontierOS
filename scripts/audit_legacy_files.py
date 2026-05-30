#!/usr/bin/env python3
"""
audit_legacy_files.py — find and (optionally) archive dead/legacy files.

Checks whether these are still imported/used anywhere:
  - app/dashboard.py            (legacy Streamlit UI)
  - app/services/scheduler.py   (superseded by app/agents/orchestrator.py)
  - frontend/                   (dead copy; active UI is static/)

Usage:
  python scripts/audit_legacy_files.py            # report only
  python scripts/audit_legacy_files.py --archive  # move unused → archive/legacy/
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent

LEGACY = {
    "app/dashboard.py":          [r"\bapp\.dashboard\b", r"from app import dashboard"],
    "app/services/scheduler.py": [r"app\.services\.scheduler", r"from app\.services import scheduler"],
    "frontend":                  [r"[\"']frontend/", r"\bfrontend\b"],
}

SEARCH_EXT = {".py", ".html", ".jsx", ".js", ".json", ".toml", ".cfg", ".txt", ".md"}


def find_usages(patterns) -> list:
    hits = []
    for path in _ROOT.rglob("*"):
        if path.suffix not in SEARCH_EXT:
            continue
        if "archive/legacy" in str(path) or "/.git/" in str(path):
            continue
        # don't count the file itself
        rel = str(path.relative_to(_ROOT))
        try:
            text = path.read_text(errors="ignore")
        except Exception:
            continue
        for pat in patterns:
            for m in re.finditer(pat, text):
                # skip self-references inside the legacy target
                if rel.startswith(tuple(LEGACY.keys())):
                    continue
                hits.append(f"{rel}: …{text[max(0, m.start()-30):m.start()+30].strip()}…")
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", action="store_true", help="Move unused legacy files to archive/legacy/")
    args = ap.parse_args()

    archive_dir = _ROOT / "archive" / "legacy"
    any_used = False

    for target, patterns in LEGACY.items():
        tpath = _ROOT / target
        exists = tpath.exists()
        usages = find_usages(patterns) if exists else []
        # filter out import-style self matches
        usages = [u for u in usages if not u.split(":")[0].startswith(target)]
        print(f"\n=== {target} ===")
        print(f"  exists: {exists}")
        print(f"  external usages: {len(usages)}")
        for u in usages[:8]:
            print(f"    {u}")

        if exists and not usages:
            if args.archive:
                dest = archive_dir / target
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(tpath), str(dest))
                print(f"  ARCHIVED → {dest.relative_to(_ROOT)}")
            else:
                print("  -> SAFE TO ARCHIVE (run with --archive)")
        elif usages:
            any_used = True
            print("  -> STILL USED; not archiving")

    if not args.archive:
        print("\nDry run. Re-run with --archive to move unused files.")


if __name__ == "__main__":
    main()
