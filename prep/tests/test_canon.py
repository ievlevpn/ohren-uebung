from fugue_prep.canon import Rule, derive, expand_leader, match
from fugue_prep.model import Note


def rule(**kw) -> Rule:
    base = dict(delay=0.0, interval=0, diatonic=False, key="C", invert_about=None,
                retrograde=False, stretch=1.0, per_tonos_step=0, repeats=1, exceptions={})
    base.update(kw)
    return Rule(**base)


def line(pitches, durs, start=0.0, v=0):
    notes, s = [], start
    for p, d in zip(pitches, durs):
        notes.append(Note(v, p, s, d))
        s += d
    return notes


# Frere Jacques, F major, 4/4, 8 bars (each pair of bars repeats).
_FJ = [
    ([65, 67, 69, 65], [1, 1, 1, 1]),               # Frè-re Jac-ques
    ([69, 70, 72], [1, 1, 2]),                      # dor-mez vous
    ([72, 74, 72, 70, 69, 65], [.5, .5, .5, .5, 1, 1]),  # son-nez les ma-ti-nes
    ([65, 60, 65], [1, 1, 2]),                      # ding dang dong
]
FJ_P = [p for ps, _ in _FJ for p in ps + ps]
FJ_D = [d for _, ds in _FJ for d in ds + ds]
FRERE_JACQUES = line(FJ_P, FJ_D)


def test_frere_jacques_is_eight_bars():
    assert sum(FJ_D) == 32


def test_round_at_the_unison():
    follower, threads = derive(FRERE_JACQUES, rule(delay=8.0, key="F"), voice=1)
    assert [n.p for n in follower] == FJ_P
    assert [n.d for n in follower] == FJ_D
    assert [n.s for n in follower] == [n.s + 8.0 for n in FRERE_JACQUES]
    assert all(n.v == 1 for n in follower)
    assert len(threads) == len(FRERE_JACQUES)
    assert all(t.a == t.b and t.kind == "imitation" and not t.broken for t in threads)


def test_diatonic_inversion_in_c_minor():
    leader = line([60, 62, 63], [1, 1, 1])  # C D E-flat, rising
    follower, threads = derive(leader, rule(diatonic=True, key="c", invert_about=67), voice=1)
    # Scale steps mirrored about G in natural C minor: D5 C5 B-flat4, falling.
    assert [n.p for n in follower] == [74, 72, 70]
    assert {t.kind for t in threads} == {"mirror"}
    # Chromatic mirroring would give semitones instead: D C B-natural.
    chromatic, _ = derive(leader, rule(key="c", invert_about=67), voice=1)
    assert [n.p for n in chromatic] == [74, 72, 71]


def test_diatonic_inversion_keeps_raised_degree():
    leader = line([71], [1])  # B-natural = raised 7th degree of C minor
    follower, _ = derive(leader, rule(diatonic=True, key="c", invert_about=67), voice=1)
    # B-flat4 (two steps above G4) mirrors to E-flat4 (two below); the raise carries: E4.
    assert follower[0].p == 64


def test_diatonic_transposition_by_scale_steps():
    leader = line([60, 62, 63, 65], [1, 1, 1, 1])  # C D E-flat F in C minor
    follower, _ = derive(leader, rule(diatonic=True, key="c", interval=1, delay=4.0), voice=1)
    assert [n.p for n in follower] == [62, 63, 65, 67]  # canon at the second


def test_crab_retrograde_ends_where_it_begins():
    leader = line([60, 62, 63, 65, 67], [1, 0.5, 0.5, 1, 2])
    follower, threads = derive(leader, rule(retrograde=True), voice=1)
    assert [n.p for n in follower] == [67, 65, 63, 62, 60]
    assert [n.d for n in follower] == [2, 1, 0.5, 0.5, 1]
    assert follower[0].s == 0.0
    assert follower[-1].p == leader[0].p
    assert follower[-1].s + follower[-1].d == leader[-1].s + leader[-1].d
    assert all(t.kind == "retrograde" for t in threads)
    assert {(t.a, t.b) for t in threads} == {(i, 4 - i) for i in range(5)}


def test_augmentation_doubles_durations_and_delays():
    leader = line([60, 62, 64], [1, 0.5, 0.5], start=2.0)
    follower, threads = derive(leader, rule(delay=4.0, stretch=2.0), voice=1)
    assert [n.d for n in follower] == [2, 1, 1]
    assert [n.s for n in follower] == [6.0, 8.0, 9.0]  # gaps between onsets doubled
    assert all(t.kind == "stretch" for t in threads)


def test_per_tonos_rises_a_whole_tone_each_repetition():
    leader = line([60, 62, 63, 60], [1, 1, 1, 1])
    r = rule(delay=1.0, per_tonos_step=2, repeats=7)
    full = expand_leader(leader, r)
    follower, threads = derive(leader, r, voice=1)
    assert len(full) == len(follower) == len(threads) == 28
    for k in range(7):
        rep = follower[4 * k: 4 * k + 4]
        assert [n.p for n in rep] == [p + 2 * k for p in (60, 62, 63, 60)]
        assert rep[0].s == 4.0 * k + 1.0
        assert [n.p for n in full[4 * k: 4 * k + 4]] == [n.p for n in rep]
    # Six rises of a whole tone close the circle: the seventh pass is back in C.
    assert [n.p % 12 for n in follower[24:]] == [n.p % 12 for n in follower[:4]]
    assert follower[24].p == follower[0].p + 12


def test_exceptions_override_single_notes():
    leader = line([60, 62, 63], [1, 1, 1])
    follower, threads = derive(leader, rule(delay=2.0, interval=7, exceptions={1: 70}), voice=1)
    assert [n.p for n in follower] == [67, 70, 70]
    assert [t.broken for t in threads] == [False, True, False]


def test_match_marks_a_bent_note_as_broken():
    r = rule(delay=8.0, key="F")
    follower, _ = derive(FRERE_JACQUES, r, voice=1)
    follower[5].p += 1
    threads = match(FRERE_JACQUES, follower, r)
    assert len(threads) == len(FRERE_JACQUES)
    broken = [t for t in threads if t.broken]
    assert len(broken) == 1 and broken[0].a == 5 and broken[0].b == 5


def test_match_marks_a_missing_note_as_broken():
    r = rule(delay=8.0, key="F")
    follower, _ = derive(FRERE_JACQUES, r, voice=1)
    del follower[3]
    threads = match(FRERE_JACQUES, follower, r)
    # nothing sounds where the answer should be: no thread at all (not a thread to an unrelated note)
    assert [t.a for t in threads] == [a for a in range(len(FRERE_JACQUES)) if a != 3]
    assert not any(t.broken for t in threads)


def test_match_draws_no_thread_when_no_follower_note_starts_at_the_predicted_onset():
    leader = line([60, 62, 64], [1, 1, 1])
    follower = [Note(1, 60, 4.0, 1), Note(1, 62, 5.0, 1), Note(1, 50, 6.5, 1)]  # third answer missing; a stray note nearby
    threads = match(leader, follower, rule(delay=4.0))
    assert [(t.a, t.b, t.broken) for t in threads] == [(0, 0, False), (1, 1, False)]


def test_free_range_leader_notes_get_no_thread():
    leader = line([60, 62, 64, 65], [1, 1, 1, 1])
    r = rule(delay=4.0, free=((2.0, 4.0),))  # half-open: notes at beats 2 and 3 are free
    follower, _ = derive(leader, r, voice=1)
    threads = match(leader, follower, r)
    assert [t.a for t in threads] == [0, 1]
    assert len(derive(leader, r, voice=1)[1]) == 4  # derive ignores free


def test_flip_alterations_lowers_the_mirror_of_a_raised_degree():
    leader = line([71], [1])  # B-natural, raised 7th of C minor
    kept, _ = derive(leader, rule(diatonic=True, key="c", invert_about=67), voice=1)
    flipped, _ = derive(leader, rule(diatonic=True, key="c", invert_about=67, flip_alterations=True), voice=1)
    assert (kept[0].p, flipped[0].p) == (64, 62)  # E (raise kept) vs D (raise flipped to a lowering)


def _bent_round(**kw):
    r = rule(delay=8.0, key="F", **kw)
    follower, _ = derive(FRERE_JACQUES, r, voice=1)
    follower[5].p += 1
    return match(FRERE_JACQUES, follower, r)


def test_pitch_tolerance_accepts_a_semitone_as_adjusted():
    threads = _bent_round(pitch_tolerance=1)
    assert not any(t.broken for t in threads)
    assert [t.a for t in threads if t.adjusted] == [5]


def test_zero_pitch_tolerance_breaks_the_same_note():
    threads = _bent_round(pitch_tolerance=0)
    assert [t.a for t in threads if t.broken] == [5]
    assert not any(t.adjusted for t in threads)


def test_a_different_duration_still_matches():
    r = rule(delay=8.0, key="F")
    follower, _ = derive(FRERE_JACQUES, r, voice=1)
    follower[4].d *= 1.5
    threads = match(FRERE_JACQUES, follower, r)
    assert not any(t.broken or t.adjusted for t in threads)


def test_an_exception_within_pitch_tolerance_is_adjusted_not_broken():
    # Bach's raised 6th/7th in a minor-key mirror canon: one semitone from the rule
    leader = line([60, 62, 63], [1, 1, 1])
    follower, threads = derive(leader, rule(delay=2.0, interval=7, pitch_tolerance=1,
                                            exceptions={1: 70, 2: 66}), voice=1)
    assert [n.p for n in follower] == [67, 70, 66]
    assert [(t.broken, t.adjusted) for t in threads] == [(False, False), (False, True), (True, False)]


def test_match_reads_an_off_scale_note_as_either_spelling():
    # Goldberg Var. 15 (G minor, mirror about g', four steps up): Bach answers A-flat with C.
    # Read as G-sharp the rule predicts D-sharp (75); read as A-flat it predicts C-flat (71),
    # one semitone from Bach's C: an adjusted imitation, not a break.
    r = rule(delay=2.0, interval=4, diatonic=True, key="g", invert_about=67, pitch_tolerance=1)
    leader = [Note(0, 67, 0.0, 1), Note(0, 68, 1.0, 1)]
    follower = [Note(1, 74, 2.0, 1), Note(1, 72, 3.0, 1)]
    threads = match(leader, follower, r)
    assert [(t.a, t.b, t.broken, t.adjusted) for t in threads] == [(0, 0, False, False), (1, 1, False, True)]


def test_derive_keeps_the_raised_lower_degree_spelling():
    r = rule(delay=2.0, interval=4, diatonic=True, key="g", invert_about=67)
    follower, _ = derive([Note(0, 68, 0.0, 1)], r, voice=1)
    assert follower[0].p == 75  # G-sharp mirrored to D-sharp, as before


def test_not_imitation_leader_notes_get_no_thread():
    """A leader note the follower merely happens to land near (a cadence, a new lead) is
    named by its beat: no thread, wherever the follower is."""
    leader = line([60, 62, 64, 65], [1, 1, 1, 1])
    follower = line([60, 62, 64, 65], [1, 1, 1, 1], start=1)
    threads = match(leader, follower, rule(delay=1, not_imitation=(2.0,)))
    assert [t.a for t in threads] == [0, 1, 3]
