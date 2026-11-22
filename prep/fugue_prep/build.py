"""Markings + sources -> web/public/data/pieces/<id>.json, library.json and glossary.json.

Run: ``cd prep && uv run python -m fugue_prep.build``.

Notes in a piece are sorted by start, then voice; thread indices point into that list
(the canon engine's local indices are remapped here). For a canon with ``repeats > 1``
the leader in the piece is the expanded leader (every pass), and every other written
voice repeats with it (same period and rise). A canon is a list of sections (leader,
followers, optional span); score canons whose voices swap roles have several. Collections without books get one unnamed
book (name ``""``) holding all their pieces.
"""
import json
import math
from dataclasses import asdict, replace
from pathlib import Path

import yaml

from .canon import Rule, derive, expand_leader, is_not_imitation, match
from .glossary import build_glossary, load_glossary
from .fugue import STRETCH, EntryMismatch, entry_reference, find_entry
from .kern import read_kern
from .markings import load_collections, load_markings
from .model import (INSTRUMENT_RANGES, Caption, Collection, Library, Mark, Note, Piece,
                    PieceSummary, ScoreVoices, Thread, Voice, instruments_for, pan_for)
from .sources import REPOS, SOURCES, fetch_repo
from .validate import validate_piece

PREP = Path(__file__).resolve().parent.parent
MARKINGS = PREP / "markings"
WEB_DATA = PREP.parent / "web" / "public" / "data"


class BuildError(Exception):
    """A piece cannot be built (source, canon check, fugue entry, validation)."""


def computed(m: dict) -> bool:
    """The followers are derived from the rule (a transcription of the written voices),
    not read from a score (kern, mutopia, or a transcription with ``score: true``)."""
    return m["source"]["kind"] in ("transcription", "generated") and not m["source"].get("score")


def _followers(m: dict) -> set[int]:
    return {f["voice"] for sec in m["canon"] or [] for f in sec["followers"]}


def scope(rule: Rule, span: tuple[float, float] | None) -> Rule:
    """The rule limited to a section: leader notes outside ``span`` count as free."""
    if span is None:
        return rule
    return replace(rule, free=(*rule.free, (-math.inf, span[0]), (span[1], math.inf)))


def counted(leader: list[Note], rule: Rule) -> int:
    """Leader notes the follower must answer: those not in a free range. A note with no
    answer in the score (no thread) is a miss, like a broken thread. Notes at a
    ``not_imitation`` beat are not counted."""
    return sum(not any(lo <= x.s < hi for lo, hi in rule.free)
               and not is_not_imitation(x.s, rule) for x in leader)


def load_voices(m: dict, markings_dir: Path = MARKINGS, secondary: bool = False) -> ScoreVoices:
    """The source's voices: every voice for kern/mutopia and score transcriptions, the
    written (non-follower) voices for other transcription/generated sources. Each note's
    ``v`` is its piece voice index.
    Only primary notes unless ``secondary`` (kern: lower chord tones and split-off
    lines, ``c=True``)."""
    src, path = m["source"], m["file"]
    kind = src["kind"]
    if kind == "kern":
        repo = src["path"].split("/", 1)[0]
        if repo in REPOS:
            fetch_repo(repo)
        warnings: list[str] = []
        voices = read_kern(SOURCES / src["path"], alternatives=src.get("alternatives", []),
                           warnings=warnings, commented_from=src.get("commented_from"))
        if not secondary:
            voices = [[x for x in notes if not x.c] for notes in voices]
        for w in warnings:
            print(f"warning: {w}")
        bpq = src.get("beats_per_quarter", 1)
        if bpq != 1:
            voices = [[replace(x, s=x.s * bpq, d=x.d * bpq) for x in notes] for notes in voices]
        unit = src.get("beat_unit", 1)
        if unit != 1:  # divide (not multiply by 1/unit): whole-beat onsets stay exact
            voices = [[replace(x, s=x.s / unit, d=x.d / unit) for x in notes] for notes in voices]
        return voices
    if kind == "mutopia":
        from .lily import fetch_mutopia, render_voices
        from .midi import read_midi
        midi = render_voices(fetch_mutopia(src["path"]))
        return read_midi(midi, beats_per_quarter=src.get("beats_per_quarter", 1))
    file = markings_dir.parent / src["path"]
    if not file.exists():
        raise BuildError(f"{path}: source file {file} does not exist")
    raw = yaml.safe_load(file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("voices"), list):
        raise BuildError(f"{file}: expected 'voices: [[[midi, start, duration], ...], ...]'")
    written = [i for i in range(len(m["voices"])) if not computed(m) or i not in _followers(m)]
    if src.get("score") and len(raw["voices"]) != len(written):
        raise BuildError(f"{file}: has {len(raw['voices'])} voices; a score transcription "
                         f"holds every piece voice ({len(written)})")
    if len(raw["voices"]) != len(written):
        raise BuildError(f"{file}: has {len(raw['voices'])} voices, {path} needs "
                         f"{len(written)} written voices ({written})")
    return [_notes(file, f"voices[{k}]", v, notes)
            for k, (v, notes) in enumerate(zip(written, raw["voices"]))]


def _notes(file: Path, where: str, v: int, notes) -> list[Note]:
    if not isinstance(notes, list):
        raise BuildError(f"{file}: {where}: expected a list of [midi, start, duration]")
    out = []
    for j, t in enumerate(notes):
        if (not isinstance(t, list) or len(t) != 3 or not isinstance(t[0], int)
                or not all(isinstance(x, (int, float)) for x in t[1:]) or t[2] <= 0):
            raise BuildError(f"{file}: {where}[{j}]: expected [midi, start, duration], got {t!r}")
        out.append(Note(v, t[0], float(t[1]), float(t[2])))
    return sorted(out, key=lambda n: n.s)


def load_ending(m: dict, markings_dir: Path = MARKINGS) -> tuple[float | None, ScoreVoices]:
    """A transcription's optional ending: ``end`` (beat where every voice stops) and
    ``coda`` (closing notes, one list per *piece* voice, followers included, absolute
    beats). Perpetual canons need both: the rule would run on, and the closing cadence
    is not imitation."""
    if m["source"]["kind"] not in ("transcription", "generated"):
        return None, []
    file = markings_dir.parent / m["source"]["path"]
    raw = yaml.safe_load(file.read_text(encoding="utf-8"))
    end, coda = raw.get("end"), raw.get("coda", [])
    if end is None:
        if coda:
            raise BuildError(f"{file}: a coda needs 'end'")
        return None, []
    if isinstance(end, bool) or not isinstance(end, (int, float)):
        raise BuildError(f"{file}: end: expected a beat, got {end!r}")
    if coda and (not isinstance(coda, list) or len(coda) != len(m["voices"])):
        raise BuildError(f"{file}: coda: expected one note list per piece voice "
                         f"({len(m['voices'])})")
    return float(end), [_notes(file, f"coda[{v}]", v, ns) for v, ns in enumerate(coda)]


def _repeat(notes: list[Note], period: float, step: int, repeats: int) -> list[Note]:
    return [replace(n, p=n.p + r * step, s=n.s + r * period)
            for r in range(repeats) for n in notes]


def _cut(by_voice: list[list[Note]], threads: list[tuple[int, int, Thread]], end: float):
    """Drop notes starting at or after ``end``, shorten those sounding past it, and keep
    only threads whose two notes remain (thread indices are remapped)."""
    keep: list[dict[int, int]] = []
    out: list[list[Note]] = []
    for notes in by_voice:
        kept, idx = [], {}
        for i, x in enumerate(notes):
            if x.s < end - 1e-9:
                idx[i] = len(kept)
                kept.append(replace(x, d=min(x.d, end - x.s)))
        keep.append(idx)
        out.append(kept)
    cut = [(va, vb, replace(t, a=keep[va][t.a], b=keep[vb][t.b])) for va, vb, t in threads
           if t.a in keep[va] and t.b in keep[vb]]
    return out, cut


def build_piece(m: dict, collection: str, markings_dir: Path = MARKINGS) -> dict:
    pid, n = m["id"], len(m["voices"])
    full = load_voices(m, markings_dir, secondary=True)
    # entries and canons see primary notes only; secondary ones join just before the end
    src = [[x for x in notes if not x.c] for notes in full]
    extra = [[x for x in notes if x.c] for notes in full]
    canon, fugue = m["canon"], m["fugue"]
    derived = computed(m)
    by_voice: list[list[Note]] = [[] for _ in range(n)]
    if derived:
        written = [v for v in range(n) if v not in _followers(m)]
        for v, notes in zip(written, src):
            by_voice[v] = notes
    else:
        if len(src) != n:
            raise BuildError(f"{m['file']}: the source has {len(src)} voices, the markings {n}")
        by_voice = [[replace(x, v=v) for x in notes] for v, notes in enumerate(src)]

    local_threads: list[tuple[int, int, Thread]] = []  # (leader voice, follower voice, thread)
    for sec in canon or []:
        lv = sec["leader"]
        leader = by_voice[lv]
        if not leader:
            raise BuildError(f"{pid}: the leader (voice {lv}) has no notes")
        if derived:
            rule0 = sec["followers"][0]["rule"]
            if rule0.repeats > 1:
                s0 = min(x.s for x in leader)
                period = max(x.s + x.d for x in leader) - s0
                for v in range(n):
                    if v == lv:
                        by_voice[v] = expand_leader(leader, rule0)
                    elif by_voice[v]:
                        by_voice[v] = _repeat(by_voice[v], period, rule0.per_tonos_step,
                                              rule0.repeats)
            for f in sec["followers"]:
                try:
                    notes, threads = derive(leader, f["rule"], f["voice"])
                except (IndexError, ValueError) as e:
                    raise BuildError(f"{pid}: follower voice {f['voice']}: {e}") from e
                by_voice[f["voice"]] = notes
                local_threads += [(lv, f["voice"], t) for t in threads]
        else:
            for f in sec["followers"]:
                rule = scope(f["rule"], sec["span"])
                try:
                    threads = match(leader, by_voice[f["voice"]], rule, f["tolerance_beats"])
                except ValueError as e:
                    raise BuildError(f"{pid}: follower voice {f['voice']}: {e}") from e
                good, total = sum(not t.broken for t in threads), counted(leader, rule)
                if not total or good / total < f["min_match"]:
                    raise BuildError(f"{pid}: follower voice {f['voice']} imitates the leader "
                                     f"(voice {lv}) in {good} of {total} non-free notes, below "
                                     f"min_match {f['min_match']:.0%}")
                local_threads += [(lv, f["voice"], t) for t in threads]

    # secondary notes join their voices before an ending cuts them
    if derived:
        written = [v for v in range(n) if v not in _followers(m)]
        extra_by = {v: ns for v, ns in zip(written, extra)}
    else:
        extra_by = dict(enumerate(extra))
    for v, ns in extra_by.items():
        by_voice[v] = by_voice[v] + [replace(x, v=v) for x in ns]

    end, coda = load_ending(m, markings_dir)
    if end is not None:
        by_voice, local_threads = _cut(by_voice, local_threads, end)
        for v, notes in enumerate(coda):
            by_voice[v] = sorted(by_voice[v] + notes, key=lambda x: x.s)

    # global order: by start, then voice
    order = sorted(((x.s, v, i) for v, notes in enumerate(by_voice) for i, x in enumerate(notes)))
    gidx = [[0] * len(notes) for notes in by_voice]
    flat: list[Note] = []
    for g, (_, v, i) in enumerate(order):
        gidx[v][i] = g
        flat.append(by_voice[v][i])
    threads = [replace(t, a=gidx[va][t.a], b=gidx[vb][t.b]) for va, vb, t in local_threads]
    threads.sort(key=lambda t: (flat[t.b].s, t.a))

    marks = [Mark(**mk) for mk in m["marks"]]
    if fugue:
        bpb = m["beats_per_bar"]
        groups: dict[str, list[Mark]] = {}
        for e in fugue["entries"]:
            try:
                ref = entry_reference(by_voice, fugue, e, piece=pid, beats_per_bar=bpb,
                                      pickup=m.get("pickup", 0))
                idx = find_entry(by_voice, ref, e["voice"], e["start"], e["transform"],
                                 piece=pid, beats_per_bar=bpb, pickup=m.get("pickup", 0),
                                 head=e["head"], tail=e["tail"], head_length=e["head_length"], octave=e.get("octave", ()))
            except EntryMismatch as err:
                raise BuildError(str(err)) from err
            factor = STRETCH[e["transform"]]
            # a free head may be tied over from before the statement's place
            begin = min(e["start"], by_voice[e["voice"]][idx[0]].s)
            end = by_voice[e["voice"]][idx[-1]].s + ref[len(idx) - 1].d * factor
            label = e["form"]
            if e.get("subject"):  # a fugue on several subjects: "subject II", "answer III"
                label += f" {e['subject']}"
            if e["transform"] != "none":
                label += f" {e['transform']}"
            if e["part"] == "head":
                label += " (head)"
            mk = Mark("entry", begin, end, voice=e["voice"], label=label)
            marks.append(mk)
            if e["stretto"] is not None:
                groups.setdefault(e["stretto"], []).append(mk)
        for g, ms in groups.items():
            marks.append(Mark("stretto", min(x.start for x in ms), max(x.end for x in ms), label=g))
    marks.sort(key=lambda x: (x.start, x.kind))

    names = [v.get("instrument", d) for v, d in
             zip(m["voices"], instruments_for(m["ensemble"], n))]
    for v, name in enumerate(names):
        ps = [x.p for x in by_voice[v]]
        lo, hi = INSTRUMENT_RANGES[name]
        if ps and (min(ps) < lo or max(ps) > hi):
            raise BuildError(f"{pid}: voice {v} ({m['voices'][v]['name']}) on {name}: lowest "
                             f"{min(ps)}, highest {max(ps)}, outside its range {lo}-{hi}; "
                             f"give the voice an instrument in the markings")
    piece = Piece(
        id=pid, title=m["title"], collection=collection, catalogue=m["catalogue"], key=m["key"],
        tempo=m["tempo"], beatsPerBar=m["beats_per_bar"], ensemble=m["ensemble"],
        voices=[Voice(v["name"], v["texture"], names[i], pan_for(i, n))
                for i, v in enumerate(m["voices"])],
        notes=flat, threads=threads, marks=marks,
        captions=sorted((Caption(**c) for c in m["captions"]), key=lambda c: c.at),
        techniques=list(m["techniques"]), listenFor=m["listen_for"],
        beatUnit=m["source"].get("beat_unit", 1 / m["source"].get("beats_per_quarter", 1)), pickup=m.get("pickup", 0),
        glossaryNotes=dict(m["glossary_notes"]))
    out = asdict(piece)
    if not out["glossaryNotes"]:  # only pieces with notes carry the field
        del out["glossaryNotes"]
    for x in out["notes"]:  # "c" only on secondary notes
        if not x["c"]:
            del x["c"]
    problems = validate_piece(out)
    if problems:
        raise BuildError(f"{m['file']}:\n  " + "\n  ".join(problems))
    return out


def build_library(collections: list[dict], built: list[tuple[dict, dict]]) -> dict:
    """``built``: (markings, piece dict) pairs in reading order."""
    def sort_key(pair):
        m, _ = pair
        return (m.get("order", math.inf), m["file"].name)

    cols = []
    summaries = []
    for col in collections:
        mine = sorted((b for b in built if b[1]["collection"] == col["id"]), key=sort_key)
        names = col["books"] or [""]
        books = {name: [] for name in names}
        for m, p in mine:
            book = m.get("book")
            if book is None:
                if len(names) > 1:
                    raise BuildError(f"{m['file']}: collection '{col['id']}' has books "
                                     f"{names}; say which with 'book'")
                book = names[0]
            if book not in books:
                raise BuildError(f"{m['file']}: book '{book}' is not one of {names}")
            books[book].append(p["id"])
            end = max(x["s"] + x["d"] for x in p["notes"])
            summaries.append(PieceSummary(
                id=p["id"], title=p["title"], collection=col["id"], catalogue=p["catalogue"],
                key=p["key"], voices=len(p["voices"]),
                bars=math.ceil((end - p["pickup"]) / p["beatsPerBar"]),
                techniques=p["techniques"], listenFor=p["listenFor"], number=m.get("number")))
        cols.append(Collection(id=col["id"], numeral=col["numeral"], name=col["name"],
                               catalogue=col["catalogue"], note=col["note"],
                               books=[{"name": k, "pieces": v} for k, v in books.items()]))
    techniques: dict[str, list[str]] = {}
    for s in summaries:
        for t in s.techniques:
            techniques.setdefault(t, []).append(s.id)
    out = asdict(Library(collections=cols, pieces=summaries,
                         techniques={t: techniques[t] for t in sorted(techniques)}))
    for x in out["pieces"]:  # "number" only where the markings give one
        if x["number"] is None:
            del x["number"]
    return out


def free_passage_pieces(markings_dir: Path = MARKINGS) -> list[str]:
    """Pieces whose markings declare music outside the imitation: a canon rule's ``free``
    ranges, or Bach's own ending (a transcription's ``end`` + coda). An ending marked
    ``editorial: true`` (a recording's closing chord on a perpetual canon) does not count."""
    out = []
    for f in sorted(Path(markings_dir).glob("*/*.yaml")):
        m = load_markings(f)
        rules = [fl["rule"] for sec in m["canon"] or [] for fl in sec["followers"]]
        if any(r.free for r in rules) or (load_ending(m, markings_dir)[0] is not None
                                          and not _editorial_ending(m, markings_dir)):
            out.append(m["id"])
    return out


def _editorial_ending(m: dict, markings_dir: Path) -> bool:
    raw = yaml.safe_load((markings_dir.parent / m["source"]["path"]).read_text(encoding="utf-8"))
    flag = raw.get("editorial", False)
    if not isinstance(flag, bool):
        raise BuildError(f"{m['source']['path']}: editorial: expected true or false, got {flag!r}")
    return flag


def check_glossary_notes(built: list[tuple[dict, dict]], glossary: dict) -> None:
    """A piece's glossary notes must name glossary entries."""
    ids = {e["id"] for e in glossary["entries"]}
    for m, p in built:
        for eid in p.get("glossaryNotes", {}):
            if eid not in ids:
                raise BuildError(f"{m['file']}: glossary_notes: '{eid}' is not a glossary entry "
                                 f"(entries: {', '.join(sorted(ids))})")


def build_all(out_dir: Path, markings_dir: Path = MARKINGS) -> None:
    """Build every piece under ``markings_dir/<collection>/*.yaml`` into ``out_dir``."""
    out_dir, markings_dir = Path(out_dir), Path(markings_dir)
    collections = load_collections(markings_dir / "collections.yaml")
    known = {c["id"] for c in collections}
    built: list[tuple[dict, dict]] = []
    ids: dict[str, Path] = {}
    for d in sorted(p for p in markings_dir.iterdir() if p.is_dir()):
        files = sorted(d.glob("*.yaml"))
        if files and d.name not in known:
            raise BuildError(f"{d}: '{d.name}' is not a collection in collections.yaml")
        for f in files:
            m = load_markings(f)
            if m["id"] in ids:
                raise BuildError(f"{f}: id '{m['id']}' is already used by {ids[m['id']]}")
            ids[m["id"]] = f
            built.append((m, build_piece(m, d.name, markings_dir)))
    library = build_library(collections, built)
    pieces_dir = out_dir / "pieces"
    pieces_dir.mkdir(parents=True, exist_ok=True)
    for old in pieces_dir.glob("*.json"):
        old.unlink()
    for _, p in built:
        (pieces_dir / f"{p['id']}.json").write_text(
            json.dumps(p, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (out_dir / "library.json").write_text(
        json.dumps(library, ensure_ascii=False, indent=1), encoding="utf-8")
    glossary = build_glossary(load_glossary(), library, {"free": free_passage_pieces(markings_dir)})
    check_glossary_notes(built, glossary)
    (out_dir / "glossary.json").write_text(json.dumps(glossary, ensure_ascii=False, indent=1),
                                           encoding="utf-8")


if __name__ == "__main__":
    build_all(WEB_DATA)
    lib = json.loads((WEB_DATA / "library.json").read_text())
    print(f"built {len(lib['pieces'])} pieces into {WEB_DATA}")
