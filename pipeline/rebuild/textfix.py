"""Rebuild: make the OCR text right.

1. re-read every block per LINE with several variants (as is, stretched sideways for
   condensed display fonts, clean black-on-white from the glyph mask) and keep the reading
   that is both confident and made of real words;
2. fix words: letter-spaced tracking ("0 0 2" -> "002"), glued words ("YOUARE" -> "YOU ARE"),
   one-letter slips using the design's own words ("KINRAV" -> "KINRAVA") or a dictionary
   ("BUOKS" -> "BOOKS"), contractions ("ISNT" -> "ISN'T"), end punctuation (":" -> ".");
3. blocks on the same line with the same style become one text ("No" + "perfect day...").
"""
from __future__ import annotations

import logging
import re

import cv2
import numpy as np

log = logging.getLogger("split")

_CONTRACT = {"ISNT": "ISN'T", "DONT": "DON'T", "CANT": "CAN'T", "WONT": "WON'T", "DOESNT": "DOESN'T",
             "DIDNT": "DIDN'T", "YOURE": "YOU'RE", "THEYRE": "THEY'RE", "WERE'": "WE'RE", "IM": "I'M",
             "IVE": "I'VE", "LETS": "LET'S", "THATS": "THAT'S", "WHATS": "WHAT'S", "HERES": "HERE'S"}


def _lm():
    try:
        import wordninja

        return wordninja, wordninja.DEFAULT_LANGUAGE_MODEL._wordcost
    except Exception:  # noqa: BLE001
        return None, {}


def _rank_ok(w, cost, max_cost):
    return w in cost and cost[w] <= max_cost


def _case_like(src, dst):
    if src.isupper():
        return dst.upper()
    if src[:1].isupper():
        return dst[:1].upper() + dst[1:]
    return dst


def _edits1(w):
    letters = "abcdefghijklmnopqrstuvwxyz"
    splits = [(w[:i], w[i:]) for i in range(len(w) + 1)]
    return {a + b[1:] for a, b in splits if b} | {a + b[1] + b[0] + b[2:] for a, b in splits if len(b) > 1} | \
        {a + ch + b[1:] for a, b in splits if b for ch in letters} | {a + ch + b for a, b in splits for ch in letters}


def _ed(a, b):
    d = np.arange(len(b) + 1)
    for i, ca in enumerate(a, 1):
        prev, d[0] = d[0], i
        for j, cb in enumerate(b, 1):
            cur = min(d[j] + 1, d[j - 1] + 1, prev + (ca != cb))
            prev, d[j] = d[j], cur
    return int(d[len(b)])


def score_text(t, cost, vocab, c):
    """confidence bonus for readings made of real words."""
    toks = re.findall(r"[A-Za-z]+|\d+", t)
    if not toks:
        return 0.0
    good = 0
    for tk in toks:
        lw = tk.lower()
        if tk.isdigit() or vocab.get(lw, 0) >= 2 or lw in cost or len(tk) == 1 and lw in "ai":
            good += 1
    return good / len(toks)


def fix_word(tok, cost, vocab, wn, c, protect=False):
    m = re.match(r"^([^A-Za-z0-9]*)([A-Za-z0-9']+)([^A-Za-z0-9]*)$", tok)
    if not m:
        return tok
    pre, core, post = m.groups()
    up = core.upper()
    if up in _CONTRACT:
        return pre + _case_like(core, _CONTRACT[up]) + post
    lw = core.lower()
    if core.isdigit():
        # a number that is one digit off a number used elsewhere in the design ("062" vs "002")
        for v in vocab:
            if v.isdigit() and len(v) == len(core) and v != core and _ed(v, core) == 1 and vocab[v] > vocab.get(core, 0):
                return pre + v + post
        return tok
    if not core.isalpha() or len(core) < 3:
        return tok
    if lw in vocab and vocab[lw] > 1 or lw in cost:  # a real word is never "corrected"
        return tok
    if protect:  # brand / logo words are not in any dictionary: keep, only the design's own spelling
        for v, n in vocab.items():
            if v != lw and v.isalpha() and len(v) == len(lw) + 1 and _ed(v, lw) == 1 and n >= 1:
                return pre + _case_like(core, v) + post
        return tok
    # 1) the design's own words (brand names!)
    for v, n in sorted(vocab.items(), key=lambda kv: -kv[1]):
        if v != lw and v.isalpha() and len(v) >= 4 and _ed(v, lw) == 1 and n >= vocab.get(lw, 0):
            return pre + _case_like(core, v) + post
    # 2) glued words: "youare" -> "you are"
    if wn is not None and len(lw) >= 5:
        parts = wn.split(lw)
        if len(parts) > 1 and all(len(p) >= 2 and _rank_ok(p, cost, c.text_split_max_cost) for p in parts):
            return pre + " ".join(_case_like(core, p) for p in parts) + post
        if len(parts) == 2:  # "fuefor" -> fue + for -> fuel + for (one missing letter only)
            fixed = []
            for p in parts:
                if _rank_ok(p, cost, c.text_split_max_cost):
                    fixed.append(p)
                    continue
                cands = [w for w in _edits1(p) if len(w) == len(p) + 1 and _rank_ok(w, cost, c.text_split_max_cost)]
                if not cands or len(p) < 3:
                    fixed = None
                    break
                fixed.append(min(cands, key=lambda w: cost[w]))
            if fixed and sum(a != b for a, b in zip(fixed, parts)) == 1:
                return pre + " ".join(_case_like(core, p) for p in fixed) + post
    # 3) one-letter slip against the dictionary ("buoks" -> "books")
    if len(lw) >= 4:
        cands = [w for w in _edits1(lw) if _rank_ok(w, cost, c.text_dict_max_cost)]
        if cands:
            return pre + _case_like(core, min(cands, key=lambda w: cost[w])) + post
    return tok


def fix_text(t, cost, vocab, wn, c, protect=False):
    t = re.sub(r"\s+", " ", t).strip()
    letters = [ch for ch in t if ch.isalpha()]
    if letters and sum(ch.isupper() for ch in letters) >= 0.75 * len(letters):
        t = t.upper()  # an all-caps line read with a stray lower-case letter ("FoR")
    toks = t.split(" ")
    # tracking: "0 0 2" / "K I N R A V A" -> one word
    if len(toks) >= 3 and all(len(x) == 1 and x.isalnum() for x in toks):
        toks = ["".join(toks)]
    toks = [fix_word(x, cost, vocab, wn, c, protect) for x in toks]
    t = " ".join(toks)
    t = re.sub(r";(\s)", r",\1", t)
    t = re.sub(r":$", ".", t)
    return t


def _lines(gm, min_gap):
    rows = gm.any(1)
    out, start, gap = [], None, 0
    for y, r in enumerate(rows):
        if r:
            if start is None:
                start = y
            gap = 0
            end = y
        elif start is not None:
            gap += 1
            if gap >= min_gap:
                out.append((start, end + 1))
                start = None
    if start is not None:
        out.append((start, end + 1))
    return out


def _clean(t):
    t = t.strip()
    t = re.sub(r"^[^A-Za-z0-9\"'(]+", "", t)
    t = re.sub(r"_$", ".", t)
    t = re.sub(r"[^A-Za-z0-9.!?'\")%]+$", "", t)
    return t


def _keep_end_punct(old, new):
    o = old.strip()
    if o and o[-1] in ".!?" and new and new[-1] not in ".!?":
        new = new.rstrip(":;,_") + o[-1]
    return new


def _read(reader, im):
    try:
        res = reader.readtext(im, detail=1, paragraph=False)
    except Exception:  # noqa: BLE001
        return "", 0.0
    if not res:
        return "", 0.0
    res.sort(key=lambda r: min(p[0] for p in r[0]))
    txt = " ".join(r[1] for r in res)
    conf = float(np.average([r[2] for r in res], weights=[max(len(r[1]), 1) for r in res]))
    return txt, conf


def reread(blocks, img_u8, glyphs, models, c, batch_vocab=None):
    """Re-read each block line by line with variants; keep the best (confidence + real words)."""
    wn, cost = _lm()
    vocab = {}
    for b in blocks:
        for tk in re.findall(r"[A-Za-z]+|\d+", str(b["text"])):
            vocab[tk.lower()] = vocab.get(tk.lower(), 0) + 1
    H, W = img_u8.shape[:2]
    reader = models.ocr
    for b in blocks:
        x, y, w, h = b["ocr_bbox"]
        p = int(0.25 * h) + 2
        px_ = int(c.text_side_pad * h) + 2  # letters just outside the OCR box (a cut-off "H")
        x0, y0, x1, y1 = max(x - px_, 0), max(y - p, 0), min(x + w + px_, W), min(y + h + p, H)
        gm = glyphs[y0:y1, x0:x1].astype(np.uint8)
        ncc, ccl, cst, _ = cv2.connectedComponentsWithStats(gm, connectivity=8)
        bx0, bx1, by0_, by1_ = x - x0, x - x0 + w, y - y0, y - y0 + h
        keepc = np.zeros(ncc, bool)
        for k_ in range(1, ncc):
            cx0, cy0, cw, ch_ = cst[k_, :4]
            # overlaps the OCR box (a letter cut by its edge counts, a neighbouring word does not)
            if cx0 < bx1 and cx0 + cw > bx0 and cy0 < by1_ and cy0 + ch_ > by0_:
                keepc[k_] = True
        gm = keepc[ccl]
        if gm.sum() < 20:
            continue
        lines = _lines(gm, max(2, int(0.08 * h)))
        if not lines:
            continue
        # only lines that belong to THIS block (padding may catch the neighbours above/below)
        by0, by1 = y - y0, y - y0 + h
        lines = [(s_, e_) for s_, e_ in lines if (min(e_, by1) - max(s_, by0)) >= 0.6 * (e_ - s_)]
        if not lines:
            continue
        line_h = np.median([e - s for s, e in lines])
        lines = [(s, e) for s, e in lines if e - s >= 0.35 * line_h]
        texts, confs = [], []
        for s, e in lines:
            lp = max(2, int(0.2 * (e - s)))
            ys, ye = max(s - lp, 0), min(e + lp, gm.shape[0])
            band = gm[ys:ye]
            cols = np.nonzero(band.any(0))[0]
            if not len(cols):
                continue
            xs, xe = max(cols.min() - lp, 0), min(cols.max() + 1 + lp, gm.shape[1])
            rgb = img_u8[y0 + ys:y0 + ye, x0 + xs:x0 + xe]
            bw = np.where(cv2.dilate(band[:, xs:xe].astype(np.uint8), np.ones((2, 2), np.uint8))[..., None] > 0,
                          0, 255).astype(np.uint8).repeat(3, -1)
            best = None
            allread = []
            for src in (rgb, bw):
                for sx in c.text_stretch:
                    hh = int(c.text_line_px)
                    sc = hh / max(src.shape[0], 1)
                    im = cv2.resize(src, (max(8, int(src.shape[1] * sc * sx)), hh), interpolation=cv2.INTER_CUBIC)
                    im = cv2.copyMakeBorder(im, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=(255, 255, 255) if src is bw
                                            else tuple(int(v) for v in np.median(src.reshape(-1, 3), 0)))
                    t, cf = _read(reader, im)
                    if not t:
                        continue
                    allread.append((t, cf))
                    sc_ = cf + c.text_word_bonus * score_text(t, cost, vocab, c)
                    if best is None or sc_ > best[0]:
                        best = (sc_, t, cf)
            digits = [re.sub(r"\s", "", t) for t, _ in allread if re.fullmatch(r"[\d\s]+", t.strip())]
            if best and len(digits) >= 3:  # numbers: majority of all readings ("062" vs "002")
                vals, cnt = np.unique(digits, return_counts=True)
                if cnt.max() >= 2:
                    best = (best[0], str(vals[cnt.argmax()]), best[2])
            if best:
                texts.append(best[1])
                confs.append(best[2])
        # a letter the OCR skipped: more letter shapes than letters read ("FINIS" + H)
        word = str(b["text"]).strip()
        if len(lines) == 1 and re.fullmatch(r"[A-Za-z]+[.!?]?", word):
            core_ = re.sub(r"[.!?]$", "", word)
            ncc2, _, cst2, _ = cv2.connectedComponentsWithStats(gm.astype(np.uint8), connectivity=8)
            hh_ = [cst2[k_, 3] for k_ in range(1, ncc2)]
            big_ = [k_ for k_ in range(1, ncc2) if hh_ and cst2[k_, 3] >= 0.5 * max(hh_)]
            if big_:
                ws_ = np.array([cst2[k_, 2] for k_ in big_], np.float64)
                mw = np.median(ws_)
                # letters glued together count by their width
                letters_ = int(sum(max(1, int(round(w_ / mw))) for w_ in ws_))
            else:
                letters_ = 0
            if letters_ == len(core_) + 1:
                cands = [w_ for w_ in _edits1(core_.lower()) if len(w_) == len(core_) + 1
                         and _rank_ok(w_, cost, c.text_dict_max_cost)]
                if cands:
                    best_w = min(cands, key=lambda w_: cost[w_])
                    log.info("  huruf terlewat (%d bentuk huruf): %r -> %r", letters_, word,
                             _case_like(core_, best_w) + word[len(core_):])
                    b["text"] = _case_like(core_, best_w) + word[len(core_):]
                    continue
        log.debug("  baca ulang %r: %d baris -> %r", b["text"], len(lines), texts)
        if not texts:
            continue
        texts = [_clean(t) for t in texts]
        new = "\n".join(texts) if len(texts) > 1 else texts[0]
        old = str(b["text"])
        new = _keep_end_punct(old, new)
        ws_old = score_text(old, cost, vocab, c)
        ws_new = score_text(new.replace("\n", " "), cost, vocab, c)
        n_old = len(re.findall(r"[A-Za-z0-9]", old))
        n_new = len(re.findall(r"[A-Za-z0-9]", new))
        if re.fullmatch(r"[\d\s]+", old) and re.fullmatch(r"\d+", new) and new != re.sub(r"\s", "", old):
            log.info("  angka dibaca ulang (mayoritas): %r -> %r", old, new)
            b["text"] = new
            continue
        weird = bool(re.search(r"[^A-Za-z0-9\s.,!?'\"\-:;&%/()\n]", new))
        cf_new = float(np.mean(confs))
        # a fuller reading of the same word ("FINIS" -> "FINISH"): more letters, still real words
        fuller = (ws_new >= ws_old and ws_new >= 0.99 and n_new > n_old and
                  _ed(re.sub(r"\W", "", new.lower()), re.sub(r"\W", "", old.lower())) <= 2 and cf_new >= b["confidence"] - 0.05)
        better = (ws_new >= c.text_reread_min_words and ws_new > ws_old + 1e-6) or fuller
        if (better and not weird and n_new >= 0.8 * n_old and new.replace("\n", " ").strip() != old.strip()):
            log.info("  teks dibaca ulang: %r -> %r", b["text"], new)
            b["text"] = new
            b["confidence"] = round(cf_new, 3)
    # vocabulary of the (re-read) design for the word fixes
    vocab = {}
    for b in blocks:
        for tk in re.findall(r"[A-Za-z]+|\d+", str(b["text"]).replace(" ", "") if
                             all(len(x) == 1 for x in str(b["text"]).split()) else str(b["text"])):
            vocab[tk.lower()] = vocab.get(tk.lower(), 0) + 1
    for k, n in (batch_vocab or {}).items():  # brand words seen in the other designs of the batch
        vocab[k] = vocab.get(k, 0) + n
    for b in blocks:
        lines_ = str(b["text"]).split("\n")
        logo = (b["y"] < c.text_logo_top * H and len(str(b["text"]).split()) <= 2
                and b["h"] < c.text_logo_max_h * H)
        fixed = "\n".join(fix_text(ln, cost, vocab, wn, c, protect=logo) for ln in lines_)
        if fixed != b["text"]:
            log.info("  teks dibetulkan: %r -> %r", b["text"], fixed)
            b["text"] = fixed
    return merge_same_line(blocks)


c_par_gap = 0.6


def merge_same_line(blocks):
    """Pieces of one line of text (same size, colour, baseline; small gap) -> one block."""
    def rgb(hx):
        return np.array([int(hx[i:i + 2], 16) for i in (1, 3, 5)])

    out = sorted(blocks, key=lambda b: (b["y"], b["x"]))
    changed = True
    while changed:
        changed = False
        for i in range(len(out)):
            for j in range(len(out)):
                if i == j:
                    continue
                a, b = out[i], out[j]
                if "\n" in str(a["text"]) or "\n" in str(b["text"]):
                    continue
                if not (0.75 <= a["h"] / max(b["h"], 1) <= 1.33):
                    continue
                if abs((a["y"] + a["h"] / 2) - (b["y"] + b["h"] / 2)) > 0.3 * max(a["h"], b["h"]):
                    continue
                gap = b["x"] - (a["x"] + a["w"])
                if gap < -0.2 * a["h"] or gap > 1.5 * max(a["h"], b["h"]):
                    continue
                if np.abs(rgb(a["color_hex"]) - rgb(b["color_hex"])).sum() > 90:
                    continue
                x0, y0 = min(a["x"], b["x"]), min(a["y"], b["y"])
                x1, y1 = max(a["x"] + a["w"], b["x"] + b["w"]), max(a["y"] + a["h"], b["y"] + b["h"])
                a.update(text=f"{a['text']} {b['text']}", x=x0, y=y0, w=x1 - x0, h=y1 - y0)
                ob = a["ocr_bbox"]
                bb = b["ocr_bbox"]
                bx0, by0 = min(ob[0], bb[0]), min(ob[1], bb[1])
                bx1, by1 = max(ob[0] + ob[2], bb[0] + bb[2]), max(ob[1] + ob[3], bb[1] + bb[3])
                a["ocr_bbox"] = [bx0, by0, bx1 - bx0, by1 - by0]
                log.info("  teks satu baris digabung: %r", a["text"])
                out.pop(j)
                changed = True
                break
            if changed:
                break
    # lines of one paragraph (same left edge, size, colour; tight spacing) -> one block
    out = sorted(out, key=lambda b: (b["y"], b["x"]))
    changed = True
    while changed:
        changed = False
        for i in range(len(out)):
            for j in range(len(out)):
                if i == j:
                    continue
                a, b = out[i], out[j]
                la = str(a["text"]).count("\n") + 1
                lh_a, lh_b = a["h"] / la, b["h"] / (str(b["text"]).count("\n") + 1)
                if not (0.7 <= lh_a / max(lh_b, 1) <= 1.4):
                    continue
                if abs(a["x"] - b["x"]) > 0.3 * lh_a:
                    continue
                gap = b["y"] - (a["y"] + a["h"])
                if gap < -0.2 * lh_a or gap > c_par_gap * lh_a:
                    continue
                if np.abs(rgb(a["color_hex"]) - rgb(b["color_hex"])).sum() > 90:
                    continue
                if a["h"] > 0.12 * 2000 or len(str(a["text"])) < 2:
                    continue
                x0, y0 = min(a["x"], b["x"]), a["y"]
                x1, y1 = max(a["x"] + a["w"], b["x"] + b["w"]), b["y"] + b["h"]
                a.update(text=f"{a['text']}\n{b['text']}", x=x0, y=y0, w=x1 - x0, h=y1 - y0)
                ob, bb = a["ocr_bbox"], b["ocr_bbox"]
                bx0, by0 = min(ob[0], bb[0]), min(ob[1], bb[1])
                bx1, by1 = max(ob[0] + ob[2], bb[0] + bb[2]), max(ob[1] + ob[3], bb[1] + bb[3])
                a["ocr_bbox"] = [bx0, by0, bx1 - bx0, by1 - by0]
                log.info("  paragraf digabung: %r", a["text"])
                out.pop(j)
                changed = True
                break
            if changed:
                break
    for i, b in enumerate(out, 1):
        b["id"] = i
    return out
