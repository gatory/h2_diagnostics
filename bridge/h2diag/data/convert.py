"""Turning decoded DDS messages into plain, JSON-safe Python data."""
import dataclasses
import math


def to_dict(obj):
    """Convert a decoded IDL message into JSON-safe python data."""
    if dataclasses.is_dataclass(obj):
        return {f.name: to_dict(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, (list, tuple)):
        return [to_dict(x) for x in obj]
    if isinstance(obj, (bytes, bytearray)):
        return list(obj)
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if hasattr(obj, "tolist"):  # numpy
        return obj.tolist()
    return obj


def num(x, nd=4):
    """JSON-safe rounded float; None for NaN/inf/missing."""
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if math.isfinite(x) else None
