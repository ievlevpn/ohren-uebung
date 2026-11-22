"""Scale-step arithmetic by hand (major / natural minor), for tests that recompute a
transformation without the canon engine."""

SCALES = {"major": (0, 2, 4, 5, 7, 9, 11), "minor": (0, 2, 3, 5, 7, 8, 10)}
TONIC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def scale_of(key: str) -> tuple[int, tuple[int, ...]]:
    tonic = TONIC[key[0].upper()] + (1 if "#" in key else -1 if key[1:2] == "-" else 0)
    return tonic, SCALES["major" if key[0].isupper() else "minor"]


def to_step(p: int, key: str) -> tuple[int, int]:
    tonic, sc = scale_of(key)
    octave, rel = divmod(p - tonic, 12)
    deg = max(i for i, o in enumerate(sc) if o <= rel)
    return octave * 7 + deg, rel - sc[deg]


def from_step(step: int, alt: int, key: str) -> int:
    tonic, sc = scale_of(key)
    octave, deg = divmod(step, 7)
    return tonic + 12 * octave + sc[deg] + alt
