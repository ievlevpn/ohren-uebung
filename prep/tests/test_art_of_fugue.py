"""The Art of Fugue (BWV 1080): the pieces from craigsapp/art-of-the-fugue teach true.

Every claim the markings and captions make about the notes is checked here: which kern
file holds which piece (its !!!OTL record), the forms of the statements, the mirror
fugues' inversus against the rectus, the canons' rules, the captions' words, and the
unfinished ending of Contrapunctus XIV. Builds the real markings once (like test_pieces).
"""
import json
import math
import re
from pathlib import Path

import pytest

from fugue_prep.build import MARKINGS, SOURCES, build_all, load_voices
from fugue_prep.canon import Rule, match
from fugue_prep.fugue import STRETCH, entry_reference, find_entry, subject_notes, subject_spec
from tests.test_pieces import MARKINGS_BY_ID, PIECES, opening_form, wtc_form

AOF = PIECES["art-of-fugue"]
KERN = [p for p in AOF if p not in ("contrapunctus01", "contrapunctus06")]  # 1, 6: Mutopia

# kern file -> (piece, words its !!!OTL / !!!OTL2 record must contain)
FILES = {
    "artfugue-002.krn": ("contrapunctus02", "Contrapunctus 2"),
    "artfugue-003.krn": ("contrapunctus03", "Contrapunctus 3"),
    "artfugue-004.krn": ("contrapunctus04", "Contrapunctus 4"),
    "artfugue-005.krn": ("contrapunctus05", "Contrapunctus 5"),
    "artfugue-007.krn": ("contrapunctus07", "Contrapunctus 7"),
    "artfugue-008.krn": ("contrapunctus08", "Contrapunctus 8"),
    "artfugue-009.krn": ("contrapunctus09", "Contrapunctus 9"),
    "artfugue-010.krn": ("contrapunctus10", "Contrapunctus 10"),
    "artfugue-011.krn": ("contrapunctus11", "Contrapunctus 11"),
    "artfugue-018a.krn": ("contrapunctus12-rectus", "(XII), a 4. (rectus)"),
    "artfugue-018b.krn": ("contrapunctus12-inversus", "(XII), a 4. (inversus)"),
    "artfugue-016a.krn": ("contrapunctus13-rectus", "(XIII), a 3. (rectus)"),
    "artfugue-016b.krn": ("contrapunctus13-inversus", "(XIII), a 3. (inversus)"),
    "artfugue-015.krn": ("canon-per-augmentationem", "Canon in Augmentation in Inversion"),
    "artfugue-012.krn": ("canon-alla-ottava", "Canon alla Ottava"),
    "artfugue-014.krn": ("canon-alla-decima", "Canon alla Decima"),
    "artfugue-013.krn": ("canon-alla-duodecima", "Canon alla Duodecima"),
    "artfugue-019.krn": ("contrapunctus14", "B-A-C-H"),
}
CANONS = ["canon-per-augmentationem", "canon-alla-ottava", "canon-alla-decima",
          "canon-alla-duodecima"]
FUGUES = [p for p in KERN if p not in CANONS]
VOICE_WORDS = ("soprano", "alto", "tenor", "bass")
PITCH = {"C": 0, "C♯": 1, "D": 2, "E♭": 3, "E": 4, "F": 5, "F♯": 6, "G": 7, "A♭": 8,
         "A": 9, "B♭": 10, "B": 11}


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("data")
    build_all(out)
    return out


def piece(built: Path, pid: str) -> dict:
    return json.loads((built / "pieces" / f"{pid}.json").read_text())


def m_of(pid):
    return MARKINGS_BY_ID[pid][1]


def records(path: Path) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("!!!") and ":" in line:
            k, v = line[3:].split(":", 1)
            out.setdefault(k.strip(), []).append(v.strip())
    return out


# ---- the source ----

def test_each_piece_reads_the_file_its_reference_records_name():
    """The file numbers do not follow Bach's: 012 is the Canon alla Ottava, 016a/b the
    three-voice mirror fugue (Contrapunctus XIII), 018a/b the four-voice one (XII), 019
    Contrapunctus XIV. Each piece reads the file whose title record names it."""
    assert sorted(p for p, _ in FILES.values()) == sorted(KERN)
    for name, (pid, words) in FILES.items():
        assert m_of(pid)["source"]["path"] == f"art-of-the-fugue/kern/{name}"
        rec = records(SOURCES / "art-of-the-fugue" / "kern" / name)
        titles = " ".join(rec.get("OTL", []) + rec.get("OTL1", []) + rec.get("OTL2", []))
        assert words in titles, (name, titles)


def test_no_file_claims_copyright_or_a_licence():
    """SOURCES.md says the files carry no copyright or licence records (!!!YEC, !!!YEM,
    !!!YER, !!!EED-licence...): if that changes, SOURCES.md must say so."""
    for name in FILES:
        rec = records(SOURCES / "art-of-the-fugue" / "kern" / name)
        assert not [k for k in rec if k.startswith("YE")], name


def kern_pickup(path: Path) -> float:
    """Quarter notes before the file's first barline (an upbeat): the longest spine's sum
    of the durations on the data lines above ``=1``."""
    lines = path.read_text(encoding="utf-8").splitlines()
    total: dict[int, float] = {}
    for line in lines:
        if line.startswith("="):
            break
        if not line or line[0] in "!*":
            continue
        for k, tok in enumerate(line.split("\t")):
            mo = re.match(r"^[\[({&]*(\d+)(\.*)", tok.split(" ")[0])
            if mo and "q" not in tok:
                d = 4 / int(mo.group(1))
                total[k] = total.get(k, 0) + d * (2 - 0.5 ** len(mo.group(2)))
    return max(total.values(), default=0)


@pytest.mark.parametrize("pid", KERN)
def test_the_pickup_is_the_kerns_upbeat(pid):
    """Bar lines follow the file: an upbeat before =1 (Contrapunctus XIII, a quarter)
    is the markings' pickup, in beats."""
    m = m_of(pid)
    src = m["source"]
    beats = kern_pickup(SOURCES / src["path"]) * src.get("beats_per_quarter", 1) / src.get(
        "beat_unit", 1)
    assert m.get("pickup", 0) == pytest.approx(beats), (pid, beats)


def test_the_collection_follows_bachs_numbering():
    assert [m_of(p)["catalogue"] for p in AOF] == (
        [f"BWV 1080, {n}" for n in range(1, 12)] + ["BWV 1080, 12"] * 2 + ["BWV 1080, 13"] * 2
        + [f"BWV 1080, {n}" for n in (14, 15, 16, 17, 19)])


def test_no_sounding_note_is_dropped(built):
    """Splits, chord tones and grace notes are secondary notes, never dropped (no
    sic/ossia readings in these files)."""
    want = {"contrapunctus05": 12, "contrapunctus07": 41, "contrapunctus08": 2,
            "contrapunctus11": 6, "canon-alla-ottava": 15, "canon-alla-decima": 5,
            "canon-per-augmentationem": 6}
    for pid in KERN:
        assert "alternatives" not in m_of(pid)["source"]
        got = sum(1 for n in piece(built, pid)["notes"] if n.get("c"))
        assert got == want.get(pid, 0), (pid, got)


def test_instruments_are_strings_except_the_keyboard_canons(built):
    for pid in AOF:
        p = piece(built, pid)
        inst = [v["instrument"] for v in p["voices"]]
        if pid in CANONS:
            assert p["ensemble"] == "harpsichord" and set(inst) == {"harpsichord"}
        else:
            assert p["ensemble"] == "strings" and set(inst) <= {"violin", "viola", "cello"}
            assert inst[0] == "violin" and inst[-1] == "cello"


# ---- the fugues: forms and subjects ----

# statements whose form the notes leave undecided (wtc_form: neither level; the opening
# interval neither the subject's nor the answer's): labelled subject. Contrapunctus X:
# the upper voice of a pair doubled in thirds changes the subject's first interval.
UNDECIDED = {("contrapunctus10", 205.0), ("contrapunctus10", 337.0)}


@pytest.mark.parametrize("pid", [p for p in FUGUES if p != "contrapunctus07"])
def test_forms_follow_the_notes(pid):
    """As in the WTC: every statement's label is the form its notes have; form_by:
    opening where it stands at neither level. In the fugues on several subjects the later
    subjects are labelled subject throughout (no answer of theirs is marked)."""
    m = m_of(pid)
    voices = load_voices(m, MARKINGS)
    for e in m["fugue"]["entries"]:
        if e.get("subject") not in (None, "I"):
            assert e["form"] == "subject" and e["form_by"] is None, (pid, e["start"])
            continue
        got = wtc_form(m, voices, e)
        if (pid, e["start"]) in UNDECIDED:
            assert got == "neither" and opening_form(m, voices, e) is None
            assert e["form"] == "subject" and e["form_by"] is None
        elif e["form_by"] == "opening":
            assert got == "neither", (pid, e["start"], got)
            assert e["form"] == opening_form(m, voices, e), (pid, e["start"])
        else:
            assert e["form"] == got, (pid, e["start"], e["form"], got)


def test_contrapunctus_7_forms_by_the_first_leap():
    """As in Contrapunctus VI: a first leap of a fourth (upside down when inverted) is the
    tonal answer, of a fifth the subject; and the subject at plain length, right way up,
    first sounds in bar 36 (the reference)."""
    m = m_of("contrapunctus07")
    voices = load_voices(m, MARKINGS)
    for e in m["fugue"]["entries"]:
        ns = [voices[e["voice"]][i] for i in find_entry(
            voices, entry_reference(voices, m["fugue"], e), e["voice"], e["start"],
            e["transform"], head=e["head"], tail=e["tail"], head_length=e["head_length"], octave=e.get("octave", ()))]
        sign = -1 if e["transform"].startswith("inverted") else 1
        leap = sign * (ns[1].p - ns[0].p)
        assert leap in (5, 7)
        assert e["form"] == ("answer" if leap == 5 else "subject"), e["start"]
    plain = [e for e in m["fugue"]["entries"] if e["transform"] == "none"]
    assert min(e["start"] for e in plain) == m["fugue"]["subject"]["start"] == 142
    assert {e["transform"] for e in m["fugue"]["entries"]} == {
        "none", "inverted", "diminished", "inverted diminished", "augmented",
        "inverted augmented"}


SUBJECTS = {  # piece -> {id: first pitches}
    "contrapunctus08": {"I": [62, 60, 65, 59], "II": [70, 68, 69, 69], "III": [69, 62, 64, 65]},
    "contrapunctus09": {"I": [62, 74, 73, 71], "II": [74, 81, 77, 74]},
    "contrapunctus10": {"I": [61, 62, 57, 65], "II": [57, 50, 52, 53]},
    "contrapunctus11": {"I": [62, 69, 67, 65], "II": [57, 58, 53, 60], "III": [51, 50, 53, 53]},
    "contrapunctus14": {"I": [50, 57, 55, 53], "II": [62, 57, 62, 64],
                        "III": [58, 57, 60, 59]},  # B♭ A C B♮: B-A-C-H
}


@pytest.mark.parametrize("pid", list(SUBJECTS))
def test_the_subjects_are_where_the_markings_say(pid, built):
    m = m_of(pid)
    voices = load_voices(m, MARKINGS)
    for sid, pitches in SUBJECTS[pid].items():
        spec = subject_spec(m["fugue"], {"subject": sid})
        assert [x.p for x in subject_notes(voices, spec)][:4] == pitches, (pid, sid)
    labels = {k["label"] for k in piece(built, pid)["marks"] if k["kind"] == "entry"}
    for sid in SUBJECTS[pid]:
        assert any(re.match(rf"(subject|answer) {sid}\b", x) for x in labels), (pid, sid)


def test_contrapunctus_14_ends_where_bach_stopped(built):
    """No completion: the tenor plays on alone from beat 2 of bar 239; B-A-C-H (subject
    III) sounds from bar 193."""
    p = piece(built, "contrapunctus14")
    last = max(n["s"] + n["d"] for n in p["notes"])
    assert math.ceil(last / 4) == 239
    tail = [n for n in p["notes"] if n["s"] >= 238 * 4 + 1]
    assert tail and {n["v"] for n in tail} == {2}
    bach = [k for k in p["marks"] if k["kind"] == "entry" and k["label"].startswith("subject III")]
    assert min(k["start"] for k in bach) == 192 * 4 + 2 and len(bach) == 12


# ---- the mirror fugues ----

# rectus voice -> (inversus voice, axis, interval in D minor scale steps)
MIRRORS = {
    ("contrapunctus12-rectus", "contrapunctus12-inversus"):
        {0: (3, 50, 11), 1: (2, 50, 11), 2: (1, 50, 11), 3: (0, 50, 11)},
    ("contrapunctus13-rectus", "contrapunctus13-inversus"):
        {0: (2, 53, 14), 1: (0, 60, 13), 2: (1, 50, 11)},
}


@pytest.mark.parametrize("pair", list(MIRRORS))
def test_the_inversus_is_the_rectus_upside_down(pair, built):
    """Every rectus voice, mirrored on the D minor scale, is an inversus voice at the
    same time (the voices exchanged, each in its own octave): at least 96 % of the notes,
    a few raised or lowered a semitone (pitch_tolerance 1); the entries mirror too."""
    rect, inv = (load_voices(m_of(p), MARKINGS) for p in pair)
    for v, (w, axis, iv) in MIRRORS[pair].items():
        rule = Rule(delay=inv[w][0].s - rect[v][0].s, interval=iv, diatonic=True, key="d",
                    invert_about=axis, retrograde=False, stretch=1, per_tonos_step=0,
                    repeats=1, pitch_tolerance=1)
        assert inv[w][0].s == rect[v][0].s
        th = match(rect[v], inv[w], rule)
        assert sum(not t.broken for t in th) >= 0.96 * len(rect[v]), (pair, v)
    er = sorted((e["start"], MIRRORS[pair][e["voice"]][0]) for e in m_of(pair[0])["fugue"]["entries"])
    ei = sorted((e["start"], e["voice"]) for e in m_of(pair[1])["fugue"]["entries"])
    assert er == ei


# ---- the canons ----

INTERVAL_WORDS = {-7: "octave lower", 11: "twelfth higher", 9: "tenth higher",
                  -14: "two octaves down"}


@pytest.mark.parametrize("pid", CANONS)
def test_canon_captions_say_what_the_rule_does(pid, built):
    """A caption on each section's leader and one on the beat its follower first answers,
    naming the interval (or the mirror and the doubled length) and the distance in bars."""
    m = m_of(pid)
    p = piece(built, pid)
    caps = {c["at"]: c["text"] for c in p["captions"]}
    notes = p["notes"]
    bpb = m["beats_per_bar"]
    for sec in m["canon"]:
        f = sec["followers"][0]
        rule = f["rule"]
        lead0 = sec["span"][0] if sec["span"] else 0
        assert any(lead0 <= at <= lead0 + bpb for at in caps), (pid, lead0)
        firsts = [notes[t["b"]]["s"] for t in p["threads"] if not t["broken"]
                  and notes[t["b"]]["v"] == f["voice"] and notes[t["a"]]["v"] == sec["leader"]
                  and lead0 <= notes[t["a"]]["s"] < (sec["span"] or (0, math.inf))[1]]
        b = min(firsts)
        text = caps[math.floor(b)]
        if rule.invert_about is not None:
            assert "upside down" in text or "inverted" in text
            assert ("twice as slow" in text or "double length" in text) == (rule.stretch == 2)
        else:
            assert INTERVAL_WORDS[rule.interval] in text or (
                rule.interval == -7 and "octave down" in text), text
            bars = (b - lead0) / bpb
            word = {4: "four bars later", 8: "eight bars later"}[round(bars)]
            assert word in text, text


# ---- captions ----

@pytest.mark.parametrize("pid", [p for p in AOF if p in FUGUES])
def test_fugue_captions_say_what_the_notes_do(pid, built):
    m = m_of(pid)
    p = piece(built, pid)
    voices = load_voices(m, MARKINGS)
    es = m["fugue"]["entries"]
    names = [v["name"].lower() for v in m["voices"]]

    def notes_of(e):
        return [voices[e["voice"]][i] for i in find_entry(
            voices, entry_reference(voices, m["fugue"], e), e["voice"], e["start"],
            e["transform"], head=e["head"], tail=e["tail"], head_length=e["head_length"], octave=e.get("octave", ()))]
    for c in p["captions"]:
        text, at = c["text"], c["at"]
        here = [e for e in es if e["start"] == at]
        near = [e for e in es if abs(e["start"] - at) <= 2 * m["beats_per_bar"]]
        assert here, text
        for w in VOICE_WORDS:
            if f"in the {w}" in text:
                assert any(names[e["voice"]] == w for e in near), (pid, text)
        if re.search(r"\bthe answer\b", text, re.I):
            assert any(e["form"] == "answer" for e in here), (pid, text)
        if re.search(r"(subject|answer)( I+)? inverted|inverted and|subject inverted", text):
            assert any(e["transform"].startswith("inverted") for e in near), (pid, text)
        for word, tr in (("diminution", "diminished"), ("augmentation", "augmented")):
            if f"in {word}" in text:
                assert any(tr in e["transform"] for e in here), (pid, text)
        for sid in ("II", "III"):
            if re.search(rf"\bsubject {sid}\b|\b{sid} in\b", text):
                assert any(e.get("subject") == sid for e in near), (pid, text)
        if "B-A-C-H" in text:
            assert any(e.get("subject") == "III" for e in here), (pid, text)
        mo = re.search(r"\bon ([A-G][♯♭]?)(?![♯♭\w])", text)
        if mo:
            assert any(notes_of(e)[0].p % 12 == PITCH[mo.group(1)] for e in here), (pid, text)
        if "last entr" in text:
            assert max(e["start"] for e in es) - at <= 8, (pid, text)
        if text.startswith("☞ Stretto"):
            assert any(e["stretto"] for e in here), (pid, text)
        mo = re.search(r"all (three|four) voices are in", text)
        if mo:
            n = {"three": 3, "four": 4}[mo.group(1)]
            assert n == len(voices) == len({e["voice"] for e in es if e["start"] <= at})
        if "All three" in text or "all three subjects" in text:
            assert {e.get("subject") for e in near} >= {"I", "II", "III"}, (pid, text)
        mo = re.search(r"a (third|sixth|tenth) apart", text)
        if mo:
            close = [e for e in es if abs(e["start"] - at) <= 1]
            pair = next([e for e in close if e.get("subject") == sid]
                        for sid in {e.get("subject") for e in close}
                        if len([e for e in close if e.get("subject") == sid]) == 2)
            a, b = (notes_of(e) for e in pair)
            gap = abs(a[2].p - b[2].p)
            size = (8, 9) if mo.group(1) == "sixth" else (3, 4)
            assert gap % 12 in size and (gap > 12) == (mo.group(1) == "tenth"), (pid, text)
