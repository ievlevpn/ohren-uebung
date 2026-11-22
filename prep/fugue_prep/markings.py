"""Read and check the hand-written markings files (YAML).

Piece file ``markings/<collection>/<anything>.yaml``::

    id, title, catalogue, key, tempo, beats_per_bar, ensemble, listen_for, techniques
    source:   {kind: kern, path, alternatives?: [bar], beats_per_quarter? | beat_unit?}  # path under prep/sources/
              # alternatives: bars whose spine splits are an edition's alternative reading
              # (sic/ossia): the extra sub-voices are dropped; every other split and chord
              # keeps its notes as secondary notes
              # commented_from: the bar from which the file comments out its ending
              # (``!!``-prefixed data lines); they are read again (kern.restore_commented)
              # beat_unit: the beat in quarter notes (0.75 = dotted eighth), for beats that
              # are not a whole fraction of a quarter; onsets are divided by it
              {kind: mutopia, path, beats_per_quarter?}       # Mutopia path, e.g. BachJS/BWV988/bwv-988-v03
              {kind: transcription | generated, path}         # path under prep/, e.g. transcriptions/x.yaml
              {kind: transcription, path, score: true}        # the transcription holds every
              # voice, followers too: the canon is matched like a score's (sections allowed)
    voices:   [{name, texture, instrument?}]                  # top voice first; instrument
              # (model.INSTRUMENT_RANGES) replaces the ensemble's default for that voice
    canon:    {leader, followers: [{voice, rule: {...Rule fields}, tolerance_beats?, min_match?}]}
              or a list of such sections, each with ``span: [start, end]`` (score sources):
              the leader's notes in that beat range, for canons whose voices swap roles
      or
    fugue:    {subject: {voice, start, length}, countersubject?: {voice, start, length},
               entries: [{voice, start, form, transform?, stretto?, head?: free|short, tail?: free,
                          part?: head, head_length?, form_by?: opening, ref?: answer}]}
              head: free — the first note (sounding at start, maybe tied over from before)
              varies in length and pitch, note 2 at most its length late (early unbounded); tail:
              free — the last note varies in pitch, at most its length late
              (fugue.find_entry); part: head + head_length: n — a statement of the
              subject's first n notes only (labelled "<form> (head)"); form_by: opening —
              the form is the opening interval's (for statements at neither the
              subject's nor the answer's pitch level; tests/test_pieces.py wtc_form);
              ref: answer — an answer matched against the first answer's notes (the
              first entry with form answer, whole, not itself ref: answer) instead of the
              subject's, for a varied answer too far from the subject (fugue.entry_reference)
              form: subject | answer | countersubject (fugues), motive | countermotive
              (inventions; motive matches fugue.subject, countermotive fugue.countersubject)
              octave: [k, ...] — intervals k (1 = notes 1-2) compared up to whole octaves:
              part of the statement moved an octave (fugue.find_entry; Contrapunctus X bar 75)
              head: short — the first note half as long as the subject's, the rest that
              much earlier (BWV 849's first subject opening with a half note for the whole)
              A fugue on several subjects (double, triple fugue) gives ``subjects: [{id,
              voice, start, length}]`` instead of ``subject`` (ids I, II, III, IV, in the
              order they are first heard); each subject or answer entry then names its
              subject (``subject: II``) and is labelled "<form> <id>" ("answer II")
    captions?: [{at | bar, text}]                             # at = beat; bar = start of that bar (1-based)
    glossary_notes?: {entry_id: text}                         # "In this piece" line on that
              # glossary entry's definition card (tests/test_glossary_notes.py checks each claim)
    pickup?                                                   # beats of upbeat before bar 1 (default 0)
    marks?:    [{kind, start, end, voice?, pitch?, label?}]   # hand-placed technique drawings
    book?, order?                                             # book within the collection; sort key
    number?                                                   # the piece's own number (WTC fugue 3),
                                                              # shown instead of its place in the book

Voices are indices (0 = top). Beats are quarter notes from the start of the piece.
A transcription/generated file holds ``voices: [[[midi, start, duration], ...], ...]``
for the *written* voices: the piece's voices that are not canon followers, in order.
Optional ``end: beat`` cuts every voice there (followers included) and ``coda: [[[midi,
start, duration], ...], ...]`` (one list per *piece* voice, absolute beats) adds the
closing notes — for perpetual canons, whose rule would run on for ever. ``editorial: true``
marks an ending that is not Bach's (a recording's closing chord); it is played, but the
glossary does not count it as a free passage.
Other keys there (source, edition, page) are free-form.

``collections.yaml``: ``collections: [{id, numeral, name, catalogue, note, books?: [name]}]``.

Every problem raises ``MarkingsError`` naming the file and the place in it.
"""
from pathlib import Path

import yaml

from .canon import Rule
from .fugue import TRANSFORMS, first_answer
from .model import ENSEMBLES, ENTRY_FORMS, INSTRUMENT_RANGES, MARK_KINDS, TEXTURES

SOURCE_KINDS = ("kern", "mutopia", "transcription", "generated")
FORMS = ENTRY_FORMS
NUM = (int, float)

PIECE_KEYS = {"id": str, "title": str, "catalogue": str, "key": str, "tempo": NUM,
              "beats_per_bar": int, "ensemble": str, "listen_for": str, "techniques": list,
              "source": dict, "voices": list}
PIECE_OPTIONAL = {"canon": (dict, list), "fugue": dict, "captions": list, "marks": list,
                  "book": str, "order": NUM, "pickup": NUM, "number": int,
                  "glossary_notes": dict}
SOURCE_OPTIONAL = {"kern": {"alternatives": list, "beats_per_quarter": NUM, "beat_unit": NUM,
                            "commented_from": int},
                   "mutopia": {"beats_per_quarter": NUM},
                   "transcription": {"score": bool}, "generated": {}}
RULE_REQUIRED = {"delay": NUM}
RULE_OPTIONAL = {"interval": int, "diatonic": bool, "key": str, "invert_about": (int, type(None)),
                 "retrograde": bool, "stretch": NUM, "per_tonos_step": int, "repeats": int,
                 "exceptions": dict, "free": list, "flip_alterations": bool,
                 "pitch_tolerance": int, "not_imitation": list}
SPAN_KEYS = {"voice": int, "start": NUM, "length": NUM}
COLLECTION_KEYS = {"id": str, "numeral": str, "name": str, "catalogue": str, "note": str}


class MarkingsError(Exception):
    """A markings file is malformed."""


class _Checker:
    def __init__(self, path: Path):
        self.path = path

    def fail(self, where: str, msg: str) -> MarkingsError:
        return MarkingsError(f"{self.path}: {where}: {msg}" if where else f"{self.path}: {msg}")

    def keys(self, obj, where: str, required: dict, optional: dict | None = None) -> dict:
        optional = optional or {}
        if not isinstance(obj, dict):
            raise self.fail(where, f"expected a mapping, got {type(obj).__name__}")
        for k in obj:
            if k not in required and k not in optional:
                raise self.fail(where, f"unknown key '{k}' (allowed: "
                                f"{', '.join(sorted([*required, *optional]))})")
        for k in required:
            if k not in obj:
                raise self.fail(where, f"missing key '{k}'")
        for k, v in obj.items():
            self.type(v, {**required, **optional}[k], f"{where}.{k}" if where else k)
        return obj

    def type(self, v, t, where: str) -> None:
        ts = t if isinstance(t, tuple) else (t,)
        if isinstance(v, bool) and bool not in ts:
            raise self.fail(where, f"expected {self._names(ts)}, got a boolean")
        if not isinstance(v, ts):
            raise self.fail(where, f"expected {self._names(ts)}, got {type(v).__name__}")

    @staticmethod
    def _names(ts) -> str:
        return " or ".join("none" if t is type(None) else t.__name__ for t in ts)

    def one_of(self, v, allowed, where: str) -> None:
        if v not in allowed:
            raise self.fail(where, f"'{v}' is not one of {', '.join(map(str, allowed))}")

    def voice(self, v: int, n: int, where: str) -> None:
        if not 0 <= v < n:
            raise self.fail(where, f"voice {v} does not exist (the piece has {n} voices)")


def _rule(c: _Checker, raw, where: str) -> Rule:
    c.keys(raw, where, RULE_REQUIRED, RULE_OPTIONAL)
    free = []
    for i, r in enumerate(raw.get("free", [])):
        if (not isinstance(r, list) or len(r) != 2
                or not all(isinstance(x, NUM) and not isinstance(x, bool) for x in r)
                or r[1] <= r[0]):
            raise c.fail(f"{where}.free[{i}]", f"expected [start, end] with end > start, got {r!r}")
        free.append((float(r[0]), float(r[1])))
    not_imitation = raw.get("not_imitation", [])
    if not all(isinstance(x, NUM) and not isinstance(x, bool) for x in not_imitation):
        raise c.fail(f"{where}.not_imitation", f"expected a list of leader beats, got {not_imitation!r}")
    exceptions = {}
    for k, v in raw.get("exceptions", {}).items():
        if not isinstance(k, int) or isinstance(v, bool) or not isinstance(v, int):
            raise c.fail(f"{where}.exceptions", f"expected follower index: MIDI pitch, got {k!r}: {v!r}")
        exceptions[k] = v
    if raw.get("diatonic") and "key" not in raw:
        raise c.fail(where, "a diatonic rule needs 'key' (music21 key string, e.g. 'c' or 'F')")
    if raw.get("repeats", 1) < 1:
        raise c.fail(f"{where}.repeats", "must be at least 1")
    if raw.get("stretch", 1) <= 0:
        raise c.fail(f"{where}.stretch", "must be positive")
    return Rule(delay=float(raw["delay"]), interval=raw.get("interval", 0),
                diatonic=raw.get("diatonic", False), key=raw.get("key", "C"),
                invert_about=raw.get("invert_about"), retrograde=raw.get("retrograde", False),
                stretch=float(raw.get("stretch", 1)), per_tonos_step=raw.get("per_tonos_step", 0),
                repeats=raw.get("repeats", 1), exceptions=exceptions, free=tuple(free),
                flip_alterations=raw.get("flip_alterations", False),
                pitch_tolerance=raw.get("pitch_tolerance", 0),
                not_imitation=tuple(float(x) for x in not_imitation))


def _canon(c: _Checker, raw, n: int) -> list[dict]:
    """The canon as a list of sections ``{leader, followers, span}`` (``span`` None = the
    whole piece). A single mapping is one section."""
    if isinstance(raw, dict):
        return [_section(c, raw, n, "canon")]
    if not raw:
        raise c.fail("canon", "needs at least one section")
    sections = [_section(c, s, n, f"canon[{i}]") for i, s in enumerate(raw)]
    if len({f["rule"].repeats for s in sections for f in s["followers"]}) > 1:
        raise c.fail("canon", "all followers must have the same 'repeats'")
    return sections


def _section(c: _Checker, raw, n: int, where: str) -> dict:
    c.keys(raw, where, {"leader": int, "followers": list}, {"span": list})
    c.voice(raw["leader"], n, f"{where}.leader")
    span = None
    if "span" in raw:
        r = raw["span"]
        if (len(r) != 2 or not all(isinstance(x, NUM) and not isinstance(x, bool) for x in r)
                or r[1] <= r[0]):
            raise c.fail(f"{where}.span", f"expected [start, end] with end > start, got {r!r}")
        span = (float(r[0]), float(r[1]))
    if not raw["followers"]:
        raise c.fail(f"{where}.followers", "needs at least one follower")
    followers, seen = [], {raw["leader"]}
    for i, f in enumerate(raw["followers"]):
        fw = f"{where}.followers[{i}]"
        c.keys(f, fw, {"voice": int, "rule": dict}, {"tolerance_beats": NUM, "min_match": NUM})
        c.voice(f["voice"], n, f"{fw}.voice")
        if f["voice"] in seen:
            raise c.fail(f"{fw}.voice", f"voice {f['voice']} is already the leader or a follower")
        seen.add(f["voice"])
        followers.append({"voice": f["voice"], "rule": _rule(c, f["rule"], f"{fw}.rule"),
                          "tolerance_beats": float(f.get("tolerance_beats", 0.01)),
                          "min_match": float(f.get("min_match", 0.9))})
    if len({f["rule"].repeats for f in followers}) > 1:
        raise c.fail(f"{where}.followers", "all followers must have the same 'repeats'")
    if len({f["rule"].per_tonos_step for f in followers}) > 1:
        raise c.fail(f"{where}.followers", "all followers must have the same 'per_tonos_step'")
    return {"leader": raw["leader"], "followers": followers, "span": span}


SUBJECT_IDS = ("I", "II", "III", "IV")


def _fugue(c: _Checker, raw, n: int) -> dict:
    c.keys(raw, "fugue", {"entries": list},
           {"subject": dict, "subjects": list, "countersubject": dict})
    if ("subject" in raw) == ("subjects" in raw):
        raise c.fail("fugue", "give exactly one of 'subject' or 'subjects'")
    subjects = None
    if "subjects" in raw:
        if not 2 <= len(raw["subjects"]) <= len(SUBJECT_IDS):
            raise c.fail("fugue.subjects", "a fugue on several subjects has two to four")
        subjects = {}
        for i, sp in enumerate(raw["subjects"]):
            where = f"fugue.subjects[{i}]"
            c.keys(sp, where, {"id": str, **SPAN_KEYS})
            if sp["id"] != SUBJECT_IDS[i]:
                raise c.fail(f"{where}.id", f"expected '{SUBJECT_IDS[i]}' (ids I, II, III, IV "
                             "in the order the subjects are first heard)")
            c.voice(sp["voice"], n, f"{where}.voice")
            if sp["length"] <= 0:
                raise c.fail(f"{where}.length", "must be positive")
            subjects[sp["id"]] = {k: sp[k] for k in SPAN_KEYS}
    for name in ("subject", "countersubject"):
        if name in raw:
            c.keys(raw[name], f"fugue.{name}", SPAN_KEYS)
            c.voice(raw[name]["voice"], n, f"fugue.{name}.voice")
            if raw[name]["length"] <= 0:
                raise c.fail(f"fugue.{name}.length", "must be positive")
    if not raw["entries"]:
        raise c.fail("fugue.entries", "needs at least one entry")
    entries = []
    for i, e in enumerate(raw["entries"]):
        where = f"fugue.entries[{i}]"
        c.keys(e, where, {"voice": int, "start": NUM, "form": str},
               {"transform": str, "stretto": (str, int), "head": str, "tail": str,
                "part": str, "head_length": int, "form_by": str, "ref": str, "subject": str,
                "octave": list})
        if not all(isinstance(k, int) and not isinstance(k, bool) and k >= 1
                   for k in e.get("octave", [])):
            raise c.fail(f"{where}.octave", "expected a list of interval numbers (1 = notes 1-2)")
        c.one_of(e.get("head", "free"), ("free", "short"), f"{where}.head")
        c.one_of(e.get("tail", "free"), ("free",), f"{where}.tail")
        if subjects is None and "subject" in e:
            raise c.fail(f"{where}.subject", "only a fugue with 'subjects' names an entry's subject")
        if subjects is not None and e["form"] in ("subject", "answer"):
            if "subject" not in e:
                raise c.fail(where, f"say which subject ({', '.join(subjects)}) with 'subject'")
            c.one_of(e["subject"], tuple(subjects), f"{where}.subject")
        c.one_of(e.get("part", "head"), ("head",), f"{where}.part")
        c.one_of(e.get("form_by", "opening"), ("opening",), f"{where}.form_by")
        c.one_of(e.get("ref", "subject"), ("subject", "answer"), f"{where}.ref")
        if e.get("ref") == "answer" and e["form"] != "answer":
            raise c.fail(f"{where}.ref", "ref: answer is only for an answer")
        if ("part" in e) != ("head_length" in e):
            raise c.fail(where, "part: head and head_length go together")
        if "head_length" in e and e["head_length"] < 2:
            raise c.fail(f"{where}.head_length", "must be at least 2")
        c.voice(e["voice"], n, f"{where}.voice")
        c.one_of(e["form"], FORMS, f"{where}.form")
        c.one_of(e.get("transform", "none"), TRANSFORMS, f"{where}.transform")
        if e["form"] in ("countersubject", "countermotive") and "countersubject" not in raw:
            raise c.fail(where, f"a {e['form']} entry needs fugue.countersubject")
        entries.append({"voice": e["voice"], "start": float(e["start"]), "form": e["form"],
                        "transform": e.get("transform", "none"),
                        "stretto": None if e.get("stretto") is None else str(e["stretto"]),
                        "head": e.get("head", "fixed"), "tail": e.get("tail", "fixed"),
                        "part": e.get("part", "whole"), "head_length": e.get("head_length"),
                        "form_by": e.get("form_by"), "ref": e.get("ref", "subject"),
                        "octave": tuple(e.get("octave", ())),
                        **({"subject": e.get("subject")} if subjects is not None else {})})
    fugue = {"subject": raw["subject"] if subjects is None else subjects[SUBJECT_IDS[0]],
             "countersubject": raw.get("countersubject"), "entries": entries}
    if subjects is not None:
        fugue["subjects"] = subjects
    for sid in sorted({e.get("subject") or "" for e in entries if e["ref"] == "answer"}):
        first = first_answer(fugue, sid or None)
        if first is None or (first["head"], first["tail"], first["transform"]) != (
                "fixed", "fixed", "none"):
            raise c.fail("fugue.entries", "ref: answer needs a first answer that is whole, "
                         "untransformed, with fixed head and tail (it is the reference)")
    return fugue


def load_markings(path: Path) -> dict:
    """Read and check one piece's markings; return them with defaults filled in, captions
    resolved to beats (``at``) and canon rules as ``Rule`` objects."""
    path = Path(path)
    c = _Checker(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise MarkingsError(f"{path}: not valid YAML: {e}") from e
    c.keys(raw, "", PIECE_KEYS, PIECE_OPTIONAL)
    c.one_of(raw["ensemble"], ENSEMBLES, "ensemble")
    if raw["beats_per_bar"] < 1:
        raise c.fail("beats_per_bar", "must be at least 1")
    if raw["tempo"] <= 0:
        raise c.fail("tempo", "must be positive")
    pickup = raw.get("pickup", 0)
    if not 0 <= pickup < raw["beats_per_bar"]:
        raise c.fail("pickup", "must be at least 0 and shorter than a bar")
    if not raw["techniques"] or not all(isinstance(t, str) and t for t in raw["techniques"]):
        raise c.fail("techniques", "expected a non-empty list of names")

    src = raw["source"]
    kind = src.get("kind") if isinstance(src, dict) else None
    c.one_of(kind, SOURCE_KINDS, "source.kind")
    c.keys(src, "source", {"kind": str, "path": str}, SOURCE_OPTIONAL[kind])
    if "beat_unit" in src and "beats_per_quarter" in src:
        raise c.fail("source.beat_unit", "give either beat_unit or beats_per_quarter, not both")
    if src.get("beat_unit", 1) <= 0:
        raise c.fail("source.beat_unit", "must be positive")
    alts = src.get("alternatives", [])
    if not all(isinstance(b, int) and not isinstance(b, bool) and b > 0 for b in alts):
        raise c.fail("source.alternatives", f"expected a list of bar numbers, got {alts!r}")

    if not raw["voices"]:
        raise c.fail("voices", "needs at least one voice")
    for i, v in enumerate(raw["voices"]):
        c.keys(v, f"voices[{i}]", {"name": str, "texture": str}, {"instrument": str})
        c.one_of(v["texture"], TEXTURES, f"voices[{i}].texture")
        if "instrument" in v:
            c.one_of(v["instrument"], tuple(INSTRUMENT_RANGES), f"voices[{i}].instrument")
    n = len(raw["voices"])

    if ("canon" in raw) == ("fugue" in raw):
        raise c.fail("", "needs exactly one of 'canon' or 'fugue'")
    canon = _canon(c, raw["canon"], n) if "canon" in raw else None
    fugue = _fugue(c, raw["fugue"], n) if "fugue" in raw else None
    score = kind in ("kern", "mutopia") or bool(src.get("score"))
    if canon and score and canon[0]["followers"][0]["rule"].repeats > 1:
        raise c.fail("canon", "repeats > 1 needs a transcription/generated source "
                     "(a score already contains every pass)")
    if canon and not score and (
            len(canon) > 1 or canon[0]["span"] is not None):
        raise c.fail("canon", "a computed follower has one section and no 'span' "
                     "(sections need a score source)")

    captions = []
    for i, cap in enumerate(raw.get("captions", [])):
        where = f"captions[{i}]"
        c.keys(cap, where, {"text": str}, {"at": NUM, "bar": int})
        if ("at" in cap) == ("bar" in cap):
            raise c.fail(where, "give exactly one of 'at' (beat) or 'bar'")
        at = cap["at"] if "at" in cap else pickup + (cap["bar"] - 1) * raw["beats_per_bar"]
        captions.append({"at": float(at), "text": cap["text"]})

    notes = raw.get("glossary_notes", {})
    for k, v in notes.items():
        if not isinstance(k, str) or not isinstance(v, str) or not v.strip():
            raise c.fail(f"glossary_notes.{k}", "expected an entry id and a line of text")

    marks = []
    for i, m in enumerate(raw.get("marks", [])):
        where = f"marks[{i}]"
        c.keys(m, where, {"kind": str, "start": NUM, "end": NUM},
               {"voice": int, "pitch": int, "label": str})
        c.one_of(m["kind"], MARK_KINDS, f"{where}.kind")
        if "voice" in m:
            c.voice(m["voice"], n, f"{where}.voice")
        marks.append({"kind": m["kind"], "start": float(m["start"]), "end": float(m["end"]),
                      "voice": m.get("voice"), "pitch": m.get("pitch"), "label": m.get("label")})

    return {**raw, "source": dict(src), "canon": canon, "fugue": fugue,
            "captions": captions, "marks": marks, "glossary_notes": dict(notes), "file": path}


def load_collections(path: Path) -> list[dict]:
    path = Path(path)
    c = _Checker(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise MarkingsError(f"{path}: not valid YAML: {e}") from e
    c.keys(raw, "", {"collections": list})
    out, ids = [], set()
    for i, col in enumerate(raw["collections"]):
        where = f"collections[{i}]"
        c.keys(col, where, COLLECTION_KEYS, {"books": list})
        if col["id"] in ids:
            raise c.fail(f"{where}.id", f"duplicate collection '{col['id']}'")
        ids.add(col["id"])
        books = col.get("books", [])
        if not all(isinstance(b, str) for b in books):
            raise c.fail(f"{where}.books", "expected a list of book names")
        out.append({**col, "books": books})
    return out
