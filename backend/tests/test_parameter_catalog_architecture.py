"""Architecture guards for the parameter catalog.

* the calculation engine and the relay-import domain never read a catalog or any OEM JSON;
* the generic matcher / validator / loader contain no manufacturer- or relay-specific logic;
* the canonical registry is OEM-neutral;
* a catalog can ask only for the named transformation primitives -- no executable code anywhere.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from app.domain.parameter_catalog.loader import CATALOG_ROOT
from app.domain.parameter_catalog.transforms import PRIMITIVES

APP = Path(__file__).resolve().parents[1] / "app"
PACKAGE = APP / "domain" / "parameter_catalog"
OEM_WORDS = re.compile(
    r"p44\d|micom|schneider|areva|alstom|7sa\d|7sl\d|siprotec|siemens|rel[56]\d\d|red670|relion|hitachi|abb\b|toshiba|"
    r"grl2|grz1|lfzp|relz|rcs-?9|nr electric|zmqpdis|zdrdir|rfpp|rfpe",
    re.IGNORECASE,
)


def test_the_calculation_engine_and_relay_import_domain_never_touch_a_catalog():
    sources = [APP / "domain" / "distance_protection.py", APP / "domain" / "impedance.py",
               *sorted((APP / "domain" / "relay_import").glob("*.py"))]
    for path in sources:
        text = path.read_text(encoding="utf-8")
        assert "parameter_catalog" not in text, f"{path.name} must not know about parameter catalogs"
        assert not re.search(r"""open\(|read_text\(|json\.load""", text), f"{path.name} must not read files"


def test_the_engine_adapter_and_apply_consume_only_the_canonical_model():
    for name in ("engine_adapter.py", "apply_settings.py"):
        text = (APP / "domain" / "relay_import" / name).read_text(encoding="utf-8")
        assert "catalog" not in text.lower(), name


def test_the_generic_catalog_code_contains_no_manufacturer_or_relay_names():
    for path in sorted(PACKAGE.glob("*.py")):
        hit = OEM_WORDS.search(path.read_text(encoding="utf-8"))
        assert hit is None, f"{path.name} mentions {hit.group(0)!r}: relay knowledge belongs in a catalog, not in the matcher"


def test_the_parameter_catalog_package_is_pure_domain_code():
    banned = re.compile(r"^\s*(?:from|import)\s+(?:fastapi|pydantic|sqlalchemy|app\.storage|app\.services|app\.api)", re.M)
    for path in sorted(PACKAGE.glob("*.py")):
        assert banned.search(path.read_text(encoding="utf-8")) is None, path.name


def test_no_code_is_ever_executed_from_catalog_data():
    for path in sorted(PACKAGE.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for call in ("eval(", "exec(", "__import__(", "compile(", "importlib", "subprocess", "pickle"):
            assert call not in text.replace("re.compile(", ""), f"{path.name} uses {call}"


def test_the_canonical_registry_is_oem_neutral():
    text = (CATALOG_ROOT / "canonical" / "distance_protection.json").read_text(encoding="utf-8")
    hit = OEM_WORDS.search(text)
    assert hit is None, f"the canonical registry mentions {hit.group(0)!r}"


def test_a_catalogs_only_behaviour_is_a_named_primitive():
    for path in sorted(CATALOG_ROOT.rglob("*.json")):
        if path.parent.name == "canonical" or path.name == "catalog.lock.json":
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for m in data["mappings"]:
            steps = m.get("transform", [])
            for step in steps if isinstance(steps, list) else [steps]:
                assert step["type"] in PRIMITIVES, (path.name, m["id"], step["type"])


def test_every_primitive_is_exercised_by_a_test():
    """A primitive nobody tests is a primitive nobody should be able to use."""
    text = (Path(__file__).parent / "test_parameter_catalog_interpreter.py").read_text(encoding="utf-8")
    for name in PRIMITIVES:
        assert f'"{name}"' in text, f"primitive {name!r} has no interpreter test"
