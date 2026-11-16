# H2 sensor reading (read-only)

Both scripts only **subscribe** to DDS topics. Neither ever publishes or sends a command to the robot.

## After lunch: cable plugged into the robot, robot powered on
```bash
cd ~/dev/unitree/sandbox/sensor_reading

# 1. List every topic, measure its rate, save a sample (~10 s)
python3 discover_topics.py
#    -> output/topics.json, output/topics.txt

# 2. Live view (maximize the terminal, ~150x42). Ctrl-C to quit.
python3 stream_sensors.py

# 3. 60 s recording for review. While it runs: tilt the robot, move an arm by hand.
python3 stream_sensors.py --log --duration 60
#    -> output/sensors_<timestamp>.jsonl  (~20 MB per minute at the default 50 Hz)
```
Then plug the cable back into the lab network. Everything to review is in `output/`.

## If you see "No topics found" / "waiting for data"
- `ip -br addr`: `enp0s31f6` needs a `192.168.123.x` address (the one your SDK2 examples used).
- Is the robot powered on and booted (roughly a minute)?
- Different interface name? Add `--iface <name>` to either script.

## Options
| script | flag | default |
|---|---|---|
| both | `--iface` | `enp0s31f6` |
| both | `--domain` | `0` |
| discover_topics.py | `--discover-secs` / `--sample-secs` | 5 / 3 |
| stream_sensors.py | `--hz` (screen refresh) | 10 |
| stream_sensors.py | `--duration N`, `--log`, `--log-hz` | off, off, 50 |

`stream_sensors.py` always shows `rt/lowstate` and `rt/secondary_imu`. If you've already run `discover_topics.py`, it also shows any BMS, main board, pressure-sensor or hand topics it found.
