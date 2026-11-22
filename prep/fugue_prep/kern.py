"""Read Humdrum **kern scores into per-voice note lists (beats = quarter notes)."""
import re
from collections.abc import Iterable
from pathlib import Path

from music21 import converter, note

from .model import Note, ScoreVoices

GRACE = 0.0625  # a grace note's length in quarter notes (a sixty-fourth): it sounds just
# before its main note, which keeps its own place and length


MANIPULATORS = ("*^", "*v", "*x", "*+", "*-")


def restore_commented(text: str, from_bar: int) -> str:
    """The file with its commented-out ending read again (BWV 865: ``wtc1f20.krn`` adds a
    fifth spine with ``*+`` at bar 80 and prefixes every line from there to the end with
    ``!!``). From the barline ``=from_bar`` on, a ``!!`` line (not ``!!!``) whose text
    has one field per spine is a data line again. A spine added there (``*+`` on the last
    spine) becomes a voice of its own from the start: the ``*+`` and the lines that set
    it up (``**kern``, key, meter) are dropped, and every earlier line gets a field for
    it (the header's interpretations and the barlines copied from the spine before it, a
    whole-bar rest ``1r`` on each bar's first data line, null tokens elsewhere; whole bars
    of 4/4 only). Raises ValueError if there is no such barline, nothing is commented
    out, or a spine is added elsewhere than after the last."""
    lines = text.splitlines()
    out: list[str] = []
    width = None  # spines, once inside the restored part
    added = None  # index in ``out`` where the added spine begins
    setup = False  # in the interpretation lines right after the ``*+``
    restored = 0
    for ln in lines:
        if width is None:
            out.append(ln)
            if ln.split("\t")[0] == f"={from_bar}":
                width = len(ln.split("\t"))
            continue
        if ln.startswith("!!") and not ln.startswith("!!!") and len(ln[2:].split("\t")) == width:
            ln = ln[2:]
            restored += 1
        fields = ln.split("\t")
        if setup:
            if ln.startswith("*") and all(f == "*" for f in fields[:-1]):
                continue  # sets up the added spine only
            setup = False
        if ln.startswith("*") and "*+" in fields:
            if fields.index("*+") != len(fields) - 1 or fields.count("*+") != 1:
                raise ValueError("only a spine added after the last one can be restored")
            added, width, setup = len(out), width + 1, True
            continue
        out.append(ln)
    if width is None:
        raise ValueError(f"no barline ={from_bar}")
    if not restored:
        raise ValueError(f"nothing is commented out from bar {from_bar}")
    if added is None:
        return "\n".join(out) + "\n"
    head, in_header, bar_open = [], True, False
    for ln in out[:added]:
        f = ln.split("\t")
        if ln.startswith("!!"):
            pass
        elif ln.startswith("!"):
            f.append("!")
        elif ln.startswith("="):
            in_header, bar_open = False, True
            f.append(f[-1])
        elif ln.startswith("*"):
            if any(re.fullmatch(r"\*M\d+/\d+", x) and x != "*M4/4" for x in f):
                raise ValueError("an added spine is padded with whole bars of 4/4 only")
            f.append(f[-1] if in_header and f[-1] not in MANIPULATORS else "*")
        elif ln.strip():
            if in_header:
                raise ValueError("music before the first barline")
            f.append("1r" if bar_open else ".")
            bar_open = False
        ln = "\t".join(f)
        head.append(ln)
    return "\n".join(head + out[added:]) + "\n"


def read_kern(path: Path, alternatives: Iterable[int] = (),
              warnings: list[str] | None = None, grace: bool = True,
              commented_from: int | None = None) -> ScoreVoices:
    """One list per spine, top voice first, sorted by start. Ties merged. No sounding
    note is dropped:

    - a grace note (appoggiatura, acciaccatura) is a secondary note ``GRACE`` long, placed
      just before its main note (a run of n grace notes takes the n * GRACE before it);
      the main note is unchanged. ``grace=False`` leaves them out (tests);

    - a chord's top note is the voice's (primary) note; its other tones are kept as
      secondary notes (``c=True``);
    - where a spine splits (`*^`) into sub-voices, the first sub-voice continues the
      voice and the notes of the others are secondary notes of the same voice (a
      secondary note at the same onset and pitch as a primary one is dropped: it is the
      same sound);
    - except in the bars listed in ``alternatives``: there the extra sub-voices are an
      edition's alternative reading (`*S/sic` / `*S/ossia`), not sounding notes, and are
      dropped; each drop is appended to ``warnings`` (naming voice and bar). A listed bar
      with no split raises ValueError.

    - a tie that continues the voice's note into a chord continues it even where the held
      pitch is not the chord's top note (it stays the primary note, the other tones are
      secondary) or where the encoding puts the tie's end on another tone of the chord
      (BWV 865's last bar: ``1AA; 1A;]``, the A held from bar 83 under a new A);
    - ``commented_from``: the bars from there to the end are commented out in the file
      and are read again (``restore_commented``); a spine added there is a voice of its
      own, silent before.

    Secondary notes play and are drawn, but entry and canon logic use primary notes only.
    music21 returns the parts top voice first (verified on BWV 847: the last spine in the
    file is the soprano), so no reversal is needed.
    """
    alternatives = set(alternatives)
    if commented_from is None:
        score = converter.parse(str(path), format="humdrum")
    else:
        text = restore_commented(Path(path).read_text(encoding="utf-8"), commented_from)
        score = converter.parse(text, format="humdrum")
    voices: ScoreVoices = []
    dropped: list[str] = []
    split_bars: set[int] = set()
    for v, part in enumerate(score.parts):
        notes: list[Note] = []
        open_tie = False  # last primary note continues into the next
        sec: list[Note] = []
        open_sec: dict[int, Note] = {}  # secondary notes whose tie continues, by pitch

        def add_secondary(p, s: float, d: float) -> None:
            tie = p.tie.type if p.tie else None
            held = open_sec.pop(p.pitch.midi, None)
            if held is not None and tie in ("continue", "stop"):
                held.d = s + d - held.s
                x = held
            else:
                x = Note(v=v, p=p.pitch.midi, s=s, d=d, c=True)
                sec.append(x)
            if tie in ("start", "continue"):
                open_sec[p.pitch.midi] = x

        def add_graces(run: list) -> None:
            """Grace notes, by the main note they precede: a run of n before an onset
            takes the n * GRACE before it, in order."""
            by_start: dict[float, list] = {}
            for start, n in run:
                if n.duration.isGrace:
                    by_start.setdefault(float(start), []).append(n)
            for start, gs in by_start.items():
                for k, g in enumerate(gs):
                    s = start - (len(gs) - k) * GRACE
                    for q in ([g] if isinstance(g, note.Note) else g.notes):
                        sec.append(Note(v=v, p=q.pitch.midi, s=s, d=GRACE, c=True))

        for m in part.getElementsByClass("Measure"):
            # In a split measure music21 keeps the shared notes directly on the Measure
            # and each sub-voice inside a Voice (placed at its own offset).
            subs = list(m.voices)
            if len(subs) > 1:
                split_bars.add(m.number)
                if m.number in alternatives:
                    dropped.append(f"voice {v} bar {m.number}")
            main = [(m.offset, n) for n in m.notes]
            if subs:
                main += [(m.offset + subs[0].offset, n) for n in subs[0].notes]
            extra = [] if m.number in alternatives else [
                (m.offset + sv.offset, n) for sv in subs[1:] for n in sv.notes]
            main_sorted = sorted(((base + n.offset, n) for base, n in main), key=lambda t: t[0])
            extra_sorted = sorted(((base + n.offset, n) for base, n in extra), key=lambda t: t[0])
            if grace:
                for run in (main_sorted, extra_sorted):
                    add_graces(run)
            for base_n in main_sorted:
                start, n = base_n
                if n.duration.isGrace:
                    continue
                s, d = float(start), float(n.duration.quarterLength)
                chord = [n] if isinstance(n, note.Note) else sorted(
                    n.notes, key=lambda x: x.pitch.midi, reverse=True)
                p = chord[0]  # the top note is the voice's
                ties = [q.tie.type if q.tie else None for q in chord]
                held = [q for q in chord if notes and q.pitch.midi == notes[-1].p]
                # a held note goes on in the chord, under its top note or with the tie's
                # end written on another tone
                carried = (open_tie and held and len(chord) > 1
                           and any(t in ("continue", "stop") for t in ties))
                if carried:
                    p = held[0]
                for q in chord:
                    if q is not p:
                        add_secondary(q, s, d)
                tie = p.tie.type if p.tie else None
                if carried or (open_tie and notes and notes[-1].p == p.pitch.midi
                               and tie in ("continue", "stop")):
                    notes[-1].d = s + d - notes[-1].s
                else:
                    notes.append(Note(v=v, p=p.pitch.midi, s=s, d=d))
                open_tie = tie in ("start", "continue")
            for start, n in extra_sorted:
                if n.duration.isGrace:
                    continue
                for q in ([n] if isinstance(n, note.Note) else n.notes):
                    add_secondary(q, float(start), float(n.duration.quarterLength))
        sounding = {(x.s, x.p) for x in notes}  # a secondary note never doubles a primary one
        sec = [x for x in sec if (x.s, x.p) not in sounding]
        voices.append(sorted(notes + sec, key=lambda x: (x.s, x.c, -x.p)))
    missing = sorted(alternatives - split_bars)
    if missing:
        raise ValueError(f"{path}: alternatives name bar {', '.join(map(str, missing))}, "
                         "which has no spine split")
    if warnings is not None:
        warnings.extend(f"{path}: dropped alternative sub-voice at {s}" for s in dropped)
    return voices
