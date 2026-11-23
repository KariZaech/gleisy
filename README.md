# Gleisbelegung – track occupancy Gantt from Swiss GTFS

Static page: one HTML file per station + date. Python standard library only, no install needed.

## 1. Get the GTFS
Download the current timetable zip (~280 MB) from
https://data.opentransportdata.swiss/de/dataset/timetable-2026-gtfs2020
(next year: timetable-2027-gtfs2020). Do not unzip.

## 2. Build a page
```
python build.py --gtfs gtfs_fp2026_20260930.zip --station "Brig" --date 2026-11-21
```
Output: `out/Brig_2026-11-21.html` -> double-click to open (works offline).
Also writes `out/Brig_2026-11-21.json` (same data, for debugging).

Options
| flag | default | meaning |
|---|---|---|
| `--station` | – | exact stop name ("Brig", "Bern", "Visp"). Wrong name -> list of candidates |
| `--date` | today | must lie inside the GTFS timetable year |
| `--all-modes` | off | include bus/tram (default: rail only) |
| `--max-turn` | 45 | max minutes for turnaround pairing |
| `--stub` | 4 | bar length (min) for arrivals/departures without partner |

Runtime: the Swiss `stop_times.txt` is large; expect a few minutes (2 streaming passes).

## 3. Reading the chart
- Row = track (platform_code), split into sub-lanes when trains/labels overlap.
- Left of bar: origin code, arrow, arrival minute. Right: departure minute, arrow, destination code.
- Above bar: category/line + train number(s) (`6203›6208` = turnaround with new number).
- Solid = through train or GTFS block_id link. Dashed = turnaround guessed (same track, next departure, nothing in between). Faint = no partner found.
- Arrows = compass direction from the station to the first stop >= 3 km away along the route. Dropdown switches between "towards origin/destination" and "direction of travel".
- Legend chips toggle categories. Hover a bar for details.

## Customise
- Colours: `COLORS` in `template.html`.
- Station short codes (GVA, BSL, ...): `ABBREV` in `build.py`.
- Test without the real feed: `python test/make_test_gtfs.py` then build with `--gtfs test/test_gtfs.zip`.
