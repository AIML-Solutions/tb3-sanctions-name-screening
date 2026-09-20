#!/usr/bin/env python3
"""Sanctions screening engine.

Implements the rules in screening_policy.md: identifier matches, name
equivalence across Arabic / Persian / Cyrillic romanizations, name order,
particles, patronymics and nasab elements, nicknames, strong and weak
aliases, entity legal-form designators, vessel prefixes and date-of-birth
corroboration.

How names are compared
----------------------
Every name token is reduced to a *set* of abstract phoneme strings rather
than to a single code.  Ambiguous graphemes branch: <ch> may be /tS/, /S/,
/x/ or /k/, <c> may be /k/, /ts/, /tS/ or /dZ/ (turkish), <j> may be /dZ/,
/Z/ (french) or a glide (slavic), <s> may be /S/ (turkish s-cedilla or
scientific s-caron with the diacritic dropped), and so on.  Vowels reduce to
three classes with their own spelling variants.  Two tokens correspond when
their key sets intersect, so any pair of conventions that can spell the same
sound meets somewhere in the middle.

Names written in Arabic script carry no short vowels, so an arabic token
yields keys made of consonants and long vowels only, and a latin token
yields a second, "skeleton" key set in which single written vowels may be
dropped.  Latin-vs-latin comparison never uses the skeletons, which keeps
Hasan and Hussein apart.

Standard library only.  Usage:

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
# script detection / folding
# ---------------------------------------------------------------------------

ARABIC_RE = re.compile(
    u'[\u0600-\u06ff\u0750-\u077f\u08a0-\u08ff\ufb50-\ufdff\ufe70-\ufefc]')
CYRILLIC_RE = re.compile(u'[\u0400-\u052f]')

CYR_MAP = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'y0',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    'і': 'i', 'ї': 'yi', 'є': 'ye', 'ґ': 'g', 'ў': 'u', 'ј': 'y', 'ђ': 'dj',
    'ћ': 'ch', 'џ': 'dzh', 'њ': 'n', 'љ': 'l',
}

PRE_FOLD = {
    'ß': 'ss', 'ø': 'o', 'æ': 'ae', 'œ': 'oe', 'đ': 'd', 'ð': 'd',
    'þ': 'th', 'ł': 'l', 'ı': 'i', 'İ': 'i', 'Ø': 'o', 'Æ': 'ae',
    'ẞ': 'ss', 'ĳ': 'ij', 'å': 'a', 'Å': 'a',
}


def cyr_to_latin(s):
    out = []
    for ch in s:
        low = ch.lower()
        if low in CYR_MAP:
            out.append(CYR_MAP[low])
        else:
            out.append(ch)
    return ''.join(out)


def fold(s):
    """Lowercase, expand special letters, strip combining marks."""
    out = []
    for ch in s:
        if ch in PRE_FOLD:
            out.append(PRE_FOLD[ch])
        else:
            out.append(ch)
    s = ''.join(out)
    s = unicodedata.normalize('NFD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return s.lower()


# ---------------------------------------------------------------------------
# latin -> phoneme keys
# ---------------------------------------------------------------------------

VOWEL_LETTERS = set('aeiouy0')

# vowel letter -> possible abstract vowel classes
VCLASS = {
    'a': 'a',
    'e': 'ai',
    'i': 'i',
    'o': 'u',
    'u': 'u',
    'y': 'i',
    '0': 'aiu',   # russian yo / any reduced vowel
}

# two letter vowel graphemes that render a single vowel
VDIGRAPH = {
    'ee': 'ai', 'oo': 'u', 'ou': 'u', 'oe': 'u', 'ue': 'u', 'ae': 'ai',
    'ai': 'ai', 'ay': 'ai', 'ei': 'ai', 'ey': 'ai', 'ie': 'i', 'iy': 'i',
    'yi': 'i', 'yy': 'i', 'aa': 'a', 'ii': 'i', 'uu': 'u', 'eu': 'ui',
    'oy': 'ui', 'oi': 'ui', 'uy': 'ui', 'ui': 'ui', 'eo': 'ai',
}

# vowel runs that may stand for an arabic short vowel (droppable in skeletons)
DROPPABLE = {'ee', 'oo', 'aa', 'ii', 'uu', 'ie', 'eh', 'ou', 'oe', 'ue'}


def _vcollapse(s):
    out = []
    for ch in s:
        if out and out[-1] == ch:
            continue
        out.append(ch)
    return ''.join(out)


_run_cache = {}


def run_alts(run):
    """All vowel-class sequences a written vowel run may stand for."""
    cached = _run_cache.get(run)
    if cached is not None:
        return cached
    if len(run) == 1:
        res = set(VCLASS[run])
        _run_cache[run] = res
        return res
    out = set()
    dig = VDIGRAPH.get(run[:2])
    if dig:
        rest = run[2:]
        if rest:
            for h in dig:
                for r in run_alts(rest):
                    out.add(_vcollapse(h + r))
        else:
            out.update(dig)
    for h in VCLASS[run[0]]:
        rest = run[1:]
        for r in run_alts(rest):
            out.add(_vcollapse(h + r))
    _run_cache[run] = out
    return out


def run_segment(run, initial=False):
    """Alternatives for a vowel run, including glide readings."""
    alts = set(run_alts(run))
    if initial and run[0] == 'e':
        for r in run_alts(run):
            alts.add('Y' + r)
    if len(run) > 1:
        if run[0] in 'yi':
            rest = run_alts(run[1:])
            for r in rest:
                alts.add('Y' + r)
                if run[0] == 'y' or '0' in run:
                    alts.add(r)
        if run[-1] in 'yi':
            for r in run_alts(run[:-1]):
                alts.add(r + 'Y')
        if run[:2] in ('ou', 'uo') and len(run) > 2:
            for r in run_alts(run[2:]):
                alts.add('F' + r)
        if run[0] in 'ou' and len(run) > 1 and run[1] in 'ae':
            for r in run_alts(run[1:]):
                alts.add('F' + r)
    return alts


# multi-character consonant clusters, longest first
CLUSTERS = [
    ('schtsch', ['WC', 'W']),
    ('stsch', ['WC', 'W']),
    ('shch', ['WC', 'W']),
    ('shtch', ['WC', 'W']),
    ('chtch', ['WC', 'W']),
    ('zsch', ['V', 'W']),
    ('zch', ['C', 'W', 'H', 'TS']),
    ('tsch', ['C', 'W', 'H']),
    ('dsch', ['J']),
    ('sch', ['W', 'V', 'SK']),
    ('tch', ['C', 'W', 'H']),
    ('dzh', ['J']),
    ('dzs', ['J']),
    ('ssz', ['W', 'S']),
    ('sh', ['W', 'V']),
    ('zh', ['V']),
    ('sj', ['W', 'SY']),
    ('ch', ['C', 'W', 'H', 'K']),
    ('cz', ['C']),
    ('sz', ['W', 'S']),
    ('dj', ['J']),
    ('tj', ['C', 'T']),
    ('dh', ['D', 'Z']),
    ('dz', ['J', 'DS']),
    ('ck', ['K']),
    ('kh', ['H', 'K']),
    ('gh', ['G', 'K']),
    ('th', ['T', 'S']),
    ('ph', ['F']),
    ('ts', ['TS', 'S']),
    ('tz', ['TS', 'S']),
    ('sjh', ['W']),
    ('stj', ['W', 'SC']),
    ('czh', ['C', 'W', 'H']),
    ('scz', ['W', 'WC']),
    ('szh', ['W', 'V']),
    ('qu', ['K', 'KF']),
    ('ng', ['NG', 'N']),
    ('gn', ['GN', 'N']),
    ('wh', ['F']),
    ('gu', ['G', 'GF']),
    ('dt', ['D', 'T']),
]

# longest cluster first, so that maximal munch applies
CLUSTERS.sort(key=lambda r: -len(r[0]))

SINGLE = {
    'b': ['B'], 'c': ['K', 'TS', 'C', 'J'], 'd': ['D'], 'f': ['F'],
    'g': ['G', 'J', 'H'], 'h': ['H'], 'j': ['J', 'V', 'Y'], 'k': ['K'],
    'l': ['L'], 'm': ['M'], 'n': ['N'], 'p': ['P'], 'q': ['K', 'G'],
    'r': ['R'], 's': ['S', 'W'], 't': ['T'], 'v': ['F'], 'w': ['F'],
    'x': ['KS', 'S', 'H'], 'z': ['Z', 'V', 'TS'],
}

# words in which a written <s> may stand for /z/ (german / slavic usage)
SLAVIC_RE = re.compile(
    r'(?:w|kh|zh|tsch|tch)|'
    r'(?:ov|ev|ow|ew|off|eff|ova|eva|owa|ewa|offa|effa|ski|sky|skaya|'
    r'skaja|ckaya|enko|tsev|tzev|ich|itch|itsch|ij|yj|iy|yi|in|yn|ina|'
    r'yna|eta|ova)$')

MAX_KEYS = 6000


def _collapse_doubles(w):
    out = []
    prev = ''
    for ch in w:
        if ch == prev and ch not in VOWEL_LETTERS:
            continue
        out.append(ch)
        prev = ch
    return ''.join(out)


FINAL_CLUSTER_RE = re.compile(r'^([^aeiouy0]*[aeiouy0]+)([bcdfghjklmnpqrstvwxz])'
                              r'([bcdfghjklmnpqrstvwxz])$')


def _push_cons(segs, alts):
    """Append a consonant segment, merging an immediate repeat (dj-dj)."""
    if segs and segs[-1][0] == 'c' and segs[-1][1] == alts:
        return
    segs.append(('c', alts, False, False))


def _segment(w, western=False):
    """Split a folded latin word into segments.

    Returns a list of (kind, alternatives, droppable) where kind is 'c'
    (consonant) or 'v' (vowel run).
    """
    segs = []
    i = 0
    n = len(w)
    s_as_z = bool(SLAVIC_RE.search(w))
    while i < n:
        ch = w[i]
        if ch in VOWEL_LETTERS:
            j = i
            while j < n and w[j] in VOWEL_LETTERS:
                j += 1
            run = w[i:j]
            drop = (len(run) == 1 or run in DROPPABLE or
                    len(set(run)) == 1)
            # a word-final vowel (optionally before a silent h) renders an
            # arabic ta marbuta / final yeh and is written a / e / i / ah
            final = (not western and w[j:] in ('', 'h')
                     and not (set(run) - set('aeiy')))
            segs.append(('v', sorted(run_segment(run, i == 0)), drop, final))
            i = j
            continue
        matched = False
        for pat, alts in CLUSTERS:
            if w.startswith(pat, i):
                # 'gu' only counts as hard g before a front vowel
                if pat == 'gu' and not (i + 2 < n and w[i + 2] in 'eiy'):
                    continue
                alts = list(alts)
                if pat == 'dt' and i + 2 != n:
                    continue
                _push_cons(segs, alts)
                i += len(pat)
                matched = True
                break
        if matched:
            continue
        if ch in SINGLE:
            alts = list(SINGLE[ch])
            if ch == 'c' and i + 1 < n and w[i + 1] in 'eiy':
                alts = alts + ['S']
            if ch == 'j':
                if i + 1 < n and w[i + 1] == '0':
                    alts = alts + ['']
                elif i > 0 and w[i - 1] in VOWEL_LETTERS:
                    alts = alts + ['']
                elif i == n - 1:
                    alts = alts + ['', 'i']
                elif i > 0 and w[i - 1] not in VOWEL_LETTERS and \
                        w[i + 1] not in VOWEL_LETTERS:
                    alts = alts + ['i']
            elif ch == 'h' and i == n - 1:
                alts = alts + ['']
            elif ch == 's' and s_as_z:
                alts = alts + ['Z']
            elif ch == 'z' and i == n - 1:
                alts = alts + ['S']
            elif ch == 'd' and i == n - 1:
                alts = alts + ['T']
            elif ch == 't' and i == n - 1:
                alts = alts + ['D']
            elif ch == 'b' and i == n - 1:
                alts = alts + ['P']
            elif ch == 'p' and i == n - 1:
                alts = alts + ['B']
            _push_cons(segs, alts)
        i += 1
    return segs


def _expand(segs, skeleton):
    """Cross-product the segment alternatives into key strings."""
    results = ['']
    for kind, alts, drop, final in segs:
        if kind == 'v':
            alts = set(alts)
            if final:
                alts.update(('a', 'i'))
            if skeleton:
                opts = set()
                for a in alts:
                    for v in _vowel_subsets(a.upper()):
                        if v:
                            opts.add(v)
                if drop:
                    opts.add('')
            else:
                opts = set(alts)
        else:
            opts = set(alts)
        new = []
        for r in results:
            for o in opts:
                new.append(r + o)
        results = list(set(new))
        if len(results) > MAX_KEYS:        # deterministic truncation
            results = sorted(results)[:MAX_KEYS]
    return set(_dedup(r) for r in results)


def _vowel_subsets(a):
    """Variants of a vowel-run reading with elidable vowels removed.

    A written vowel only disappears when it sits next to a glide (the short
    vowel an arabic script does not write); a plain vowel sequence has to be
    realised."""
    if 'Y' not in a and 'F' not in a:
        return {a}
    out = ['']
    for ch in a:
        if ch in 'AIU':
            out = [x + ch for x in out] + out
        else:
            out = [x + ch for x in out]
    return set(out)


# only identical *vowels* may merge (an elided consonant can leave two)
_DUP_RE = re.compile(r'([aiuAIU])\1+')


def _dedup(s):
    return _DUP_RE.sub(r'\1', s)


# arabic definite article: al-/el-/ul- or a sun-letter assimilated form,
# which always shows the doubled consonant (as-sabah -> assabah)
ARTICLE_RE = re.compile(
    r'^(?:[aeiou](?:sh|sch|ch)(?=sh|sch|ch)|[aeiou](l|d|n|r|s|t|z)(?=\1)|'
    r'a-?l|e-?l|u-?l|i-?l|o-?l)[- ]?')


PARTPREFIX_RE = re.compile(
    r'^(?:vander|vanden|vonder|van|von|della|del|des|de|da|du|di|le|la|'
    r'der|den|dos|das|ter)')


GUARD_EXTRA = {
    'elizaveta', 'yelizaveta', 'elisaweta', 'oleg', 'olga', 'ilya', 'ulyana',
    'alexandrovich', 'aleksandrovich', 'alexeevich', 'alekseevich',
    'olesya', 'elvira', 'albina', 'alina', 'alma', 'ildar', 'ulugbek',
    'elena', 'yelena', 'jelena', 'elisabeth', 'elizabeth', 'ekaterina',
    'olsen', 'olson', 'olsson', 'alexey', 'alexei', 'aleksei', 'aleksey',
    'alexander', 'aleksandr', 'alexandr', 'alexandra', 'aleksandra',
    'ulrich', 'alberto', 'alfred', 'elliot', 'ilyas', 'elias',
}


def _word_forms(w):
    """String level spelling variants of one latin word."""
    stack = [w]
    seen = set()
    while stack:
        x = stack.pop()
        if x in seen or not x:
            continue
        seen.add(x)
        if len(x) > 4 and x[-1] == 'h':          # silent final h
            stack.append(x[:-1])
        if len(x) > 4 and x[-1] == 'e':          # decorative final e
            stack.append(x[:-1])
        if len(x) > 3 and x[0] in 'aeiou' and x[1] in 'aeiou':
            stack.append(x[1:])
        if len(x) > 5 and x[0] == 'm' and x[2] == 'c' and \
                x[1] in 'aeiou':                 # MacDonald / McDonald
            stack.append('mc' + x[3:])
        if x.endswith('son') and len(x) > 4:     # Andersson / Andersen
            stack.append(x[:-3] + 'sen')
        if x.endswith('sohn') and len(x) > 5:
            stack.append(x[:-4] + 'sen')
        if len(x) <= 5:                          # Fahd / Fahad, Bakr / Baker
            m3 = FINAL_CLUSTER_RE.match(x)
            if m3:
                for v in 'eaiu':
                    stack.append(m3.group(1) + m3.group(2) + v + m3.group(3))
        if x in NICK or x in GUARD_EXTRA:
            # a known western given name is never an article + stem
            continue
        m = ARTICLE_RE.match(x)                  # al- / el- / assimilated
        if m:
            rest = x[m.end():]
            if len(rest) >= (4 if rest[:1] in 'aeiouy' else 3):
                stack.append(rest)
        m2 = PARTPREFIX_RE.match(x)              # van der / de la / du ...
        if m2 and len(x) - m2.end() >= 4:
            rest = x[m2.end():]
            if rest[0] not in 'aeiouy0' and any(c in 'aeiouy0' for c in rest):
                stack.append(rest)
    return set(_collapse_doubles(f) for f in seen)


_latin_cache = {}


def latin_keys(word):
    """Return (full_keys, skeleton_keys) for one latin word."""
    if word in _latin_cache:
        return _latin_cache[word]
    w = fold(word)
    w = re.sub(r"[^a-z0-9]", '', w)
    # mark russian yo
    w = re.sub(r'(?<=..)(?<=[yij])o(?=[bcdfghjklmnpqrstvwxz])', '0', w)
    if not w:
        res = (frozenset(), frozenset())
        _latin_cache[word] = res
        return res
    full = set()
    skel = set()
    western = w in NICK or w in GUARD_EXTRA
    for form in _word_forms(w):
        segs = _segment(form, western)
        if not segs:
            continue
        full |= _expand(segs, False)
        skel |= _expand(segs, True)
    res = (frozenset(full), frozenset(skel))
    _latin_cache[word] = res
    return res


# ---------------------------------------------------------------------------
# arabic / persian -> phoneme keys
# ---------------------------------------------------------------------------

# consonant map -> list of alternatives
AR_CONS = {
    'ب': ['B'],                    # beh
    'پ': ['P'],                    # peh
    'ت': ['T'],                    # teh
    'ث': ['T', 'S'],               # theh
    'ج': ['J'],                    # jeem
    'چ': ['C'],                    # cheh
    'ح': ['H'],                    # hah
    'خ': ['H'],                    # khah
    'د': ['D'],                    # dal
    'ذ': ['Z', 'D'],               # thal
    'ر': ['R'],                    # reh
    'ز': ['Z'],                    # zain
    'ژ': ['V'],                    # jeh (zh)
    'س': ['S'],                    # seen
    'ش': ['W'],                    # sheen
    'ص': ['S'],                    # sad
    'ض': ['D', 'Z'],               # dad
    'ط': ['T'],                    # tah
    'ظ': ['Z', 'T'],               # zah
    'ع': [''],                     # ain
    'غ': ['G', 'K'],               # ghain
    'ف': ['F'],                    # feh
    'ق': ['K', 'G'],               # qaf
    'ك': ['K'],                    # kaf
    'ک': ['K'],                    # keheh
    'گ': ['G'],                    # gaf
    'ل': ['L'],                    # lam
    'م': ['M'],                    # meem
    'ن': ['N'],                    # noon
    'ه': ['H'],                    # heh
    'ھ': ['H'],
    'ء': [''],                     # hamza
    'ؤ': ['', 'F'],                # waw with hamza
    'ئ': ['', 'Y'],                # yeh with hamza
}

AR_LONG = {
    'ا': ['A'],                    # alef
    'آ': ['A'],                    # alef madda
    'أ': ['A', 'I'],               # alef hamza above
    'إ': ['I', 'A'],               # alef hamza below
    'و': ['U', 'F'],               # waw
    'ي': ['I', 'Y'],               # yeh
    'ی': ['I', 'Y'],               # farsi yeh
    'ى': ['A', 'I'],               # alef maksura
    'ے': ['I', 'Y'],               # yeh barree
}

AR_TAMARBUTA = 'ة'
AR_DIACRITICS = set('ًٌٍَُِّْٓ'
                    'ٕٔـٰ')

_arabic_cache = {}


def arabic_keys(word):
    """Return the set of consonant+long-vowel skeleton keys for an arabic word."""
    if word in _arabic_cache:
        return _arabic_cache[word]
    w = ''.join(ch for ch in word if ch not in AR_DIACRITICS)
    w = w.replace('ٱ', 'ا')
    forms = [w]
    # definite article
    if w.startswith('ال') and len(w) > 3:
        forms.append(w[2:])
    out = set()
    for form in forms:
        results = ['']
        prev = ''
        for idx, ch in enumerate(form):
            if ch == prev and ch in AR_CONS:
                continue
            prev = ch
            if ch in AR_CONS:
                alts = list(AR_CONS[ch])
                if idx == len(form) - 1:
                    if ch in ('ه', 'ھ'):
                        alts = alts + ['', 'A', 'I']
                    elif ch in ('ح', 'خ'):
                        alts = alts + ['']
            elif ch in AR_LONG:
                alts = list(AR_LONG[ch])
                if idx == 0:
                    alts = list(set(alts) | {'A', 'I'})
            elif ch == AR_TAMARBUTA:
                alts = ['', 'A', 'I']
            else:
                continue
            new = []
            for r in results:
                for a in alts:
                    new.append(r + a)
            results = list(set(new))
            if len(results) > MAX_KEYS:
                results = sorted(results)[:MAX_KEYS]
        out |= set(_dedup(r) for r in results)
    res = frozenset(out)
    _arabic_cache[word] = res
    return res


# ---------------------------------------------------------------------------
# token objects
# ---------------------------------------------------------------------------

class Tok(object):
    __slots__ = ('raw', 'arabic', 'lk', 'sk', 'lat')

    def __init__(self, raw):
        self.raw = raw
        if ARABIC_RE.search(raw):
            self.arabic = True
            self.lk = frozenset()
            self.sk = arabic_keys(raw)
            self.lat = ''
        else:
            self.arabic = False
            src = cyr_to_latin(raw) if CYRILLIC_RE.search(raw) else raw
            self.lat = re.sub(r'[^a-z0-9]', '', fold(src))
            self.lk, self.sk = latin_keys(src)


_tok_cache = {}


def get_tok(raw):
    t = _tok_cache.get(raw)
    if t is None:
        t = Tok(raw)
        _tok_cache[raw] = t
    return t


def _pairs(xs, ys):
    cnt = 0
    if len(xs) * len(ys) > MAX_KEYS:       # deterministic truncation
        xs, ys = sorted(xs), sorted(ys)
    for x in xs:
        for y in ys:
            yield x, y
            cnt += 1
            if cnt > MAX_KEYS:
                return


def _seam(x, y):
    if x and y and x[-1] == y[0]:
        return x + y[1:]
    return x + y


def get_multi_tok(raws):
    """A token that may be read several ways (all key sets unioned)."""
    raws = tuple(dict.fromkeys(raws))
    key = '|'.join(raws)
    t = _tok_cache.get(key)
    if t is not None:
        return t
    parts = [get_tok(r) for r in raws]
    t = Tok.__new__(Tok)
    t.raw = raws[0]
    t.arabic = any(p.arabic for p in parts)
    t.lat = parts[0].lat
    t.lk = frozenset().union(*[p.lk for p in parts])
    t.sk = frozenset().union(*[p.sk for p in parts])
    _tok_cache[key] = t
    return t


def join_toks(a, b):
    """Concatenated token (compound surname)."""
    raw = a.raw + '§' + b.raw
    t = _tok_cache.get(raw)
    if t is not None:
        return t
    t = Tok.__new__(Tok)
    t.raw = raw
    t.arabic = a.arabic or b.arabic
    t.lat = a.lat + b.lat
    t.lk = frozenset(_seam(x, y) for x, y in _pairs(a.lk, b.lk))
    t.sk = frozenset(_seam(x, y) for x, y in _pairs(a.sk, b.sk))
    _tok_cache[raw] = t
    return t


def tok_match(a, b):
    if a is b:
        return True
    if a.arabic or b.arabic:
        return not a.sk.isdisjoint(b.sk)
    return not a.lk.isdisjoint(b.lk)


# ---------------------------------------------------------------------------
# nicknames / given-name equivalences
# ---------------------------------------------------------------------------

NICK_GROUPS = [
    # english hypocorisms
    ['william', 'bill', 'billy', 'will', 'willie', 'liam', 'willy'],
    ['robert', 'bob', 'bobby', 'rob', 'robbie'],
    ['richard', 'dick', 'rick', 'ricky', 'rich', 'richie', 'dicky'],
    ['james', 'jim', 'jimmy', 'jamie', 'jimmie', 'jaime'],
    ['john', 'johnny', 'jack', 'jon', 'johnnie', 'jonathan'],
    ['michael', 'mike', 'mikey', 'mick', 'micky', 'mickey'],
    ['thomas', 'tom', 'tommy'],
    ['charles', 'chuck', 'charlie', 'chas', 'charley'],
    ['joseph', 'joe', 'joey'],
    ['christopher', 'chris', 'kit'],
    ['daniel', 'dan', 'danny', 'dannie'],
    ['matthew', 'matt', 'matty'],
    ['anthony', 'tony'],
    ['donald', 'don', 'donnie', 'donny'],
    ['edward', 'ed', 'eddie', 'eddy', 'ted', 'teddy'],
    ['theodore', 'theo', 'ted', 'teddy'],
    ['frederick', 'fred', 'freddie', 'freddy', 'frederic'],
    ['andrew', 'andy', 'drew', 'andres'],
    ['alexander', 'alex', 'xander', 'aleksandr', 'sasha', 'alexandr',
     'alejandro', 'alessandro'],
    ['alexandra', 'aleksandra'],
    ['nicholas', 'nick', 'nicky', 'nicolas', 'nikolaus'],
    ['benjamin', 'ben', 'benny', 'benji', 'bennie'],
    ['samuel', 'sam', 'sammy'],
    ['steven', 'steve', 'stephen', 'stevie'],
    ['peter', 'pete', 'pedro', 'pierre', 'petr', 'pyotr', 'piotr'],
    ['henry', 'hank', 'harry', 'hal', 'enrique', 'heinrich'],
    ['kenneth', 'ken', 'kenny'],
    ['timothy', 'tim', 'timmy'],
    ['gregory', 'greg', 'gregg'],
    ['francisco', 'frank', 'fran', 'paco', 'pancho', 'frankie', 'francis'],
    ['jose', 'pepe'],
    ['eugene', 'yevgeny', 'evgeny', 'evgeni', 'yevgeni', 'eugen'],
    ['elizabeth', 'liz', 'beth', 'betty', 'lizzie', 'eliza', 'libby',
     'elisabeth', 'bettie'],
    ['katherine', 'kate', 'katie', 'kathy', 'cathy', 'kat', 'katy',
     'kitty', 'catherine', 'kathryn', 'katharine'],
    ['margaret', 'maggie', 'meg', 'peggy', 'marge', 'margie'],
    ['rebecca', 'becca', 'becky', 'becki'],
    ['susan', 'sue', 'suzy', 'susie', 'suzie', 'susanna'],
    ['patricia', 'pat', 'patty', 'trish', 'tricia', 'patti'],
    ['dorothy', 'dot', 'dottie'],
    ['jennifer', 'jen', 'jenny', 'jenn', 'jennie'],
    ['victoria', 'vicky', 'vicki', 'vickie', 'tori', 'viktoria',
     'viktoriya'],
    ['barbara', 'barb', 'babs', 'barbie'],
    ['deborah', 'deb', 'debbie', 'debra'],
    ['pamela', 'pam'],
    ['cynthia', 'cindy'],
    ['christine', 'chrissy', 'christina', 'christa'],
    ['stephanie'],
    ['abigail', 'abby'],
    # russian hypocorisms that this list uses as aliases
    ['dmitri', 'dima', 'dmitry', 'dmitriy'],
    ['nikolai', 'kolya', 'nikolay'],
    ['anatoly', 'tolya', 'anatoli'],
    ['vladimir', 'vova'],
    # cross-language equivalents
    ['charles', 'carlos', 'karl', 'carl'],
    ['george', 'jorge', 'georgy', 'georg'],
    ['william', 'guillermo', 'wilhelm'],
    ['anthony', 'antonio', 'anton'],
    ['edward', 'eduardo', 'eduard'],
    ['richard', 'ricardo'],
    ['robert', 'roberto'],
    ['philip', 'felipe', 'phillip'],
    ['paul', 'pablo', 'pavel'],
    ['thomas', 'tomas'],
    ['maria', 'mariya', 'marya'],
    ['helen', 'helena'],
]

SURNAME_GROUPS = [
    ['pedersen', 'petersen', 'peterson', 'pederson', 'pettersen',
     'pettersson', 'petersson', 'pedersson'],
]
SURNAME_EQUIV = defaultdict(set)
for _grp in SURNAME_GROUPS:
    for _a in _grp:
        SURNAME_EQUIV[_a].update(_grp)

NICK = defaultdict(set)
for _grp in NICK_GROUPS:
    for _a in _grp:
        NICK[_a].update(_grp)


# ---------------------------------------------------------------------------
# name parsing
# ---------------------------------------------------------------------------

PARTICLES = {
    'al', 'el', 'ul', 'il', 'ol',
    'la', 'le', 'de', 'del', 'della', 'da', 'dos', 'das', 'du', 'van',
    'von', 'der', 'den', 'ter', 'te', 'di', 'do', 'lo', 'abu', 'umm',
    'ould', 'ait', 'ap', 'mac', 'mc', 'saint', 'st', 'the',
}
# sun-letter assimilated forms of the arabic article; only an article when
# the following word starts with the same consonant (as-Sabah, an-Najjar)
ASSIM = {
    'ad': 'd', 'an': 'n', 'ar': 'r', 'as': 's', 'at': 't', 'az': 'z',
    'ash': 'sh', 'asch': 'sch', 'ach': 'ch', 'ath': 'th', 'adh': 'dh',
    'ed': 'd', 'en': 'n', 'er': 'r', 'es': 's', 'et': 't', 'ez': 'z',
    'esh': 'sh', 'esch': 'sch', 'ech': 'ch',
}
NASAB_RE = re.compile(r'^(?:b|b[aeiou]n+|ib[aeiou]?n+|bint|bint[ei]|'
                      r'veled|walad)e?$')
NASAB = {'بن', 'ابن', 'بنت'}
_NASAB_TOKS = None


def is_nasab(t):
    global _NASAB_TOKS
    if t in NASAB or NASAB_RE.match(t):
        return True
    if len(t) > 5 or ARABIC_RE.search(t):
        return False
    if _NASAB_TOKS is None:
        _NASAB_TOKS = [get_tok(x) for x in ('bin', 'ibn', 'bint')]
    tk = get_tok(t)
    return any(tok_match(tk, u) for u in _NASAB_TOKS)


DROP_TOKENS = {'jr', 'sr', 'ii', 'iii', 'iv', 'mr', 'mrs', 'ms', 'dr',
               'prof', 'sheikh', 'hajji', 'haji'}

ABD_RE = re.compile(r'^[ae]+bd')
# "abd" plus at most a linking vowel and the article: a bare prefix that
# belongs with the *next* token (Abd al-Aziz, Abdul Aziz, Abdoel Aziz)
ABD_PREFIX_RE = re.compile(r'^[ae]+bd[aeiou]*[lr]?$')
AR_ABD = {'عبد'}
ALLAH = {'allah', 'alah', 'ullah', 'ulah', 'ollah', 'olah', 'lah',
         'illah', 'ilah', 'الله'}


def split_tokens(name):
    s = name.replace('\u2019', "'").replace('\u02bc', "'")
    s = re.sub(r"[.;/\\()\[\]\"]", ' ', s)
    s = s.replace('-', ' ').replace('_', ' ')
    s = re.sub(r"'", '', s)
    parts = [p for p in s.split(',')]
    if len(parts) > 1 and any(p.strip() for p in parts[1:]):
        # "Family, Given" -> put the given part first
        s = ' '.join(parts[1:]) + ' ' + parts[0]
    else:
        s = ' '.join(parts)
    toks = [t for t in s.split() if t]
    k = len(toks)
    while k > 1 and fold(toks[k - 1]) in PARTICLES:
        k -= 1
    if 0 < k < len(toks):
        toks = toks[k:] + toks[:k]
    return toks


class ParsedName(object):
    __slots__ = ('core', 'pairs')

    def __init__(self, core):
        self.core = core
        self.pairs = build_pairs(core)


def build_pairs(core):
    n = len(core)
    pairs = []
    if n < 2:
        return pairs
    if n == 2:
        pairs.append((core[0], core[1]))
        pairs.append((core[1], core[0]))
        return pairs
    a, z = core[0], core[-1]
    pairs.append((a, z))
    pairs.append((z, a))
    j_last = join_toks(core[-2], core[-1])
    pairs.append((a, j_last))
    pairs.append((j_last, a))
    j_first = join_toks(core[0], core[1])
    pairs.append((j_first, z))
    pairs.append((z, j_first))
    if n == 3:
        pairs.append((core[1], join_toks(core[0], core[2])))
        pairs.append((core[1], join_toks(core[2], core[0])))
    return pairs


# russian patronymics: <vowel> v/w <vowel> + ich / itch / na ...
PATRONYMIC_RE = re.compile(
    r'[aeiouy]{1,3}[vw]{1,2}[aeiouy]{0,3}'
    r'(?:tsch|itsch|tch|ch|sch|cz|tz|c|z|nn?[aeiouy])[aeh]*$')


def _skippable_article(folded, j, n):
    t = folded[j]
    if isinstance(t, tuple) or _is_script(t):
        return False
    if t in PARTICLES or len(t) == 1:
        return True
    if t in ASSIM and j + 1 < n and not isinstance(folded[j + 1], tuple) \
            and not _is_script(folded[j + 1]) \
            and folded[j + 1].startswith(ASSIM[t]):
        return True
    return False


def is_patronymic(folded):
    return bool(PATRONYMIC_RE.search(folded)) and len(folded) > 6


def _is_script(t):
    return bool(ARABIC_RE.search(t))


def parse_name(name, kind='individual'):
    toks = split_tokens(name)
    if not toks:
        return ParsedName([])
    folded = []
    for t in toks:
        if _is_script(t):
            folded.append(t)
        elif CYRILLIC_RE.search(t):
            folded.append(fold(cyr_to_latin(t)))
        else:
            folded.append(fold(t))
    core = []
    i = 0
    n = len(folded)
    while i < n:
        low = folded[i]
        if isinstance(low, tuple):
            core.append(low)
            i += 1
            continue
        script = _is_script(low)
        if low in DROP_TOKENS:
            i += 1
            continue
        # arabic / western nasab: bin <father>
        if is_nasab(low) and i + 1 < n:
            remaining = n - (i + 2)
            if i > 0 and len(core) + remaining >= 2:
                j = i + 2
                # father may be an abd- compound: bin abd al-aziz
                fn = folded[i + 1]
                if (fn in AR_ABD or
                        (not _is_script(fn) and ABD_PREFIX_RE.match(fn))):
                    while j + 1 < n and _skippable_article(folded, j, n):
                        j += 1
                    if j < n and len(core) + (n - (j + 1)) >= 2:
                        j += 1
                i = j
                continue
        if len(low) == 1 and not script:
            if low in ('o', 'd', 'l') and i + 1 < n and \
                    not _is_script(folded[i + 1]) and \
                    folded[i + 1] not in PARTICLES:
                folded[i + 1] = (low + folded[i + 1], folded[i + 1])
            i += 1
            continue
        if low in ASSIM and i + 1 < n and not _is_script(folded[i + 1]) and \
                not isinstance(folded[i + 1], tuple) and \
                folded[i + 1].startswith(ASSIM[low]):
            folded[i + 1] = low + folded[i + 1]
            i += 1
            continue
        if low in PARTICLES and i + 1 < n:
            # articles and nobiliary particles attach to the following word
            j = i
            pref = ''
            while j < n - 1 and not isinstance(folded[j], tuple) and \
                    folded[j] in PARTICLES and not _is_script(folded[j]):
                pref += folded[j]
                j += 1
            if isinstance(folded[j], tuple):
                folded[j] = tuple(pref + x for x in folded[j]) + folded[j]
            elif not _is_script(folded[j]):
                folded[j] = pref + folded[j]
            i = j
            continue
        if not script and is_patronymic(low):
            remaining = n - (i + 1)
            if len(core) + remaining >= 2:
                i += 1
                continue
        # abd- compounds
        if low in AR_ABD and i + 1 < n:
            j = i + 1
            while j + 1 < n and _skippable_article(folded, j, n):
                j += 1
            core.append(('abd', folded[j]))
            i = j + 1
            continue
        if not script and ABD_RE.match(low):
            if ABD_PREFIX_RE.match(low.rstrip('he')) and i + 1 < n:
                j = i + 1
                while j + 1 < n and _skippable_article(folded, j, n):
                    j += 1
                nxt = folded[j]
                if isinstance(nxt, tuple):
                    nxt = nxt[0]
                core.append(('abd', nxt))
                i = j + 1
                continue
            low = _collapse_doubles(low)
            if len(low) > 5:
                rest = low[low.index('bd') + 2:]
                if len(rest) >= 3:
                    core.append(('abd', rest))
                    i += 1
                    continue
        core.append(low)
        i += 1
    merged = []
    for c in core:
        if merged and not isinstance(c, tuple) and c in ALLAH and \
                not isinstance(merged[-1], tuple):
            merged[-1] = merged[-1] + c
            continue
        merged.append(c)
    core = merged
    out = []
    for c in core:
        if isinstance(c, tuple):
            if len(c) == 2 and c[0] == 'abd':
                out.append(join_toks(get_tok('abd'), get_tok(c[1])))
            else:
                out.append(get_multi_tok(c))
        else:
            out.append(get_tok(c))
    return ParsedName(out)


def given_tok_set(tok):
    """Expand nicknames for a given-name token."""
    base = tok.raw
    alts = NICK.get(base)
    if not alts:
        return [tok]
    return [tok] + [get_tok(a) for a in alts if a != base]


FEM_SUFFIX = [
    ('ova', 'ov'), ('eva', 'ev'), ('yova', 'yov'), ('iova', 'iov'),
    ('owa', 'ow'), ('ewa', 'ew'), ('ffa', 'ff'), ('offa', 'off'),
    ('ina', 'in'), ('yna', 'yn'), ('skaya', 'ski'), ('tskaya', 'tski'),
    ('skaja', 'ski'), ('ckaja', 'cki'), ('skaia', 'ski'), ('ckaia', 'cki'),
    ('aya', 'y'), ('aja', 'y'), ('aia', 'y'), ('cka', 'cki'),
    ('ska', 'ski'), ('a', ''),
]


def family_tok_set(tok):
    """Russian/Slavic feminine surname forms map to the masculine stem."""
    if tok.arabic:
        return [tok]
    raw = tok.lat
    outs = [tok]
    for alt in SURNAME_EQUIV.get(raw, ()):
        if alt != raw:
            outs.append(get_tok(alt))
    for suf, rep in FEM_SUFFIX:
        if raw.endswith(suf) and len(raw) - len(suf) >= 3:
            if suf == 'a' and not re.search(
                    r'(ov|ev|in|yn|ow|ew|ff|sk|tsk|zk|ck)a$', raw):
                continue
            outs.append(get_tok(raw[:len(raw) - len(suf)] + rep))
            break
    return outs


# ---------------------------------------------------------------------------
# entity / vessel names
# ---------------------------------------------------------------------------

LEGAL_PHRASES = [
    'public joint stock company', 'joint stock company',
    'limited liability company', 'free zone establishment',
    'free zone company', 'sociedad anonima', 'open joint stock company',
    'closed joint stock company', 'private joint stock company',
    'public limited company', 'and company', 'sp z o o', 'sp zoo', 'sp z oo',
    'gmbh und co kg', 'gmbh and co kg', 's de rl', 'sa de cv',
    'limited liability partnership', 'general trading',
]
LEGAL_TOKENS = {
    'llc', 'lllc', 'ltd', 'limited', 'sa', 'gmbh', 'jsc', 'ao', 'oao',
    'zao', 'pjsc', 'ojsc', 'co', 'company', 'corp', 'corporation', 'inc',
    'incorporated', 'fze', 'fzllc', 'fzco', 'fz', 'plc', 'ag', 'nv', 'bv',
    'srl', 'spa', 'pte', 'pvt', 'llp', 'lp', 'kg', 'ohg', 'oy', 'ab',
    'as', 'sarl', 'sas', 'sl', 'kft', 'doo', 'dd', 'joint', 'stock',
    'liability', 'establishment', 'sociedad', 'anonima', 'zone',
    'ooo', 'cjsc', 'sdn', 'bhd', 'pt', 'tbk', 'cv', 'pty', 'ltda', 'lda',
    'aps', 'asa', 'snc', 'sca', 'eurl', 'slu', 'sau', 'oyj', 'spzoo',
    'incorporation', 'limitada',
    'the', 'and', 'of', '公司',
}

# ordinal suffixes are written as roman numerals, words or digits
NUMWORD = {
    'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5', 'vi': '6',
    'vii': '7', 'viii': '8', 'ix': '9', 'x': '10', 'xi': '11', 'xii': '12',
    'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5',
    'six': '6', 'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10',
    'first': '1', 'second': '2', 'third': '3', 'fourth': '4', 'fifth': '5',
    '1': '1', '2': '2', '3': '3', '4': '4', '5': '5', '6': '6', '7': '7',
    '8': '8', '9': '9', '10': '10',
}
VESSEL_PREFIX = {'mv', 'mt', 'ms', 'ss', 'mts', 'mtv', 'vessel', 'motor',
                 'tanker', 'the', 'm', 'v', 't', 's', 'fv', 'lng', 'lpg',
                 'msv', 'osv', 'sv', 'mss'}

ENT_EQUIV = {
    'bosporus': 'bosphorus',
}


def norm_org(name, vessel=False):
    s = fold(name)
    s = s.replace('&', ' and ')
    s = re.sub(r'\.(?=\s|$)', '', s)
    s = s.replace('.', '')
    s = re.sub(r'[^a-z0-9؀-ۿЀ-ӿ]+', ' ', s)
    s = ' ' + ' '.join(s.split()) + ' '
    for ph in LEGAL_PHRASES:
        s = s.replace(' ' + ph + ' ', ' ')
    toks = s.split()
    out = []
    for t in toks:
        if t in LEGAL_TOKENS:
            continue
        if vessel and not out and t in VESSEL_PREFIX:
            continue
        out.append(ENT_EQUIV.get(t, t))
    if vessel:
        while out and out[0] in VESSEL_PREFIX:
            out.pop(0)
    if len(out) > 1 and out[-1] in NUMWORD:
        out[-1] = NUMWORD[out[-1]]
    return tuple(out)


# ---------------------------------------------------------------------------
# dates
# ---------------------------------------------------------------------------

def dob_parts(d):
    if not d:
        return None
    d = d.strip()
    m = re.match(r'^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?$', d)
    if not m:
        return None
    parts = [m.group(1)]
    if m.group(2):
        parts.append('%02d' % int(m.group(2)))
    if m.group(3):
        parts.append('%02d' % int(m.group(3)))
    return parts


def dob_check(cust, entry):
    """Returns (compatible, corroborated)."""
    a = dob_parts(cust)
    b = dob_parts(entry)
    if a is None or b is None:
        return True, False
    n = min(len(a), len(b))
    if a[:n] == b[:n]:
        return True, True
    return False, False


# ---------------------------------------------------------------------------
# watchlist index
# ---------------------------------------------------------------------------

class EntryName(object):
    __slots__ = ('uid', 'parsed', 'raw', 'arabic')

    def __init__(self, uid, raw, parsed):
        self.uid = uid
        self.raw = raw
        self.parsed = parsed
        self.arabic = bool(ARABIC_RE.search(raw))


class Engine(object):
    def __init__(self, entries):
        self.entries = {}
        self.by_id = {}
        self.person_names = []
        self.tok_index = defaultdict(set)   # key -> set(name idx)
        self.org_index = defaultdict(set)   # word tuple -> set(uid)
        self.weak_index = defaultdict(list)
        self.has_latin = {}
        for e in entries:
            uid = e['uid']
            self.entries[uid] = e
            for ident in e.get('ids') or []:
                key = (str(ident.get('type', '')).strip().lower(),
                       re.sub(r'[^A-Za-z0-9]', '',
                              str(ident.get('number', ''))).upper())
                if key[1]:
                    self.by_id.setdefault(key, []).append(uid)
            typ = e.get('type', 'individual')
            names = []
            if e.get('primary_name'):
                names.append((e['primary_name'], 'strong'))
            if e.get('script_name'):
                names.append((e['script_name'], 'strong'))
            for a in e.get('aliases') or []:
                names.append((a['name'], a.get('strength', 'strong')))
            if typ == 'individual':
                self.has_latin[uid] = any(
                    not ARABIC_RE.search(r) for r, s in names
                    if s != 'weak')
                for raw, strength in names:
                    if strength == 'weak':
                        wt = weak_toks(raw)
                        if wt:
                            for k in wt[0].sk:
                                self.weak_index[k].append((uid, wt))
                        continue
                    pn = parse_name(raw)
                    idx = len(self.person_names)
                    self.person_names.append(EntryName(uid, raw, pn))
                    seen = set()
                    for t in pn.core:
                        for k in t.sk:
                            if k not in seen:
                                seen.add(k)
                                self.tok_index[k].add(idx)
            else:
                vessel = (typ == 'vessel')
                for raw, strength in names:
                    if strength == 'weak':
                        wt = weak_toks(raw)
                        if wt:
                            for k in wt[0].sk:
                                self.weak_index[k].append((uid, wt))
                        continue
                    key = norm_org(raw, vessel)
                    if key:
                        self.org_index[key].add(uid)

    def candidates(self, parsed):
        cands = set()
        for t in parsed.core:
            for k in t.sk:
                s = self.tok_index.get(k)
                if s:
                    cands |= s
        return cands


def weak_toks(raw):
    return tuple(get_tok(t if (ARABIC_RE.search(t) or CYRILLIC_RE.search(t))
                         else fold(t)) for t in split_tokens(raw))


def weak_seq_match(a, b):
    if len(a) != len(b) or not a:
        return False
    return all(tok_match(x, y) for x, y in zip(a, b))


# ---------------------------------------------------------------------------
# name matching
# ---------------------------------------------------------------------------

def names_match(a, b):
    """a, b: ParsedName - do they refer to the same person?"""
    if not a.pairs or not b.pairs:
        return False
    for (g1, f1) in a.pairs:
        g1s = given_tok_set(g1)
        f1s = family_tok_set(f1)
        for (g2, f2) in b.pairs:
            ok = False
            for x in g1s:
                for y in given_tok_set(g2):
                    if tok_match(x, y):
                        ok = True
                        break
                if ok:
                    break
            if not ok:
                continue
            ok = False
            for x in f1s:
                for y in family_tok_set(f2):
                    if tok_match(x, y):
                        ok = True
                        break
                if ok:
                    break
            if ok:
                return True
    return False


# ---------------------------------------------------------------------------
# screening
# ---------------------------------------------------------------------------

def screen_customer(row, eng):
    name = (row.get('full_name') or '').strip()
    dob = (row.get('dob') or '').strip()
    ctype = (row.get('type') or 'individual').strip().lower()
    id_type = (row.get('id_type') or '').strip().lower()
    id_num = re.sub(r'[^A-Za-z0-9]', '', (row.get('id_number') or '')).upper()

    # Rule 1: identifiers
    if id_type and id_num:
        uids = eng.by_id.get((id_type, id_num))
        if uids:
            return sorted(uids)[0]

    results = []   # (dob_supported, uid)

    if ctype == 'individual':
        parsed = parse_name(name)
        cust_arabic = bool(ARABIC_RE.search(name))
        for idx in eng.candidates(parsed):
            en = eng.person_names[idx]
            e = eng.entries[en.uid]
            if e.get('type', 'individual') != 'individual':
                continue
            # an original-script name is only consulted for a script customer
            # or when the entry carries no latin spelling at all
            if en.arabic and not cust_arabic and eng.has_latin.get(en.uid):
                continue
            ok, corr = dob_check(dob, e.get('dob', ''))
            if not ok:
                continue
            if names_match(parsed, en.parsed):
                results.append((corr, en.uid))
    else:
        vessel = (ctype == 'vessel')
        key = norm_org(name, vessel)
        uids = eng.org_index.get(key)
        if uids:
            for uid in uids:
                e = eng.entries[uid]
                if e.get('type', 'individual') == 'individual':
                    continue
                results.append((False, uid))
        if not results and key:
            key2 = norm_org(name, True)
            uids = eng.org_index.get(key2)
            if uids:
                for uid in uids:
                    e = eng.entries[uid]
                    if e.get('type', 'individual') == 'individual':
                        continue
                    results.append((False, uid))

    # Rule 3: weak aliases need an identical full date of birth
    cdob = dob_parts(dob)
    if cdob is not None and len(cdob) == 3:
        wt = weak_toks(name)
        if wt:
            seen = set()
            for k in wt[0].sk:
                for uid, awt in eng.weak_index.get(k, ()):
                    if uid in seen:
                        continue
                    e = eng.entries[uid]
                    if dob_parts(e.get('dob', '')) != cdob:
                        continue
                    if weak_seq_match(wt, awt):
                        seen.add(uid)
                        results.append((True, uid))

    if not results:
        return None
    results.sort(key=lambda r: (not r[0], r[1]))
    return results[0][1]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--watchlist', required=True)
    ap.add_argument('--customers', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args(argv)

    with open(args.watchlist, encoding='utf-8') as fh:
        wl = json.load(fh)
    eng = Engine(wl)

    with open(args.customers, encoding='utf-8-sig', newline='') as fh:
        rows = list(csv.DictReader(fh))

    with open(args.out, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['customer_id', 'decision', 'matched_uid'])
        for row in rows:
            try:
                uid = screen_customer(row, eng)
            except Exception:           # never lose the whole batch
                uid = None
            if uid:
                w.writerow([row.get('customer_id', ''), 'MATCH', uid])
            else:
                w.writerow([row.get('customer_id', ''), 'NO_MATCH', ''])
    return 0


if __name__ == '__main__':
    sys.exit(main())
