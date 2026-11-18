"""② PROCESSING: turning raw messages into meaning.

May import sources/; must not import output/ or views/ (tests/test_layers.py checks).

    state.py      RobotState      newest message per role -> normalized snapshot dict
    health.py     HealthMonitor   snapshot -> warnings, with hysteresis memory
                  evaluate()      the same rules, stateless (used by the unit tests)
    pipeline.py   H2Diagnostics   tick(): source -> state -> health (+ recorder)
    preflight.py  run()           watch N seconds of ticks -> PASS / WARN / FAIL report
"""
