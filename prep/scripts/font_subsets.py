# /// script
# dependencies = ["fonttools", "brotli"]
# ///
"""Build the web's symbol subsets (one-off, not part of the build):

    uv run prep/scripts/font_subsets.py

Inputs, downloaded by hand into prep/sources/fonts/ (git-ignored):
- GaramondLibre-Regular.otf, GaramondLibre-Italic.otf: Garamond Libre 1.4
  (github.com/dbenjaminmiller/garamond-libre, release garamond-libre_1.4.zip; MIT-style
  licence, web/src/fonts/GaramondLibre-COPYING.txt);
- NotoMusic-Regular.ttf: Noto Music (github.com/google/fonts, ofl/notomusic; SIL OFL 1.1,
  web/src/fonts/NotoMusic-OFL.txt).

Outputs, in web/src/fonts/:
- GaramondLibre-Accidentals-{Regular,Italic}.woff2: ♩ ♪ ♭ ♮ ♯ (U+2669-266A, U+266D-266F),
  which EB Garamond lacks;
- NotoMusic-HalfNote.woff2: the half note U+1D15E, which Garamond Libre lacks, scaled and
  lowered to Garamond Libre's ♩ (the same height and depth), so tempo labels match.
"""
from pathlib import Path

from fontTools import subset
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "prep" / "sources" / "fonts"
OUT = ROOT / "web" / "src" / "fonts"
NOTES = [0x2669, 0x266A]
ACCIDENTALS = [0x266D, 0x266E, 0x266F]
HALF = 0x1D15E


def cut(font: TTFont, codes: list[int]) -> TTFont:
    opts = subset.Options()
    opts.layout_features = []
    opts.name_IDs = ["*"]
    opts.notdef_outline = True
    s = subset.Subsetter(opts)
    s.populate(unicodes=codes)
    s.subset(font)
    return font


def bounds(font: TTFont, code: int):
    gs = font.getGlyphSet()
    pen = BoundsPen(gs)
    gs[font.getBestCmap()[code]].draw(pen)
    return pen.bounds


def main() -> None:
    for style in ("Regular", "Italic"):
        f = cut(TTFont(SRC / f"GaramondLibre-{style}.otf"), NOTES + ACCIDENTALS)
        f.flavor = "woff2"
        f.save(OUT / f"GaramondLibre-Accidentals-{style}.woff2")
    _, q_lo, _, q_hi = bounds(TTFont(SRC / "GaramondLibre-Regular.otf"), 0x2669)
    f = cut(TTFont(SRC / "NotoMusic-Regular.ttf"), [HALF])
    _, h_lo, _, h_hi = bounds(f, HALF)
    k = (q_hi - q_lo) / (h_hi - h_lo)
    dy = q_lo - h_lo * k
    name = f.getBestCmap()[HALF]
    gs = f.getGlyphSet()
    pen = TTGlyphPen(gs)
    gs[name].draw(TransformPen(pen, (k, 0, 0, k, 0, dy)))
    f["glyf"][name] = pen.glyph()
    width, _ = f["hmtx"][name]
    f["hmtx"][name] = (round(width * k), 0)
    f["glyf"][name].recalcBounds(f["glyf"])
    f["hmtx"][name] = (round(width * k), f["glyf"][name].xMin)
    f.flavor = "woff2"
    f.save(OUT / "NotoMusic-HalfNote.woff2")


if __name__ == "__main__":
    main()
