"""Shared helpers for H2 topic discovery and sensor streaming.

READ-ONLY: nothing in this package creates a DDS writer / ChannelPublisher.
"""
import dataclasses
import importlib
import inspect
import math
import pkgutil
from pathlib import Path

IFACE = "enp0s31f6"
DOMAIN_ID = 0
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

# Index order copied from unitree_sdk2_python/example/h2/low_level/h2_ankle_swing_example.py
# (H2JointIndex). Not imported, because that module creates publishers.
H2_JOINT_NAMES = [
    "L_hip_pitch", "L_hip_roll", "L_hip_yaw", "L_knee", "L_ankle_roll", "L_ankle_pitch",
    "R_hip_pitch", "R_hip_roll", "R_hip_yaw", "R_knee", "R_ankle_roll", "R_ankle_pitch",
    "waist_roll", "waist_pitch", "waist_yaw",
    "L_shoulder_pitch", "L_shoulder_roll", "L_shoulder_yaw", "L_elbow",
    "L_wrist_yaw", "L_wrist_pitch", "L_wrist_roll",
    "R_shoulder_pitch", "R_shoulder_roll", "R_shoulder_yaw", "R_elbow",
    "R_wrist_yaw", "R_wrist_pitch", "R_wrist_roll",
    "head_pitch", "head_yaw",
]
H2_NUM_MOTOR = len(H2_JOINT_NAMES)  # 31


def normalize_type_name(name: str) -> str:
    """'unitree_hg::msg::dds_::LowState_' -> 'unitree_hg.msg.dds_.LowState_'"""
    return name.replace("::", ".")


def _build_type_registry():
    """Map DDS type name -> IDL Python class for every message in unitree_sdk2py.idl."""
    from cyclonedds.idl import IdlStruct
    import unitree_sdk2py.idl as idl_pkg

    registry = {}
    for mod_info in pkgutil.walk_packages(idl_pkg.__path__, idl_pkg.__name__ + "."):
        try:
            mod = importlib.import_module(mod_info.name)
        except Exception:
            continue
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, IdlStruct) and obj is not IdlStruct:
                tn = getattr(obj, "__idl_typename__", None)
                if tn:
                    registry[normalize_type_name(tn)] = obj
    return registry


_REGISTRY = None


def type_registry():
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_type_registry()
    return _REGISTRY


def lookup_type(dds_type_name: str):
    return type_registry().get(normalize_type_name(dds_type_name))


def to_dict(obj):
    """Convert an IDL message into JSON-safe python data."""
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


def init_dds(domain_id: int = DOMAIN_ID, iface: str = IFACE):
    """Initialise the unitree_sdk2py channel factory on a given interface."""
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize

    ChannelFactoryInitialize(domain_id, iface)
