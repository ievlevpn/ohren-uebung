"""The glossary: prep/glossary.yaml + library techniques -> web/public/data/glossary.json.

Each entry defines one technique and lists its ``aliases`` (lower case): every technique
named in the library (the markings' ``techniques``) must be the alias of exactly one entry,
or the build fails. "Hear it in" is generated: the pieces whose techniques map to the entry,
in library order; ``hear_note`` may add a word per technique ("at the fourth").

An entry's ``example`` is a tiny piece drawn by the roll's own renderer. Its notes are
written in a compact notation (``"C4/1 D4 Eb4/.5 r/1"``: name, accidentals, octave with
C4 = 60, then ``/beats``; a duration carries over to the next note; ``r`` is a rest), and
its followers are derived with the canon engine, so the picture is musically exact::

    example:
      key: C                 # music21 key string for diatonic rules (lower case = minor)
      tempo: 60              # slow: the example is for listening closely
      voices: [{name: Comes, texture: hatch}, {name: Dux, texture: solid}]   # top first
      written: [{voice: 1, at: 0, notes: "C4/1 D4 E4", repeat?: {times: 3, step: 2}}]
      derived: [{from: 1, voice: 0, span?: [0, 8], rule: {delay: 2, interval: 4}}]
      marks: [{kind: entry, start: 0, end: 4, voice: 1, label: subject}]
      caption: "..."

``rule`` takes the fields of ``canon.Rule``; ``diatonic`` defaults to true and ``key`` to
the example's key. ``span`` limits the leader to the notes starting in [start, end).
Derived voices are computed in order, so a later rule may imitate an earlier follower.
"""
import re
from dataclasses import asdict
from pathlib import Path

import yaml

from .canon import Rule, derive, expand_leader
from .model import Mark, Note, Thread, Voice, instruments_for, pan_for
from .validate import validate_piece

PREP = Path(__file__).resolve().parent.parent
GLOSSARY = PREP / "glossary.yaml"


class GlossaryError(Exception):
    """The glossary cannot be built (bad notation, unmapped technique, bad example)."""


_STEP = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_NOTE = re.compile(r"^(?:([A-G])([#b♯♭]*)(-?\d)|r)(?:/(\d*\.?\d+))?$")


def parse_notes(text: str, at: float = 0) -> list[tuple[int, float, float]]:
    """``"C4/1 D4 Eb4/.5 r/1"`` -> [(pitch, start, duration)], starting at beat ``at``."""
    out: list[tuple[int, float, float]] = []
    t, dur = float(at), 1.0
    for tok in text.split():
        m = _NOTE.match(tok)
        if not m:
            raise GlossaryError(f"cannot read the note '{tok}' in '{text}'")
        letter, acc, octave, d = m.groups()
        if d is not None:
            dur = float(d)
        if letter is not None:
            alt = sum(1 if c in "#♯" else -1 for c in acc)
            p = 12 * (int(octave) + 1) + _STEP[letter] + alt
            out.append((p, _num(t), _num(dur)))
        t += dur
    return out


def _num(x: float) -> float:
    return int(x) if float(x).is_integer() else x


def load_glossary(path: Path = GLOSSARY) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def _rule(spec: dict, key: str) -> Rule:
    known = {"delay", "interval", "diatonic", "key", "invert_about", "retrograde", "stretch",
             "per_tonos_step", "repeats", "exceptions", "pitch_tolerance"}
    extra = set(spec) - known
    if extra:
        raise GlossaryError(f"unknown rule fields {sorted(extra)}")
    return Rule(delay=spec.get("delay", 0), interval=spec.get("interval", 0),
                diatonic=spec.get("diatonic", True), key=spec.get("key", key),
                invert_about=spec.get("invert_about"), retrograde=spec.get("retrograde", False),
                stretch=spec.get("stretch", 1), per_tonos_step=spec.get("per_tonos_step", 0),
                repeats=spec.get("repeats", 1), exceptions=dict(spec.get("exceptions", {})),
                pitch_tolerance=spec.get("pitch_tolerance", 0))


def build_example(eid: str, ex: dict) -> dict:
    """The example as a piece dict (the shape of web/src/model.ts ``Piece``) plus its caption."""
    n = len(ex["voices"])
    ensemble = ex.get("ensemble", "chamber")
    names = [v.get("instrument", d) for v, d in zip(ex["voices"], instruments_for(ensemble, n))]
    by_voice: list[list[Note]] = [[] for _ in range(n)]
    for w in ex.get("written", []):
        line = [Note(w["voice"], p, s, d) for p, s, d in parse_notes(w["notes"], w.get("at", 0))]
        rep = w.get("repeat")
        if rep:
            line = expand_leader(line, _rule({"repeats": rep["times"],
                                              "per_tonos_step": rep["step"]}, ex["key"]))
        by_voice[w["voice"]] += line
    links: list[tuple[Note, Note, Thread]] = []
    for d in ex.get("derived", []):
        rule = _rule(d["rule"], ex["key"])
        v, f = d["from"], d["voice"]
        span = d.get("span")
        leader = sorted((x for x in by_voice[v] if span is None or span[0] <= x.s < span[1]),
                        key=lambda x: x.s)
        if not leader:
            raise GlossaryError(f"{eid}: the leader (voice {v}) has no notes")
        notes, threads = derive(leader, rule, f)
        if rule.repeats > 1:  # a perpetual canon: the leader's voice holds every pass
            if span is not None or len(leader) != len(by_voice[v]):
                raise GlossaryError(f"{eid}: a repeating rule takes the whole leader voice")
            leader = by_voice[v] = expand_leader(leader, rule)
        by_voice[f] += notes
        links += [(leader[t.a], notes[t.b], t) for t in threads]

    flat = sorted((x for vs in by_voice for x in vs), key=lambda x: (x.s, x.v))
    index = {id(x): i for i, x in enumerate(flat)}
    threads = [Thread(index[id(a)], index[id(b)], t.kind, t.broken, t.adjusted)
               for a, b, t in links]
    threads.sort(key=lambda t: (flat[t.b].s, t.a))
    marks = sorted((Mark(**m) for m in ex.get("marks", [])), key=lambda m: (m.start, m.kind))
    out = {
        "id": f"glossary-{eid}", "title": "", "collection": "", "catalogue": "",
        "key": ex["key"], "tempo": ex.get("tempo", 60), "beatsPerBar": ex.get("beats_per_bar", 4),
        "ensemble": ensemble,
        "voices": [asdict(Voice(v["name"], v["texture"], names[i], pan_for(i, n)))
                   for i, v in enumerate(ex["voices"])],
        "notes": [{k: val for k, val in asdict(x).items() if k != "c"} for x in flat],
        "threads": [asdict(t) for t in threads],
        "marks": [{k: val for k, val in asdict(m).items() if val is not None} for m in marks],
        "captions": [], "techniques": [], "listenFor": "",
        "caption": ex["caption"],
    }
    problems = validate_piece(out)
    if problems:
        raise GlossaryError("\n  ".join(problems))
    return out


ENTRY_FIELDS = {"id", "title", "also", "aliases", "short", "text", "related", "hear_note",
                "example", "unlinked", "pieces_from"}


def build_glossary(raw: dict, library: dict, generated: dict[str, list[str]] | None = None) -> dict:
    """The glossary as written to glossary.json: entries in alphabetical order, each with
    its pieces and ``links`` (the aliases a caption may link: all but ``unlinked``, which
    are also ordinary words), ``techniques`` (library technique -> entry id) and
    ``ordinary`` (phrases where a linkable alias is an ordinary word; the linker skips them).

    An entry with ``pieces_from: <name>`` lists ``generated[name]`` (piece ids, e.g. the
    pieces whose markings declare free music) instead of pieces by technique."""
    generated = generated or {}
    entries = raw["entries"]
    owner: dict[str, str] = {}
    for e in entries:
        extra = set(e) - ENTRY_FIELDS
        if extra:
            raise GlossaryError(f"{e.get('id')}: unknown fields {sorted(extra)}")
        for a in e["aliases"]:
            if a != a.lower():
                raise GlossaryError(f"{e['id']}: alias '{a}' must be lower case")
            if a in owner:
                raise GlossaryError(f"alias '{a}' belongs to both {owner[a]} and {e['id']}")
            owner[a] = e["id"]
    ids = {e["id"] for e in entries}
    techniques: dict[str, str] = {}
    for t in library["techniques"]:
        if t.lower() not in owner:
            raise GlossaryError(f"library technique '{t}' is not an alias of any glossary entry")
        techniques[t] = owner[t.lower()]
    order = {p["id"]: i for i, p in enumerate(library["pieces"])}
    out = []
    for e in sorted(entries, key=lambda e: e["title"].lower()):
        for r in e.get("related", []):
            if r not in ids or r == e["id"]:
                raise GlossaryError(f"{e['id']}: related '{r}' is not another entry")
        notes = e.get("hear_note", {})
        for t in notes:
            if t not in e["aliases"]:
                raise GlossaryError(f"{e['id']}: hear_note '{t}' is not one of its aliases")
        for a in e.get("unlinked", []):
            if a not in e["aliases"]:
                raise GlossaryError(f"{e['id']}: unlinked '{a}' is not one of its aliases")
        pieces: dict[str, dict] = {}
        source = e.get("pieces_from")
        if source is not None:
            if source not in generated:
                raise GlossaryError(f"{e['id']}: no generated piece list '{source}'")
            for pid in generated[source]:
                if pid in order:
                    pieces[pid] = {"id": pid}
        for t, pids in library["techniques"].items():
            if techniques[t] != e["id"]:
                continue
            for pid in pids:
                item = pieces.setdefault(pid, {"id": pid})
                if t.lower() in notes:
                    item["note"] = notes[t.lower()]
        entry = {
            "id": e["id"], "title": e["title"], "also": e.get("also", ""),
            "aliases": list(e["aliases"]),
            "links": [a for a in e["aliases"] if a not in e.get("unlinked", [])],
            "short": e["short"].strip(), "text": e["text"].strip(),
            "related": list(e.get("related", [])),
            "pieces": sorted(pieces.values(), key=lambda x: order[x["id"]]),
        }
        if "example" in e:
            try:
                entry["example"] = build_example(e["id"], e["example"])
            except (KeyError, ValueError, IndexError) as err:
                raise GlossaryError(f"{e['id']}: example: {err!r}") from err
        out.append(entry)
    return {"entries": out, "techniques": techniques, "ordinary": list(raw.get("ordinary", []))}
