"""Validate retained results against the requesting session's shared source timebase.

Definitions and eager arrays stay immutable. No result/authorization cache is shared
between requests: all original inputs, including calculated parents, are checked
before returning arrays. Compatible timing can restore the same retained result.
"""
from __future__ import annotations

import hashlib
import json

from app.domain.calculated_channel import timebases_aligned
from app.domain.time_reference import source_start_epoch, source_timestamp_utc, effective_timing_reference
from app.services.errors import IncompatibleTimeBaseError, ImportServiceError


def _inspect(channel, *, workspace_id, source_registry, calc_registry):
    sources, checked, visiting = {}, {}, set()

    def source(sid):
        if sid not in sources:
            active = source_registry.get(workspace_id, sid)
            if active is None:
                raise IncompatibleTimeBaseError("A recording required by this calculated channel is no longer available.")
            sources[sid] = active
        active = sources[sid]
        return sid, active.record.waveform_data["time"].to_numpy(), source_start_epoch(active.metadata)

    def visit(node):
        if node.id in checked:
            return checked[node.id]
        if node.id in visiting:
            raise IncompatibleTimeBaseError("This calculated channel has a cyclic dependency.")
        visiting.add(node.id)
        operands = []
        for ref in node.inputs:
            if ref.kind == "source":
                operands.append(source(ref.source_id))
            else:
                parent = calc_registry.get(workspace_id, ref.calculated_channel_id)
                if parent is None:
                    raise IncompatibleTimeBaseError("A calculated input required by this channel is no longer available.")
                operands.append(visit(parent))
        if not operands or any(not timebases_aligned(*operands[0], *other) for other in operands[1:]):
            raise IncompatibleTimeBaseError(
                "This calculated result is unavailable because its input recordings do not have compatible "
                "sample times in this session. Restore compatible time interpretations to use it again."
            )
        _, _, epoch = source(node.reference_source_id)
        identity = node.reference_source_id, node.time, epoch
        visiting.remove(node.id)
        checked[node.id] = identity
        return identity

    visit(channel)
    return sources


def get_calculated_result(workspace_id, calculated_channel_id, *, source_registry, calc_registry):
    """The common array-access gate; missing root ids retain the existing None contract."""
    channel = calc_registry.get(workspace_id, calculated_channel_id)
    if channel is not None:
        _inspect(channel, workspace_id=workspace_id, source_registry=source_registry, calc_registry=calc_registry)
    return channel


def calculated_timing_metadata(channel, *, source_registry, calc_registry):
    """Live catalogue validity and cache token, never an authorization substitute.

    Include every transitive source, not only the reference source or a revision
    counter. Different sessions can have identical revisions with different clocks.
    No arrays or interpretation are written back into the definition.
    """
    source_ids, seen = set(), set()
    def roots(node):
        if node.id in seen:
            return
        seen.add(node.id)
        for ref in node.inputs:
            if ref.kind == "source":
                source_ids.add(ref.source_id)
            else:
                parent = calc_registry.get(channel.workspace_id, ref.calculated_channel_id)
                if parent is not None:
                    roots(parent)
    roots(channel)
    fingerprint = []
    for sid in sorted(source_ids):
        active = source_registry.get(channel.workspace_id, sid)
        if active is None:
            fingerprint.append((sid, None))
            continue
        metadata = active.metadata
        utc = source_timestamp_utc(metadata, "start_time")
        fingerprint.append((sid, utc.isoformat() if utc else None, metadata.time_basis,
                            effective_timing_reference(metadata), metadata.time_reference_revision))
    error = None
    try:
        _inspect(channel, workspace_id=channel.workspace_id, source_registry=source_registry, calc_registry=calc_registry)
    except ImportServiceError as exc:
        error = exc.message
    return {
        "timing_status": "incompatible" if error else "valid", "timing_error": error,
        "timing_source_ids": sorted(source_ids),
        "timing_fingerprint": hashlib.sha256(json.dumps(fingerprint, separators=(",", ":")).encode()).hexdigest(),
    }
