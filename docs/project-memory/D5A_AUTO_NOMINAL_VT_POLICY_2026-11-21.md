# D5A — Nominal-derived VT is valid engineering configuration (DEC-215)

**Status:** owner decision 2026-11-21, implemented on `uat/dev-d5a-20261121`; supersedes the earlier D5A rule that treated
`auto_nominal` VT as display-only. Not pushed or deployed until owner review.

## 1. Decision

An automatically derived VT is accepted as valid engineering configuration, consistent with the existing Per-Unit
nominal-voltage policy. When a Voltage Measurement Group has **no stored VT**, Recording Details derives
`primary = nominal kV x 1000`, `secondary = 110 V`. Both values are immediately usable by every consuming module. No
engineer confirmation or Edit → Save is required, and the UI never calls a valid derived VT "assumed", "provisional",
"unverified" or "display-only". An "Auto-derived" provenance label is shown.

## 2. Rules (all implemented)

| # | Rule | Where |
|---|---|---|
| 1 | One definition of the derivation, shared by Recording Details and the protection resolver | `backend/app/domain/auto_nominal_vt.py` (`derive_auto_nominal_vt`) |
| 2 | Precedence unchanged: **manual > recording_metadata > auto_nominal > not_configured**. A stored VT of any authority always wins; changing the nominal or the VT refreshes every consumer on the next read | resolver + view |
| 3 | Provenance preserved: the context reports `authority = "auto_nominal"` (never `manual` / `recording_metadata`); a *stored* `auto_nominal` authority is still not trusted | `protection_instrument_context.py` |
| 4 | Refused, never guessed, when the nominal is not an accepted value: missing / non-finite / non-positive nominal, `manual_conflict_detected`, base authority `needs_review` / `unavailable`. The reason is reported (`nominal_refused_reason`) | `auto_nominal_vt.py` |
| 5 | Other checks unchanged: invalid pair, genuine ratio conflict between groups, measurement-side checks (differing / mixed / undeclared sides), strict-mode side authority, double-conversion guards | resolver / `independent_side_service` / frontend plan |
| 6 | CT is never derived (not from equipment rating, MVA or capacity). It is configured independently | resolver (`test_a_ct_is_never_derived_from_equipment_rating_or_capacity`) |
| 7 | PU and conversion mathematics untouched; the Recording Details effective-VT view yields identical values | `measurement_group_view_service.py` (refactor only) |

## 3. API contract change (`protection-instrument-context`)

- `voltage.ignored_nominal_kv` is replaced by `voltage.nominal_ll_kv` (the group's nominal, when it exists) and
  `voltage.nominal_refused_reason` (`manual_conflict` | `base_not_accepted`, only when the VT could not be derived).
- Diagnostic `VT_NOMINAL_DISPLAY_ONLY` (info) is replaced by `VT_NOMINAL_NOT_USABLE` (warning), emitted only when a nominal
  exists but could not yield a VT. A valid derived VT produces no `VT_AUTHORITY_MISSING`.
- `authority` may now be `auto_nominal` (consumable) or `mixed` (groups with equal ratios but different authorities).

## 4. Frontend

Impedance Locus and Distance Protection show the VT like any other (`132 kV / 110 V (Auto-derived, <group>)`) with no warning
and calculate without any confirmation. A manual VT saved in Recording Details replaces it. When a nominal cannot be used the
message states why (conflict with channel evidence / base not accepted) and what to do; with no VT and no nominal the message
asks for the nominal voltage or the VT. Recording Details' note reads "Auto-derived from nominal voltage (110 V secondary
default)." Manual mode, Overcurrent and the Waveform Analysis page are unchanged.

## 5. CT shown in Recording Details but reported "not configured" — investigation

**Verified in code (not assumed):**

- Recording Details shows a CT whenever `ct_primary_a` and `ct_secondary_a` are present on the *group the engineer is
  viewing* (`wwRdCtSectionHtml`); the analyzers read the CT of the *group that owns the analysis's resolved current channel*
  (`group_for_channel`), through the same `CurrentGroupConfigRegistry`.
- Every writer of a CT stamps `ct_authority = "manual"` (`update_current_ct_config`); there is no path that stores values with
  another authority, so an authority mismatch is not a plausible cause.
- All group configuration registries are **in memory**. A backend restart — including every DEV deployment — discards sources,
  Measurement Groups and any CT/VT entered; re-uploading re-creates the suggested groups with **no CT** (a CT is never derived).

**Candidate explanations, in order of what the evidence can already distinguish:**

1. *Configuration lost on redeploy:* the CT was entered before the DEV build `503dc81` was deployed and the recording was
   re-uploaded afterwards. Recording Details would then also show "— Not configured" for the CT of the re-created group.
2. *Different group:* the CT was entered on a different Current group than the one containing the analysis's current channel
   (e.g. a second current group for the same bay). The page now names the group it reads ("CT is not configured for '<group>'")
   and — see §6 — points at any other Current group in the recording that does hold a CT.
3. *A genuine defect* (values present on the owning group yet reported not configured). Nothing in the code reviewed allows this,
   but it cannot be excluded without the live data.

**Not yet verified:** the owner's live DEV workspace. It cannot be listed anonymously (no workspace-listing route), so the stored
group configuration has not been read. To settle it, with the workspace id (`localStorage.getItem("powerwave.workspaceId")`)
and the API base `https://api.dev.powerwave.oruxa.uk`:

```
GET /api/v1/workspaces/{ws}/sources                                   -> source id(s)
GET /api/v1/workspaces/{ws}/sources/{src}/measurement-groups          -> each Current group: id, channel_refs, current_config.ct_*
GET /api/v1/workspaces/{ws}/engineering-contexts                      -> context id
GET /api/v1/workspaces/{ws}/engineering-contexts/{ctx}/protection-instrument-context?analysis=impedance&phase=A
                                                                      -> channels[].measurement_group_id, current.{ratio_status, group_ids}
```

Compare the group that holds the CT with `channels[].measurement_group_id` of the `Ia` role.

## 6. Diagnostic added for the CT case

When a CT is reported not configured but another Current group of the same recording holds one, the message says so
("A CT of 1200 A / 1 A is configured on '<group>', but <channel> belongs to '<group>'"), so an off-group CT is visible without
inspecting the API.
