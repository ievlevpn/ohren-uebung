import pytest

from fugue_prep.build import MARKINGS, load_voices
from fugue_prep.fugue import EntryMismatch, entry_reference, find_entry, first_answer, subject_notes
from fugue_prep.markings import load_markings
from fugue_prep.model import Note

BWV847 = MARKINGS / "wtc" / "bwv847.yaml"


@pytest.fixture(scope="module")
def bwv847():
    m = load_markings(BWV847)
    return m, load_voices(m, MARKINGS)


def test_subject_of_bwv847_is_found_at_its_8_entries(bwv847):
    m, voices = bwv847
    subject = subject_notes(voices, m["fugue"]["subject"])
    assert [n.p for n in subject[:5]] == [72, 71, 72, 67, 68]
    entries = [e for e in m["fugue"]["entries"] if e["form"] != "countersubject"]
    assert len(entries) == 8
    bars = []
    for e in entries:
        idx = find_entry(voices, subject, e["voice"], e["start"], e["transform"],
                         piece=m["id"], beats_per_bar=m["beats_per_bar"])
        assert len(idx) == len(subject)
        assert voices[e["voice"]][idx[0]].s == e["start"]
        bars.append(int(e["start"] // 4) + 1)
    assert bars == [1, 3, 7, 11, 15, 20, 26, 29]


def test_misplaced_entry_is_reported(bwv847):
    m, voices = bwv847
    subject = subject_notes(voices, m["fugue"]["subject"])
    # the answer enters in the soprano at beat 8.5 (bar 3); one beat late is wrong
    with pytest.raises(EntryMismatch, match="bwv847: bar 3"):
        find_entry(voices, subject, 0, 9.5, "none", piece="bwv847", beats_per_bar=4)


SUBJECT = [Note(0, 60, 0, 1), Note(0, 62, 1, 1), Note(0, 63, 2, 0.5), Note(0, 65, 2.5, 0.5),
           Note(0, 67, 3, 2)]


def test_inverted_entry_is_found():
    # the subject mirrored (G F Eb... downwards) in voice 1 at beat 8, with one free
    # note before it
    inv = [Note(1, 67, 7, 1)] + [Note(1, 67 - (n.p - 60), 8 + n.s, n.d) for n in SUBJECT]
    voices = [SUBJECT, inv]
    assert find_entry(voices, SUBJECT, 1, 8, "inverted") == [1, 2, 3, 4, 5]
    with pytest.raises(EntryMismatch):
        find_entry(voices, SUBJECT, 1, 8, "none")


def test_augmented_and_diminished_entries_are_found():
    aug = [Note(1, n.p - 12, 10 + 2 * n.s, 2 * n.d) for n in SUBJECT]
    dim = [Note(1, n.p + 7, 30 + n.s / 2, n.d / 2) for n in SUBJECT]
    voices = [SUBJECT, aug + dim]
    assert find_entry(voices, SUBJECT, 1, 10, "augmented") == [0, 1, 2, 3, 4]
    assert find_entry(voices, SUBJECT, 1, 30, "diminished") == [5, 6, 7, 8, 9]


def test_interval_off_by_more_than_two_semitones_is_not_an_entry():
    answer = [Note(1, p, 4 + n.s, n.d) for p, n in zip([67, 72, 74, 75, 77], SUBJECT)]
    voices = [SUBJECT, answer]
    # 60→62 answered 67→72: off by 3 semitones → not an entry
    with pytest.raises(EntryMismatch, match="voice 1"):
        find_entry(voices, SUBJECT, 1, 4, "none")


def test_inverted_diminished_and_augmented_entries_are_found():
    # Contrapunctus VI-VII: the subject inverted and in diminution (or augmentation) at once
    inv_dim = [Note(1, 79 - (n.p - 60), 20 + n.s / 2, n.d / 2) for n in SUBJECT]
    inv_aug = [Note(1, 55 - (n.p - 60), 40 + 2 * n.s, 2 * n.d) for n in SUBJECT]
    voices = [SUBJECT, inv_dim + inv_aug]
    assert find_entry(voices, SUBJECT, 1, 20, "inverted diminished") == [0, 1, 2, 3, 4]
    assert find_entry(voices, SUBJECT, 1, 40, "inverted augmented") == [5, 6, 7, 8, 9]
    with pytest.raises(EntryMismatch):
        find_entry(voices, SUBJECT, 1, 20, "diminished")


def test_a_diatonic_inversion_is_found_although_its_semitones_differ():
    # Art of Fugue head D A F D C# D E F, inverted diatonically in D minor (D<->A axis):
    # A D F A Bb A G F; whole and half steps trade places, so few intervals are equal in
    # semitones, but each is within one
    head = [Note(0, p, 2 * i, 2) for i, p in enumerate([62, 69, 65, 62, 61, 62, 64, 65])]
    inv = [Note(1, p, 20 + 2 * i, 2) for i, p in enumerate([69, 62, 65, 69, 70, 69, 67, 65])]
    assert find_entry([head, inv], head, 1, 20, "inverted") == list(range(8))


def test_a_motive_on_another_scale_degree_is_found():
    # Invention 1: the motive C D E F D E C in a sequence a third higher (bar 16, E F G A
    # F G E): a diatonic transposition trades whole and half steps, so the semitones
    # differ, but every interval keeps its size in scale steps (a second stays a second)
    motive = [Note(0, p, 0.25 * i, 0.25) for i, p in enumerate([60, 62, 64, 65, 62, 64, 60])]
    seq = [Note(1, p, 4 + 0.25 * i, 0.25) for i, p in enumerate([64, 65, 67, 69, 65, 67, 64])]
    assert find_entry([motive, seq], motive, 1, 4) == list(range(7))


def test_an_inversion_that_turns_seconds_into_thirds_is_not_an_entry():
    # the mirror of C D E F D E C is C Bb Ab G Bb Ab C; a line that answers its steps
    # with thirds (one semitone off each) is not the motive inverted
    motive = [Note(0, p, 0.25 * i, 0.25) for i, p in enumerate([60, 62, 64, 65, 62, 64, 60])]
    wrong = [Note(1, p, 4 + 0.25 * i, 0.25) for i, p in enumerate([72, 69, 66, 64, 67, 64, 68])]
    with pytest.raises(EntryMismatch):
        find_entry([motive, wrong], motive, 1, 4, "inverted")


def test_a_missing_entry_names_the_bar_after_an_upbeat():
    # 3 beats a bar after a one-beat upbeat: beat 4 is in bar 2 (bar 1 is beats 1-4)
    motive = [Note(0, 60, 0, 1), Note(0, 62, 1, 1)]
    with pytest.raises(EntryMismatch, match="bar 2:"):
        find_entry([motive], motive, 0, 4.5, beats_per_bar=3, pickup=1)


def test_head_free_matches_from_the_second_note():
    """head: free — the first note may be held longer (or replaced by a held-over note of
    another pitch): its duration and its interval to note 2 are not compared; notes 2..n
    are matched at their onsets relative to note 2, the next note after the first."""
    held = [Note(0, 58, 10, 1.5)] + [Note(0, n.p, 10.5 + n.s, n.d) for n in SUBJECT[1:]]
    voices = [held]
    with pytest.raises(EntryMismatch):
        find_entry(voices, SUBJECT, 0, 10)
    assert find_entry(voices, SUBJECT, 0, 10, head="free") == [0, 1, 2, 3, 4]


def test_tail_free_lets_the_last_note_come_late_and_turn_elsewhere():
    """tail: free — the mirror of head: free: the last note is the next note after the
    second-last (held longer here, a suspension), and its interval is not compared."""
    late = [Note(0, n.p, n.s, n.d) for n in SUBJECT[:-2]] + [Note(0, 65, 2.5, 1.25),
                                                              Note(0, 58, 3.75, 2)]
    voices = [late]
    with pytest.raises(EntryMismatch, match="no note at beat 3"):
        find_entry(voices, SUBJECT, 0, 0)
    assert find_entry(voices, SUBJECT, 0, 0, tail="free") == [0, 1, 2, 3, 4]
    with pytest.raises(EntryMismatch, match="no note after"):
        find_entry([late[:-1]], SUBJECT, 0, 0, tail="free")


def test_head_free_is_capped_at_the_first_notes_length():
    """head: free holds the first note at most twice as long: note 2 may come late by no
    more than the subject's first note (expected onset + that duration); a later note is
    not the subject's note 2, and the entry is not there."""
    def held(extra):
        return [Note(0, 58, 10, 1 + extra)] + [Note(0, n.p, 10 + extra + n.s, n.d)
                                                for n in SUBJECT[1:]]
    assert find_entry([held(1)], SUBJECT, 0, 10, head="free") == [0, 1, 2, 3, 4]
    with pytest.raises(EntryMismatch, match="note 2 comes .* late"):
        find_entry([held(1.5)], SUBJECT, 0, 10, head="free")


def test_tail_free_is_capped_at_the_last_notes_length():
    """tail: free lets the last note come late by at most the subject's last note's
    length (expected onset + that duration); a note any later is not the subject's end."""
    def late(extra):
        return [Note(0, n.p, n.s, n.d) for n in SUBJECT[:-2]] + [
            Note(0, 65, 2.5, 0.5 + extra), Note(0, 58, 3 + extra, 2)]
    assert find_entry([late(2)], SUBJECT, 0, 0, tail="free") == [0, 1, 2, 3, 4]
    with pytest.raises(EntryMismatch, match="last note comes .* late"):
        find_entry([late(2.5)], SUBJECT, 0, 0, tail="free")


def test_head_free_takes_a_note_held_over_from_before():
    """head: free — the first note may be tied over from before the statement's place
    (BWV 852 bar 11: an E-flat from beat 4.5 of bar 10 into the downbeat): at ``start``
    a note sounds that began earlier; notes 2..n keep their places from ``start``."""
    tied = [Note(0, 58, 9.5, 0.75)] + [Note(0, n.p, 10 + n.s, n.d) for n in SUBJECT[1:]]
    assert find_entry([tied], SUBJECT, 0, 10, head="free") == [0, 1, 2, 3, 4]
    with pytest.raises(EntryMismatch, match="no note at beat 10"):
        find_entry([tied], SUBJECT, 0, 10)


def test_head_length_matches_only_the_opening_notes():
    """part: head — a statement that keeps only the subject's opening ``head_length`` notes
    and then goes its own way is found by those notes alone."""
    head = [Note(0, n.p, 10 + n.s, n.d) for n in SUBJECT[:3]] + [Note(0, 50, 12.5, 0.5),
                                                                 Note(0, 40, 13, 2)]
    with pytest.raises(EntryMismatch):
        find_entry([head], SUBJECT, 0, 10)
    assert find_entry([head], SUBJECT, 0, 10, head_length=3) == [0, 1, 2]
    with pytest.raises(ValueError, match="head_length"):
        find_entry([head], SUBJECT, 0, 10, head_length=1)


def test_head_free_does_not_bound_an_early_note_2():
    """head: free has no early bound for note 2, on purpose: for a legato subject note 2
    always follows the first note, and where the first note is followed by a rest Bach may
    shorten it (BWV 864 bar 31: the head D enters two eighths late, the subject's three
    eighths' rest shrinks to one, and note 2 keeps its place). Note 2 is still the next
    note after the first: the late bound and the intervals do the checking."""
    gapped = [Note(0, 69, 0, 1), Note(0, 68, 4, 1), Note(0, 73, 5, 1), Note(0, 69, 6, 1)]
    late_head = [Note(0, 62, 12, 2), Note(0, 61, 14, 1), Note(0, 66, 15, 1), Note(0, 62, 16, 1)]
    assert find_entry([late_head], gapped, 0, 12, head="free") == [0, 1, 2, 3]
    with pytest.raises(EntryMismatch):
        find_entry([late_head], gapped, 0, 12)


def _fa_fugue():
    subj = [Note(0, p, float(i), 1.0) for i, p in enumerate([60, 62, 64])]
    ans = [Note(0, p, 10.0 + i, 1.0) for i, p in enumerate([67, 69, 71])]
    voices = [subj + ans]
    fugue = {"subject": {"voice": 0, "start": 0, "length": 3},
             "entries": [{"voice": 0, "start": 10, "form": "answer"},
                         {"voice": 0, "start": 5, "form": "answer"},
                         {"voice": 0, "start": 0, "form": "subject"}]}
    return voices, fugue


def test_first_answer_is_the_earliest_by_start_not_list_order():
    _, fugue = _fa_fugue()
    assert first_answer(fugue)["start"] == 5


def test_entry_reference_errors_name_the_piece_and_bar():
    voices, fugue = _fa_fugue()
    fugue["entries"][1]["start"] = 7  # no answer there: the earliest is the broken one
    e = {"voice": 0, "start": 10, "form": "subject", "ref": "answer"}
    with pytest.raises(EntryMismatch, match=r"tiny: bar 4:"):
        entry_reference(voices, fugue, e, piece="tiny", beats_per_bar=2, pickup=1)


def test_head_short_matches_a_half_note_for_the_whole():
    """BWV 849: subject I opens with a whole note, most later statements with a half note;
    head: short places notes 2..n that half-length earlier, and compares every interval."""
    subj = [Note(0, 61, 0, 2), Note(0, 60, 2, 1), Note(0, 64, 3, 1), Note(0, 63, 4, 2)]
    short = [Note(1, 68, 10, 1), Note(1, 67, 11, 1), Note(1, 71, 12, 1), Note(1, 70, 13, 2)]
    voices = [subj, short]
    assert find_entry(voices, subj, 1, 10, head="short") == [0, 1, 2, 3]
    with pytest.raises(EntryMismatch):
        find_entry(voices, subj, 1, 10)  # not without head: short
    wrong = [Note(1, 68, 10, 1), Note(1, 64, 11, 1), Note(1, 71, 12, 1), Note(1, 70, 13, 2)]
    with pytest.raises(EntryMismatch, match="interval 1"):
        find_entry([subj, wrong], subj, 1, 10, head="short")  # the first interval counts
    with pytest.raises(ValueError):
        find_entry(voices, subj, 1, 10, head="half")


def test_entries_of_several_subjects_are_matched_against_their_own():
    from fugue_prep.fugue import subject_spec
    m = load_markings(MARKINGS / "wtc" / "bwv849.yaml")
    voices = load_voices(m, MARKINGS)
    f = m["fugue"]
    for e in f["entries"]:
        ref = entry_reference(voices, f, e)
        assert ref == subject_notes(voices, f["subjects"][e["subject"]])
        assert subject_spec(f, e) is f["subjects"][e["subject"]]
    assert [first_answer(f, k)["start"] for k in ("I", "II", "III")] == [6, 96, 118.5]
    assert first_answer(f) is None  # every entry names its subject
