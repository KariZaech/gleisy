#!/usr/bin/env python3
"""Build or reuse a cached station page and start the static web server."""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
WEB_ROOT = Path("/usr/share/nginx/html")
DEFAULT_CACHE_DIR = Path("/cache")


def env_flag(name, default="false"):
    value = os.environ.get(name, default).strip().lower()
    if value not in {"true", "false", "1", "0", "yes", "no", "on", "off"}:
        raise SystemExit(f"{name} must be a boolean value, got {value!r}")
    return value in {"true", "1", "yes", "on"}


def safe_slug(value):
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value).strip("_") or "station"


def gtfs_fingerprint(gtfs_path):
    stat = gtfs_path.stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def build_cache_file(cache_dir, station, target_date, all_modes, max_turn, stub, gtfs_path):
    raw_key = "|".join([
        station,
        target_date,
        f"all_modes={int(all_modes)}",
        f"max_turn={max_turn}",
        f"stub={stub}",
        f"gtfs={gtfs_path}",
        f"fp={gtfs_fingerprint(gtfs_path)}",
    ])
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:12]
    filename = f"{safe_slug(station)}_{target_date}_{digest}.html"
    return cache_dir / filename


def main():
    gtfs = Path(os.environ.get("GTFS_FILE", "/data/gtfs.zip"))
    station = os.environ.get("STATION", "").strip()
    if not station:
        raise SystemExit("STATION must be set to an exact GTFS station name")
    if not gtfs.is_file():
        raise SystemExit(f"GTFS file not found: {gtfs}")

    target_date = os.environ.get("DATE", "").strip() or date.today().isoformat()
    max_turn = os.environ.get("MAX_TURN", "45").strip()
    stub = os.environ.get("STUB", "4").strip()
    all_modes = env_flag("ALL_MODES", "false")
    force_rebuild = env_flag("FORCE_REBUILD", "false")

    cache_dir = Path(os.environ.get("CACHE_DIR", str(DEFAULT_CACHE_DIR)))
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_html = build_cache_file(cache_dir, station, target_date, all_modes, max_turn, stub, gtfs)

    if cached_html.is_file() and cached_html.stat().st_size > 0 and not force_rebuild:
        print(f"[cache] Reusing cached HTML: {cached_html}", flush=True)
    else:
        if force_rebuild and cached_html.exists():
            print(f"[cache] FORCE_REBUILD=true, regenerating: {cached_html}", flush=True)
        else:
            print(f"[cache] Building HTML for {station} ({target_date}) -> {cached_html}", flush=True)

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
                target_date,
                "--max-turn",
                max_turn,
                "--stub",
                stub,
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

            tmp_target = cache_dir / f".{cached_html.name}.tmp.{os.getpid()}"
            shutil.copyfile(pages[0], tmp_target)
            os.replace(tmp_target, cached_html)
        finally:
            build_dir.cleanup()

    WEB_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cached_html, WEB_ROOT / "index.html")

    os.execvp("nginx", ["nginx", "-g", "daemon off;"])


if __name__ == "__main__":
    main()