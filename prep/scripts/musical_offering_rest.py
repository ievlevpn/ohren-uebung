"""One-off: the written voices of the other Musical Offering canons, from Reccmo's MIDI files.

Not part of the build. Run once to write ``prep/transcriptions/bwv1079-*.yaml`` for the
canon perpetuus super thema regium, the canon a 2 violini in unisono, the fuga canonica,
the canon a 2 quaerendo invenietis and the canon perpetuus of the Sonata; kept so they can
be re-derived and re-checked. Same method and helpers as ``musical_offering.py``.

Source: IMSLP, "Musikalisches Opfer, BWV 1079", Reccmo's MIDI files (#221461 BWV 1079/2,
#221463 BWV 1079/3b, #221467 BWV 1079/4, #221470 BWV 1079/6 (solutions a and b),
#221475 BWV 1079/9). Downloaded by hand into ``prep/sources/imslp/midi/`` (git-ignored):

    cd prep && uv run python -u scripts/musical_offering_rest.py sources/imslp/midi

Checked against IMSLP10042 (BGA 31.2, PDF page = printed page). Beyond ``tracks``'s
cleaning, two kinds of Reccmo's playing are put back to the notation by hand, each
checked on the plate: a trill he spells out in 32nd notes becomes its main note
(``collapse``), and a tied note he strikes again becomes one note (``tie``).
There is no MIDI of the Canon a 4 among Reccmo's files; it is not transcribed here.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from musical_offering import (EDITION, SOURCE, Rule, check_written, dump,  # noqa: E402
                              exceptions, repeat, tracks, window)


def collapse(notes, lo, hi):
    """A spelled-out trill in [lo, hi) becomes its main (first) note, lasting hi - lo."""
    inside = [n for n in notes if lo - 1e-9 <= n[1] < hi - 1e-9]
    assert inside and abs(inside[0][1] - lo) < 1e-9, (lo, hi, inside[:2])
    keep = [n for n in notes if not lo - 1e-9 <= n[1] < hi - 1e-9]
    return sorted(keep + [[inside[0][0], lo, hi - lo]], key=lambda n: n[1])


def with_duration(notes, fixes):
    """Set the duration of the notes keyed (pitch, onset) in ``fixes``; each must exist."""
    out = [[p, s, fixes.get((p, s), d)] for p, s, d in notes]
    assert len({(p, s) for p, s, _ in notes} & set(fixes)) == len(fixes), fixes
    return out


def tie(notes, at):
    """The note at ``at`` and the next (same pitch, struck again) are one tied note."""
    i = next(k for k, n in enumerate(notes) if abs(n[1] - at) < 1e-9)
    a, b = notes[i], notes[i + 1]
    assert a[0] == b[0] and abs(a[1] + a[2] - b[1]) < 1e-9, (a, b)
    return notes[:i] + [[a[0], a[1], a[2] + b[2]]] + notes[i + 2:]


def main(folder: Path) -> None:
    def find(tag):
        (hit,) = folder.glob(f"*{tag}*.mid")
        return tracks(hit)

    # Canon perpetuus super thema regium (BWV 1079/2): flute and thema written; the
    # bass plays the flute two octaves lower one bar later. The loop is 5 bars (20 beats).
    flute, thema, _bass = find("BWV_1079_2")
    f1, t1 = window(flute, 0.75, 20.75), window(thema, 0, 20)
    passes, end = 4, 76
    check_written("flute", repeat(f1, 20, 0, passes), flute, end)
    check_written("thema", repeat(t1, 20, 0, passes), thema, end)
    exceptions(repeat(f1, 20, 0, passes), Rule(4, -24, False, "C", None, False, 1, 0, 1),
               _bass, end)  # exact: none
    dump("bwv1079-thema-regium", """
Canon perpetuus super thema regium, BWV 1079 — the written voices: the canon's upper
voice (flute) and the royal theme (violin), one 5-bar pass (C minor, 4/4). The bass
plays the upper voice two octaves lower one bar later (computed). Four passes, the
fourth cut at beat 76 by Reccmo's closing C chord (end/coda, editorial).""",
         {"source": SOURCE + " (#221461)", "edition": EDITION,
          "pages": "IMSLP10042, page 8 (riddle); resolution (Kirnberger) IMSLP10042, page 41",
          "voices": [f1, t1], "end": end,
          "coda": [[[84, 76, 2]], [[64, 76, 2]], [[48, 76, 2]]]})

    # Canon a 2 violini in unisono (Canones diversi 2.): violin I and the bass (the royal
    # theme) written; violin II plays violin I at the unison one bar later. The 8-bar
    # loop is written out four times: violin I's pass starts on beat 1 and ends with a
    # crotchet rest, so its span is not the 32-beat period.
    v1, _v2, bass = find("BWV_1079_3b")
    for k in range(4):
        v1 = collapse(v1, 7 + 32 * k, 7.75 + 32 * k)  # c'8. tr (bar 2)
    p1, b1 = window(v1, 1, 33), window(bass, 0, 32)
    check_written("violin I", repeat(p1, 32, 0, 4), v1, 128)
    check_written("bass", repeat(b1, 32, 0, 4), bass, 128)
    exceptions(repeat(p1, 32, 0, 4), Rule(4, 0, False, "C", None, False, 1, 0, 1),
               collapse_all(_v2, [(11 + 32 * k, 11.75 + 32 * k) for k in range(4)]), 131)
    dump("bwv1079-violini-in-unisono", """
Canon a 2 violini in unisono, BWV 1079 — the written voices: violin I and the bass (the
royal theme), the 8-bar perpetual canon written out four times (C minor, 4/4). Violin II
plays violin I at the unison one bar later (computed); after violin I's fourth pass it
finishes its own, over the bass's closing C (Reccmo's, end/coda, editorial).""",
         {"source": SOURCE + " (#221463)", "edition": EDITION,
          "pages": "IMSLP10042, page 8 (riddle: 2.); resolution (Kirnberger) IMSLP10042, page 41",
          "voices": [repeat(p1, 32, 0, 4), repeat(b1, 32, 0, 4)], "end": 131,
          "coda": [[], [], [[48, 128, 3]]]})

    # Fuga canonica in Epidiapente (BWV 1079/4): Reccmo's harpsichord track holds both
    # hands (both may sound the same pitch at once: tracks() pairs first on, first off). The right hand is the dux: every flute note is a right-hand note a fifth
    # higher 40 beats later; up to beat 271 the rest is the bass, from there (the flute
    # finishing the canon alone) the upper of the harpsichord's two lines is the dux.
    flute, harpsichord = find("BWV_1079.4")
    images = {(p, s) for p, s, _ in flute}
    rh, lh, taken = [], [], set()
    for n in harpsichord:  # a unison of both hands (c' at beat 61) is two notes: one each
        key = (n[0], n[1])
        if key not in taken and ((n[0] + 7, n[1] + 40) in images
                                 or (n[1] >= 271 and n[0] >= 58)):
            rh.append(n)
            taken.add(key)
        else:
            lh.append(n)
    for lo, hi in ((102, 104), (182, 184), (266, 268)):  # e''2 tr, g'2 tr, g'2 tr
        rh = collapse(rh, lo, hi)
    # Where both hands hold c' at once, the MIDI's note-offs cannot say which c' is
    # which: first-on-first-off gives the bass's long c' the right hand's short end and
    # vice versa. Durations from the plate (IMSLP10042 p. 43 bars 16-17, p. 44 bars 51-52):
    # the bass's c'2~c'8 at beat 62 and c'2~c'4 at beat 202; the right hand's c'8 at 63.5
    # and 203.
    rh = with_duration(rh, {(60, 63.5): 0.5, (60, 203): 0.5})
    lh = with_duration(lh, {(60, 62): 2.5, (60, 202): 3})
    for a, b in zip(rh, rh[1:]):
        assert b[1] >= a[1] + a[2] - 1e-9, ("right hand overlaps", a, b)
    for a, b in zip(lh, lh[1:]):
        assert b[1] >= a[1] + a[2] - 1e-9, ("bass overlaps", a, b)
    end = 308
    exceptions(window(rh, 0, end), Rule(40, 7, False, "C", None, False, 1, 0, 1),
               collapse_all(flute, [(142, 144), (222, 224), (306, 308)]), end)  # exact: none
    dump("bwv1079-fuga-canonica", """
Fuga canonica in Epidiapente, BWV 1079 — the written voices: the harpsichord's right
hand (the dux, from the royal theme) and its bass (C minor, 4/4, 78 bars). The flute
plays the dux a fifth higher ten bars later (computed), to its last note at beat 308;
the dux runs on alone for its last ten bars. The final chord, held under a fermata, is
the coda (end/coda). Where both hands sound the same pitch at once (c' at beats 61,
62-64.5 and 202-205, b♭ at 207-209; IMSLP10042 p. 43 bars 16-17, p. 44 bars 51-53) each
hand has its own note, durations as printed.""",
         {"source": SOURCE + " (#221467)", "edition": EDITION,
          "pages": "IMSLP10042, pages 10-11 (riddle); resolution IMSLP10042, pages 43-44",
          "voices": [window(rh, 0, end), window(lh, 0, end)], "end": end,
          "coda": [[[72, 308, 4]], [[72, 308, 4]], [[36, 308, 4]]]})

    # Canon a 2 quaerendo invenietis (BWV 1079/6): Reccmo plays two solutions (a: the
    # viola leads; b: the cello leads). Solution a only, BGA's solution A (IMSLP10042,
    # page 49, after the Allgemeine Musikalische Zeitung VIII, p. 287): the cello answers
    # the viola by exact contrary motion about g, 2½ bars later. 15-bar loop.
    viola, cello = find("BWV_1079_6")
    for k in range(3):
        viola = collapse(viola, 30 + 60 * k, 31 + 60 * k)  # d'4 tr
    p1, end = window(viola, 3, 63), 160
    check_written("viola", repeat(p1, 60, 0, 3), viola, end)
    exceptions(p1, Rule(10, 0, False, "C", 55, False, 1, 0, 3), cello, end)  # exact: none
    dump("bwv1079-quaerendo", """
Canon a 2 quaerendo invenietis, BWV 1079 — the written voice: the dux (viola), one pass
of the 15-bar perpetual canon from its upbeat (C minor, 4/4). The comes (cello) answers
by exact contrary motion about g, 2½ bars later (computed): BGA's solution A. Two
passes and most of a third, then Reccmo's closing chord at beat 160 (end/coda,
editorial).""",
         {"source": SOURCE + " (#221470, the first of its two solutions)", "edition": EDITION,
          "pages": "IMSLP10042, page 20 (riddle); solution A IMSLP10042, page 49 "
                   "(after Allg. Mus. Zeitung VIII, p. 287)",
          "voices": [p1], "end": end, "coda": [[[63, 160, 2]], [[48, 160, 2]]]})

    # Canon perpetuus (BWV 1079/9, after the Sonata): the BGA prints it in score (pages
    # 36-37), so every voice is transcribed and the canon is matched, not computed: the
    # violin answers the flute by exact contrary motion two bars later: about one axis,
    # then a minor seventh lower for the flute's notes from bar 18 beat 4 (beat 71, the
    # violin answering from bar 20, beat 79) to the repeat.
    flute, violin, bass = find("BWV_1079_9")
    for k in range(3):
        flute = tie(tie(flute, 19 + 120 * k), 42 + 120 * k)  # e♭''4~e♭''4, c''2~c''4
        violin = tie(violin, 19 + 120 * k)  # c''4~c''4
    check_written("flute", repeat(window(flute, 1, 121), 120, 0, 3), flute, 296)
    dump("bwv1079-canone-perpetuo", """
Canone perpetuo, BWV 1079 — every voice: flute, violin, continuo (C minor, 2/2 counted
in crotchets). Two bars, then the 30-bar repeat played twice and a third time to the
fermata in bar 15 of the piece (bar 13 of the repeat, beat 296), where the BGA's (Fine)
is.""",
         {"source": SOURCE + " (#221475)", "edition": EDITION,
          "pages": "IMSLP10042, pages 36-37 (printed in score)",
          "voices": [flute, violin, bass]})


def collapse_all(notes, spans):
    for lo, hi in spans:
        notes = collapse(notes, lo, hi)
    return notes


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser())
