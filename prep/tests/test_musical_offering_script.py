"""The one-off extraction script's MIDI reading (scripts/musical_offering.py)."""
import sys
from pathlib import Path

import mido

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from musical_offering import tracks  # noqa: E402


def test_overlapping_notes_of_one_pitch_are_both_kept(tmp_path):
    """Two hands on one channel: c' held for two beats, struck again by the other hand
    after one beat, both released in turn (first on, first off) -> two notes."""
    mid = mido.MidiFile(ticks_per_beat=480)
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    tr.append(mido.Message("note_on", note=60, velocity=80, time=0))
    tr.append(mido.Message("note_on", note=60, velocity=80, time=480))
    tr.append(mido.Message("note_off", note=60, velocity=0, time=480))   # the first: 0-2
    tr.append(mido.Message("note_off", note=60, velocity=0, time=480))   # the second: 1-3
    path = tmp_path / "two.mid"
    mid.save(str(path))
    (notes,) = tracks(path)
    assert [(p, s) for p, s, _ in notes] == [(60, 0), (60, 1)]
