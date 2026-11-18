"""Source: the interface every message source implements (the robot or a recording).

The rest of the bridge only ever talks to a Source, so it can't tell (and doesn't
care) whether messages come from DDS or from a .jsonl file. That's what makes
"replay first" work: swap LiveSource for ReplaySource and nothing else changes.
"""
from abc import ABC, abstractmethod

from .stats import TopicStats


class Source(ABC):
    """Base class for LiveSource and ReplaySource.

    Attributes every subclass sets:
        live    True for the robot, False for a recording
        done    True once there is nothing more to read (a finished replay)
        topics  topic names this source can deliver
        stats   {topic: TopicStats}, updated as messages arrive
    """

    live: bool
    done: bool = False
    topics: list[str]
    stats: dict[str, TopicStats]

    def start(self) -> "Source":
        """Begin receiving. Returns self so you can write `src = LiveSource(...).start()`."""
        return self

    @abstractmethod
    def now(self) -> float:
        """This source's clock in seconds (monotonic; virtual for replay)."""

    @abstractmethod
    def poll(self, dt: float) -> list[tuple[str, dict]]:
        """Advance by dt seconds; return [(topic, data)], newest message per topic."""

    def close(self) -> None:
        """Release resources. Safe to call more than once."""
