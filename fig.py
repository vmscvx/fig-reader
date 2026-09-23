"""Дерево узлов из canvas.json: поиск кадров и печать поддерева.

    python fig.py find "Каталог"          # кадры/секции/символы с подстрокой в имени
    python fig.py tree 706:38090 4        # поддерево узла на 4 уровня: тип, имя, x,y, размер, текст

canvas.json берётся из текущей папки или из переменной FIG_CANVAS.
"""
import base64, json, os, struct, sys

_J = json.load(open(os.environ.get("FIG_CANVAS", "canvas.json"), encoding="utf8"))
N = _J["nodes"]
BLOBS = _J.get("blobs", [])


def gid(g):
    return f"{g['sessionID']}:{g['localID']}"


BY = {gid(n["guid"]): n for n in N}
KIDS = {}
for n in N:
    p = n.get("parentIndex")
    if p:
        KIDS.setdefault(gid(p["guid"]), []).append(n)
for v in KIDS.values():
    v.sort(key=lambda n: n["parentIndex"]["position"])


def svg_path(blob_index):
    """commandsBlob -> SVG d. Команда — байт, аргументы float32 LE (как у OpenPencil:
    0 Z, 1 M x y, 2 L x y, 3 Q x1 y1 x y, 4 C x1 y1 x2 y2 x y)."""
    b = base64.b64decode(BLOBS[blob_index]); i = 0; out = []
    argc = {0: 0, 1: 2, 2: 2, 3: 4, 4: 6}
    while i < len(b):
        c = b[i]; i += 1
        if c not in argc:
            break
        a = struct.unpack_from(f"<{argc[c]}f", b, i); i += 4 * argc[c]
        out.append("ZMLQC"[c] + " ".join(f"{v:.2f}" for v in a))
    return "".join(out)


def path(n):
    out = []
    while n:
        out.append(n.get("name", "?"))
        p = n.get("parentIndex")
        n = BY.get(gid(p["guid"])) if p else None
    return " / ".join(reversed(out))


def line(n):
    t, sz = n.get("transform", {}), n.get("size", {})
    s = f'{n.get("type")} {gid(n["guid"])} "{n.get("name", "")}"'
    if n.get("type") == "INSTANCE" and n.get("symbolData", {}).get("symbolID"):
        s += " -> " + BY.get(gid(n["symbolData"]["symbolID"]), {}).get("name", "?")
    s += f' {t.get("m02", 0):.0f},{t.get("m12", 0):.0f} {sz.get("x", 0):.0f}x{sz.get("y", 0):.0f}'
    if n.get("type") == "TEXT":
        s += " " + repr(n.get("textData", {}).get("characters", "")[:80])
    return s


def tree(g, depth, d=0):
    print("  " * d + line(BY[g]))
    if d < depth:
        for k in KIDS.get(g, []):
            tree(gid(k["guid"]), depth, d + 1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "find":
        q = sys.argv[2].lower()
        for n in N:
            if n.get("type") in ("FRAME", "SECTION", "SYMBOL", "CANVAS") and q in n.get("name", "").lower():
                print(line(n), "|", path(n))
    elif cmd == "tree":
        tree(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 3)
    else:
        print(__doc__)
