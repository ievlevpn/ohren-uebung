import pytest

from fugue_prep.canon import Rule, match
from fugue_prep.lily import fetch_mutopia, render_voices
from fugue_prep.midi import read_midi

THRESHOLD = 0.90


@pytest.fixture(scope="module")
def var3():
    return read_midi(render_voices(fetch_mutopia("BachJS/BWV988/bwv-988-v03")))


@pytest.fixture(scope="module")
def var15():
    return read_midi(render_voices(fetch_mutopia("BachJS/BWV988/bwv-988-v15")))


def leader_follower(voices):
    """The two canonic voices: the two whose first onsets are earliest among the upper
    pair — by construction in these scores, the bass is the lowest voice."""
    upper = sorted(voices[:2], key=lambda v: v[0].s)
    return upper[0], upper[1]


def unbroken(leader, follower, rule):
    threads = match(leader, follower, rule)
    return sum(not t.broken for t in threads) / len(threads)


def test_var3_has_three_voices(var3):
    assert len(var3) == 3
    assert [n.v for n in var3[2][:1]] == [2]  # voice index follows top-first order


def test_var3_upper_voices_are_a_canon_at_the_unison_one_bar_apart(var3):
    leader, follower = leader_follower(var3)
    assert follower[0].s - leader[0].s == 6  # one bar of 12/8 = 6 quarter beats
    # free: leader notes in the last bar of each half (beats 42-48, 90-96), whose
    # imitation would fall after the half's double bar - the follower cadences instead.
    rule = Rule(6, 0, False, "G", None, False, 1, 0, 1, free=((42, 48), (90, 96)))
    assert unbroken(leader, follower, rule) >= THRESHOLD


def test_var15_has_three_voices(var15):
    assert len(var15) == 3


def test_var15_upper_voices_are_a_canon_at_the_fifth_inverted(var15):
    leader, follower = leader_follower(var15)
    assert follower[0].s - leader[0].s == 2  # one bar of 2/4
    assert (leader[0].p, follower[0].p) == (67, 74)  # g' answered by d'' (a fifth up)
    rule = Rule(2, 4, True, "g", 67, False, 1, 0, 1,
                free=((30, 32), (62, 64)), pitch_tolerance=1)  # Bach's +-1 chromatic adjustments; last beats of each half: image falls past the double bar
    # axis g', answer 4 scale steps up
    assert unbroken(leader, follower, rule) >= THRESHOLD


# --- patch_source / read_midi units -------------------------------------------------
import shutil
import subprocess

import mido

from fugue_prep.lily import MIDI_CONTEXT, patch_source


def test_patch_source_handles_a_midi_block_with_nested_braces():
    ly = r'\score { { c4 } \midi { \context { \Score tempoWholesPerMinute = #(ly:make-moment 66 4) } } }'
    out = patch_source(ly)
    assert MIDI_CONTEXT in out
    assert "tempoWholesPerMinute" in out  # the original context is kept


def test_patch_source_drops_legacy_tempo_and_adds_missing_midi():
    assert r"\tempo" not in patch_source(r"\score { { c4 } \midi { \tempo 8 = 66 } }")
    assert MIDI_CONTEXT in patch_source(r"\score { { c4 } }")


def test_change_staff_both_spellings_removed():
    out = patch_source('\\score { { \\change Staff = "up" c4 \\change Staff = #"down" d4 '
                       '\\change Staff = lower e4 } \\midi { } }')
    assert "change" not in out


def test_two_voices_on_one_staff_give_two_voices(tmp_path):
    if not shutil.which("lilypond"):
        pytest.skip("lilypond missing")
    ly = tmp_path / "two.ly"
    ly.write_text('\\version "2.24.0"\n\\score { \\new Staff << { c\'4 d\'4 e\'4 f\'4 } \\\\ { c4 d4 e4 f4 } >> '
                  '\\midi { \\context { \\Score tempoWholesPerMinute = #(ly:make-moment 90 4) } } }\n')
    voices = read_midi(render_voices(ly))
    assert len(voices) == 2


def _synthetic_midi(tmp_path, events):
    mid = mido.MidiFile(ticks_per_beat=480)
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    last = 0
    for t, kind, note in events:
        tr.append(mido.Message(kind, channel=0, note=note, velocity=64, time=t - last))
        last = t
    path = tmp_path / "s.mid"
    mid.save(str(path))
    return path


def test_read_midi_cuts_a_restruck_note_at_the_new_onset(tmp_path):
    path = _synthetic_midi(tmp_path, [(0, "note_on", 60), (480, "note_on", 60), (960, "note_off", 60)])
    (voice,) = read_midi(path)
    assert [(n.p, n.s, n.d) for n in voice] == [(60, 0.0, 1.0), (60, 1.0, 1.0)]


def test_read_midi_keeps_tracks_apart_on_the_same_channel(tmp_path):
    # old Mutopia scores (no explicit Voice contexts): one track per staff, all on channel 0
    mid = mido.MidiFile(ticks_per_beat=480)
    for note in (72, 48):
        tr = mido.MidiTrack()
        tr.append(mido.Message("note_on", channel=0, note=note, velocity=64, time=0))
        tr.append(mido.Message("note_off", channel=0, note=note, velocity=0, time=480))
        mid.tracks.append(tr)
    path = tmp_path / "two.mid"
    mid.save(str(path))
    voices = read_midi(path)
    assert [[n.p for n in v] for v in voices] == [[72], [48]]


def test_render_voices_finds_included_files_next_to_the_score(tmp_path):
    # multi-file Mutopia sources (<name>-lys.zip) \include their voices
    if not shutil.which("lilypond"):
        pytest.skip("lilypond missing")
    (tmp_path / "upper.ily").write_text("upper = { c''4 d''4 }\n")
    ly = tmp_path / "main.ly"
    ly.write_text('\\version "2.24.0"\n\\include "upper.ily"\n'
                  '\\score { \\new Staff << \\upper \\\\ { c4 d4 } >> \\midi { } }\n')
    voices = read_midi(render_voices(ly))
    assert [[n.p for n in v] for v in voices] == [[72, 74], [48, 50]]


# --- first/second endings -----------------------------------------------------------
ENDINGS = ("\\version \"2.24.0\"\n"
           "mus = \\relative c' { \\repeat volta 2 { c4 d } % a { brace in a comment\n"
           "  \\alternative { { e4 g' } { f4 } } g4 }\n"
           "\\score { \\mus \\midi { } }\n")


def test_patch_source_tags_every_ending_but_the_last_and_removes_them_in_the_score():
    out = patch_source(ENDINGS)
    assert out.count("\\tag #'fugueEarlierEnding") == 1
    assert "\\tag #'fugueEarlierEnding { e4 g' }" in out
    assert "\\removeWithTag #'fugueEarlierEnding" in out


def test_only_the_last_ending_sounds_with_its_relative_pitches_kept(tmp_path):
    # \relative runs through the first ending into the second (f after g'' is f''), so the
    # first ending is removed after \relative has fixed the pitches, not deleted as text.
    if not shutil.which("lilypond"):
        pytest.skip("lilypond missing")
    ly = tmp_path / "endings.ly"
    ly.write_text(ENDINGS)
    (voice,) = read_midi(render_voices(ly))
    assert [(n.p, n.s) for n in voice] == [(60, 0.0), (62, 1.0), (77, 2.0), (79, 3.0)]


def test_patch_source_leaves_scores_without_endings_alone():
    assert "removeWithTag" not in patch_source(r"\score { \repeat volta 2 { c4 } \midi { } }")
