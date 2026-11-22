import json
import shutil
from pathlib import Path

import pytest
import yaml

from fugue_prep.build import MARKINGS, BuildError, build_all
from fugue_prep.markings import MarkingsError, load_markings
from fugue_prep.markings import load_collections
from fugue_prep.model import ENSEMBLE_INSTRUMENTS, ENSEMBLES, instruments_for, pan_for
from fugue_prep.validate import validate_piece


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("data")
    build_all(out)
    return out


def pieces(out: Path) -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((out / "pieces").glob("*.json"))]


def test_build_writes_valid_pieces(built):
    ps = pieces(built)
    assert {p["id"] for p in ps} >= {"bwv847", "frere-jacques"}
    for p in ps:
        assert validate_piece(p) == [], p["id"]


def test_technique_index_lists_each_piece_under_each_of_its_techniques(built):
    lib = json.loads((built / "library.json").read_text())
    ps = pieces(built)
    for p in ps:
        assert p["techniques"]
        for t in p["techniques"]:
            assert p["id"] in lib["techniques"][t]
    listed = {(t, pid) for t, ids in lib["techniques"].items() for pid in ids}
    assert listed == {(t, p["id"]) for p in ps for t in p["techniques"]}
    assert list(lib["techniques"]) == sorted(lib["techniques"])


def test_library_has_the_six_collections_in_order(built):
    lib = json.loads((built / "library.json").read_text())
    cols = lib["collections"]
    assert [c["id"] for c in cols] == ["rounds", "musical-offering", "goldberg", "art-of-fugue", "wtc",
                                       "inventions"]
    assert [c["numeral"] for c in cols] == ["I", "II", "III", "IV", "V", "VI"]
    assert [b["name"] for b in cols[-1]["books"]] == ["Inventions", "Sinfonias"]
    wtc = cols[-2]
    assert wtc["books"][0]["name"] == "Book I" and wtc["books"][0]["pieces"][:2] == ["bwv846", "bwv847"]
    summary = {s["id"]: s for s in lib["pieces"]}["bwv847"]
    assert summary["voices"] == 3 and summary["bars"] == 31 and summary["collection"] == "wtc"


def test_library_summaries_carry_listen_for_and_catalogue(built):
    lib = json.loads((built / "library.json").read_text())
    by_id = {p["id"]: p for p in pieces(built)}
    for s in lib["pieces"]:
        p = by_id[s["id"]]
        assert s["listenFor"] == p["listenFor"] and s["listenFor"], s["id"]
        assert s["catalogue"] == p["catalogue"] and s["catalogue"], s["id"]


def test_round_threads_use_global_note_indices(built):
    p = json.loads((built / "pieces" / "frere-jacques.json").read_text())
    notes = p["notes"]
    assert p["threads"]
    for t in p["threads"]:
        a, b = notes[t["a"]], notes[t["b"]]
        assert a["v"] == 0 and b["v"] in (1, 2, 3)
        assert b["p"] == a["p"] and b["s"] - a["s"] == 8 * b["v"]
        assert not t["broken"]
    assert notes == sorted(notes, key=lambda n: (n["s"], n["v"]))


def test_fugue_entries_become_marks(built):
    p = json.loads((built / "pieces" / "bwv847.json").read_text())
    entries = [m for m in p["marks"] if m["kind"] == "entry" and m["label"] != "countersubject"]
    assert len(entries) == 8  # the subject's entries; the countersubject's are marks too
    assert entries[1] == {"kind": "entry", "start": 8.5, "end": 16.25, "voice": 0,
                          "pitch": None, "label": "answer"}


def test_voices_get_default_instruments_and_pan(built):
    p = json.loads((built / "pieces" / "bwv847.json").read_text())
    assert [v["instrument"] for v in p["voices"]] == ["harpsichord"] * 3
    assert [v["pan"] for v in p["voices"]] == [-0.6, 0.0, 0.6]


def test_instruments_for_each_ensemble():
    assert instruments_for("strings", 4) == ["violin", "violin", "viola", "cello"]
    assert instruments_for("strings", 3) == ["violin", "violin", "cello"]
    assert instruments_for("strings", 2) == ["violin", "cello"]
    assert instruments_for("chamber", 3) == ["flute", "violin", "cello"]
    # chamber: the cello is continuo; a two-voice (treble) canon is flute + violin
    assert instruments_for("chamber", 2) == ["flute", "violin"]
    assert instruments_for("chamber", 1) == ["flute"]
    assert instruments_for("chamber", 4) == ["flute", "violin", "violin", "cello"]
    assert instruments_for("organ", 4) == ["organ"] * 4
    assert instruments_for("harpsichord", 1) == ["harpsichord"]
    assert [pan_for(i, 5) for i in range(5)] == [-0.6, -0.3, 0.0, 0.3, 0.6]
    assert pan_for(0, 1) == 0.0


# --- a scratch markings tree for error cases and per-tonos remapping ---

TINY_TRANSCRIPTION = {"source": "test", "voices": [[[60, 0, 1], [62, 1, 1], [64, 2, 2]]]}
TINY_PIECE = {
    "id": "tiny-tonos", "title": "Tiny", "catalogue": "T 1", "key": "C major", "tempo": 80,
    "beats_per_bar": 4, "ensemble": "chamber", "listen_for": "rising", "techniques": ["per tonos"],
    "source": {"kind": "generated", "path": "transcriptions/tiny.yaml"},
    # instruments with room for the scratch tests' notes (the chamber defaults have not)
    "voices": [{"name": "Dux", "texture": "solid", "instrument": "harpsichord"},
               {"name": "Comes", "texture": "hatch", "instrument": "cello"}],
    "canon": {"leader": 0, "followers": [
        {"voice": 1, "rule": {"delay": 1, "interval": -12, "per_tonos_step": 2, "repeats": 3}}]},
    "captions": [{"at": 0, "text": "Begins."}, {"bar": 2, "text": "Rises."}],
}


def scratch(tmp_path: Path, piece: dict, transcription: dict | None = None) -> Path:
    root = tmp_path / "prep"
    (root / "markings" / "rounds").mkdir(parents=True, exist_ok=True)
    (root / "transcriptions").mkdir(exist_ok=True)
    shutil.copy(MARKINGS / "collections.yaml", root / "markings" / "collections.yaml")
    (root / "transcriptions" / "tiny.yaml").write_text(yaml.safe_dump(transcription or TINY_TRANSCRIPTION))
    (root / "markings" / "rounds" / "tiny.yaml").write_text(yaml.safe_dump(piece, sort_keys=False))
    return root / "markings"


def test_per_tonos_threads_point_into_the_expanded_leader(tmp_path):
    out = tmp_path / "out"
    build_all(out, markings_dir=scratch(tmp_path, TINY_PIECE))
    p = json.loads((out / "pieces" / "tiny-tonos.json").read_text())
    notes = p["notes"]
    assert len(notes) == 18 and len(p["threads"]) == 9
    leader = [n for n in notes if n["v"] == 0]
    assert [n["p"] for n in leader] == [60, 62, 64, 62, 64, 66, 64, 66, 68]
    for t in p["threads"]:
        a, b = notes[t["a"]], notes[t["b"]]
        assert (a["v"], b["v"]) == (0, 1)
        assert b["p"] == a["p"] - 12 and b["s"] == a["s"] + 1
    assert p["captions"] == [{"at": 0, "text": "Begins."}, {"at": 4, "text": "Rises."}]
    assert validate_piece(p) == []


def test_unknown_key_is_reported_with_the_file(tmp_path):
    bad = dict(TINY_PIECE, tempi=80)
    with pytest.raises(MarkingsError, match=r"tiny\.yaml.*unknown key 'tempi'"):
        build_all(tmp_path / "out", markings_dir=scratch(tmp_path, bad))


def test_missing_key_is_reported_with_the_file(tmp_path):
    bad = {k: v for k, v in TINY_PIECE.items() if k != "ensemble"}
    with pytest.raises(MarkingsError, match=r"tiny\.yaml.*missing key 'ensemble'"):
        build_all(tmp_path / "out", markings_dir=scratch(tmp_path, bad))


def test_unknown_rule_field_is_reported(tmp_path):
    bad = json.loads(json.dumps(TINY_PIECE))
    bad["canon"]["followers"][0]["rule"]["intervall"] = 3
    with pytest.raises(MarkingsError, match=r"tiny\.yaml.*canon\.followers\[0\]\.rule.*'intervall'"):
        load_markings_tree(tmp_path, bad)


def test_every_rule_field_is_accepted(tmp_path):
    full = json.loads(json.dumps(TINY_PIECE))
    full["canon"]["followers"][0]["rule"] = {
        "delay": 4, "interval": -4, "diatonic": True, "key": "c", "invert_about": 67,
        "retrograde": False, "stretch": 2, "per_tonos_step": 0, "repeats": 1,
        "exceptions": {2: 59}, "free": [[8, 12]], "flip_alterations": True, "pitch_tolerance": 1,
        "not_imitation": [3, 4.5]}
    m = load_markings_tree(tmp_path, full)
    rule = m["canon"][0]["followers"][0]["rule"]
    assert rule.free == ((8.0, 12.0),) and rule.exceptions == {2: 59} and rule.invert_about == 67
    assert rule.not_imitation == (3.0, 4.5)


def test_bad_enum_and_voice_are_reported(tmp_path):
    bad = dict(TINY_PIECE, ensemble="choir")
    with pytest.raises(MarkingsError, match="ensemble"):
        load_markings_tree(tmp_path, bad)
    bad = json.loads(json.dumps(TINY_PIECE))
    bad["canon"]["followers"][0]["voice"] = 5
    with pytest.raises(MarkingsError, match="voice 5"):
        load_markings_tree(tmp_path, bad)


def test_countersubject_entry_needs_a_countersubject(tmp_path):
    bad = {k: v for k, v in TINY_PIECE.items() if k != "canon"}
    bad["fugue"] = {"subject": {"voice": 0, "start": 0, "length": 4},
                    "entries": [{"voice": 0, "start": 0, "form": "countersubject"}]}
    with pytest.raises(MarkingsError, match="countersubject"):
        load_markings_tree(tmp_path, bad)


def test_misplaced_entry_fails_the_build(tmp_path):
    bad = {k: v for k, v in TINY_PIECE.items() if k != "canon"}
    bad["voices"] = bad["voices"][:1]
    bad["fugue"] = {"subject": {"voice": 0, "start": 0, "length": 4},
                    "entries": [{"voice": 0, "start": 1, "form": "subject"}]}
    with pytest.raises(BuildError, match="tiny-tonos: bar 1"):
        build_all(tmp_path / "out", markings_dir=scratch(tmp_path, bad))


def load_markings_tree(tmp_path: Path, piece: dict) -> dict:
    return load_markings(scratch(tmp_path, piece) / "rounds" / "tiny.yaml")


# --- small fixes carried into Task 7 ---

def test_ensembles_are_the_instrument_table_keys():
    assert ENSEMBLES == tuple(ENSEMBLE_INSTRUMENTS)


def test_followers_must_share_per_tonos_step(tmp_path):
    bad = json.loads(json.dumps(TINY_PIECE))
    bad["voices"].append({"name": "Third", "texture": "stipple"})
    bad["canon"]["followers"].append(
        {"voice": 2, "rule": {"delay": 2, "per_tonos_step": 1, "repeats": 3}})
    with pytest.raises(MarkingsError, match="per_tonos_step"):
        load_markings_tree(tmp_path, bad)


def test_empty_fugue_entries_are_rejected(tmp_path):
    bad = {k: v for k, v in TINY_PIECE.items() if k != "canon"}
    bad["fugue"] = {"subject": {"voice": 0, "start": 0, "length": 4}, "entries": []}
    with pytest.raises(MarkingsError, match="entries"):
        load_markings_tree(tmp_path, bad)


def test_bad_yaml_in_collections_is_a_markings_error(tmp_path):
    f = tmp_path / "collections.yaml"
    f.write_text("collections: [unclosed\n")
    with pytest.raises(MarkingsError, match="collections.yaml.*not valid YAML"):
        load_collections(f)


# --- the end of a perpetual canon: cut, then a closing cadence ---

def test_end_cuts_every_voice_and_coda_adds_the_closing_notes(tmp_path):
    piece = json.loads(json.dumps(TINY_PIECE))
    trans = dict(TINY_TRANSCRIPTION, end=9.5,
                 coda=[[[72, 10, 2]], [[60, 10, 2]]])  # one list per piece voice
    out = tmp_path / "out"
    build_all(out, markings_dir=scratch(tmp_path, piece, trans))
    p = json.loads((out / "pieces" / "tiny-tonos.json").read_text())
    notes = p["notes"]
    assert all(n["s"] < 10 or (n["s"], n["d"]) == (10, 2) for n in notes)
    assert all(n["s"] + n["d"] <= 12 for n in notes)
    assert all(n["s"] + n["d"] <= 9.5 for n in notes if n["s"] < 10)  # overlapping notes shortened
    assert sorted(n["d"] for n in notes if n["s"] == 9) == [0.5, 0.5]
    finals = sorted((n["v"], n["p"]) for n in notes if n["s"] == 10)
    assert finals == [(0, 72), (1, 60)]
    # threads only between notes that remain, none to the coda
    for t in p["threads"]:
        assert notes[t["a"]]["s"] < 10 and notes[t["b"]]["s"] < 10
        assert notes[t["b"]]["p"] == notes[t["a"]]["p"] - 12
    # leader onsets 0 1 2 4 5 6 8 9 survive, follower 1 2 3 5 6 7 9: seven pairs
    assert len(p["threads"]) == 7
    assert validate_piece(p) == []


def test_coda_needs_one_list_per_piece_voice(tmp_path):
    trans = dict(TINY_TRANSCRIPTION, end=10, coda=[[[72, 10, 2]]])
    with pytest.raises(BuildError, match="coda"):
        build_all(tmp_path / "out", markings_dir=scratch(tmp_path, TINY_PIECE, trans))


def test_beat_unit_is_the_beat_in_quarter_notes(built):
    by_id = {p["id"]: p for p in pieces(built)}
    assert by_id["goldberg-var06"]["beatUnit"] == 0.5  # 3/8: a beat is an eighth
    assert by_id["goldberg-var03"]["beatUnit"] == 1
    assert by_id["bwv847"]["beatUnit"] == 1


# --- canons checked against a score: the share of the leader that is imitated ---

def _score_piece(canon) -> dict:
    piece = {k: v for k, v in TINY_PIECE.items() if k != "canon"}
    return dict(piece, source={"kind": "mutopia", "path": "Test/none"}, canon=canon)


def _fake_score(monkeypatch, voices):
    import fugue_prep.build as build
    from fugue_prep.model import Note
    notes = [[Note(v, p, float(s), float(d)) for p, s, d in vs] for v, vs in enumerate(voices)]
    monkeypatch.setattr(build, "load_voices", lambda m, markings_dir=MARKINGS, secondary=False: notes)


# ten leader notes; the follower imitates the first five one beat later, then is silent
TEN = [[60 + i, i, 1] for i in range(10)]
FIVE = [[60 + i, i + 1, 1] for i in range(5)]


def test_min_match_counts_unanswered_leader_notes(tmp_path, monkeypatch):
    """A follower that stops imitating has no threads there; those leader notes are misses."""
    _fake_score(monkeypatch, [TEN, FIVE])
    piece = _score_piece({"leader": 0, "followers": [{"voice": 1, "rule": {"delay": 1}}]})
    with pytest.raises(BuildError, match=r"5 of 10 .*notes"):
        build_all(tmp_path / "out", markings_dir=scratch(tmp_path, piece))


def test_free_leader_notes_are_not_counted(tmp_path, monkeypatch):
    _fake_score(monkeypatch, [TEN, FIVE])
    piece = _score_piece({"leader": 0, "followers": [
        {"voice": 1, "rule": {"delay": 1, "free": [[5, 10]]}}]})
    build_all(tmp_path / "out", markings_dir=scratch(tmp_path, piece))
    p = json.loads((tmp_path / "out" / "pieces" / "tiny-tonos.json").read_text())
    assert len(p["threads"]) == 5


def test_canon_sections_let_the_voices_swap_roles(tmp_path, monkeypatch):
    """Voice 0 leads in beats [0, 5), voice 1 in [5, 10): a section's span is its leader's
    notes; outside it nothing is matched or counted."""
    upper = [[72, 0, 1], [74, 1, 1], [76, 2, 1], [77, 3, 1], [79, 4, 1],
             [72, 6, 1], [71, 7, 1], [69, 8, 1], [67, 9, 1], [65, 10, 1]]
    lower = [[60, 1, 1], [62, 2, 1], [64, 3, 1], [65, 4, 1], [67, 5, 1],
             [60, 5, 1], [59, 6, 1], [57, 7, 1], [55, 8, 1], [53, 9, 1]]
    lower.pop(4)  # the lower voice's last answer gives way to its own lead at beat 5
    _fake_score(monkeypatch, [upper, lower])
    piece = _score_piece([
        {"span": [0, 4], "leader": 0, "followers": [{"voice": 1, "rule": {"delay": 1, "interval": -12}}]},
        {"span": [5, 10], "leader": 1, "followers": [{"voice": 0, "rule": {"delay": 1, "interval": 12}}]},
    ])
    out = tmp_path / "out"
    build_all(out, markings_dir=scratch(tmp_path, piece))
    p = json.loads((out / "pieces" / "tiny-tonos.json").read_text())
    notes = p["notes"]
    pairs = [(notes[t["a"]]["v"], notes[t["b"]]["v"], notes[t["a"]]["s"]) for t in p["threads"]]
    assert pairs == [(0, 1, 0), (0, 1, 1), (0, 1, 2), (0, 1, 3),
                     (1, 0, 5), (1, 0, 6), (1, 0, 7), (1, 0, 8), (1, 0, 9)]
    assert all(not t["broken"] for t in p["threads"])


def test_canon_sections_are_checked(tmp_path):
    two = [{"span": [0, 4], "leader": 0, "followers": [{"voice": 1, "rule": {"delay": 1}}]},
           {"span": [4, 2], "leader": 1, "followers": [{"voice": 0, "rule": {"delay": 1}}]}]
    with pytest.raises(MarkingsError, match=r"canon\[1\]\.span"):
        load_markings_tree(tmp_path, _score_piece(two))
    two[1]["span"] = [4, 8]
    # a computed follower (transcription/generated source) has one section only
    with pytest.raises(MarkingsError, match="one section"):
        load_markings_tree(tmp_path, dict(TINY_PIECE, canon=two))
    m = load_markings_tree(tmp_path, _score_piece(two))
    assert [s["span"] for s in m["canon"]] == [(0.0, 4.0), (4.0, 8.0)]
    assert [s["leader"] for s in m["canon"]] == [0, 1]


def test_not_imitation_notes_are_not_counted(tmp_path, monkeypatch):
    """Leader notes named in not_imitation are neither threaded nor counted for min_match."""
    _fake_score(monkeypatch, [TEN, FIVE])
    piece = _score_piece({"leader": 0, "followers": [
        {"voice": 1, "rule": {"delay": 1, "free": [[6, 10]], "not_imitation": [1, 5]}}]})
    build_all(tmp_path / "out", markings_dir=scratch(tmp_path, piece))
    p = json.loads((tmp_path / "out" / "pieces" / "tiny-tonos.json").read_text())
    assert sorted(p["notes"][t["a"]]["s"] for t in p["threads"]) == [0, 2, 3, 4]


# --- kern sources counted in eighths (3/8, 9/8 Inventions) ---

TINY_KERN = """**kern
*M3/8
=1
8c
8d
8e
=2
4.f
*-
"""


def test_kern_source_can_count_beats_in_eighths(tmp_path, monkeypatch):
    import fugue_prep.build as build
    from fugue_prep.build import load_voices
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "tiny.krn").write_text(TINY_KERN)
    monkeypatch.setattr(build, "SOURCES", tmp_path / "src")
    piece = {k: v for k, v in TINY_PIECE.items() if k != "canon"}
    piece = dict(piece, beats_per_bar=3, voices=[{"name": "Solo", "texture": "solid"}],
                 source={"kind": "kern", "path": "tiny.krn", "beats_per_quarter": 2},
                 fugue={"subject": {"voice": 0, "start": 0, "length": 3},
                        "entries": [{"voice": 0, "start": 0, "form": "subject"}]})
    md = scratch(tmp_path, piece)
    m = load_markings(md / "rounds" / "tiny.yaml")
    [notes] = load_voices(m, md)
    assert [(n.p, n.s, n.d) for n in notes] == [(60, 0, 1), (62, 1, 1), (64, 2, 1), (65, 3, 3)]
    build_all(tmp_path / "out", markings_dir=md)
    assert pieces(tmp_path / "out")[0]["beatUnit"] == 0.5


def test_kern_source_can_count_beats_in_dotted_eighths(tmp_path, monkeypatch):
    """9/16 counts three dotted eighths a bar: beat_unit 0.75 (quarter notes per beat). Onsets
    are divided by it, so whole-beat onsets come out exact (1.5 / 0.75 == 2.0)."""
    import fugue_prep.build as build
    from fugue_prep.build import load_voices
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "tiny.krn").write_text(TINY_KERN)
    monkeypatch.setattr(build, "SOURCES", tmp_path / "src")
    piece = {k: v for k, v in TINY_PIECE.items() if k != "canon"}
    piece = dict(piece, beats_per_bar=3, voices=[{"name": "Solo", "texture": "solid"}],
                 source={"kind": "kern", "path": "tiny.krn", "beat_unit": 0.75},
                 fugue={"subject": {"voice": 0, "start": 0, "length": 2},
                        "entries": [{"voice": 0, "start": 0, "form": "subject"}]})
    md = scratch(tmp_path, piece)
    m = load_markings(md / "rounds" / "tiny.yaml")
    [notes] = load_voices(m, md)
    assert [n.s for n in notes] == [0, 0.5 / 0.75, 1 / 0.75, 1.5 / 0.75] and notes[3].s == 2.0
    build_all(tmp_path / "out", markings_dir=md)
    assert pieces(tmp_path / "out")[0]["beatUnit"] == 0.75


def test_a_source_names_its_beat_once(tmp_path):
    piece = {k: v for k, v in TINY_PIECE.items() if k != "canon"}
    piece = dict(piece, voices=[{"name": "Solo", "texture": "solid"}],
                 source={"kind": "kern", "path": "tiny.krn", "beat_unit": 0.75,
                         "beats_per_quarter": 2},
                 fugue={"subject": {"voice": 0, "start": 0, "length": 2},
                        "entries": [{"voice": 0, "start": 0, "form": "subject"}]})
    md = scratch(tmp_path, piece)
    with pytest.raises(MarkingsError, match="beat_unit"):
        load_markings(md / "rounds" / "tiny.yaml")


def test_the_inventions_source_is_fetched():
    from fugue_prep.sources import fetch_inventions
    path = fetch_inventions()
    assert (path / "kern" / "inven01.krn").exists() and (path / "kern" / "sinfo15.krn").exists()


def test_the_musical_offering_source_is_fetched():
    from fugue_prep.sources import fetch_musical_offering
    path = fetch_musical_offering()
    assert path.name == "bach-musical-offering"
    assert (path / "kern" / "offering-001.krn").exists()  # Ricercar a 3
    assert (path / "kern" / "offering-002.krn").exists()  # Ricercar a 6


# --- inventions: motive/countermotive forms, and pieces that open with an upbeat ---

def _kern_piece(tmp_path, monkeypatch, **extra):
    import fugue_prep.build as build
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "tiny.krn").write_text(TINY_KERN)
    monkeypatch.setattr(build, "SOURCES", tmp_path / "src")
    piece = {k: v for k, v in TINY_PIECE.items() if k != "canon"}
    piece = dict(piece, beats_per_bar=3, voices=[{"name": "Solo", "texture": "solid"}],
                 source={"kind": "kern", "path": "tiny.krn", "beats_per_quarter": 2}, **extra)
    return scratch(tmp_path, piece)


def test_motive_and_countermotive_entries_are_labelled_so(tmp_path, monkeypatch):
    # c d e | f: the motive c-d (beats 0-2), the "countermotive" e-f (beats 2-4)
    md = _kern_piece(tmp_path, monkeypatch, fugue={
        "subject": {"voice": 0, "start": 0, "length": 2},
        "countersubject": {"voice": 0, "start": 2, "length": 2},
        "entries": [{"voice": 0, "start": 0, "form": "motive"},
                    {"voice": 0, "start": 2, "form": "countermotive"},
                    {"voice": 0, "start": 1, "form": "motive", "transform": "inverted"}]},
        captions=[{"at": 0, "text": "Motive."}])
    with pytest.raises(BuildError, match="bar 1"):  # d-e is not c-d inverted
        build_all(tmp_path / "out", markings_dir=md)
    m = yaml.safe_load((md / "rounds" / "tiny.yaml").read_text())
    m["fugue"]["entries"].pop()
    (md / "rounds" / "tiny.yaml").write_text(yaml.safe_dump(m, sort_keys=False))
    build_all(tmp_path / "out", markings_dir=md)
    marks = pieces(tmp_path / "out")[0]["marks"]
    assert [k["label"] for k in marks if k["kind"] == "entry"] == ["motive", "countermotive"]


def test_countermotive_entry_needs_a_countersubject_span(tmp_path, monkeypatch):
    md = _kern_piece(tmp_path, monkeypatch, fugue={
        "subject": {"voice": 0, "start": 0, "length": 2},
        "entries": [{"voice": 0, "start": 2, "form": "countermotive"}]})
    with pytest.raises(MarkingsError, match="countersubject"):
        load_markings(md / "rounds" / "tiny.yaml")


def test_a_pickup_shifts_bar_numbers(tmp_path, monkeypatch):
    """pickup: the upbeat's length in beats. Bar n starts at pickup + (n-1) * beats_per_bar,
    for captions given by bar, the bar count, and the piece JSON (the web numbers bars
    from it)."""
    md = _kern_piece(tmp_path, monkeypatch, pickup=1, fugue={
        "subject": {"voice": 0, "start": 0, "length": 2},
        "entries": [{"voice": 0, "start": 0, "form": "motive"}]},
        captions=[{"at": 0, "text": "Upbeat."}, {"bar": 2, "text": "Bar two."}])
    m = load_markings(md / "rounds" / "tiny.yaml")
    assert [c["at"] for c in m["captions"]] == [0, 4]
    build_all(tmp_path / "out", markings_dir=md)
    p = pieces(tmp_path / "out")[0]
    assert p["pickup"] == 1
    lib = json.loads((tmp_path / "out" / "library.json").read_text())
    # notes end at beat 6: the upbeat (0-1), bar 1 (1-4), and part of bar 2 (4-6)
    assert {s["id"]: s for s in lib["pieces"]}["tiny-tonos"]["bars"] == 2


def test_pickup_must_be_shorter_than_a_bar(tmp_path, monkeypatch):
    md = _kern_piece(tmp_path, monkeypatch, pickup=3, fugue={
        "subject": {"voice": 0, "start": 0, "length": 2},
        "entries": [{"voice": 0, "start": 0, "form": "motive"}]})
    with pytest.raises(MarkingsError, match="pickup"):
        load_markings(md / "rounds" / "tiny.yaml")


def test_pieces_without_an_upbeat_have_pickup_zero(built):
    # Invention 3 and Contrapunctus XIII (rectus and inversus) open with an upbeat
    upbeat = {"invention03", "contrapunctus13-rectus", "contrapunctus13-inversus"}
    assert all(p["pickup"] == 0 for p in pieces(built) if p["id"] not in upbeat)


def test_end_cuts_secondary_notes_too(tmp_path, monkeypatch):
    """Secondary notes join the voices before an 'end' cut: one sounding past the end is
    shortened, one starting after it is dropped."""
    import fugue_prep.build as build
    from fugue_prep.model import Note
    written = [[Note(0, 60, 0, 1), Note(0, 62, 1, 1), Note(0, 64, 2, 2),
                Note(0, 55, 2, 10, c=True), Note(0, 52, 11, 1, c=True)]]
    monkeypatch.setattr(build, "load_voices", lambda m, markings_dir=MARKINGS, secondary=False:
                        written if secondary else [[x for x in written[0] if not x.c]])
    trans = dict(TINY_TRANSCRIPTION, end=9.5)
    out = tmp_path / "out"
    build_all(out, markings_dir=scratch(tmp_path, json.loads(json.dumps(TINY_PIECE)), trans))
    notes = json.loads((out / "pieces" / "tiny-tonos.json").read_text())["notes"]
    sec = [(n["v"], n["p"], n["s"], n["d"]) for n in notes if n.get("c")]
    assert sec == [(0, 55, 2, 7.5)]
    assert all(n["s"] + n["d"] <= 9.5 for n in notes)


def test_head_entries_need_a_head_length(tmp_path):
    """part: head names how many opening notes the statement keeps (head_length >= 2);
    form_by: opening is the only alternative way to decide a form."""
    for extra, msg in (({"part": "head"}, "head_length"), ({"head_length": 4}, "part"),
                       ({"part": "head", "head_length": 1}, "head_length"),
                       ({"part": "tail", "head_length": 3}, "part"),
                       ({"form_by": "ear"}, "form_by")):
        bad = {k: v for k, v in TINY_PIECE.items() if k != "canon"}
        bad["fugue"] = {"subject": {"voice": 0, "start": 0, "length": 4},
                        "entries": [{"voice": 0, "start": 0, "form": "subject", **extra}]}
        with pytest.raises(MarkingsError, match=msg):
            load_markings_tree(tmp_path, bad)


def test_a_head_entry_is_labelled_and_spans_its_head(tmp_path):
    piece = {k: v for k, v in TINY_PIECE.items() if k != "canon"}
    piece["voices"] = piece["voices"][:1]
    piece["techniques"] = ["fugue"]
    piece["fugue"] = {"subject": {"voice": 0, "start": 0, "length": 2},
                      "entries": [{"voice": 0, "start": 0, "form": "subject"},
                                  {"voice": 0, "start": 2, "form": "answer", "part": "head",
                                   "head_length": 2}]}
    tr = {"source": "test", "voices": [[[60, 0, 1], [62, 1, 1], [67, 2, 1], [69, 3, 1],
                                        [50, 4, 2]]]}
    out = tmp_path / "out"
    build_all(out, markings_dir=scratch(tmp_path, piece, tr))
    p = json.loads((out / "pieces" / "tiny-tonos.json").read_text())
    marks = [(m["start"], m["end"], m["label"]) for m in p["marks"] if m["kind"] == "entry"]
    assert marks == [(0, 2, "subject"), (2, 4, "answer (head)")]


# --- a transcription that is a score: every voice written, followers matched ---

def test_a_score_transcription_matches_its_followers_section_by_section(tmp_path):
    """``score: true``: the transcription holds every voice (followers too), so the canon
    is matched like a score's, and may change its rule from one section to the next."""
    trans = {"source": "test", "voices": [
        [[72, 0, 1], [74, 1, 1], [76, 2, 1], [77, 3, 1], [79, 4, 1], [77, 5, 1]],
        [[60, 1, 1], [62, 2, 1], [64, 3, 1], [65, 4, 1], [69, 5, 1], [67, 6, 1]]]}
    piece = dict(TINY_PIECE, source={"kind": "transcription", "path": "transcriptions/tiny.yaml",
                                     "score": True}, canon=[
        {"span": [0, 4], "leader": 0, "followers": [
            {"voice": 1, "rule": {"delay": 1, "interval": -12}, "min_match": 1}]},
        {"span": [4, 6], "leader": 0, "followers": [
            {"voice": 1, "rule": {"delay": 1, "interval": -10}, "min_match": 1}]}])
    out = tmp_path / "out"
    build_all(out, markings_dir=scratch(tmp_path, piece, trans))
    p = json.loads((out / "pieces" / "tiny-tonos.json").read_text())
    notes = p["notes"]
    assert len(notes) == 12
    gaps = [notes[t["b"]]["p"] - notes[t["a"]]["p"] for t in p["threads"]]
    assert gaps == [-12, -12, -12, -12, -10, -10]
    assert all(not t["broken"] for t in p["threads"])


def test_a_score_transcription_is_checked(tmp_path):
    two = [{"span": [0, 4], "leader": 0, "followers": [{"voice": 1, "rule": {"delay": 1}}]},
           {"span": [4, 8], "leader": 0, "followers": [{"voice": 1, "rule": {"delay": 1}}]}]
    src = {"kind": "transcription", "path": "transcriptions/tiny.yaml", "score": True}
    m = load_markings_tree(tmp_path, dict(TINY_PIECE, source=src, canon=two))
    assert m["source"]["score"] is True and len(m["canon"]) == 2
    # a score already holds every pass: no per-tonos repeats
    with pytest.raises(MarkingsError, match="repeats"):
        load_markings_tree(tmp_path, dict(TINY_PIECE, source=src))
    # a score transcription must hold every piece voice
    with pytest.raises(BuildError, match="every"):
        build_all(tmp_path / "out", markings_dir=scratch(
            tmp_path, dict(TINY_PIECE, source=src, canon=two)))


# --- per-voice instruments and instrument ranges ---

def test_instrument_ranges_cover_every_ensemble_instrument():
    from fugue_prep.model import INSTRUMENT_RANGES
    assert {i for t in ENSEMBLE_INSTRUMENTS.values() for i in t} | {"viola"} == set(INSTRUMENT_RANGES)
    assert INSTRUMENT_RANGES["flute"] == (60, 96)        # C4-C7
    assert INSTRUMENT_RANGES["violin"] == (55, 105)      # G3-A7
    assert INSTRUMENT_RANGES["viola"] == (48, 88)        # C3-E6
    assert INSTRUMENT_RANGES["cello"] == (36, 81)        # C2-A5
    assert INSTRUMENT_RANGES["harpsichord"] == (29, 89)  # F1-F6
    assert INSTRUMENT_RANGES["organ"] == (36, 96)        # C2-C7


def test_a_voice_can_name_its_instrument(tmp_path):
    """``instrument`` on a voice overrides the ensemble's default for that voice only."""
    piece = json.loads(json.dumps(TINY_PIECE))
    piece["voices"][1]["instrument"] = "viola"  # the comes, 48-56: in the viola's range
    out = tmp_path / "out"
    build_all(out, markings_dir=scratch(tmp_path, piece))
    p = json.loads((out / "pieces" / "tiny-tonos.json").read_text())
    assert [v["instrument"] for v in p["voices"]] == ["harpsichord", "viola"]


def test_unknown_instrument_is_reported(tmp_path):
    piece = json.loads(json.dumps(TINY_PIECE))
    piece["voices"][0]["instrument"] = "lute"
    with pytest.raises(MarkingsError, match=r"voices\[0\]\.instrument"):
        load_markings_tree(tmp_path, piece)


def test_a_voice_out_of_its_instruments_range_fails_the_build(tmp_path):
    """Chamber, 2 voices = flute + violin; the comes an octave below the dux (48-56) is
    below the violin's G3."""
    piece = json.loads(json.dumps(TINY_PIECE))
    del piece["voices"][1]["instrument"]
    with pytest.raises(BuildError, match=r"tiny-tonos: voice 1 \(Comes\) on violin: "
                                         r"lowest 48, highest 56, outside its range 55-105"):
        build_all(tmp_path / "out", markings_dir=scratch(tmp_path, piece))


def test_build_writes_the_glossary(built):
    g = json.loads((built / "glossary.json").read_text())
    lib = json.loads((built / "library.json").read_text())
    assert set(g["techniques"]) == set(lib["techniques"])


def test_an_editorial_ending_is_not_a_free_passage(tmp_path):
    from fugue_prep.build import free_passage_pieces, load_ending
    src = MARKINGS.parent
    mk = tmp_path / "markings"
    shutil.copytree(src / "markings", mk)
    shutil.copytree(src / "transcriptions", tmp_path / "transcriptions")
    assert "bwv1079-quaerendo" not in free_passage_pieces(mk)
    t = tmp_path / "transcriptions" / "bwv1079-quaerendo.yaml"
    raw = yaml.safe_load(t.read_text())
    assert raw["editorial"] is True
    end, coda = load_ending(load_markings(mk / "musical-offering" / "quaerendo.yaml"), mk)
    assert end == 160 and coda  # still played: only the glossary leaves it out
    raw["editorial"] = False
    t.write_text(yaml.safe_dump(raw))
    assert "bwv1079-quaerendo" in free_passage_pieces(mk)


# --- glossary notes: an "In this piece" line on a definition card ---

def test_glossary_notes_go_into_the_piece(tmp_path):
    out = tmp_path / "out"
    piece = {**TINY_PIECE, "glossary_notes": {"per-tonos": "Each pass a tone higher."}}
    build_all(out, markings_dir=scratch(tmp_path, piece))
    p = json.loads((out / "pieces" / "tiny-tonos.json").read_text())
    assert p["glossaryNotes"] == {"per-tonos": "Each pass a tone higher."}
    assert validate_piece(p) == []


def test_a_piece_without_glossary_notes_has_none(built):
    p = json.loads((built / "pieces" / "bwv847.json").read_text())
    assert "glossaryNotes" not in p


def test_glossary_notes_name_glossary_entries(tmp_path):
    piece = {**TINY_PIECE, "glossary_notes": {"hocket": "Not an entry."}}
    with pytest.raises(BuildError, match="hocket"):
        build_all(tmp_path / "out", markings_dir=scratch(tmp_path, piece))


def test_glossary_notes_are_text(tmp_path):
    for bad in ({"per-tonos": 3}, {"per-tonos": ""}, ["per-tonos"]):
        with pytest.raises(MarkingsError, match="glossary_notes"):
            load_markings_tree(tmp_path, {**TINY_PIECE, "glossary_notes": bad})


# --- ref: answer: a varied answer matched against the first answer, not the subject ---

def _ref_piece(entries):
    piece = {k: v for k, v in TINY_PIECE.items() if k != "canon"}
    piece["voices"] = piece["voices"][:1]
    piece["techniques"] = ["fugue"]
    piece["fugue"] = {"subject": {"voice": 0, "start": 0, "length": 4}, "entries": entries}
    return piece


def test_ref_answer_is_checked(tmp_path):
    """ref: answer only on an answer, and only where a plain first answer exists (whole,
    fixed head and tail, untransformed, itself matched against the subject)."""
    s = {"voice": 0, "start": 0, "form": "subject"}
    a = {"voice": 0, "start": 4, "form": "answer"}
    for entries, msg in (([s, {**a, "ref": "countersubject"}], "ref"),
                         ([s, {**s, "start": 8, "ref": "answer"}, a], "ref"),
                         ([s, {**a, "ref": "answer"}], "first answer"),
                         ([s, {**a, "tail": "free"}, {**a, "start": 8, "ref": "answer"}],
                          "first answer")):
        with pytest.raises(MarkingsError, match=msg):
            load_markings_tree(tmp_path, _ref_piece(entries))
    m = load_markings_tree(tmp_path, _ref_piece([s, a, {**a, "start": 8, "ref": "answer"}]))
    assert [e["ref"] for e in m["fugue"]["entries"]] == ["subject", "subject", "answer"]


def test_a_ref_answer_entry_matches_the_first_answer(tmp_path):
    """Subject C D E F G A (+2 +2 +1 +2 +2); answer G A B C D F (last interval +3, as a
    tonal answer may change one); a varied answer ending G A B C D G (+5) is 3 semitones
    off the subject's last interval but 2 off the answer's: found only with ref: answer."""
    subj = [[p, i, 1] for i, p in enumerate([60, 62, 64, 65, 67, 69])]
    ans = [[p, 6 + i, 1] for i, p in enumerate([67, 69, 71, 72, 74, 77])]
    var = [[p, 12 + i, 1] for i, p in enumerate([67, 69, 71, 72, 74, 79])]
    tr = {"source": "test", "voices": [subj + ans + var]}
    s = {"voice": 0, "start": 0, "form": "subject"}
    a = {"voice": 0, "start": 6, "form": "answer"}
    piece = _ref_piece([s, a, {**a, "start": 12}])
    piece["fugue"]["subject"]["length"] = 6
    with pytest.raises(BuildError, match="no none entry in voice 0 at beat 12"):
        build_all(tmp_path / "o1", markings_dir=scratch(tmp_path, piece, tr))
    piece["fugue"]["entries"][2]["ref"] = "answer"
    out = tmp_path / "o2"
    build_all(out, markings_dir=scratch(tmp_path, piece, tr))
    p = json.loads((out / "pieces" / "tiny-tonos.json").read_text())
    marks = [(m["start"], m["end"], m["label"]) for m in p["marks"] if m["kind"] == "entry"]
    assert marks == [(0, 6, "subject"), (6, 12, "answer"), (12, 18, "answer")]


def test_several_subjects_are_checked(tmp_path):
    """A double/triple fugue gives ``subjects`` (ids I, II, ... in order) instead of
    ``subject``; each subject or answer entry names its subject, and only then."""
    base = {k: v for k, v in TINY_PIECE.items() if k != "canon"}
    two = [{"id": "I", "voice": 0, "start": 0, "length": 2},
           {"id": "II", "voice": 0, "start": 2, "length": 2}]
    ok = dict(base, fugue={"subjects": two, "entries": [
        {"voice": 0, "start": 0, "form": "subject", "subject": "I"},
        {"voice": 0, "start": 2, "form": "subject", "subject": "II"}]})
    m = load_markings_tree(tmp_path, ok)
    assert list(m["fugue"]["subjects"]) == ["I", "II"]
    assert m["fugue"]["subject"] == m["fugue"]["subjects"]["I"]
    assert [e["subject"] for e in m["fugue"]["entries"]] == ["I", "II"]
    cases = [
        ({"subjects": two, "subject": two[0], "entries": ok["fugue"]["entries"]}, "exactly one"),
        ({"subjects": [two[1], two[0]], "entries": ok["fugue"]["entries"]}, "expected 'I'"),
        ({"subjects": two[:1], "entries": ok["fugue"]["entries"]}, "two to four"),
        ({"subjects": two, "entries": [{"voice": 0, "start": 0, "form": "subject"}]},
         "say which subject"),
        ({"subjects": two, "entries": [{"voice": 0, "start": 0, "form": "subject",
                                        "subject": "III"}]}, "'III' is not one of"),
        ({"subject": two[0] | {}, "entries": [{"voice": 0, "start": 0, "form": "subject",
                                                "subject": "I"}]}, "only a fugue with"),
    ]
    for fugue, msg in cases:
        if "subject" in fugue and isinstance(fugue["subject"], dict):
            fugue["subject"] = {k: v for k, v in fugue["subject"].items() if k != "id"}
        with pytest.raises(MarkingsError, match=msg):
            load_markings_tree(tmp_path, dict(base, fugue=fugue))


def test_head_short_is_the_only_new_head(tmp_path):
    base = {k: v for k, v in TINY_PIECE.items() if k != "canon"}
    for head, good in (("short", True), ("free", True), ("half", False)):
        piece = dict(base, fugue={"subject": {"voice": 0, "start": 0, "length": 4}, "entries": [
            {"voice": 0, "start": 0, "form": "subject", "head": head}]})
        if good:
            assert load_markings_tree(tmp_path, piece)["fugue"]["entries"][0]["head"] == head
        else:
            with pytest.raises(MarkingsError, match="head"):
                load_markings_tree(tmp_path, piece)


def test_entry_labels_name_their_subject(tmp_path):
    """Labels: "subject II", "answer I inverted"; a one-subject fugue keeps "subject"."""
    from fugue_prep.build import build_piece
    trans = {"source": "test", "voices": [[[60, 0, 1], [62, 1, 1], [67, 2, 1], [65, 3, 1],
                                           [60, 4, 1], [58, 5, 1], [67, 6, 1], [69, 7, 1]]]}
    base = {k: v for k, v in TINY_PIECE.items() if k != "canon"}
    base["voices"] = base["voices"][:1]
    piece = dict(base, fugue={"subjects": [{"id": "I", "voice": 0, "start": 0, "length": 2},
                                           {"id": "II", "voice": 0, "start": 2, "length": 2}],
                              "entries": [
        {"voice": 0, "start": 0, "form": "subject", "subject": "I"},
        {"voice": 0, "start": 2, "form": "subject", "subject": "II"},
        {"voice": 0, "start": 4, "form": "answer", "subject": "I", "transform": "inverted"}]})
    root = scratch(tmp_path, piece, trans)
    m = load_markings(next(root.glob("*/*.yaml")))
    p = build_piece(m, "rounds", root)
    assert [k["label"] for k in p["marks"] if k["kind"] == "entry"] == [
        "subject I", "subject II", "answer I inverted"]
