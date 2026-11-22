"""Find the entries of a fugue subject or an invention motive in a score.

An entry matches when every subject note has a partner in the voice at the same
relative onset (scaled for augmentation/diminution) and the melodic intervals agree:
each within ``MAX_DEVIATION`` semitones of the subject's (negated when inverted), and at
least ``MIN_EXACT`` of them exact. The tolerance admits tonal answers (a fourth answered
by a fifth) and modal changes (the subject in the relative major); measured on BWV 847,
every real entry has at least 14 of 19 intervals exact and none deviates by more than 2.
Durations are not compared (Bach shortens or ties the last note of an entry).

"Exact" means the same size in scale steps (a second stays a second, a third a third,
major or minor): a diatonic transposition (the motive on another degree, in a sequence)
and a diatonic mirror both trade whole and half steps without changing the steps. The
step size is read from the semitones (1-2 = a second, 3-4 = a third, 5 = a fourth,
6 = a fourth or a fifth, 7 = a fifth, 8-9 = a sixth, 10-11 = a seventh).
"""
import math

from .model import Note, ScoreVoices

TRANSFORMS = ("none", "inverted", "augmented", "diminished",
              "inverted augmented", "inverted diminished")
STRETCH = {"none": 1.0, "inverted": 1.0, "augmented": 2.0, "diminished": 0.5,
           "inverted augmented": 2.0, "inverted diminished": 0.5}
MAX_DEVIATION = 2  # semitones
MIN_EXACT = 0.7  # fraction of intervals that must be exact
ONSET_TOLERANCE = 0.01  # beats


# scale steps an interval of n semitones (within the octave) can span
_STEPS = {0: {0}, 1: {1}, 2: {1}, 3: {2}, 4: {2}, 5: {3}, 6: {3, 4}, 7: {4}, 8: {5}, 9: {5},
          10: {6}, 11: {6}}


def steps(semitones: int) -> set[int]:
    """The interval's possible sizes in scale steps, signed like it (+-7 per octave)."""
    octaves, rest = divmod(abs(semitones), 12)
    sign = -1 if semitones < 0 else 1
    return {sign * (7 * octaves + k) for k in _STEPS[rest]}


class EntryMismatch(Exception):
    """A marked entry is not where the markings say."""


def subject_notes(voices: ScoreVoices, spec: dict) -> list[Note]:
    """The notes of voice ``spec['voice']`` starting in [start, start + length) beats."""
    lo, hi = spec["start"], spec["start"] + spec["length"]
    return [n for n in voices[spec["voice"]]
            if not n.c and lo - ONSET_TOLERANCE <= n.s < hi - ONSET_TOLERANCE]


def subject_spec(fugue: dict, e: dict) -> dict:
    """The subject an entry states: ``fugue.subjects[e.subject]`` in a fugue on several
    subjects (a double or triple fugue), else ``fugue.subject``."""
    subjects = fugue.get("subjects")
    if subjects and e.get("subject") is not None:
        return subjects[e["subject"]]
    return fugue["subject"]


def first_answer(fugue: dict, subject: str | None = None) -> dict | None:
    """The fugue's first answer (of subject ``subject`` in a fugue on several subjects):
    the earliest entry (by ``start``) with form answer, whole, matched against the
    subject (not ``ref: answer``); None if there is none."""
    return min((e for e in fugue["entries"] if e["form"] == "answer"
                and e.get("part", "whole") == "whole"
                and e.get("ref", "subject") == "subject"
                and e.get("subject") == subject),
               key=lambda e: e["start"], default=None)


def entry_reference(voices: ScoreVoices, fugue: dict, e: dict, *, piece: str = "?",
                    beats_per_bar: int = 4, pickup: float = 0) -> list[Note]:
    """The notes an entry is matched against: the countersubject for (counter)subject
    forms of it, the first answer's notes for ``ref: answer``, else the subject (in a fugue
    on several subjects, the one the entry names)."""
    if e["form"] in ("countersubject", "countermotive"):
        return subject_notes(voices, fugue["countersubject"])
    subject = subject_notes(voices, subject_spec(fugue, e))
    if e.get("ref", "subject") != "answer":
        return subject
    a = first_answer(fugue, e.get("subject"))
    if a is None:
        raise ValueError("ref: answer, but the fugue has no first answer")
    idx = find_entry(voices, subject, a["voice"], a["start"], a.get("transform", "none"),
                     piece=piece, beats_per_bar=beats_per_bar, pickup=pickup)
    return [voices[a["voice"]][i] for i in idx]


def find_entry(voices: ScoreVoices, subject: list[Note], voice: int, start: float,
               transform: str = "none", *, piece: str = "?", beats_per_bar: int = 4,
               pickup: float = 0, head: str = "fixed", tail: str = "fixed",
               head_length: int | None = None, octave: tuple[int, ...] = ()) -> list[int]:
    """Indices into ``voices[voice]`` of the entry's notes, one per subject note.
    Secondary notes (``c``: lower chord tones, split-off lines) are never part of an entry.

    ``head="free"``: the first note is the note sounding at ``start`` (the statement's
    place): it may begin there and be held longer, or be tied over from before, and be of
    another pitch: its onset, duration and interval to note 2 are not compared;
    note 2 is the next note after it, and notes 3..n are placed relative to note 2.
    Note 2 may come late by at most the subject's first note (held at most twice as long).
    It may come early without bound: for a legato subject note 2 always follows the first
    note anyway, and where the first note is followed by a rest Bach shortens that rest
    (BWV 864 bar 31: the head D enters two eighths late, after a pickup, and note 2 keeps
    its place), so an early bound would reject real statements.
    ``tail="free"`` (the mirror): the last note may come early or late (the note before
    it held or cut short) and turn elsewhere: it is the next note after note n-1, and its
    interval is not compared; it may come late by at most the subject's last note's length.

    ``head="short"``: the first note is half as long as the subject's (BWV 849: most
    statements of the first subject open with a half note for its whole note): it begins
    at ``start`` and its pitch is compared, and every later note comes that half-length
    earlier than the subject puts it. Only where the markings say so (``head: short``); no
    other tolerance changes.

    ``octave``: interval numbers (1 = notes 1-2) where the statement moves part of the
    subject an octave away (Contrapunctus X bar 75: notes 4-6 an octave down); those
    intervals are compared after adding or taking away whole octaves. Only where the
    markings say so (``octave: [3, 6]``).

    ``head_length``: a statement of the subject's head only (markings ``part: head``): only
    the first ``head_length`` subject notes are matched (``tail`` then applies to the last
    of them).

    Raises ``EntryMismatch`` ("<piece>: bar <n>: ...") if the entry is not there.
    """
    if transform not in TRANSFORMS:
        raise ValueError(f"unknown transform {transform!r}")

    def fail(why: str) -> EntryMismatch:
        bar = math.floor((start - pickup) / beats_per_bar) + 1
        return EntryMismatch(f"{piece}: bar {bar}: no {transform} entry in voice {voice} "
                             f"at beat {start}: {why}")

    if not subject:
        raise fail("the subject is empty")
    if not 0 <= voice < len(voices):
        raise fail("no such voice")
    if head_length is not None:
        if not 2 <= head_length <= len(subject):
            raise ValueError(f"head_length must be 2..{len(subject)}, got {head_length}")
        subject = subject[:head_length]
    if head not in ("fixed", "free", "short") or tail not in ("fixed", "free"):
        raise ValueError(f"head must be 'fixed', 'free' or 'short', tail 'fixed' or 'free', "
                         f"got {head!r}/{tail!r}")
    notes = voices[voice]
    factor = STRETCH[transform]

    def at(beat: float) -> int:
        found = [i for i, m in enumerate(notes) if not m.c and abs(m.s - beat) <= ONSET_TOLERANCE]
        if not found:
            raise fail(f"no note at beat {beat}")
        return found[0]

    if head == "free" and len(subject) > 1:
        sounding = [i for i, m in enumerate(notes) if not m.c
                    and m.s <= start + ONSET_TOLERANCE and m.s + m.d > start + ONSET_TOLERANCE]
        if not sounding:
            raise fail(f"no note sounds at beat {start}")
        first = sounding[-1]
    else:
        first = at(start)
    if head == "free" and len(subject) > 1:
        nxt = next((i for i in range(first + 1, len(notes))
                    if not notes[i].c and notes[i].s > start + ONSET_TOLERANCE), None)
        if nxt is None:
            raise fail("no note after the first")
        due = start + (subject[1].s - subject[0].s) * factor
        if notes[nxt].s > due + subject[0].d * factor + ONSET_TOLERANCE:
            raise fail(f"note 2 comes {notes[nxt].s - due} beats late (at most the "
                       f"first note's {subject[0].d * factor})")
        anchor, ref = notes[nxt].s, subject[1].s
        body = subject[1:-1] if tail == "free" else subject[1:]
        idx = [first] + [at(anchor + (n.s - ref) * factor) for n in body]
    else:
        body = subject[:-1] if tail == "free" else subject
        # head short: notes 2..n come half the first note's length early
        early = subject[0].d / 2 if head == "short" else 0
        idx = [at(start + (n.s - subject[0].s - (early if k else 0)) * factor)
               for k, n in enumerate(body)]
    if tail == "free" and len(subject) > 1:
        prev = idx[-1]
        last = next((i for i in range(prev + 1, len(notes))
                     if not notes[i].c and notes[i].s > notes[prev].s + ONSET_TOLERANCE), None)
        if last is None:
            raise fail("no note after the second-last")
        due = notes[prev].s + (subject[-1].s - subject[-2].s) * factor
        if notes[last].s > due + subject[-1].d * factor + ONSET_TOLERANCE:
            raise fail(f"the last note comes {notes[last].s - due} beats late (at most "
                       f"its {subject[-1].d * factor})")
        idx.append(last)
    sign = -1 if transform.startswith("inverted") else 1
    want_iv = [sign * (b.p - a.p) for a, b in zip(subject, subject[1:])]
    got_iv = [notes[j].p - notes[i].p for i, j in zip(idx, idx[1:])]
    for k in octave:  # an octave displacement Bach writes into the statement
        if 1 <= k <= len(got_iv):
            got_iv[k - 1] += 12 * round((want_iv[k - 1] - got_iv[k - 1]) / 12)
    lo = 1 if head == "free" else 0
    hi = len(got_iv) - 1 if tail == "free" else len(got_iv)
    want_iv, got_iv = want_iv[lo:hi], got_iv[lo:hi]
    dev = [abs(g - w) for g, w in zip(got_iv, want_iv)]
    if dev and max(dev) > MAX_DEVIATION:
        k = dev.index(max(dev))
        raise fail(f"interval {k + 1 + lo} is {got_iv[k]} semitones, the subject has {want_iv[k]}")
    exact = sum(bool(steps(g) & steps(w)) for g, w in zip(got_iv, want_iv))
    if dev and exact < MIN_EXACT * len(dev):
        raise fail(f"only {exact} of {len(dev)} intervals exact")
    return idx
