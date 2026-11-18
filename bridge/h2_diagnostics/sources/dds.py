import importlib
import inspect
import pkgutil


def init(domain_id, iface):
    """Initialise the unitree_sdk2py channel factory on one network interface."""
    from unitree_sdk2py.core.channel import ChannelFactoryInitialize

    ChannelFactoryInitialize(domain_id, iface)


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
    """Built once on first use (walks every SDK message module, ~1 s)."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_type_registry()
    return _REGISTRY


def lookup_type(dds_type_name):
    """IDL class for a DDS type name, or None if the SDK doesn't define it."""
    return type_registry().get(normalize_type_name(dds_type_name))
