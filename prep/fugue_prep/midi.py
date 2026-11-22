"""Read a MIDI file into per-voice notes (one voice per track and channel that has notes)."""
from pathlib import Path

import mido

from .model import Note, ScoreVoices


def read_midi(path: Path, beats_per_quarter: float = 1) -> ScoreVoices:
    """Voices top first (highest mean pitch first); times in quarter-note beats
    multiplied by ``beats_per_quarter``.
    A note struck again while still sounding is cut at the new onset. Tied notes arrive as one note (LilyPond merges them)."""
    mid = mido.MidiFile(str(path))
    scale = beats_per_quarter / mid.ticks_per_beat
    # a voice = (track, channel): LilyPond writes one track per staff, and with
    # midiChannelMapping = #'voice one channel per voice inside it; old scores without
    # explicit Voice contexts put every staff on channel 0 of its own track
    by_channel: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
    for k, track in enumerate(mid.tracks):
        t = 0
        open_: dict[tuple[int, int], int] = {}
        for msg in track:
            t += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                key = (msg.channel, msg.note)
                if key in open_:  # re-struck while sounding: close the earlier note here
                    by_channel.setdefault((k, msg.channel), []).append((open_[key], t, msg.note))
                open_[key] = t
            elif msg.type in ("note_off", "note_on") and (msg.channel, msg.note) in open_:
                start = open_.pop((msg.channel, msg.note))
                by_channel.setdefault((k, msg.channel), []).append((start, t, msg.note))
    voices = []
    for ch in sorted(by_channel):
        notes = sorted(by_channel[ch])
        voices.append([(s, e, p) for s, e, p in notes])
    voices.sort(key=lambda v: -sum(p for _, _, p in v) / len(v))
    return [[Note(i, p, s * scale, (e - s) * scale) for s, e, p in v] for i, v in enumerate(voices)]
