"""Canon engine: a written leader plus a canonic rule gives the follower and its threads.

Index convention: every ``Thread`` returned here is *local* — ``a`` indexes the
(expanded) leader list and ``b`` the follower list. The build step (Task 6) remaps
them to indices into the piece's global note list.

Pitch arithmetic
----------------
* ``diatonic=False``: ``interval`` and the inversion are in semitones.
* ``diatonic=True``: ``interval`` counts scale steps of ``key`` (a music21 key string,
  lowercase = minor, e.g. ``"c"``; uppercase = major, e.g. ``"C"``) and inversion mirrors
  scale steps about ``invert_about`` (a MIDI pitch that must lie on the scale).
  The scale is music21's: major, or *natural* minor. A leader note off the scale is read
  as a scale degree plus a chromatic alteration, taking the degree below and raising it
  (in C minor B-natural = raised B-flat, F-sharp = raised F); the alteration is kept, with
  the same sign, on the follower's degree. Bach's own deviations from a strict
  application (e.g. a raised leading note in the follower) go in ``Rule.exceptions``.
  ``match`` also tries the other spelling (the degree above, lowered: A-flat rather than
  G-sharp in G minor) and keeps whichever prediction is closer to the score.

Order of operations for one note: invert (if ``invert_about``), then transpose by
``interval``; timing: retrograde/stretch about the leader's start, then ``delay``.
"""
from dataclasses import dataclass, field, replace
from functools import lru_cache

from music21 import key as m21key

from .model import Note, Thread


@dataclass
class Rule:
    delay: float  # beats from the leader's first onset to the follower's first onset
    interval: int  # semitones, or scale steps when diatonic
    diatonic: bool
    key: str  # music21 key string: "c" = C minor, "F" = F major
    invert_about: int | None  # MIDI pitch of the mirror axis, None = no inversion
    retrograde: bool
    stretch: float  # 2 = augmentation, 0.5 = diminution
    per_tonos_step: int  # semitones each repetition rises (2 = whole tone)
    repeats: int  # passes of the whole canon (1 = no per-tonos repetition)
    exceptions: dict[int, int] = field(default_factory=dict)  # follower index -> MIDI pitch
    # Half-open leader-beat ranges where the follower does not imitate (cadences, free
    # codas). ``match`` makes no thread for a leader note starting in one; ``derive``
    # ignores the field (it builds the follower from the rule, free or not).
    free: tuple[tuple[float, float], ...] = ()
    # Diatonic inversion only: a raised degree answers as a lowered mirror degree
    # (the alteration changes sign). Default keeps the "preserved per degree" ruling.
    flip_alterations: bool = False
    # ``match`` only: a follower note within this many semitones of the prediction still
    # imitates it (Bach's chromatic adjustments); such threads are ``adjusted``, not broken.
    pitch_tolerance: int = 0
    # ``match`` only: leader beats whose image the follower lands near only by chance (a
    # cadence, a voice starting its own lead). Like ``free`` but for single notes: no
    # thread, and not counted as a miss.
    not_imitation: tuple[float, ...] = ()


def is_not_imitation(beat: float, rule: Rule) -> bool:
    return any(abs(beat - b) < 1e-6 for b in rule.not_imitation)


def thread_kind(rule: Rule) -> str:
    """Precedence: retrograde > mirror > stretch > imitation."""
    if rule.retrograde:
        return "retrograde"
    if rule.invert_about is not None:
        return "mirror"
    if rule.stretch != 1:
        return "stretch"
    return "imitation"


@lru_cache(maxsize=None)
def _scale(key_name: str) -> tuple[int, tuple[int, ...]]:
    """Tonic pitch class and the seven scale offsets (semitones above the tonic)."""
    k = m21key.Key(key_name)
    tonic = k.tonic.pitchClass
    offsets = tuple((p.pitchClass - tonic) % 12 for p in k.pitches[:7])
    return tonic, offsets


def _to_steps(p: int, key_name: str) -> tuple[int, int]:
    """MIDI pitch -> (absolute scale step, chromatic alteration in semitones)."""
    tonic, offsets = _scale(key_name)
    octave, rel = divmod(p - tonic, 12)
    degree = max(i for i, off in enumerate(offsets) if off <= rel)
    return octave * 7 + degree, rel - offsets[degree]


def _to_steps_upper(p: int, key_name: str) -> tuple[int, int] | None:
    """The other spelling of an off-scale pitch: the degree above, lowered. None on the scale."""
    step, alt = _to_steps(p, key_name)
    if not alt:
        return None
    tonic, offsets = _scale(key_name)
    octave, degree = divmod(step + 1, 7)
    return step + 1, (p - tonic) - (octave * 12 + offsets[degree])


def _from_steps(step: int, alteration: int, key_name: str) -> int:
    tonic, offsets = _scale(key_name)
    octave, degree = divmod(step, 7)
    return tonic + octave * 12 + offsets[degree] + alteration


def _pitch(p: int, rule: Rule, spelling: tuple[int, int] | None = None) -> int:
    """The rule applied to one pitch; ``spelling`` (step, alteration) overrides the default reading."""
    if not rule.diatonic:
        if rule.invert_about is not None:
            p = 2 * rule.invert_about - p
        return p + rule.interval
    step, alt = spelling or _to_steps(p, rule.key)
    if rule.invert_about is not None:
        axis, axis_alt = _to_steps(rule.invert_about, rule.key)
        if axis_alt:
            raise ValueError(f"inversion axis {rule.invert_about} is not on the scale of {rule.key}")
        step = 2 * axis - step
        if rule.flip_alterations:
            alt = -alt
    return _from_steps(step + rule.interval, alt, rule.key)


def _span(leader: list[Note]) -> tuple[float, float]:
    return min(n.s for n in leader), max(n.s + n.d for n in leader)


def expand_leader(leader: list[Note], rule: Rule) -> list[Note]:
    """The leader played ``rule.repeats`` times, each pass ``per_tonos_step`` semitones
    higher and starting where the previous pass ended (period = the leader's span).
    With ``repeats == 1`` this is a copy of the leader."""
    if not leader:
        return []
    s0, end = _span(leader)
    period = end - s0
    return [replace(n, p=n.p + r * rule.per_tonos_step, s=n.s + r * period)
            for r in range(rule.repeats) for n in leader]


def _predict(leader: list[Note], rule: Rule, voice: int) -> tuple[list[Note], list[int]]:
    """Follower notes sorted by onset, and for each expanded-leader note its follower index.

    Per tonos: every pass of the follower is pass 0 shifted by the same period and
    transposition as the leader pass it imitates (for diatonic rules this equals moving
    the key up with it); delay and stretch are the same in every pass, measured from
    that pass's own start.
    """
    if not leader:
        return [], []
    s0, end = _span(leader)
    period = end - s0
    base = []
    for n in leader:
        if rule.retrograde:
            s = s0 + rule.delay + (end - n.s - n.d) * rule.stretch
        else:
            s = s0 + rule.delay + (n.s - s0) * rule.stretch
        base.append(Note(voice, _pitch(n.p, rule), s, n.d * rule.stretch))
    raw = [replace(b, p=b.p + r * rule.per_tonos_step, s=b.s + r * period)
           for r in range(rule.repeats) for b in base]
    order = sorted(range(len(raw)), key=lambda i: raw[i].s)  # stable: ties keep leader order
    position = [0] * len(raw)
    for pos, i in enumerate(order):
        position[i] = pos
    return [raw[i] for i in order], position


def derive(leader: list[Note], rule: Rule, voice: int) -> tuple[list[Note], list[Thread]]:
    """Compute the follower (voice ``voice``) and one thread per note.

    With ``repeats > 1`` the thread's ``a`` indexes ``expand_leader(leader, rule)``.
    ``rule.exceptions`` (follower index -> MIDI pitch) is applied after derivation. As in
    ``match``, an overridden note within ``rule.pitch_tolerance`` semitones of the rule's
    pitch keeps an unbroken, ``adjusted`` thread (a chromatic adjustment, e.g. a raised
    6th or 7th in a minor-key mirror canon); further away, the thread is ``broken``.
    """
    follower, position = _predict(leader, rule, voice)
    kind = thread_kind(rule)
    threads = [Thread(a, b, kind) for a, b in enumerate(position)]
    for idx, p in rule.exceptions.items():
        if follower[idx].p != p:
            close = abs(follower[idx].p - p) <= rule.pitch_tolerance
            follower[idx].p = p
            for t in threads:
                if t.b == idx:
                    t.adjusted, t.broken = close, not close
    return follower, threads


def match(leader: list[Note], follower: list[Note], rule: Rule,
          tolerance_beats: float = 0.01) -> list[Thread]:
    """Threads for a canon whose follower comes from a score.

    For each (expanded) leader note the rule predicts a follower note (ignoring
    ``rule.exceptions``). A follower note whose onset is within ``tolerance_beats`` of the
    prediction and whose pitch is within ``rule.pitch_tolerance`` semitones is its partner
    (durations are not compared: ties, splits and ornaments); the closest pitch wins.
    The thread is unbroken; ``adjusted=True`` if the pitch differs from the prediction.
    For diatonic rules an off-scale leader note is predicted under both spellings (lower
    degree raised, upper degree lowered); the one closer to the score counts. If a follower
    note starts there but no pitch fits, the thread is broken (to the closest pitch). If no
    follower note starts at the predicted onset, there is no thread: nothing in the score
    answers that note. Leader notes in ``rule.free`` or at a ``rule.not_imitation`` beat
    get no thread. Threads come in leader order.
    """
    predicted, position = _predict(leader, replace(rule, exceptions={}), voice=0)
    kind = thread_kind(rule)
    leader_s = [n.s for n in expand_leader(leader, rule)]
    threads = []
    for a, pos in enumerate(position):
        if any(lo <= leader_s[a] < hi for lo, hi in rule.free) or is_not_imitation(
                leader_s[a], rule):
            continue
        want = predicted[pos]
        wants = [want.p]
        if rule.diatonic:
            src = leader[a % len(leader)].p
            upper = _to_steps_upper(src, rule.key)
            if upper is not None:
                wants.append(_pitch(src, rule, upper) + (a // len(leader)) * rule.per_tonos_step)
        near = [i for i, n in enumerate(follower) if abs(n.s - want.s) <= tolerance_beats]
        if not near:
            continue

        def dist(i: int) -> int:
            return min(abs(follower[i].p - w) for w in wants)
        b = min(near, key=dist)
        if dist(b) <= rule.pitch_tolerance:
            threads.append(Thread(a, b, kind, adjusted=dist(b) != 0))
        else:
            threads.append(Thread(a, b, kind, broken=True))
    return threads
