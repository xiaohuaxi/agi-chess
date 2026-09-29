"""DIY prototype: PGN -> frames (python-chess SVG -> cairosvg PNG -> Pillow compose) -> ffmpeg mp4."""
import io, subprocess, sys, os
import chess, chess.pgn, chess.svg, cairosvg
from PIL import Image, ImageDraw, ImageFont

W, H = (1080, 1920) if os.environ.get("RATIO", "9:16") == "9:16" else (1920, 1080)
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"   # CJK-capable, macOS only
BG, FG = (24, 24, 28), (235, 235, 235)
font = lambda s: ImageFont.truetype(FONT, s)
BOARD = min(W, H) - 40 if W < H else H - 200
END_TXT = {"将死": "将死 Checkmate"}

def board_png(board, last, size):
    chk = board.king(board.turn) if board.is_check() else None
    svg = chess.svg.board(board, lastmove=last, check=chk, size=size, coordinates=False,
        colors={"square light": "#f0d9b5", "square dark": "#b58863",
                "square light lastmove": "#cdd26a", "square dark lastmove": "#aaa23a"})
    return Image.open(io.BytesIO(cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size))).convert("RGB")

def text_c(d, xy, t, f, fill=FG):
    d.text(xy, t, font=f, fill=fill, anchor="mm")

def frame(game, board, last, ply, total, banner=None):
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    bi = board_png(board, last, BOARD)
    if W < H: bx, by = (W - BOARD)//2, (H - BOARD)//2
    else:     bx, by = 60, (H - BOARD)//2
    im.paste(bi, (bx, by))
    wn, bn = game.headers["White"], game.headers["Black"]
    tx = bx + BOARD//2 if W < H else bx + BOARD + (W - bx - BOARD)//2
    if W < H:
        text_c(d, (W//2, by - 60), f"黑  {bn}", font(48)); text_c(d, (W//2, by + BOARD + 60), f"白  {wn}", font(48))
        text_c(d, (W//2, 90), f"第 {ply} / {total} 步", font(36), (160,160,160))
    else:
        text_c(d, (tx, H//2 - 120), f"黑  {bn}", font(48)); text_c(d, (tx, H//2 + 120), f"白  {wn}", font(48))
        text_c(d, (tx, 90), f"第 {ply} / {total} 步", font(36), (160,160,160))
    if banner:
        d.rectangle([bx, by + BOARD//2 - 80, bx + BOARD, by + BOARD//2 + 80], fill=(0,0,0))
        text_c(d, (bx + BOARD//2, by + BOARD//2), banner, font(64), (255, 220, 100))
    return im

def title(game):
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    text_c(d, (W//2, H//2 - 200), game.headers.get("Event", ""), font(44), (160,160,160))
    text_c(d, (W//2, H//2 - 60), game.headers["White"], font(90)); text_c(d, (W//2, H//2 + 40), "vs", font(50), (160,160,160))
    text_c(d, (W//2, H//2 + 140), game.headers["Black"], font(90))
    return im

def main(pgn, out, sec=2.5):
    game = chess.pgn.read_game(open(pgn, encoding="utf-8"))
    tmp = out + ".frames"; os.makedirs(tmp, exist_ok=True); n = 0; durs = []
    def save(im, dur):
        nonlocal n; im.save(f"{tmp}/{n:04d}.png"); durs.append(dur); n += 1
    save(title(game), 3)
    moves = list(game.mainline()); total = len(moves)
    save(frame(game, chess.Board(), None, 0, total), sec)
    for i, node in enumerate(moves, 1):
        b = node.board(); last = node.move
        end = i == total
        save(frame(game, b, last, i, total, END_TXT.get(game.headers.get("Termination"), game.headers.get("Termination")) + "  " + game.headers["Result"] if end else None), 4 if end else sec)
    with open(f"{tmp}/list.txt", "w") as f:
        for i, dur in enumerate(durs): f.write(f"file '{i:04d}.png'\nduration {dur}\n")
        f.write(f"file '{n-1:04d}.png'\n")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-i", f"{tmp}/list.txt",
                    "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "20", out], check=True)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
