"""Piece data model: mirrors web/src/model.ts. Serialise with dataclasses.asdict."""
from dataclasses import dataclass, field

# Instruments per ensemble, top voice first; the last entry is the bass instrument.
# web/src/audio/ensembles.ts mirrors this table and the two functions below.
ENSEMBLE_INSTRUMENTS = {
    "chamber": ("flute", "violin", "cello"),  # cello = continuo
    "harpsichord": ("harpsichord",),
    "strings": ("violin", "violin", "viola", "cello"),
    "organ": ("organ",),
}
ENSEMBLES = tuple(ENSEMBLE_INSTRUMENTS)
# Playable range per instrument, (lowest, highest) MIDI pitch. A voice may name its own
# instrument in the markings (any of these); the build fails when a voice's default
# instrument would have to play outside its range.
INSTRUMENT_RANGES = {
    "flute": (60, 96),        # C4-C7
    "violin": (55, 105),      # G3-A7
    "viola": (48, 88),        # C3-E6
    "cello": (36, 81),        # C2-A5
    "harpsichord": (29, 89),  # F1-F6
    "organ": (36, 96),        # C2-C7
}
# Ensembles whose bass instrument is continuo: a piece with fewer voices than the table
# (a treble canon) plays on the upper instruments only.
CONTINUO = {"chamber"}
TEXTURES = ("solid", "hatch", "stipple", "dashed", "open", "cross")  # cross: cross-hatched
THREAD_KINDS = ("imitation", "mirror", "retrograde", "stretch")
MARK_KINDS = ("mirror-axis", "crab-axis", "stretch", "rise", "entry", "stretto")
# Forms of a marked entry; an entry mark's label is its form (plus its transform, plus
# " (head)" for a statement of the subject's head alone). Fugues
# use subject/answer/countersubject; inventions use motive/countermotive.
ENTRY_FORMS = ("subject", "answer", "countersubject", "motive", "countermotive")


@dataclass
class Note:
    v: int  # voice index
    p: int  # MIDI pitch
    s: float  # start, beats
    d: float  # duration, beats
    c: bool = False  # secondary: a lower chord tone or a split-off line; played and drawn,
    # but entry and canon logic use primary notes only


@dataclass
class Voice:
    name: str
    texture: str
    instrument: str
    pan: float


@dataclass
class Thread:
    a: int  # note index
    b: int  # note index
    kind: str
    broken: bool = False
    adjusted: bool = False  # pitch within tolerance of, but not equal to, the rule's prediction


@dataclass
class Mark:
    kind: str
    start: float
    end: float
    voice: int | None = None
    pitch: int | None = None
    label: str | None = None


@dataclass
class Caption:
    at: float
    text: str


@dataclass
class Piece:
    id: str
    title: str
    collection: str
    catalogue: str
    key: str
    tempo: float
    beatsPerBar: int
    ensemble: str
    voices: list[Voice] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    threads: list[Thread] = field(default_factory=list)
    marks: list[Mark] = field(default_factory=list)
    captions: list[Caption] = field(default_factory=list)
    techniques: list[str] = field(default_factory=list)
    listenFor: str = ""
    beatUnit: float = 1  # the beat in quarter notes: 1 = crotchet, 0.5 = quaver (tempo is per beat)
    pickup: float = 0  # beats of upbeat before bar 1: bar n starts at pickup + (n-1)*beatsPerBar
    glossaryNotes: dict[str, str] = field(default_factory=dict)  # glossary entry id -> "In this piece"


@dataclass
class Collection:
    id: str
    numeral: str
    name: str
    catalogue: str
    note: str
    books: list[dict] = field(default_factory=list)  # {name, pieces: [id]}


@dataclass
class PieceSummary:
    id: str
    title: str
    collection: str
    catalogue: str
    key: str
    voices: int
    bars: int
    techniques: list[str] = field(default_factory=list)
    listenFor: str = ""
    number: int | None = None  # the piece's own number in its book (WTC fugue 3), if not its place


@dataclass
class Library:
    collections: list[Collection] = field(default_factory=list)
    pieces: list[PieceSummary] = field(default_factory=list)
    techniques: dict[str, list[str]] = field(default_factory=dict)

ScoreVoices = list[list[Note]]  # one list of notes per voice, top voice first


def instruments_for(ensemble: str, voices: int) -> list[str]:
    """Default instrument per voice (top first). Fewer voices than the table: upper voices
    take instruments from the top, the bass voice gets the bass instrument; more voices:
    the last upper instrument repeats. A single voice gets the top instrument. In a
    continuo ensemble (``CONTINUO``) a piece with fewer voices than the table has no bass
    instrument: chamber, 2 voices = flute + violin."""
    table = ENSEMBLE_INSTRUMENTS[ensemble]
    if voices == 1 or len(table) == 1:
        return [table[0]] * voices
    if ensemble in CONTINUO and voices < len(table):
        return list(table[:voices])
    upper, bass = table[:-1], table[-1]
    return [upper[min(i, len(upper) - 1)] for i in range(voices - 1)] + [bass]


def pan_for(voice: int, voices: int) -> float:
    """Stereo position: voices spread evenly from -0.6 (top voice, left) to 0.6 (bass, right)."""
    if voices <= 1:
        return 0.0
    return round(-0.6 + 1.2 * voice / (voices - 1), 6)
