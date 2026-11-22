"""Every "In this piece" line (markings ``glossary_notes``) is a musical claim; each is
checked here against the built piece. A new note needs a new check: the test fails on a
note it does not know, and on a check whose note has gone or changed."""
import json

import pytest

from fugue_prep.build import WEB_DATA
from tests.scales import from_step, to_step


def piece(pid: str) -> dict:
    return json.loads((WEB_DATA / "pieces" / f"{pid}.json").read_text())


def pairs(p: dict) -> list[tuple[dict, dict, dict]]:
    """(leader note, follower note, thread), by the leader's start."""
    ns = p["notes"]
    return sorted(((ns[t["a"]], ns[t["b"]], t) for t in p["threads"]), key=lambda x: x[0]["s"])


def bar(p: dict, beat: float) -> int:
    return int((beat - p.get("pickup", 0)) // p["beatsPerBar"]) + 1


def mirrored_about(p: dict, lead: int, follow: int, axis: int, key: str) -> None:
    """The follower is the leader mirrored diatonically about ``axis`` (each note's accidental
    carried over); an adjusted note is exactly a semitone from that strict mirror (Bach's raised
    or lowered 6th and 7th), every other note exactly on it."""
    ps = pairs(p)
    assert ps
    ax = to_step(axis, key)[0]
    for a, b, t in ps:
        assert (a["v"], b["v"], t["kind"]) == (lead, follow, "mirror")
        step, alt = to_step(a["p"], key)
        strict = from_step(2 * ax - step, alt, key)
        assert abs(b["p"] - strict) == (1 if t["adjusted"] else 0), (a, b)
    assert any(m["kind"] == "mirror-axis" and m["pitch"] == axis for m in p["marks"])


def check_motum_inversion(p):
    mirrored_about(p, 1, 2, 63, "c")  # 63 = e♭'


def check_augmentationem_augmentation(p):
    for a, b, _ in pairs(p):
        if b["s"] + b["d"] < 144:  # the closing chord at beat 144 cuts the last one
            assert b["d"] == 2 * a["d"], (a, b)
    assert any(m["kind"] == "stretch" and m["label"] == "×2" for m in p["marks"])


def check_augmentationem_inversion(p):
    mirrored_about(p, 2, 0, 63, "c")


def check_quaerendo_inversion(p):
    ps = pairs(p)
    assert all(a["p"] + b["p"] == 2 * 55 for a, b, _ in ps)  # exact, about g (55)
    answered = {a["p"]: b["p"] for a, b, _ in ps}
    assert answered[60] == 50 and answered[63] == 47  # c' -> d, e♭' -> b


def check_canone_perpetuo_inversion(p):
    ps = pairs(p)
    assert all(b["s"] - a["s"] == 8 for a, b, _ in ps)  # two bars of 4/4
    assert any(a["p"] == 72 and b["p"] == 79 for a, b, _ in ps)  # c'' -> g''
    # the axis by the violin's bars, in order: pitch sum 151, or 141 (10 semitones, a minor
    # seventh, lower; its adjusted notes are a semitone off, sum 140)
    runs: list[list] = []
    for a, b, t in sorted(ps, key=lambda x: x[1]["s"]):
        axis = "first" if a["p"] + b["p"] == 151 else "lower"
        assert a["p"] + b["p"] in ((151,) if axis == "first" else (141, 140)), (a, b)
        if runs and runs[-1][0] == axis:
            runs[-1][2] = bar(p, b["s"])
        else:
            runs.append([axis, bar(p, b["s"]), bar(p, b["s"])])
    assert runs == [["first", 3, 20], ["lower", 20, 32], ["first", 33, 50], ["lower", 50, 62],
                    ["first", 63, 75]]


def check_per_tonos(p):
    rises = [m["label"] for m in p["marks"] if m["kind"] == "rise"]
    assert rises == ["C minor", "D minor", "E minor", "F♯ minor", "G♯ minor", "B♭ minor"]
    # the dux's pass begins after a semiquaver rest and ends on the next pass's downbeat
    dux = [n for n in p["notes"] if n["v"] == 2]
    def pass_(k):
        return [(n["p"], n["s"] - 32 * k, n["d"]) for n in dux if 32 * k < n["s"] <= 32 * (k + 1)]
    for k in range(1, 6):
        want = [(q + 2 * k, s, d) for q, s, d in pass_(0)]
        if k == 5:  # the last pass ends on the closing chord instead of the next downbeat
            assert pass_(k)[:-1] == want[:-1]
        else:
            assert pass_(k) == want, k


def check_cancrizans_retrograde(p):
    dux = sorted((n for n in p["notes"] if n["v"] == 0), key=lambda n: n["s"])
    comes = sorted((n for n in p["notes"] if n["v"] == 1), key=lambda n: n["s"])
    end = max(n["s"] + n["d"] for n in dux)
    assert [(n["p"], end - n["s"] - n["d"], n["d"]) for n in reversed(dux)] == \
        [(n["p"], n["s"], n["d"]) for n in comes]
    assert comes[0]["p"] == dux[-1]["p"] and comes[-1]["p"] == dux[0]["p"]


def check_thema_regium_canon(p):
    assert p["voices"][1]["name"] == "Thema"
    assert {(a["v"], b["v"]) for a, b, _ in pairs(p)} == {(0, 2)}  # flute -> cello only
    assert (p["voices"][0]["instrument"], p["voices"][2]["instrument"]) == ("flute", "cello")


def check_violini_unison(p):
    ps = pairs(p)
    assert all(b["p"] == a["p"] and b["s"] - a["s"] == 4 for a, b, _ in ps)
    v1 = [n for n in p["notes"] if n["v"] == 0]
    v2 = [n for n in p["notes"] if n["v"] == 1]
    above = {(b["p"] > a["p"]) for a in v1 for b in v2
             if b["s"] < a["s"] + a["d"] and a["s"] < b["s"] + b["d"] and a["p"] != b["p"]}
    assert above == {True, False}  # each violin is sometimes the higher: they cross


def check_fuga_canonica_interval(p):
    assert {(a["v"], b["v"]) for a, b, _ in pairs(p)} == {(1, 0)}  # the bass (2) is free
    assert [v["instrument"] for v in p["voices"]] == ["flute", "harpsichord", "harpsichord"]
    assert p["voices"][2]["name"] == "Bass"


def check_var15_inversion(p):
    ps = pairs(p)
    assert all((a["v"], b["v"]) == (1, 0) for a, b, _ in ps)
    assert [v["name"] for v in p["voices"][:2]] == ["Comes", "Dux"]
    steps = 0
    for (a1, b1, _), (a2, b2, _) in zip(ps, ps[1:]):
        da, db = a2["p"] - a1["p"], b2["p"] - b1["p"]
        if da or db:
            assert da * db < 0, (a1, a2)
            steps += 1
    assert steps > 100
    assert any(m["kind"] == "mirror-axis" for m in p["marks"])


def check_canon_a4_unison(p):
    """Each thread from the flute: to the violin at the same pitch, to the cello and the
    harpsichord two octaves lower; the entries 7, 14 and 21 bars after the flute's."""
    facts = {}
    for a, b, t in pairs(p):
        assert t["kind"] == "imitation" and not t["broken"] and not t["adjusted"]
        assert a["v"] == 0
        facts.setdefault(b["v"], set()).add((b["p"] - a["p"], b["s"] - a["s"]))
    assert facts == {1: {(0, 56)}, 2: {(-24, 28)}, 3: {(-24, 84)}}
    names = [v["name"] for v in p["voices"]]
    assert names == ["Treble I", "Treble II", "Bass I", "Bass II"]


NOTES = {
    ("bwv1079-motum-contrarium", "inversion"):
        ("The comes mirrors the dux about E♭ — watch the dashed line.", check_motum_inversion),
    ("bwv1079-augmentationem", "augmentation"):
        ("Every note of the comes lasts twice as long as the dux note it answers: the bracket "
         "marked ×2.", check_augmentationem_augmentation),
    ("bwv1079-augmentationem", "inversion"):
        ("The comes is upside down as well: the dux mirrored about E♭, along the dashed line.",
         check_augmentationem_inversion),
    ("bwv1079-quaerendo", "inversion"):
        ("An exact mirror about g: the dux's c' is answered by d, its e♭' by b.",
         check_quaerendo_inversion),
    ("bwv1079-canone-perpetuo", "inversion"):
        ("Exact contrary motion: the flute's c'' is answered by the violin's g'', two bars later; "
         "in bars 20–32, and again in bars 50–62, the mirror lies a seventh lower.", check_canone_perpetuo_inversion),
    ("bwv1079-per-tonos", "per-tonos"):
        ("Six passes, each a whole tone higher than the last: C, D, E, F♯, G♯ and B♭ minor.",
         check_per_tonos),
    ("bwv1079-cancrizans", "retrograde"):
        ("The comes is the dux read backwards: it begins with the dux's last note and ends with "
         "its first.", check_cancrizans_retrograde),
    ("bwv1079-thema-regium", "canon"):
        ("The royal theme in the middle takes no part in the canon: only the flute and the cello "
         "imitate.", check_thema_regium_canon),
    ("bwv1079-violini-in-unisono", "canon-at-the-unison"):
        ("At the unison the two violins share one range, so their lines cross: switch one off "
         "to hear the other.", check_violini_unison),
    ("bwv1079-canon-a4", "canon-at-the-unison"):
        ("Four voices, one line: the two trebles sing it at the same pitch, the two basses two "
         "octaves lower; the four entries come seven bars apart.", check_canon_a4_unison),
    ("bwv1079-fuga-canonica", "canon-at-an-interval"):
        ("The bass is free: only the flute imitates, following the harpsichord's right hand.",
         check_fuga_canonica_interval),
    ("goldberg-var15", "inversion"):
        ("Where the dux rises the comes falls, step for step: the dashed line is the axis "
         "between them.", check_var15_inversion),
}


def notes_in_the_data() -> dict[tuple[str, str], str]:
    out = {}
    for f in sorted((WEB_DATA / "pieces").glob("*.json")):
        p = json.loads(f.read_text())
        for eid, text in p.get("glossaryNotes", {}).items():
            out[(p["id"], eid)] = text
    return out


def test_every_note_has_a_check_and_says_what_is_checked():
    assert notes_in_the_data() == {k: text for k, (text, _) in NOTES.items()}


@pytest.mark.parametrize("key", sorted(NOTES), ids=lambda k: f"{k[0]}:{k[1]}")
def test_the_note_is_true_of_the_piece(key):
    _, check = NOTES[key]
    check(piece(key[0]))


def test_notes_name_the_entries_of_techniques_the_piece_has():
    g = json.loads((WEB_DATA / "glossary.json").read_text())
    for (pid, eid) in NOTES:
        p = piece(pid)
        assert eid in {g["techniques"][t] for t in p["techniques"]}, (pid, eid)
