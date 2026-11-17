# Retiring `examples/sensor_reading_example/`

Every feature of the example scripts, where it lives in the bridge now, and how it
was or will be checked. **Delete `examples/` only once every "on the Thor" box is
ticked.** Commands assume `cd ~/dev/h2_diagnostics/bridge && source ../.venv/bin/activate`.

✅ = verified offline on the workstation (tests or a run). ☐ = needs the robot.

## `stream_sensors.py` → `h2diag live` / `record` / `replay`

| Example feature | Bridge | Offline | On the Thor |
|---|---|---|---|
| Live full-screen view (topic health, both IMUs, joints, battery, board, hands) | `python -m h2diag live --iface eth10` | ✅ `test_view.py` renders it from the sample recording | ☐ run it; every topic shows `ok` |
| Clear "is this live?" marking | red `● LIVE` banner + red border | ✅ `test_live_screen_says_live` | ☐ see it |
| "waiting for data: check cable/iface" hint | red line after 3 s with no messages | ✅ `test_live_banner_shows_recording_and_no_data_hint` | ☐ run with a wrong `--iface` (e.g. `lo`): hint appears |
| `--log --duration 60`: record while viewing | `live --record NAME` (note + Enter = marker); or `record --live --name NAME --seconds 60` without the screen | ✅ `test_run_records_while_viewing` | ☐ `live --record m1`, type a note + Enter, Ctrl-C; then `replay 1` shows it and the marker |
| Summary table after quitting (msgs, avg Hz) | printed after `live` / `replay` exit | ✅ same test | ☐ see it after Ctrl-C |
| "No data received" message after quitting | printed if nothing arrived | (simple branch) | ☐ with a wrong `--iface` |
| `--hz` screen refresh | fixed 10 Hz (`REFRESH_HZ` in `views/sensors.py`) | — | — |
| Extra topics picked up from `topics.json` | **not carried over on purpose:** the bridge shows only confirmed H2 topics (CLAUDE.md ground rule 4); use `h2diag topics` to see everything | — | — |
| Showed `rt/lowstate` (1 kHz) | shows `rt/lf/lowstate` (20 Hz, same type); `replay` of old recordings still reads `rt/lowstate` | ✅ | — |
| Recording format (`.jsonl`, meta line, `t`/`topic`/`data`) | unchanged: old recordings replay as-is | ✅ `test_record_then_replay_roundtrip` | — |

## `discover_topics.py` → `h2diag topics`

| Example feature | Bridge | Offline | On the Thor |
|---|---|---|---|
| Find every published topic (builtin DDS reader) | `python -m h2diag topics --iface eth10` (`data/probe.py: discover_publications`, code unchanged) | — needs DDS | ☐ about 120 topics listed, like 2026-11-13 |
| Rate + one decoded sample per topic | `sample_topics` + `summarize_discovery` | ✅ `test_discovery_summary_matches_example_format` | ☐ `rt/lowstate` ≈ 1050 Hz, hands 100 Hz |
| `--discover-secs`, `--sample-secs`, `--no-samples` | same flags | ✅ (`--help`) | — |
| Saves `topics.json` + `topics.txt` | `results/discovery/topics_<stamp>.json/.txt` (gitignored; not overwritten) | ✅ `test_topics_text_reproduces_the_examples_saved_output`: the 2026-11-13 JSON turns into the identical `topics.txt` | ☐ files appear |
| "No topics found" hint | same, exit code 1 | — | ☐ wrong `--iface` |
| — (new) | `topics --show FILE` views a saved discovery offline | ✅ `test_topics_show_and_rates_validation` | — |

## `rate_probe.py` → `h2diag rates`

| Example feature | Bridge | Offline | On the Thor |
|---|---|---|---|
| Sets `bridge`, `lowstate`, `all_fast`; `--topics`; `--secs` | `python -m h2diag rates --iface eth10 --set bridge` | ✅ `test_rate_sets_only_use_known_topics` | ☐ `--set bridge` ≈ 280 msg/s total, `--set lowstate` ≈ 1052 Hz |
| Hz, mean gap, max gap, total msg/s | `summarize_rates` + `views/tables.py` | ✅ `test_rate_summary_hz_gaps_and_total` | ☐ `--set all_fast`: max gaps up to ~22 ms, as on 2026-11-16 |
| 1 s settle before counting | kept | — | — |
| **`rt/lowcmd` in `all_fast`** | **left out (decision needed):** its type name is a command type, which the read-only guard (`test_bridge_never_writes_to_robot`) forbids anywhere in the package. Subscribing only *reads*, so it's safe, but loosening a safety check is your call. | — | ☐ decide: allow reading command types in `data/probe.py` only, or leave it out |

## `common.py` → `h2diag/data/`

| Example feature | Bridge |
|---|---|
| `init_dds` | `data/dds.py: init` |
| Type registry, `lookup_type`, `normalize_type_name` | `data/dds.py` (unchanged code) |
| `to_dict` | `data/convert.py` |
| `H2_JOINT_NAMES` | **dropped on purpose:** it was the scrambled `ankle_swing` order. The bridge uses `layout.BODY_JOINTS` (matches Unitree's H2 joint table). |
| `IFACE = "enp0s31f6"` (workstation) | `--iface` default is `eth10` (Thor) |

## `output/` and README

| Item | Now |
|---|---|
| `sensors_20261112_150110.jsonl` | `bridge/tests/data/` (tests + `replay` list) ✅ |
| `topics.json` / `topics.txt` | `bridge/tests/data/topics_20261113.*` ✅ |
| `sensors_20261112_131912.jsonl` | deleted (it was empty: header only) ✅ |
| README "No data?" troubleshooting | `bridge/README.md` → "No data?" ✅ |

## When everything is ticked

```bash
git rm -r examples/
```
Then remove the `common.py` mentions from `docs/field_map.md` and `CLAUDE.md`.
