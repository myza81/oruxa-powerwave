"""Static guards for the shared live workspace signal catalogue.

The catalogue is a derived view over ww.sourceChannelsData and
ww.calculatedChannels plus a publish/subscribe seam. These checks keep the
producers routed through it and the catalogue free of any consumer
knowledge. Runtime behaviour is covered by browser-tests/signal_catalogue.spec.js.
"""

from __future__ import annotations

import re
from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _catalogue_block(source: str) -> str:
    start = source.index("// Shared live workspace signal catalogue")
    end = source.index("async function wwFetchCalculatedChannels()", start)
    return source[start:end]


def test_calculated_channel_mirror_is_only_mutated_through_the_catalogue_helpers():
    source = _source()
    block = _catalogue_block(source)
    outside = source.replace(block, "")
    # Reset is the one documented direct writer; it publishes immediately after.
    outside_mutations = re.findall(r"ww\.calculatedChannels\.(?:set|delete)\(", outside)
    assert outside_mutations == []
    assert outside.count("ww.calculatedChannels.clear();") == 1
    reset = outside[outside.index("ww.calculatedChannels.clear();"):]
    assert 'wwSignalCataloguePublish({ type: "reset"' in reset[:400]
    for helper in ("wwCalculatedChannelsUpsert(", "wwCalculatedChannelsRemove(", "wwCalculatedChannelsReplaceAll("):
        assert helper in outside


def test_raw_signal_producers_publish_after_mutating_their_authority():
    source = _source()
    assert source.count('wwSignalCataloguePublish({ type: "added", origin: "raw"') == 1
    assert source.count('wwSignalCataloguePublish({ type: "removed", origin: "raw"') == 2
    ensure = source[source.index("async function wwEnsureSourceChannelsFetched"):]
    ensure = ensure[:ensure.index("return true;")]
    assert ensure.index("ww.sourceChannelsData.set(") < ensure.index('type: "added", origin: "raw"')


def test_catalogue_is_a_derived_view_not_a_store_and_knows_no_consumer():
    block = _catalogue_block(_source())
    assert "ww.sourceChannelsData.values()" in block
    assert "ww.calculatedChannels.values()" in block
    # No signal storage of its own: only a counter and the listener set.
    assert "const wwSignalCatalogue = { revision: 0, listeners: new Set() };" in block
    code = "\n".join(line for line in block.splitlines() if not line.strip().startswith("//"))
    for consumer in ("Oscillation", "Phasor", "Overcurrent", "Impedance", "Waveform", "Table", "Compliance"):
        assert consumer not in code
    # Eligibility belongs to the consumer: the list only accepts its predicate.
    assert "function wwSignalCatalogueList(predicate)" in block
    assert "wwSignalCatalogueIsCurrent" in block


def test_listener_failures_are_isolated():
    block = _catalogue_block(_source())
    publish = block[block.index("function wwSignalCataloguePublish"):block.index("function wwSignalFromCalculatedChannel")]
    assert "try { listener(event); } catch" in publish


def test_builder_candidates_come_from_the_catalogue_not_a_second_merge():
    source = _source()
    body = source[source.index("function wwCcAvailableCandidates()"):source.index("function wwCcInputDisplayName(")]
    assert "wwSignalCatalogueList(" in body
    assert "ww.sourceChannelInventory" not in body
    assert "ww.calculatedChannels" not in body
    # The builder's own eligibility: analog signals only.
    assert 'signal.signalType === "analog"' in body


def test_event_reconstruction_holds_no_private_calculated_channel_inventory():
    source = _source()
    state = source[source.index("const wwErState = {"):]
    state = state[:state.index("};")]
    keys = re.findall(r"^ {12}(\w+):", state.split("{", 1)[1], re.MULTILINE)
    assert "calculatedChannels" not in keys
    assert "wwErState.calculatedChannels" not in source
    reader = source[source.index("function wwErCalculatedChannels()"):]
    reader = reader[:reader.index("function wwErObserveSignalCatalogue")]
    assert "wwSignalCatalogueList(" in reader
    observer = source[source.index("function wwErObserveSignalCatalogue()"):]
    observer = observer[:observer.index("async function wwErSend(")]
    assert "wwSignalCatalogueSubscribe(" in observer
    assert "wwErObserveSignalCatalogue();" in source
