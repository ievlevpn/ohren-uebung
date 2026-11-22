"""One-off: the written voices of four Musical Offering canons, from Reccmo's MIDI files.

Not part of the build. It was run once to write ``prep/transcriptions/bwv1079-*.yaml``;
it is kept so the transcriptions can be re-derived and re-checked.

Source: IMSLP, "Musikalisches Opfer, BWV 1079", Reccmo's typeset canons with MIDI
(#221462 Canon 1 cancrizans, #221464 Canon 3 per motum contrarium, #221465 Canon 4 per
augmentationem, #221466 Canon 5 per tonos; IMSLP files WIMA.*-BWV_1079_3a..3e). Download
them by hand (IMSLP needs a browser) into one folder and pass it as the argument:

    cd prep && uv run python -u scripts/musical_offering.py ~/Downloads/bwv1079-midi

Checked against the Bach-Gesellschaft edition, vol. 31.2 (Alfred Dörffel, Breitkopf &
Härtel 1885; IMSLP #10042, file IMSLP10042-BWV1079-b.pdf, kept in prep/sources/imslp/,
git-ignored; PDF page = printed page): Bach's riddle notation on pages 8-9 and the
resolutions (after Kirnberger) in the Anhang, pages 41-43. Reccmo plays ~95 % legato and spells out
trills; onsets are snapped to 1/32 beat, trills (a run alternating two pitches) become one
note, durations go back to notated values. The follower each rule computes is compared
with Reccmo's follower: differences become ``exceptions`` (Bach's chromatic adjustments).
"""
import json
import sys
from pathlib import Path

import mido

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fugue_prep.canon import Rule, derive  # noqa: E402
from fugue_prep.model import Note  # noqa: E402

GRID = (0.0625, 0.125, 0.1875, 0.25, 0.375, 0.5, 0.75, 1, 1.25, 1.5, 1.75, 2, 2.5, 3, 3.5, 4,
        6, 8)
OUT = Path(__file__).resolve().parent.parent / "transcriptions"


def q(x: float, g: int = 32) -> float:
    return round(x * g) / g


def tracks(path: Path) -> list[list[list]]:
    """[[midi, start, duration], ...] per track that has notes, in file order."""
    mid = mido.MidiFile(str(path), clip=True)  # 221475 has a malformed sysex
    out = []
    for tr in mid.tracks:
        t, on, notes = 0, {}, []
        for m in tr:
            t += m.time
            # first on, first off per (channel, pitch): two hands on one channel may hold
            # the same pitch at once (the Fuga canonica's harpsichord track)
            if m.type == "note_on" and m.velocity > 0:
                on.setdefault((m.channel, m.note), []).append(t)
            elif m.type in ("note_off", "note_on") and on.get((m.channel, m.note)):
                s = on[(m.channel, m.note)].pop(0)
                notes.append([m.note, q(s / mid.ticks_per_beat), (t - s) / mid.ticks_per_beat])
        if not notes:
            continue
        notes.sort(key=lambda n: n[1])
        merged, i = [], 0
        while i < len(notes):
            p, s, d = notes[i]
            if (i + 2 < len(notes) and notes[i + 1][2] < 0.07 and notes[i + 1][1] - s < 0.2
                    and notes[i + 2][0] == p and notes[i + 1][0] != p):
                j = i + 1  # a trill: the run alternates between two pitches
                while (j + 1 < len(notes) and notes[j + 1][2] < 0.07
                       and notes[j + 1][0] in (p, notes[i + 1][0])):
                    j += 1
                merged.append([p, s, notes[j][1] + notes[j][2] - s])
                i = j + 1
                continue
            merged.append([p, s, d])
            i += 1
        clean = []
        for k, (p, s, d) in enumerate(merged):
            want = min(GRID, key=lambda g: abs(g - d / 0.95))
            if k + 1 < len(merged) and abs((merged[k + 1][1] - s) - want) <= 0.13:
                want = merged[k + 1][1] - s  # legato: up to the next onset
            clean.append([p, s, want])
        out.append(clean)
    return out


def window(notes, lo, hi):
    return [list(n) for n in notes if lo - 1e-9 <= n[1] < hi - 1e-9]


def repeat(notes, period, step, times):
    return [[p + r * step, s + r * period, d] for r in range(times) for p, s, d in notes]


def exceptions(leader, rule, ref, end):
    """Follower index -> Reccmo's pitch where it differs from the rule (onsets < end)."""
    notes = [Note(0, p, s, d) for p, s, d in leader]
    follower, _ = derive(notes, rule, 1)
    have = {q(s): p for p, s, _ in ref if s < end}
    out, missing = {}, []
    for i, n in enumerate(follower):
        if n.s >= end:
            continue
        p = have.get(q(n.s))
        if p is None:
            missing.append(n.s)
        elif p != n.p:
            if abs(p - n.p) > rule.pitch_tolerance:
                raise SystemExit(f"follower note {i} at beat {n.s}: Reccmo {p}, rule {n.p}")
            out[i] = p
    if missing:
        raise SystemExit(f"Reccmo's follower has no note at beats {missing[:8]}")
    return out


def check_written(name, written, ref, end):
    """Every written note before ``end`` must be in Reccmo's part, and vice versa."""
    a = {(p, q(s)) for p, s, _ in written if s < end}
    b = {(p, q(s)) for p, s, _ in ref if s < end}
    if a != b:
        raise SystemExit(f"{name}: written voice and Reccmo differ before beat {end}: "
                         f"{sorted(a - b)[:6]} / {sorted(b - a)[:6]}")


def dump(name: str, header: str, data: dict) -> None:
    def flow(notes):
        return "[" + ", ".join(f"[{p}, {s:g}, {d:g}]" for p, s, d in notes) + "]"
    lines = [f"# {line}".rstrip() for line in header.strip().splitlines()]
    for k in ("source", "edition", "pages"):
        lines.append(f"{k}: {json.dumps(data[k], ensure_ascii=False)}")
    lines.append("voices:")
    lines += [f"  - {flow(v)}" for v in data["voices"]]
    if "end" in data:
        lines.append(f"end: {data['end']:g}")
        lines.append("coda:")
        lines += [f"  - {flow(v)}" for v in data["coda"]]
    (OUT / f"{name}.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {name}.yaml")
    if "exceptions" in data:  # for the markings' rule
        ex = ", ".join(f"{k}: {v}" for k, v in data["exceptions"].items())
        print(f"  {len(data['exceptions'])} exceptions: {{{ex}}}")


EDITION = "Bach-Gesellschaft Ausgabe vol. 31.2 (ed. Alfred Dörffel, Breitkopf & Härtel 1885), IMSLP #10042"
SOURCE = "Reccmo's MIDI on IMSLP (BWV 1079 page), notes checked against the edition"


def main(folder: Path) -> None:
    def find(tag):
        (hit,) = folder.glob(f"*BWV_1079_{tag}*.mid")
        return tracks(hit)

    # Canon 1 a 2 cancrizans: one written line; the comes is the same line backwards.
    (dux, comes) = find("3a")
    leader = window(dux, 0, 72)
    exceptions(leader, Rule(0, 0, False, "C", None, True, 1, 0, 1), comes, 72)  # exact: none
    dump("bwv1079-cancrizans", """
Canon a 2 cancrizans, BWV 1079 — the written voice (18 bars of 4/4, C minor).
The second voice is the same line read backwards (computed by the rule).""",
         {"source": SOURCE + " (#221462); same notes as Nate Eldredge's LilyPond, github.com/captbaritone/crab_canon",
          "edition": EDITION, "pages": "IMSLP10042, page 8 (riddle: Canones diversi, 1.); resolution IMSLP10042, page 41", "voices": [leader]})

    # Canon 3 a 2 per motum contrarium: Thema + dux written; comes by contrary motion.
    theme, dux, comes = find("3c")
    t1, d1 = window(theme, 0, 16), window(dux, 0.25, 16.25)
    passes, end = 4, 61.5
    rule = Rule(2, 0, True, "c", 63, False, 1, 0, passes, pitch_tolerance=1)
    check_written("thema", repeat(t1, 16, 0, passes), theme, end)
    check_written("dux", repeat(d1, 16, 0, passes), dux, end)
    ex = exceptions(d1, rule, comes, end)
    coda = [window(theme, end, 99), window(dux, end, 99), window(comes, end, 99)]
    dump("bwv1079-motum-contrarium", """
Canon a 2 per motum contrarium, BWV 1079 — the written voices: Thema (royal theme,
ornamented) and the dux, one pass of the 4-bar perpetual canon (C minor, 4/4).
The comes answers by contrary motion two beats later (computed). Four passes, then the
closing cadence (end/coda: Reccmo's ending, editorial — Bach's canon has none).""",
         {"source": SOURCE + " (#221464)", "edition": EDITION,
          "pages": "IMSLP10042, page 9 (riddle: 3.); resolution IMSLP10042, page 42", "voices": [t1, d1], "end": end,
          "coda": coda, "exceptions": ex})

    # Canon 4 a 2 per augmentationem, contrario motu: comes inverted at double length.
    comes, theme, dux = find("3d")
    t1, d1 = window(theme, 0, 32), window(dux, 0.75, 32.75)
    end = 144
    tw, dw = repeat(t1, 32, 0, 5), repeat(d1, 32, 0, 5)
    check_written("thema", tw, theme, end)
    check_written("dux", dw, dux, end)
    rule = Rule(1.75, 0, True, "c", 63, False, 2, 0, 1, pitch_tolerance=1)
    ex = exceptions(dw, rule, comes, end)
    coda = [window(comes, end, 999), window(theme, end, 999), window(dux, end, 999)]
    dump("bwv1079-augmentationem", """
Canon a 2 per augmentationem, contrario motu, BWV 1079 — the written voices: Thema
(ornamented) and the dux, 8 bars each (C minor, 4/4), written out five times: the
comes, by contrary motion in notes of double length, needs 16 bars for the dux's 8, so
the perpetual canon plays the dux twice per round of the comes. Two full rounds of the
comes (to beat 130.5) and 3⅜ bars of a third, then Reccmo's closing chord at beat 144
(end/coda, editorial).""",
         {"source": SOURCE + " (#221465)", "edition": EDITION,
          "pages": "IMSLP10042, page 9 (riddle: 4.); resolution IMSLP10042, page 42", "voices": [tw, dw], "end": end,
          "coda": coda, "exceptions": ex})

    # Canon 5 a 2 per tonos: Thema + dux written; comes a fifth above, one bar later;
    # each pass a whole tone higher, six passes back to C minor.
    theme, comes, dux = find("3e")
    t1, d1 = window(theme, 0, 32), window(dux, 0.25, 32.25)
    end = 192
    rule = Rule(4, 7, False, "C", None, False, 1, 2, 6)
    check_written("thema", repeat(t1, 32, 2, 6), theme, end)
    check_written("dux", repeat(d1, 32, 2, 6), dux, end)
    exceptions(d1, rule, comes, end)  # exact: none
    coda = [window(theme, end, 999), window(comes, end, 999), window(dux, end, 999)]
    dump("bwv1079-per-tonos", """
Canon a 2 per tonos, BWV 1079 — the written voices: Thema (ornamented) and the dux,
one 8-bar pass (C minor modulating to D minor, 4/4). The comes plays the dux a fifth
higher one bar later (computed); every pass rises a whole tone, six passes return to
C minor, then Reccmo's closing chord (end/coda, editorial).""",
         {"source": SOURCE + " (#221466)", "edition": EDITION,
          "pages": "IMSLP10042, page 9 (riddle: 5.); resolution IMSLP10042, page 43", "voices": [t1, d1], "end": end,
          "coda": coda})


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser())
