"""Consistency checks on a piece dict (as written to JSON)."""
import math

from .model import ENSEMBLES, MARK_KINDS, TEXTURES, THREAD_KINDS


def validate_piece(piece: dict) -> list[str]:
    pid = piece.get("id", "?")
    bpb = piece.get("beatsPerBar") or 4
    notes = piece.get("notes", [])
    voices = piece.get("voices", [])
    problems: list[str] = []

    pickup = piece.get("pickup", 0)

    def bar(beat: float) -> int:
        return math.floor((beat - pickup) / bpb) + 1

    def add(msg: str, beat: float | None = None) -> None:
        where = f"bar {bar(beat)}: " if beat is not None else ""
        problems.append(f"{pid}: {where}{msg}")

    if piece.get("ensemble") not in ENSEMBLES:
        add(f"unknown ensemble '{piece.get('ensemble')}'")
    for i, v in enumerate(voices):
        if v.get("texture") not in TEXTURES:
            add(f"voice {i} has unknown texture '{v.get('texture')}'")
    if not notes:
        add("piece has no notes")
    end = max((n["s"] + n["d"] for n in notes), default=0)

    prev = None
    for i, n in enumerate(notes):
        if not 0 <= n["v"] < len(voices):
            add(f"note {i} uses missing voice {n['v']}", n["s"])
        if not 0 <= n["p"] <= 127:
            add(f"note {i} has pitch {n['p']} outside MIDI range", n["s"])
        if "c" in n and not isinstance(n["c"], bool):
            add(f"note {i} has a non-boolean 'c'", n["s"])
        if n["d"] <= 0:
            add(f"note {i} has non-positive duration", n["s"])
        if prev is not None and n["s"] < prev:
            add(f"note {i} is not sorted by start", n["s"])
        prev = n["s"]

    for i, t in enumerate(piece.get("threads", [])):
        for end_name in ("a", "b"):
            idx = t[end_name]
            if not 0 <= idx < len(notes):
                add(f"thread {i} → note {idx} does not exist")
        if t.get("kind") not in THREAD_KINDS:
            add(f"thread {i} has unknown kind '{t.get('kind')}'")

    for i, m in enumerate(piece.get("marks", [])):
        if m.get("kind") not in MARK_KINDS:
            add(f"mark {i} has unknown kind '{m.get('kind')}'", m["start"])
        if m["end"] < m["start"]:
            add(f"mark {i} ends before it starts", m["start"])
        if m["end"] > end:
            add(f"mark {i} runs beyond the end", m["start"])
        v = m.get("voice")
        if v is not None and not 0 <= v < len(voices):
            add(f"mark {i} uses missing voice {v}", m["start"])

    for i, c in enumerate(piece.get("captions", [])):
        if c["at"] < 0 or c["at"] > end:
            add(f"caption at {c['at']} is beyond the end", c["at"])
    return problems
