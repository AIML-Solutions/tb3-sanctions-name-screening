#!/usr/bin/env python3
"""
Sanctions screening engine (Python 3.12, standard library only).

    python3 screen.py --watchlist watchlist.json \
                      --customers customers.csv --out decisions.csv

It writes one `customer_id,decision,matched_uid` row per customer and applies
the rules of screening_policy.md: identifiers (rule 1), name equivalence
across transliterations, name order, particles, patronymics and nicknames
(rule 2), strong and weak aliases (rule 3), dates of birth (rule 4), company
suffixes, chinese romanisations and vessel prefixes (rule 5).

How name equivalence is decided
-------------------------------
The watchlist is a *closed pool* of canonical names, so every name token --
from the list or from a customer -- is resolved to one of those canonical
roots, and two names correspond when their multisets of roots are equal
(after particles, patronymics, nasab elements, titles and initials are
removed).  Resolution uses, in order:

  1. a phonetic key (grapheme -> coarse phoneme) that absorbs the bulk of the
     romanisation noise;
  2. an index of generated spellings -- every root is expanded under the
     common conventions (French, German, Polish, Turkish, Indonesian,
     scientific/ISO, Gulf Arabic with sun-letter assimilation, western
     nicknames) -- plus the spellings mined from the list itself, where an
     entry's aliases and original-script name denote the same person;
  3. a weighted edit distance over the phonetic alphabet, for spellings no
     generator produced.

Resolving both sides to a root, rather than comparing two spellings directly,
is what keeps look-alikes apart: a customer's "Hasen" is nearer to the root
Hassan than to Hussein, so it never matches a Hussein on the list.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata

# --------------------------------------------------------------------------
# 1.  character folding
# --------------------------------------------------------------------------

_SPECIAL = {
    "ß": "ss", "ä": "a", "ö": "o", "ü": "u", "å": "a", "æ": "ae", "ø": "o",
    "ñ": "n", "ç": "ch", "ş": "sh", "ğ": "g", "ı": "i", "ł": "l", "ż": "zh",
    "ź": "z", "ś": "sh", "ć": "ch", "ń": "n", "ą": "a", "ę": "e", "č": "ch",
    "š": "sh", "ž": "zh", "ř": "rzh", "ě": "e", "ů": "u", "đ": "d", "þ": "th",
    "ð": "d", "ġ": "gh", "ḥ": "h", "ṣ": "s", "ṭ": "t", "ẓ": "z", "ḍ": "d",
    "ʿ": "", "ʾ": "", "ʻ": "", "’": "", "'": "", "`": "", "´": "",
}

_CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "і": "i", "ї": "yi", "є": "ye", "ґ": "g", "ў": "u",
}

_ARA = {
    "ا": "a", "أ": "a", "إ": "i", "آ": "a", "ب": "b", "ت": "t", "ث": "th",
    "ج": "j", "ح": "h", "خ": "kh", "د": "d", "ذ": "dh", "ر": "r", "ز": "z",
    "س": "s", "ش": "sh", "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "",
    "غ": "gh", "ف": "f", "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n",
    "ه": "h", "و": "u", "ي": "y", "ى": "a", "ة": "a", "ء": "", "ئ": "y",
    "ؤ": "u", "پ": "p", "چ": "ch", "ژ": "zh", "گ": "g", "ک": "k", "ی": "y",
    "ٱ": "a", "ه‌": "h",
}

_AR_RANGE = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")
_CY_RANGE = re.compile(r"[Ѐ-ӿԀ-ԯ]")
_PERSIAN_ONLY = re.compile(r"[پچژگکی]")


def script_of(text: str) -> str:
    if not text:
        return "latin"
    if _AR_RANGE.search(text):
        return "fa" if _PERSIAN_ONLY.search(text) else "ar"
    if _CY_RANGE.search(text):
        return "cyr"
    return "latin"


def translit(text: str) -> str:
    """Transliterate Arabic/Persian/Cyrillic characters to Latin."""
    out = []
    for ch in text.lower():
        if ch in _CYR:
            out.append(_CYR[ch])
        elif ch in _ARA:
            out.append(_ARA[ch])
        elif "ً" <= ch <= "ْ" or ch == "ـ":
            continue  # arabic diacritics / tatweel
        else:
            out.append(ch)
    return "".join(out)


def fold(text: str) -> str:
    """Lower-case, expand special letters, drop diacritics, keep [a-z ]."""
    text = text.lower()
    text = "".join(_SPECIAL.get(c, c) for c in text)
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z]+", "", text)
    return text


# --------------------------------------------------------------------------
# 2.  phonetic key
# --------------------------------------------------------------------------
# alphabet: vowels aeiou   consonants b p f t d k g s z X J h m n l r
#   X = post-alveolar family (sh / ch / zh / j / sch / tsch / cz / sz ...)
#   J = the letter <j> read as a separate ambiguous sound (j ~ y ~ zh)

_DIGRAPHS = [
    ("schtsch", "X"), ("stsch", "X"), ("shch", "X"), ("szcz", "X"),
    ("sztsch", "X"), ("chtch", "X"),
    ("dsch", "X"), ("tsch", "X"), ("sch", "X"), ("tch", "X"), ("dzh", "X"),
    ("dj", "X"), ("sh", "X"), ("zh", "X"), ("ch", "X"), ("sz", "X"),
    ("cz", "X"), ("sj", "X"), ("tj", "X"), ("kh", "h"), ("gh", "g"),
    ("ph", "f"), ("th", "t"), ("ck", "k"), ("qu", "k"), ("q", "k"),
    ("x", "ks"), ("ts", "z"), ("tz", "z"), ("cs", "X"),
]
_VOWELS = set("aeiou")


def pkey(word: str) -> str:
    """Phonetic key of an already folded latin word."""
    if not word:
        return ""
    s = word
    # vowel digraphs
    s = s.replace("oeu", "u").replace("ou", "u").replace("oe", "o")
    s = s.replace("ue", "u").replace("ae", "e").replace("ee", "i")
    s = s.replace("ij", "i").replace("aa", "a").replace("oo", "u")
    s = s.replace("ii", "i").replace("uu", "u")
    out = []
    i = 0
    n = len(s)
    while i < n:
        for pat, rep in _DIGRAPHS:
            if s.startswith(pat, i):
                out.append(rep)
                i += len(pat)
                break
        else:
            c = s[i]
            if c == "c":
                out.append("C")
            elif c == "w":
                out.append("f")
            elif c == "v":
                out.append("f")
            elif c == "j":
                out.append("J")
            elif c == "y":
                out.append("i")
            else:
                out.append(c)
            i += 1
    key = "".join(out)
    # collapse doubles
    res = []
    for c in key:
        if res and res[-1] == c:
            continue
        res.append(c)
    key = "".join(res)
    # the last stop of a word is unstable across conventions (Ahmad / Ahmet /
    # Ahmede), so it gets its own symbol
    for i in range(len(key) - 1, -1, -1):
        if key[i] not in _VOWELS:
            if key[i] in "dt":
                key = key[:i] + "D" + key[i + 1:]
            break
    return key


# --------------------------------------------------------------------------
# 3.  weighted edit distance
# --------------------------------------------------------------------------

def _sym(pairs, cost, table):
    for a, b in pairs:
        table[(a, b)] = cost
        table[(b, a)] = cost


_SUB = {}
_sym([("a", "e"), ("e", "i"), ("o", "u")], 0.20, _SUB)
_sym([("a", "o"), ("a", "i"), ("e", "o"), ("e", "u"), ("i", "o")], 0.45, _SUB)
_sym([("a", "u"), ("i", "u")], 0.45, _SUB)
_sym([("X", "J")], 0.15, _SUB)
_sym([("C", "k"), ("C", "s"), ("C", "z")], 0.25, _SUB)
_sym([("C", "X")], 0.30, _SUB)
_sym([("C", "J"), ("C", "g")], 0.40, _SUB)
_sym([("X", "s"), ("X", "z"), ("J", "i")], 0.30, _SUB)
_sym([("X", "g"), ("J", "g"), ("J", "z"), ("s", "z")], 0.35, _SUB)
_sym([("X", "h"), ("X", "k"), ("J", "s")], 0.45, _SUB)
_sym([("b", "p"), ("p", "f"), ("f", "b")], 0.30, _SUB)
_sym([("D", "d"), ("D", "t")], 0.10, _SUB)
_sym([("t", "d")], 0.55, _SUB)
_sym([("D", "z"), ("D", "s")], 0.75, _SUB)
_sym([("k", "g"), ("k", "h"), ("g", "h")], 0.50, _SUB)
_sym([("m", "n")], 0.60, _SUB)
_sym([("l", "r")], 0.75, _SUB)
_sym([("s", "t"), ("z", "d"), ("d", "z")], 0.70, _SUB)

_INDEL = {"h": 0.25, "J": 0.35, "i": 0.30, "a": 0.30, "e": 0.30,
          "o": 0.30, "u": 0.30, "D": 0.85}
_DEF_INDEL = 1.0


def _ind(c):
    return _INDEL.get(c, _DEF_INDEL)


def wdist(a: str, b: str, cap: float = 3.0) -> float:
    """Weighted Levenshtein distance between two phonetic keys."""
    if a == b:
        return 0.0
    la, lb = len(a), len(b)
    if not la:
        return sum(_ind(c) for c in b)
    if not lb:
        return sum(_ind(c) for c in a)
    prev = [0.0] * (lb + 1)
    for j in range(1, lb + 1):
        prev[j] = prev[j - 1] + _ind(b[j - 1])
    for i in range(1, la + 1):
        ca = a[i - 1]
        cur = [prev[0] + _ind(ca)] + [0.0] * lb
        best = cur[0]
        for j in range(1, lb + 1):
            cb = b[j - 1]
            if ca == cb:
                v = prev[j - 1]
            else:
                v = prev[j - 1] + _SUB.get((ca, cb), 1.0)
            d = prev[j] + _ind(ca)
            if d < v:
                v = d
            d = cur[j - 1] + _ind(cb)
            if d < v:
                v = d
            cur[j] = v
            if v < best:
                best = v
        if best > cap:
            return cap + 1.0
        prev = cur
    return prev[lb]


def skeleton(key: str) -> str:
    return "".join(c for c in key if c not in _VOWELS)




# --------------------------------------------------------------------------
# 3b.  original-script keys
# --------------------------------------------------------------------------
# Arabic script writes no short vowels, and <w>/<y> double as long vowels, so
# one written form stands for several latin readings.

_SIND = {"h": 0.10, "J": 0.15, "i": 0.08, "a": 0.08, "e": 0.08, "o": 0.08,
         "u": 0.08, "D": 0.80}


def sdist(a: str, b: str, cap: float = 2.0) -> float:
    """Distance between a script-derived key and a latin key."""
    la, lb = len(a), len(b)
    if not la or not lb:
        return 3.0
    prev = [0.0] * (lb + 1)
    for j in range(1, lb + 1):
        prev[j] = prev[j - 1] + _SIND.get(b[j - 1], _DEF_INDEL)
    for i in range(1, la + 1):
        ca = a[i - 1]
        ia = _SIND.get(ca, _DEF_INDEL)
        cur = [prev[0] + ia] + [0.0] * lb
        best = cur[0]
        for j in range(1, lb + 1):
            cb = b[j - 1]
            v = prev[j - 1] if ca == cb else prev[j - 1] + _SUB.get((ca, cb), 1.0)
            d = prev[j] + ia
            if d < v:
                v = d
            d = cur[j - 1] + _SIND.get(cb, _DEF_INDEL)
            if d < v:
                v = d
            cur[j] = v
            if v < best:
                best = v
        if best > cap:
            return cap + 1.0
        prev = cur
    return prev[lb]


def script_keys(folded: str) -> list:
    """Readings of a transliterated arabic/persian token (w/y ambiguity)."""
    outs = [""]
    for ch in folded:
        if ch == "u":
            outs = [o + c for o in outs for c in ("u", "v")]
        elif ch == "y":
            outs = [o + c for o in outs for c in ("y", "j")]
        else:
            outs = [o + ch for o in outs]
        if len(outs) > 32:
            outs = outs[:32]
    seen = []
    for o in outs:
        k = pkey(o)
        if k not in seen:
            seen.append(k)
    return seen
# --------------------------------------------------------------------------
# 4.  spelling generators (canonical name -> conventional spellings)
# --------------------------------------------------------------------------

def _apply(rules, s):
    for pat, rep in rules:
        s = re.sub(pat, rep, s)
    return s


_CONVENTIONS = [
    # german
    [(r"shch", "schtsch"), (r"sh", "sch"), (r"ch", "tsch"), (r"zh", "sch"),
     (r"kh", "ch"), (r"v", "w"), (r"ts", "z"), (r"^y", "j"), (r"ya", "ja"),
     (r"yu", "ju"), (r"yo", "jo"), (r"ye", "je"), (r"y", "j"), (r"ou", "u")],
    # german (light)
    [(r"kh", "ch"), (r"v", "w"), (r"^y", "j"), (r"ya", "ja"), (r"yu", "ju"),
     (r"j", "dsch")],
    # french
    [(r"shch", "chtch"), (r"sh", "ch"), (r"ch", "tch"), (r"zh", "j"),
     (r"ov$", "off"), (r"ev$", "eff"), (r"u", "ou"), (r"y$", "i"),
     (r"^y", "i"), (r"j", "dj"), (r"kh", "kh")],
    # french (light)
    [(r"ov$", "off"), (r"ev$", "eff"), (r"sh", "ch"), (r"ch", "tch"),
     (r"u", "ou"), (r"ee", "e")],
    # polish
    [(r"shch", "szcz"), (r"sh", "sz"), (r"ch", "cz"), (r"zh", "z"),
     (r"v", "w"), (r"kh", "ch")],
    # scientific / ISO, diacritics dropped
    [(r"shch", "sc"), (r"sh", "s"), (r"ch", "c"), (r"zh", "z"), (r"kh", "h"),
     (r"ts", "c"), (r"y$", "ij"), (r"iy$", "ij"), (r"^y", "j"), (r"ya", "ja"),
     (r"yu", "ju"), (r"ye", "e"), (r"y", "j"), (r"j$", "j")],
    # scientific, <j> for the i-glide
    [(r"shch", "sc"), (r"sh", "s"), (r"ch", "c"), (r"zh", "z"), (r"kh", "h"),
     (r"ts", "c"), (r"ai", "aj"), (r"ei", "ej"), (r"y$", "ij"), (r"y", "j")],
    # scientific with <ja> for <ia>
    [(r"shch", "sc"), (r"sh", "s"), (r"ch", "c"), (r"zh", "z"), (r"kh", "h"),
     (r"ts", "c"), (r"ia", "ja"), (r"iu", "ju"), (r"y$", "ij"), (r"^y", "j"),
     (r"ya", "ja"), (r"yu", "ju"), (r"y", "j")],
    # polish with <ja>/<ie>
    [(r"shch", "szcz"), (r"sh", "sz"), (r"ch", "cz"), (r"zh", "z"),
     (r"v", "w"), (r"kh", "ch"), (r"ia", "ja"), (r"^ye", "je"), (r"ye", "je"),
     (r"e", "ie")],
    # turkish
    [(r"^j", "c"), (r"j", "c"), (r"q", "k"), (r"kh", "h"), (r"th", "t"),
     (r"sh", "s"), (r"ou", "u"), (r"w", "v"), (r"d$", "t"), (r"a([^aeiou]*)$",
                                                             r"e\1")],
    # turkish (light)
    [(r"^j", "c"), (r"q", "k"), (r"kh", "h"), (r"sh", "s"), (r"d$", "t")],
    # indonesian / malay
    [(r"sh", "sj"), (r"j", "dj"), (r"ch", "tj"), (r"kh", "ch"), (r"u", "oe"),
     (r"^y", "j"), (r"y", "j"), (r"q", "k"), (r"^h", "h")],
    # indonesian (light)
    [(r"u", "oe"), (r"^y", "j"), (r"sh", "sj"), (r"c", "tj")],
    # arabic gulf / heavy
    [(r"q", "gh"), (r"j", "g"), (r"th", "t"), (r"dh", "d")],
    [(r"q", "k"), (r"j", "j"), (r"ee", "i"), (r"ou", "u")],
    # doubled vowels / long vowel spellings
    [(r"i", "ee"), (r"u", "oo")],
    [(r"ou", "u"), (r"u", "ou")],
    # unstressed vowel drift
    [(r"i", "e")],
    [(r"e", "i")],
    [(r"a", "e")],
]


def gen_variants(name: str, decorate: bool = True) -> set:
    """Conventional spellings for one canonical latin name token."""
    base = name.lower()
    out = {base}
    for rules in _CONVENTIONS:
        try:
            out.add(_apply(rules, base))
        except re.error:
            pass
    if not decorate:
        return {v for v in out if v}
    extra = set()
    for v in list(out):
        if v and v[-1] not in "aeiou":
            extra.add(v + "e")
        if v.endswith("a"):
            extra.add(v + "h")
        if v.endswith("i"):
            extra.add(v + "e")
        if v.endswith("y"):
            extra.add(v[:-1] + "i")
            extra.add(v[:-1] + "iy")
        if "ks" in v:
            extra.add(v.replace("ks", "x"))
        if "ov" in v:
            extra.add(v.replace("ov", "ow"))
    out |= extra
    return {v for v in out if v}


# nicknames / hypocorisms  (variant -> canonical given name)
NICKNAMES = {
    "bill": ["william"], "billy": ["william"], "will": ["william"],
    "willy": ["william"], "liam": ["william"], "wil": ["william"],
    "kate": ["katherine"], "katie": ["katherine"], "kathy": ["katherine"],
    "kathie": ["katherine"], "kay": ["katherine"],
    "cathy": ["katherine"], "katy": ["katherine"], "kat": ["katherine"],
    "kitty": ["katherine"], "kit": ["katherine", "christopher"],
    "beth": ["elizabeth"], "liz": ["elizabeth"], "lizzy": ["elizabeth"],
    "lizzie": ["elizabeth"], "elsie": ["elizabeth"], "bessie": ["elizabeth"],
    "betty": ["elizabeth"], "betsy": ["elizabeth"], "eliza": ["elizabeth"],
    "libby": ["elizabeth"], "elisabeth": ["elizabeth"],
    "meg": ["margaret"], "maggie": ["margaret"], "peggy": ["margaret"],
    "marge": ["margaret"], "margie": ["margaret"], "greta": ["margaret"],
    "becky": ["rebecca"], "becca": ["rebecca"], "reba": ["rebecca"],
    "sam": ["samuel"], "sammy": ["samuel"],
    "mike": ["michael"], "mikey": ["michael"], "mick": ["michael"],
    "micky": ["michael"], "misha": ["michael"],
    "tony": ["anthony"], "ant": ["anthony"],
    "pete": ["peter"], "petey": ["peter"], "pedro": ["peter"],
    "pietro": ["peter"],
    "joe": ["joseph", "jose"], "joey": ["joseph", "jose"], "josef": ["joseph"],
    "pepe": ["jose"], "jos": ["joseph"],
    "fred": ["frederick"], "freddie": ["frederick"], "freddy": ["frederick"],
    "fritz": ["frederick"], "rick": ["richard", "frederick"],
    "rob": ["robert"], "bob": ["robert"], "bobby": ["robert"],
    "robbie": ["robert"], "bert": ["robert"], "bobbie": ["robert"],
    "dick": ["richard"], "ricky": ["richard"], "rich": ["richard"],
    "richie": ["richard"],
    "chuck": ["charles"], "charlie": ["charles"], "chas": ["charles"],
    "carlos": ["charles"],
    "dot": ["dorothy"], "dotty": ["dorothy"], "dottie": ["dorothy"],
    "dolly": ["dorothy"], "dora": ["dorothy"], "dorthy": ["dorothy"],
    "pat": ["patricia"], "patty": ["patricia"], "trish": ["patricia"],
    "tricia": ["patricia"], "patsy": ["patricia"],
    "jen": ["jennifer"], "jenny": ["jennifer"], "jenn": ["jennifer"],
    "sue": ["susan"], "suzy": ["susan"], "susie": ["susan"],
    "suzie": ["susan"], "suzanne": ["susan"],
    "tom": ["thomas"], "tommy": ["thomas"], "tommie": ["thomas"],
    "chris": ["christopher"], "topher": ["christopher"],
    "dan": ["daniel"], "danny": ["daniel"], "dani": ["daniel"],
    "ed": ["edward"], "eddie": ["edward"], "ned": ["edward"],
    "ted": ["edward", "theodore"], "teddy": ["edward", "theodore"],
    "theo": ["theodore"],
    "jim": ["james"], "jimmy": ["james"], "jamie": ["james"],
    "jimmie": ["james"],
    "nick": ["nicholas"], "nico": ["nicholas"], "nicky": ["nicholas"],
    "nicolas": ["nicholas"], "niklas": ["nicholas"],
    "andy": ["andrew"], "drew": ["andrew"],
    "alex": ["alexander"], "sandy": ["alexander"], "xander": ["alexander"],
    "ben": ["benjamin"], "benny": ["benjamin"], "benji": ["benjamin"],
    "hank": ["henry"], "harry": ["henry"], "hal": ["henry"],
    "steve": ["steven"], "stevie": ["steven"], "stephen": ["steven"],
    "tori": ["victoria"], "vicky": ["victoria"], "vickie": ["victoria"],
    "vic": ["victoria"],
    "barb": ["barbara"], "babs": ["barbara"], "barbie": ["barbara"],
    "matt": ["matthew"], "matty": ["matthew"],
    "frank": ["francisco"], "frankie": ["francisco"],
    "paco": ["francisco"], "pancho": ["francisco"],
    "cisco": ["francisco"], "fran": ["francisco"], "francis": ["francisco"],
    "jack": ["john"], "johnny": ["john"], "jon": ["john"], "jonny": ["john"],
    "jackie": ["john"],
    "eugene": ["yevgeny"], "gene": ["yevgeny"],
    "marie": ["maria"], "mary": ["maria"],
}

# lexical (non-transliterative) renderings used by some conventions
LEXICAL = {
    "muhammad": ["mehmet", "muhammet", "mohammet", "mehmed"],
    "ahmad": ["ahmet", "achmad", "achmat"],
    "khadija": ["hatice", "hatije", "chadidjah"],
    "aisha": ["ayse", "aise", "aisyah", "aisjah"],
    "zainab": ["zeynep", "zeyneb"],
    "amina": ["emine"],
    "mariam": ["meryem"],
    "maryam": ["meryem"],
    "fatima": ["fatma"],
    "fatemeh": ["fatma"],
    "najjar": ["neccar", "nacar", "naggar", "nagar"],
    "jamal": ["cemal", "djemal", "gamal"],
    "kamal": ["kemal"],
    "yusuf": ["joesoef", "jusuf", "yousef", "youssef"],
    "omar": ["omer", "oemar", "umar"],
    "anwar": ["enver"],
    "majid": ["mecit", "macit", "madjid"],
    "rashid": ["resit", "rasit", "rasjid", "rasyid"],
    "salim": ["selim"],
    "karim": ["kerim", "kerem", "kariem"],
    "samir": ["semir", "samier"],
    "khalid": ["halit", "halid", "chalid", "cholid"],
    "qasim": ["kasim", "gasim"],
    "hussein": ["huseyin", "hoesein", "husein"],
    "mahmoud": ["mahmut", "mahmoed"],
    "nabil": ["nebil", "nabiel"],
    "walid": ["velid", "walied"],
    "tariq": ["tarik"],
    "sayed": ["seyyid", "seyid", "sajjid"],
    "yevgeny": ["eugene", "evgenij", "jewgenij"],
    "mikhail": ["mihail", "michail"],
    "nikolai": ["nikolaj"],
    "yelizaveta": ["elizaveta", "jelizaveta"],
    "hisham": ["hisam", "hisjam", "hisyam"],
    "bashar": ["besar", "basjar", "basyar"],
    "shahin": ["sahin", "sjahin", "syahin"],
    "shamsi": ["semsi", "sjamsi", "syamsi"],
    "darwish": ["darwisj", "darwisy"],
    "mansour": ["mansoer", "mansur"],
    "yassin": ["jassin", "yasin"],
    "hashimi": ["hasjimi", "hasyimi"],
    "jabouri": ["djabouri", "gabouri"],
    "sultan": ["soeltan"],
    "mustafa": ["moestafa", "mustapha"],
    "nour": ["noer", "nur"],
    "layla": ["leyla", "laila"],
    "salma": ["selma"],
    "ibrahim": ["ibrahem", "brahim"],
    "abdaziz": ["abdulazis", "abdelaziz", "abdoelazis"],
}

# names that are the same person across the culture pools of the list
CROSS_POOL = [
    ("aleksandr", "alexander"), ("maksim", "maxim"),
    ("viktoria", "victoria"), ("yelizaveta", "elizabeth"),
    ("mariam", "maryam"), ("hussein", "hossein"), ("layla", "leila"),
    ("mahdi", "mehdi"), ("saeed", "saeid"), ("hashimi", "hashemi"),
    ("fatima", "fatemeh"), ("maria", "mariya"), ("yusuf", "yousef"),
    ("nikolai", "nicholas"), ("mikhail", "michael"), ("yuri", "yury"),
]

# chinese surname stems: pinyin -> other romanisations
CHINESE = {
    "li": ["lee", "lei", "ly", "ri", "lie"],
    "zhao": ["chao", "chiu", "chio", "jiu", "diu"],
    "song": ["sung", "soong", "shong", "sng"],
    "jiang": ["chiang", "kong", "cheung", "keong", "kang", "chio", "geong"],
    "dai": ["tai", "toa", "tye", "tay"],
    "ye": ["yeh", "yip", "ip", "yap", "iap", "yeap", "yeoh"],
    "guo": ["kuo", "kwok", "kwek", "quek", "kueh", "koay", "kok", "kuah"],
    "fan": ["faan", "huan", "hoan", "hwan", "pham", "van"],
    "qian": ["chien", "chinn", "tsien", "chi", "chin"],
    "du": ["tu", "to", "too", "toh", "doo", "tou"],
    "luo": ["lo", "law", "loh", "lore"],
    "peng": ["pang", "phang", "pheh", "beng", "phe", "pheng"],
    "gao": ["kao", "ko", "koh", "kou", "kow", "kaw"],
    "liu": ["liou", "lau", "lauw", "low", "liew", "lew", "lieu", "yau"],
    "tang": ["tong", "tng", "teng", "thong", "thang", "tang"],
    "lin": ["lim", "lam", "ling", "liem", "lien"],
    "hu": ["hoo", "woo", "oh", "ow", "ou", "hoe", "wu"],
    "zhu": ["chu", "choo", "chue", "gee", "tsu"],
    "wu": ["ng", "goh", "ngo", "woo", "ngoh", "eng", "go", "oo"],
    "liang": ["leung", "leong", "neo", "niu", "nio", "liong", "nyo"],
    "yang": ["yeung", "yeo", "yong", "iong", "ieong", "yeoh"],
    "ma": ["mah", "mar", "beh", "bey", "mak"],
    "chen": ["chan", "tan", "chin", "ting", "chun", "chean"],
    "yuan": ["yuen", "oan", "uan", "yen", "guan"],
    "xie": ["hsieh", "tse", "che", "cheah", "chia", "sia", "shieh", "chay"],
    "xu": ["hsu", "hui", "khoo", "chee", "zee", "hooi", "shui", "tsui", "koh"],
    "zeng": ["tseng", "tsang", "jeng"],
    "pan": ["poon", "pun", "phua", "puan", "pua", "phoon"],
    "sun": ["suen", "soon", "swan", "shuen", "sng"],
    "zhou": ["chou", "chow", "chau", "chew", "chiew", "jew", "jow", "chiu"],
    "feng": ["fung", "foong", "fong", "pheng", "pang"],
    "wang": ["wong", "ong", "heng", "vang", "waan", "wung"],
    "huang": ["hwang", "wong", "ng", "ooi", "uy", "oei", "whang", "bong"],
    "cai": ["tsai", "choi", "choy", "chua", "chuah", "chai", "chye", "tsay"],
    "he": ["ho", "hoe", "hor", "hoh", "hah"],
    "lu": ["loo", "luk", "lok", "loke", "look", "lo", "loh"],
    "cao": ["tsao", "cho", "chho", "tso", "chaw"],
    "deng": ["teng", "tang", "tan", "thang", "theng", "tung"],
    "cui": ["chui", "chwee", "tsuey", "tsui"],
    "han": ["hon", "hahn", "haan", "hann"],
    "shen": ["sum", "sham", "sim", "shum", "sen", "shim"],
    "zhang": ["chang", "cheung", "cheong", "teo", "tio", "tiu", "chong",
              "jang", "tiong", "tjong"],
    "zheng": ["cheng", "cheang", "tay", "tee", "chang"],
    "wei": ["wai", "ngai", "goay"],
    "ding": ["ting", "teng"],
    "yu": ["yue", "yau", "yee", "ie", "u", "hsu", "yi"],
    "lai": ["lie", "loi", "lay"],
    "qiu": ["chiu", "yau", "khoo", "hew"],
    "xiao": ["hsiao", "siu", "sio", "shaw", "seow"],
    "ceng": ["tsang"],
}

# --------------------------------------------------------------------------
# 5.  name structure
# --------------------------------------------------------------------------

PARTICLES = {
    "de", "del", "della", "der", "den", "di", "da", "das", "dos", "du",
    "la", "le", "les", "van", "von", "vander", "vanden", "mac", "mc",
    "bin", "ibn", "ben", "bint", "binti", "binte", "bte", "al", "el", "ul",
    "ould", "ap", "abu",
}
NASAB = {"bin", "ibn", "ben", "bint", "binti", "binte", "bte", "b", "bn",
         "veled", "walad"}
SURNAME_PREFIX = sorted(["vander", "vanden", "vonder", "van", "von", "mac",
                         "mc", "de", "del", "dela", "della", "des", "du",
                         "di", "da", "dos", "le", "la", "o", "st"], key=len, reverse=True)
ARTICLE_PREFIX = sorted(
    ["ash", "adh", "ath", "ech", "esh", "ish", "ad", "as", "at", "an", "ar",
     "az", "al", "el", "ul", "il", "ol", "es", "er", "ez", "en", "em", "ed",
     "et", "ac"], key=len, reverse=True)
ABD = {"abd", "abdu", "abdul", "abdel", "abdal", "abdol", "abed", "abdoul",
       "abdool", "abdou", "bd", "abda", "abt", "apd"}
ALLAH = re.compile(r"^[auoe]*l+(?:[ao]h?|h)$")

TITLES = {"mr", "mrs", "ms", "miss", "dr", "prof", "professor", "sir",
          "madam", "messrs"}
SUFFIXES = {"jr", "sr", "phd", "md", "esq"}

PATRONYMIC = re.compile(
    r"(vich|vitch|vitsch|witsch|wich|witch|wicz|vic|vics|vych|"
    r"vna|wna|ivna|evna|ovna|itschna|ichna)$")
# the same test on the phonetic key, so that -owitsch, -ovic, -owicz, -ovitjh
# and friends are all recognised
PATRONYMIC_KEY = re.compile(r"^.{3,}[oeui][fp][aeiou]*[XCzskt]{1,2}h?e?$")
PATRONYMIC_KEY2 = re.compile(r"^.{3,}[oeui][fp][aeiou]*n[aeiou]h?$")

LEGAL = {
    "llc", "lllc", "ltd", "limited", "liability", "company", "co", "corp",
    "corporation", "inc", "incorporated", "sa", "sociedad", "anonima",
    "gmbh", "jsc", "joint", "stock", "ao", "oao", "ooo", "pjsc", "ojsc",
    "fze", "fzllc", "fzco", "fz", "free", "zone", "establishment", "public",
    "plc", "ag", "nv", "bv", "srl", "spa", "pte", "pty", "kg", "ohg", "se",
    "oy", "ab", "as", "sarl", "sas", "sl", "cjsc", "zao", "pt", "tbk",
    "holding",
}
VESSEL_PREFIX = {"m/v", "mv", "m/t", "mt", "ms", "m/s", "ss", "s/s", "mss",
                 "vessel", "the", "fv", "f/v", "rv", "tug", "motor", "tanker"}


_HYPH = re.compile(r"[-‐‑–—]+")
_ART_SET = frozenset(ARTICLE_PREFIX)
_ART_CAP = re.compile(r"^(?:Al|El|Ul|As|Ash|Ad|Adh|At|Ath|An|Ar|Az|Es|Ez|En)"
                      r"(?=[A-Z])")


def _art_head(tok: str) -> bool:
    """True when the token starts with 'al-' and friends."""
    m = re.match(r"^([^-‐‑–—'’]{1,3})['’-]", tok)
    return bool(m) and fold(m.group(1)) in _ART_SET


def split_tokens(name: str) -> list:
    """Split a name into tokens; an article joined by a hyphen stays attached."""
    name = name.replace("’", "'").replace("`", "'")
    name = re.sub(r"[,;/]+", " ", name)
    name = re.sub(r"\.", ". ", name)
    out = []
    for p in (q for q in re.split(r"\s+", name.strip()) if q):
        if _HYPH.search(p) and not _art_head(p):
            out.extend(x for x in _HYPH.split(p) if x)
        else:
            out.append(p)
    return out


def strip_article(f: str) -> str:
    """Remove a leading arabic article from a folded token (unconditional)."""
    for p in ARTICLE_PREFIX:
        if f.startswith(p) and len(f) - len(p) >= 3:
            return f[len(p):]
    return f


_ART_MARK = re.compile(r"^(?:[AaEeUu][lLsSdDtTnNrRzZ]?h?)[-'\u2019]")
_ART_CAP = re.compile(r"^(?:Al|El|Ul|As|Ash|Ad|Adh|At|Ath|An|Ar|Az|Es|Ez)"
                      r"(?=[A-Z])")


def strip_article_marked(raw: str, f: str, script: str = "latin") -> str:
    """Strip the arabic article only where the spelling marks it."""
    if script != "latin":
        if f.startswith("al") and len(f) >= 5:
            return f[2:]
        return f
    if _art_head(raw) or _ART_CAP.match(raw):
        return strip_article(f)
    return f


def strip_surname_prefix(f: str) -> str:
    for p in SURNAME_PREFIX:
        if f.startswith(p) and len(f) - len(p) >= 3:
            return f[len(p):]
    return f


def _norm_abd_rest(rest: str) -> str:
    for _ in range(3):
        if ALLAH.match(rest) or rest in ("llah", "lah", "la"):
            return "allah"
        for p in ("ul", "ol", "al", "el", "il", "ur", "ar", "or", "er", "u",
                  "o", "a", "e"):
            if rest.startswith(p) and len(rest) - len(p) >= 3:
                rest = rest[len(p):]
                break
        else:
            break
    return rest


_ABD_TAIL = re.compile(r"^[aeioulr]{0,4}$")


def _unit(parts, i, sc):
    """Read one name unit starting at parts[i]; returns (next_i, raw, fold)."""
    n = len(parts)
    raw = parts[i]
    f = fold(translit(raw)) if sc != "latin" else fold(raw)
    j = i + 1
    if not (f in ABD or (f.startswith("abd") and len(f) >= 4)):
        return j, raw, f
    rest = _norm_abd_rest(f[3:]) if len(f) > 3 else ""
    if ALLAH.match(rest):
        return j, raw, "abdallah"
    if _ABD_TAIL.match(rest):
        # the name part sits in the following token(s)
        rest = ""
        while j < n:
            nxt = parts[j]
            nf = fold(translit(nxt)) if sc != "latin" else fold(nxt)
            j += 1
            if not nf:
                continue
            raw += " " + nxt
            if nf in ("al", "el", "ul", "ol", "il", "as", "ad", "at", "an",
                      "ar", "az", "ash", "a", "e"):
                continue
            rest = strip_article(nf)
            if ALLAH.match(rest) or ALLAH.match(nf):
                rest = "allah"
            break
        if not rest:
            return j, raw, "abd"
    return j, raw, "abd" + rest


class Tok:
    __slots__ = ("raw", "fold", "key", "roots", "script")

    def __init__(self, raw, fold_, key, script="latin"):
        self.raw = raw
        self.fold = fold_
        self.key = key
        self.script = script
        self.roots = None

    def __repr__(self):
        return "<%s %s %s>" % (self.raw, self.key, self.roots)


class PersonName:
    """Parsed personal name: core tokens plus the dropped nasab tokens."""

    def __init__(self, raw: str):
        self.raw = raw
        sc = script_of(raw)
        self.script = sc
        parts = split_tokens(raw)
        core, nasab, patro = [], [], []
        i = 0
        n = len(parts)
        while i < n:
            p = parts[i]
            f = fold(translit(p)) if sc != "latin" else fold(p)
            if not f:
                i += 1
                continue
            low = f
            # initials, courtesy titles and generation suffixes
            if len(low) == 1 and sc == "latin":
                i += 1
                continue
            if sc == "latin" and ((i == 0 and low in TITLES) or
                                  (i == n - 1 and low in SUFFIXES and core)):
                i += 1
                continue
            # nasab marker: drop marker and the father's name
            if low in NASAB and i < n - 1 and (
                    i > 0 or (n >= 3 and low != "ben")):
                j, fa, ff = _unit(parts, i + 1, sc)
                if ff:
                    nasab.append(Tok(fa, ff, pkey(
                        strip_article_marked(fa, ff, sc)), sc))
                i = j
                continue
            # 'abd' compounds
            if low in ABD and i + 1 < n:
                j, raw2, nf = _unit(parts, i, sc)
                if nf:
                    core.append(Tok(raw2, nf, pkey(nf), sc))
                    i = j
                    continue
            if low.startswith("abd") and len(low) > 5:
                rest = _norm_abd_rest(low[3:])
                merged = "abd" + rest
                core.append(Tok(p, merged, pkey(merged), sc))
                i += 1
                continue
            # allah as a separate word attaches to the previous token
            if ALLAH.match(low) and len(low) >= 4 and core:
                prev = core[-1]
                merged = prev.fold + "allah"
                core[-1] = Tok(prev.raw + " " + p, merged, pkey(merged), sc)
                i += 1
                continue
            # particles are dropped (their stem carries the identity)
            if low in PARTICLES and len(low) <= 5 and not (
                    low in NASAB and i == 0):
                i += 1
                continue
            # patronymics are optional on both sides
            if sc in ("latin", "cyr") and len(low) > 6:
                k = pkey(low)
                if (PATRONYMIC.search(low) or PATRONYMIC_KEY.search(k)
                        or PATRONYMIC_KEY2.search(k)):
                    patro.append(Tok(p, low, pkey(low), sc))
                    i += 1
                    continue
            core.append(Tok(p, low, pkey(strip_article_marked(p, low, sc)), sc))
            i += 1
        self.alts = []
        if core and core[0].fold == "ben" and len(core) >= 3:
            self.alts.append(core[2:] if len(core) > 2 else core[1:])
        if len(core) < 2 and patro:
            core.extend(patro[:2 - len(core)])
            patro = patro[2 - len(core):] if len(core) < 2 else []
        self.core = core
        self.nasab = nasab
        self.patro = patro

    def __repr__(self):
        return "PersonName(%r, core=%s)" % (self.raw, self.core)
# --------------------------------------------------------------------------
# 6.  gazetteer of canonical roots
# --------------------------------------------------------------------------

TIE = 0.10
RESOLVE_BASE = 0.60
RESOLVE_PER = 0.110
PAIR_BASE = 0.65
PAIR_PER = 0.110


def thresh(k1, k2, base=RESOLVE_BASE, per=RESOLVE_PER):
    return base + per * min(len(k1), len(k2))


def _ru_masculine(f: str) -> str:
    """Russian feminine surname -> masculine base."""
    for suf, rep in (("skaya", "sky"), ("skaia", "sky"), ("ckaja", "sky"),
                     ("tskaya", "tsky"), ("zkaya", "zky")):
        if f.endswith(suf):
            return f[: -len(suf)] + rep
    for suf in ("ova", "eva", "ina", "yna", "aya"):
        if f.endswith(suf) and len(f) > 5:
            return f[:-1]
    return f


class Gazetteer:
    def __init__(self):
        self.index = {}            # phonetic key -> set(root ids)
        self.root_keys = {}        # root id -> canonical key
        self.root_skel = {}        # root id -> consonant skeleton
        self.by_len = {}           # length -> [(key, root_id)]
        self.all_len = {}
        self.pending = []
        self.groups = {}           # root -> roots that denote the same name
        self.cache = {}

    # -- construction ------------------------------------------------------
    def add_key(self, key, root):
        if not key:
            return
        s = self.index.get(key)
        if s is None:
            self.index[key] = {root}
        else:
            s.add(root)

    def add_root(self, folded, raw=None, script="latin", ru=False):
        """Register a canonical name form; returns its root id."""
        base = _ru_masculine(strip_article_marked(raw if raw is not None
                                                  else folded, folded, script))
        if not base:
            return None
        root = base
        if root not in self.root_keys:
            self.root_keys[root] = pkey(base)
            self.root_skel[root] = skeleton(pkey(base))
            self.pending.append((base, ru))
        self.add_key(pkey(folded), root)
        self.add_key(pkey(base), root)
        return root

    def expand(self):
        """Index the generated spellings of every root registered so far."""
        canon = {}
        for root, key in self.root_keys.items():
            canon.setdefault(key, set()).add(root)
        while self.pending:
            base, ru = self.pending.pop()
            root = base
            variants = gen_variants(base)
            if ru and re.search(r"(ov|ev|in|yn|sky|ski|tsky|enko|ich)$", base):
                for v in list(variants):
                    v2 = re.sub(r"sk(ij|iy|yj|i|y)$", "skaya", v)
                    if v2 != v:
                        variants.add(v2)
                        variants.add(v2[:-2] + "ja")
                    elif v.endswith(("ov", "ev", "in", "yn", "ow", "ew",
                                     "off", "eff", "of", "ef", "iw", "yw")):
                        variants.add(v + "a")
            variants.add(strip_surname_prefix(base))
            for v in variants:
                k = pkey(v)
                owners = canon.get(k)
                if owners and root not in owners:
                    continue           # never shadow another root's own name
                self.add_key(k, root)

    def finish(self):
        self.expand()
        by_len = {}
        for root, key in self.root_keys.items():
            by_len.setdefault(len(key), []).append((key, root))
        self.by_len = by_len
        all_len = {}
        for key, roots in self.index.items():
            all_len.setdefault(len(key), []).append((key, roots))
        self.all_len = all_len

    def fuzzy_any(self, key):
        """Nearest *spelling* in the whole index (fallback)."""
        if not key:
            return None
        best, bestd = None, 9.9
        for ln in range(max(1, len(key) - 3), len(key) + 4):
            for k2, roots in self.all_len.get(ln, ()):
                t = thresh(key, k2) * 0.75
                d = wdist(key, k2, cap=t)
                if d > t:
                    continue
                if d < bestd - 1e-9:
                    bestd, best = d, set(roots)
                elif abs(d - bestd) <= TIE:
                    best |= set(roots)
        return best

    # -- resolution --------------------------------------------------------
    def fuzzy(self, key, extra=0.0):
        """Nearest canonical roots for a phonetic key."""
        if not key:
            return None
        best = None
        bestd = 9.9
        lim = thresh(key, key) + extra
        for ln in range(max(1, len(key) - 4), len(key) + 5):
            for k2, root in self.by_len.get(ln, ()):
                t = min(thresh(key, k2) + extra, lim + 0.5)
                d = wdist(key, k2, cap=t)
                if d > t:
                    continue
                if d < bestd - 1e-9:
                    bestd = d
                    best = {root: d}
                elif best is not None and d <= bestd + TIE:
                    best[root] = d
        if not best:
            return None
        return {r for r, d in best.items() if d <= bestd + TIE}

    def resolve(self, tok):
        k = tok.key
        if k in self.cache:
            tok.roots = self.cache[k]
            return tok.roots
        r = self.index.get(k)
        if r is None:
            k2 = pkey(strip_surname_prefix(tok.fold))
            if k2 != k:
                r = self.index.get(k2)
        if r is None:
            k3 = pkey(strip_article(tok.fold))
            if k3 != k:
                r = self.index.get(k3)
        if r is None and tok.script != "latin":
            r = self._resolve_script(tok)
        if r is None:
            r = self.fuzzy(k)
        if r is None:
            r = self.fuzzy_any(k)
        if r:
            out = set(r)
            for root in r:
                out |= self.groups.get(root, set())
            r = frozenset(out)
        else:
            r = None
        self.cache[k] = r
        tok.roots = r
        return r

    def _resolve_script(self, tok):
        """Original-script token that the watchlist alignment did not cover."""
        keys = script_keys(tok.fold)
        hit = set()
        for k in keys:
            r = self.index.get(k)
            if r:
                hit |= r
        if hit:
            return hit
        best, bestd = None, 9.9
        for k in keys:
            if len(k) < 2:
                continue
            for root, rk in self.root_keys.items():
                if len(rk) - len(k) > 4 or len(k) - len(rk) > 2:
                    continue
                d = sdist(k, rk)
                if d <= 0.62 and d < bestd - 1e-9:
                    bestd, best = d, {root}
                elif best is not None and abs(d - bestd) <= 1e-9:
                    best.add(root)
        return best


def build_gazetteer(entries):
    g = Gazetteer()
    people = [e for e in entries if e.get("type") == "individual"]
    # 1. the canonical pool: tokens of latin primary names
    for e in people:
        pn = e.get("primary_name") or ""
        if script_of(pn) == "latin":
            ru = script_of(e.get("script_name") or "") == "cyr"
            for t in PersonName(pn).core:
                g.add_root(t.fold, t.raw, ru=ru)
    g.finish()
    # 2. entries with no latin primary name: reuse an existing root when the
    #    latin alias is only a spelling variant, else open a new root
    fresh = False
    for e in people:
        pn = e.get("primary_name") or ""
        if script_of(pn) == "latin":
            continue
        for a in e.get("aliases") or ():
            if a.get("strength") != "strong" or script_of(a["name"]) != "latin":
                continue
            for t in PersonName(a["name"]).core:
                k = pkey(_ru_masculine(strip_article_marked(t.raw, t.fold)))
                if k in g.index or t.key in g.index:
                    continue
                r = g.fuzzy(k)
                if r:
                    for root in r:
                        g.add_key(k, root)
                else:
                    g.add_root(t.fold, t.raw,
                               ru=script_of(e.get("script_name") or "") == "cyr")
                    fresh = True
            break
    if fresh:
        g.finish()
    for a, b in CROSS_POOL:
        if a in g.root_keys and b in g.root_keys:
            grp = (g.groups.get(a, set()) | g.groups.get(b, set()) | {a, b})
            for r in grp:
                g.groups[r] = set(grp)
    for canon, forms in LEXICAL.items():
        roots = g.index.get(pkey(canon))
        if roots:
            for r in list(roots):
                for f in forms:
                    for v in gen_variants(f, decorate=False):
                        g.add_key(pkey(v), r)
    for nick, fulls in NICKNAMES.items():
        for full in fulls:
            roots = g.index.get(pkey(full))
            if roots:
                for r in list(roots):
                    for v in gen_variants(nick, decorate=False):
                        g.add_key(pkey(v), r)

    # 3. mine variant spellings: the forms of one entry denote one person
    def align(dst_tokens, src_tokens):
        used = set()
        for dt in dst_tokens:
            if dt.key in g.index:
                continue
            best, bestd = None, 9.9
            for i, st in enumerate(src_tokens):
                if i in used or not g.resolve(st):
                    continue
                if dt.script != "latin" or st.script != "latin":
                    a, b = (dt.key, st.key) if dt.script != "latin" else (st.key, dt.key)
                    d = min(sdist(k, b) for k in script_keys(
                        dt.fold if dt.script != "latin" else st.fold))
                else:
                    d = wdist(dt.key, st.key, cap=3.0)
                if d < bestd:
                    bestd, best = d, i
            if best is not None and bestd <= 2.2:
                used.add(best)
                for r in g.resolve(src_tokens[best]):
                    g.add_key(dt.key, r)
                    if dt.script != "latin":
                        for k in script_keys(dt.fold):
                            g.add_key(k, r)

    for _round in range(2):
        for e in people:
            forms = []
            pn = e.get("primary_name") or ""
            if pn:
                forms.append(PersonName(pn))
            sn = e.get("script_name") or ""
            if sn and sn != pn:
                forms.append(PersonName(sn))
            for a in e.get("aliases") or ():
                if a.get("strength") == "strong":
                    forms.append(PersonName(a["name"]))
            if len(forms) < 2:
                continue
            scored = []
            for f in forms:
                ok = sum(1 for t in f.core if g.resolve(t))
                scored.append((ok - 0.01 * len(f.core), f))
            scored.sort(key=lambda x: -x[0])
            ref = scored[0][1]
            for _, f in scored[1:]:
                align(f.core, ref.core)
                align(ref.core, f.core)
    g.cache.clear()
    return g


# --------------------------------------------------------------------------
# 7.  name comparison
# --------------------------------------------------------------------------

def tok_equiv(a, b):
    if a.key == b.key:
        return True
    ra, rb = a.roots, b.roots
    if ra and rb:
        return bool(ra & rb)
    if a.script != "latin" or b.script != "latin":
        ska, skb = skeleton(a.key), skeleton(b.key)
        return wdist(ska, skb, cap=1.0) <= 0.5
    d = wdist(a.key, b.key, cap=2.0)
    return d <= thresh(a.key, b.key, PAIR_BASE, PAIR_PER)


def _bipartite(a, b):
    """perfect matching between two equal-size token lists"""
    n = len(a)
    if n != len(b):
        return False
    adj = []
    for ta in a:
        row = [j for j, tb in enumerate(b) if tok_equiv(ta, tb)]
        if not row:
            return False
        adj.append(row)
    match = [-1] * n

    def try_k(i, seen):
        for j in adj[i]:
            if j in seen:
                continue
            seen.add(j)
            if match[j] == -1 or try_k(match[j], seen):
                match[j] = i
                return True
        return False

    for i in range(n):
        if not try_k(i, set()):
            return False
    return True


def _merge_forms(toks):
    """token list plus variants where two adjacent tokens are glued together"""
    out = [toks]
    n = len(toks)
    if n >= 2:
        for i in range(n - 1):
            merged = toks[i].fold + toks[i + 1].fold
            t = Tok(toks[i].raw + toks[i + 1].raw, merged, pkey(merged),
                    toks[i].script)
            out.append(toks[:i] + [t] + toks[i + 2:])
    return out


def name_forms(pn):
    forms = [pn.core]
    if pn.nasab:
        forms.append(pn.core + pn.nasab)
    forms.extend(getattr(pn, "alts", ()))
    return forms


def names_equiv(pa, pb, gaz, min_tokens=2):
    fa = name_forms(pa)
    fb = name_forms(pb)
    for a in fa:
        if len(a) < min_tokens:
            continue
        for b in fb:
            if len(b) < min_tokens:
                continue
            if len(a) == len(b):
                if _bipartite(a, b):
                    return True
            elif abs(len(a) - len(b)) == 1:
                if len(a) > len(b):
                    for am in _merge_forms(a)[1:]:
                        for t in am:
                            if t.roots is None:
                                gaz.resolve(t)
                        if _bipartite(am, b):
                            return True
                else:
                    for bm in _merge_forms(b)[1:]:
                        for t in bm:
                            if t.roots is None:
                                gaz.resolve(t)
                        if _bipartite(a, bm):
                            return True
    return False


# --------------------------------------------------------------------------
# 8.  entities and vessels
# --------------------------------------------------------------------------

_CH_ALIAS = {}
for _py, _alts in CHINESE.items():
    for _rank, _a in enumerate(_alts):
        _CH_ALIAS.setdefault(_a, []).append((_rank, _py))
for _a in _CH_ALIAS:
    _CH_ALIAS[_a].sort()

SKIP_WORDS = {"and", "the", "of"}
_ROMAN = {"i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x",
          "one", "two", "three", "four", "five"}
_VPREFIX = re.compile(
    r"^(?:the\s+)?(?:m/v|m/t|m/s|s/s|f/v|mv|mt|ms|ss|fv|rv|"
    r"vessel|motor\s+vessel|motor\s+tanker|tug)\s+", re.I)


def org_words(name, kind, pinyin_stems=frozenset()):
    s = (name or "").lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[.\u2019'`]", "", s)
    s = re.sub(r"[,;\-\u2010\u2011\u2013\u2014/]+", " ", s) if kind == "entity" \
        else re.sub(r"[,;\-\u2010\u2011\u2013\u2014]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if kind == "vessel":
        prev = None
        while prev != s:
            prev = s
            s = _VPREFIX.sub("", s).strip()
        s = s.replace("/", " ")
    elif s.startswith("the "):
        s = s[4:]
    words = []
    for p in s.split():
        f = fold(p)
        if not f:
            continue
        if kind == "entity" and f in LEGAL:
            continue
        if f in SKIP_WORDS:
            continue
        words.append(f)
    return words


def word_variants(w, pinyin_stems):
    """spellings of one organisation word -> {form: penalty}"""
    out = {w: 0}
    a = strip_article(w)
    if a != w:
        out[a] = 0
    if w not in pinyin_stems:
        for i, (rank, py) in enumerate(_CH_ALIAS.get(w, ())):
            out.setdefault(py, 1 + i + rank)
    return out


def org_cost(wa, wb, pinyin_stems):
    """None when the names differ, else a small penalty (0 = identical)."""
    if len(wa) != len(wb):
        return None
    cost = 0
    for x, y in zip(wa, wb):
        if x == y:
            continue
        vx = word_variants(x, pinyin_stems)
        vy = word_variants(y, pinyin_stems)
        common = set(vx) & set(vy)
        if common:
            cost += min(vx[c] + vy[c] for c in common)
            continue
        if min(len(x), len(y)) < 5 or x in _ROMAN or y in _ROMAN:
            return None
        kx, ky = pkey(strip_article(x)), pkey(strip_article(y))
        if kx == ky:
            continue
        if wdist(kx, ky, cap=0.5) <= 0.35:
            cost += 1
            continue
        return None
    return cost


def org_equiv(wa, wb, pinyin_stems):
    return org_cost(wa, wb, pinyin_stems) is not None
# --------------------------------------------------------------------------
# 9.  watchlist model
# --------------------------------------------------------------------------

def norm_id(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def norm_dob(s):
    s = (s or "").strip()
    m = re.match(r"^(\d{4})(?:[-/](\d{1,2}))?(?:[-/](\d{1,2}))?$", s)
    if not m:
        return ""
    y, mo, d = m.group(1), m.group(2), m.group(3)
    out = y
    if mo:
        out += "-%02d" % int(mo)
        if d:
            out += "-%02d" % int(d)
    return out


def dob_compatible(cd, ed):
    """(compatible, corroborated) for customer dob vs entry dob"""
    if not cd or not ed:
        return True, False
    n = min(len(cd), len(ed))
    if n >= 7:
        n = 10 if n >= 10 else 7
    else:
        n = 4
    return cd[:n] == ed[:n], True


class Entry:
    __slots__ = ("uid", "type", "dob", "names", "weak", "ids", "words",
                 "roots", "forms_raw")

    def __init__(self, raw):
        self.uid = raw["uid"]
        self.type = raw.get("type") or "individual"
        self.dob = norm_dob(raw.get("dob"))
        self.ids = set()
        for i in raw.get("ids") or ():
            self.ids.add(((i.get("type") or "").strip().lower(),
                          norm_id(i.get("number"))))
        self.names = []
        self.weak = []
        self.words = []
        self.roots = set()
        self.forms_raw = []
        forms = []
        pn = raw.get("primary_name") or ""
        if pn:
            forms.append(pn)
        sn = raw.get("script_name") or ""
        if sn and sn != pn:
            forms.append(sn)
        strong = [a["name"] for a in (raw.get("aliases") or ())
                  if a.get("strength") == "strong" and a.get("name")]
        weak = [a["name"] for a in (raw.get("aliases") or ())
                if a.get("strength") != "strong" and a.get("name")]
        if self.type == "individual":
            self.names = [PersonName(f) for f in forms + strong]
            self.weak = [PersonName(w) for w in weak]
        else:
            self.forms_raw = forms + strong
            self.weak = [PersonName(w) for w in weak]


class Screener:
    def __init__(self, raw_entries):
        self.entries = [Entry(e) for e in raw_entries]
        self.gaz = build_gazetteer(raw_entries)
        self.id_index = {}
        self.root_index = {}
        self.key_index = {}
        self.pre_index = {}
        self.word_index = {}
        # pinyin stems that the list itself uses
        stems = set()
        for e, raw in zip(self.entries, raw_entries):
            if e.type == "individual":
                continue
            for f in getattr(e, "forms_raw", []):
                for w in org_words(f, e.type):
                    if w in CHINESE:
                        stems.add(w)
        self.pinyin_stems = stems
        self.id_index2 = {}
        for idx, (e, raw) in enumerate(zip(self.entries, raw_entries)):
            for key in e.ids:
                self.id_index.setdefault(key, []).append(idx)
                bare = re.sub(r"^[a-z]+", "", key[1])
                if bare and bare != key[1]:
                    self.id_index2.setdefault((key[0], bare), []).append(idx)
            if e.type == "individual":
                for pn in e.names + e.weak:
                    for t in pn.core + pn.nasab:
                        self.gaz.resolve(t)
                # an alias denotes the same person: prefer the roots that the
                # primary name already uses
                proots = set()
                if e.names:
                    for t in e.names[0].core + e.names[0].nasab:
                        if t.roots:
                            proots |= t.roots
                for pn in e.names[1:]:
                    for t in pn.core + pn.nasab:
                        if t.roots and len(t.roots) > 1:
                            inter = t.roots & proots
                            if inter:
                                t.roots = frozenset(inter)
                for pn in e.names + e.weak:
                    for t in pn.core + pn.nasab:
                        r = t.roots
                        if r:
                            e.roots |= r
                            for rr in r:
                                self.root_index.setdefault(rr, set()).add(idx)
                        self.key_index.setdefault(t.key, set()).add(idx)
            else:
                e.words = [org_words(f, e.type) for f in
                           getattr(e, "forms_raw", [])]
                for pn in e.weak:
                    for t in pn.core:
                        self.key_index.setdefault(t.key, set()).add(idx)
                for ws in e.words:
                    for w in ws:
                        for v in word_variants(w, frozenset()):
                            self.word_index.setdefault(v, set()).add(idx)
                        self.word_index.setdefault(w, set()).add(idx)

    # ----------------------------------------------------------------
    def screen(self, cust):
        ctype = (cust.get("type") or "").strip().lower()
        cdob = norm_dob(cust.get("dob"))
        cid = ((cust.get("id_type") or "").strip().lower(),
               norm_id(cust.get("id_number")))
        name = cust.get("full_name") or ""

        # Rule 1 -- identifiers
        if cid[0] and cid[1]:
            hits = self.id_index.get(cid) or self.id_index2.get(cid)
            if hits:
                return sorted(self.entries[i].uid for i in hits)[0]

        if not name.strip():
            return None

        if ctype == "individual":
            return self._screen_person(name, cdob)
        if ctype in ("entity", "vessel"):
            return self._screen_org(name, ctype)
        # the type column is missing or unknown: try every reading
        return (self._screen_person(name, cdob)
                or self._screen_org(name, "entity")
                or self._screen_org(name, "vessel"))

    # ----------------------------------------------------------------
    def _screen_person(self, name, cdob):
        pn = PersonName(name)
        for t in pn.core + pn.nasab:
            self.gaz.resolve(t)
        cand = set()
        for t in pn.core:
            if t.roots:
                for r in t.roots:
                    cand |= self.root_index.get(r, ())
            else:
                cand |= self.pre_index.get(t.key[:3], set())
            cand |= self.key_index.get(t.key, set())
        strong_hits = []
        weak_hits = []
        for idx in cand:
            e = self.entries[idx]
            if e.type != "individual":
                continue
            ok, corr = dob_compatible(cdob, e.dob)
            matched = False
            for form in e.names:
                if names_equiv(pn, form, self.gaz):
                    matched = True
                    break
            if matched:
                if ok:
                    strong_hits.append((0 if corr else 1, e.uid))
                continue
            if cdob and len(cdob) == 10 and e.dob == cdob:
                for form in e.weak:
                    if names_equiv(pn, form, self.gaz, min_tokens=1):
                        weak_hits.append((0, e.uid))
                        break
        hits = strong_hits or weak_hits
        if not hits:
            return None
        hits.sort()
        return hits[0][1]

    # ----------------------------------------------------------------
    def _screen_org(self, name, ctype):
        words = org_words(name, ctype)
        if not words:
            return None
        cand = set()
        for w in words:
            for v in word_variants(w, self.pinyin_stems):
                cand |= self.word_index.get(v, set())
        hits = []
        for idx in cand:
            e = self.entries[idx]
            if e.type != ctype:
                continue
            best = None
            for ws in e.words:
                c = org_cost(words, ws, self.pinyin_stems)
                if c is not None and (best is None or c < best):
                    best = c
            if best is not None:
                hits.append((best, e.uid))
        if not hits:
            return None
        return sorted(hits)[0][1]


# --------------------------------------------------------------------------
# 10.  command line
# --------------------------------------------------------------------------

def run(watchlist_path, customers_path, out_path):
    with open(watchlist_path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    scr = Screener(raw)
    with open(customers_path, "r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    out = []
    for row in rows:
        try:
            uid = scr.screen(row)
        except Exception:          # a malformed row must not stop the batch
            uid = None
        out.append((row.get("customer_id") or "", "MATCH" if uid else "NO_MATCH",
                    uid or ""))
    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["customer_id", "decision", "matched_uid"])
        for r in out:
            w.writerow(r)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="sanctions screening")
    ap.add_argument("--watchlist", required=True)
    ap.add_argument("--customers", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    run(args.watchlist, args.customers, args.out)


if __name__ == "__main__":
    main()
