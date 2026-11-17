"""Both message sources implement the same Source interface (sources/base.py)."""
import pytest

from h2_diagnostics.sources import LiveSource, ReplaySource, Source


def test_both_sources_are_sources(recording):
    assert issubclass(LiveSource, Source)
    assert isinstance(ReplaySource(recording), Source)
    assert LiveSource("lo").live is True  # constructing doesn't touch DDS; start() does


def test_source_is_abstract():
    with pytest.raises(TypeError):
        Source()

    class Incomplete(Source):  # forgot poll()
        def now(self):
            return 0.0

    with pytest.raises(TypeError):
        Incomplete()
