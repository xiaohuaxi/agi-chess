"""Build the cm-chessboard piece sprite from the 12 Cburnett originals in this folder.

Usage: python3 viewer/vendor/cburnett-pieces/build_sprite.py
Writes viewer/vendor/cm-chessboard/assets/pieces/cburnett.svg.

Same layout as cm-chessboard's standard.svg: a 40x40 sprite whose top-level
<g id="wk"> ... <g id="bp"> groups are referenced by <use href="#wk">. Each
original is 45x45, so its content is scaled by 40/45 with no other change;
element ids inside the originals are dropped so they cannot clash on the page.
"""
import pathlib
import xml.etree.ElementTree as ET

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE.parent / "cm-chessboard" / "assets" / "pieces" / "cburnett.svg"
SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)

HEADER = """<?xml version="1.0" encoding="UTF-8"?><!--

Chess pieces by Cburnett, from Wikimedia Commons
(https://commons.wikimedia.org/wiki/Category:SVG_chess_pieces/Standard_transparent),
used under the 3-clause BSD license, one of the licenses offered on each file page.
Copyright (c) Cburnett. License text and per-file sources: viewer/vendor/cburnett-pieces/.
Assembled into a cm-chessboard sprite by build_sprite.py (scaled 40/45, ids dropped).

-->
"""


def main():
    sprite = ET.Element(f"{{{SVG}}}svg", {"width": "40px", "height": "40px", "viewBox": "0 0 40 40", "version": "1.1"})
    for color, c in (("w", "l"), ("b", "d")):
        for p in "kqbnrp":
            src = ET.parse(HERE / f"Chess_{p}{c}t45.svg").getroot()
            g = ET.SubElement(sprite, f"{{{SVG}}}g", {"id": color + p, "transform": "scale(0.888889)"})
            for child in src:
                for el in child.iter():
                    el.attrib.pop("id", None)
                g.append(child)
    ET.indent(sprite, space="  ")
    OUT.write_text(HEADER + ET.tostring(sprite, encoding="unicode") + "\n", encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
