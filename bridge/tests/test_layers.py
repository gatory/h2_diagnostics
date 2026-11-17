"""The package's layers only depend downward:

    layout.py  <-  data/  <-  processing/  <-  output/, views/      (__main__ wires all)

A lower layer importing a higher one is how a codebase turns into a tangle, so
this fails the build when it happens. Reads imports with `ast` (no code is run).
"""
import ast
from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "h2diag"

# layer -> layers it must NOT import
FORBIDDEN = {
    "data": {"processing", "output", "views"},
    "processing": {"output", "views"},
    "output": {"views"},
    "views": {"output"},  # views get a recorder handed in; they don't build outputs
}


def _imported_layers(py):
    """Top-level h2diag subpackages imported by this file (relative or absolute)."""
    parts = py.relative_to(PKG).parts[:-1]  # e.g. ("views",)
    found = set()
    for node in ast.walk(ast.parse(py.read_text())):
        if isinstance(node, ast.ImportFrom):
            if node.level:  # relative: resolve against this file's package
                base = list(parts[: len(parts) - (node.level - 1)])
                mod = base + (node.module.split(".") if node.module else [])
                names = [mod + [a.name] for a in node.names] if not node.module else [mod]
            elif node.module and node.module.startswith("h2diag"):
                names = [node.module.split(".")[1:]]
            else:
                continue
            found |= {n[0] for n in names if n}
        elif isinstance(node, ast.Import):
            found |= {a.name.split(".")[1] for a in node.names
                      if a.name.startswith("h2diag.") and a.name.count(".")}
    return found


def test_layers_only_depend_downward():
    checked = 0
    for layer, banned in FORBIDDEN.items():
        for py in (PKG / layer).rglob("*.py"):
            bad = _imported_layers(py) & banned
            assert not bad, f"{py.relative_to(PKG)} imports {bad}: wrong direction"
            checked += 1
    assert checked >= 15


def test_detects_a_wrong_way_import(tmp_path, monkeypatch):
    # The checker itself must work: a fake data/ module importing processing/.
    fake = tmp_path / "h2diag" / "data"
    fake.mkdir(parents=True)
    (fake / "bad.py").write_text("from ..processing import health\n")
    monkeypatch.setattr(__import__(__name__), "PKG", tmp_path / "h2diag")
    assert _imported_layers(fake / "bad.py") == {"processing"}
