"""Static regression checks for the "Start New Workspace" UAT fix: the
Calculated Channels Signal Builder's own transient form state
(wwCcBuilder/wwCcRmsEligibility) previously survived a workspace reset,
even though ww.calculatedChannels itself was already correctly cleared.
Same source-text substring-assertion pattern as
test_frontend_calculated_channel_time_mode.py -- this repo has no
browser/DOM test runner for the single-file frontend.
"""

from __future__ import annotations

from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"


def _source() -> str:
    return FRONTEND.read_text(encoding="utf-8")


def _function_body(source: str, signature: str, next_signature: str) -> str:
    start = source.index(signature)
    end = source.index(next_signature, start)
    return source[start:end]


def test_workspace_reset_branch_resets_the_signal_builder():
    source = _source()
    body = _function_body(source, "function wwClearWorkspace(options)", "function wwStickyRulerElapsedUnit")
    reset_branch = body[body.index("if (options.resetSourceBounds)") : body.index("} else {")]
    assert "ww.calculatedChannels.clear();" in reset_branch
    assert "wwCcResetBuilder();" in reset_branch
    assert "wwCcListErrors.clear();" in reset_branch
    # Must run BEFORE the page re-render, or the re-render would still
    # draw the stale builder state it was meant to replace.
    assert reset_branch.index("wwCcResetBuilder();") < reset_branch.index("wwRenderCalculatedChannelsPage();")


def test_plain_clear_workspace_branch_is_unaffected():
    # Section 16/27: "Clear Workspace" (display-only) must NOT reset the
    # builder or rotate anything -- confirm the fix is scoped only to the
    # resetSourceBounds branch, never the plain-clear else branch.
    source = _source()
    body = _function_body(source, "function wwClearWorkspace(options)", "function wwStickyRulerElapsedUnit")
    else_branch = body[body.index("} else {") : body.index("ww.customGroups = [];")]
    assert "wwCcResetBuilder()" not in else_branch
    assert "ww.calculatedChannels.clear()" not in else_branch


def test_reset_builder_clears_operation_inputs_name_and_eligibility():
    # wwCcResetBuilder() is the SAME function already used after every
    # successful creation (wwCcCreateChannel()) -- reused, not duplicated.
    source = _source()
    body = _function_body(source, "function wwCcResetBuilder()", "function wwCcResolveNominalFrequencyAuthority")
    assert "wwCcBuilder.operation = null;" in body
    assert "wwCcBuilder.inputs = [];" in body
    assert "wwCcBuilder.name = \"\";" in body
    assert "wwCcResetRmsEligibility();" in body


def test_reset_rms_eligibility_invalidates_in_flight_requests():
    # This is what protects against a stale async RMS eligibility
    # response (issued in the OLD workspace) landing after a reset --
    # bumping the generation counter makes wwCcCheckRmsEligibility()'s
    # own existing staleness guard discard it.
    source = _source()
    body = _function_body(source, "function wwCcResetRmsEligibility()", "function wwCcAvailableCandidates()")
    assert "wwCcRmsEligibilityGeneration += 1;" in body
    assert "clearTimeout(wwCcRmsEligibilityDebounceTimer);" in body


def test_start_new_workspace_still_rotates_workspace_id_before_clearing():
    # Confirms the EXISTING id-rotation lifecycle (already correct, not
    # touched by this fix) -- backend DELETE succeeds, then and only then
    # a new id is minted and used to refresh the footer.
    source = _source()
    body = _function_body(source, "async function resetToNewWorkspace()", "// ------")
    assert "await fetch(" in body
    assert "{ method: \"DELETE\" }" in body
    assert "if (!response.ok)" in body
    assert "localStorage.setItem(WORKSPACE_STORAGE_KEY, crypto.randomUUID());" in body
    assert 'document.getElementById("statusBarWorkspaceId").textContent = currentWorkspaceId();' in body
    assert "wwClearWorkspace({ resetSourceBounds: true });" in body
    # Order matters: rotate/clear only happens AFTER the DELETE succeeds
    # (an early `return` on failure must skip everything after it).
    assert body.index("await fetch(") < body.index("localStorage.setItem(WORKSPACE_STORAGE_KEY")


def test_current_workspace_id_is_never_cached_stale():
    # currentWorkspaceId() must read localStorage fresh every call --
    # otherwise even a correct rotation could still render a stale id
    # somewhere that cached an earlier read.
    source = _source()
    body = _function_body(source, "function currentWorkspaceId()", "// --")
    assert "localStorage.getItem(WORKSPACE_STORAGE_KEY)" in body
