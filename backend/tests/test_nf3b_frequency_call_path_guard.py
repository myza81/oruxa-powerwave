"""NF-3B -- the nominal-frequency consumer call-path guard (extends the NF-1 reader tripwire).

The NF-1 tripwire (`test_nf1_nominal_frequency_authority.py::TestNoConsumerChange`) counts one pattern, `x.metadata.nominal_frequency`.
NF-3A showed that is not enough: a frequency reaches an engineering result through carried copies (`candidate.nominal_frequency`),
dictionary keys (`parameters["nominal_frequency_hz"]`), calculated-channel inheritance, default arguments and literal 50 Hz
windows, and through the frontend. This guard freezes ALL of those as an explicit inventory, so a new or forgotten call path fails
a test instead of quietly computing with the wrong frequency.

How to read and maintain it. Every table below is an exact inventory (the test fails on any difference, in either direction), and
every entry carries the NF-3A consumer id it belongs to:

* `K` unrelated to a recording's nominal frequency (a constant that happens to equal 50 or 60);
* `D` a different, justified authority (importer producing the imported value, the authority itself, the one sanctioned default);
* `M` still has to be migrated onto `app.services.nominal_frequency_access` (the NF-3C..NF-3H slices). A migrating slice REMOVES
  its entries here in the same commit; nothing is ever added to an `M` row to make a test pass.

A new entry needs a reviewed reason in the commit message. In NF-3B no consumer is changed, so every table equals the NF-3A
inventory exactly.
"""

from __future__ import annotations

import ast
import re
import textwrap
from collections import Counter
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
APP_DIR = BACKEND / "app"
FRONTEND_INDEX = BACKEND.parent / "frontend" / "index.html"

# --------------------------------------------------------------------------------------------------- the inventories
#: G1. Every `<anything>.nominal_frequency` attribute READ (the imported value or a carried copy of it).
ATTRIBUTE_READS = {
    "schemas/source.py": 1,                                  # D  the source summary echoes the imported value (original metadata)
    # NF-3C migrated C-05 (compliance_measurement_service) and C-04 (compliance_readiness_service): both rows removed.
    "services/import_service.py": 1,                         # D  C-18 importer: provider metadata -> SourceMetadata
    "services/nominal_frequency_service.py": 1,              # D  the authority reads the immutable imported value
    # NF-3C migrated C-06 (oscillation_representation_service): row removed.
    # NF-3D migrated C-01 (phasor_analysis_service) and C-02 (overcurrent_analysis_service): both rows removed.
    "services/preparation_conversion_service.py": 1,         # D  C-18 CSV/Excel importer
    "services/synchronization_service.py": 1,                # D  C-03 migrated in NF-3C; the one read left echoes the DECLARED value for an unusable recording (O-7 option A)
}

#: G2. Every string constant naming a frequency field (dictionary keys, `parameters[...]`, `.get(...)`): the wire/storage names.
FREQUENCY_KEYS = {
    ("domain/oscillation_classification.py", "nominal_frequency_hz"): 3,       # M  C-08 NF-3G
    ("providers/ben/provider.py", "nominal_frequency_hz"): 1,                  # D  C-18 BEN upload value
    ("services/calculated_channel_service.py", "nominal_frequency_hz"): 4,     # D/M C-14 (RMS parameter), C-13 (power: NF-3F)
    ("services/calculated_channel_staleness.py", "nominal_frequency_hz"): 1,   # K  NF-3E: reads the STORED parameter to compare it with the accessor
    ("services/compliance_readiness_service.py", "nominal_frequency_hz"): 2,   # M  C-04 NF-3C
    ("services/oscillation_cross_signal_service.py", "nominal_frequency_hz"): 2,  # M  C-07 NF-3C
    ("services/oscillation_representation_service.py", "nominal_frequency_hz"): 1,  # M  C-06 NF-3C
    ("services/oscillation_spectrum_service.py", "nominal_frequency_hz"): 1,   # M  C-07 NF-3C
    ("services/phasor_analysis_service.py", "reference_frequency_hz"): 1,      # D  the caller-supplied override parameter name (NF-3D)
}

#: G3. Every numeric literal equal to 50, 60 or 0.02 (a hard-coded fundamental or window length would be one of these).
#: value = (count, class, note)
NUMERIC_LITERALS = {
    "domain/auto_base_evidence.py": (2, "K", "0.02 kV tolerance; 60 kV in a standard-voltage table"),
    "domain/calculated_channel.py": (2, "M", "C-12 default nominal_frequency_hz=50.0 of the two power kernels (NF-3F, removed in NF-3H)"),
    "domain/damping_estimation.py": (1, "K", "0.02 envelope floor fraction"),
    "domain/event_reconstruction.py": (1, "K", "annotation box offset"),
    "domain/metadata.py": (1, "D", "DEFAULT_NOMINAL_FREQUENCY_HZ: the one sanctioned default, used by the NF-1 resolver"),
    "domain/oscillation_classification.py": (1, "M", "C-08 ASSUMED_NOMINAL_FREQUENCY_HZ (NF-3G)"),
    "domain/overcurrent.py": (1, "K", "IEC IDMT alpha = 0.02"),
    "domain/relay_import/identification.py": (2, "K", "score thresholds"),
    "domain/sliding_phasor.py": (1, "M", "C-16 default reference_frequency_hz=50.0 (NF-3H)"),
    "domain/waveform_evidence.py": (1, "M", "C-16/C-17 default nominal_frequency_hz=50.0 (NF-3H; Auto Base evidence deferred, O-3)"),
    "providers/ben/layout.py": (1, "K", "byte offset 0x3C"),
    "providers/ben/legacy_ben5k/gpth_slow.py": (3, "K", "60-byte frame length"),
    "providers/comtrade.py": (1, "D", "C-18 importer default when `lf` is unparseable (flagged nominal_frequency_assumed)"),
    "services/calculated_channel_service.py": (6, "M", "C-11 gates (4), C-13 stored parameter (2) of the power channels (NF-3F)"),
    "services/time_axis_interpreters.py": (4, "K", "minutes/seconds arithmetic"),
    "services/time_axis_normalization.py": (3, "K", "minutes/seconds arithmetic"),
    "services/time_axis_service.py": (1, "K", "time-axis sample limit"),
}

#: G4. Default VALUES of frequency-named parameters: a caller that omits the argument silently gets this frequency.
FREQUENCY_DEFAULTS = {
    ("domain/calculated_channel.py", "evaluate_power_channel", "nominal_frequency_hz", 50.0),                 # M C-12 NF-3F
    ("domain/calculated_channel.py", "evaluate_three_phase_power_channel", "nominal_frequency_hz", 50.0),     # M C-12 NF-3F
    ("domain/sliding_phasor.py", "compute_sliding_phasor", "reference_frequency_hz", 50.0),                   # M C-16 NF-3H
    ("domain/waveform_evidence.py", "extract_waveform_evidence", "nominal_frequency_hz", 50.0),               # M C-16 NF-3H / O-3
}

#: G5. Who may import which module. The NF-1 service layer owns the gate, so only the accessor imports it; in NF-3B only the
#: application factory and the NF-1 router import the accessor (no engineering consumer yet).
SERVICE_IMPORTERS = {"services/nominal_frequency_access.py"}
#: NF-3C: the migrated consumers (and the router dependency that hands the synchronization service its accessor) join the importers. Each later slice
#: adds ITS files here, in the same commit that migrates them.
ACCESS_IMPORTERS = {
    "main.py", "api/v1/nominal_frequency.py", "api/v1/synchronization.py",
    "services/compliance_measurement_service.py", "services/compliance_readiness_service.py", "services/synchronization_service.py",
    # C-06 / C-07: the oscillation chain passes the accessor down to the one representation that reads the frequency
    "api/v1/oscillation.py", "services/oscillation_representation_service.py", "services/oscillation_spectrum_service.py",
    "services/oscillation_spectrogram_service.py", "services/oscillation_damping_service.py", "services/oscillation_cross_signal_service.py",
    "services/oscillation_interpretation_service.py", "services/oscillation_mode_shape_service.py", "services/oscillation_coherence_service.py",
    # NF-3D: C-01 / C-02 (phasor, overcurrent) read through the accessor; the shared decision function and the services and routers that pass the
    # accessor down to them (impedance, distance, sequence, line-to-line) import it for the type only.
    "services/analysis_reference_frequency.py", "services/phasor_analysis_service.py", "services/overcurrent_analysis_service.py",
    "services/impedance_analysis_service.py", "services/distance_protection_analysis_service.py", "services/sequence_components_analysis_service.py",
    "services/line_to_line_voltage_service.py", "api/v1/engineering_contexts.py", "api/v1/calculated_channels.py",
    # NF-3E: derived staleness compares a stored RMS frequency with the accessor's answer (the only reader of the effective frequency there);
    # the creation service takes the accessor to stamp provenance, verify a recording-following frequency and refuse stale inputs.
    "services/calculated_channel_staleness.py", "services/calculated_channel_service.py",
}
#: Files that may mention the registry at all; of these only the service layer may READ it (lifecycle removal is the rest).
REGISTRY_USERS = {
    "api/v1/sources.py", "api/v1/workspaces.py", "main.py", "services/nominal_frequency_access.py",
    "services/nominal_frequency_service.py",
}
REGISTRY_READ_METHODS = {"get", "snapshot", "revision", "set", "clear", "count"}

#: G6. The frontend (`frontend/index.html`): exact occurrence counts of every frequency token. NF-3A C-22..C-24 and the NF-2 block.
FRONTEND_TOKENS = {
    "nominal_frequency_hz": 9,
    "nominal_frequency(bare)": 11,   # NF-3E: +1 (`nominal_frequency_basis` in the RMS create payload)
    "nominalFrequency": 53,          # NF-3C: +2 (the dormant facts card takes an optional `nominalFrequencyInfo`); NF-3E: +20 (O-8 builder authority)
    "reference_frequency": 2,
    "nominalFrequencyOverride": 2,
}
_FRONTEND_PATTERNS = {
    "nominal_frequency_hz": r"nominal_frequency_hz",
    "nominal_frequency(bare)": r"nominal_frequency(?!_hz|_assumed)",
    "nominalFrequency": r"nominalFrequency",
    "reference_frequency": r"reference_frequency",
    "nominalFrequencyOverride": r"nominalFrequencyOverride",
}

_FREQUENCY_STRINGS = {"nominal_frequency", "nominal_frequency_hz", "reference_frequency_hz"}
_NUMERIC = {50, 60, 0.02}


# ------------------------------------------------------------------------------------------------------ the scanner
def _files(app_dir: Path):
    for path in sorted(app_dir.rglob("*.py")):
        yield path.relative_to(app_dir).as_posix(), ast.parse(path.read_text(encoding="utf-8"))


def scan_attribute_reads(app_dir: Path) -> dict[str, int]:
    out: Counter = Counter()
    for rel, tree in _files(app_dir):
        out[rel] += sum(1 for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "nominal_frequency" and isinstance(n.ctx, ast.Load))
    return {k: v for k, v in out.items() if v}


def scan_frequency_keys(app_dir: Path) -> dict[tuple[str, str], int]:
    out: Counter = Counter()
    for rel, tree in _files(app_dir):
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in _FREQUENCY_STRINGS:
                out[(rel, n.value)] += 1
    return dict(out)


def scan_numeric_literals(app_dir: Path) -> dict[str, int]:
    out: Counter = Counter()
    for rel, tree in _files(app_dir):
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool) and n.value in _NUMERIC:
                out[rel] += 1
    return dict(out)


def scan_frequency_defaults(app_dir: Path) -> set[tuple[str, str, str, float]]:
    found = set()
    for rel, tree in _files(app_dir):
        for n in ast.walk(tree):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            a = n.args
            positional = a.posonlyargs + a.args
            pairs = list(zip(positional[len(positional) - len(a.defaults):], a.defaults)) + list(zip(a.kwonlyargs, a.kw_defaults))
            for arg, default in pairs:
                if "freq" in arg.arg and isinstance(default, ast.Constant) and isinstance(default.value, (int, float)):
                    found.add((rel, n.name, arg.arg, float(default.value)))
    return found


def scan_importers(app_dir: Path, module: str) -> set[str]:
    """Files that import `module` (a dotted name), by AST, so a mention in a docstring or comment does not count."""
    users = set()
    short = module.rsplit(".", 1)[1]
    for rel, tree in _files(app_dir):
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and (n.module == module or (n.module == module.rsplit(".", 1)[0] and any(a.name == short for a in n.names))):
                users.add(rel)
            if isinstance(n, ast.Import) and any(a.name == module for a in n.names):
                users.add(rel)
    return users


def scan_registry_users(app_dir: Path) -> tuple[set[str], set[str]]:
    """(files mentioning the registry type or the app.state attribute, files that READ its stored state)."""
    mentions, readers = set(), set()
    for rel, tree in _files(app_dir):
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and any(a.name == "NominalFrequencyRegistry" for a in n.names) and n.module != "app.services.nominal_frequency_registry":
                mentions.add(rel)
            if isinstance(n, ast.ImportFrom) and n.module == "app.services.nominal_frequency_registry":
                mentions.add(rel)
            if isinstance(n, ast.Attribute) and n.attr == "nominal_frequency_registry":
                mentions.add(rel)
            if isinstance(n, ast.Attribute) and n.attr in REGISTRY_READ_METHODS:
                base = n.value
                name = base.id if isinstance(base, ast.Name) else base.attr if isinstance(base, ast.Attribute) else ""
                if "nominal_frequency_registry" in name or name == "registry" and rel.startswith("services/nominal_frequency_"):
                    readers.add(rel)
    return mentions, readers


def scan_frontend(text: str) -> dict[str, int]:
    return {name: len(re.findall(pattern, text)) for name, pattern in _FRONTEND_PATTERNS.items()}


# -------------------------------------------------------------------------------------------------------- the guard
class TestTheInventoryIsExact:
    def test_attribute_reads_of_the_imported_value_and_its_carried_copies(self):
        assert scan_attribute_reads(APP_DIR) == ATTRIBUTE_READS

    def test_frequency_field_names_used_as_keys_and_parameters(self):
        assert scan_frequency_keys(APP_DIR) == FREQUENCY_KEYS

    def test_hard_coded_fifty_sixty_and_window_literals(self):
        assert {k: v for k, v in scan_numeric_literals(APP_DIR).items()} == {k: v[0] for k, v in NUMERIC_LITERALS.items()}

    def test_default_values_of_frequency_parameters(self):
        assert scan_frequency_defaults(APP_DIR) == FREQUENCY_DEFAULTS

    def test_every_literal_entry_is_classified(self):
        assert all(cls in {"K", "D", "M"} and note for _, cls, note in NUMERIC_LITERALS.values())

    def test_the_frequency_defaults_are_a_subset_of_the_migrate_class(self):
        migrate_files = {rel for rel, (_, cls, _) in NUMERIC_LITERALS.items() if cls == "M"}
        assert {rel for rel, *_ in FREQUENCY_DEFAULTS} <= migrate_files

    def test_the_frontend_frequency_tokens(self):
        assert scan_frontend(FRONTEND_INDEX.read_text(encoding="utf-8")) == FRONTEND_TOKENS


class TestTheAuthorityCannotBeBypassed:
    def test_only_the_gated_accessor_imports_the_nf1_service_layer(self):
        assert scan_importers(APP_DIR, "app.services.nominal_frequency_service") == SERVICE_IMPORTERS

    def test_only_the_migrated_consumers_import_the_accessor(self):
        assert scan_importers(APP_DIR, "app.services.nominal_frequency_access") == ACCESS_IMPORTERS

    def test_the_stored_manual_value_is_read_only_by_the_service_layer(self):
        mentions, readers = scan_registry_users(APP_DIR)
        assert mentions == REGISTRY_USERS
        assert readers == {"services/nominal_frequency_service.py"}

    def test_the_resolver_is_imported_only_by_the_service_layer_the_schema_and_the_accessor(self):
        users = scan_importers(APP_DIR, "app.domain.nominal_frequency")
        # NF-3C: oscillation_representation_service imports only the five ORIGIN_* NAMES (the public vocabulary it reports); it never
        # calls the resolver. The accessor is still its only source of a frequency (see the importer test above).
        assert users == {"services/nominal_frequency_service.py", "services/nominal_frequency_registry.py",
                         "services/nominal_frequency_access.py", "schemas/nominal_frequency.py",
                         "services/oscillation_representation_service.py",
                         "services/calculated_channel_staleness.py"}                  # NF-3E: ORIGIN_* names for the reason text only

    def test_the_server_side_gate_is_read_from_settings_by_one_place(self):
        users = sorted(rel for rel, _ in _files(APP_DIR) if "nominal_frequency_manual_override_enabled" in (APP_DIR / rel).read_text(encoding="utf-8"))
        assert users == ["config.py", "main.py"]


# ------------------------------------------------------------------------- the guard catches what it exists to catch
OFFENDERS = {
    "a direct read of the imported value": "def f(active):\n    return active.metadata.nominal_frequency\n",
    "a carried copy read": "def f(candidate):\n    return candidate.nominal_frequency\n",
    "a calculated-channel frequency parameter read": 'def f(channel):\n    return channel.parameters["nominal_frequency_hz"]\n',
    "a hard-coded fifty hertz window": "def f(time):\n    return window(time, 50.0)\n",
    "a hard-coded sixty hertz fundamental": "FUNDAMENTAL = 60\n",
}


@pytest.mark.parametrize("label,source", sorted(OFFENDERS.items()))
def test_a_synthetic_new_consumer_that_bypasses_the_accessor_is_detected(tmp_path, label, source):
    app = tmp_path / "app"
    (app / "services").mkdir(parents=True)
    (app / "services" / "new_consumer.py").write_text(source, encoding="utf-8")
    found = (scan_attribute_reads(app), scan_frequency_keys(app), scan_numeric_literals(app))
    assert any(found), f"the guard did not notice: {label}"


def test_a_synthetic_default_frequency_argument_is_detected(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "m.py").write_text("def analyse(time, nominal_frequency_hz=60.0):\n    return time\n", encoding="utf-8")
    assert scan_frequency_defaults(app) == {("m.py", "analyse", "nominal_frequency_hz", 60.0)}


def test_a_synthetic_bypass_of_the_gate_through_the_service_or_the_registry_is_detected(tmp_path):
    app = tmp_path / "app"
    (app / "services").mkdir(parents=True)
    (app / "services" / "greedy.py").write_text(textwrap.dedent('''
        from app.services.nominal_frequency_service import effective_nominal_frequency

        def f(request):
            return request.app.state.nominal_frequency_registry.snapshot("w", "s")
    '''), encoding="utf-8")
    assert scan_importers(app, "app.services.nominal_frequency_service") == {"services/greedy.py"}
    mentions, readers = scan_registry_users(app)
    assert mentions == {"services/greedy.py"} and readers == {"services/greedy.py"}


def test_a_synthetic_import_of_the_accessor_by_a_consumer_is_detected(tmp_path):
    app = tmp_path / "app"
    (app / "services").mkdir(parents=True)
    (app / "services" / "adopter.py").write_text("from app.services.nominal_frequency_access import NominalFrequencyAccess\n", encoding="utf-8")
    assert scan_importers(app, "app.services.nominal_frequency_access") == {"services/adopter.py"}


def test_the_frontend_scanner_counts_tokens():
    assert scan_frontend("x.nominalFrequency + nominal_frequency + nominal_frequency_hz + reference_frequency_hz") == {
        "nominal_frequency_hz": 1, "nominal_frequency(bare)": 1, "nominalFrequency": 1, "reference_frequency": 1, "nominalFrequencyOverride": 0}


def test_docstring_mentions_do_not_count_as_imports(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "doc.py").write_text('"""See app.services.nominal_frequency_service for the authority."""\n', encoding="utf-8")
    assert scan_importers(app, "app.services.nominal_frequency_service") == set()
