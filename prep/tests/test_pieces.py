"""The pieces of the library: every piece builds, validates and teaches true.

Builds the real markings once (network and LilyPond on first run, like test_build).
"""
import json
import math
from pathlib import Path

import pytest

from fugue_prep.build import MARKINGS, SOURCES, build_all, computed, load_voices
from fugue_prep.fugue import (entry_reference, find_entry, first_answer, subject_notes,
                               subject_spec)
from fugue_prep.markings import load_markings
from fugue_prep.model import TEXTURES
from fugue_prep.validate import validate_piece

PIECES = {
    "rounds": ["frere-jacques"],
    "musical-offering": ["bwv1079-ricercar-a3", "bwv1079-thema-regium", "bwv1079-cancrizans",
                         "bwv1079-violini-in-unisono", "bwv1079-motum-contrarium",
                         "bwv1079-augmentationem", "bwv1079-per-tonos", "bwv1079-fuga-canonica",
                         "bwv1079-ricercar-a6", "bwv1079-quaerendo", "bwv1079-canon-a4",
                         "bwv1079-canone-perpetuo"],
    "goldberg": ["goldberg-var03", "goldberg-var06", "goldberg-var09", "goldberg-var12",
                 "goldberg-var15", "goldberg-var18", "goldberg-var21", "goldberg-var24",
                 "goldberg-var27"],
    "art-of-fugue": ["contrapunctus01", "contrapunctus02", "contrapunctus03", "contrapunctus04",
                     "contrapunctus05", "contrapunctus06", "contrapunctus07", "contrapunctus08",
                     "contrapunctus09", "contrapunctus10", "contrapunctus11",
                     "contrapunctus12-rectus", "contrapunctus12-inversus",
                     "contrapunctus13-rectus", "contrapunctus13-inversus",
                     "canon-per-augmentationem", "canon-alla-ottava", "canon-alla-decima",
                     "canon-alla-duodecima", "contrapunctus14"],
    "wtc": [f"bwv{n}" for n in range(846, 870)],
    "inventions": [f"invention{n:02d}" for n in range(1, 16)]
                  + [f"sinfonia{n:02d}" for n in range(1, 16)],
}
ENSEMBLE = {"rounds": "strings", "musical-offering": "chamber", "goldberg": "harpsichord",
            "art-of-fugue": "strings", "wtc": "harpsichord", "inventions": "harpsichord"}
# the two ricercars are keyboard music: harpsichord, not the canons' chamber ensemble
ENSEMBLE_OF_PIECE = {"bwv1079-ricercar-a3": "harpsichord", "bwv1079-ricercar-a6": "harpsichord",
                     # the Art of Fugue canons: two-stave keyboard pieces (two of them wider
                     # than any string instrument)
                     "canon-per-augmentationem": "harpsichord", "canon-alla-ottava": "harpsichord",
                     "canon-alla-decima": "harpsichord", "canon-alla-duodecima": "harpsichord"}
MARKINGS_BY_ID = {load_markings(f)["id"]: (f.parent.name, load_markings(f))
                  for f in sorted(MARKINGS.glob("*/*.yaml"))}


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("data")
    build_all(out)
    return out


def piece(built: Path, pid: str) -> dict:
    return json.loads((built / "pieces" / f"{pid}.json").read_text())


def test_the_pieces_in_their_collections(built):
    lib = json.loads((built / "library.json").read_text())
    got = {c["id"]: [p for b in c["books"] for p in b["pieces"]] for c in lib["collections"]}
    assert got == PIECES
    assert len(list((built / "pieces").glob("*.json"))) == 96


@pytest.mark.parametrize("pid", [p for ps in PIECES.values() for p in ps])
def test_every_piece_validates_and_is_marked_up(built, pid):
    p = piece(built, pid)
    assert validate_piece(p) == []
    col, m = MARKINGS_BY_ID[pid]
    assert p["ensemble"] == ENSEMBLE_OF_PIECE.get(pid, ENSEMBLE[col])
    assert [v["texture"] for v in p["voices"]] == list(TEXTURES[:len(p["voices"])])
    caps = p["captions"]
    assert caps and caps[0]["at"] <= 4 * p["beatsPerBar"]
    assert all(c["text"].startswith("☞ ") and len(c["text"]) <= 80 for c in caps), caps
    assert len({c["at"] for c in caps}) == len(caps)  # one caption at a time
    assert p["listenFor"] and p["techniques"]


def _canons():
    return [(pid, m) for pid, (_, m) in MARKINGS_BY_ID.items() if m["canon"]]


def _free(rule, span) -> list[tuple[float, float]]:
    """The leader beats a section does not count: its free ranges and outside its span."""
    out = list(rule.free)
    if span is not None:
        out += [(-math.inf, span[0]), (span[1], math.inf)]
    return out


@pytest.mark.parametrize("pid", [pid for pid, _ in _canons()])
def test_canon_threads_hold(built, pid):
    """Computed followers: 100 % unbroken. Followers from a score: at least min_match
    (90 %) of the leader's non-free notes have an unbroken thread (an unanswered note is
    a miss)."""
    m = MARKINGS_BY_ID[pid][1]
    p = piece(built, pid)
    notes, threads = p["notes"], p["threads"]
    derived = computed(m)
    for sec in m["canon"]:
        lv, free = sec["leader"], None
        for f in sec["followers"]:
            free = _free(f["rule"], sec["span"])

            def counted(s: float, rule=f["rule"]) -> bool:
                return (not any(lo <= s < hi for lo, hi in free)
                        and s not in rule.not_imitation)
            mine = [t for t in threads if notes[t["b"]]["v"] == f["voice"]
                    and notes[t["a"]]["v"] == lv and counted(notes[t["a"]]["s"])]
            assert mine, f"{pid}: no threads to voice {f['voice']}"
            if derived:
                assert all(not t["broken"] for t in mine), pid
                continue
            leader = [n for n in notes if n["v"] == lv and counted(n["s"])]
            rate = sum(not t["broken"] for t in mine) / len(leader)
            assert rate >= f["min_match"], f"{pid}: voice {lv} -> {f['voice']}: {rate:.1%}"


def _fugues():
    return [(pid, m) for pid, (_, m) in MARKINGS_BY_ID.items() if m["fugue"]]


@pytest.mark.parametrize("pid", [pid for pid, _ in _fugues()])
def test_every_fugue_entry_is_found(built, pid):
    m = MARKINGS_BY_ID[pid][1]
    voices = load_voices(m, MARKINGS)
    for e in m["fugue"]["entries"]:
        idx = find_entry(voices, entry_reference(voices, m["fugue"], e), e["voice"], e["start"],
                         e["transform"],
                         head=e["head"], tail=e["tail"], head_length=e["head_length"], octave=e.get("octave", ()),
                         piece=pid, beats_per_bar=m["beats_per_bar"], pickup=m.get("pickup", 0))
        first = voices[e["voice"]][idx[0]]
        if e["head"] == "free":  # the first note sounds at the statement's place
            assert first.s <= e["start"] + 0.01 < first.s + first.d
        else:
            assert first.s == pytest.approx(e["start"])
    marks = [k for k in piece(built, pid)["marks"] if k["kind"] == "entry"]
    assert len(marks) == len(m["fugue"]["entries"])


def test_bwv847_countersubject_is_marked_and_captioned(built):
    p = piece(built, "bwv847")
    cs = [k for k in p["marks"] if k["kind"] == "entry" and k["label"] == "countersubject"]
    assert [(k["voice"], k["start"]) for k in cs] == [(1, 8.5), (0, 24.5), (1, 76.5)]
    assert any("countersubject" in c["text"] and c["at"] == 8.5 for c in p["captions"])


def test_contrapunctus_vi_has_every_form_and_stretto(built):
    m = MARKINGS_BY_ID["contrapunctus06"][1]
    forms = {e["transform"] for e in m["fugue"]["entries"]}
    assert forms == {"none", "inverted", "diminished", "inverted diminished"}
    p = piece(built, "contrapunctus06")
    assert len([k for k in p["marks"] if k["kind"] == "stretto"]) >= 5


def test_canon_per_tonos_ends_in_its_starting_key_after_six_rises(built):
    m = MARKINGS_BY_ID["bwv1079-per-tonos"][1]
    rule = m["canon"][0]["followers"][0]["rule"]
    assert (rule.repeats, rule.per_tonos_step) == (6, 2)
    assert rule.repeats * rule.per_tonos_step == 12  # a whole circle of whole tones
    p = piece(built, "bwv1079-per-tonos")
    notes = p["notes"]
    dux = [n for n in notes if n["v"] == 2]
    first = dux[0]
    second = next(n for n in dux if n["s"] >= first["s"] + 32)
    assert (second["s"] - first["s"], second["p"] - first["p"]) == (32, 2)  # one rise
    last_onset = max(n["s"] for n in notes)
    assert last_onset == 6 * 32  # after six passes
    final = [n["p"] for n in notes if n["s"] == last_onset]
    assert min(final) % 12 == 0  # C in the bass of the closing chord
    assert {x % 12 for x in final} <= {0, 3, 4, 7}  # a C chord
    first_theme = min((n for n in notes if n["v"] == 0), key=lambda n: n["s"])
    assert first_theme["p"] % 12 == 0  # the piece began on C


def test_the_crab_canon_voices_are_exact_retrogrades(built):
    p = piece(built, "bwv1079-cancrizans")
    notes = p["notes"]
    end = max(n["s"] + n["d"] for n in notes)
    fwd = sorted((n["p"], n["s"], n["d"]) for n in notes if n["v"] == 0)
    back = sorted((n["p"], end - n["s"] - n["d"], n["d"]) for n in notes if n["v"] == 1)
    assert fwd == back and len(fwd) == 89
    assert all(t["kind"] == "retrograde" and not t["broken"] for t in p["threads"])


@pytest.mark.parametrize("pid", [pid for pid, m in _canons() if any(
    f["rule"].free for sec in m["canon"] for f in sec["followers"])])
def test_free_ranges_contain_no_imitation(pid):
    """A free range must not hide real imitation: no leader note inside one has a
    follower note where the rule predicts it, at the predicted pitch or a semitone off."""
    from dataclasses import replace

    from fugue_prep.canon import match
    m = MARKINGS_BY_ID[pid][1]
    voices = load_voices(m, MARKINGS)
    for sec in m["canon"]:
        leader = voices[sec["leader"]]
        for f in sec["followers"]:
            rule = f["rule"]
            threads = match(leader, voices[f["voice"]], replace(rule, free=()),
                            f["tolerance_beats"])
            hidden = [leader[t.a].s for t in threads if not t.broken
                      and any(lo <= leader[t.a].s < hi for lo, hi in rule.free)]
            assert hidden == [], f"{pid}: imitation inside free ranges at beats {hidden}"


@pytest.mark.parametrize("pid", [pid for pid, _ in _fugues()])
def test_fugue_captions_sit_on_entries(built, pid):
    """Each caption of a fugue appears when the entry it names begins."""
    m = MARKINGS_BY_ID[pid][1]
    starts = {e["start"] for e in m["fugue"]["entries"]}
    for c in piece(built, pid)["captions"]:
        assert c["at"] in starts, f"{pid}: caption at beat {c['at']} is on no entry: {c['text']}"


def test_crab_canon_captions_start_together(built):
    caps = piece(built, "bwv1079-cancrizans")["captions"]
    assert caps[0]["at"] == 0 and "backwards" in caps[0]["text"]  # delay 0: both at once


# --- the other Musical Offering canons ---

# Per canon section: (leader voice, follower voice, delay in beats, pitch fact, by contrary
# motion?). The pitch fact is the follower's distance from the leader in semitones (signed:
# + = higher), or for a mirror canon the sum of the two pitches (constant: the axis is half
# of it). Checked against the notes by test_musical_offering_rule_from_the_first_pair.
MUSICAL_OFFERING = {
    "bwv1079-thema-regium": [(0, 2, 4, -24, False)],     # two octaves lower, a bar later
    "bwv1079-violini-in-unisono": [(0, 1, 4, 0, False)],  # unison, a bar later
    "bwv1079-fuga-canonica": [(1, 0, 40, 7, False)],      # a fifth higher, ten bars later
    "bwv1079-quaerendo": [(0, 1, 10, 110, True)],         # mirror about g (55), 2½ bars
    # the BGA's resolution (IMSLP10042 pp. 50-51): bass I two octaves lower 7 bars later,
    # treble II at the same pitch 14 bars later, bass II two octaves lower 21 bars later
    "bwv1079-canon-a4": [(0, 2, 28, -24, False), (0, 1, 56, 0, False),
                         (0, 3, 84, -24, False)],
    # mirror two bars (8 beats) later, pitch sum 151; for the flute's notes from bar 18
    # beat 4 (beat 71; the violin answers from bar 20, beat 79) to the repeat a minor
    # seventh lower (141); each of the three times round
    "bwv1079-canone-perpetuo": [(0, 1, 8, 151, True), (0, 1, 8, 141, True),
                                (0, 1, 8, 151, True), (0, 1, 8, 141, True),
                                (0, 1, 8, 151, True)],
}
THEMA_REGIUM = [60, 63, 67, 68, 59]  # c e♭ g a♭ b♮: the royal theme's head


@pytest.mark.parametrize("pid", list(MUSICAL_OFFERING))
def test_musical_offering_rule_from_the_first_pair(built, pid):
    m = MARKINGS_BY_ID[pid][1]
    p = piece(built, pid)
    assert m["ensemble"] == "chamber"
    secs = [(sec, f) for sec in m["canon"] for f in sec["followers"]]
    assert len(secs) == len(MUSICAL_OFFERING[pid])
    for (sec, f), (lv, fv, delay, fact, mirror) in zip(secs, MUSICAL_OFFERING[pid]):
        rule = f["rule"]
        assert (sec["leader"], f["voice"]) == (lv, fv), pid
        assert rule.delay == delay and (rule.invert_about is not None) == mirror, pid
        assert not rule.diatonic, pid  # every one of these is at exact intervals
        pairs = _first_pairs(p, sec, f)
        a, b = pairs[0]
        assert b["s"] - a["s"] == delay, pid
        if mirror:
            assert a["p"] + b["p"] == fact, pid
            a2, b2 = next((x, y) for x, y in pairs[1:] if x["p"] != a["p"])
            assert (a2["p"] - a["p"]) * (b2["p"] - b["p"]) < 0, pid
        else:
            assert b["p"] - a["p"] == fact, pid


@pytest.mark.parametrize("pid", list(MUSICAL_OFFERING))
def test_musical_offering_captions_sit_on_the_entries(built, pid):
    """The follower's entry gets a caption on the beat it sounds in, its leader one in the
    bar before its first imitated note (the first section of each)."""
    m = MARKINGS_BY_ID[pid][1]
    p = piece(built, pid)
    at = {c["at"] for c in p["captions"]}
    sec = m["canon"][0]
    a, b = _first_pairs(p, sec, sec["followers"][0])[0]
    assert any(a["s"] - p["beatsPerBar"] < x <= a["s"] for x in at), pid
    assert math.floor(b["s"]) in at, f"{pid}: no caption on the entry beat {b['s']}"


# what the entry caption must say, from the table: the interval (or the mirror) and the delay
INTERVAL_WORDS = {-24: "two octaves lower", 0: "same pitch", 7: "a fifth higher"}
BAR_WORDS = {1: "one bar later", 2: "two bars later", 2.5: "two and a half bars later",
             7: "seven bars later", 10: "ten bars later"}


@pytest.mark.parametrize("pid", list(MUSICAL_OFFERING))
def test_musical_offering_entry_captions_say_what_the_notes_do(built, pid):
    m = MARKINGS_BY_ID[pid][1]
    p = piece(built, pid)
    lv, fv, delay, fact, mirror = MUSICAL_OFFERING[pid][0]
    sec = m["canon"][0]
    _, b = _first_pairs(p, sec, sec["followers"][0])[0]
    text = {c["at"]: c["text"] for c in p["captions"]}[math.floor(b["s"])]
    assert BAR_WORDS[delay / p["beatsPerBar"]] in text, text
    if mirror:
        assert "upside down" in text or "contrary motion" in text, text
    else:
        assert INTERVAL_WORDS[fact] in text, text


# The royal theme as the plates give it (IMSLP10042 p. 41, Kirnberger; p. 10 for the
# Fuga canonica's dux): one pass of each voice that carries it, in MIDI pitches.
THEMA_PASS = {
    # Canon perpetuus super thema regium, the violin (alto), 5 bars: c e♭ g a♭ | b r r g |
    # f♯ f e e♭~ | e♭ d d♭ c b a g. b c f | e e♭~ e♭ d c d d(tr)
    "bwv1079-thema-regium": [60, 63, 67, 68, 59, 67, 66, 65, 64, 63, 62, 61, 60, 59, 57, 55,
                             59, 60, 65, 64, 63, 62, 60, 62, 62],
    # Violini in unisono, the bass, 8 bars: c e♭ | g a♭ | b r g | f♯ f | e e♭~ |
    # e♭ d d♭ c | b g c f~ | f e♭ d
    "bwv1079-violini-in-unisono": [48, 51, 55, 56, 47, 55, 54, 53, 52, 51, 50, 49, 48, 47, 43,
                                   48, 53, 51, 50],
}


def test_the_royal_theme_is_written_in_full(built):
    """Every pass of the theme-carrying voice, note for note, then the closing note."""
    p = [n["p"] for n in piece(built, "bwv1079-thema-regium")["notes"] if n["v"] == 1]
    one = THEMA_PASS["bwv1079-thema-regium"]
    assert p == one * 3 + one[:19] + [64]  # the fourth pass cut at beat 76; e' in the chord
    p = [n["p"] for n in piece(built, "bwv1079-violini-in-unisono")["notes"] if n["v"] == 2]
    assert p == THEMA_PASS["bwv1079-violini-in-unisono"] * 4 + [48]  # four passes, then c
    dux = [n["p"] for n in piece(built, "bwv1079-fuga-canonica")["notes"] if n["v"] == 1]
    # the Fuga canonica's dux opens with the theme in long notes, bars 1-8
    assert dux[:20] == [60, 63, 67, 68, 59, 67, 66, 65, 64, 63, 62, 61, 60, 59, 57, 55, 60,
                        65, 63, 62]


# instruments per voice, from the plates' scoring where they give one
INSTRUMENTS = {
    "bwv1079-thema-regium": ["flute", "violin", "cello"],     # Reccmo's (no scoring printed)
    "bwv1079-violini-in-unisono": ["violin", "violin", "cello"],  # "Violino I, II" (p. 41)
    "bwv1079-fuga-canonica": ["flute", "harpsichord", "harpsichord"],  # "Flauto e Violino",
    # "Cembalo" (p. 43)
    "bwv1079-quaerendo": ["viola", "cello"],                  # tenor and bass clefs (p. 20)
    # the BGA names no instruments (pp. 50-51: two treble staves, two bass staves)
    "bwv1079-canon-a4": ["flute", "violin", "cello", "harpsichord"],
    "bwv1079-canone-perpetuo": ["flute", "violin", "cello"],  # "Flauto traverso, Violino,
    # Continuo" (p. 36)
}


@pytest.mark.parametrize("pid", list(INSTRUMENTS))
def test_musical_offering_instruments(built, pid):
    assert [v["instrument"] for v in piece(built, pid)["voices"]] == INSTRUMENTS[pid]


def test_the_fuga_canonica_bass_keeps_its_unisons_with_the_dux(built):
    """Where both harpsichord hands sound c' (IMSLP10042 p. 43 bars 16-17, p. 44 bars
    51-53) each hand has its own note, as printed."""
    notes = piece(built, "bwv1079-fuga-canonica")["notes"]
    bass = {(n["p"], n["s"], n["d"]) for n in notes if n["v"] == 2}
    dux = {(n["p"], n["s"], n["d"]) for n in notes if n["v"] == 1}
    assert {(60, 61, 0.5), (60, 62, 2.5), (60, 202, 3), (58, 207, 2)} <= bass
    assert {(60, 61, 0.5), (60, 63.5, 0.5), (60, 203, 0.5), (58, 208.5, 0.5)} <= dux


def test_the_fuga_canonica_bass_is_free(built):
    """The canon is the flute and the harpsichord's right hand; the bass is no part of it."""
    p = piece(built, "bwv1079-fuga-canonica")
    notes = p["notes"]
    assert {(notes[t["a"]]["v"], notes[t["b"]]["v"]) for t in p["threads"]} == {(1, 0)}
    assert all(not t["broken"] and not t["adjusted"] for t in p["threads"])


def test_the_canone_perpetuo_mirror_drops_a_seventh(built):
    m = MARKINGS_BY_ID["bwv1079-canone-perpetuo"][1]
    assert m["source"].get("score") is True  # matched against the printed score
    spans = [sec["span"] for sec in m["canon"]]
    # the flute's notes from bar 18 beat 4 to the repeat; the violin answers from bar 20
    assert spans[1] == (71, 121) and spans[3] == (191, 241)
    p = piece(built, "bwv1079-canone-perpetuo")
    notes = p["notes"]
    sums = {}
    for t in p["threads"]:
        a, b = notes[t["a"]], notes[t["b"]]
        if not t["adjusted"]:
            sums.setdefault(any(lo <= a["s"] < hi for lo, hi in (spans[1], spans[3])),
                            set()).add(a["p"] + b["p"])
    assert sums == {False: {151}, True: {141}}
    assert all(not t["broken"] for t in p["threads"])
    caps = {c["at"]: c["text"] for c in p["captions"]}
    assert "seventh" in caps[79]  # the violin's first note on the new axis


# The Canon a 4's riddle line as read from the plate (IMSLP10042 p. 20), bar by bar from
# the opening quarter rest to the repeat sign: Bach's notes, in MIDI pitches.
CANON_A4_LINE = [
    [67, 69, 70, 72, 74, 75], [66, 74], [73, 69, 71, 72], [71, 67, 69, 70],
    [69, 68, 69, 68, 67, 66, 67], [66, 64, 62, 63, 62, 66, 69, 72],
    [70, 74, 78, 79, 69, 75, 74, 72], [70, 69, 67, 66, 67, 79, 77, 75, 74, 72, 70, 69, 67],
    [69, 70, 72, 74, 77, 76, 79], [77, 76, 74, 73, 75, 74, 77], [75, 74, 72, 71, 74, 73, 76],
    [74, 72, 71, 74, 72, 71, 72], [67, 66, 67, 69, 62, 74], [72, 70, 72, 70, 69],
    [70, 72, 70, 69, 67, 69, 70, 72], [74, 75, 74, 72, 70, 69, 67, 70], [69, 67, 66, 69],
    [67, 65, 64, 67], [65, 65, 72, 75], [74, 67, 66, 62], [67, 63, 60, 62],
    [67, 79, 81, 82, 84, 86, 84, 82], [81, 78, 79, 81, 74], [76, 77, 79, 81],
    [74, 76, 78, 79], [74, 75, 69], [81, 82, 84, 82, 84, 81, 78], [79, 70, 75, 66], [67],
]
DARDEL = SOURCES / "other" / "dardel-BWV1079_11-canon-a-4.mid"


def test_the_canon_a4_line_is_the_plates(built):
    """The flute plays the riddle line three times, bar by bar as printed (a note tied over
    the bar line counts in the bar it starts in), then holds its g' at beat 336."""
    p = piece(built, "bwv1079-canon-a4")
    flute = [n for n in p["notes"] if n["v"] == 0]
    bars = {}
    for n in flute:
        if n["s"] < 113:
            bars.setdefault(int(n["s"] // 4), []).append(n["p"])
    assert [bars[b] for b in sorted(bars)] == CANON_A4_LINE
    one = [n["p"] for n in flute if n["s"] < 113]
    assert [n["p"] for n in flute] == one * 3 and flute[-1]["s"] == 336
    assert flute[0]["s"] == 1 and flute[-1]["d"] == 2  # after the quarter rest; the end


def test_the_canon_a4_entries_follow_the_resolution(built):
    """IMSLP10042 pp. 50-51: the four voices begin on g', G, g', G, seven bars apart, each
    with the riddle's first note; all four stop together at beat 338."""
    p = piece(built, "bwv1079-canon-a4")
    first = {}
    for n in p["notes"]:
        first.setdefault(n["v"], (n["s"], n["p"]))
    assert first == {0: (1, 67), 2: (29, 43), 1: (57, 67), 3: (85, 43)}
    ends = {v: max(n["s"] + n["d"] for n in p["notes"] if n["v"] == v) for v in range(4)}
    assert set(ends.values()) == {338}
    assert all(not t["broken"] and not t["adjusted"] for t in p["threads"])
    caps = {c["at"]: c["text"] for c in p["captions"]}
    assert "same pitch" in caps[57] and "fourteen bars" in caps[57]
    assert "two octaves below the flute, like the cello" in caps[85]
    assert len(caps[85]) <= 80


@pytest.mark.skipif(not DARDEL.exists(), reason="dardel.info MIDI not downloaded (git-ignored)")
def test_the_canon_a4_agrees_with_dardels_midi_note_for_note(built):
    """dardel.info's MIDI (four tracks, one per voice, in the BGA's staff order) is a
    check, not the source: every computed note, ending included, is in it, and nothing
    else."""
    import mido
    mid = mido.MidiFile(DARDEL)
    want = []
    for v, track in enumerate(mid.tracks[1:]):
        tick, on = 0, {}
        for msg in track:
            tick += msg.time
            if msg.type == "note_on" and msg.velocity:
                on[msg.note] = tick
            elif msg.type in ("note_on", "note_off") and msg.note in on:
                s = on.pop(msg.note)
                want.append((v, msg.note, s / mid.ticks_per_beat, (tick - s) / mid.ticks_per_beat))
    p = piece(built, "bwv1079-canon-a4")
    got = [(n["v"], n["p"], n["s"], n["d"]) for n in p["notes"]]
    assert sorted(got) == sorted(want)


def test_the_quaerendo_resolution_is_cited():
    m = MARKINGS_BY_ID["bwv1079-quaerendo"][1]
    text = m["file"].read_text()
    assert "solution A" in text and "Allgemeine Musikalische Zeitung" in text


# --- the Goldberg canons: one canon at every interval from the unison to the ninth ---

# Per canon section: (leader voice, follower voice, delay in beats, interval in scale
# steps (signed: + = the follower is higher), by contrary motion?). Checked against the
# music, bar by bar (see each markings file). Var. 12, 24 and 27 swap roles.
GOLDBERG = {
    "goldberg-var03": [(0, 1, 6, 0, False)],
    "goldberg-var06": [(1, 0, 3, 1, False)],
    "goldberg-var09": [(0, 1, 4, -2, False)],
    "goldberg-var12": [(0, 1, 3, -3, True), (1, 0, 3, 3, True)],
    "goldberg-var15": [(1, 0, 2, 4, True)],
    "goldberg-var18": [(1, 0, 1, 5, False)],
    "goldberg-var21": [(1, 0, 2, 6, False)],
    "goldberg-var24": [(0, 1, 18, -7, False), (1, 0, 18, 7, False), (1, 0, 18, 7, False),
                       (0, 1, 18, -7, False)],
    "goldberg-var27": [(1, 0, 6, 8, False), (0, 1, 6, -8, False)],
}
# semitones a diatonic interval of n steps can span (major/minor/perfect/augmented)
SEMITONES = {0: {0}, 1: {1, 2}, 2: {3, 4}, 3: {5, 6}, 4: {6, 7}, 5: {8, 9}, 6: {10, 11},
             7: {12}, 8: {13, 14}}


def test_goldberg_steps_through_every_interval():
    steps = sorted({abs(sec[3]) for secs in GOLDBERG.values() for sec in secs})
    assert steps == list(range(9))
    assert set(GOLDBERG) == set(PIECES["goldberg"])


def _first_pairs(p: dict, sec: dict, f: dict) -> list[tuple[dict, dict]]:
    notes = p["notes"]
    free = _free(f["rule"], sec["span"])
    pairs = [(notes[t["a"]], notes[t["b"]]) for t in p["threads"]
             if not t["broken"] and not t["adjusted"] and notes[t["a"]]["v"] == sec["leader"]
             and notes[t["b"]]["v"] == f["voice"]
             and not any(lo <= notes[t["a"]]["s"] < hi for lo, hi in free)]
    return sorted(pairs, key=lambda ab: ab[0]["s"])


@pytest.mark.parametrize("pid", list(GOLDBERG))
def test_goldberg_canon_interval_direction_and_delay(built, pid):
    m = MARKINGS_BY_ID[pid][1]
    p = piece(built, pid)
    assert m["ensemble"] == "harpsichord"
    secs = [(sec, f) for sec in m["canon"] for f in sec["followers"]]
    assert len(secs) == len(GOLDBERG[pid])
    for (sec, f), (lv, fv, delay, steps, mirror) in zip(secs, GOLDBERG[pid]):
        rule = f["rule"]
        assert (sec["leader"], f["voice"]) == (lv, fv), pid
        assert rule.delay == delay and rule.interval == steps, pid
        assert (rule.invert_about is not None) == mirror, pid
        pairs = _first_pairs(p, sec, f)
        (a, b) = pairs[0]
        assert b["s"] - a["s"] == delay, pid
        sign = 1 if steps >= 0 else -1
        assert b["p"] - a["p"] in {sign * x for x in SEMITONES[abs(steps)]}, pid
        if mirror:
            # contrary motion: where the leader first moves, the follower moves the other way
            a2, b2 = next((x, y) for x, y in pairs[1:] if x["p"] != a["p"])
            assert (a2["p"] - a["p"]) * (b2["p"] - b["p"]) < 0, pid


@pytest.mark.parametrize("pid", list(GOLDBERG))
def test_goldberg_captions_sit_on_the_entries(built, pid):
    """Each section's follower gets a caption on the beat its first imitated note sounds
    in; its leader one within the bar before its first imitated note."""
    m = MARKINGS_BY_ID[pid][1]
    p = piece(built, pid)
    at = {c["at"] for c in p["captions"]}
    for sec in m["canon"]:
        for f in sec["followers"]:
            a, b = _first_pairs(p, sec, f)[0]
            assert any(a["s"] - p["beatsPerBar"] < x <= a["s"] for x in at), \
                f"{pid}: no caption for the leader at beat {a['s']}"
            assert math.floor(b["s"]) in at, f"{pid}: no caption on the entry beat {b['s']}"


@pytest.mark.parametrize("pid,beat", [("goldberg-var12", 46.75), ("goldberg-var24", 66),
                                      ("goldberg-var24", 72)])
def test_no_thread_from_a_note_that_is_not_imitated(built, pid, beat):
    """Chance landings near a leader note's image (a cadence, a voice starting its own
    lead) are named in not_imitation and draw no thread."""
    m = MARKINGS_BY_ID[pid][1]
    assert any(beat in f["rule"].not_imitation for sec in m["canon"] for f in sec["followers"])
    p = piece(built, pid)
    notes = p["notes"]
    leaders = {sec["leader"] for sec in m["canon"]}
    from_beat = [t for t in p["threads"]
                 if notes[t["a"]]["s"] == beat and notes[t["a"]]["v"] in leaders]
    assert from_beat == [], f"{pid}: a thread starts at beat {beat}"


# --- the fifteen two-part Inventions, BWV 772-786 ---

INVENTIONS = [p for p in PIECES["inventions"] if p.startswith("invention")]
# Per piece: (beats per bar, beat in quarter notes) from the time signature, and the
# motive's first statement: (voice, start beat, its opening pitches), checked against the
# score. Inventions 2 and 8 are marked as canons; there the line is the leader's opening.
INVENTION_FACTS = {
    "invention01": (4, 1, 0, 0.25, [60, 62, 64, 65, 62, 64, 60]),        # C D E F D E C
    "invention02": (4, 1, 0, 0.5, [72, 71, 72, 74, 75, 67, 68, 70]),     # c b c d eb g ab bb
    "invention03": (3, 0.5, 0, 0, [62, 64, 66, 64, 67, 66, 64, 62]),     # D E F# E G F# E D
    "invention04": (3, 0.5, 0, 0, [62, 64, 65, 67, 69, 70, 61]),         # D E F G A Bb C#
    "invention05": (4, 1, 0, 0.5, [63, 62, 63, 65, 67, 68]),             # Eb D Eb F G Ab
    "invention06": (3, 0.5, 0, 0.5, [76, 75, 74, 73, 71, 69, 68, 66]),   # E D# D C# B A G# F#
    "invention07": (4, 1, 0, 0.5, [71, 69, 67, 66, 67, 64]),             # B A G F# G E
    "invention08": (3, 1, 0, 0.5, [65, 69, 65, 72, 65, 77]),             # F A F C F F
    "invention09": (3, 1, 0, 0, [72, 70, 68, 67, 68, 65, 73]),           # C Bb Ab G Ab F Db
    "invention10": (9, 0.5, 0, 0, [67, 71, 74, 71, 67, 74, 71, 67]),     # G B D B G D B G
    "invention11": (4, 1, 0, 0.25, [62, 64, 66, 67, 69, 70, 67, 69]),    # D E F# G A Bb G A
    "invention12": (6, 1, 0, 0, [69, 69, 69, 69, 71]),                   # A A A A B
    "invention13": (4, 1, 0, 0.25, [64, 69, 72, 71, 64, 71, 74, 72]),    # E A C B E B D C
    "invention14": (4, 1, 0, 0.25, [70, 72, 74, 72, 70, 77, 74, 82, 77]),  # Bb C D C Bb F D Bb F
    "invention15": (4, 1, 0, 0.5, [71, 70, 71, 66, 67, 66, 71, 66]),     # B A# B F# G F# B F#
}
# canon sections (Inventions 2 and 8): (leader, follower, delay in beats, semitones)
INVENTION_CANONS = {
    "invention02": [(0, 1, 8, -12), (1, 0, 8, 12)],
    "invention08": [(0, 1, 3, -12), (1, 0, 3, 24), (0, 1, 3, -12)],
}


def test_every_invention_has_a_fact_row():
    assert set(INVENTION_FACTS) == set(INVENTIONS)


@pytest.mark.parametrize("pid", INVENTIONS)
def test_invention_motive_is_the_opening_of_the_score(built, pid):
    """The marked motive (or the canon's leader) begins where the score's first statement
    does, with the score's opening pitches; bar length and beat follow the time signature."""
    bpb, unit, voice, start, pitches = INVENTION_FACTS[pid]
    m = MARKINGS_BY_ID[pid][1]
    p = piece(built, pid)
    assert (p["beatsPerBar"], p["beatUnit"]) == (bpb, unit)
    assert "alternatives" not in m["source"]  # no dropped notes
    assert m["source"]["path"].startswith("inventions/kern/inven")
    voices = load_voices(m, MARKINGS)
    if m["fugue"]:
        spec = m["fugue"]["subject"]
        assert (spec["voice"], spec["start"]) == (voice, start)
        notes = subject_notes(voices, spec)
        assert [n.p for n in notes[:len(pitches)]] == pitches
        first = next(e for e in m["fugue"]["entries"] if e["form"] == "motive")
        assert (first["voice"], first["start"]) == (voice, start)
    else:
        lead = [n for n in voices[voice] if n.s >= start][:len(pitches)]
        assert lead[0].s == start and [n.p for n in lead] == pitches
        assert m["canon"][0]["leader"] == voice


@pytest.mark.parametrize("pid", list(INVENTION_CANONS))
def test_invention_canons_follow_at_the_octave(built, pid):
    m = MARKINGS_BY_ID[pid][1]
    p = piece(built, pid)
    secs = [(sec, f) for sec in m["canon"] for f in sec["followers"]]
    assert len(secs) == len(INVENTION_CANONS[pid])
    at = {c["at"] for c in p["captions"]}
    for (sec, f), (lv, fv, delay, semis) in zip(secs, INVENTION_CANONS[pid]):
        rule = f["rule"]
        assert (sec["leader"], f["voice"], rule.delay, rule.interval) == (lv, fv, delay, semis)
        assert not rule.diatonic and sec["span"] is not None
        a, b = _first_pairs(p, sec, f)[0]
        assert (b["s"] - a["s"], b["p"] - a["p"]) == (delay, semis), pid
        # a caption for the leader within the bar before its first imitated note, and one
        # for the follower within the beat before its first answering note
        assert any(a["s"] - p["beatsPerBar"] < x <= a["s"] for x in at), (pid, a["s"])
        assert any(b["s"] - 1 <= x <= b["s"] for x in at), (pid, b["s"])


@pytest.mark.parametrize("pid", INVENTIONS)
def test_invention_captions_speak_of_motives(built, pid):
    caps = piece(built, pid)["captions"]
    texts = " ".join(c["text"] for c in caps).lower()
    assert "subject" not in texts.replace("countersubject", ""), pid
    m = MARKINGS_BY_ID[pid][1]
    assert "motive" in texts or m["canon"], pid
    assert "canon" in texts or not m["canon"], pid


def test_invention_motives_turn_upside_down_and_overlap(built):
    """Facts from the scores: Invention 1 inverts its motive in both voices, 14 answers each
    half bar with the motive inverted, 11 inverts its chromatic countermotive, 10 brings the
    motive in stretto (one eighth apart) in bars 27 and 28, and in 6 the two lines swap
    voices (invertible counterpoint)."""
    def entries(pid):
        return MARKINGS_BY_ID[pid][1]["fugue"]["entries"]
    inv1 = {e["voice"] for e in entries("invention01") if e["transform"] == "inverted"}
    assert inv1 == {0, 1}
    assert sum(e["transform"] == "inverted" for e in entries("invention14")) >= 8
    assert any(e["form"] == "countermotive" and e["transform"] == "inverted"
               for e in entries("invention11"))
    stretti = [k for k in piece(built, "invention10")["marks"] if k["kind"] == "stretto"]
    assert [math.floor(k["start"] / 9) + 1 for k in stretti] == [27, 28]
    six = entries("invention06")
    assert {e["voice"] for e in six if e["form"] == "motive"} == {0, 1}
    assert {e["voice"] for e in six if e["form"] == "countermotive"} == {0, 1}


@pytest.mark.parametrize("pid", INVENTIONS)
def test_invention_entries_are_motives_and_countermotives(built, pid):
    """Inventions speak of motives: their entry marks (and so the roll's labels and rail
    pointer) say motive/countermotive, never the fugue's subject/answer/countersubject."""
    m = MARKINGS_BY_ID[pid][1]
    if m["canon"]:
        return
    assert {e["form"] for e in m["fugue"]["entries"]} <= {"motive", "countermotive"}
    labels = {k["label"].split()[0] for k in piece(built, pid)["marks"] if k["kind"] == "entry"}
    assert labels <= {"motive", "countermotive"} and "motive" in labels


def test_fugues_keep_their_subjects(built):
    for pid in (*PIECES["wtc"], "contrapunctus01", "contrapunctus06"):
        forms = {e["form"] for e in MARKINGS_BY_ID[pid][1]["fugue"]["entries"]}
        assert forms <= {"subject", "answer", "countersubject"}, pid


def test_invention_3_opens_with_its_upbeat(built):
    """The score opens with a one-eighth upbeat (D-E sixteenths) before bar 1: Bach's bar n
    starts at beat 1 + 3(n-1). Every motive begins on the last eighth of a bar, so the bar
    it is labelled with is the bar it starts in."""
    p = piece(built, "invention03")
    assert p["pickup"] == 1 and p["notes"][0]["s"] == 0
    starts = [k["start"] for k in p["marks"] if k["kind"] == "entry"]
    assert all((s - 1) % 3 == 2 for s in starts[1:]) and starts[0] == 0
    bars = [math.floor((s - p["pickup"]) / p["beatsPerBar"]) + 1 for s in starts]
    assert bars[:4] == [0, 2, 12, 14]  # the upbeat, then bass bar 2 into 3, ...


# --- the fifteen three-part Sinfonias, BWV 787-801 ---

SINFONIAS = [p for p in PIECES["inventions"] if p.startswith("sinfonia")]
# Per piece: (beats per bar, beat in quarter notes) from the time signature, and the
# motive's first statement: (voice, start beat, its opening pitches), checked against the
# score (voices: 0 upper, 1 middle, 2 lower).
SINFONIA_FACTS = {
    "sinfonia01": (4, 1, 0, 0.25, [67, 69, 71, 72, 74, 76, 77, 79]),     # G A B C D E F G
    "sinfonia02": (12, 0.5, 0, 0, [72, 67, 75, 75, 72, 79]),            # C G Eb Eb C G
    "sinfonia03": (4, 1, 0, 0.5, [78, 79, 81, 72, 71, 76]),             # F# G A C B E
    "sinfonia04": (4, 1, 0, 0.25, [74, 73, 74, 69, 77]),                # D C# D A F
    "sinfonia05": (3, 1, 0, 1.75, [70, 75, 77, 74]),                    # Bb Eb F D
    "sinfonia06": (9, 0.5, 1, 0, [64, 66, 68, 69, 71, 73, 71, 73, 69]),  # E F# G# A B C# B C# A
    "sinfonia07": (3, 1, 0, 0.5, [71, 76, 78, 79, 78, 81]),             # B E F# G F# A
    "sinfonia08": (4, 1, 1, 0.5, [72, 69, 74, 72, 70, 69, 67]),         # C A D C Bb A G
    "sinfonia09": (4, 1, 1, 0.5, [65, 68, 67, 67, 70, 69]),             # F Ab G G Bb A
    "sinfonia10": (3, 1, 0, 0.5, [67, 66, 67, 69, 71, 72, 74, 71]),     # G F# G A B C D B
    "sinfonia11": (3, 0.5, 0, 0.5, [74, 70, 67, 79]),                   # D Bb G G
    "sinfonia12": (4, 1, 0, 0, [69, 68, 69, 71, 69, 68, 69]),           # A G# A B A G# A
    "sinfonia13": (3, 0.5, 0, 0, [69, 71, 72, 74, 72, 71]),             # A B C D C B
    "sinfonia14": (4, 1, 1, 1.25, [70, 69, 67, 65, 67, 62, 63, 65]),    # Bb A G F G D Eb F
    "sinfonia15": (3, 0.75, 0, 0, [71, 66, 66, 67, 66, 66, 71]),        # B F# F# G F# F# B
}


def test_every_sinfonia_has_a_fact_row():
    assert set(SINFONIA_FACTS) == set(SINFONIAS) and len(SINFONIAS) == 15


@pytest.mark.parametrize("pid", SINFONIAS)
def test_sinfonia_motive_is_the_opening_of_the_score(built, pid):
    """Three voices, read whole (no dropped notes); the marked motive begins where the
    score's first statement does, with the score's pitches; bar and beat follow the time
    signature; the piece sits in the book Sinfonias, in BWV order."""
    bpb, unit, voice, start, pitches = SINFONIA_FACTS[pid]
    m = MARKINGS_BY_ID[pid][1]
    p = piece(built, pid)
    assert (p["beatsPerBar"], p["beatUnit"]) == (bpb, unit)
    assert len(p["voices"]) == 3 and "alternatives" not in m["source"]
    n = int(pid[-2:])
    assert m["source"]["path"] == f"inventions/kern/sinfo{n:02d}.krn"
    assert (m["book"], m["order"], m["catalogue"]) == ("Sinfonias", n, f"BWV {786 + n}")
    voices = load_voices(m, MARKINGS)
    spec = m["fugue"]["subject"]
    assert (spec["voice"], spec["start"]) == (voice, start)
    assert [x.p for x in subject_notes(voices, spec)[:len(pitches)]] == pitches
    first = min(m["fugue"]["entries"], key=lambda e: e["start"])
    assert (first["voice"], first["start"], first["form"]) == (voice, start, "motive")


@pytest.mark.parametrize("pid", SINFONIAS)
def test_sinfonia_captions_and_entries_speak_of_motives(built, pid):
    m = MARKINGS_BY_ID[pid][1]
    texts = " ".join(c["text"] for c in piece(built, pid)["captions"]).lower()
    assert "motive" in texts and "subject" not in texts, pid
    assert {e["form"] for e in m["fugue"]["entries"]} <= {"motive", "countermotive"}
    labels = {k["label"].split()[0] for k in piece(built, pid)["marks"] if k["kind"] == "entry"}
    assert labels <= {"motive", "countermotive"}


def test_sinfonia_facts_from_the_scores(built):
    """What the markings claim about the music, read from the scores when writing them. The
    entries themselves are checked against the score by test_every_fugue_entry_is_found;
    here: Sinfonia 1 marks inversions in all three voices; 8 marks two strettos, in bars 7
    and 8; 6 marks the motive and its inversion starting together in bar 35; 9 pairs each
    of its 10 motives with a countermotive half a beat later, and that countermotive is a
    chromatic descent in the score (five falling semitones); 15 (9/16) counts three dotted
    eighths a bar, at ♪. = 64 (192 sixteenths a minute)."""
    def entries(pid):
        return MARKINGS_BY_ID[pid][1]["fugue"]["entries"]
    assert {e["voice"] for e in entries("sinfonia01") if e["transform"] == "inverted"} == {0, 1, 2}
    stretti = [k for k in piece(built, "sinfonia08")["marks"] if k["kind"] == "stretto"]
    assert [math.floor(k["start"] / 4) + 1 for k in stretti] == [7, 8]
    bar35 = [(e["voice"], e["transform"]) for e in entries("sinfonia06") if e["start"] == 306]
    assert sorted(bar35) == [(0, "inverted"), (1, "none")]
    nine = entries("sinfonia09")
    motives = sorted(e["start"] for e in nine if e["form"] == "motive")
    counter = sorted(e["start"] for e in nine if e["form"] == "countermotive")
    assert len(motives) == 10 and counter == [s + 0.5 for s in motives]
    voices = load_voices(MARKINGS_BY_ID["sinfonia09"][1], MARKINGS)
    cm = subject_notes(voices, MARKINGS_BY_ID["sinfonia09"][1]["fugue"]["countersubject"])
    assert [b.p - a.p for a, b in zip(cm, cm[1:])] == [-1] * 5
    p15 = piece(built, "sinfonia15")
    assert (p15["beatUnit"], p15["beatsPerBar"], p15["tempo"]) == (0.75, 3, 64)
    assert max(n["s"] for n in p15["notes"]) == 37 * 3  # the last chord on bar 38's downbeat


# --- The Well-Tempered Clavier, Book I: fugues 1-24 (BWV 846-869) ---

WTC = PIECES["wtc"]
# Per fugue: (beats per bar, beat in quarter notes) from the time signature; the subject's
# first statement (voice, start beat, its pitches, checked against the score); and the
# sub-voices dropped as an edition's alternative reading (source.alternatives; None: none).
# Every other split and chord keeps its notes as secondary notes. Fugue 4 is a triple fugue
# (its subject I here); fugue 20's file comments out its last eight bars, read again.
WTC_FACTS = {
    "bwv846": (4, 1, 1, 0.5, [60, 62, 64, 65, 67, 65, 64, 69, 62, 67, 69, 67, 65, 64],
               ["voice 0 bar 9", "voice 0 bar 12", "voice 1 bar 4"]),  # C D E F G F E A D G A G F E
    "bwv847": (4, 1, 1, 0.5, None, None),
    "bwv849": (2, 2, 4, 0, [49, 48, 52, 51], None),  # C# B# E D# (subject I)
    "bwv848": (4, 1, 0, 1.5, [68, 70, 68, 66, 68, 77, 73, 68, 66, 65, 66, 75, 65, 73, 63, 72, 61],
               None),  # G# A# G# F# G# E# C# G# F# E# F# D# E# C# D# B# C#
    "bwv851": (3, 1, 0, 0.5, [62, 64, 65, 67, 64, 65, 62, 61, 62, 70, 67, 69], None),
    "bwv852": (4, 1, 0, 0, [70, 67, 65, 67, 63, 68, 67, 68, 72, 70, 69, 65, 75, 74, 72, 70],
               None),
    "bwv850": (4, 1, 3, 1, [50, 52, 54, 55, 54, 52, 54, 50, 59, 59, 57, 55, 54], None),
    "bwv853": (4, 1, 1, 0, [63, 70, 71, 70, 68, 66, 68, 70, 63, 68, 66, 65, 63], None),
    "bwv854": (4, 1, 1, 1.5, [64, 66, 59, 61, 63, 64, 63, 64, 66, 68, 69, 71, 68], None),
    "bwv855": (3, 1, 0, 0, [64, 67, 71, 76, 75, 76, 74, 76, 73, 76, 72, 76,
                            71, 76, 75, 76, 70, 73, 67, 66, 67, 70, 66, 64], None),
    "bwv856": (3, 0.5, 1, 0, [60, 62, 60, 58, 60, 52, 53, 55, 57, 58, 60, 58, 57, 55, 57], None),
    "bwv857": (4, 1, 2, 1, [60, 61, 60, 59, 64, 65, 58, 57, 56, 55, 53], ["voice 1 bar 41"]),
    "bwv858": (4, 1, 0, 0.5, [73, 78, 77, 78, 77, 75, 73, 71, 73, 75, 73, 71, 70, 68, 73, 70],
               None),  # C# F# E# F# E# D# C#, B C# D#, C# B A# G# C# A#
    "bwv859": (6, 1, 2, 1, [54, 56, 57, 56, 58, 59, 58, 56, 58, 60, 61, 59, 57, 61, 59, 57, 56,
                            54], None),  # F# G# A G# A# B A# G# A# B# C# B A C# B A G# F#
    "bwv860": (6, 0.5, 0, 0, [67, 69, 67, 66, 67, 69, 71, 69, 67, 69, 71, 69, 67, 62, 72, 71, 69,
                              67, 66, 76, 74], None),  # G A G F# G A B A G A B A G D C' B A G F# E' D'
    "bwv861": (4, 1, 1, 0.5, [62, 63, 55, 54, 55, 57, 58, 60, 58, 57, 58],
               None),  # D Eb G F# G A Bb C Bb A Bb
    "bwv862": (4, 1, 2, 1, [56, 63, 60, 56, 65, 61, 63], None),  # Ab Eb C Ab F Db Eb
    "bwv863": (4, 1, 2, 1, [56, 55, 56, 58, 59, 58, 56, 62, 63, 54, 56, 56, 58, 58, 51],
               ["voice 2 bar 32"]),  # G# F## G# A# B A# G# C## D# F# G# G# A# A# D#
    "bwv864": (9, 0.5, 0, 0, [69, 68, 73, 69, 74, 71, 76, 73, 78, 76, 81, 74, 73],
               ["voice 1 bar 51", "voice 1 bar 53"]),  # A G# C# A D B E C# F# E A D C#
    "bwv865": (4, 1, 2, 0.5, [57, 56, 57, 59, 60, 60, 59, 60, 62, 64, 62, 60, 62, 64, 65, 56, 52],
               ["voice 1 bar 69"]),  # A G# A B C C B C D E D C D E F G# E
    "bwv866": (3, 1, 0, 0.5, [65, 67, 65, 70, 62, 60, 69, 67, 70, 69, 67, 65, 72, 63, 62, 70, 72,
                              69, 70, 72, 74, 75, 74, 72, 75, 74, 72, 70, 72, 69, 70, 72, 74, 75,
                              74, 72, 75, 74], None),  # F G F Bb D C A G Bb A G F C Eb D, 2 runs
    "bwv867": (2, 2, 0, 0, [70, 65, 78, 77, 75, 73, 72, 73, 75, 77],
               None),  # Bb F Gb F Eb Db C Db Eb F
    "bwv868": (4, 1, 2, 0.5, [59, 58, 59, 61, 54, 56, 58, 59, 61, 63, 64, 63, 61, 59],
               None),  # B A# B C# F# G# A# B C# D# E D# C# B
    "bwv869": (4, 1, 1, 0.5, [66, 62, 59, 67, 66, 71, 70, 64, 63, 72, 71, 66, 65, 74, 73, 72, 73,
                              69, 66, 68, 66], None),  # F# D B G F# B A# E D# C B F# E# D C# B# C# A F# G# F#
}


def test_every_wtc_fugue_has_a_fact_row():
    assert set(WTC_FACTS) == set(WTC) and len(WTC) == 24  # Book I complete


@pytest.mark.parametrize("pid", WTC)
def test_wtc_fugue_subject_is_the_opening_of_the_score(built, pid):
    """Book I, in BWV order; beats follow the time signature; the subject begins where the
    score's first statement does, with its pitches; the dux is the first entry; spine
    alternatives drop only the sub-voices listed (sic/ossia readings, see SOURCES.md)."""
    from fugue_prep.kern import read_kern
    bpb, unit, voice, start, pitches, dropped = WTC_FACTS[pid]
    m = MARKINGS_BY_ID[pid][1]
    p = piece(built, pid)
    n = int(pid[3:]) - 845
    assert (m["book"], m["catalogue"]) == ("Book I", f"BWV {845 + n}")
    assert m["source"]["path"] == f"bach-wtc-fugues/kern/wtc1f{n:02d}.krn"
    assert m["order"] == n and m["number"] == n
    lib = json.loads((built / "library.json").read_text())
    assert {x["id"]: x for x in lib["pieces"]}[pid]["number"] == n
    assert (p["beatsPerBar"], p["beatUnit"]) == (bpb, unit)
    spec = m["fugue"]["subject"]
    assert (spec["voice"], spec["start"]) == (voice, start)
    voices = load_voices(m, MARKINGS)
    if pitches:
        assert [x.p for x in subject_notes(voices, spec)] == pitches
    first = min(m["fugue"]["entries"], key=lambda e: (e["start"], e["form"] != "subject"))
    assert (first["voice"], first["start"], first["form"]) == (voice, start, "subject")
    warnings: list[str] = []
    read_kern(SOURCES / m["source"]["path"], alternatives=m["source"].get("alternatives", []),
              warnings=warnings, commented_from=m["source"].get("commented_from"))
    assert [w.split("sub-voice at ")[1] for w in warnings] == (dropped or [])
    assert ("alternatives" in m["source"]) == bool(dropped)


def _entry_notes(m, voices, e):
    idx = find_entry(voices, entry_reference(voices, m["fugue"], e), e["voice"], e["start"],
                     e["transform"],
                     head=e["head"], tail=e["tail"], head_length=e["head_length"], octave=e.get("octave", ()))
    return [voices[e["voice"]][i] for i in idx]


def _forms_context(m, voices, e):
    """The subject, the first answer and the statement, cut to the statement's length (a
    head statement keeps only its first notes). In a fugue on several subjects, the
    statement's own subject and that subject's first answer."""
    subj = subject_notes(voices, subject_spec(m["fugue"], e))
    fa = first_answer(m["fugue"], e.get("subject"))
    ans = _entry_notes(m, voices, fa) if fa else None
    got = _entry_notes(m, voices, e)
    k = len(got)
    return subj[:k], (ans[:k] if ans else None), got


def wtc_form(m, voices, e) -> str:
    """The form a statement's notes say it has, from note 2 on (the head may be free):
    where the answer's body (intervals 2..n, in scale steps) differs from the subject's,
    the body that fits better; where the bodies agree (a real answer, or a tonal answer
    that changes only the first interval), or the fits tie (BWV 866 bar 26: one interval
    like the answer's, the next like the subject's), the pitch level of notes 3..n (the
    commonest transposition; a mode change moves a few): the subject's level (the dux's),
    the answer's level, or "neither" (another key). Inverted statements are subjects
    unless their body is the inverted answer's."""
    from fugue_prep.fugue import steps
    subj, ans, got = _forms_context(m, voices, e)
    if ans is None:
        return "subject"
    sign = -1 if e["transform"].startswith("inverted") else 1
    ivs = lambda ns: [b.p - a.p for a, b in zip(ns, ns[1:])][1:]  # noqa: E731
    s_iv, a_iv, g_iv = ivs(subj), ivs(ans), [sign * x for x in ivs(got)]
    if e["tail"] == "free":
        s_iv, a_iv, g_iv = s_iv[:-1], a_iv[:-1], g_iv[:-1]
    same = lambda x, y: bool(steps(x) & steps(y))  # noqa: E731
    if any(not same(a, b) for a, b in zip(s_iv, a_iv)):
        fs = sum(same(g, w) for g, w in zip(g_iv, s_iv))
        fa = sum(same(g, w) for g, w in zip(g_iv, a_iv))
        if fs != fa:
            return "subject" if fs > fa else "answer"
    if sign < 0:
        return "subject"
    def level(ns):
        from collections import Counter
        return Counter((a.p - b.p) % 12 for a, b in zip(ns[2:], subj[2:])).most_common(1)[0][0]
    lv = level(got)
    return "answer" if lv == level(ans) else "subject" if lv == 0 else "neither"


def opening_form(m, voices, e) -> str | None:
    """form_by: opening — the form the first interval says: the answer's opening interval
    (in scale steps) and not the subject's makes an answer; the subject's (or both, a real
    answer) a subject. None: neither."""
    from fugue_prep.fugue import steps
    subj, ans, got = _forms_context(m, voices, e)
    sign = -1 if e["transform"].startswith("inverted") else 1
    g = sign * (got[1].p - got[0].p)
    is_s = bool(steps(g) & steps(subj[1].p - subj[0].p))
    is_a = ans is not None and bool(steps(g) & steps(ans[1].p - ans[0].p))
    if not (is_s or is_a) and e["head"] == "free" and len(got) > 2:
        # a free head's first interval may be anything (BWV 849 bar 12, G# E# for F# E#):
        # where it is neither form's, the next interval decides
        g = sign * (got[2].p - got[1].p)
        is_s = bool(steps(g) & steps(subj[2].p - subj[1].p))
        is_a = ans is not None and bool(steps(g) & steps(ans[2].p - ans[1].p))
    return "subject" if is_s else "answer" if is_a else None


@pytest.mark.parametrize("pid", WTC)
def test_wtc_forms_follow_the_notes(pid):
    """Every statement's label is the form its notes have (wtc_form). A statement at
    neither the subject's nor the answer's pitch level must say so with form_by: opening,
    and then its opening interval decides; form_by: opening anywhere else fails."""
    _forms_follow_the_notes(pid)


def _forms_follow_the_notes(pid):
    m = MARKINGS_BY_ID[pid][1]
    voices = load_voices(m, MARKINGS)
    for e in m["fugue"]["entries"]:
        if e["form"] == "countersubject":
            continue
        got = wtc_form(m, voices, e)
        if e["form_by"] == "opening":
            assert got == "neither", (pid, e["start"], "form_by: opening, but level says", got)
            assert e["form"] == opening_form(m, voices, e), (pid, e["start"], e["form"])
        else:
            assert got != "neither", (pid, e["start"], "neither level: needs form_by: opening")
            assert e["form"] == got, (pid, e["start"], e["form"], got)


def test_wtc_facts_from_the_scores(built):
    """What the markings claim, read from the scores. BWV 846: seven strettos (bars 7, 10,
    14, 16, 19, 20, 24). BWV 853: the inversion from bar 30, a stretto of the inversion in
    bars 44-45, the subject in augmentation in bars 62 (bass), 67 (alto) and 77 (soprano).
    BWV 855: two voices; the countersubject above the answer in bar 3 and below the subject
    in bar 22 (the parts swapped), and bar 19 in octaves. BWV 856 (3/8): three strettos,
    the one of bar 37 an octave apart each time. BWV 857: the countersubject under the
    answer, bar 4."""
    def bars(pid, kind="stretto"):
        p = piece(built, pid)
        return [math.floor((k["start"] - p["pickup"]) / p["beatsPerBar"]) + 1
                for k in p["marks"] if k["kind"] == kind]
    assert bars("bwv846") == [7, 10, 14, 16, 19, 20, 24]
    e853 = MARKINGS_BY_ID["bwv853"][1]["fugue"]["entries"]
    inv = [e["start"] for e in e853 if e["transform"] == "inverted"]
    assert min(inv) == 116 and math.floor(116 / 4) + 1 == 30
    aug = [(math.floor(e["start"] / 4) + 1, e["voice"]) for e in e853 if e["transform"] == "augmented"]
    assert aug == [(62, 2), (67, 1), (77, 0)]
    assert bars("bwv853") == [44, 61, 67]
    e855 = MARKINGS_BY_ID["bwv855"][1]["fugue"]["entries"]
    cs = {(e["start"], e["voice"]) for e in e855 if e["form"] == "countersubject"}
    assert {(6, 0), (63, 1)} <= cs
    v855 = load_voices(MARKINGS_BY_ID["bwv855"][1], MARKINGS)
    bar19 = [[x.p for x in ns if 54 <= x.s < 57] for ns in v855]
    assert len(bar19[0]) == 12 and [a - b for a, b in zip(*bar19)] == [24] * 12
    s856 = [k for k in piece(built, "bwv856")["marks"] if k["kind"] == "stretto"]
    assert [math.floor(k["start"] / 3) + 1 for k in s856] == [26, 37, 47]
    e856 = {e["start"]: e for e in MARKINGS_BY_ID["bwv856"][1]["fugue"]["entries"]}
    v856 = load_voices(MARKINGS_BY_ID["bwv856"][1], MARKINGS)
    first = [next(x.p for x in v856[e856[s]["voice"]] if x.s == s) for s in (108, 114, 120)]
    assert [a - b for a, b in zip(first, first[1:])] == [12, 12]
    e857 = MARKINGS_BY_ID["bwv857"][1]["fugue"]["entries"]
    assert any((e["voice"], e["start"], e["form"]) == (2, 13.0, "countersubject") for e in e857)


def test_no_sounding_note_is_dropped(built):
    """Chord tones and split-off lines are secondary notes: BWV 846 ends with the alto's E5
    (the final chord's third), the closing splits of BWV 848, 851, 852, 860, 861 and 869 keep
    their second line (BWV 863 and 864 split only for sic/ossia readings); secondary notes
    are never inside an entry's notes (find_entry skips them)."""
    def secondary(pid):
        return [(n["v"], n["s"], n["p"]) for n in piece(built, pid)["notes"] if n.get("c")]
    end846 = max(n["s"] for n in piece(built, "bwv846")["notes"])
    assert (1, end846, 76) in secondary("bwv846")
    assert len([x for x in secondary("bwv848") if x[1] >= 54 * 4]) == 8  # E#4 sounds once
    assert len([x for x in secondary("bwv851") if x[1] >= 42 * 3]) >= 12
    assert [(x[1], x[2]) for x in secondary("bwv852") if x[1] >= 36 * 4] == [
        (144.25, 61), (145.0, 60), (145.75, 59), (146.0, 58)]
    assert len([x for x in secondary("bwv860") if x[1] >= 83 * 6]) == 7  # bars 84-85, eighths
    assert [x[0] for x in secondary("bwv861") if x[1] >= 32 * 4] == [1] * 6  # alto, bars 33-34
    assert len([x for x in secondary("bwv869") if x[0] == 3 and x[1] >= 74 * 4]) == 10
    assert secondary("bwv863") == [] and secondary("bwv864") == []
    for pid in PIECES["wtc"] + RICERCARS:
        m = MARKINGS_BY_ID[pid][1]
        voices = load_voices(m, MARKINGS, secondary=True)
        for e in m["fugue"]["entries"]:
            if e["form"] == "countersubject":
                continue
            idx = find_entry(voices, entry_reference(voices, m["fugue"], e), e["voice"],
                             e["start"], e["transform"],
                     head=e["head"], tail=e["tail"], head_length=e["head_length"], octave=e.get("octave", ()))
            assert not any(voices[e["voice"]][i].c for i in idx), (pid, e)


def test_wtc_fugues_3_6_7_from_the_scores(built):
    """BWV 848 brings its exposition back in bars 42-46 (soprano, alto, bass at the first
    entries' pitches); BWV 851 inverts its subject and has five strettos (bars 13, 17, 21,
    27, 39), the inversion first in bar 14; BWV 852's answer is tonal (a step for a third)."""
    e848 = MARKINGS_BY_ID["bwv848"][1]["fugue"]["entries"]
    v848 = load_voices(MARKINGS_BY_ID["bwv848"][1], MARKINGS)
    def first(v, s, voices):
        return next(x.p for x in voices[v] if x.s == s)
    assert [first(v, s, v848) for v, s in ((0, 1.5), (1, 9.5), (2, 17.5))] == \
        [first(v, s, v848) for v, s in ((0, 165.5), (1, 173.5), (2, 181.5))]
    assert {(e["voice"], e["start"]) for e in e848} >= {(0, 165.5), (1, 173.5), (2, 181.5)}
    p851 = piece(built, "bwv851")
    st = [math.floor(k["start"] / 3) + 1 for k in p851["marks"] if k["kind"] == "stretto"]
    assert st == [13, 17, 21, 27, 39]
    inv = [e["start"] for e in MARKINGS_BY_ID["bwv851"][1]["fugue"]["entries"]
           if e["transform"] == "inverted"]
    assert math.floor(min(inv) / 3) + 1 == 14


def test_wtc_free_heads_and_tails_from_the_scores(built):
    """Statements whose first note is held over or whose last note turns elsewhere are
    marked with head/tail: free: BWV 846's bass in bar 17 (the fourth voice of the bar-16
    stretto), BWV 852's four openings tied over the barline (bars 10-11, 25-26, 28-29,
    33-34), placed on the downbeat with marks from the tied note; BWV 851's subject
    ends on the A of bar 3 and five statements turn it elsewhere; in BWV 853 only the
    bar-3 statement has the answer's third (the soprano's inversion in bar 64 apart: it
    inverts the answer)."""
    def entries(pid):
        return MARKINGS_BY_ID[pid][1]["fugue"]["entries"]
    bass17 = next(e for e in entries("bwv846") if e["start"] == 66)
    assert (bass17["voice"], bass17["head"], bass17["stretto"]) == (3, "free", "s4")
    heads = [math.floor(e["start"] / 4) + 1 for e in entries("bwv852") if e["head"] == "free"]
    assert heads == [11, 26, 29, 34] and len(entries("bwv852")) == 9
    # each statement is in its place (a downbeat); its mark begins with the tied-over note
    starts = {k["start"] for k in piece(built, "bwv852")["marks"] if k["kind"] == "entry"}
    assert {39.5, 99.5, 111, 131.5} <= starts and not {40, 100, 112, 132} & starts
    assert sum(e["tail"] == "free" for e in entries("bwv851")) == 5
    assert [e["start"] for e in entries("bwv853")
            if e["form"] == "answer" and e["transform"] == "none"] == [10]
    # the soprano in bar 64 inverts the answer (its third), matched against it
    inv_answer = [(e["start"], e["ref"]) for e in entries("bwv853")
                  if e["form"] == "answer" and e["transform"] == "inverted"]
    assert inv_answer == [(254, "answer")]
    p846 = piece(built, "bwv846")
    s4 = [k for k in p846["marks"] if k["kind"] == "stretto" and k["label"] == "s4"]
    assert len(s4) == 1 and s4[0]["start"] == 61.5


def test_wtc_fugues_13_to_24_from_the_scores(built):
    """What the markings of fugues 13-24 claim, read from the scores. BWV 858: the
    countersubject against the answer (bar 3) and the bass's subject (bar 5). BWV 859 and 860
    turn the subject upside down (859: alto bar 20, bass 32; 860: from bar 20). BWV 861:
    strettos in bars 17 and 28. BWV 862: a one-bar subject; from bar 27 the voices enter a
    bar apart. BWV 863: a regular countersubject. BWV 864: one subject (not a double
    fugue); the answer enters in bar 2 while the subject still runs. BWV 866: the
    subject ends with two bars of sixteenths, kept in every statement. BWV 867: a 10-note
    subject (to the F of bar 4), many statements of its head alone, and the five-voice
    stretto of bars 67-69, a half note apart. BWV 868: the inversion in bars 18 and 20, in
    stretto with the bass. BWV 869: the subject uses all twelve pitch classes."""
    def entries(pid, form=None, transform=None):
        es = MARKINGS_BY_ID[pid][1]["fugue"]["entries"]
        return [e for e in es if (form is None or e["form"] == form)
                and (transform is None or e["transform"] == transform)]
    def bar(pid, beat):
        p = piece(built, pid)
        return math.floor((beat - p["pickup"]) / p["beatsPerBar"]) + 1
    def stretto_bars(pid):
        return [bar(pid, k["start"]) for k in piece(built, pid)["marks"] if k["kind"] == "stretto"]
    def notes(pid, e):
        m = MARKINGS_BY_ID[pid][1]
        voices = load_voices(m, MARKINGS)
        return _entry_notes(m, voices, e)
    assert [(e["voice"], bar("bwv858", e["start"])) for e in entries("bwv858", "countersubject")] \
        == [(0, 3), (1, 5)]
    assert [(e["voice"], bar("bwv859", e["start"])) for e in entries("bwv859", None, "inverted")] \
        == [(1, 20), (3, 32)]
    inv860 = [bar("bwv860", e["start"]) for e in entries("bwv860", None, "inverted")]
    assert inv860 == [20, 24, 28, 43, 69]
    assert stretto_bars("bwv861") == [17, 28]
    assert MARKINGS_BY_ID["bwv862"][1]["fugue"]["subject"]["length"] <= 4  # one bar
    late862 = sorted((e["start"], e["voice"]) for e in entries("bwv862") if 104 <= e["start"] < 120)
    assert late862 == [(105, 3), (109, 2), (113, 1), (117, 0)]
    assert len(entries("bwv863", "countersubject")) == 5
    m864 = MARKINGS_BY_ID["bwv864"][1]["fugue"]
    assert m864["countersubject"] is None and stretto_bars("bwv864") == [1]
    subj864 = notes("bwv864", m864["entries"][0])
    assert next(e for e in m864["entries"] if e["form"] == "answer")["start"] < subj864[-1].s
    for e in entries("bwv866", "subject") + entries("bwv866", "answer"):
        ns = notes("bwv866", e)
        assert len(ns) == 38 and [x.d for x in ns[-23:-1]] == [0.25] * 22
    s867 = sorted((e["start"], e["voice"]) for e in entries("bwv867") if e.get("stretto") == "s5")
    assert s867 == [(133, 0), (134, 1), (135, 2), (136, 3), (137, 4)]  # half-note beats
    assert stretto_bars("bwv867") == [1, 25, 50, 53, 67]
    # the subject arches to the dominant F on bar 4's downbeat; statements that keep only
    # its opening are heads, labelled so on the roll
    m867 = MARKINGS_BY_ID["bwv867"][1]["fugue"]
    subj867 = subject_notes(load_voices(MARKINGS_BY_ID["bwv867"][1], MARKINGS), m867["subject"])
    assert (subj867[-1].p, subj867[-1].s) == (77, 6.0)
    whole = [bar("bwv867", e["start"]) for e in m867["entries"] if e["part"] == "whole"]
    assert whole == [1, 3, 25, 53, 55, 55, 67, 69]
    labels = [k["label"] for k in piece(built, "bwv867")["marks"] if k["kind"] == "entry"]
    assert labels.count("subject (head)") + labels.count("answer (head)") == 12
    # the alto in bar 68 compresses its ending (Db Eb in sixteenths, F early): only its first
    # eight notes stand where the subject puts them, so only they are marked
    alto68 = next(e for e in m867["entries"] if (e["voice"], e["start"]) == (2, 135))
    assert (alto68["part"], alto68["head_length"], alto68["tail"]) == ("head", 8, "fixed")
    got = notes("bwv867", alto68)
    assert [x.s - 135 for x in got] == [x.s for x in subj867[:8]]  # no note mis-paired
    assert (got[-1].p, got[-1].s) == (61, 140.0)  # the Db, where the subject has it
    assert [bar("bwv868", e["start"]) for e in entries("bwv868", None, "inverted")] == [18, 20]
    assert stretto_bars("bwv868") == [20]
    # the bass in bar 47 states the answer on D (ref: answer: D C♯, the answer's step)
    bass47 = next(e for e in entries("bwv869") if (e["voice"], e["start"]) == (3, 186.5))
    assert (bass47["form"], bass47["ref"]) == ("answer", "answer")
    assert [x.p for x in notes("bwv869", bass47)[:4]] == [50, 49, 45, 54]
    subj869 = subject_notes(load_voices(MARKINGS_BY_ID["bwv869"][1], MARKINGS),
                            MARKINGS_BY_ID["bwv869"][1]["fugue"]["subject"])
    assert len({x.p % 12 for x in subj869}) == 12


def test_bwv865_reads_its_commented_ending(built):
    """BWV 865 (fugue 20): the kern file adds a fifth spine at bar 80 and comments out every
    line from there to the end (bars 80-87). Read again (source.commented_from), the added
    spine is a fifth voice, silent before bar 80: 205 notes sound from bar 80 (the file's
    206 note onsets, less the tenor's unison E in the last chord), 12 of them secondary
    chord tones; the fifth voice states the subject on D from bar 84; the bass
    holds its A from bar 83 to the end (the tie carried into the last bar, under the new A
    above it); the last bars agree with the Bach-Gesellschaft plate (p. 73)."""
    from fugue_prep.kern import read_kern
    path = SOURCES / "bach-wtc-fugues/kern/wtc1f20.krn"
    lines = path.read_text().splitlines()
    assert sum(ln.startswith("!!=8") for ln in lines) == 7  # bars 81-87, commented out
    plain = read_kern(path, alternatives=[69])
    assert len(plain) == 5 and len(plain[0]) == 0  # unread: an empty fifth part, bars dropped
    voices = read_kern(path, alternatives=[69], commented_from=80)
    assert len(voices) == 5 and min(x.s for x in voices[0]) == 79 * 4
    p = piece(built, "bwv865")
    late = [n for n in p["notes"] if n["s"] >= 79 * 4]
    assert len(late) == 205 and sum(bool(n.get("c")) for n in late) == 12
    # chord tones: soprano bars 80 and 87, alto bar 82, tenor bar 87, the bass's octave A
    assert {n["v"] for n in late if n.get("c")} == {1, 2, 3, 4}
    assert sum(n["v"] == 0 for n in late) == 53 and not any(n["v"] == 0 for n in p["notes"]
                                                             if n["s"] < 79 * 4)
    fifth = next(e for e in MARKINGS_BY_ID["bwv865"][1]["fugue"]["entries"] if e["voice"] == 0)
    assert (fifth["start"], fifth["part"], fifth["stretto"]) == (334.5, "whole", "s12")
    pedal = [n for n in p["notes"] if n["v"] == 4 and not n.get("c") and n["s"] == 82 * 4 + 2]
    assert [(n["p"], n["d"]) for n in pedal] == [(45, 18)]  # A2 to the end of bar 87
    # the plate, bar by bar: the five voices' notes (pitch, onset in the bar) in bar 87
    end = {(n["p"], n["s"] - 86 * 4) for n in p["notes"] if n["s"] >= 86 * 4}
    assert end >= {(81, 0), (57, 0), (69, 2), (73, 2), (64, 2), (65, 0), (68, 1.75)}
    assert max(n["s"] + n["d"] for n in p["notes"]) == 87 * 4


def test_wtc_fugues_4_and_20_from_the_scores(built):
    """BWV 849 is a triple fugue: subject I (C# B# E D#, whole and half notes) from bar 1,
    subject II (running eighths) from bar 36, subject III (C#, F# three times, E# D# E#)
    from bar 49, where all three sound at once; subject I comes in stretto in bars 94-97.
    BWV 865 states its subject upright and inverted, in twelve strettos two beats apart."""
    m = MARKINGS_BY_ID["bwv849"][1]
    f = m["fugue"]
    assert list(f["subjects"]) == ["I", "II", "III"]
    voices = load_voices(m, MARKINGS)
    pcs = {k: [x.p % 12 for x in subject_notes(voices, sp)] for k, sp in f["subjects"].items()}
    assert pcs["I"] == [1, 0, 4, 3]
    assert pcs["II"] == [8, 6, 8, 9, 8, 6, 4, 8, 6, 4, 6, 8, 6, 4, 3, 6]
    assert pcs["III"] == [1, 6, 6, 6, 5, 3, 5]
    first = {k: min(e["start"] for e in f["entries"] if e.get("subject") == k) for k in pcs}
    assert {k: math.floor(b / 2) + 1 for k, b in first.items()} == {"I": 1, "II": 36, "III": 49}
    # at the alto's first subject III, I and II sound above it
    sounding = {e["subject"] for e in f["entries"]
                if e["start"] <= 96.5 < e["start"] + f["subjects"][e["subject"]]["length"]}
    assert sounding == {"I", "II", "III"}
    counts = {k: sum(e.get("subject") == k for e in f["entries"]) for k in pcs}
    assert counts == {"I": 24, "II": 13, "III": 32}
    p = piece(built, "bwv849")
    labels = {k["label"] for k in p["marks"] if k["kind"] == "entry"}
    assert labels == {"subject I", "answer I", "subject II", "answer II", "subject II inverted",
                      "subject III", "answer III"}
    st = [(math.floor(k["start"] / 2) + 1, k["label"]) for k in p["marks"] if k["kind"] == "stretto"]
    assert st == [(94, "s1"), (107, "s2")]
    # strettos follow the rule, within one subject: a statement that begins at least a
    # beat before the previous statement of its subject ends its last note
    for sid in pcs:
        es = sorted((e for e in f["entries"] if e.get("subject") == sid), key=lambda e: e["start"])
        for a, b in zip(es, es[1:]):
            last = _entry_notes(m, voices, a)[-1].s
            assert (b["start"] <= last - 1) == (b["stretto"] is not None and
                                                b["stretto"] == a["stretto"]), (sid, b)
    # most statements of subject I open with a half note (head: short)
    short = [e for e in f["entries"] if e["head"] == "short"]
    assert len(short) == 11 and all(_entry_notes(m, voices, e)[1].s == e["start"] + 1
                                    for e in short)
    e865 = MARKINGS_BY_ID["bwv865"][1]["fugue"]["entries"]
    assert sum(e["transform"] == "inverted" and e["part"] == "whole" for e in e865) == 15
    assert len([k for k in piece(built, "bwv865")["marks"] if k["kind"] == "stretto"]) == 12


# Caption claims, checked against the notes: per caption (beat), the voice it names, the
# subject and form of the statement there, and the pitch class it starts on (None: not named).
CAPTION_FACTS = {
    "bwv849": {0: (4, "I", "subject", 1), 6: (3, "I", "answer", 8), 13: (2, "I", "subject", None),
               27: (0, "I", "subject", None), 70: (0, "II", "subject", None),
               80: (3, "II", "subject", None), 96.5: (2, "III", "subject", None),
               118.5: (3, "III", "answer", 8), 186: (0, "I", "subject", None),
               212.5: (1, "III", "subject", None), 223: (1, "I", "subject", 6)},
    "bwv865": {0.5: (2, None, "subject", 9), 12.5: (1, None, "answer", 4),
               28.5: (4, None, "subject", 9), 40.5: (3, None, "answer", 4),
               54.5: (1, None, "subject", 4), 106.5: (1, None, "subject", 9),
               168.5: (1, None, "subject", 0), 318.5: (1, None, "subject", 9),
               330.5: (3, None, "subject", None), 334.5: (0, None, "subject", 2)},
}
VOICE_WORDS = {"bwv849": ["soprano I", "soprano II", "alto", "tenor", "bass"],
               "bwv865": ["fifth voice", "soprano", "alto", "tenor", "bass"]}
PC_WORDS = {1: "C♯", 8: "G♯", 6: "F♯", 9: "A", 4: "E", 0: "C", 2: "D"}


@pytest.mark.parametrize("pid", ["bwv849", "bwv865"])
def test_wtc_4_and_20_captions_say_what_the_notes_do(built, pid):
    m = MARKINGS_BY_ID[pid][1]
    p = piece(built, pid)
    voices = load_voices(m, MARKINGS)
    es = m["fugue"]["entries"]
    facts = CAPTION_FACTS[pid]
    assert sorted(c["at"] for c in p["captions"]) == sorted(facts)
    for c in p["captions"]:
        text = c["text"]
        v, sid, form, pc = facts[c["at"]]
        e = next(x for x in es if x["start"] == c["at"] and x["voice"] == v)
        assert (e.get("subject"), e["form"]) == (sid, form), text
        assert VOICE_WORDS[pid][v] in text.replace("Soprano", "soprano").replace("The", "the"), text
        if sid:
            assert f"ubject {sid}" in text or "answers subject" in text, text
        assert ("answer" in text) == (form == "answer"), text
        ns = _entry_notes(m, voices, e)
        if pc is not None:
            assert ns[0].p % 12 == pc and f"on {PC_WORDS[pc]}" in text or \
                f"from {PC_WORDS[pc]}" in text or f"bass: {PC_WORDS[pc]}" in text, text
        if "down to B♯, up to E, down to D♯" in text:
            assert [x.p % 12 for x in ns] == [1, 0, 4, 3]
        if "upside down" in text or "inverts" in text:
            assert e["transform"] == "inverted", text
        if "first note now a half note" in text:
            assert e["head"] == "short" and ns[0].d == 1, text
        if "enters last" in text or "answers last" in text:
            others = [min(x.s for x in vs) for u, vs in enumerate(voices) if u != v]
            n = {"all four voices": 4, "all five voices": 5}[next(
                k for k in ("all four voices", "all five voices") if k in text)]
            # the voice's first note, after n - 1 others (BWV 865's fifth comes in bar 80)
            assert min(x.s for x in voices[v]) == e["start"], text
            assert sum(f < e["start"] for f in others) == n - 1, text
        if "a step lower" in text:  # bar 2 of subject II is bar 1 a diatonic step down
            assert all(1 <= a.p - b.p <= 2 for a, b in zip(ns[:8], ns[8:])), text
        if "all three at once" in text:
            on = {x.get("subject") for x in es if x["start"] <= e["start"] and
                  _entry_notes(m, voices, x)[-1].s >= e["start"]}
            assert on == {"I", "II", "III"}, text
        if "together, a third apart" in text:
            mate = next(x for x in es if x["start"] == e["start"] and x["voice"] != v)
            assert abs(_entry_notes(m, voices, mate)[0].p - ns[0].p) in (3, 4), text
        if "Stretto" in text:
            assert e["stretto"] is not None, text
            group = sorted((x for x in es if x["stretto"] == e["stretto"]), key=lambda x: x["start"])
            names = [VOICE_WORDS[pid][x["voice"]] for x in group]
            assert ", ".join(names[:-1]) + ", then the " + names[-1] in text or \
                "then the " + names[-1] in text, (text, names)
            if "two beats later" in text:
                assert group[1]["start"] - group[0]["start"] == 2, text
        if "a last time" in text:
            assert e is max((x for x in es if x.get("subject") == sid), key=lambda x: x["start"])
        if "grows to five voices" in text:  # the added line enters in this bar
            added = min(n["s"] for n in p["notes"] if n["v"] == 0)
            assert math.floor(added / 4) == math.floor(e["start"] / 4), text
        if "held A" in text:
            assert any(n["v"] == 4 and n["p"] % 12 == 9 and n["s"] < e["start"]
                       and n["s"] + n["d"] >= e["start"] + 6 for n in p["notes"]), text


# --- The Musical Offering: the two ricercars on the royal theme (BWV 1079/1 and /5) ---

RICERCARS = ["bwv1079-ricercar-a3", "bwv1079-ricercar-a6"]
# Per ricercar: (beats per bar, kern file, the voice of the first statement, its pitches).
# A beat is a half note (both are alla breve: the a 3 in ¢, four quarters a bar; the a 6
# two whole notes a bar). The subject is the royal theme to its close on the tonic C, as
# the score's first statement gives it (IMSLP10042 p. 3, bars 1-9; p. 12, bars 1-5):
# c e♭ g a♭ b, g f♯ f e e♭ d d♭ c b (a) g c f e♭ d c. The a 6 omits the a.
RICERCAR_FACTS = {
    "bwv1079-ricercar-a3": (2, "bach-musical-offering/kern/offering-001.krn", 0,
                            [72, 75, 79, 80, 71, 79, 78, 77, 76, 75, 74, 73, 72, 71, 69, 67,
                             72, 77, 75, 74, 72]),
    "bwv1079-ricercar-a6": (4, "bach-musical-offering/kern/offering-002.krn", 2,
                            [60, 63, 67, 68, 59, 67, 66, 65, 64, 63, 62, 61, 60, 59, 55, 60,
                             65, 63, 62, 60]),
}
# Every statement of the theme, (voice, bar, form), checked against the score: the a 3's
# ten, the a 6's twelve (its first soprano in bar 66 the answer's shape on E♭ with a
# major third, ref: answer; its bass in bar 99 only to the F, where it turns into the
# final cadence; its second soprano in bar 86 the answer with B♮ for B♭, G B C E♭ F♯,
# matched against the first answer: ref: answer).
RICERCAR_ENTRIES = {
    "bwv1079-ricercar-a3": [(0, 1, "subject"), (1, 10, "answer"), (2, 23, "subject"),
                            (2, 46, "subject"), (1, 59, "subject"), (0, 72, "subject"),
                            (2, 95, "subject"), (0, 141, "subject"), (1, 153, "answer"),
                            (2, 169, "subject")],
    "bwv1079-ricercar-a6": [(2, 1, "subject"), (1, 5, "answer"), (4, 9, "subject"),
                            (3, 13, "answer"), (0, 19, "subject"), (5, 25, "answer"),
                            (4, 48, "answer"), (2, 58, "subject"), (0, 66, "answer"),
                            (3, 73, "subject"), (1, 86, "answer"), (5, 99, "subject")],
}


def _bar(m, beat):
    return math.floor((beat - m.get("pickup", 0)) / m["beats_per_bar"]) + 1


@pytest.mark.parametrize("pid", RICERCARS)
def test_ricercar_subject_is_the_royal_theme(built, pid):
    bpb, path, voice, pitches = RICERCAR_FACTS[pid]
    m = MARKINGS_BY_ID[pid][1]
    p = piece(built, pid)
    assert m["source"] == {"kind": "kern", "path": path, "beats_per_quarter": 0.5}
    assert (p["beatsPerBar"], p["beatUnit"], p["pickup"]) == (bpb, 2, 0)
    spec = m["fugue"]["subject"]
    assert (spec["voice"], spec["start"]) == (voice, 0)
    voices = load_voices(m, MARKINGS)
    subj = subject_notes(voices, spec)
    assert [x.p for x in subj] == pitches
    # the theme alone until the answer, which enters as it closes on the tonic
    answer = next(e for e in m["fugue"]["entries"] if e["form"] == "answer")
    assert all(x.s >= answer["start"] for v, ns in enumerate(voices) if v != voice for x in ns)
    assert subj[-1].s <= answer["start"] <= subj[-1].s + 2


@pytest.mark.parametrize("pid", RICERCARS)
def test_ricercar_statements_from_the_scores(built, pid):
    m = MARKINGS_BY_ID[pid][1]
    es = m["fugue"]["entries"]
    assert [(e["voice"], _bar(m, e["start"]), e["form"]) for e in es] == RICERCAR_ENTRIES[pid]
    assert all(e["start"] == (_bar(m, e["start"]) - 1) * m["beats_per_bar"] for e in es)
    assert m["fugue"]["countersubject"] is None
    assert all(e["transform"] == "none" and e["stretto"] is None for e in es)
    assert not [k for k in piece(built, pid)["marks"] if k["kind"] == "stretto"]
    heads = [(_bar(m, e["start"]), e["head_length"], e["tail"]) for e in es if e["part"] == "head"]
    assert heads == ([(99, 17, "free")] if pid.endswith("a6") else [])


def test_ricercar_a6_bar_86_is_the_answer_with_b_natural(built):
    """The second soprano in bar 86 states the answer with B♮ (IMSLP10042 p. 18): G B♮ C E♭
    F♯; its second interval is a semitone where the subject's is a major third (3 off), so
    it is matched against the first answer (bar 5, G B♭ C E♭ F♯: 1 off), ref: answer."""
    from fugue_prep.fugue import EntryMismatch
    m = MARKINGS_BY_ID["bwv1079-ricercar-a6"][1]
    voices = load_voices(m, MARKINGS)
    start = (86 - 1) * 4
    assert [x.p for x in voices[1] if start <= x.s < start + 5] == [67, 71, 72, 75, 66]
    e = next(e for e in m["fugue"]["entries"] if e["start"] == start)
    assert (e["voice"], e["form"], e["ref"]) == (1, "answer", "answer")
    with pytest.raises(EntryMismatch):
        find_entry(voices, subject_notes(voices, m["fugue"]["subject"]), 1, start)
    assert len(_entry_notes(m, voices, e)) == 20
    assert any(k["kind"] == "entry" and k["voice"] == 1 and k["start"] == start
               for k in piece(built, "bwv1079-ricercar-a6")["marks"])


@pytest.mark.parametrize("pid", RICERCARS)
def test_ricercar_forms_follow_the_notes(pid):
    _forms_follow_the_notes(pid)


def test_ricercar_voices_and_instruments(built):
    """Keyboard music: the a 3 is Bach's keyboard ricercar; the a 6, printed in open score,
    is for keyboard too, and its bass goes down to B♭1, below the cello's and the organ's
    C2. Six voices take six textures."""
    for pid, n in (("bwv1079-ricercar-a3", 3), ("bwv1079-ricercar-a6", 6)):
        p = piece(built, pid)
        assert [v["instrument"] for v in p["voices"]] == ["harpsichord"] * n
        assert len({v["texture"] for v in p["voices"]}) == n
    bass = [n["p"] for n in piece(built, "bwv1079-ricercar-a6")["notes"] if n["v"] == 5]
    assert min(bass) == 34


# Caption claims, checked against the notes (test_ricercar_captions_say_what_the_notes_do):
# per caption, the voice it names and the note the statement starts on.
RICERCAR_VOICE_WORDS = {
    "bwv1079-ricercar-a3": ["soprano", "alto", "bass"],
    "bwv1079-ricercar-a6": ["first soprano", "second soprano", "alto", "first tenor",
                            "second tenor", "bass"],
}
PITCH_WORDS = {0: "C", 7: "G", 5: "F", 10: "B♭", 3: "E♭"}
ORDINALS = {"Third voice": 3, "Fourth voice": 4, "Fifth voice": 5, "Sixth voice": 6}


@pytest.mark.parametrize("pid", RICERCARS)
def test_ricercar_captions_say_what_the_notes_do(built, pid):
    m = MARKINGS_BY_ID[pid][1]
    p = piece(built, pid)
    voices = load_voices(m, MARKINGS)
    es = sorted(m["fugue"]["entries"], key=lambda e: e["start"])
    marks = {(k["voice"], k["start"]): k for k in p["marks"] if k["kind"] == "entry"}
    words = RICERCAR_VOICE_WORDS[pid]
    entered = sorted(range(len(voices)), key=lambda v: voices[v][0].s)
    subj = subject_notes(voices, m["fugue"]["subject"])
    bpb = m["beats_per_bar"]
    gaps = {}
    for a, b in zip(es, es[1:]):
        gaps[b["start"]] = b["start"] - marks[(a["voice"], a["start"])]["end"]
    for c in p["captions"]:
        e = next(x for x in es if x["start"] == c["at"])
        text, v = c["text"], e["voice"]
        ns = _entry_notes(m, voices, e)
        # the voice, named once ("in the <voice>")
        named = [w for w in words if f"in the {w}" in text]
        assert words[v] in named and len(named) == 1, (pid, text)
        assert f"on {PITCH_WORDS[ns[0].p % 12]}" in text, (pid, text)
        assert ("answer" in text) == (e["form"] == "answer"), (pid, text)
        if "alone" in text:
            assert all(x.s >= es[1]["start"] for u, xs in enumerate(voices) if u != v
                       for x in xs), text
        if "G is answered by C" in text:
            assert (subj[2].p % 12, ns[2].p % 12) == (7, 0), text
        for word, k in ORDINALS.items():
            if word in text:
                assert entered.index(v) + 1 == k and voices[v][0].s == e["start"], text
        if "octave below the alto" in text or "octave above the alto" in text:
            alto = ns[0].p - subj[0].p
            assert alto == (-12 if "below" in text else 12), text
        if " minor" in text:
            key = text.split(", in ")[1].split(" minor")[0]
            assert PITCH_WORDS[ns[0].p % 12] == key, text
            assert [ns[1].p - ns[0].p, ns[2].p - ns[1].p] == [3, 4], text  # a minor triad
        if "after a long episode" in text:
            assert gaps[e["start"]] >= 8 * bpb, (text, gaps[e["start"]] / bpb)
        if "longest episode" in text:
            assert gaps[e["start"]] == max(gaps.values()), text
        if "exposition is complete" in text:
            assert len({x["voice"] for x in es if x["start"] <= e["start"]}) == len(voices)
        if "third now major" in text:  # the first answer's is minor
            fa = _entry_notes(m, voices, first_answer(m["fugue"]))
            assert (ns[1].p - ns[0].p, fa[1].p - fa[0].p) == (4, 3), text
        if "with B♮ for B♭" in text:  # note 2: B♮ where the first answer has B♭
            fa = _entry_notes(m, voices, first_answer(m["fugue"]))
            assert (ns[1].p % 12, fa[1].p % 12) == (11, 10), text
        if "last entry" in text:
            assert e is es[-1], text
        if "breaks off into the cadence" in text:
            assert e["part"] == "head" and max(x.s for x in voices[v]) - ns[-1].s <= 2 * bpb


def test_grace_notes_play_as_secondary_notes(built):
    """Grace notes sound (secondary, never matched): the Ricercar a 3's two appoggiaturas
    before the last chord (half-note beats: 1/16 of a quarter is 1/32 of a beat) and
    Sinfonia 5's 66 ornaments."""
    g = 0.0625 / 2
    sec = [(n["v"], n["p"], n["s"], n["d"]) for n in piece(built, "bwv1079-ricercar-a3")["notes"]
           if n.get("c")]
    assert sec == [(0, 71, 368 - g, g), (1, 65, 368 - g, g)]
    s5 = [n for n in piece(built, "sinfonia05")["notes"] if n.get("c")]
    assert len(s5) == 66 and {n["d"] for n in s5} == {0.0625}
