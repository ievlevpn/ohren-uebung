from fugue_prep.kern import read_kern
from fugue_prep.sources import fetch_wtc_fugues

PATH = fetch_wtc_fugues() / "kern" / "wtc1f02.krn"
VOICES = read_kern(PATH)


def test_three_voices():
    assert len(VOICES) == 3


def test_subject_opens_c_b_c_g_ab():
    alto = VOICES[1]
    assert [n.p for n in alto[:5]] == [72, 71, 72, 67, 68]
    assert alto[0].s == 0.5  # after an eighth rest, bar 1


def test_answer_enters_in_soprano_bar_3_on_g():
    first = VOICES[0][0]  # soprano is voice 0
    assert first.p % 12 == 7
    assert 8.0 <= first.s < 12.0  # bar 3 of 4/4


def test_voices_ordered_top_first():
    means = [sum(n.p for n in v) / len(v) for v in VOICES]
    assert means[0] > means[1] > means[2]
    assert [n.v for n in VOICES[2][:1]] == [2]


def test_ties_are_merged():
    # count note tokens in the source that are not tie continuations/ends
    count = 0
    ties = 0
    for line in PATH.read_text().splitlines():
        if line.startswith(("!", "*", "=")):
            continue
        for tok in (t for field in line.split("\t") for t in field.split(" ")):  # chord tones too
            if tok == "." or "r" in tok or "q" in tok:
                continue
            if "[" in tok:
                ties += 1
            if "_" in tok or "]" in tok:
                continue
            count += 1
    assert ties > 0
    assert sum(len(v) for v in VOICES) == count


F01 = fetch_wtc_fugues() / "kern" / "wtc1f01.krn"


def primary(voice):
    return [n for n in voice if not n.c]


def test_a_split_keeps_every_sub_voice_by_default():
    """No split raises any more: the extra sub-voices become secondary notes (c=True) of
    their voice. wtc1f01 bar 9 soprano without 'alternatives': the ossia's F#5 sixteenth
    comes back as a secondary note (its E5 starts with the main text's E5, so it is the
    same sound and not doubled)."""
    warnings: list[str] = []
    voices = read_kern(F01, warnings=warnings)
    assert warnings == []
    sec = [(n.s, n.p, n.d) for n in voices[0] if n.c and 32.0 <= n.s < 36.0]
    assert sec == [(34.75, 78, 0.25)]


def test_alternatives_drop_the_ossia_and_say_so():
    warnings: list[str] = []
    voices = read_kern(F01, alternatives=[4, 9, 12], warnings=warnings)
    assert [w.split("at ")[-1] for w in warnings] == ["voice 0 bar 9", "voice 0 bar 12",
                                                       "voice 1 bar 4"]
    for voice in voices:
        assert not any(n.c for n in voice if 12 <= n.s < 16 or 32 <= n.s < 36 or 44 <= n.s < 48)
        prim = primary(voice)
        for a, b in zip(prim, prim[1:]):
            assert a.s + a.d <= b.s + 1e-9, (a, b)


def test_alternatives_keep_direct_notes_and_offsets():
    # wtc1f01 bar 9 (starts at beat 32), soprano: 2ff, then split (main text 8xee 8xff#),
    # then [4gg tied into bar 10.
    voices = read_kern(F01, alternatives=[4, 9, 12])
    bar9 = [(n.s, n.p) for n in voices[0] if 32.0 <= n.s < 36.0]
    assert bar9 == [(32.0, 77), (34.0, 76), (34.5, 78), (35.0, 79)]
    assert [n.d for n in voices[0] if n.s == 35.0] == [2.0]  # tie merged across the barline


def test_an_alternative_bar_without_a_split_is_an_error():
    import pytest
    with pytest.raises(ValueError, match="bar 5"):
        read_kern(F01, alternatives=[4, 5])


def test_a_chord_keeps_all_its_tones():
    """BWV 846's last chord: the alto holds G5 and E5 (the chord's third); the top note
    is primary, the E5 secondary."""
    voices = read_kern(F01, alternatives=[4, 9, 12])
    last = max(n.s for n in voices[1])
    assert sorted((n.p, n.c) for n in voices[1] if n.s == last) == [(76, True), (79, False)]


def test_a_melodic_split_keeps_both_lines():
    """wtc1f07 bar 37 (beat 144): the soprano splits; the second line D-flat, C, C-flat,
    B-flat is kept as secondary notes beside the first line's held E-flat."""
    voices = read_kern(fetch_wtc_fugues() / "kern" / "wtc1f07.krn")
    sop = [n for n in voices[0] if n.s >= 144]
    assert [(n.s, n.p) for n in sop if not n.c] == [(144.0, 63)]
    assert [(n.s, n.p, n.d) for n in sop if n.c] == [(144.25, 61, 0.75), (145.0, 60, 0.75),
                                                     (145.75, 59, 0.25), (146.0, 58, 2.0)]


def test_find_entry_ignores_secondary_notes():
    from fugue_prep.fugue import find_entry
    from fugue_prep.model import Note
    subject = [Note(0, 60, 0, 1), Note(0, 62, 1, 1), Note(0, 64, 2, 1)]
    voice = [Note(0, 67, 4, 1, c=True), Note(0, 60, 4, 1), Note(0, 71, 5, 1, c=True),
             Note(0, 62, 5, 1), Note(0, 64, 6, 1)]
    assert find_entry([voice], subject, 0, 4) == [1, 3, 4]


def test_a_secondary_note_never_doubles_a_primary_one():
    """wtc1f03 bar 55: both soprano lines start on E#4 at beat 216; it sounds once."""
    voices = read_kern(fetch_wtc_fugues() / "kern" / "wtc1f03.krn")
    for voice in voices:
        primary_keys = {(n.s, n.p) for n in voice if not n.c}
        assert not [n for n in voice if n.c and (n.s, n.p) in primary_keys]
    assert [n.c for n in voices[0] if (n.s, n.p) == (216.0, 65)] == [False]


# --- grace notes: sounding notes, kept as secondary notes just before their main note ---

def _kern_sources():
    from fugue_prep.build import MARKINGS
    from fugue_prep.markings import load_markings
    from fugue_prep.sources import SOURCES, fetch_repo, REPOS
    paths = sorted({load_markings(f)["source"]["path"] for f in MARKINGS.glob("*/*.yaml")
                    if load_markings(f)["source"]["kind"] == "kern"})
    for p in paths:
        fetch_repo(p.split("/", 1)[0]) if p.split("/", 1)[0] in REPOS else None
    return [SOURCES / p for p in paths]


def test_grace_notes_are_secondary_and_sound_just_before_their_main_note():
    """Ricercar a 3, last bar (IMSLP10042 p. 7): appoggiaturas b' (soprano) and f' (alto)
    before the final chord at beat 736 (quarters): a sixty-fourth (1/16 of a quarter)
    before it, secondary; the main notes keep their place and length."""
    from fugue_prep.kern import GRACE
    from fugue_prep.sources import fetch_musical_offering
    voices = read_kern(fetch_musical_offering() / "kern" / "offering-001.krn")
    assert GRACE == 0.0625
    assert [(n.p, n.s, n.d) for n in voices[0] if n.c] == [(71, 736 - GRACE, GRACE)]
    assert [(n.p, n.s, n.d) for n in voices[1] if n.c] == [(65, 736 - GRACE, GRACE)]
    assert [(n.p, n.s, n.d) for n in voices[0] if not n.c][-1] == (72, 736.0, 2.0)
    assert [(n.p, n.s, n.d) for n in voices[1] if not n.c][-1] == (64, 736.0, 2.0)


def test_grace_notes_leave_every_other_note_unchanged():
    """For every kern source in the library: reading with grace notes adds only secondary
    notes of length GRACE, each ending where a primary note of its voice begins (or a run
    of grace notes before it); everything else is what the read without them gives."""
    from fugue_prep.kern import GRACE
    counts = {}
    for path in _kern_sources():
        with_g = read_kern(path)
        without = read_kern(path, grace=False)
        n = 0
        for a, b in zip(with_g, without):
            extra = [x for x in a if x not in b]
            assert [x for x in a if x not in extra] == b, path.name
            starts = {x.s for x in a if not x.c}
            for x in extra:
                assert x.c and x.d == GRACE, (path.name, x)
                k = 1
                while x.s + k * GRACE not in starts:  # a run of grace notes
                    assert any(y.s == x.s + k * GRACE for y in extra), (path.name, x)
                    k += 1
            n += len(extra)
        if n:
            counts[path.name] = n
    assert counts == {"offering-001.krn": 2, "sinfo05.krn": 66, "artfugue-008.krn": 2,
                      "artfugue-011.krn": 2, "artfugue-012.krn": 15, "artfugue-014.krn": 5,
                      "artfugue-015.krn": 6}


def test_restore_commented_reads_a_commented_ending():
    """The commented lines are read again; a spine added with ``*+`` is a voice of its
    own from the start: whole-bar rests before, the header and barlines copied."""
    import pytest
    from fugue_prep.kern import restore_commented
    text = "\n".join([
        "**kern\t**kern", "*M4/4\t*M4/4", "=1\t=1", "2c\t2e", "2d\t2f", "=2\t=2",
        "!! Three-voice material until the end:", "*\t*+", "*\t*\t**kern", "*\t*\t*M4/4",
        "!!1c\t1e\t1g", "!!==\t==\t==", "!!*-\t*-\t*-", ""])
    out = restore_commented(text, 2).splitlines()
    assert out == ["**kern\t**kern\t**kern", "*M4/4\t*M4/4\t*M4/4", "=1\t=1\t=1",
                   "2c\t2e\t1r", "2d\t2f\t.", "=2\t=2\t=2",
                   "!! Three-voice material until the end:", "1c\t1e\t1g",
                   "==\t==\t==", "*-\t*-\t*-"]
    with pytest.raises(ValueError, match="no barline =3"):
        restore_commented(text, 3)
    with pytest.raises(ValueError, match="nothing is commented"):
        restore_commented(text.replace("!!1c", "1c").replace("!!==", "==")
                          .replace("!!*-", "*-"), 2)
    with pytest.raises(ValueError, match="4/4 only"):
        restore_commented(text.replace("*M4/4\t*M4/4", "*M3/4\t*M3/4"), 2)
