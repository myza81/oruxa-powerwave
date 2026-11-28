"""NF-2 -- the nominal-frequency control is behind a release gate and is the only frontend user of the NF-1 endpoint.

Static checks over the shipped frontend files. The behaviour (gate off, gate on, every state) is covered end to end by
`browser-tests/nf2_recording_details_nominal_frequency.spec.js`; these tests make the *default* impossible to flip by accident:
no checked-in or generated runtime configuration turns the control on, and nothing but the one gate function reads the flag.
"""

from __future__ import annotations

import re
from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
INDEX = (FRONTEND / "index.html").read_text(encoding="utf-8")
GATE_FLAG = "nominalFrequencyOverride"


def _nf_block() -> str:
    start = INDEX.index("// NF-2: recording-level nominal frequency")
    return INDEX[start:INDEX.index("// NF-2-BLOCK-END", start)]


def test_the_checked_in_runtime_config_does_not_enable_the_control():
    config = (FRONTEND / "config.js").read_text(encoding="utf-8")
    assert GATE_FLAG not in config and "featureFlags" not in config


def test_the_container_entrypoint_cannot_emit_the_flag():
    scripts = list((FRONTEND / "docker-entrypoint.d").glob("*"))
    assert scripts, "entrypoint scripts not found"
    for script in scripts:
        text = script.read_text(encoding="utf-8")
        assert GATE_FLAG not in text and "featureFlags" not in text, script.name


def test_the_flag_is_read_in_exactly_one_place_and_only_the_boolean_true_opens_it():
    reads = [m.start() for m in re.finditer(GATE_FLAG, INDEX)]
    assert len(reads) == 2, "one definition comment/read pair expected"          # the header comment and the single read
    gate = re.search(r"function wwNfEnabled\(\) \{(.*?)\n        \}", INDEX, re.S).group(1)
    assert "=== true" in gate and GATE_FLAG in gate
    assert "POWERWAVE_CONFIG" in gate


def test_the_gate_guards_the_only_entry_point_into_the_control():
    uses = [m.start() for m in re.finditer(r"wwNfEnabled\(\)", INDEX)]
    assert len(uses) == 2                                                         # the definition and the one call
    assert 'right.push(wwNfEnabled() ? wwRdNfSectionHtml(s) : row("Nominal frequency", nomFreq));' in INDEX
    # the section builder is reachable only through that call, and is the only thing that starts a request
    assert len(re.findall(r"wwRdNfSectionHtml\(", INDEX)) == 2
    assert len(re.findall(r"wwRdNfEnsure\(", INDEX)) == 2                          # definition + the section builder


def test_the_control_uses_only_the_nf1_endpoint_and_no_other_frequency_authority():
    block = _nf_block()
    urls = re.findall(r'"/sources/"[^;]*?"(/[a-z-]+)"', block) + re.findall(r'"(/nominal-frequency)"', block)
    assert set(urls) == {"/nominal-frequency"}
    assert len(re.findall(r"fetch\(", block)) == 2                                # one read, one write
    assert "reference_frequency_hz" not in block and "nominal_frequency_hz" not in block


def test_no_other_part_of_the_page_reads_the_control_state():
    outside = INDEX.replace(_nf_block(), "")
    names = re.findall(r"\bwwRdNf\w*", outside)
    # the only references outside the block: the row call, and the three invalidation hooks
    assert sorted(set(names)) == ["wwRdNfInvalidate", "wwRdNfSectionHtml"], sorted(set(names))
    assert names.count("wwRdNfInvalidate") == 3 and names.count("wwRdNfSectionHtml") == 1


def test_the_control_says_it_is_a_preview_until_the_consumers_are_migrated():
    block = _nf_block()
    assert "const WW_NF_CONSUMERS_MIGRATED = false;" in block
    assert "Preview: calculations do not use this setting yet." in block
    assert "if (!WW_NF_CONSUMERS_MIGRATED)" in block


def test_the_existing_nominal_frequency_readers_of_the_page_are_untouched():
    # NF-2 adds no consumer migration: the calculated-channel builder still reads the imported value from the inventory.
    assert "nominalFrequency: data.source.nominal_frequency" in INDEX
    assert "wwRdNf" not in INDEX[INDEX.index("nominalFrequency: data.source.nominal_frequency") - 400:
                                 INDEX.index("nominalFrequency: data.source.nominal_frequency") + 400]
