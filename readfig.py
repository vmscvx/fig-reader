"""Разбор .fig (Figma) без Figma: zip -> canvas.fig -> kiwi-схема + данные -> canvas.json.

    python readfig.py "макет.fig" [canvas.json]

canvas.json = {"nodes": [...все узлы...], "blobs": [base64, ...]}. Байтовые поля
узлов (хеши картинок) — hex; blobs — контуры векторов (commandsBlob) и сетки.

Контейнер (openpencil.dev/reference/file-format, dev.to «How Figma stores your
design files»): "fig-kiwi" 8 байт, версия uint32 LE, дальше куски
«uint32 LE длина + данные»: 0 — kiwi-схема (raw deflate), 1 — сообщение
(zstd, если начинается с 28 B5 2F FD, иначе raw deflate).

Чтение значений — один в один с evanw/kiwi js/bb.ts и js/binary.ts
(https://github.com/evanw/kiwi/tree/master/js).
"""
import base64, json, struct, sys, zipfile, zlib
from compression import zstd

def unpack(b):
    return zstd.decompress(b) if b[:4] == b"\x28\xb5\x2f\xfd" else zlib.decompress(b, -15)

class R:
    """ByteBuffer из kiwi/js/bb.ts."""
    def __init__(s, b): s.b = b; s.i = 0
    def byte(s): v = s.b[s.i]; s.i += 1; return v
    def vu(s):  # readVarUint: не больше 5 байт, результат uint32
        v = 0; sh = 0
        while True:
            c = s.byte(); v |= (c & 127) << sh; sh += 7
            if not (c & 128 and sh < 35): return v & 0xFFFFFFFF
    def vi(s):  # readVarInt: (uint | 0), затем зигзаг
        v = s.vu()
        return ~(v >> 1) if v & 1 else v >> 1
    def vu64(s):  # readVarUint64: девятый байт берётся целиком
        v = 0; sh = 0
        while True:
            c = s.byte()
            if not (c & 128 and sh < 56): return v | (c << sh)
            v |= (c & 127) << sh; sh += 7
    def vi64(s):
        v = s.vu64(); return ~(v >> 1) if v & 1 else v >> 1
    def f(s):  # readVarFloat: 0 — один байт, иначе 4 байта с экспонентой в младших битах
        c = s.b[s.i]
        if c == 0: s.i += 1; return 0.0
        bits = struct.unpack_from("<I", s.b, s.i)[0]; s.i += 4
        bits = ((bits << 23) | (bits >> 9)) & 0xFFFFFFFF
        return struct.unpack("<f", struct.pack("<I", bits))[0]
    def s(s):  # readString: UTF-8 до нулевого байта
        j = s.b.index(0, s.i); v = s.b[s.i:j].decode("utf8", "replace"); s.i = j + 1; return v

def schema(b):
    r = R(b); defs = []
    for _ in range(r.vu()):
        name = r.s(); kind = r.byte(); fields = []
        for _ in range(r.vu()):
            fields.append((r.s(), r.vi(), r.byte() & 1, r.vu()))
        defs.append((name, kind, fields))
    return defs

def decoder(defs):
    by = {d[0]: d for d in defs}
    # Встроенные типы: ~индекс в [bool, byte, int, uint, float, string, int64, uint64]
    prim = {-1: lambda r: bool(r.byte()), -2: R.byte, -3: R.vi, -4: R.vu, -5: R.f, -6: R.s, -7: R.vi64, -8: R.vu64}
    def val(r, t):
        if t < 0: return prim[t](r)
        name, kind, fields = defs[t]
        if kind == 0:
            v = r.vu()
            for fn, _, _, fv in fields:
                if fv == v: return fn
            return v
        if kind == 1:
            return {fn: field(r, ft, arr) for fn, ft, arr, _ in fields}
        out = {}; idx = {fv: (fn, ft, arr) for fn, ft, arr, fv in fields}
        while True:
            k = r.vu()
            if k == 0: return out
            if k not in idx: raise ValueError(f"{name}: неизвестное поле {k}")
            fn, ft, arr = idx[k]; out[fn] = field(r, ft, arr)
    def field(r, t, arr):
        if arr:
            n = r.vu()
            if t == -2:  # readByteArray
                v = r.b[r.i:r.i + n]; r.i += n; return v
            return [val(r, t) for _ in range(n)]
        return val(r, t)
    return lambda b: val(R(b), next(i for i, d in enumerate(defs) if d[0] == "Message"))

def read_canvas(path):
    """Узлы документа (nodeChanges) и blobs из .fig-файла."""
    # .fig из «Save local copy» — zip с canvas.fig внутри; старые файлы — сам canvas.fig
    raw = zipfile.ZipFile(path).read("canvas.fig") if zipfile.is_zipfile(path) else open(path, "rb").read()
    if raw[:8] != b"fig-kiwi":
        raise ValueError("не fig-kiwi: " + raw[:8].hex())
    i = 12; chunks = []
    while i + 4 <= len(raw):
        n = struct.unpack_from("<I", raw, i)[0]; chunks.append(raw[i + 4:i + 4 + n]); i += 4 + n
    defs = schema(unpack(chunks[0]))
    msg = decoder(defs)(unpack(chunks[1]))
    return msg.get("nodeChanges", []), [b.get("bytes") or b"" for b in msg.get("blobs", [])]


if __name__ == "__main__":
    nodes, blobs = read_canvas(sys.argv[1])
    out = sys.argv[2] if len(sys.argv) > 2 else "canvas.json"
    json.dump({"nodes": nodes, "blobs": [base64.b64encode(b).decode() for b in blobs]},
              open(out, "w", encoding="utf8"), ensure_ascii=False, default=lambda b: b.hex())
    print(len(nodes), "nodes,", len(blobs), "blobs ->", out)
