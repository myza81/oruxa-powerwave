"""Structured diff and patch for the NF-3D approved-changes manifest (not a test module).

`structured_diff(before, after)` lists every difference between two JSON-like trees as `(path, before, after)` where `path` is a tuple of
dict keys and list indexes, and `ABSENT` stands for "no such key". A value of a different type is one entry at that node (for example an HTTP
500 body, a string, becoming a response object). `apply_entries` replays entries onto a tree and refuses an entry whose recorded "before" is not
what the tree holds, so a manifest can never silently approve something it did not describe.
"""

from __future__ import annotations

import copy
from typing import Any

ABSENT = {"__absent__": True}


def _is_absent(value: Any) -> bool:
    return isinstance(value, dict) and value == ABSENT


def structured_diff(before: Any, after: Any, path: tuple = ()) -> list[tuple[tuple, Any, Any]]:
    if isinstance(before, dict) and isinstance(after, dict):
        out: list = []
        for key in sorted(set(before) | set(after)):
            if key not in before:
                out.append((path + (key,), ABSENT, after[key]))
            elif key not in after:
                out.append((path + (key,), before[key], ABSENT))
            else:
                out += structured_diff(before[key], after[key], path + (key,))
        return out
    if isinstance(before, list) and isinstance(after, list) and len(before) == len(after):
        out = []
        for i, (b, a) in enumerate(zip(before, after)):
            out += structured_diff(b, a, path + (i,))
        return out
    if before == after and type(before) is type(after):
        return []
    return [(path, before, after)]


def _walk(tree: Any, path: tuple) -> tuple[Any, Any]:
    node = tree
    for token in path[:-1]:
        node = node[token]
    return node, path[-1]


def apply_entries(tree: Any, entries: list[dict]) -> Any:
    """A copy of `tree` with each entry applied; raises if an entry's recorded `before` does not match."""
    out = copy.deepcopy(tree)
    for entry in entries:
        path = tuple(entry["path"])
        parent, leaf = _walk(out, path)
        before, after = entry["before"], entry["after"]
        present = (leaf in parent) if isinstance(parent, dict) else True
        if _is_absent(before):
            if present:
                raise AssertionError(f"approved change {path!r} adds a field that already exists")
        elif not present or parent[leaf] != before:
            raise AssertionError(f"approved change {path!r}: the recorded 'before' does not match the tree")
        if _is_absent(after):
            del parent[leaf]
        else:
            parent[leaf] = copy.deepcopy(after)
    return out
