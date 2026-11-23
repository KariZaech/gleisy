#!/usr/bin/env python3
"""
Track occupancy Gantt builder (Swiss GTFS -> static HTML page).

Usage:
    python build.py --gtfs gtfs_fp2026.zip --station "Brig" --date 2026-11-21
    python build.py --gtfs gtfs_fp2026.zip --station "Brig" --date 2026-11-21 --all-modes

Output: out/<station>_<date>.html  (self-contained, double-click to open)

Only the Python standard library is used.
"""
import argparse
import csv
import io
import json
import math
import re
import sys
import time
import zipfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "template.html"

RAIL_ROUTE_TYPES = {2} | set(range(100, 118))  # GTFS basic + extended rail types

# Short codes shown at the bar ends. Extend as you like (exact name match first, then prefix).
ABBREV = {
    "Genève-Aéroport": "GVA", "Genève": "GEN", "Lausanne": "LAS", "Sion": "SIO",
    "Monthey": "MTY", "Monthey-Ville": "MTY", "St-Gingolph (Suisse)": "SGG", "St-Gingolph": "SGG",
    "Basel SBB": "BSL", "Basel Bad Bf": "BSL", "Bern": "BRN", "Romanshorn": "ROM",
    "Zürich HB": "ZRH", "Zürich Flughafen": "ZRH", "Spiez": "SPZ", "Thun": "THU",
    "Domodossola": "DMO", "Domodossola (I)": "DMO", "Milano Centrale": "MIL",
    "Venezia S. Lucia": "VEN", "Frankfurt (Main) Hbf": "FRA", "Visp": "VSP",
    "Zermatt": "ZER", "Fiesch": "FIE", "Andermatt": "AND", "Oberwald": "OBW",
    "St. Moritz": "SMO", "Goppenstein": "GOP", "Iselle di Trasquera": "ISE",
    "Brig": "BRG", "Olten": "OLT", "Luzern": "LZ", "Chur": "CHU",
}


# ---------------------------------------------------------------- helpers
def open_csv(zf, name):
    """Yield dict rows of a GTFS file inside the zip (handles BOM)."""
    if name not in zf.namelist():
        return
    with zf.open(name) as fh:
        reader = csv.DictReader(io.TextIOWrapper(fh, encoding="utf-8-sig", newline=""))
        for row in reader:
            yield row


def gtfs_time_to_min(t):
    if not t:
        return None
    h, m, *_ = t.strip().split(":")
    return int(h) * 60 + int(m)


def haversine_km(a, b):
    (lat1, lon1), (lat2, lon2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def bearing_deg(a, b):
    (lat1, lon1), (lat2, lon2) = a, b
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def abbrev(name):
    if not name:
        return ""
    if name in ABBREV:
        return ABBREV[name]
    for k, v in ABBREV.items():
        if name.startswith(k):
            return v
    word = re.split(r"[ ,(/]", name)[0]
    return word[:10]


def category_and_label(route):
    sn = (route.get("route_short_name") or "").strip()
    desc = (route.get("route_desc") or "").strip()
    if desc and len(desc) <= 5 and re.fullmatch(r"[A-Za-z]+", desc):
        cat = desc.upper()
        if not sn:
            label = cat
        elif sn.upper().startswith(cat):
            label = sn
        else:
            label = cat + sn
    else:
        m = re.match(r"[A-Za-z]+", sn)
        cat = m.group(0).upper() if m else "OTHER"
        label = sn or cat
    return cat, label


def track_of(stop):
    pc = (stop.get("platform_code") or "").strip()
    if not pc:
        sid = stop["stop_id"]
        if ":" in sid:
            pc = sid.rsplit(":", 1)[-1]
    if not pc or pc == "0":
        return "?"
    return pc


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ---------------------------------------------------------------- loading
def load_stops(zf):
    stops = {}
    for r in open_csv(zf, "stops.txt"):
        try:
            lat, lon = float(r["stop_lat"]), float(r["stop_lon"])
        except (ValueError, KeyError):
            lat = lon = None
        stops[r["stop_id"]] = {
            "stop_id": r["stop_id"],
            "name": r.get("stop_name", ""),
            "parent": (r.get("parent_station") or "").strip(),
            "loc_type": (r.get("location_type") or "0").strip() or "0",
            "platform_code": r.get("platform_code", ""),
            "coord": (lat, lon) if lat is not None else None,
        }
    return stops


def find_station(stops, query):
    q = query.strip().lower()
    exact = [s for s in stops.values() if s["name"].lower() == q]
    if not exact:
        cands = sorted({s["name"] for s in stops.values() if q in s["name"].lower()})
        print(f"No exact station named '{query}'. Candidates:")
        for c in cands[:40]:
            print("   ", c)
        sys.exit(1)
    # prefer the parent station
    parents = [s for s in exact if s["loc_type"] == "1"]
    root = parents[0] if parents else exact[0]
    root_id = root["stop_id"] if root["loc_type"] == "1" else (root["parent"] or root["stop_id"])
    # Children via parent_station, or id prefix on the FULL root id.
    # Works for "8501609:0:3" and SLOID ids "ch:1:sloid:1609:0:3".
    key = re.sub(r"^Parent", "", root_id)
    ids = {root_id}
    for s in stops.values():
        sid = s["stop_id"]
        if s["parent"] == root_id or sid == key or sid.startswith(key + ":"):
            ids.add(sid)
    coord = root["coord"] or next((stops[i]["coord"] for i in ids if stops[i]["coord"]), None)
    return {"name": root["name"], "root_id": root_id, "ids": ids, "coord": coord}


def active_services(zf, day):
    ymd = day.strftime("%Y%m%d")
    wd = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][day.weekday()]
    active = set()
    for r in open_csv(zf, "calendar.txt"):
        if r["start_date"] <= ymd <= r["end_date"] and r.get(wd) == "1":
            active.add(r["service_id"])
    for r in open_csv(zf, "calendar_dates.txt"):
        if r["date"] == ymd:
            if r["exception_type"] == "1":
                active.add(r["service_id"])
            elif r["exception_type"] == "2":
                active.discard(r["service_id"])
    return active


def iter_stop_times_raw(zf):
    """Fast line iterator over stop_times.txt -> (cols dict, raw line)."""
    with zf.open("stop_times.txt") as fh:
        text = io.TextIOWrapper(fh, encoding="utf-8-sig", newline="")
        header = next(csv.reader([text.readline()]))
        idx = {h.strip(): i for i, h in enumerate(header)}
        for line in text:
            yield idx, line


def split_line(line):
    if '"' in line:
        return next(csv.reader([line]))
    return line.rstrip("\r\n").split(",")


# ---------------------------------------------------------------- main build
def build(gtfs_path, station_query, day, all_modes, max_turn, stub):
    t0 = time.time()
    zf = zipfile.ZipFile(gtfs_path)

    log("Loading stops ...")
    stops = load_stops(zf)
    st = find_station(stops, station_query)
    log(f"Station: {st['name']} root={st['root_id']} ({len(st['ids'])} stop ids): "
        + ", ".join(sorted(st["ids"])[:12]))
    if len(st["ids"]) > 80:
        log("ERROR: too many stop ids matched for one station - aborting"); sys.exit(1)
    if not st["coord"]:
        log("WARNING: station has no coordinates -> no direction arrows")

    log("Loading routes / calendar / trips ...")
    routes = {r["route_id"]: r for r in open_csv(zf, "routes.txt")}
    services = active_services(zf, day)
    trips = {}
    for r in open_csv(zf, "trips.txt"):
        if r["service_id"] not in services:
            continue
        route = routes.get(r["route_id"], {})
        try:
            rtype = int(route.get("route_type", "2"))
        except ValueError:
            rtype = 2
        if not all_modes and rtype not in RAIL_ROUTE_TYPES:
            continue
        cat, label = category_and_label(route)
        trips[r["trip_id"]] = {
            "no": (r.get("trip_short_name") or "").strip(),
            "headsign": (r.get("trip_headsign") or "").strip(),
            "block": (r.get("block_id") or "").strip(),
            "cat": cat,
            "label": label,
            "rtype": rtype,
        }
    log(f"Active trips on {day}: {len(trips)}")

    # pass 1: which active trips call at the station?
    log("Scanning stop_times.txt (pass 1/2) ...")
    needle = min((re.sub(r"^Parent", "", i) for i in st["ids"]), key=len)  # cheap pre-filter
    hit = set()
    for idx, line in iter_stop_times_raw(zf):
        if needle not in line:
            continue
        cols = split_line(line)
        if cols[idx["stop_id"]] in st["ids"] and cols[idx["trip_id"]] in trips:
            hit.add(cols[idx["trip_id"]])
    log(f"Trips calling at station: {len(hit)}")

    # pass 2: full stop lists of those trips
    log("Scanning stop_times.txt (pass 2/2) ...")
    calls = defaultdict(list)
    for idx, line in iter_stop_times_raw(zf):
        cols = split_line(line)
        tid = cols[idx["trip_id"]]
        if tid in hit:
            calls[tid].append((
                int(cols[idx["stop_sequence"]]),
                cols[idx["stop_id"]],
                gtfs_time_to_min(cols[idx["arrival_time"]]),
                gtfs_time_to_min(cols[idx["departure_time"]]),
            ))

    def stop_name(sid):
        s = stops.get(sid, {})
        if s.get("parent") and s["parent"] in stops:
            return stops[s["parent"]]["name"]
        return s.get("name", sid)

    def direction(seq_stops, here):
        """Bearing to first stop >= 3 km away along seq_stops (fallback: farthest checked)."""
        if not st["coord"]:
            return None
        best = None
        for sid in seq_stops:
            c = stops.get(sid, {}).get("coord")
            if not c:
                continue
            best = c
            if haversine_km(st["coord"], c) >= 3:
                break
        return round(bearing_deg(st["coord"], best)) if best else None

    # build per-trip events at the station
    events = []
    for tid, lst in calls.items():
        lst.sort()
        tr = trips[tid]
        for i, (seq, sid, arr, dep) in enumerate(lst):
            if sid not in st["ids"]:
                continue
            before = [x[1] for x in reversed(lst[:i])]
            after = [x[1] for x in lst[i + 1:]]
            first, last = i == 0, i == len(lst) - 1
            origin = stop_name(lst[0][1])
            dest = stop_name(lst[-1][1])
            ev = {
                "trip": tid, "track": track_of(stops.get(sid, {"stop_id": sid})),
                "cat": tr["cat"], "label": tr["label"], "no": tr["no"], "block": tr["block"],
                "arr": None if first else (arr if arr is not None else dep),
                "dep": None if last else (dep if dep is not None else arr),
                "from": origin, "to": tr["headsign"] or dest,
                "prev": stop_name(before[0]) if before else None,
                "next": stop_name(after[0]) if after else None,
                "brgIn": direction(before, sid) if before else None,
                "brgOut": direction(after, sid) if after else None,
            }
            events.append(ev)
    log(f"Station events: {len(events)}")
    if len(events) > 5000:
        log(f"WARNING: {len(events)} events is unusually high for one station - check station matching")

    bars = pair_events(events, max_turn, stub)
    log(f"Bars: {len(bars)}  (done in {time.time() - t0:.0f}s)")

    tracks = sorted({b["track"] for b in bars},
                    key=lambda t: (0, int(re.match(r"\d+", t).group()), t) if re.match(r"\d+", t) else (1, 0, t))
    return {
        "station": st["name"],
        "date": day.isoformat(),
        "weekday": day.strftime("%A"),
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": Path(gtfs_path).name,
        "tracks": tracks,
        "bars": bars,
    }


def side(ev, kind):
    """Arrival side (kind='in') or departure side (kind='out') of a bar."""
    if kind == "in":
        return {"t": ev["arr"], "no": ev["no"], "label": ev["label"], "name": ev["from"],
                "code": abbrev(ev["from"]), "via": ev["prev"], "brg": ev["brgIn"]}
    return {"t": ev["dep"], "no": ev["no"], "label": ev["label"], "name": ev["to"],
            "code": abbrev(ev["to"]), "via": ev["next"], "brg": ev["brgOut"]}


def pair_events(events, max_turn, stub):
    bars = []
    term = [e for e in events if e["arr"] is not None and e["dep"] is None]
    orig = [e for e in events if e["dep"] is not None and e["arr"] is None]
    thru = [e for e in events if e["arr"] is not None and e["dep"] is not None]

    for e in thru:
        bars.append({"track": e["track"], "cat": e["cat"], "label": e["label"], "pairing": "through",
                     "start": e["arr"], "end": max(e["dep"], e["arr"]),
                     "in": side(e, "in"), "out": side(e, "out")})

    used = set()
    # 1) block_id match (same vehicle per GTFS)
    by_block = defaultdict(list)
    for o in orig:
        if o["block"]:
            by_block[o["block"]].append(o)
    pairs = []
    for t in sorted(term, key=lambda x: x["arr"]):
        if not t["block"]:
            continue
        cands = [o for o in by_block.get(t["block"], []) if id(o) not in used and o["dep"] >= t["arr"]]
        if cands:
            o = min(cands, key=lambda x: x["dep"])
            used.add(id(o)); used.add(id(t))
            pairs.append((t, o, "block"))

    # 2) heuristic: same track, next originating departure, nothing else on the track in between
    occupancy = defaultdict(list)  # track -> list of (start,end) of other events
    for e in events:
        s = e["arr"] if e["arr"] is not None else e["dep"]
        en = e["dep"] if e["dep"] is not None else e["arr"]
        occupancy[e["track"]].append((s, en, id(e)))
    for t in sorted(term, key=lambda x: x["arr"]):
        if id(t) in used or t["track"] == "?":
            continue
        cands = sorted((o for o in orig if id(o) not in used and o["track"] == t["track"]
                        and t["arr"] <= o["dep"] <= t["arr"] + max_turn), key=lambda x: x["dep"])
        for o in cands:
            blocked = any(a < o["dep"] and b > t["arr"] and k not in (id(t), id(o))
                          for a, b, k in occupancy[t["track"]])
            if not blocked:
                used.add(id(o)); used.add(id(t))
                pairs.append((t, o, "turnaround"))
                break

    for t, o, how in pairs:
        bars.append({"track": t["track"], "cat": o["cat"], "label": o["label"], "pairing": how,
                     "inCat": t["cat"], "start": t["arr"], "end": o["dep"],
                     "in": side(t, "in"), "out": side(o, "out")})
    for t in term:
        if id(t) not in used:
            bars.append({"track": t["track"], "cat": t["cat"], "label": t["label"], "pairing": "terminating",
                         "start": t["arr"], "end": t["arr"] + stub, "in": side(t, "in"), "out": None})
    for o in orig:
        if id(o) not in used:
            bars.append({"track": o["track"], "cat": o["cat"], "label": o["label"], "pairing": "originating",
                         "start": o["dep"] - stub, "end": o["dep"], "in": None, "out": side(o, "out")})
    bars.sort(key=lambda b: (b["track"], b["start"]))
    return bars


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gtfs", required=True, help="Path to the Swiss GTFS zip")
    ap.add_argument("--station", required=True, help='Exact station name, e.g. "Brig" or "Bern"')
    ap.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD (default: today)")
    ap.add_argument("--all-modes", action="store_true", help="Include bus/tram/etc. (default: rail only)")
    ap.add_argument("--max-turn", type=int, default=45, help="Max minutes for turnaround pairing (default 45)")
    ap.add_argument("--stub", type=int, default=4, help="Bar length in min for unpaired arrivals/departures")
    ap.add_argument("--out", default=str(HERE / "out"), help="Output folder")
    a = ap.parse_args()

    day = date.fromisoformat(a.date)
    data = build(a.gtfs, a.station, day, a.all_modes, a.max_turn, a.stub)

    out_dir = Path(a.out); out_dir.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9]+", "_", data["station"]).strip("_")
    html = TEMPLATE.read_text(encoding="utf-8").replace(
        "/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
    target = out_dir / f"{safe}_{day.isoformat()}.html"
    target.write_text(html, encoding="utf-8")
    (out_dir / f"{safe}_{day.isoformat()}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Written: {target}")


if __name__ == "__main__":
    main()
