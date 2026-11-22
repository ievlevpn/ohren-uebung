import copy
import json
from pathlib import Path

from fugue_prep.validate import validate_piece

FIXTURE = Path(__file__).parent / "fixtures" / "tiny_piece.json"


def load() -> dict:
    return copy.deepcopy(json.loads(FIXTURE.read_text()))


def test_tiny_piece_is_valid():
    assert validate_piece(load()) == []


def test_thread_to_missing_note_is_reported():
    p = load()
    p["threads"][0]["b"] = 99
    assert "tiny: thread 0 → note 99 does not exist" in validate_piece(p)


def test_notes_must_be_sorted_by_start():
    p = load()
    p["notes"][0], p["notes"][7] = p["notes"][7], p["notes"][0]
    problems = validate_piece(p)
    assert any("not sorted by start" in m and m.startswith("tiny: bar ") for m in problems)


def test_caption_beyond_the_end_is_reported():
    p = load()
    p["captions"].append({"at": 50, "text": "late"})
    problems = validate_piece(p)
    assert any("caption at 50" in m and "beyond the end" in m and m.startswith("tiny: bar 13") for m in problems)


def test_unknown_ensemble_is_reported():
    p = load()
    p["ensemble"] = "kazoo"
    assert any("unknown ensemble 'kazoo'" in m for m in validate_piece(p))


def test_bar_numbers_count_from_the_end_of_the_upbeat():
    p = load()
    p["pickup"] = 2
    p["captions"].append({"at": 50, "text": "late"})
    # beat 50 with a 2-beat upbeat and 4 beats a bar: (50 - 2) / 4 + 1 = bar 13
    assert any(m.startswith("tiny: bar 13: caption at 50") for m in validate_piece(p))
    p["pickup"] = 3
    assert any(m.startswith("tiny: bar 12: caption at 50") for m in validate_piece(p))
