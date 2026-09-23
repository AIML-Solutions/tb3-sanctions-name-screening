#!/usr/bin/env python3
"""Sanctions screening engine.

Decides, for every customer record, whether it refers to the same person,
company or vessel as a watchlist entry, under the rules of
``screening_policy.md``: transliteration equivalence for Arabic, Persian and
Cyrillic romanisations, Chinese romanisations of company stems, name order,
particles, patronymics, nicknames, strong/weak aliases, company suffixes,
vessel prefixes, identifiers and dates of birth.

Standard library only.  Usage::

    python3 screen.py --watchlist watchlist.json --customers customers.csv \
                      --out decisions.csv
"""

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict

# ---------------------------------------------------------------------------
# 1. character level normalisation
# ---------------------------------------------------------------------------

# Graphemes expanded before combining marks are stripped: dropping the mark
# would destroy the sound (Turkish "ş" is sh, Czech "č" is ch, ...).
PRE_MAP = {
    "ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "å": "a",
    "ü": "ue", "ö": "oe", "ä": "ae",
    "ı": "i", "ş": "sh", "ç": "ch", "ğ": "gh",
    "š": "sh", "ž": "zh", "č": "ch", "ć": "ch", "ś": "sh",
    "ź": "zh", "ż": "zh", "ř": "rzh", "ł": "l", "ń": "n",
    "ę": "e", "ą": "a", "ñ": "n", "ð": "d", "þ": "th", "đ": "d",
    "ș": "sh", "ț": "ts", "ĉ": "ch", "ĵ": "j", "ŝ": "sh", "ĝ": "j",
}


def deaccent(s):
    """Lower-case, expand special graphemes, drop combining marks."""
    s = s.lower()
    if any(c in PRE_MAP for c in s):
        s = "".join(PRE_MAP.get(c, c) for c in s)
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
CYRILLIC_RE = re.compile(r"[Ѐ-ӿԀ-ԯ]")
CJK_RE = re.compile(r"[㐀-鿿]")


def script_of(s):
    if ARABIC_RE.search(s):
        return "arab"
    if CYRILLIC_RE.search(s):
        return "cyr"
    if CJK_RE.search(s):
        return "cjk"
    return "latin"


# --- Arabic / Persian -------------------------------------------------------

AR_NORM = {
    "ي": "ی", "ى": "ی", "ئ": "ی",
    "ك": "ک", "ة": "ه",
    "أ": "ا", "إ": "ا", "آ": "ا",
    "ٱ": "ا", "ؤ": "و",
}

AR_TRANSLIT = {
    "ا": "a", "ب": "b", "ت": "t", "ث": "th",
    "ج": "j", "ح": "h", "خ": "kh", "د": "d",
    "ذ": "dh", "ر": "r", "ز": "z", "س": "s",
    "ش": "sh", "ص": "s", "ض": "d", "ط": "t",
    "ظ": "z", "ع": "", "غ": "gh", "ف": "f",
    "ق": "q", "ک": "k", "ل": "l", "م": "m",
    "ن": "n", "ه": "h", "و": "u", "ی": "i",
    "ء": "", "ـ": "", "پ": "p", "چ": "ch",
    "ژ": "zh", "گ": "g",
}

AR_ARTICLE = "ال"          # alef + lam
AR_ALLAH = "الله"
AR_ABD = "عبد"
AR_NASR = "نصر"
AR_BIN = ("بن", "ابن", "بنت")


def ar_normalize(s):
    s = unicodedata.normalize("NFC", s)
    s = "".join(c for c in s if not ("ً" <= c <= "ْ"))
    s = "".join(AR_NORM.get(c, c) for c in s)
    # a final ya / alif maqsura is the same /a/ as a final alif, so the
    # arabic and persian spellings of one name agree (Layla = Leila)
    if len(s) > 3 and s[-1] == "ی":
        s = s[:-1] + "ا"
    return s


def ar_strip_article(s):
    if s.startswith(AR_ARTICLE) and len(s) > 4 and s != AR_ALLAH:
        return s[2:]
    return s


def ar_translit(s):
    s = ar_normalize(s)
    return "".join(AR_TRANSLIT.get(c, "") for c in s)


# --- Cyrillic ---------------------------------------------------------------

CYR_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g",
    "д": "d", "е": "e", "ё": "yo", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya", "є": "ye", "і": "i", "ї": "yi",
    "ґ": "g", "ў": "v",
}


def cyr_translit(s):
    return "".join(CYR_TRANSLIT.get(c, c) for c in s.lower())


def to_latin(tok):
    sc = script_of(tok)
    if sc == "cyr":
        return cyr_translit(tok)
    if sc == "arab":
        return ar_translit(tok)
    return deaccent(tok)


# ---------------------------------------------------------------------------
# 2. phonetic skeleton
# ---------------------------------------------------------------------------
#
# A skeleton is a tuple of coarse phoneme symbols.  Orthographic conventions
# that spell one sound differently (sch/sh/sz/sj/s-caron, tsch/tch/cz/ch,
# w/v, ff/v, kh/ch/h, ou/u, y/i, doubled letters, silent final -e/-h)
# collapse onto the same symbol; vowels collapse into three classes so that
# vowel colouring is cheap but vowel *position* is still significant
# (Faris != Farsi).

VOWELS = set("aeiouy")

DIGRAPHS = [
    ("sjtsj", "S C"), ("stsch", "S C"), ("shch", "S C"), ("sstch", "S C"),
    ("schtsch", "S C"), ("chtch", "S C"), ("szcz", "S C"),
    ("tsch", "C"), ("dsch", "J"), ("sch", "S"), ("tch", "C"),
    ("tsh", "C"), ("tsj", "C"), ("dzh", "J"), ("dzj", "J"),
    ("zsh", "Z"), ("zj", "Z"), ("sz", "S"),
    ("sh", "S"), ("cz", "C"), ("sj", "S"),
    ("dj", "J"), ("zh", "Z"), ("ts", "T"), ("tz", "T"),
    ("ch", "X"), ("kh", "h"), ("gh", "g"), ("ph", "f"),
    ("th", "t"), ("ck", "k"), ("qu", "k v"), ("qv", "k v"),
    ("x", "k s"), ("q", "k"), ("rzh", "r"),
]

VOWEL_CLASS = {"a": "A", "e": "E", "i": "E", "o": "O", "u": "O", "y": "E"}
VOWEL_SET = frozenset(("A", "E", "O"))


def skeleton(tok):
    """Phonetic skeleton of a latin token, as a tuple of symbols."""
    s = deaccent(tok)
    s = re.sub(r"[^a-z]", "", s)
    if not s:
        return ()
    # i/y glide spellings are interchangeable: Viktoriya = Viktoria
    s = re.sub(r"iy(?=[aeou])", "y", s)
    s = re.sub(r"yi(?=[aeou])", "y", s)
    # slavic j is the y-glide (Cajkovskij = Chaikovsky, Sergej = Sergey)
    s = re.sub(r"(?<=[aeiou])j(?![aeiou])", "y", s)
    s = re.sub(r"j$", "i", s)
    # u/o between vowels is the w-glide (Aouad = Awad)
    s = re.sub(r"(?<=[aeiou])[ou](?=[aei])", "w", s)
    if len(s) > 3 and s.endswith("e") and s[-2] not in VOWELS:
        s = s[:-1]                      # silent final -e   (Bakre -> Bakr)
    if len(s) > 3 and s.endswith("h") and s[-2] in VOWELS:
        s = s[:-1]                      # final -h          (Hudah -> Huda)
    out = []
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch in VOWELS:
            if ch in "yi" and i + 1 < n and s[i + 1] in "aeou" and \
                    (i == 0 or s[i - 1] not in VOWELS):
                out.append("y")         # consonantal y / i  (Yusuf, Iachin)
                i += 1
                continue
            j = i
            while j < n and s[j] in VOWELS:
                j += 1
            run = s[i:j]
            k = 0
            ln = len(run)
            while k < ln:
                m = k + 1
                while m < ln and not (run[m] in "yi" and m + 1 < ln):
                    m += 1
                out.append(VOWEL_CLASS.get(run[k], "E"))
                if m < ln:
                    out.append("y")     # glide inside the run: Sayed, Nayef
                    k = m + 1
                else:
                    k = m
            i = j
            continue
        hit = False
        for gr, rep in DIGRAPHS:
            if s.startswith(gr, i):
                out.extend(rep.split())
                i += len(gr)
                hit = True
                break
        if hit:
            continue
        if ch == "j":
            out.append("J")
        elif ch == "c":
            out.append("c")             # ambiguous bare c
        else:
            out.append(ch)
        i += 1
    res = []
    for sym in out:
        if res and res[-1] == sym:
            continue
        res.append(sym)
    return tuple(res)


def _mk_costs():
    c = {}

    def put(a, b, v):
        c[(a, b)] = v
        c[(b, a)] = v

    put("A", "E", 0.30)
    put("A", "O", 0.40)
    put("E", "O", 0.40)
    put("s", "S", 0.35)
    put("s", "z", 0.30)
    put("s", "T", 0.35)
    put("z", "T", 0.35)
    put("z", "Z", 0.30)
    put("S", "Z", 0.35)
    put("S", "C", 0.30)
    put("C", "T", 0.30)
    put("C", "J", 0.30)
    put("J", "Z", 0.20)
    put("J", "y", 0.25)
    put("J", "g", 0.35)
    put("J", "h", 0.50)
    put("S", "X", 0.10)
    put("C", "X", 0.10)
    put("h", "X", 0.25)
    put("k", "X", 0.25)
    put("J", "X", 0.30)
    put("T", "X", 0.30)
    put("s", "X", 0.30)
    put("Z", "X", 0.25)
    for other, v in (("k", 0.12), ("s", 0.12), ("T", 0.15), ("C", 0.12),
                     ("S", 0.20), ("J", 0.18), ("X", 0.10), ("z", 0.25),
                     ("g", 0.35)):
        put("c", other, v)
    put("t", "d", 0.30)
    put("p", "b", 0.35)
    put("p", "f", 0.35)
    put("b", "v", 0.40)
    put("f", "v", 0.25)
    put("k", "g", 0.35)
    put("k", "h", 0.30)
    put("g", "h", 0.35)
    put("t", "T", 0.40)
    put("d", "T", 0.50)
    put("t", "s", 0.55)
    put("m", "n", 0.55)
    put("l", "r", 0.60)
    put("y", "E", 0.25)
    put("y", "v", 0.55)
    put("n", "l", 0.70)
    put("v", "g", 0.55)
    put("h", "y", 0.60)
    put("w", "v", 0.15)
    put("w", "O", 0.30)
    put("w", "y", 0.50)
    put("w", "b", 0.55)
    put("w", "f", 0.45)
    put("w", "A", 0.60)
    put("w", "E", 0.60)
    return c


SUB_COST = _mk_costs()
INDEL = {"A": 0.40, "E": 0.40, "O": 0.40, "h": 0.25, "y": 0.35,
         "w": 0.40, "v": 0.55, "n": 0.60, "r": 0.60, "l": 0.60, "s": 0.70}
DEFAULT_INDEL = 0.85
DEFAULT_SUB = 1.0


def pdist(a, b, cutoff=1.2):
    """Bounded weighted edit distance between two skeletons."""
    la, lb = len(a), len(b)
    if la == 0 or lb == 0:
        return sum(INDEL.get(x, DEFAULT_INDEL) for x in (a or b))
    prev2 = None
    prev = [0.0] * (lb + 1)
    for j in range(1, lb + 1):
        prev[j] = prev[j - 1] + INDEL.get(b[j - 1], DEFAULT_INDEL)
    for i in range(1, la + 1):
        ai = a[i - 1]
        cur = [prev[0] + INDEL.get(ai, DEFAULT_INDEL)] + [0.0] * lb
        best = cur[0]
        for j in range(1, lb + 1):
            bj = b[j - 1]
            if ai == bj:
                v = prev[j - 1]
            else:
                v = prev[j - 1] + SUB_COST.get((ai, bj), DEFAULT_SUB)
            d = prev[j] + INDEL.get(ai, DEFAULT_INDEL)
            if d < v:
                v = d
            d = cur[j - 1] + INDEL.get(bj, DEFAULT_INDEL)
            if d < v:
                v = d
            if i > 1 and j > 1 and ai == b[j - 2] and a[i - 2] == bj:
                d = prev2[j - 2] + 0.60
                if d < v:
                    v = d
            cur[j] = v
            if v < best:
                best = v
        if best > cutoff:
            return best
        prev2 = prev
        prev = cur
    return prev[lb]


# ---------------------------------------------------------------------------
# 3. name structure
# ---------------------------------------------------------------------------

NASAB = {"bin", "ibn", "ben", "bint", "b", "binti", "binte", "bn", "ould",
         "walad"}
AMBIG_NASAB = {"ben", "b"}
STRICT_NASAB = NASAB - AMBIG_NASAB
ARABIC_ARTICLES = {"al", "el", "ul", "as", "ash", "ad", "ar", "at", "az",
                   "an", "ed", "es", "er", "et", "ez", "en", "il", "ul"}
WEST_PARTICLES = {"de", "la", "le", "du", "des", "del", "della", "van",
                  "von", "der", "den", "da", "dos", "do", "di", "ter",
                  "ten", "af", "av", "mac", "mc", "o", "st", "abu", "abou",
                  "umm", "dell"}
PATRONYM_RE = re.compile(
    r"(?:o|e|i|y)(?:v|w|f)(?:i|e|y|j)?"
    r"(?:ch|tch|tsch|tsj|cz|c|tj|che|tche|sj|sch)e?$"
    r"|(?:o|e|i|y)(?:v|w|f)n(?:a|ah|e)$"
    r"|itsch$|itsj$|itch$|ich$|icz$|ovna$|evna$|ovic$|evic$")

ABD_RE = re.compile(r"^abd(?:ul|ool|oul|ol|al|el|il|ur|ar|er|u|o|a|e|i)?$")
ABD_ALLAH_RE = re.compile(r"^[aeiou]*l{1,2}[aeiou]+h?$")


def norm_abd(tok):
    """Canonicalise a one-token 'Abd al-X' compound to abd+X."""
    if not tok.startswith("abd") or len(tok) <= 5:
        return tok
    rest = tok[3:]
    if ABD_ALLAH_RE.match(rest):
        return "abdallah"
    for conn in ("ull", "ool", "oul", "ul", "ol", "al", "el", "il", "ur",
                 "ar", "er", "u", "o", "a", "e", "i", ""):
        if rest.startswith(conn) and len(rest) - len(conn) >= 3:
            return "abd" + rest[len(conn):]
    return tok


def strip_article(tok):
    """Strip a leading arabic article written with a separator."""
    m = re.match(r"^(?:a|e|u|i)(?:[lnrszdt])?[-'](?=.)", tok)
    if m:
        rest = tok[m.end():]
        if len(rest) >= 2:
            return rest
    return tok


def strip_article_attached(tok):
    """Strip a leading arabic article written solid: ElSayide -> sayide.

    Only 'al/el/ul/il' or a sun-letter article whose consonant is doubled by
    assimilation (ash-Shamsi -> ashshamsi, an-Najjar -> annajjar) qualifies,
    so ordinary names (Artem, Alexander) are left alone.
    """
    m = re.match(r"^(?:a|e|u|i)l(.{3,})$", tok)
    if m:
        return m.group(1)
    m = re.match(r"^(?:a|e)([snrdtz])h?(.{3,})$", tok)
    if m and m.group(2).startswith(m.group(1)):
        return m.group(2)
    return None


ARTICLE_PENALTY = 0.35
COMPAT_MAX = 0.45      # max distance for a cross-tradition class link


def is_initial(tok):
    t = tok.strip(".")
    return len(t) == 1 and t.isalpha()


def tokenize(name):
    s = name.strip().replace("’", "'").replace("‘", "'")
    parts = re.split(r"\s*,\s*", s)
    if len(parts) > 1:
        head = [t for t in re.split(r"\s+", parts[0].strip()) if t]
        rest = [t for t in re.split(r"\s+", " ".join(parts[1:]).strip()) if t]
        return head + rest, len(head)
    return [t for t in re.split(r"\s+", s) if t], None


class NameParse(object):
    """Structured view of a personal name (either script, any order)."""

    __slots__ = ("name", "core", "strands", "nasab", "initials", "comma",
                 "ncore", "core_all", "nasab_idx")

    def __init__(self, name, nasab_markers=NASAB):
        self.name = name
        toks, comma = tokenize(name)
        self.comma = comma
        units = []                      # (bare_key, script)
        for t in toks:
            sc = script_of(t)
            if sc == "latin":
                b = re.sub(r"[^a-z'\-]", "", deaccent(t))
                b = strip_article(b)            # al-Masri -> masri
                b = re.sub(r"[^a-z]", "", b)
                if not b:
                    continue
                units.append([b, "latin", is_initial(t.strip("."))])
            else:
                b = ar_normalize(t) if sc == "arab" else t.lower()
                b = re.sub(r"[^\w]", "", b, flags=re.UNICODE)
                if not b:
                    continue
                units.append([b, sc, False])
        # --- join Abd / Nasr compounds -------------------------------------
        joined = []
        i = 0
        n = len(units)
        while i < n:
            b, sc, ini = units[i]
            if sc == "latin" and ABD_RE.match(b) and i + 1 < n and \
                    units[i + 1][1] == "latin" and not units[i + 1][2]:
                j = i + 1
                if units[j][0] in ARABIC_ARTICLES and j + 1 < n and \
                        units[j + 1][1] == "latin" and not units[j + 1][2]:
                    j += 1              # "Abd Al Aziz" written with spaces
                nxt = strip_article(units[j][0])
                nxt = strip_article_attached(nxt) or nxt
                joined.append(["abd" + nxt, "latin", False])
                i = j + 1
                continue
            if sc == "arab" and b == AR_ABD and i + 1 < n:
                joined.append([b + ar_strip_article(units[i + 1][0]), "arab",
                               False])
                i += 2
                continue
            if sc == "latin" and b in ("nasr", "nasser") and i + 1 < n and \
                    units[i + 1][0] in ("allah", "alla", "ullah", "ulla",
                                        "allahe"):
                joined.append(["nasrallah", "latin", False])
                i += 2
                continue
            if sc == "arab" and b == AR_NASR and i + 1 < n and \
                    units[i + 1][0] == AR_ALLAH:
                joined.append([b + units[i + 1][0], "arab", False])
                i += 2
                continue
            if sc == "latin":
                joined.append([norm_abd(b), sc, ini])
            else:
                joined.append([b, sc, ini])
            i += 1
        # --- split roles ----------------------------------------------------
        core = []
        core_all = []
        nasab_idx = set()
        strands = []
        nasab = []
        initials = []
        pend = []
        i = 0
        n = len(joined)
        while i < n:
            b, sc, ini = joined[i]
            if (sc == "latin" and b in nasab_markers) or \
                    (sc == "arab" and b in AR_BIN):
                if i + 1 < n and not joined[i + 1][2] and \
                        joined[i + 1][0] not in nasab_markers:
                    nb, nsc = joined[i + 1][0], joined[i + 1][1]
                    if nsc == "latin":
                        nb = strip_article(nb)
                    else:
                        nb = ar_strip_article(nb)
                    nasab.append((nb, nsc))
                    nasab_idx.add(len(core_all))
                    core_all.append((nb, nsc))
                    i += 2
                    continue
                if len(b) <= 2:
                    i += 1
                    continue
            if ini:
                initials.append(b)
                i += 1
                continue
            if sc == "latin":
                if b in WEST_PARTICLES or b in ARABIC_ARTICLES:
                    nxt_ok = i + 1 < n and not joined[i + 1][2] and \
                        joined[i + 1][0] not in NASAB
                    if nxt_ok:
                        pend.append(b)
                        i += 1
                        continue
                    strands.extend(pend)      # keep the original order
                    del pend[:]
                    strands.append(b)
                    i += 1
                    continue
                b2 = strip_article(b)
                if pend:
                    west = [p for p in pend if p not in ARABIC_ARTICLES]
                    if west:
                        b2 = "".join(west) + b2
                    pend = []
                core.append((b2, "latin"))
                core_all.append((b2, "latin"))
            else:
                v = (ar_strip_article(b) if sc == "arab" else b, sc)
                core.append(v)
                core_all.append(v)
            i += 1
        strands.extend(pend)
        self.core = core
        self.core_all = core_all
        self.nasab_idx = nasab_idx
        self.strands = strands
        self.nasab = nasab
        self.initials = initials
        self.ncore = len(core)

    def __repr__(self):
        return "NameParse(%r -> core=%r strand=%r nasab=%r)" % (
            self.name, self.core, self.strands, self.nasab)


def looks_patronymic(bare, sc):
    lat = bare if sc == "latin" else to_latin(bare)
    if len(lat) < 6:
        return False
    return bool(PATRONYM_RE.search(lat))


# ---------------------------------------------------------------------------
# 4. lexicon: surface form -> canonical class
# ---------------------------------------------------------------------------

class Lexicon(object):
    def __init__(self):
        self.parent = {}
        self.surface = {}
        self.entries = []
        self.by_len = defaultdict(list)
        self.maxlen = 0
        self._cache = {}
        self._skel = {}

    def find(self, x):
        p = self.parent
        root = x
        while p.get(root, root) != root:
            root = p[root]
        while p.get(x, x) != x:
            p[x], x = root, p[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return ra
        if rb < ra:
            ra, rb = rb, ra
        self.parent[rb] = ra
        return ra

    def add_surface(self, surf, cls, merge=True):
        """Record that *surf* spells class *cls*.

        With ``merge`` (evidence from aliases / original script) an existing
        assignment is unified with the new one; without it the surface simply
        becomes ambiguous (Ted -> Edward or Theodore).
        """
        if not surf or not cls:
            return
        self.parent.setdefault(cls, cls)
        prev = self.surface.get(surf)
        if prev is None:
            self.surface[surf] = [cls]
        elif merge:
            for p in prev:
                self.union(p, cls)
            self.surface[surf] = [self.find(cls)]
        elif not any(self.find(p) == self.find(cls) for p in prev):
            prev.append(cls)

    def skel(self, s):
        v = self._skel.get(s)
        if v is None:
            v = skeleton(s)
            self._skel[s] = v
        return v

    def finalize(self):
        seen = set()
        self.by_cons = defaultdict(set)
        for surf, clss in self.surface.items():
            if script_of(surf) != "latin":
                continue
            sk = self.skel(surf)
            if not sk:
                continue
            for cls in clss:
                root = self.find(cls)
                if (surf, root) in seen:
                    continue
                seen.add((surf, root))
                self.entries.append((surf, sk, root))
        for surf, sk, root in self.entries:
            self.by_len[len(sk)].append((sk, root))
            self.by_cons[tuple(x for x in sk if x not in VOWEL_SET)].add(root)
        self.maxlen = max(self.by_len) if self.by_len else 0

    def resolve_consonants(self, token):
        """Fallback for original-script tokens: arabic script writes no short
        vowels, so compare the consonant skeleton only."""
        cons = tuple(x for x in self.skel(token) if x not in VOWEL_SET)
        if len(cons) < 2:
            return []
        out = self.by_cons.get(cons)
        return [(r, 0.5) for r in out] if out else []

    def resolve(self, token, band=0.22):
        """Candidate (class, cost) list for a latin token."""
        hit = self._cache.get(token)
        if hit is not None:
            return hit
        res = []
        direct = self.surface.get(token)
        if direct is not None:
            res = []
            for c in direct:
                r = self.find(c)
                if all(r != x for x, _ in res):
                    res.append((r, 0.0))
        else:
            sk = self.skel(token)
            if sk:
                cut = min(1.15, 0.17 * len(sk) + 0.14)
                span = int(cut / 0.40) + 1
                best = {}
                lo, hi = max(1, len(sk) - span), min(self.maxlen,
                                                     len(sk) + span)
                for L in range(lo, hi + 1):
                    for sk2, root in self.by_len[L]:
                        d = pdist(sk, sk2, cut)
                        if d <= cut and (root not in best or d < best[root]):
                            best[root] = d
                if best:
                    bv = min(best.values())
                    res = sorted([(r, d) for r, d in best.items()
                                  if d <= bv + band], key=lambda x: x[1])
        self._cache[token] = res
        return res


# ---------------------------------------------------------------------------
# 5. nicknames
# ---------------------------------------------------------------------------

NICKNAMES = {
    "william": ["bill", "billy", "will", "willy", "willie", "liam"],
    "katherine": ["kate", "katie", "kathy", "cathy", "kath", "katy",
                  "catherine", "kathryn", "kitty"],
    "michael": ["mike", "mikey", "mick", "micky"],
    "samuel": ["sam", "sammy"],
    "peter": ["pete", "petey"],
    "margaret": ["meg", "maggie", "peggy", "marge", "margie"],
    "anthony": ["tony"],
    "john": ["jack", "johnny", "jon", "jonny"],
    "rebecca": ["becky", "becca"],
    "frederick": ["fred", "freddie", "freddy"],
    "andrew": ["drew", "andy"],
    "joseph": ["joe", "joey"],
    "elizabeth": ["beth", "liz", "lizzie", "betty", "betsy", "eliza",
                  "libby"],
    "daniel": ["dan", "danny"],
    "benjamin": ["ben", "benny", "benji"],
    "christopher": ["chris", "kit"],
    "robert": ["bob", "bobby", "rob", "robbie"],
    "richard": ["rick", "ricky", "dick", "richie"],
    "james": ["jim", "jimmy", "jamie"],
    "charles": ["charlie", "chuck", "chas"],
    "thomas": ["tom", "tommy"],
    "edward": ["ed", "eddie", "eddy", "ted", "teddy", "ned"],
    "theodore": ["ted", "teddy", "theo"],
    "nicholas": ["nick", "nicky", "nico"],
    "alexander": ["alex", "alec", "xander"],
    "susan": ["sue", "susie", "suzy"],
    "barbara": ["barb", "babs", "barbie"],
    "jennifer": ["jen", "jenny"],
    "patricia": ["pat", "patty", "trish", "tricia"],
    "victoria": ["vicky", "vicki", "tori"],
    "dorothy": ["dot", "dottie", "dolly"],
    "maria": ["mary", "mia"],
    "mary": ["molly", "polly", "may"],
    "stephen": ["steve", "stevie"],
    "steven": ["steve", "stevie"],
    "matthew": ["matt", "matty"],
    "henry": ["hank", "harry", "hal"],
    "francisco": ["paco", "pancho", "frank", "fran", "francis", "cisco"],
    "jose": ["pepe", "joselito"],
    "eugene": ["gene"],
    "lawrence": ["larry"],
    "gregory": ["greg"],
    "kenneth": ["ken", "kenny"],
    "ronald": ["ron", "ronnie"],
    "donald": ["don", "donnie"],
    "raymond": ["ray"],
    "philip": ["phil"],
    "vincent": ["vince"],
    "walter": ["walt"],
    "leonard": ["leo", "len", "lenny"],
    "antonio": ["tony", "tonio"],
    "manuel": ["manny", "manolo"],
    "eduardo": ["lalo"],
    "roberto": ["beto"],
    "alberto": ["beto"],
    "isabel": ["bella", "chabela"],
    "christina": ["tina", "christie"],
    "cristina": ["tina"],
    "angela": ["angie"],
    "deborah": ["deb", "debbie"],
    "kimberly": ["kim"],
    "pamela": ["pam"],
    "cynthia": ["cindy"],
    "veronica": ["vero"],
    "dolores": ["lola"],
    "enrique": ["quique"],
    "ignacio": ["nacho"],
    "guillermo": ["memo"],
}


# Forms of one name in another naming tradition.  Like nicknames these are
# alternatives, not merges: they add a candidate, they never fuse two classes.
TRADITION_FORMS = {
    "muhammad": ["mehmet", "mehmed", "muhammet", "mohamad", "muhamad",
                 "mahomet", "mehemet"],
    "ahmad": ["ahmet", "ahmed", "achmad", "achmed", "ahmat"],
    "qasim": ["kasim", "kassim", "kacem"],
    "jamal": ["cemal", "djamal", "gamal"],
    "hussein": ["huseyin", "husein", "hoesin", "hussain", "husain"],
    "khalid": ["halit", "halid", "chalid", "khaled"],
    "yusuf": ["yusof", "jusuf", "joesoef", "youssef", "yousef", "yousuf"],
    "ibrahim": ["ebrahim", "brahim", "ibrahem"],
    "omar": ["omer", "umar", "oumar"],
    "uthman": ["osman", "othman", "usman"],
    "sulaiman": ["suleyman", "sulayman", "soleiman", "sleiman"],
    "khalil": ["halil", "chalil"],
    "aisha": ["ayse", "aysha", "aicha", "ayesha"],
    "fatima": ["fatma", "fatme", "fatemeh", "fatimah"],
    "khadija": ["hatice", "hadija", "khadijah"],
    "majid": ["mecit", "madjid", "majeed"],
    "amin": ["emin", "ameen"],
    "anwar": ["enver", "anouar"],
    "rashid": ["resit", "rachid", "rasheed"],
    "salim": ["selim", "saleem"],
    "karim": ["kerim", "kareem", "carim"],
    "murad": ["murat", "mourad"],
    "sharif": ["sjarif", "cherif", "shareef", "syarif"],
    "mahmoud": ["mahmut", "mahmood", "machmoed"],
    "nasser": ["nasir", "nassir", "naser"],
    "tariq": ["tarik", "tarek", "tareq"],
    "hamza": ["hamzah", "hamze"],
    "yasser": ["yasir", "yassir", "jasser"],
    "saeed": ["sait", "said", "sayid", "saïd"],
    "abdullah": ["abdoellah", "abdulah", "abdallah"],
    "sergei": ["siergiej", "sergej", "sergey", "serguei"],
    "vasily": ["wasilij", "wassili", "vasili"],
    "yelizaveta": ["jelizaweta", "elisaveta"],
    "elena": ["jelena", "helena", "olena"],
    "yevgeny": ["jewgeni", "evgenij", "eugene"],
    "fyodor": ["fiodor", "feodor", "theodor"],
    "ivan": ["iwan", "ioann"],
    "nikolai": ["mikolaj", "nikolay", "nicolai"],
    "mikhail": ["michail", "michal", "mihail"],
    "pavel": ["pawel", "paul"],
    "yuri": ["juri", "jurij", "youri"],
    "grigory": ["grigorij", "gregor", "grzegorz"],
    "aleksandr": ["aleksander", "alexandr", "olexandr"],
    "dmitri": ["dmitrij", "dimitri", "dmytro"],
}


NICK_SET = set()
for _full, _nicks in NICKNAMES.items():
    NICK_SET.update(_nicks)


# ---------------------------------------------------------------------------
# 6. organisations and vessels
# ---------------------------------------------------------------------------

LEGAL_FORMS = {
    "llc", "lc", "ltd", "limited", "inc", "incorporated", "corp",
    "corporation", "co", "company", "sa", "sociedad", "anonima", "gmbh",
    "jsc", "joint", "stock", "ao", "oao", "pjsc", "ojsc", "zao", "pao",
    "fze", "fz", "fzllc", "fzco", "plc", "ag", "nv", "bv", "sarl", "srl",
    "spa", "kg", "mbh", "pte", "pty", "llp", "lp", "public", "liability",
    "free", "zone", "establishment", "est", "pvt", "private", "cjsc",
    "oy", "ab", "aps", "sas", "sl", "se", "kk", "societe", "anonyme",
    "aktiengesellschaft", "limitada", "lda", "sdn", "bhd", "berhad",
    "tbk", "doo", "dd", "ood", "eood", "gmb", "lllc", "lda",
}
LEGAL_DROP_WORDS = {"the", "and"}
VESSEL_PREFIXES = {"mv", "mt", "ms", "ss", "mss", "mtv", "fv", "vessel",
                   "tug", "rv", "sv", "myv"}

CHINESE_STEMS = [
    ["li", "lee", "lei", "ly", "lie", "rhee"],
    ["zhang", "chang", "cheung", "cheong", "teo", "tio", "tiong", "chong",
     "diong", "tiew"],
    ["wang", "wong", "ong", "heng", "vong", "waang", "uong"],
    ["liu", "lau", "low", "liew", "lew", "liou", "lao", "lieu"],
    ["chen", "chan", "tan", "chean", "chin", "chun", "ting"],
    ["yang", "yeung", "yeo", "yeoh", "yio", "ieong", "young", "yong"],
    ["huang", "hwang", "wong", "ng", "ooi", "oei", "uy", "wee",
     "bong", "whang"],
    ["zhao", "chao", "chiu", "chio", "jiu", "tiu", "tio"],
    ["wu", "ng", "goh", "gouw", "ngo", "ngoh", "woo", "go"],
    ["zhou", "chou", "chow", "chew", "jew", "chau", "chiew"],
    ["xu", "hsu", "hui", "tsui", "khoo", "kho", "hee", "chee", "shui"],
    ["sun", "suen", "sng", "soon", "swen", "shuen"],
    ["ma", "mah", "mar", "bee", "beh"],
    ["zhu", "chu", "choo", "chue", "gee", "ju", "chyu"],
    ["hu", "woo", "aw", "oh", "ow", "fu", "hoo", "wu"],
    ["guo", "kuo", "kwok", "kwek", "quek", "kueh", "kuik", "kok", "ker",
     "kwak"],
    ["he", "ho", "hoh", "hor", "hoe", "hop"],
    ["gao", "kao", "ko", "koh", "kou", "kaw", "kow"],
    ["lin", "lam", "lim", "lum", "ling"],
    ["luo", "lo", "law", "loh", "lor", "loe", "lowe"],
    ["zheng", "cheng", "chang", "tay", "tee", "teh", "chiang", "cheang"],
    ["liang", "leung", "leong", "neo", "niu", "nio", "liong", "lang"],
    ["xie", "hsieh", "tse", "chia", "cheah", "seah", "sia", "shia"],
    ["tang", "tong", "thong", "tng", "thang", "tung"],
    ["han", "hon", "hahn", "hann"],
    ["cao", "tsao", "cho", "tso", "chaw", "tsou"],
    ["deng", "teng", "thean", "then", "tin", "tang"],
    ["feng", "fung", "phang", "foong", "pung"],
    ["peng", "pang", "phe", "pong", "phang", "phoon"],
    ["cai", "tsai", "choi", "tsoi", "chua", "chuah", "chye", "chai", "cua",
     "choy"],
    ["pan", "poon", "pun", "phua", "phan", "puan", "pon"],
    ["du", "tu", "to", "toh", "tou", "doh", "dou"],
    ["dai", "tai", "te", "toe", "day", "tay"],
    ["ye", "yeh", "yip", "ip", "yap", "iap", "yeap", "yehp"],
    ["shen", "sum", "sham", "sim", "sin", "shim", "shum"],
    ["cui", "chui", "chwee", "chooi", "tsui", "chuy"],
    ["qian", "chien", "chin", "jin", "cheen"],
    ["jiang", "chiang", "kong", "keung", "kang", "geung", "keong", "chong"],
    ["yuan", "yuen", "oan", "wan", "yen", "guan", "wang"],
    ["song", "sung", "soong", "shung"],
    ["fan", "faan", "huan", "hoan", "fann", "hwan", "fon"],
    ["lu", "loo", "luk", "look", "loke", "lou", "lok"],
    ["zeng", "tseng", "tsang", "chng", "dzang", "chen"],
    ["xiao", "hsiao", "siu", "seow", "sio", "shaw", "siew"],
    ["su", "soo", "sou", "so", "soh"],
    ["yu", "yue", "yee", "ee", "yuh", "yew"],
    ["ding", "ting", "teng", "deng", "tin"],
    ["shi", "shih", "sek", "sze", "see", "shee"],
    ["jin", "kam", "kim", "gim", "kum"],
    ["qiu", "yau", "hew", "khoo", "chiu"],
    ["zhong", "chung", "jong", "cheng", "chong"],
    ["hong", "hung", "ang", "hoong", "ong"],
    ["wei", "ngai", "wai", "goay", "ooi"],
    ["yan", "ngan", "gan", "ean", "yen"],
    ["dong", "tung", "tong", "toong"],
    ["mao", "mou", "mo", "mow", "mao"],
    ["bai", "pai", "pak", "peh", "pek"],
    ["tian", "tien", "thien", "chan", "tiam"],
    ["meng", "mang", "mong", "beng"],
    ["kong", "khong", "hong", "kung"],
    ["duan", "tuan", "toan", "tuen"],
]


def build_chinese_map(list_stems=()):
    """spelling -> pinyin stem(s).

    A spelling that is itself one of the pinyin stems *on the list* never maps
    to a different stem: on a list that carries both Wu and Hu, a customer
    writing "Wu" means Wu, not the cantonese reading of Hu.
    """
    heads = set(r[0] for r in CHINESE_STEMS)
    protected = heads & set(list_stems)
    m = defaultdict(set)
    for row in CHINESE_STEMS:
        head = row[0]
        m[head].add(head)
        for sp in row[1:]:
            if sp != head and sp in protected:
                continue
            m[sp].add(head)
    return m


CHINESE_ROM = build_chinese_map()


VESSEL_PREFIX_RE = re.compile(
    r"^\s*(?:m\s*[/.\-]\s*[vts]|s\s*[/.\-]\s*s|f\s*[/.\-]\s*v|"
    r"m\s*[/.\-]?\s*v|vessel|tug)\b[.\s]*", re.I)


def org_words(name):
    """Normalised content words of an organisation / vessel name."""
    s = deaccent(name)
    s = s.replace("&", " and ")
    s = s.replace("'", "").replace("’", "")   # Wade-Giles: Ch'en = Chen
    s2 = VESSEL_PREFIX_RE.sub(" ", s)
    if s2.strip():
        s = s2
    s = re.sub(r"[^a-z0-9]+", " ", s)
    words = [w for w in s.split() if w]
    # solid-letter legal forms: "G. m. b. H." -> gmbh, "L.L.C." -> llc
    merged = []
    run = []
    for w in words:
        if len(w) == 1 and w.isalpha():
            run.append(w)
        else:
            if run:
                merged.append("".join(run))
                run = []
            merged.append(w)
    if run:
        merged.append("".join(run))
    words = merged
    while words and words[0] in VESSEL_PREFIXES:
        words = words[1:]
    while words and words[0] in LEGAL_DROP_WORDS:
        words = words[1:]
    words = [w for w in words if w not in LEGAL_DROP_WORDS]
    core = list(words)
    while core and core[-1] in LEGAL_FORMS:
        core.pop()
    if not core:
        core = words
    return core


def org_key(name):
    return " ".join(org_words(name))


def org_variant_keys(name, rom=None):
    """Keys after mapping a leading chinese stem to its pinyin form(s)."""
    core = org_words(name)
    out = set()
    if core:
        for st in (rom or CHINESE_ROM).get(core[0], ()):
            out.add(" ".join([st] + core[1:]))
    return out


def weak_key(name):
    s = deaccent(name)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


# ---------------------------------------------------------------------------
# 7. dates
# ---------------------------------------------------------------------------

def norm_date(s):
    s = (s or "").strip()
    if not s:
        return ""
    s = s.replace("/", "-").replace(".", "-")
    m = re.match(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?$", s)
    if not m:
        return ""
    out = m.group(1)
    if m.group(2):
        out += "-%02d" % int(m.group(2))
        if m.group(3):
            out += "-%02d" % int(m.group(3))
    return out


def dob_compare(cust, entry):
    c, e = norm_date(cust), norm_date(entry)
    if not c or not e:
        return "unknown"
    n = min(len(c), len(e))
    return "agree" if c[:n] == e[:n] else "conflict"


# ---------------------------------------------------------------------------
# 8. engine
# ---------------------------------------------------------------------------

class Engine(object):
    def __init__(self, watchlist):
        self.entries = watchlist
        self.lex = Lexicon()
        self._parses = {}
        self.compat = {}
        self._build_lexicon()
        self._build_index()
        self._build_compat()

    # -- token resolution ---------------------------------------------------
    def classes(self, bare, sc="latin"):
        """Candidate classes for one core token."""
        out = self._classes_raw(bare, sc)
        if not self.compat:
            return out
        extra = []
        have = set(c for c, _ in out)
        for c, d in out:
            for c2 in self.compat.get(c, ()):
                if c2 not in have:
                    have.add(c2)
                    extra.append((c2, d + 0.05))
        return out + extra if extra else out

    def _classes_raw(self, bare, sc="latin"):
        if sc != "latin":
            direct = self.lex.surface.get(bare)
            if direct is not None:
                return [(self.lex.find(c), 0.0) for c in direct]
            lat = to_latin(bare)
            out = self.lex.resolve(lat)
            if not out and sc == "arab":
                out = self.lex.resolve_consonants(lat)
            return out or [("?" + bare, 0.0)]
        out = self.lex.resolve(bare)
        if not out or out[0][1] > 0.0:
            alt = strip_article_attached(bare)
            if alt:
                o2 = [(c, d + ARTICLE_PENALTY) for c, d in
                      self.lex.resolve(alt)]
                if o2:
                    merged = {}
                    for c, d in out + o2:
                        if c not in merged or d < merged[c]:
                            merged[c] = d
                    bv = min(merged.values())
                    out = sorted([(c, d) for c, d in merged.items()
                                  if d <= bv + 0.22], key=lambda x: x[1])
        if not out:
            return [("?" + "".join(self.lex.skel(bare)), 0.0)]
        return out

    # -- lexicon ------------------------------------------------------------
    def parse(self, name):
        p = self._parses.get(name)
        if p is None:
            p = NameParse(name)
            self._parses[name] = p
        return p

    def parse_variants(self, name):
        """Parses of *name*; 'Ben'/'B.' may be a nasab marker or a name."""
        key = "\x00" + name
        v = self._parses.get(key)
        if v is None:
            p = self.parse(name)
            v = [p]
            if p.nasab:
                words = [re.sub(r"[^a-z]", "", w)
                         for w in deaccent(name).replace(",", " ").split()]
                # "Ben"/"B." only gets a second, non-nasab reading when it
                # opens the name (Ben J. De la Cruz) or when reading it as a
                # marker would leave no name behind (John B. Smith)
                if (words and words[0] in AMBIG_NASAB) or \
                        (len(p.core) < 2 and
                         set(words) & AMBIG_NASAB):
                    alt = NameParse(name, STRICT_NASAB)
                    if alt.core != p.core:
                        v.append(alt)
            self._parses[key] = v
        return v

    def _build_lexicon(self):
        lex = self.lex
        persons = [e for e in self.entries
                   if (e.get("type") or "").lower() == "individual"]
        for e in persons:
            pp = self.parse(e.get("primary_name") or "")
            for bare, sc in pp.core:
                if sc == "latin":
                    lex.add_surface(bare, bare)
            for bare, sc in pp.nasab:
                if sc == "latin":
                    lex.add_surface(bare, bare)
        # script names aligned with a latin primary
        for e in persons:
            sn = e.get("script_name")
            pn = e.get("primary_name") or ""
            if not sn or script_of(pn) != "latin":
                continue
            pp, sp = self.parse(pn), self.parse(sn)
            if len(sp.core) == len(pp.core) and len(sp.nasab) == len(pp.nasab):
                for (sb, ssc), (pb, psc) in zip(sp.core, pp.core):
                    if ssc != "latin" and psc == "latin":
                        lex.add_surface(sb, pb)
                for (sb, ssc), (pb, psc) in zip(sp.nasab, pp.nasab):
                    if ssc != "latin" and psc == "latin":
                        lex.add_surface(sb, pb)
        # strong aliases aligned with the primary
        for e in persons:
            pn = e.get("primary_name") or ""
            pp = self.parse(pn)
            for al in e.get("aliases") or []:
                if al.get("strength") != "strong":
                    continue
                ap = self.parse(al.get("name") or "")
                if len(ap.core) == len(pp.core):
                    pairs = list(zip(ap.core, pp.core))
                elif len(ap.core) >= 2 and len(pp.core) >= 2:
                    # the alias may drop a middle name or a patronymic; the
                    # first and last parts still line up
                    pairs = [(ap.core[0], pp.core[0]),
                             (ap.core[-1], pp.core[-1])]
                else:
                    continue
                for (ab, asc), (pb, psc) in pairs:
                    if asc != "latin":
                        continue
                    # a nickname alias must not merge two full names
                    # (Ted = Edward or Theodore)
                    mg = not (ab in NICK_SET or pb in NICK_SET)
                    if psc == "latin":
                        lex.add_surface(ab, pb, merge=mg)
                    else:
                        for cls in lex.surface.get(pb) or ():
                            lex.add_surface(ab, cls, merge=mg)
                for (ab, asc), (pb, psc) in zip(ap.nasab, pp.nasab):
                    if asc == "latin" and psc == "latin":
                        lex.add_surface(ab, pb)
        # english nicknames: a nickname may belong to several full names, so
        # it must not merge them into one class
        for full, nicks in NICKNAMES.items():
            clss = lex.surface.get(full)
            if clss is None:
                for nk in nicks:
                    if nk in lex.surface:
                        clss = lex.surface[nk]
                        break
            if not clss:
                continue
            for cls in list(clss):
                lex.add_surface(full, cls, merge=False)
                for nk in nicks:
                    lex.add_surface(nk, cls, merge=False)
        # forms of one name in another naming tradition
        for full, alts in TRADITION_FORMS.items():
            clss = lex.surface.get(full)
            if not clss:
                continue
            for cls in list(clss):
                for alt in alts:
                    lex.add_surface(alt, cls, merge=False)
        # slavic feminine surnames
        for surf in list(lex.surface.keys()):
            if script_of(surf) != "latin":
                continue
            masc = None
            m = re.match(r"^(.*(?:ov|ev|in|yn))a$", surf)
            if m and m.group(1) in lex.surface:
                masc = m.group(1)
            elif surf.endswith("skaya") and surf[:-5] + "sky" in lex.surface:
                masc = surf[:-5] + "sky"
            elif surf.endswith("aya") and surf[:-3] + "y" in lex.surface:
                masc = surf[:-3] + "y"
            if masc:
                for a in lex.surface[surf]:
                    for b in lex.surface[masc]:
                        lex.union(a, b)
        lex.finalize()

    # -- index --------------------------------------------------------------
    def _build_index(self):
        # classes the watchlist itself uses as patronymics
        self.patro_classes = set()
        for e in self.entries:
            if (e.get("type") or "").lower() != "individual":
                continue
            names = [e.get("primary_name") or "", e.get("script_name") or ""]
            names += [a.get("name") or "" for a in e.get("aliases") or []
                      if a.get("strength") == "strong"]
            for nm in names:
                if not nm.strip():
                    continue
                p = self.parse(nm)
                for b, sc in p.core:
                    if looks_patronymic(b, sc):
                        for c, _ in self.classes(b, sc):
                            self.patro_classes.add(c)
        stems = set()
        for e in self.entries:
            if (e.get("type") or "").lower() in ("entity", "vessel"):
                w = org_words(e.get("primary_name") or "")
                if w:
                    stems.add(w[0])
        self.chinese_rom = build_chinese_map(stems)
        self.by_id = defaultdict(list)
        self.by_class = defaultdict(list)
        self.by_org = defaultdict(list)
        self.by_orgvar = defaultdict(list)
        self.by_weak = defaultdict(list)
        for e in self.entries:
            for ident in e.get("ids") or []:
                key = ((ident.get("type") or "").strip().lower(),
                       re.sub(r"[^a-z0-9]", "",
                              (ident.get("number") or "").lower()))
                self.by_id[key].append(e["uid"])
            for al in e.get("aliases") or []:
                if al.get("strength") != "weak":
                    continue
                nm = al.get("name") or ""
                self.by_weak[weak_key(nm)].append(e)
                sk = skeleton(nm)
                if sk:
                    self.by_weak[sk].append(e)
            typ = (e.get("type") or "").lower()
            if typ == "individual":
                names = self._person_names(e)
                e["_names"] = names
                seen = set()
                for nm in names:
                    for c in nm["given_cls"] + nm["family_cls"]:
                        if (c, id(nm)) in seen:
                            continue
                        seen.add((c, id(nm)))
                        self.by_class[c].append(e)
            else:
                keys, vkeys = set(), set()
                for nm in self._org_names(e):
                    keys.add(org_key(nm))
                    vkeys |= org_variant_keys(nm, self.chinese_rom)
                e["_orgkeys"] = keys
                for k in keys:
                    self.by_org[k].append(e)
                for k in vkeys:
                    self.by_orgvar[k].append(e)

    def _build_compat(self):
        """Link classes that are one name written in two naming traditions.

        Michael/Mikhail, Victoria/Viktoria, Alexander/Aleksandr: a customer
        spelling can sit between them, so both have to stay candidates.  Two
        classes of the *same* tradition are never linked - within one
        tradition similar names (Hassan/Hussein, Dalal/Talal, Fares/Farsi)
        are different people and the look-alike decoys rely on that.
        """
        lex = self.lex
        culture = {}
        for surf, clss in lex.surface.items():
            sc = script_of(surf)
            if sc == "latin":
                continue
            for c in clss:
                culture[lex.find(c)] = sc
        roles = defaultdict(set)
        for e in self.entries:
            for nm in e.get("_names") or ():
                for c in nm["given_cls"]:
                    roles[c].add("g")
                for c in nm["family_cls"]:
                    roles[c].add("f")
        surfs = defaultdict(list)
        for surf, sk, root in lex.entries:
            surfs[root].append(sk)
        bylen = defaultdict(list)
        for root, sks in surfs.items():
            for sk in sks:
                bylen[len(sk)].append((sk, root))
        compat = defaultdict(set)
        for root, sks in surfs.items():
            cu = culture.get(root, "latin")
            rl = roles.get(root)
            if not rl:
                continue
            for sk in sks:
                for L in (len(sk) - 1, len(sk), len(sk) + 1):
                    for sk2, root2 in bylen.get(L, ()):
                        if root2 == root or root2 in compat[root]:
                            continue
                        if culture.get(root2, "latin") == cu:
                            continue
                        if not (roles.get(root2) or set()) & rl:
                            continue
                        if pdist(sk, sk2, COMPAT_MAX) <= COMPAT_MAX:
                            compat[root].add(root2)
                            compat[root2].add(root)
        self.compat = dict(compat)

    def _org_names(self, e):
        out = [e.get("primary_name") or ""]
        for al in e.get("aliases") or []:
            if al.get("strength") == "strong":
                out.append(al.get("name") or "")
        return [n for n in out if n.strip()]

    def _person_names(self, e):
        out = []
        seen = set()
        cand = [e.get("primary_name") or ""]
        sn = e.get("script_name")
        if sn and sn != e.get("primary_name"):
            cand.append(sn)
        for al in e.get("aliases") or []:
            if al.get("strength") == "strong":
                cand.append(al.get("name") or "")
        for nm in cand:
            if not nm.strip():
                continue
            for p in self.parse_variants(nm):
                if not p.core:
                    continue
                keep = [c for i, c in enumerate(p.core)
                        if not (2 < len(p.core) and 0 < i < len(p.core) - 1
                                and looks_patronymic(c[0], c[1]))]

                if len(keep) < 2:
                    keep = list(p.core)
                gcls = [c for c, _ in self.classes(*keep[0])]
                fcls = [c for c, _ in self.classes(*keep[-1])]
                single = len(keep) == 1
                key = (tuple(sorted(gcls)), tuple(sorted(fcls)), single)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"raw": nm, "given_cls": gcls,
                            "family_cls": fcls, "single": single})
        return out

    # -- screening ----------------------------------------------------------
    def screen(self, cust):
        typ = (cust.get("type") or "").strip().lower()
        idt = (cust.get("id_type") or "").strip().lower()
        idn = re.sub(r"[^a-z0-9]", "", (cust.get("id_number") or "").lower())
        if idt and idn:
            uids = self.by_id.get((idt, idn))
            if uids:
                return sorted(uids)[0]
        name = cust.get("full_name") or ""
        dob = cust.get("dob") or ""
        if typ in ("entity", "vessel"):
            cands = self.match_org(name, typ)
        elif typ == "individual":
            cands = self.match_person(name, dob)
        else:
            cands = self.match_org(name) or self.match_person(name, dob)
        cands = cands + self.match_weak(name, dob)
        if not cands:
            return None
        cands.sort(key=lambda c: (-c[0], c[1]))
        return cands[0][1]

    def match_weak(self, name, dob):
        """Rule 3: a weak alias needs the customer name to be that alias and
        an identical full date of birth."""
        out = []
        nd = norm_date(dob)
        if len(nd) != 10:
            return out
        seen = set()
        for key in (weak_key(name), skeleton(name)):
            if not key:
                continue
            for e in self.by_weak.get(key, ()):
                if e["uid"] in seen:
                    continue
                seen.add(e["uid"])
                if norm_date(e.get("dob") or "") == nd:
                    out.append((2, e["uid"]))
        return out

    def match_org(self, name, typ=None):
        out = []
        seen = set()
        key = org_key(name)
        if not key:
            return out
        for e in self.by_org.get(key, ()):
            if typ and (e.get("type") or "").lower() != typ:
                continue
            if e["uid"] not in seen:
                seen.add(e["uid"])
                out.append((1, e["uid"]))
        if out:
            return out
        for k in org_variant_keys(name, self.chinese_rom):
            for e in self.by_orgvar.get(k, ()):
                if typ and (e.get("type") or "").lower() != typ:
                    continue
                if e["uid"] not in seen:
                    seen.add(e["uid"])
                    out.append((1, e["uid"]))
        return out

    def is_patro(self, bare, sc, cls):
        """A token is a patronymic if it is spelled like one or resolves to a
        class that the watchlist uses as a patronymic."""
        if looks_patronymic(bare, sc):
            return True
        return any(c in self.patro_classes for c, _ in cls)

    def _views(self, p):
        """(parse, token classes, candidate index sets) for a parsed name."""
        cls = [self.classes(b, sc) for b, sc in p.core_all]
        patro = [self.is_patro(b, sc, cls[i])
                 for i, (b, sc) in enumerate(p.core_all)]
        n = len(cls)
        views = []
        # the father's name in a nasab ("bin Khalid") is never the customer's
        # own given or family name; where the marker itself is ambiguous
        # ("Ben", "B.") parse_variants supplies a second reading instead.
        base = [i for i in range(n) if i not in p.nasab_idx]
        if base:
            idx = [i for i in base if not (patro[i] and i > base[0])]
            views.append(idx if len(idx) >= 2 else list(base))
        return cls, views

    def match_person(self, name, dob):
        parses = []
        for p in self.parse_variants(name):
            if p.core_all:
                cls, views = self._views(p)
                parses.append((p, cls, views))
        if not parses:
            return []
        cand = {}
        for p, cls, views in parses:
            for lst in cls:
                for c, _ in lst:
                    for e in self.by_class.get(c, ()):
                        cand[e["uid"]] = e
        out = []
        for uid, e in cand.items():
            st = dob_compare(dob, e.get("dob") or "")
            if st == "conflict":
                continue
            hit = False
            for p, cls, views in parses:
                for nm in e["_names"]:
                    if self.name_match(p, cls, views, nm):
                        hit = True
                        break
                if hit:
                    break
            if hit:
                out.append((2 if st == "agree" else 1, uid))
        return out

    def name_match(self, p, cls, views, nm):
        gset, fset = set(nm["given_cls"]), set(nm["family_cls"])
        for idx in views:
            if nm["single"]:
                if len(idx) != 1 or not fset:
                    continue
                if set(c for c, _ in cls[idx[0]]) & fset:
                    return True
                continue
            if len(idx) < 2 or not gset or not fset:
                continue
            first, last = idx[0], idx[-1]
            cf = set(c for c, _ in cls[first])
            cl = set(c for c, _ in cls[last])
            if len(idx) > 2:
                # a compound surname may be written spaced: Smith Jones
                cf |= self._joined_classes(p, idx[0], idx[1])
                cl |= self._joined_classes(p, idx[-2], idx[-1])
            if (cf & gset) and (cl & fset):
                return True
            if (cl & gset) and (cf & fset):
                return True
            if p.strands:
                ef = cf | self._strand_classes(p, p.core_all[first])
                el = cl | self._strand_classes(p, p.core_all[last])
                if (ef & gset) and (el & fset):
                    return True
                if (el & gset) and (ef & fset):
                    return True
        return False

    def _joined_classes(self, p, i, j):
        a, asc = p.core_all[i]
        b, bsc = p.core_all[j]
        if asc != "latin" or bsc != "latin":
            return set()
        return set(c for c, _ in self.classes(a + b))

    def _strand_classes(self, p, core_tok):
        bare, sc = core_tok
        if sc != "latin":
            return set()
        out = set()
        for pref in ("".join(p.strands), p.strands[-1]):
            if not pref:
                continue
            for c, _ in self.classes(pref + bare):
                out.add(c)
        return out


# ---------------------------------------------------------------------------
# 9. driver
# ---------------------------------------------------------------------------

def run(watchlist_path, customers_path, out_path):
    with open(watchlist_path, encoding="utf-8") as fh:
        watchlist = json.load(fh)
    eng = Engine(watchlist)
    rows = []
    with open(customers_path, encoding="utf-8-sig", newline="") as fh:
        for cust in csv.DictReader(fh):
            uid = eng.screen(cust)
            rows.append((cust.get("customer_id", ""),
                         "MATCH" if uid else "NO_MATCH", uid or ""))
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        wr = csv.writer(fh)
        wr.writerow(["customer_id", "decision", "matched_uid"])
        wr.writerows(rows)
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="sanctions screening")
    ap.add_argument("--watchlist", required=True)
    ap.add_argument("--customers", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    run(args.watchlist, args.customers, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
