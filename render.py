"""Кадр Figma -> HTML для сверки глазами.

    python render.py "макет.fig" 706:38090 frame.html

Раскладка абсолютная, по transform и size узлов: заливки (цвет, градиент,
картинка из images/ внутри .fig с кадрированием по transform заливки),
скругления, обводки, тексты со шрифтом и цветом, векторы и иконки по
fillGeometry/strokeGeometry, инстансы через символ с оверрайдами.
Не рисуются эффекты (тени, размытие), повороты узлов и перестроение
auto-layout у растянутых инстансов — это инструмент «посмотреть», а не
пиксель в пиксель.
"""
import base64, html, os, sys, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fig import BY, KIDS, gid, svg_path
Z = zipfile.ZipFile(sys.argv[1]) if __name__ == "__main__" else None
NAMES = set(Z.namelist()) if Z else set()

def rgba(c, op=1.0):
    return f"rgba({round(c['r']*255)},{round(c['g']*255)},{round(c['b']*255)},{c.get('a',1)*op:.3f})"

def img_url(h):
    p = f"images/{h}"
    if p not in NAMES: return None
    b = Z.read(p); mime = "image/png" if b[:4] == b"\x89PNG" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(b).decode()}"

VECTOR_TYPES = {"VECTOR", "BOOLEAN_OPERATION", "STAR", "LINE", "ELLIPSE", "REGULAR_POLYGON"}


def paint_color(paints):
    for p in paints or []:
        if p.get("visible") is False: continue
        if p["type"] == "SOLID": return rgba(p["color"], p.get("opacity", 1))
        if p["type"].startswith("GRADIENT") and p.get("stops"): return rgba(p["stops"][0]["color"])
    return None


def image_tag(p, w, h):
    """Картинка с кадрированием: для CROP/TILE (в .fig CROP хранится как STRETCH)
    матрица = scale(w, h) · T⁻¹ · scale(1/imgW, 1/imgH), как в OpenPencil
    (packages/core/src/canvas/fills.ts)."""
    u = img_url(p.get("image", {}).get("hash", ""))
    if not u: return ""
    t, iw, ih = p.get("transform"), p.get("originalImageWidth"), p.get("originalImageHeight")
    mode = p.get("imageScaleMode", "FILL")
    if t and iw and ih and mode in ("STRETCH", "CROP", "TILE"):
        a, b, c, d, e, f = t["m00"], t["m01"], t["m02"], t["m10"], t["m11"], t["m12"]
        det = a * e - b * d
        if det:
            ia, ib, id_, ie = e / det, -b / det, -d / det, a / det
            ic, if_ = -(ia * c + ib * f), -(id_ * c + ie * f)
            # точка картинки (px) -> узел (px)
            m = (w * ia / iw, h * id_ / iw, w * ib / ih, h * ie / ih, w * ic, h * if_)
            return (f'<img src="{u}" style="position:absolute;left:0;top:0;width:{iw}px;height:{ih}px;'
                    f'max-width:none;transform-origin:0 0;transform:matrix({",".join(f"{v:.5f}" for v in m)})">')
    fit = "contain" if mode == "FIT" else "cover"
    return f'<img src="{u}" style="position:absolute;inset:0;width:100%;height:100%;object-fit:{fit}">'


def key(n): 
    k = n.get("overrideKey") or n["guid"]; return f"{k['sessionID']}:{k['localID']}"

def render(n, ov, out, root=False):
    if n.get("visible") is False: return
    o = dict(ov.get((key(n),), {}))
    typ = n.get("type"); kids = KIDS.get(gid(n["guid"]), []); sub = ov
    if typ == "INSTANCE" and n.get("symbolData", {}).get("symbolID") and BY.get(gid(n["symbolData"]["symbolID"])):
        sym = BY[gid(n["symbolData"]["symbolID"])]
        kids = KIDS.get(gid(sym["guid"]), [])
        sub = dict(ov)
        for so in n["symbolData"].get("symbolOverrides") or []:
            path = tuple(f"{g['sessionID']}:{g['localID']}" for g in so["guidPath"]["guids"])
            sub[path] = {**sub.get(path, {}), **so}
        # оверрайд с путём на сам символ красит корень инстанса (фон карточки)
        o = {**o, **sub.get((key(sym),), {})}
        if "fillPaints" not in o and "fillPaints" not in n: o["fillPaints"] = sym.get("fillPaints")
        if not n.get("cornerRadius") and sym.get("cornerRadius"): n = {**n, "cornerRadius": sym["cornerRadius"]}
    t = n.get("transform", {}); sz = n.get("size", {})
    x = 0 if root else t.get("m02", 0); y = 0 if root else t.get("m12", 0)
    w, h = sz.get("x", 0), sz.get("y", 0)
    st = [f"left:{x:.0f}px;top:{y:.0f}px;width:{w:.0f}px;height:{h:.0f}px"]
    fills = o.get("fillPaints", n.get("fillPaints")) or []
    bg = []
    for p in fills:
        if p.get("visible") is False: continue
        if p["type"] == "SOLID" and typ != "TEXT": bg.append(f"linear-gradient({rgba(p['color'], p.get('opacity',1))},{rgba(p['color'], p.get('opacity',1))})")
        elif p["type"].startswith("GRADIENT") and p.get("stops"):
            bg.append("linear-gradient(90deg," + ",".join(f"{rgba(s['color'])} {s['position']*100:.0f}%" for s in p["stops"]) + ")")
    imgs = "".join(image_tag(p, w, h) for p in fills if p["type"] == "IMAGE" and p.get("visible") is not False)
    if typ in VECTOR_TYPES: bg = []  # у векторов заливка — это цвет контура, а не фон
    if bg: st.append("background:" + ",".join(reversed(bg)))
    if imgs: st.append("overflow:hidden")  # картинка кадрируется рамкой узла
    r = n.get("cornerRadius")
    if r: st.append(f"border-radius:{r:.0f}px")
    elif n.get("rectangleTopLeftCornerRadius") is not None and n.get("rectangleCornerRadiiIndependent"):
        st.append("border-radius:" + " ".join(f"{n.get(k,0):.0f}px" for k in ("rectangleTopLeftCornerRadius","rectangleTopRightCornerRadius","rectangleBottomRightCornerRadius","rectangleBottomLeftCornerRadius")))
    strokes = [p for p in (n.get("strokePaints") or []) if p.get("visible") is not False and p["type"] == "SOLID"]
    if strokes and n.get("strokeWeight") and typ not in VECTOR_TYPES: st.append(f"box-shadow:inset 0 0 0 {n['strokeWeight']:.0f}px {rgba(strokes[0]['color'], strokes[0].get('opacity',1))}")
    if n.get("frameMaskDisabled") is False or n.get("clipsContent"): st.append("overflow:hidden")
    if n.get("opacity") is not None and n.get("opacity") < 1: st.append(f"opacity:{n['opacity']}")
    inner = ""
    if typ == "TEXT":
        td = o.get("textData", n.get("textData", {}))
        col = next((rgba(p["color"], p.get("opacity",1)) for p in fills if p["type"] == "SOLID"), "#000")
        fn = n.get("fontName", {}); style = fn.get("style", "")
        wt = 800 if "Extra" in style else 700 if "Bold" in style else 600 if "Semi" in style else 500 if "Medium" in style else 400
        lh = n.get("lineHeight", {})
        lhs = {"PIXELS": f"line-height:{lh.get('value', 0):.0f}px;", "RAW": f"line-height:{lh.get('value', 0):.2f};",
               "PERCENT": f"line-height:{lh.get('value', 0):.0f}%;"}.get(lh.get("units"), "")
        al = {"CENTER": "center", "RIGHT": "right"}.get(n.get("textAlignHorizontal"), "left")
        # «Авто-ширина» в Figma — текст в одну строку: не даём браузеру переносить
        ws = "pre" if n.get("textAutoResize") == "WIDTH_AND_HEIGHT" else "pre-wrap"
        st.append(f"color:{col};font-family:'{fn.get('family','Manrope')}',Manrope,sans-serif;font-weight:{wt};font-size:{n.get('fontSize',14):.0f}px;{lhs}text-align:{al};white-space:{ws}")
        inner = html.escape(td.get("characters", ""))
    if typ in VECTOR_TYPES:
        paths = []
        fc, sc = paint_color(fills), paint_color(n.get("strokePaints"))
        for g in n.get("fillGeometry") or []:
            if fc and g.get("commandsBlob") is not None:
                paths.append(f'<path d="{svg_path(g["commandsBlob"])}" fill="{fc}" fill-rule="{"evenodd" if g.get("windingRule") == "ODD" else "nonzero"}"/>')
        for g in n.get("strokeGeometry") or []:
            if sc and g.get("commandsBlob") is not None:
                paths.append(f'<path d="{svg_path(g["commandsBlob"])}" fill="{sc}"/>')
        inner = f'<svg width="{w:.1f}" height="{h:.1f}" style="position:absolute;left:0;top:0;overflow:visible">{"".join(paths)}</svg>'
        kids = []  # у BOOLEAN_OPERATION результат уже в геометрии родителя
    out.append(f'<div title="{html.escape(n.get("name",""))}" style="position:absolute;{";".join(st)}">{imgs}{inner}')
    # вложенные оверрайды: срезаем первый элемент пути
    for k in kids:
        kk = key(k); nested = {p[1:]: v for p, v in sub.items() if len(p) > 1 and p[0] == kk}
        render(k, {**sub, **nested}, out)
    out.append("</div>")

if __name__ == "__main__":
    n = BY[sys.argv[2]]; out = []
    render(n, {}, out, root=True)
    w, h = n["size"]["x"], n["size"]["y"]
    open(sys.argv[3], "w", encoding="utf8").write(
        f'<!doctype html><meta charset="utf-8"><link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">'
        f'<body style="margin:0;background:#ccc"><div style="position:relative;width:{w:.0f}px;height:{h:.0f}px;font-family:Manrope">{"".join(out)}</div>')
    print("ok", w, h)
