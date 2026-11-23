#!/usr/bin/env python3
"""Build the configured station page and start the static web server."""
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
WEB_ROOT = Path("/usr/share/nginx/html")


def env_flag(name):
    value = os.environ.get(name, "false").strip().lower()
    if value not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
        raise SystemExit(f"{name} must be a boolean value, got {value!r}")
    return value in {"true", "1", "yes", "on"}


def main():
    gtfs = Path(os.environ.get("GTFS_FILE", "/data/gtfs.zip"))
    station = os.environ.get("STATION", "").strip()
    if not station:
        raise SystemExit("STATION must be set to an exact GTFS station name")
    if not gtfs.is_file():
        raise SystemExit(f"GTFS file not found: {gtfs}")
    all_modes = env_flag("ALL_MODES")

    build_dir = tempfile.TemporaryDirectory(prefix="gleisy-")
    try:
        command = [
            sys.executable,
            str(APP_DIR / "build.py"),
            "--gtfs",
            str(gtfs),
            "--station",
            station,
            "--date",
            os.environ.get("DATE", "").strip() or date.today().isoformat(),
            "--max-turn",
            os.environ.get("MAX_TURN", "45"),
            "--stub",
            os.environ.get("STUB", "4"),
            "--out",
            build_dir.name,
        ]
        if all_modes:
            command.append("--all-modes")

        result = subprocess.run(command, check=False)
        if result.returncode:
            raise SystemExit(result.returncode)

        pages = list(Path(build_dir.name).glob("*.html"))
        if len(pages) != 1:
            raise SystemExit(f"Expected one generated HTML page, found {len(pages)}")

        WEB_ROOT.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pages[0], WEB_ROOT / "index.html")
    finally:
        build_dir.cleanup()

    os.execvp("nginx", ["nginx", "-g", "daemon off;"])


if __name__ == "__main__":
    main()
