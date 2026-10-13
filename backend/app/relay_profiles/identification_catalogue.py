"""Identification catalogue: which relay lines the importer can *recognise*.

Relay Import Slice 5. Recognised means identifiable from a document -- it
does NOT mean the relay's settings can be interpreted, and it is not
"validated". Validation is reserved for profiles that later pass owner UAT
with real setting files. Nothing here maps a setting to an engineering
meaning.

Each entry is data for the OEM-neutral ``RelayIdentifier``:

* ``model_patterns``     the model identifier (strongest evidence);
* ``family_markers``     brand/family text that is not the model itself;
* ``parameter_signatures`` a distinctive naming family of that line's
  parameters (counted only when several entries show it).

Generic protection vocabulary (zone, reach, R1, X1, K0, CT, VT, ...) is
deliberately absent: it is shared by every distance relay.

``manufacturer`` is the normalised identity, ``None`` where the project has
not established it. ``MANUFACTURER_ALIASES`` records brand transitions so a
document written under an older name still normalises.
"""

from __future__ import annotations

from functools import lru_cache

from app.domain.parameter_catalog.loader import CatalogStore, default_store, verify_shipped_catalogs
from app.domain.parameter_catalog.profile import active_catalog_profiles
from app.domain.relay_import.identification import (
    ManufacturerAliases,
    ParameterSignature,
    RelayIdentificationDescriptor,
)
from app.domain.relay_import.profile import RelayProfileRegistry
from app.relay_profiles.hitachi_red670 import HitachiRed670Profile
from app.relay_profiles.micom_p441 import MicomP441Profile
from app.relay_profiles.siemens_7sa511 import Siemens7SA511Profile

SCHNEIDER = "Schneider Electric"
SIEMENS = "Siemens"
TOSHIBA = "Toshiba"
NR_ELECTRIC = "NR Electric"
HITACHI_ENERGY = "Hitachi Energy"

#: Canonical name -> other names it has been published under. The canonical
#: name is what the API exposes; the spelling found in a document is kept
#: separately in the result.
MANUFACTURER_ALIASES = ManufacturerAliases.from_mapping(
    {
        SCHNEIDER: ("Schneider", "Areva T&D", "Areva", "Alstom Grid", "Alstom"),
        SIEMENS: ("Siemens AG", "Siemens Energy"),
        TOSHIBA: ("Toshiba Energy Systems & Solutions", "Toshiba Corporation"),
        NR_ELECTRIC: ("NR Electric Co", "NARI"),
        HITACHI_ENERGY: ("Hitachi ABB Power Grids", "ABB Power Grids", "ABB", "Asea Brown Boveri"),
    }
)

_RELION_670_SIGNATURES = (
    ParameterSignature("hw-configuration-paths", r"^HW Configuration/", min_matches=2),
    ParameterSignature("function-block-operation", r"^[A-Z]{2,6}\d*:(?:Operation|OscRelease)$", min_matches=2),
)

IDENTIFICATION_DESCRIPTORS: tuple[RelayIdentificationDescriptor, ...] = (
    RelayIdentificationDescriptor(
        profile_id="schneider-micom-p441",
        manufacturer=SCHNEIDER,
        relay_family="MiCOM P44x",
        model="P441",
        model_patterns=(r"P441",),
        family_markers=(r"MiCOM",),
        parameter_signatures=(ParameterSignature("ddb-numbering", r"^DDB\s+\d+\s*-\s*\d+$", min_matches=2),),
    ),
    RelayIdentificationDescriptor(
        profile_id="siemens-7sa511",
        manufacturer=SIEMENS,
        relay_family="SIPROTEC 7SA5",
        model="7SA511",
        model_patterns=(r"7SA511",),
        family_markers=(r"DIGSI\s*V?3",),
    ),
    RelayIdentificationDescriptor(
        profile_id="siemens-7sa613",
        manufacturer=SIEMENS,
        relay_family="SIPROTEC 4 7SA6",
        model="7SA613",
        model_patterns=(r"7SA613\d?",),
        family_markers=(r"7SA6xx", r"DIGSI\s*4"),
    ),
    RelayIdentificationDescriptor(
        profile_id="siemens-siprotec5-7sl87",
        manufacturer=SIEMENS,
        relay_family="SIPROTEC 5",
        model="7SL87",
        model_patterns=(r"7SL87",),
        family_markers=(r"SIPROTEC\s*5", r"DIGSI\s*5"),
        parameter_signatures=(
            ParameterSignature("digsi5-address-numbers", r"(?<![\d.])\d{1,3}\.\d{3,4}\.\d{1,4}\.\d{3}(?![\d.])", target="text", min_matches=3),
        ),
    ),
    RelayIdentificationDescriptor(
        profile_id="toshiba-grl200",
        manufacturer=TOSHIBA,
        relay_family="GR200",
        model="GRL200",
        model_patterns=(r"GRL-?200",),
        parameter_signatures=(ParameterSignature("op-mode-id-names", r"^OP Mode (?:ID|Name)\d+$", min_matches=3),),
    ),
    RelayIdentificationDescriptor(
        profile_id="toshiba-grz100",
        manufacturer=TOSHIBA,
        relay_family="GRZ100",
        model="GRZ100",
        model_patterns=(r"GRZ-?100",),
        parameter_signatures=(
            ParameterSignature(
                "bracketed-section-markers",
                r"^\[(?:VERSION|STATUS|RECORD|PARAMETER|DESCRIPTION|DISCRIPTION|COMMUNICATION|BINARY INPUT|BINARY OUTPUT|ACTIVE GROUP)\]$",
                min_matches=3,
            ),
        ),
    ),
    RelayIdentificationDescriptor(
        profile_id="nr-rcs941",
        manufacturer=NR_ELECTRIC,
        relay_family="RCS-9xx",
        model="RCS-941",
        model_patterns=(r"RCS-?941",),
        parameter_signatures=(ParameterSignature("enable-switch-names", r"^En_[A-Za-z0-9]", min_matches=5),),
    ),
    RelayIdentificationDescriptor(
        profile_id="hitachi-red670",
        manufacturer=HITACHI_ENERGY,
        relay_family="Relion 670",
        model="RED670",
        model_patterns=(r"RED-?670",),
        parameter_signatures=_RELION_670_SIGNATURES,
    ),
    RelayIdentificationDescriptor(
        profile_id="hitachi-rel670",
        manufacturer=HITACHI_ENERGY,
        relay_family="Relion 670",
        model="REL670",
        model_patterns=(r"REL-?670",),
        parameter_signatures=_RELION_670_SIGNATURES,
    ),
    RelayIdentificationDescriptor(
        profile_id="hitachi-rel511",
        manufacturer=HITACHI_ENERGY,
        relay_family="REx5xx",
        model="REL511",
        model_patterns=(r"REL-?511",),
        parameter_signatures=(
            ParameterSignature("zone-reach-names", r"^(?:[XR][01]|RFN?)Z[1-5]$", min_matches=3),
            ParameterSignature("ct-vt-primary-names", r"^(?:CT|VT)Prim\s", min_matches=2),
        ),
    ),
    # Manufacturer intentionally not asserted for the two older lines below:
    # the project has not recorded it, and identification must not guess.
    RelayIdentificationDescriptor(
        profile_id="lfzp111",
        relay_family="LFZP",
        model="LFZP111",
        model_patterns=(r"LFZP-?111",),
        parameter_signatures=(ParameterSignature("kz-factor-names", r"^KZ(?:Ph|N|F|M|\d+[XY]?)(?:_PRIME)?$", min_matches=4),),
    ),
    RelayIdentificationDescriptor(
        profile_id="relz100",
        relay_family="RELZ 100",
        model="RELZ100",
        model_patterns=(r"RELZ-?100",),
        parameter_signatures=(
            ParameterSignature("reference-group-names", r"^(?:Ref_(?:Id|Transf|Line)|AddFu_[A-Za-z]+):", min_matches=4),
        ),
    ),
)


def build_registry(store: CatalogStore | None = None) -> RelayProfileRegistry:
    """A fresh registry: the identification catalogue plus the interpretation profiles that exist.

    Catalog-first (DEC-195): every *active* parameter catalog interprets the relay it describes. A relay
    that also has a hand-written profile (MiCOM P441, Hitachi RED670) is interpreted by the catalog for
    every target the catalog maps, with the hand-written profile demoted to an *extension* that supplies
    only what the catalog schema cannot yet express; a relay with a catalog and no profile needs no
    Python. A hand-written profile with no active catalog (Siemens 7SA511) is unchanged, and every other
    catalogued relay is identification-only. ``store`` overrides the shipped catalogs (tests)."""
    hand_written = (MicomP441Profile(), Siemens7SA511Profile(), HitachiRed670Profile())
    catalog_profiles = active_catalog_profiles(store or default_store(), hand_written)
    by_id = {p.profile_id: p for p in catalog_profiles}
    standalone_ids = {d.profile_id for d in IDENTIFICATION_DESCRIPTORS}
    for profile in catalog_profiles:
        profile.use_catalog_identification = profile.profile_id not in standalone_ids
    return RelayProfileRegistry(
        # a catalog-first relay keeps its place; a catalog-only relay follows the hand-written ones
        profiles=(
            *(by_id.get(p.profile_id, p) for p in hand_written),
            *(p for p in catalog_profiles if p.profile_id not in {h.profile_id for h in hand_written}),
        ),
        identification_descriptors=IDENTIFICATION_DESCRIPTORS,
        manufacturer_aliases=MANUFACTURER_ALIASES,
    )


@lru_cache(maxsize=1)
def default_registry() -> RelayProfileRegistry:
    """Shared read-only registry used by the upload service. Identification and
    interpretation are stateless, so one instance is safe across requests; do not
    register into it."""
    return build_registry(verify_shipped_catalogs())
