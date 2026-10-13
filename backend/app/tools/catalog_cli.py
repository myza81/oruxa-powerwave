"""Parameter-catalog administrator workflow, on the command line.

    edit JSON  ->  validate  ->  dry-run against a real sheet  ->  make available (set "lifecycle": "active")

    python -m app.tools.catalog_cli validate-catalog <catalog.json> [--root DIR]
    python -m app.tools.catalog_cli dry-run <catalog.json> <relay-settings.pdf> [--root DIR] [--json]
    python -m app.tools.catalog_cli list [--root DIR]

``validate-catalog`` checks the file exactly as the service would load it -- schema, canonical targets,
transformations, units, enums, duplicate / conflicting mappings, relay / model / firmware applicability
against the catalogs already installed, the semantic lock -- and names every problem with its location
(``mappings[3] (vendor.x_reach).transform[0]``). ``dry-run`` reads a real PDF through the catalog and
reports what would be recognised, mapped, transformed, unmapped and conflicting. Neither command changes
the catalog tree or any application state. Exit status 0 = valid, 1 = invalid, 2 = usage / input error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.domain.parameter_catalog.dry_run import dry_run, render_text, to_dict
from app.domain.parameter_catalog.loader import CATALOG_ROOT, REGISTRY_FILE, load_registry, load_store, validate_catalog_file
from app.domain.relay_import.raw_document import RawRelayDocument


def _validate(args: argparse.Namespace) -> int:
    result = validate_catalog_file(Path(args.catalog), Path(args.root))
    if not result.ok:
        print(f"INVALID: {result.path}")
        for issue in result.issues:
            print(f"  - {result.locate(issue)}: [{issue.code}] {issue.message}")
        print(f"{len(result.issues)} problem(s). The catalog was not used.")
        return 1
    c = result.catalog
    print(f"OK: {c.catalog_id} {c.version} ({c.lifecycle}) -- {len(c.mappings)} mappings, "
          f"{len({m.canonical for m in c.mappings})} canonical targets, relay {c.applicability.manufacturer} "
          f"{c.applicability.model}, firmware {', '.join(c.applicability.versions)}")
    if c.lifecycle != "active":
        print(f'It is "{c.lifecycle}": the service will not use it until "lifecycle" is "active".')
    return 0


def _read_document(path: Path) -> RawRelayDocument:
    if path.suffix.lower() != ".pdf":
        raise ValueError("only PDF relay settings sheets are supported")
    from app.services.relay_pdf_extractor import PdfExtractionStatus, extract_pdf

    result = extract_pdf(path.read_bytes())
    if result.status is PdfExtractionStatus.UNREADABLE or result.document is None:
        raise ValueError("the PDF could not be read")
    return result.document


def _dry_run(args: argparse.Namespace) -> int:
    check = validate_catalog_file(Path(args.catalog), Path(args.root))
    if check.catalog is None:
        print(f"INVALID: {check.path}", file=sys.stderr)
        for issue in check.issues:
            print(f"  - {check.locate(issue)}: [{issue.code}] {issue.message}", file=sys.stderr)
        return 1
    try:
        document = _read_document(Path(args.document))
    except (OSError, ValueError) as exc:
        print(f"cannot read the document: {exc}", file=sys.stderr)
        return 2
    registry = load_registry(Path(args.root) / REGISTRY_FILE)
    report = dry_run(check.catalog, registry, document)
    print(json.dumps(to_dict(report), indent=2, ensure_ascii=False) if args.json else render_text(report))
    return 1 if report.conflicting and args.fail_on_conflict else 0


def _list(args: argparse.Namespace) -> int:
    store = load_store(Path(args.root))
    for c in sorted(store.catalogs, key=lambda c: (c.catalog_id, c.version)):
        print(f"{c.catalog_id} {c.version}  {c.lifecycle:<9} {c.applicability.manufacturer} {c.applicability.model}")
    for r in store.rejected:
        print(f"REJECTED {r}")
    return 1 if store.rejected else 0


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):                 # Ω, ÷ and − must not crash a Windows console
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(prog="catalog_cli", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn, help_ in (
        ("validate-catalog", _validate, "validate a catalog file (changes nothing)"),
        ("dry-run", _dry_run, "show what a catalog does with a real PDF (changes nothing)"),
        ("list", _list, "list the installed catalogs and any rejected ones"),
    ):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--root", default=str(CATALOG_ROOT), help="catalog tree (default: the installed one)")
        p.set_defaults(fn=fn)
        if name != "list":
            p.add_argument("catalog", help="path of the catalog JSON file")
        if name == "dry-run":
            p.add_argument("document", help="path of the relay settings PDF")
            p.add_argument("--json", action="store_true", help="machine-readable output")
            p.add_argument("--fail-on-conflict", action="store_true", help="exit 1 when any value conflicts")
    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
