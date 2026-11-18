The project works like an assembly line. Each level takes the output of the level below it and adds one kind of meaning. I'll go from the ground up, following one message from the robot all 
the way to your screen.                                                                                                                                                                       

---

Level 0: layout.py, the facts about the robot

What it is: constants only, no logic, no imports. Think of it as a static config class.

It answers "what is this robot?":
- BODY_JOINTS: slot 12 is waist_yaw, slot 18 is L_elbow, and so on (31 joints)
- JOINT_LIMITS: the min and max angle for each joint
- LIVE_TOPICS: which DDS topics to subscribe to, and how often each should arrive (rt/lf/lowstate should arrive at 20 Hz)
- ROLES: maps a job ("body", "battery", "hand_left") to the topics that can fill it

Why it's at the bottom: every other file needs these facts, and they don't need anything. When a robot test teaches you something new (as T1 did), this is usually the one file you edit.

---

Level 1: sources/, where messages come from

The interface: Source (sources/base.py). Every source promises to provide:

┌────────────┬───────────────────────────────────────────────────────────────┐
│   Member   │                            Meaning                            │
├────────────┼───────────────────────────────────────────────────────────────┤
│ poll(dt)   │ "Give me any new messages": returns [(topic, data_dict), ...] │
├────────────┼───────────────────────────────────────────────────────────────┤
│ now()      │ the source's clock                                            │
├────────────┼───────────────────────────────────────────────────────────────┤
│ stats      │ {topic: TopicStats}: counts, rates and age, per topic         │
├────────────┼───────────────────────────────────────────────────────────────┤
│ live, done │ is this the real robot? has a recording run out?              │
└────────────┴───────────────────────────────────────────────────────────────┘

Two implementations:
- LiveSource (live.py) subscribes to DDS on the Thor.
  - DDS calls its handler on a background thread for every message. The handler does almost nothing: it counts the arrival (stats.hit()) and keeps only the newest message.
  - Decoding into a dict happens later, in poll() on the main thread. That's because Python decoding is the slow part.
- ReplaySource (replay.py) reads a .jsonl recording and plays it back on a virtual clock. Each poll(dt) moves the clock forward by dt and returns the records whose time has come.

This is the most important design decision in the project. Everything above this level only ever calls source.poll(). It never knows whether a robot or a file is on the other end. That's how
ground rule 2 ("replay first") works: you develop on the workstation with a recording, and on the Thor you swap in LiveSource. In OOP terms it's polymorphism through an interface.

Helpers at this level:
- TopicStats: arrival counter, thread-safe because DDS threads call it
- convert.py: to_dict() (DDS message → plain dict) and num() (safe rounding)
- sessions.py: lists recordings on disk
- probe.py and dds.py: the topics and rates discovery tools

After level 1 you have raw dicts per topic, with field names straight from Unitree, such as motor_state[12]["temperature"].

---

Level 2: processing/, turning raw data into meaning

There are three classes, each with one job, plus a coordinator.

RobotState (state.py) is memory plus translation.
- ingest(topic, data) uses layout.TOPIC_ROLE to decide which job the message fills ("body", "battery"…) and keeps the newest one per role.
- snapshot() turns those raw dicts into the snapshot: one clean dict with named joints ("name": "waist_yaw"), sensible units (volts, not millivolts), and topic stats.
- The snapshot is the central data structure of the project. Ground rule 3, "one pipeline", means everything downstream reads this same dict.

HealthMonitor (health.py) is judgment.
- It reads a snapshot and returns warnings, for example {"id": "temp:waist_yaw", "level": "warn", "msg": "waist_yaw at 71 °C"}.
- It compares values against LIMITS. Those limits are provisional guesses for now.
- It remembers last tick's levels for hysteresis: once a warning switches on at 70 °C, it stays on until the value drops below 67 °C, so it doesn't flicker on and off at 69.9/70.1.
- That memory is why it's a class. The rules themselves are a stateless function, evaluate(), which the unit tests call directly.

H2Diagnostics (pipeline.py) is the coordinator. It owns one source, state, health monitor and optional recorder, and runs them in order:

def tick(self, dt):
    for topic, data in self.source.poll(dt):     # level 1: get messages
        self.state.ingest(topic, data)           # level 2: remember them
        if self.recorder: self.recorder.write(topic, data)   # level 3: save them
    snap = self.state.snapshot(...)              # level 2: build meaning
    snap["warnings"] = self.health.evaluate(snap, ...)   # level 2: judge it
    return snap

That one method is the heartbeat of the whole project. Something above calls it about 50 times a second.

preflight.py is a short consumer of the pipeline: it calls tick() for 10 seconds, collects the worst warnings it saw, and returns PASS, WARN or FAIL.

Notice how the pipeline gets its parts. It creates RobotState and HealthMonitor itself, but is handed the source and the recorder (dependency injection). That's what lets the same pipeline
run live, on a replay, or in a test.

---

Level 3: output/ and views/, the places a snapshot can go

These are siblings. Neither imports the other; both just consume snapshots.

output/, data leaving the process:
- Recorder (recorder.py) writes .jsonl files: a meta header line, one line per message, and marker lines for your notes. ReplaySource reads that same format back, which closes the loop between levels 1 and 3. Today's recording becomes tomorrow's replay source.
- server.py runs the WebSocket server on :8765.
  - It calls bridge.tick() at 50 Hz and broadcasts every second snapshot (25 Hz) to the dashboard.
  - The dashboard can send back only recorder commands (record_start, record_stop, marker). Nothing is ever sent to the robot (ground rule 1).

views/, the terminal screens:
- sensors.py is the full-screen live/replay view. It runs its own tick loop and redraws the snapshot with rich.
- report.py turns a preflight result into text; tables.py draws the session, topic and rate tables.

---

Level 4: __main__.py, the wiring

This is where all the objects get built and connected. Each subcommand is a different combination of the same parts:

┌──────────────────────┬──────────────┬─────────────────────────────────┐
│       Command        │    Source    │             Output              │
├──────────────────────┼──────────────┼─────────────────────────────────┤
│ live                 │ LiveSource   │ pipeline → terminal view        │
├──────────────────────┼──────────────┼─────────────────────────────────┤
│ replay 1             │ ReplaySource │ pipeline → terminal view        │
├──────────────────────┼──────────────┼─────────────────────────────────┤
│ record --live        │ LiveSource   │ pipeline with Recorder attached │
├──────────────────────┼──────────────┼─────────────────────────────────┤
│ serve --live         │ LiveSource   │ pipeline → WebSocket            │
├──────────────────────┼──────────────┼─────────────────────────────────┤
│ preflight --replay F │ ReplaySource │ pipeline → preflight report     │
└──────────────────────┴──────────────┴─────────────────────────────────┘

For example, _source(args) is the whole decision about whether this run uses the robot or a file:

if args.live:
    return LiveSource(args.iface, args.domain).start()
return ReplaySource(args.replay, ...)

---

One message, start to finish

Say waist_yaw heats up to 71 °C while you're running serve --live:

1. Robot → DDS: a LowState_ message arrives on rt/lf/lowstate. LiveSource's handler counts it and keeps it as the newest. (level 1)
2. Tick: server.py calls bridge.tick(0.02), which calls source.poll(), which decodes the message into a dict. (levels 3 → 2 → 1)
3. RobotState.ingest looks up "rt/lf/lowstate" in layout (role "body") and stores it. (levels 2 → 0)
4. snapshot() uses layout.BODY_JOINTS to label slot 12 as "waist_yaw" with temp: [71, 66]. (levels 2 → 0)
5. HealthMonitor compares 71 against LIMITS["body_temp"] = (70, 85) and adds a warning. (level 2)
6. server.py turns the snapshot into JSON and sends it over Wi-Fi to the dashboard. (level 3)

The rule that holds it together

Imports only point down: layout ← sources ← processing ← output, views ← __main__. tests/test_layers.py fails if anything points up. In practice:
- You can change how warnings are shown without touching how they're computed.
- You can change where data comes from without touching anything above it.
- You can test level 2 with a fake source and no robot. Most of the tests do exactly that, using the 2026-11-12 recording.

If you want, I can turn this into a diagram page you can keep open while you read the code.