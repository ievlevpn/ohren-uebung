"""Mutopia LilyPond sources -> one MIDI channel per Voice context -> notes per voice."""
import io
import re
import subprocess
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from .sources import SOURCES

MUTOPIA = "https://www.mutopiaproject.org/ftp"
MIDI_CONTEXT = r"\context { \Score midiChannelMapping = #'voice }"
EARLIER_ENDING = "fugueEarlierEnding"


def _block_end(text: str, open_at: int) -> int:
    """Index just past the ``}`` closing the ``{`` at ``open_at``; ``%`` comments skipped."""
    depth, k = 0, open_at
    while k < len(text):
        c = text[k]
        if c == "%":
            nl = text.find("\n", k)
            k = len(text) if nl < 0 else nl
            continue
        depth += {"{": 1, "}": -1}.get(c, 0)
        k += 1
        if depth == 0:
            return k
    raise ValueError("unbalanced braces")


def _keep_last_endings(text: str) -> str:
    """Play only the last ending of every ``\\alternative`` (see ``patch_source``)."""
    out, pos, tagged = [], 0, False
    for m in re.finditer(r"\\alternative\s*\{", text):
        if m.start() < pos:
            continue
        end = _block_end(text, m.end() - 1)
        groups, k = [], m.end()
        while True:  # top-level { ... } groups inside the block
            j = text.find("{", k, end - 1)
            if j < 0:
                break
            if "%" in text[k:j]:  # a comment between groups: skip past its line
                k = text.find("\n", k + text[k:j].index("%")) + 1
                continue
            groups.append(j)
            k = _block_end(text, j)
        out.append(text[pos:m.start()])
        body = text[m.start():end]
        for j in reversed(groups[:-1]):
            j -= m.start()
            body = body[:j] + f"\\tag #'{EARLIER_ENDING} " + body[j:]
            tagged = True
        out.append(body)
        pos = end
    text = "".join(out) + text[pos:]
    if tagged:
        text = re.sub(r"\\score\s*\{", lambda m: m.group(0) + f" \\removeWithTag #'{EARLIER_ENDING} ", text)
    return text


def fetch_mutopia(path: str) -> Path:
    """Download ``<path>/<name>.ly`` (e.g. ``BachJS/BWV988/bwv-988-v03``) once; return the file.

    Multi-file sources have no ``<name>.ly`` but a ``<name>-lys.zip`` (main file plus
    ``\\include``d parts): it is unpacked into ``mutopia/<name>-lys/``."""
    name = path.rstrip("/").rsplit("/", 1)[-1]
    base = f"{MUTOPIA}/{path.strip('/')}"
    dest = SOURCES / "mutopia" / f"{name}.ly"
    packed = SOURCES / "mutopia" / f"{name}-lys" / f"{name}.ly"
    if dest.exists():
        return dest
    if packed.exists():
        return packed
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(f"{base}/{name}.ly", timeout=60) as r:
            dest.write_bytes(r.read())
        return dest
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
    with urllib.request.urlopen(f"{base}/{name}-lys.zip", timeout=60) as r:
        data = r.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for member in z.namelist():  # only plain files inside <name>-lys/
            target = (dest.parent / member).resolve()
            if not str(target).startswith(str(dest.parent.resolve() / f"{name}-lys")):
                raise RuntimeError(f"unexpected path {member!r} in {name}-lys.zip")
        z.extractall(dest.parent)
    if not packed.exists():
        raise RuntimeError(f"{name}-lys.zip has no {name}.ly")
    return packed


def patch_source(text: str) -> str:
    """Make the score render one MIDI channel per Voice.

    * Any ``\\midi { ... }`` block gets the per-voice channel mapping, and a legacy
      ``\\tempo`` inside it (old syntax, now an error) is dropped.
    * A ``\\score`` with no ``\\midi`` gets one.
    * Only the last ending of each ``\\alternative`` sounds. Repeats are not unfolded (each
      half is heard once), so the first ending would otherwise play straight into the
      second. The earlier endings are tagged and removed by ``\\removeWithTag`` at the
      score, i.e. after ``\\relative`` has fixed every pitch: ``\\relative`` runs through the
      first ending into the second, so deleting it as text would move later notes by octaves.
    * ``\\change Staff`` is removed: LilyPond gives a voice that crosses staves a new
      channel on the other staff, so one voice would split across channels. Staves do not
      matter for sound. Parallel voices written as ``<< \\a \\\\ \\b >>`` are already
      separate Voice contexts, so no extra Voice contexts were needed (see SOURCES.md).
    """
    text = _keep_last_endings(text)
    text = re.sub(r"\\change\s+Staff\s*=\s*#?\"?[\w-]+\"?", "{ }", text)
    m = re.search(r"\\midi\s*\{", text)
    if m:
        # brace-count to the end of the block (it may hold nested \\context { ... })
        depth, k = 1, m.end()
        while depth and k < len(text):
            depth += {"{": 1, "}": -1}.get(text[k], 0)
            k += 1
        body = re.sub(r"\\tempo\s+\d+\s*=\s*\d+", "", text[m.end():k - 1])
        text = text[:m.start()] + "\\midi { " + MIDI_CONTEXT + body + "}" + text[k:]
    else:
        i = text.rindex("}")
        text = text[:i] + "\\midi { " + MIDI_CONTEXT + " }\n" + text[i:]
    if "midiChannelMapping = #'voice" not in text:
        raise RuntimeError("could not add midiChannelMapping to the score")
    return text


def render_voices(ly: Path) -> Path:
    """Patch a copy of ``ly``, run convert-ly if needed, run lilypond; return the .mid."""
    out = ly.parent / "voices"
    out.mkdir(exist_ok=True)
    patched = out / ly.name
    patched.write_text(patch_source(ly.read_text(encoding="utf-8")), encoding="utf-8")
    midi = out / (ly.stem + ".midi")
    midi.unlink(missing_ok=True)
    # -I: the patched copy lives in voices/, its \\include files next to the original
    cmd = ["lilypond", "-I", str(ly.parent), "-o", str(out / ly.stem), str(patched)]
    run = subprocess.run(cmd, capture_output=True, text=True)
    if not midi.exists():
        # older source syntax: upgrade the copy in place and retry
        subprocess.run(["convert-ly", "-e", str(patched)], capture_output=True, text=True)
        run = subprocess.run(cmd, capture_output=True, text=True)
    if not midi.exists():
        raise RuntimeError(f"lilypond failed for {ly}:\n{run.stderr[-2000:]}")
    return midi
