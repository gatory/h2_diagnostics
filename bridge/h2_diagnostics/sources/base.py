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

    keep_all: the pipeline sets this True while recording. Then poll() returns every
    message, in arrival order, instead of only the newest per topic. Off by default
    because the live view only needs the newest, and converting every message costs CPU.
    """

    live: bool
    done: bool = False
    topics: list[str]
    stats: dict[str, TopicStats]
    keep_all: bool = False

    def start(self) -> "Source":
        """Begin receiving. Returns self so you can write `src = LiveSource(...).start()`."""
        return self

    @abstractmethod
    def now(self) -> float:
        """This source's clock in seconds (monotonic; virtual for replay)."""

    @abstractmethod
    def poll(self, dt: float) -> list[tuple[str, dict, float]]:
        """Advance by dt seconds; return [(topic, data, t)] in arrival order.

        t is when the message arrived, on this source's clock (comparable to now()).
        Newest message per topic, or every message while keep_all is True."""

    def close(self) -> None:
        """Release resources. Safe to call more than once."""
