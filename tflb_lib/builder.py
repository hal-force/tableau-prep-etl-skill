"""
Top-level .tfl read/mutate/write pipeline.

A .tfl is a ZIP archive whose load-bearing member is `flow` (JSON). The
other members (`displaySettings`, `maestroMetadata`, `flowGraphThumbnail.svg`)
can be preserved verbatim; we never need to touch them.

`build()` reads a source .tfl, lets a caller-supplied list of mutators
edit the parsed flow JSON in place, and writes the result to a new .tfl.
Higher-level domain logic (e.g. "wire the invoice QA branch") composes
these mutators in the calling package.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Optional
from zipfile import ZIP_DEFLATED, ZipFile


# Type alias: a mutator takes the parsed flow dict, mutates it in place,
# and may return any JSON-serializable summary that gets included in the
# build report.
Mutator = Callable[[dict], Any]


def read_flow(src_tfl: Path) -> tuple[dict, dict[str, bytes]]:
    """Read a .tfl, return (parsed flow dict, all members as bytes).

    The caller mutates the flow dict and passes everything back to
    `write_flow()`.
    """
    members: dict[str, bytes] = {}
    with ZipFile(src_tfl, "r") as zin:
        for info in zin.infolist():
            members[info.filename] = zin.read(info.filename)
    if "flow" not in members:
        raise RuntimeError(f"{src_tfl} is not a valid .tfl (no 'flow' member)")
    flow = json.loads(members["flow"])
    return flow, members


def write_flow(flow: dict, members: dict[str, bytes], dst_tfl: Path) -> None:
    """Write the (mutated) flow back into a .tfl ZIP at dst_tfl."""
    dst_tfl.parent.mkdir(parents=True, exist_ok=True)
    members = dict(members)
    members["flow"] = json.dumps(flow, indent=2).encode("utf-8")

    tmp = dst_tfl.with_suffix(dst_tfl.suffix + ".tmp")
    with ZipFile(tmp, "w", ZIP_DEFLATED) as zout:
        for name, data in members.items():
            zout.writestr(name, data)
    tmp.replace(dst_tfl)


def build(
    src_tfl: Path,
    dst_tfl: Path,
    mutators: list[tuple[str, Mutator]],
) -> dict:
    """Apply each (label, mutator) in order to the source .tfl's flow JSON,
    write the result to dst_tfl, and return a build report.

    `mutators` is a list of (label, callable). The label is used in the
    return value so callers can see which mutator produced which summary.

    Returns:
        {"src": ..., "dst": ..., "results": {label: mutator_return_value, ...}}
    """
    flow, members = read_flow(src_tfl)
    results: dict[str, Any] = {}
    for label, mutator in mutators:
        results[label] = mutator(flow)
    write_flow(flow, members, dst_tfl)
    return {
        "src": str(src_tfl),
        "dst": str(dst_tfl),
        "results": results,
    }
