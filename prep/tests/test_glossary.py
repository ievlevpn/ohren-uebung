"""The glossary: every technique defined once, every illustration musically exact."""
import json
import re
from fractions import Fraction

import pytest
import yaml

from fugue_prep.build import WEB_DATA, free_passage_pieces
from fugue_prep.glossary import (GLOSSARY, GlossaryError, build_glossary, load_glossary,
                                 parse_notes)
from fugue_prep.model import INSTRUMENT_RANGES
from fugue_prep.validate import validate_piece
from tests.scales import from_step, to_step

LIBRARY = json.loads((WEB_DATA / "library.json").read_text())
RAW = yaml.safe_load(GLOSSARY.read_text())
FREE = free_passage_pieces()


@pytest.fixture(scope="module")
def glossary() -> dict:
    return build_glossary(load_glossary(), LIBRARY, {"free": FREE})


def entry_of(g: dict, eid: str) -> dict:
    return next(e for e in g["entries"] if e["id"] == eid)


# ---- notation ----

def test_parse_notes_reads_names_octaves_and_carried_durations():
    assert parse_notes("C4/1 D4 Eb4/.5 F#4 r/1 B3/2", at=2) == [
        (60, 2, 1), (62, 3, 1), (63, 4, 0.5), (66, 4.5, 0.5), (59, 6, 2)]
    assert parse_notes("C♯5/1.5 B♭4", at=0) == [(73, 0, 1.5), (70, 1.5, 1.5)]
    with pytest.raises(GlossaryError):
        parse_notes("H4/1", at=0)


# ---- the mapping from library techniques to entries ----

def test_every_library_technique_maps_to_exactly_one_entry(glossary):
    entries_by_alias: dict[str, list[str]] = {}
    for e in glossary["entries"]:
        for a in e["aliases"]:
            entries_by_alias.setdefault(a, []).append(e["id"])
    assert all(len(ids) == 1 for ids in entries_by_alias.values()), entries_by_alias
    for t in LIBRARY["techniques"]:
        assert t.lower() in entries_by_alias, f"library technique '{t}' has no glossary entry"
        assert glossary["techniques"][t] == entries_by_alias[t.lower()][0]
    assert set(glossary["techniques"]) == set(LIBRARY["techniques"])


def test_an_unknown_technique_fails_the_build():
    lib = {**LIBRARY, "techniques": {**LIBRARY["techniques"], "hocket": ["bwv846"]}}
    with pytest.raises(GlossaryError, match="hocket"):
        build_glossary(load_glossary(), lib, {"free": FREE})


def test_hear_it_in_lists_exactly_the_pieces_with_the_technique(glossary):
    order = [p["id"] for p in LIBRARY["pieces"]]
    for e in glossary["entries"]:
        want = {pid for t, ids in LIBRARY["techniques"].items()
                if glossary["techniques"][t] == e["id"] for pid in ids}
        if e["id"] == "free-passage":
            want = set(FREE)
        got = [x["id"] for x in e["pieces"]]
        assert set(got) == want, e["id"]
        assert got == sorted(got, key=order.index), e["id"]  # library order, no repeats


def test_no_entry_has_an_empty_hear_it_in(glossary):
    for e in glossary["entries"]:
        assert e["pieces"], e["id"]


def test_free_passage_lists_the_pieces_whose_markings_declare_free_music(glossary):
    # a canon rule's free ranges (Goldberg canons' closing bars) or a transcription's end + coda
    # canon rules' free ranges (Goldberg canons' cadences, Invention 2, the Canone
    # perpetuo's unimitated last bars, the Canon alla Ottava's close) and Bach's own ending (the Fuga canonica's fermata);
    # editors' closing chords on perpetual canons (Reccmo's) do not count
    assert sorted(FREE) == sorted([
        "goldberg-var03", "goldberg-var06", "goldberg-var09", "goldberg-var12",
        "goldberg-var15", "goldberg-var21", "goldberg-var24", "goldberg-var27", "invention02",
        "bwv1079-fuga-canonica", "bwv1079-canone-perpetuo", "canon-alla-ottava"])
    assert [x["id"] for x in entry_of(glossary, "free-passage")["pieces"]] == [
        p["id"] for p in LIBRARY["pieces"] if p["id"] in FREE]
    with pytest.raises(GlossaryError, match="free"):
        build_glossary(load_glossary(), LIBRARY)


def test_perpetual_canons_are_the_loops_of_the_library(glossary):
    ids = {x["id"] for x in entry_of(glossary, "perpetual-canon")["pieces"]}
    assert ids == {"frere-jacques", "bwv1079-thema-regium", "bwv1079-violini-in-unisono",
                   "bwv1079-motum-contrarium", "bwv1079-augmentationem", "bwv1079-per-tonos",
                   "bwv1079-quaerendo", "bwv1079-canon-a4", "bwv1079-canone-perpetuo"}


def texts_of_the_pieces() -> list[str]:
    out = []
    for f in sorted((WEB_DATA / "pieces").glob("*.json")):
        p = json.loads(f.read_text())
        out += [c["text"] for c in p["captions"]] + [p["listenFor"]]
        out += [m["label"] for m in p["marks"] if m.get("label")]
    return out


# An alias is an ordinary word when a verb's context surrounds it: after a modal, "to" or a
# pronoun subject ("will answer", "it comes"), or, for the aliases that are also verbs,
# before a particle or object ("comes back", "answers them").
_BEFORE = re.compile(r"\b(will|to|can|could|may|might|must|shall|should|would|it|he|she|"
                     r"they|which|that|who)\s+$", re.I)
_AFTER = {
    "comes": re.compile(r"^\s+(back|in|round|out|up|down|along|from|to|again)\b", re.I),
    "answer": re.compile(r"^\s+(it|them|him|her|back|again)\b", re.I),
    "mirror": re.compile(r"^\s+(it|them|the|each)\b", re.I),
}


def unsafe_uses(alias: str, text: str, ordinary: list[str]) -> list[str]:
    """Every whole-word occurrence of ``alias`` (or its plural / 3rd person: +s) in
    ``text`` that reads as an ordinary word and is not inside an ``ordinary`` phrase."""
    covered = [m.span() for p in ordinary for m in re.finditer(re.escape(p), text, re.I)]
    after = _AFTER.get(alias)
    out = []
    for m in re.finditer(r"(?<![\w-])" + re.escape(alias) + r"s?(?![\w-])", text, re.I):
        if any(lo <= m.start() and m.end() <= hi for lo, hi in covered):
            continue
        if _BEFORE.search(text[:m.start()]) or (after and after.match(text[m.end():])):
            out.append(f"{text[max(0, m.start() - 20):m.end() + 20]!r}")
    return out


def test_the_linkable_alias_check_catches_ordinary_words():
    """Synthetic captions: each must be caught (the guard Task 2's linker relies on)."""
    bad = {
        "comes": ["☞ The theme comes back in the bass.", "☞ Then it comes in, softly.",
                  "☞ The tune comes round again.", "☞ Here it comes: the dux."],
        "answer": ["☞ The violin will answer it.", "☞ The alto answers them at once.",
                   "☞ Free voices answer it.", "☞ The bass waits to answer."],
        "mirror": ["☞ The voices mirror each other."],
    }
    for alias, texts in bad.items():
        for t in texts:
            assert unsafe_uses(alias, t, []), (alias, t)
    # every occurrence counts, not only the first; a phrase covers only its own span
    t = "☞ The answer in the alto; then the soprano will answer it."
    assert len(unsafe_uses("answer", t, [])) == 1
    assert unsafe_uses("answer", t, ["will answer it"]) == []
    assert unsafe_uses("answer", t, ["the answer in the alto"]) != []
    # whole words only
    assert unsafe_uses("comes", "☞ It becomes clear.", []) == []
    assert unsafe_uses("answer", "☞ It was answered.", []) == []
    # technical uses pass
    for alias, t in [("comes", "☞ Comes: the dux a fifth higher."),
                     ("answer", "☞ The answer in the soprano, on G."),
                     ("comes", "☞ The comes begins its second round, the dux its third.")]:
        assert unsafe_uses(alias, t, []) == [], t


def test_only_safe_aliases_are_linkable(glossary):
    """Task 2 links technique words in captions; an alias that is also an ordinary word
    ("four times round", "a half cadence") must not be linkable."""
    links = {a: e["id"] for e in glossary["entries"] for a in e["links"]}
    for e in glossary["entries"]:
        assert set(e["links"]) <= set(e["aliases"]), e["id"]
    for word in ("round", "cadence", "coda", "free passage", "episode"):
        assert word not in links, word
    assert links["inversion"] == "inversion" and links["dux"] == "canon"
    texts = texts_of_the_pieces()
    ordinary = glossary["ordinary"]
    problems = [(a, u) for a in links for t in texts for u in unsafe_uses(a, t, ordinary)]
    assert problems == []
    for p in ordinary:
        assert any(p.lower() in t.lower() for t in texts), f"ordinary phrase '{p}' is stale"


def test_a_card_opened_by_a_word_defines_that_word(glossary):
    """Words that open a broader entry are explained in its text ("exposition" opens Fugue)."""
    fugue = entry_of(glossary, "fugue")
    assert "exposition" in fugue["links"]
    assert "this opening is the exposition" in fugue["text"]


def test_canons_at_an_interval_say_which_interval(glossary):
    e = entry_of(glossary, "canon-at-an-interval")
    notes = {x["id"]: x.get("note") for x in e["pieces"]}
    assert notes["goldberg-var12"] == "at the fourth"
    assert notes["goldberg-var27"] == "at the ninth"
    assert notes["invention02"] == "at the octave"


def test_related_entries_exist_and_ids_are_unique(glossary):
    ids = [e["id"] for e in glossary["entries"]]
    assert len(ids) == len(set(ids))
    for e in glossary["entries"]:
        for r in e["related"]:
            assert r in ids and r != e["id"], (e["id"], r)


def test_entries_are_short_plain_and_alphabetical(glossary):
    titles = [e["title"] for e in glossary["entries"]]
    assert titles == sorted(titles, key=str.lower)
    for e in glossary["entries"]:
        sentences = [s for s in e["text"].replace("…", "").split(". ") if s.strip()]
        assert 2 <= len(sentences) <= 4, (e["id"], len(sentences))
        assert e["short"] and len(e["short"]) < len(e["text"]), e["id"]


# ---- the illustrations ----

def test_examples_validate_as_pieces(glossary):
    for e in glossary["entries"]:
        ex = e.get("example")
        if ex is None:
            continue
        assert validate_piece(ex) == [], e["id"]
        assert ex["caption"], e["id"]
        notes = ex["notes"]
        assert notes == sorted(notes, key=lambda n: (n["s"], n["v"]))
        for v, voice in enumerate(ex["voices"]):
            lo, hi = INSTRUMENT_RANGES[voice["instrument"]]
            ps = [n["p"] for n in notes if n["v"] == v]
            assert ps and lo <= min(ps) and max(ps) <= hi, (e["id"], v)


# An independent recomputation of each declared transformation (scale steps by hand,
# not through the canon engine), compared with the notes the build wrote.
def expected_follower(leader: list[tuple], rule: dict, key: str) -> list[tuple]:
    s0 = min(s for _, s, _ in leader)
    end = max(s + d for _, s, d in leader)
    period = end - s0
    out = []
    for r in range(rule.get("repeats", 1)):
        for p, s, d in leader:
            if rule.get("diatonic", True):
                step, alt = to_step(p, key)
                if rule.get("invert_about") is not None:
                    step = 2 * to_step(rule["invert_about"], key)[0] - step
                q = from_step(step + rule.get("interval", 0), alt, key)
            else:
                q = p if rule.get("invert_about") is None else 2 * rule["invert_about"] - p
                q += rule.get("interval", 0)
            k = rule.get("stretch", 1)
            if rule.get("retrograde"):
                t = s0 + rule.get("delay", 0) + (end - s - d) * k
            else:
                t = s0 + rule.get("delay", 0) + (s - s0) * k
            out.append((q + r * rule.get("per_tonos_step", 0), t + r * period, d * k))
    out.sort(key=lambda n: n[1])
    for i, p in rule.get("exceptions", {}).items():
        out[i] = (p, *out[i][1:])
    return out


def raw_entry(eid: str) -> dict:
    return next(e for e in RAW["entries"] if e["id"] == eid)


def voice_notes(ex: dict, v: int, span=None) -> list[tuple]:
    return [(n["p"], n["s"], n["d"]) for n in ex["notes"] if n["v"] == v
            and (span is None or span[0] <= n["s"] < span[1])]


def test_every_derived_voice_equals_its_declared_transformation(glossary):
    checked = 0
    for e in glossary["entries"]:
        ex = e.get("example")
        if ex is None:
            continue
        spec = raw_entry(e["id"])["example"]
        key = spec["key"]
        for w in spec.get("written", []):
            rep = w.get("repeat")
            if rep:  # a written line repeated per tonos: pass r is pass 0 raised r steps
                line = parse_notes(w["notes"], at=w.get("at", 0))
                period = max(s + d for _, s, d in line) - min(s for _, s, d in line)
                want = [(p + r * rep["step"], s + r * period, d)
                        for r in range(rep["times"]) for p, s, d in line]
                assert set(want) <= set(voice_notes(ex, w["voice"])), e["id"]
                checked += 1
        for d in spec.get("derived", []):
            span = d.get("span")
            leader = [n for n in spec_voice(spec, d["from"], upto=d) if
                      span is None or span[0] <= n[1] < span[1]]
            want = expected_follower(leader, d["rule"], key)
            lo = min(s for _, s, _ in want)
            hi = max(s + dur for _, s, dur in want)
            got = [n for n in voice_notes(ex, d["voice"]) if lo <= n[1] and n[1] + n[2] <= hi]
            assert sorted(want, key=lambda n: (n[1], n[0])) == sorted(got, key=lambda n: (n[1], n[0])), e["id"]
            # every follower note hangs on a thread from its leader note
            threaded = {(ex["notes"][t["b"]]["p"], ex["notes"][t["b"]]["s"]) for t in ex["threads"]}
            assert {(p, s) for p, s, _ in want} <= threaded, e["id"]
            checked += 1
    assert checked >= 12


def spec_voice(spec: dict, v: int, upto: dict) -> list[tuple]:
    """The notes of voice ``v`` as the yaml writes them, plus earlier derived voices."""
    notes = [n for w in spec.get("written", []) if w["voice"] == v
             for n in parse_notes(w["notes"], at=w.get("at", 0))]
    for d in spec.get("derived", []):
        if d is upto:
            break
        if d["voice"] == v:
            span = d.get("span")
            leader = [n for n in spec_voice(spec, d["from"], upto=d)
                      if span is None or span[0] <= n[1] < span[1]]
            notes += expected_follower(leader, d["rule"], spec["key"])
    return sorted(notes, key=lambda n: n[1])


def test_the_named_transformations_look_as_their_names_say(glossary):
    """Spot checks in plain arithmetic, one per transformation."""
    ex = entry_of(glossary, "inversion")["example"]
    dux, comes = voice_notes(ex, 0), voice_notes(ex, 1)
    ups = [b[0] - a[0] for a, b in zip(dux, dux[1:])]
    downs = [b[0] - a[0] for a, b in zip(comes, comes[1:])]
    assert all((u > 0) == (d < 0) for u, d in zip(ups, downs))  # every rise a fall
    ex = entry_of(glossary, "retrograde")["example"]
    fwd, back = voice_notes(ex, 0), voice_notes(ex, 1)
    assert [p for p, _, _ in back] == [p for p, _, _ in reversed(fwd)]
    assert [d for _, _, d in back] == [d for _, _, d in reversed(fwd)]
    ex = entry_of(glossary, "augmentation")["example"]
    a, b = voice_notes(ex, 0), voice_notes(ex, 1)
    assert [d * 2 for *_, d in a] == [d for *_, d in b]
    assert len({q - p for (p, *_), (q, *_) in zip(a, b)}) == 1  # same shape, one transposition
    ex = entry_of(glossary, "diminution")["example"]
    a, b = voice_notes(ex, 0), voice_notes(ex, 1)
    assert [Fraction(d) / 2 for *_, d in a] == [Fraction(d) for *_, d in b]
    ex = entry_of(glossary, "canon-at-the-unison")["example"]
    a, b = voice_notes(ex, 0), voice_notes(ex, 1)
    assert [p for p, *_ in b] == [p for p, *_ in a][:len(b)]
    ex = entry_of(glossary, "answer")["example"]
    subject, answer = voice_notes(ex, 1), voice_notes(ex, 0)
    shifts = [q - p for (p, *_), (q, *_) in zip(subject, answer)]
    assert shifts[0] == 7 and shifts[1] == 5 and set(shifts[2:]) == {7}  # tonal: C-G answered G-C


CONSONANT = {0, 3, 4, 7, 8, 9}


def test_canonic_examples_are_consonant_on_the_beat(glossary):
    """Two notes sounding together on a beat make a consonance (a fourth only between
    upper voices), and no two voices move in parallel fifths or octaves from beat to beat."""
    for e in glossary["entries"]:
        ex = e.get("example")
        if ex is None or len(ex["voices"]) < 2:
            continue
        end = max(n["s"] + n["d"] for n in ex["notes"])
        prev: dict[tuple[int, int], tuple[int, int, int]] = {}
        for beat in range(int(end)):
            sounding = {n["v"]: n for n in ex["notes"] if n["s"] <= beat < n["s"] + n["d"]}
            if len(sounding) < 2:
                prev = {}
                continue
            bass = min(n["p"] for n in sounding.values())
            for a in sounding.values():
                for b in sounding.values():
                    if a["v"] >= b["v"]:
                        continue
                    iv = abs(a["p"] - b["p"]) % 12
                    ok = iv in CONSONANT or (iv == 5 and min(a["p"], b["p"]) != bass)
                    assert ok, f"{e['id']}: beat {beat}: {a['p']} against {b['p']}"
                    key = (a["v"], b["v"])
                    last = prev.get(key)
                    if last and iv in (0, 7) and last[0] == iv and (last[1], last[2]) != (a["p"], b["p"]):
                        pytest.fail(f"{e['id']}: beat {beat}: parallel {'octaves' if iv == 0 else 'fifths'}")
            prev = {(a["v"], b["v"]): (abs(a["p"] - b["p"]) % 12, a["p"], b["p"])
                    for a in sounding.values() for b in sounding.values() if a["v"] < b["v"]}


# ---- the written file ----

def test_glossary_json_is_current(glossary):
    on_disk = json.loads((WEB_DATA / "glossary.json").read_text())
    assert on_disk == glossary


def test_short_definitions_are_one_sentence(glossary):
    for e in glossary["entries"]:
        body = e["short"].rstrip(".")
        assert e["short"].endswith(".") and ". " not in body and "? " not in body, e["id"]
