"""D5A-2B2C-1B mutation checks for the unified measurement-side integration of recorded Impedance / Distance.

Each mutant is a small, deliberate defect injected into one production file -- a reversed conversion ratio, a double
conversion, a bypass of the shared authority, a request ratio standing in for Recording Details', wrong-group VT/CT
borrowing, a disabled guard -- and the two new backend suites (`test_d5a_2b2c_1b_authority_enforcement.py`,
`test_d5a_2b2c_1b_impedance_distance_oracles.py`) must FAIL for it ("KILLED"). A mutant that "SURVIVED" means the suite
does not protect that behaviour.

Usage (from the repository root, with the backend virtualenv's Python):
    python scripts/diagnostics/d5a_2b2c_1b_mutation_checks.py [substring of a mutant name ...]

Every mutated file is restored from its original bytes in a `finally`, even on failure or interruption; run it on a clean
working tree and check `git status` afterwards. It never touches anything but the files named below.
"""

import os
import subprocess
import sys

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "backend"))
PY = sys.executable
APP = os.path.join(ROOT, "app")
SIDE_SVC = os.path.join(APP, "services", "independent_side_service.py")
AUTH = os.path.join(APP, "services", "recorded_side_authority.py")
DOMAIN = os.path.join(APP, "domain", "side_conversion.py")
IMP = os.path.join(APP, "services", "impedance_analysis_service.py")
DIST = os.path.join(APP, "services", "distance_protection_analysis_service.py")
CTX = os.path.join(APP, "services", "protection_instrument_context.py")
TESTS = [os.path.join("tests", "test_d5a_2b2c_1b_authority_enforcement.py"), os.path.join("tests", "test_d5a_2b2c_1b_impedance_distance_oracles.py")]

# (name, file, [(old, new), ...])
MUTANTS = [
    ("reversed conversion ratio (multiply <-> divide)", DOMAIN,
     [("    return value * ratio if (source_side == SIDE_SECONDARY and output_side == SIDE_PRIMARY) else value / ratio",
       "    return value / ratio if (source_side == SIDE_SECONDARY and output_side == SIDE_PRIMARY) else value * ratio")]),
    ("double conversion of the impedance voltage", IMP,
     [("plan.scale_voltage(voltage), voltage_role.angle_deg_absolute", "plan.scale_voltage(plan.scale_voltage(voltage)), voltage_role.angle_deg_absolute")]),
    ("double conversion of the impedance current", IMP,
     [("plan.scale_current(current),\n        current_role.angle_deg_absolute", "plan.scale_current(plan.scale_current(current)),\n        current_role.angle_deg_absolute")]),
    ("double conversion of a distance voltage leg", DIST,
     [("plan.scale_voltage(volts[1]), v2_role.angle_deg_absolute", "plan.scale_voltage(plan.scale_voltage(volts[1])), v2_role.angle_deg_absolute")]),
    ("distance current leg not converted", DIST,
     [("plan.scale_current(amps[1]), i2_role.angle_deg_absolute", "amps[1], i2_role.angle_deg_absolute")]),
    ("low-current floor not scaled with the current conversion (impedance)", IMP,
     [("min_current=MIN_CURRENT_A * plan.current_scale", "min_current=MIN_CURRENT_A")]),
    ("bypass of the shared authority: conversions use the DECLARED side, not the effective side", SIDE_SVC,
     [("        voltage_side=voltage.side, current_side=current.side, output_side=impedance_basis,\n        vt_ratio=",
       "        voltage_side=voltage.declared_sides[0], current_side=current.declared_sides[0], output_side=impedance_basis,\n        vt_ratio=")]),
    ("assertions are never validated against the effective side", SIDE_SVC,
     [("            if asserted is not None and asserted != qa.side:", "            if False and asserted is not None and asserted != qa.side:")]),
    ("request ratio replaces the authoritative one (and its conflict is not checked)", SIDE_SVC,
     [("            if not math.isclose(req_p / req_s, ctx.ratio, rel_tol=_RATIO_REL_TOL):", "            if False and not math.isclose(req_p / req_s, ctx.ratio, rel_tol=_RATIO_REL_TOL):"),
      ("        ratios[quantity] = ctx.ratio", "        ratios[quantity] = (req_p / req_s) if (req_p and req_s) else ctx.ratio")]),
    ("a request ratio compensates for a missing authoritative ratio", SIDE_SVC,
     [("        if ctx is None or not ctx.ratio_consumable:\n            return make_block(",
       "        if (ctx is None or not ctx.ratio_consumable) and not (_positive(request[0]) and _positive(request[1])):\n            return make_block(")]),
    ("a ratio is required even where no conversion is needed", SIDE_SVC,
     [("        if not qa.ratio_required:\n            continue", "        if False:\n            continue")]),
    ("wrong-group borrowing: an ungrouped channel borrows another group's VT/CT", CTX,
     [("        group_id = group_registry.group_for_channel(workspace_id, ref) if ref.kind == \"source\" else None",
       "        group_id = (group_registry.group_for_channel(workspace_id, ref) or next((g.id for g in group_registry.list_for_workspace(workspace_id) if g.kind == kind), None)) if ref.kind == \"source\" else None")]),
    ("wrong-group borrowing: a recording uses the first group of its kind in the workspace", CTX,
     [("        group_id = group_registry.group_for_channel(workspace_id, ref) if ref.kind == \"source\" else None",
       "        group_id = next((g.id for g in group_registry.list_for_workspace(workspace_id) if g.kind == kind), None) if ref.kind == \"source\" else None")]),
    ("mixed declarations in a Measurement Group are ignored", AUTH,
     [("    if not side.usable:\n        problem = PROBLEM_UNRESOLVED", "    in_conflict = False\n    if not side.usable:\n        problem = PROBLEM_UNRESOLVED")]),
    ("a recording-level inference is accepted as a usable side", AUTH,
     [("    elif side.inferred:\n        problem = PROBLEM_INFERRED", "    elif False:\n        problem = PROBLEM_INFERRED")]),
    ("calculated channels are not guarded", AUTH,
     [("    if ref.kind != \"source\":\n        return ChannelSideAuthority(ref, None, None, None, PROBLEM_CALCULATED)",
       "    if False and ref.kind != \"source\":\n        return ChannelSideAuthority(ref, None, None, None, PROBLEM_CALCULATED)")]),
    ("the ratio-required flag is inverted", SIDE_SVC,
     [('**{**base, "ratio_required": side != output_side}', '**{**base, "ratio_required": side == output_side}')]),
]

only = sys.argv[1:]
for name, path, pairs in MUTANTS:
    if only and not any(o in name for o in only):
        continue
    original = open(path, "rb").read()
    text = original.decode("utf-8")
    crlf = "\r\n" in text
    body = text.replace("\r\n", "\n")
    missing = [old[:70] for old, _new in pairs if body.count(old) != 1]
    if missing:
        print(name, "| PATTERN NOT FOUND/AMBIGUOUS", missing, flush=True)
        continue
    mutated = body
    for old, new in pairs:
        mutated = mutated.replace(old, new)
    if crlf:
        mutated = mutated.replace("\n", "\r\n")
    try:
        open(path, "wb").write(mutated.encode("utf-8"))
        proc = subprocess.run([PY, "-m", "pytest", "-p", "no:cacheprovider", *TESTS, "-x", "-q", "--no-header"],
                              cwd=ROOT, capture_output=True, text=True, timeout=1500)
        out = proc.stdout + proc.stderr
        first = next((l for l in out.splitlines() if l.startswith("FAILED") or l.startswith("ERROR")), "")
        print(name, "|", "KILLED" if proc.returncode != 0 else "SURVIVED", "|", first[:150], flush=True)
    finally:
        open(path, "wb").write(original)
