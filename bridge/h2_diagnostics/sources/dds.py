"""The gateway to DDS: the ONLY module that imports unitree_sdk2py or cyclonedds.

Everything else (LiveSource, the probes) goes through these functions, so:
  - read-only is guaranteed here: there is a way to subscribe, and none to publish
  - an SDK change, or a swap to another DDS stack, touches one file
  - tests can replace these functions with fakes and run LiveSource without a robot
tests/test_layers.py checks that no other module imports the SDK.

The SDK is imported inside each function (lazily), so replay and the tests run on
machines without unitree_sdk2py/CycloneDDS installed.
"""
import importlib
import inspect
import logging
import pkgutil
import time

log = logging.getLogger("h2_diagnostics.dds")

HG_MODULE = "unitree_sdk2py.idl.unitree_hg.msg.dds_"


def init(domain_id, iface):
    """Initialise the unitree_sdk2py channel factory on one network interface."""
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize

    ChannelFactoryInitialize(domain_id, iface)


# ------------------------------------------------------------------ subscribing

class Subscription:
    """One read-only subscription: calls on_message(msg) on a DDS thread for every
    message on `topic`, already decoded into an instance of `msg_type`."""

    def __init__(self, topic, msg_type, on_message):
        from unitree_sdk2py.core.channel import ChannelSubscriber

        self.topic = topic
        self._sub = ChannelSubscriber(topic, msg_type)
        self._sub.Init(on_message, 0)

    def close(self):
        """Stop receiving. Safe to call more than once; never raises."""
        sub, self._sub = self._sub, None
        if sub is not None:
            try:
                sub.Close()
            except Exception as e:
                log.warning("Closing %s subscription: %s", self.topic, e)


def subscribe(topic, msg_type, on_message):
    """Start receiving `topic`. Returns a Subscription; call .close() when done."""
    return Subscription(topic, msg_type, on_message)


def close_all(subs):
    for sub in subs:
        sub.close()


# ------------------------------------------------------------------ message types

def hg_type(name):
    """IDL class for an H2 (unitree_hg) message by short name: 'LowState_' -> LowState_."""
    return getattr(importlib.import_module(HG_MODULE), name)


def normalize_type_name(name):
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
        except Exception as e:
            log.warning("Type registry: skipping %s (import failed: %s)", mod_info.name, e)
            continue
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if issubclass(obj, IdlStruct) and obj is not IdlStruct:
                tn = getattr(obj, "__idl_typename__", None)
                if tn:
                    registry[normalize_type_name(tn)] = obj
    return registry


_REGISTRY = None


def type_registry():
    """Built once on first use (walks every SDK message module, ~1 s)."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_type_registry()
    return _REGISTRY


def lookup_type(dds_type_name):
    """IDL class for a DDS type name, or None if the SDK doesn't define it."""
    return type_registry().get(normalize_type_name(dds_type_name))


# ------------------------------------------------------------------ discovery

def discover_publications(domain_id, secs):
    """Listen for publishers. Returns {topic: {"type", "writers": set, "participants": set}}.

    Uses DDS's built-in publication topic (a read-only reader), not the SDK channels.

    Call init() first: this DomainParticipant names no interface, so it joins the
    Domain that init() configured (e.g. eth10). Without init(), CycloneDDS picks an
    interface itself, possibly the wrong one, and finds nothing.
    """
    from cyclonedds.builtin import BuiltinDataReader, BuiltinTopicDcpsPublication
    from cyclonedds.domain import DomainParticipant

    dp = DomainParticipant(domain_id)
    reader = BuiltinDataReader(dp, BuiltinTopicDcpsPublication)
    topics = {}
    deadline = time.monotonic() + secs
    while time.monotonic() < deadline:
        for ep in reader.take(N=256):
            name = getattr(ep, "topic_name", None)
            if not name:
                continue
            entry = topics.setdefault(
                name, {"type": ep.type_name, "writers": set(), "participants": set()})
            entry["writers"].add(str(ep.key))
            entry["participants"].add(str(ep.participant_key))
        time.sleep(0.1)
    return topics
