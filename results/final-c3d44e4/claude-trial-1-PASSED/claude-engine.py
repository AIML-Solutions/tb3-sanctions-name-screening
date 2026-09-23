#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sanctions screening engine (Python 3, standard library only).

Usage:
    python3 screen.py --watchlist <watchlist.json> --customers <customers.csv> \
                      --out <decisions.csv>

Implements the screening policy:
  Rule 1 identifiers, Rule 2 name equivalence across romanisations,
  Rule 3 strong / weak aliases, Rule 4 date of birth, Rule 5 entities and
  vessels, Rule 6 nationality is informational.

How names are compared
----------------------
Every name token is reduced to a set of *phonetic keys*.  A key is a string
over a small phoneme alphabet (x = sh, c = ch, Z = zh, X = shch, T = ts,
A = vowel, E = diphthong, I = final -i/-y, y = glide).  Spelling conventions
that are ambiguous produce several keys, so a token matches another token
when their key sets intersect.  The rules cover the digraphs of the English,
French, German, Polish, Turkish, Indonesian/Malay and scientific-Slavic
conventions, Gulf and sun-letter spellings of Arabic, doubled consonants,
added trailing -e/-h, feminine Slavic endings and Western nicknames.

Original-script names are handled with a script-to-latin lexicon learned from
the watchlist itself (entries that carry both a script name and a latin name),
with a rule-based fallback for tokens the lexicon does not cover.

Two personal names correspond when the entry's given name and its family name
each match a *different* customer token, and every remaining customer token is
explained by the entry (nasab father name, patronymic, initial).  Organisation
and vessel names correspond when, after legal-form designators and vessel
prefixes are removed, every word corresponds - Chinese surname stems match
across pinyin, Wade-Giles, Cantonese and Hokkien spellings.
"""

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict

# ==========================================================================
# 1. Character level normalisation
# ==========================================================================

SPECIAL_CHARS = {
    u'\xdf': 'ss',    # ss
    u'\xe6': 'ae',    # ae
    u'œ': 'oe',  # oe
    u'\xf8': 'o',     # o slash
    u'\xe5': 'a',     # a ring
    u'\xf1': 'n',     # n tilde
    u'\xe7': 'ch',    # c cedilla (Turkish ch)
    u'ş': 'sh',  # s cedilla (Turkish sh)
    u'š': 'sh',  # s caron
    u'ž': 'zh',  # z caron
    u'č': 'ch',  # c caron
    u'ć': 'ch',  # c acute
    u'ś': 'sh',  # s acute
    u'ź': 'zh',  # z acute
    u'ż': 'zh',  # z dot
    u'ł': 'l',   # l stroke
    u'đ': 'd',   # d stroke
    u'ğ': 'g',   # g breve (Turkish)
    u'ı': 'i',   # dotless i
    u'İ': 'i',   # I dot
    u'\xfd': 'y',
    u'\xfe': 't',
    u'\xf0': 'd',
    u'ę': 'e',
    u'ą': 'a',
    u'ń': 'n',
}

ARABIC_LO, ARABIC_HI = 0x0600, 0x06FF
CYRILLIC_LO, CYRILLIC_HI = 0x0400, 0x04FF


def script_kind(text):
    """Return 'ar', 'cy' or None for the dominant non-latin script."""
    ar = cy = 0
    for ch in text:
        o = ord(ch)
        if ARABIC_LO <= o <= ARABIC_HI:
            ar += 1
        elif CYRILLIC_LO <= o <= CYRILLIC_HI:
            cy += 1
    if ar and ar >= cy:
        return 'ar'
    if cy:
        return 'cy'
    return None


def basic_clean(token):
    """Lower-case, expand special letters, drop accents and punctuation."""
    t = token.lower()
    if any(ch in SPECIAL_CHARS for ch in t):
        t = ''.join(SPECIAL_CHARS.get(ch, ch) for ch in t)
    t = unicodedata.normalize('NFD', t)
    t = ''.join(c for c in t if not unicodedata.combining(c))
    return ''.join(c for c in t if c.isalpha())


# ==========================================================================
# 2. Phonetic keys for latin tokens
# ==========================================================================
# phoneme alphabet:  x = sh, c = ch, Z = zh, X = shch, T = ts,
#                    y = glide, A = vowel, E = diphthong, I = final -i/-y

VOWELS = frozenset('aeiou')

RULES = [
    ('schtsch', ['X', 'x']),
    ('shtsch', ['X', 'x']),
    ('stsch', ['X', 'x']),
    ('shtch', ['X']),
    ('tchtch', ['X']),
    ('szch', ['X', 'x']),
    ('szcz', ['X']),
    ('shch', ['X']),
    ('chtsch', ['X']),
    ('chtch', ['X']),
    ('chch', ['X']),
    ('tsch', ['c', 'x']),
    ('dsch', ['j']),
    ('dzh', ['j']),
    ('sch', ['x', 'X', 'Z', 'c']),
    ('stch', ['c', 'x']),
    ('tch', ['c', 'x']),
    ('tsh', ['c', 'x']),
    ('cz', ['c']),
    ('sz', ['x', 's']),
    ('zh', ['Z']),
    ('zch', ['c']),
    ('dj', ['j']),
    ('dz', ['j']),
    ('ch', ['c', 'x', 'h', 'k']),
    ('sh', ['x', 'Z']),
    ('sj', ['x']),
    ('kh', ['h']),
    ('gh', ['g']),
    ('ph', ['v']),
    ('th', ['t']),
    ('ck', ['k']),
    ('cc', ['k']),
    ('tz', ['T']),
    ('ts', ['T']),
    ('x', ['ks']),
    ('qu', ['kv', 'k']),
    ('q', ['k', 'g']),
    ('w', ['v', 'w']),
    ('f', ['v']),
    ('ff', ['v']),
    ('ll', ['l']),
    ('ss', ['s']),
    ('mm', ['m']),
    ('nn', ['n']),
    ('tt', ['t']),
    ('dd', ['d']),
    ('bb', ['b']),
    ('pp', ['p']),
    ('gg', ['g']),
    ('kk', ['k']),
    ('rr', ['r']),
    ('zz', ['z']),
    ('vv', ['v']),
    ('j', ['j', 'y', 'Z']),
    ('1', ['y']),   # mandatory glide marker
    ('g', ['g', 'j']),
]
RULE_MAP = defaultdict(list)
for _pat, _alts in RULES:
    RULE_MAP[_pat[0]].append((_pat, _alts))
for _k in RULE_MAP:
    RULE_MAP[_k].sort(key=lambda kv: -len(kv[0]))

LONG_PAIRS = ('aa', 'ee', 'ii', 'oo', 'uu', 'ou', 'oe', 'ue', 'eu', 'ea')

MAX_VARIANTS = 400


AMBIG_PAIRS = ('ae', 'ea', 'ao', 'oa')


def _vowel_symbol(run, at_end):
    """Vowel run -> one or more vowel phonemes."""
    if at_end:
        if run[-1] in 'iy' or run.endswith('ee'):
            return ['I']
        return ['A']
    r = run
    prev = None
    while prev != r:
        prev = r
        for p in LONG_PAIRS:
            r = r.replace(p, p[0])
    if 'ee' in run or 'ii' in run:
        # long i may or may not stand for a glide (Hosseini / Hosseeni)
        return ['A', 'E']
    if len(r) == 1:
        return ['A']
    if any(p in r for p in AMBIG_PAIRS):
        return ['E', 'A']
    return ['E']


SLAVIC_RE = re.compile(r'(ov|ev|ow|ew|off|eff|in|yn|sky|ski|skij|skiy|skii|'
                       r'skoy|enko|chuk|uk|ich|itch|itsch|ova|eva|owa|ewa|'
                       r'offa|effa|ina|yna|aya|aja|skaya|skaja|tsev|zev|cev)$')


SLAV_KEYS = set()


def looks_slavic(s):
    return len(s) >= 5 and bool(SLAVIC_RE.search(s))


def token_is_slavic(tok):
    """True when the token is spelled like, or sounds like, a russian name."""
    if looks_slavic(tok):
        return True
    if SLAV_KEYS and not phon_keys(tok).isdisjoint(SLAV_KEYS):
        return True
    return False


DBL_CONS_RE = re.compile(r'([bcdfgjklmnpqrstvwxz])\1')


def _expand(s, slav=False, sib=True):
    """All phoneme strings for a cleaned latin token."""
    s = DBL_CONS_RE.sub(r'\1', s)
    results = ['']
    i = 0
    n = len(s)
    while i < n:
        ch = s[i]
        if ch in VOWELS or ch == 'y' or ch == 'j':
            nxt = s[i + 1] if i + 1 < n else ''
            prev_cons = (i == 0) or not (s[i - 1] in VOWELS or s[i - 1] == 'y')
            if ch == 'j':
                if nxt in VOWELS and prev_cons:
                    alts = ('y', '', 'j', 'Z') if (i == 0 or slav) \
                        else ('y', 'j', 'Z')
                    results = [r + a for r in results for a in alts]
                else:
                    results = [r + a for r in results for a in ('j', 'y', 'Z')]
                i += 1
                continue
            if ch in 'yi' and nxt in VOWELS and not (ch == 'i' and nxt == 'i'):
                # consonantal glide; optional after a consonant (ya/ia, io/yo)
                alts = ('y', '') if prev_cons else ('y',)
                results = [r + a for r in results for a in alts]
                i += 1
                continue
            if s[i:i + 2] in ('ou', 'oo') and i + 2 < n and s[i + 2] in VOWELS:
                results = [r + a for r in results for a in ('w', 'A')]
                i += 2
                continue
            j = i
            while j < n and (s[j] in VOWELS or s[j] == 'y'):
                if s[j] == 'y' and j > i and (j + 1 < n and s[j + 1] in VOWELS):
                    break
                j += 1
            results = [r + v for r in results
                       for v in _vowel_symbol(s[i:j], j >= n)]
            i = j
            continue
        if ch == 's' and s[i:i + 2] == 'sy' and i + 2 < n and s[i + 2] in VOWELS:
            # indonesian / malay sy = sh (Syarif), else plain s + glide
            results = [r + a for r in results for a in ('x', 'sy')]
            i += 2
            continue
        matched = False
        for pat, alts in RULE_MAP.get(ch, ()):
            if len(pat) > 1 and s.startswith(pat, i):
                results = [r + a for r in results for a in alts]
                i += len(pat)
                matched = True
                break
        if matched:
            if len(results) > MAX_VARIANTS:
                results = results[:MAX_VARIANTS]
            continue
        if ch == 'c':
            nxt = s[i + 1] if i + 1 < n else ''
            alts = ['s', 'k', 'j'] if nxt in 'eiy' else ['k', 'T', 'j']
            if slav:
                alts = alts + ['c', 'T']
            results = [r + a for r in results for a in set(alts)]
            i += 1
            continue
        if slav and ch in 'sz':
            if ch == 's':
                alts = ['s', 'x', 'z', 'T'] if sib else ['s', 'z', 'T']
            else:
                alts = ['z', 'Z', 'T'] if sib else ['z', 'T']
            results = [r + a for r in results for a in alts]
            i += 1
            continue
        for pat, alts in RULE_MAP.get(ch, ()):
            if len(pat) == 1:
                results = [r + a for r in results for a in alts]
                matched = True
                break
        if not matched:
            results = [r + ch for r in results]
        i += 1
        if len(results) > MAX_VARIANTS:
            results = results[:MAX_VARIANTS]
    return results


DOUBLE_RE = re.compile(r'(.)\1+')
GLIDE_RE = re.compile(r'([AEI])y([AEI])')
HIATUS_RE = re.compile(r'([AEI])y(A[vf])')


SHCH_PARTS = ('xc', 'cc', 'Xc', 'xX', 'sc')


def _post(key, slav=False):
    out = set()
    keys = [key]
    if slav:
        for p in SHCH_PARTS:
            if p in key:
                keys.append(key.replace(p, 'X'))
    res = set()
    for kk in keys:
        res |= _post1(kk, slav)
    return res


def _post1(key, slav=False):
    out = set()
    k = DOUBLE_RE.sub(r'\1', key)
    forms = [k, GLIDE_RE.sub('E', k)]
    if slav:
        # russian hiatus: Andreyev / Andreev, Nikolayev / Nikolaev
        forms.append(HIATUS_RE.sub(r'\1\2', k))
    for base in forms:
        base = DOUBLE_RE.sub(r'\1', base)
        if not base:
            continue
        out.add(base)
        last = base[-1]
        swap = {'f': 'fv', 'v': 'fv', 'd': 'dt', 't': 'dt', 'b': 'bp',
                'p': 'bp', 's': 'sz', 'z': 'sz'}.get(last)
        if swap:
            for c in swap:
                out.add(DOUBLE_RE.sub(r'\1', base[:-1] + c))
        elif len(base) > 2 and base[-1] == 'I' and base[-2] in 'dt':
            for c in 'dt':
                out.add(base[:-2] + c + 'I')
    return out


FEM_SUFFIXES = ('ova', 'eva', 'ina', 'yna', 'owa', 'ewa', 'offa', 'effa',
                'ava', 'iva', 'uva', 'ffa', 'ofa', 'efa', 'afa')
FEM_ADJ = ('skaya', 'skaja', 'skaia', 'tskaya', 'tskaja', 'tskaia', 'sskaya',
           'ckaja', 'ckaya', 'zkaya', 'skaa')


def _trailing_variants(s):
    out = {s}
    cur = s
    while len(cur) > 4 and cur[-1] in 'eh':
        cur = cur[:-1]
        out.add(cur)
    return out


def _morph_variants(s):
    out = {s}
    for suf in FEM_ADJ:
        if s.endswith(suf) and len(s) > len(suf) + 1:
            out.add(s[:-len(suf)] + 'ski')
            return out
    if len(s) >= 6:
        for suf in FEM_SUFFIXES:
            if s.endswith(suf):
                out.add(s[:-1])
                break
    return out


JY_RE = re.compile(r'(?<=[aeiou])j(?![aeiou])')
IY_RE = re.compile(r'iy(?=[aeiou])')
IJ_RE = re.compile(r'ij(?=[aeiou])')

_KEY_CACHE = {}


def phon_keys(token, slav=False):
    """Phonetic key set for a single latin name token."""
    ck = (token, slav)
    v = _KEY_CACHE.get(ck)
    if v is not None:
        return v
    s = basic_clean(token)
    if not s:
        v = frozenset()
        _KEY_CACHE[ck] = v
        return v
    slav = slav or looks_slavic(s)
    spellings = {s}
    if IY_RE.search(s):
        spellings.add(IY_RE.sub('1', s))
    if IJ_RE.search(s):
        spellings.add(IJ_RE.sub('1', s))
    if slav and 'sc' in s and 'sch' not in s:
        spellings.add(s.replace('sc', 'shch'))
    if JY_RE.search(s):
        # scientific / german transliteration: j after a vowel is the glide j
        spellings.add(JY_RE.sub('y', s))
    # a doubled sibilant is a latin spelling device, never russian s/z = sh/zh
    sib = 'ss' not in s and 'zz' not in s
    keys = set()
    for sp in spellings:
        for a in _trailing_variants(sp):
            for b in _morph_variants(a):
                for k in _expand(b, slav, sib):
                    keys |= _post(k, slav)
    v = frozenset(keys)
    _KEY_CACHE[ck] = v
    return v


# ==========================================================================
# 3. Original script handling
# ==========================================================================

CYR_DICT = {
    u'щ': 'shch', u'ш': 'sh', u'ч': 'ch', u'ж': 'zh',
    u'ц': 'ts', u'ю': 'yu', u'я': 'ya', u'ё': 'yo',
    u'а': 'a', u'б': 'b', u'в': 'v', u'г': 'g',
    u'д': 'd', u'е': 'e', u'з': 'z', u'и': 'i',
    u'й': 'y', u'к': 'k', u'л': 'l', u'м': 'm',
    u'н': 'n', u'о': 'o', u'п': 'p', u'р': 'r',
    u'с': 's', u'т': 't', u'у': 'u', u'ф': 'f',
    u'х': 'kh', u'ъ': '', u'ы': 'y', u'ь': '',
    u'э': 'e', u'є': 'ye', u'і': 'i', u'ї': 'yi',
    u'ґ': 'g',
}

ARA_MAP = {
    u'ا': 'a', u'أ': 'a', u'إ': 'a', u'آ': 'a',
    u'ء': '', u'ؤ': 'w', u'ئ': 'y', u'ى': 'a',
    u'ب': 'b', u'پ': 'p', u'ت': 't', u'ث': 't',
    u'ج': 'j', u'چ': 'ch', u'ح': 'h', u'خ': 'kh',
    u'د': 'd', u'ذ': 'z', u'ر': 'r', u'ز': 'z',
    u'ژ': 'zh', u'س': 's', u'ش': 'sh', u'ص': 's',
    u'ض': 'd', u'ط': 't', u'ظ': 'z', u'ع': '3',
    u'غ': 'gh', u'ف': 'f', u'ق': 'q', u'ك': 'k',
    u'ک': 'k', u'گ': 'g', u'ل': 'l', u'م': 'm',
    u'ن': 'n', u'ه': 'h', u'ة': 'h', u'و': 'w',
    u'ي': 'y', u'ی': 'y', u'ـ': '',
}

ARABIC_ARTICLE = (u'ال',)   # al-


def cyr_to_latin(token):
    out = []
    for ch in token.lower():
        if ch in CYR_DICT:
            out.append(CYR_DICT[ch])
        elif ch.isalpha():
            out.append(ch)
    return ''.join(out)


def ara_translit(token):
    out = []
    for ch in token:
        if ch in ARA_MAP:
            out.append(ARA_MAP[ch])
    return ''.join(out)


def ara_keys(token):
    """Fallback keys for an arabic/persian token with no lexicon entry."""
    t = ara_translit(token)
    if not t:
        return frozenset()
    # split into pieces at consonant boundaries; short vowels are unwritten
    pieces = re.findall(r'sh|ch|kh|gh|zh|th|[a-z3]', t)
    forms = ['']
    for idx, p in enumerate(pieces):
        nxt = []
        if p == 'a':
            opts = ['a']
        elif p == '3':
            opts = ['a', '']
        elif p == 'w':
            opts = ['u', 'w', 'o']
        elif p == 'y':
            opts = ['i', 'y']
        else:
            opts = [p]
        for f in forms:
            for o in opts:
                if f and o not in 'aeiou' and f[-1] not in 'aeiou':
                    nxt.append(f + 'a' + o)
                    nxt.append(f + o)
                else:
                    nxt.append(f + o)
        forms = nxt[:120]
    keys = set()
    for f in forms[:120]:
        keys |= phon_keys(f)
    return frozenset(keys)


# ==========================================================================
# 4. Equivalence tables
# ==========================================================================

NICKNAMES = {
    'william': ['bill', 'billy', 'will', 'willie', 'liam'],
    'robert': ['bob', 'bobby', 'rob', 'robbie'],
    'richard': ['dick', 'rick', 'ricky', 'rich', 'richie'],
    'john': ['jack', 'johnny', 'jon', 'johnnie'],
    'michael': ['mike', 'mikey', 'mick', 'micky', 'mickey'],
    'james': ['jim', 'jimmy', 'jamie'],
    'charles': ['charlie', 'chuck', 'chas'],
    'thomas': ['tom', 'tommy'],
    'christopher': ['chris', 'kit'],
    'daniel': ['dan', 'danny'],
    'matthew': ['matt'],
    'anthony': ['tony'],
    'joseph': ['joe', 'joey'],
    'benjamin': ['ben', 'benny', 'benji'],
    'samuel': ['sam', 'sammy'],
    'nicholas': ['nick', 'nicky'],
    'alexander': ['alex', 'sasha', 'sandy', 'xander'],
    'andrew': ['andy', 'drew'],
    'edward': ['ed', 'eddie', 'ted', 'teddy', 'ned'],
    'theodore': ['ted', 'teddy', 'theo'],
    'frederick': ['fred', 'freddie', 'freddy'],
    'henry': ['hank', 'harry', 'hal'],
    'peter': ['pete'],
    'stephen': ['steve'],
    'steven': ['steve'],
    'timothy': ['tim', 'timmy'],
    'gregory': ['greg'],
    'kenneth': ['ken', 'kenny'],
    'ronald': ['ron', 'ronnie'],
    'donald': ['don', 'donnie'],
    'lawrence': ['larry'],
    'jeffrey': ['jeff'],
    'david': ['dave', 'davey'],
    'patrick': ['pat', 'paddy'],
    'francisco': ['paco', 'frank', 'pancho', 'cisco'],
    'francis': ['frank', 'frankie'],
    'jose': ['pepe'],
    'antonio': ['tono'],
    'manuel': ['manny', 'manolo'],
    'eduardo': ['lalo'],
    'roberto': ['beto'],
    'katherine': ['kate', 'kathy', 'katie', 'kat', 'kitty', 'kit', 'cathy'],
    'catherine': ['cathy', 'kate', 'katie', 'cat'],
    'elizabeth': ['liz', 'beth', 'lizzy', 'betty', 'eliza', 'libby'],
    'margaret': ['meg', 'maggie', 'peggy', 'marge'],
    'rebecca': ['becky', 'becca'],
    'victoria': ['vicky', 'vickie', 'tori', 'vic'],
    'jennifer': ['jen', 'jenny', 'jenn'],
    'dorothy': ['dot', 'dottie', 'dolly'],
    'patricia': ['pat', 'patty', 'tricia', 'trish'],
    'deborah': ['deb', 'debbie'],
    'susan': ['sue', 'susie'],
    'barbara': ['barb', 'barbie', 'babs'],
    'christine': ['chris', 'chrissy'],
    'christina': ['chris', 'tina', 'christy'],
    'kimberly': ['kim'],
    'pamela': ['pam'],
    'sandra': ['sandy'],
    'cynthia': ['cindy'],
    'angela': ['angie'],
    'melissa': ['mel'],
    'stephanie': ['steph'],
    'caroline': ['carrie'],
    'charlotte': ['lottie'],
    'alexandra': ['alex', 'sasha'],
    'natalia': ['natasha'],
    'darya': ['dasha'],
    'ekaterina': ['katya'],
    'elena': ['lena'],
    'olga': ['olya'],
    'tatiana': ['tanya'],
    'nadezhda': ['nadya'],
    'lyudmila': ['luda'],
    'svetlana': ['sveta'],
    'irina': ['ira'],
    'anastasia': ['nastya'],
    'kseniya': ['ksyusha'],
    'vladimir': ['vova', 'volodya'],
    'dmitri': ['dima', 'mitya'],
    'nikolai': ['kolya'],
    'anatoly': ['tolya'],
    'yevgeny': ['zhenya'],
    'aleksei': ['alyosha', 'lyosha'],
    'sergei': ['seryozha'],
    'yuri': ['yura'],
    'vyacheslav': ['slava'],
    'viktor': ['vitya'],
    'boris': ['borya'],
    'gennady': ['gena'],
    'valentina': ['valya'],
    'konstantin': ['kostya'],
    'pavel': ['pasha'],
    'maksim': ['maks'],
    'stanislav': ['stas'],
    'roman': ['roma'],
    'leonid': ['lyonya'],
    'galina': ['galya'],
}

EQUIV_GROUPS = [
    ['zhanna', 'zanna', 'shanna', 'schanna'],
    ['tsoi', 'tsoy', 'tzoy', 'tzoi', 'zoi', 'zoy', 'coi', 'coj', 'tsoiy',
     'tzoiy', 'choi', 'soi', 'soy', 'soiy', 'ssoi', 'ssoy', 'zoiy', 'coy'],
    ['petersen', 'pedersen', 'peterson', 'pederson', 'petersson',
     'pettersen', 'petterson'],
    ['yevgeny', 'evgeny', 'eugene', 'evgueny', 'yevgeni', 'jevgeni'],
    ['aleksandr', 'alexander', 'alexandr', 'aleksander', 'alexandre'],
    ['aleksei', 'alexei', 'alexey', 'aleksey', 'aleksej', 'alexeev'],
    ['maksim', 'maxim', 'maksym'],
    ['nikolai', 'nikolay', 'nicolai'],
    ['dmitri', 'dmitry', 'dmitrij', 'dimitri'],
    ['sergei', 'sergey', 'serguei', 'sergej'],
    ['yuri', 'yury', 'yuriy', 'iouri'],
    ['artyom', 'artem', 'artiom'],
    ['semyon', 'semen', 'semion'],
    ['fyodor', 'fedor'],
    ['yelizaveta', 'elizaveta'],
    ['pyotr', 'petr'],
]

NICK_GROUPS = defaultdict(set)


def _build_nick_groups():
    """name -> the other spellings it may stand for.

    A nickname stands for its full names (Ted -> Edward, Theodore) but a full
    name is never replaced by a nickname, so Edward and Theodore stay apart.
    The explicit equivalence groups are closed.
    """
    rel = defaultdict(set)
    for canon, nicks in NICKNAMES.items():
        for nk in nicks:
            rel[nk].add(canon)
    for grp in EQUIV_GROUPS:
        for g in grp:
            rel[g] |= set(grp) - {g}
    for name, others in rel.items():
        NICK_GROUPS[name] = others | {name}


_build_nick_groups()

CHINESE_SURNAMES = {
    'chen': ['chen', "ch'en", 'chan', 'tan', 'chun'],
    'li': ['li', 'lee', 'ly', 'lei', 'ley', 'lay'],
    'liu': ['liu', 'lau', 'lao', 'low', 'liew', 'lew'],
    'wang': ['wang', 'wong', 'ong', 'heng', 'vong'],
    'zhang': ['zhang', 'chang', 'cheung', 'teo', 'teoh', 'tiong', 'chong'],
    'zhao': ['zhao', 'chao', 'chiu', 'chio', 'jao', 'tiau', 'tio'],
    'huang': ['huang', 'hwang', 'wong', 'ng', 'ooi', 'oei', 'uy', 'whang',
              'wee'],
    'wu': ['wu', 'ng', 'goh', 'woo', 'ngo', 'eng', 'gouw'],
    'zhou': ['zhou', 'chou', 'chow', 'chew', 'chau', 'jou'],
    'xu': ['xu', 'hsu', 'tsui', 'hui', 'khoo', 'kho', 'chee'],
    'sun': ['sun', 'suen', 'sng', 'soon', 'shuen'],
    'ma': ['ma', 'mah', 'beh'],
    'zhu': ['zhu', 'chu', 'chue', 'choo', 'ju'],
    'hu': ['hu', 'wu', 'woo', 'oh', 'aw', 'ow'],
    'guo': ['guo', 'kuo', 'kwok', 'kuok', 'kueh', 'quek', 'kwek', 'keh',
            'koay', 'kok'],
    'he': ['he', 'ho', 'hoh', 'hoe'],
    'gao': ['gao', 'kao', 'ko', 'kou', 'kaw', 'koh'],
    'lin': ['lin', 'lam', 'lim', 'lum', 'liem'],
    'luo': ['luo', 'lo', 'law', 'loh'],
    'zheng': ['zheng', 'cheng', 'chiang', 'teh', 'tay', 'tee'],
    'liang': ['liang', 'leung', 'neo', 'nio', 'leong'],
    'xie': ['xie', 'hsieh', 'tse', 'cheah', 'chia', 'sia', 'shieh', 'seah'],
    'song': ['song', 'sung', 'soong', 'sang'],
    'tang': ['tang', "t'ang", 'tong', 'tng', 'thong', 'thng'],
    'deng': ['deng', 'teng', 'thien'],
    'feng': ['feng', 'fung', 'foong'],
    'peng': ['peng', "p'eng", 'pang', 'phang', 'phee'],
    'cao': ['cao', "ts'ao", 'tso', 'cho', 'chaw'],
    'zeng': ['zeng', 'tseng', 'tsang', 'chng', 'tsen'],
    'ye': ['ye', 'yeh', 'yip', 'yap', 'ip', 'yeap'],
    'pan': ['pan', "p'an", 'poon', 'phua', 'pua', 'pun', 'phan'],
    'du': ['du', 'tu', 'to', 'tou', 'toh'],
    'dai': ['dai', 'tai', 'te', 'toi', 'tay'],
    'fan': ['fan', 'faan', 'huan', 'hoan', 'fann'],
    'qian': ['qian', "ch'ien", 'chin', 'chien', 'chee'],
    'jiang': ['jiang', 'chiang', 'kong', 'kang', 'keung'],
    'shen': ['shen', 'sham', 'sim', 'shum', 'sum'],
    'yang': ['yang', 'yeung', 'yeo', 'yio', 'yong', 'iong'],
    'cai': ['cai', "ts'ai", 'choi', 'chua', 'chuah', 'chai', 'tsoi'],
    'ding': ['ding', 'ting', 'teng'],
    'jin': ['jin', 'chin', 'kam', 'kim', 'king'],
    'shi': ['shi', 'shih', 'shek', 'sek', 'sze'],
    'yu': ['yu', 'yue', 'yee', 'ee', 'joo'],
    'lu': ['lu', 'loo', 'lok', 'luk', 'loke'],
    'han': ['han', 'hon', 'hahn'],
    'xiao': ['xiao', 'hsiao', 'siu', 'sio', 'seow'],
    'gu': ['gu', 'ku', 'koo', 'goo'],
    'wei': ['wei', 'ngai', 'gui', 'wai'],
    'qiu': ['qiu', "ch'iu", 'yau', 'hiew'],
    'meng': ['meng', 'mang'],
    'mo': ['mo', 'mok', 'moh'],
    'fang': ['fang', 'fong', 'png'],
    'hou': ['hou', 'hau', 'hao'],
    'kong': ['kong', 'hung', 'khong'],
    'bai': ['bai', 'pai', 'pak'],
    'tian': ['tian', "t'ien", 'tin'],
    'cheng': ['cheng', "ch'eng", 'ching'],
    'zhong': ['zhong', 'chung', 'chong'],
    'shao': ['shao', 'shiu', 'siew'],
    'xiong': ['xiong', 'hsiung', 'hung'],
    'yuan': ['yuan', 'yuen', 'wan', 'oan'],
    'ren': ['ren', 'jen', 'yam'],
    'qi': ['qi', "ch'i", 'chai'],
    'cui': ['cui', "ts'ui", 'chui', 'tsui', 'chhui'],
    'bo': ['bo', 'po'],
    'an': ['an', 'on'],
}

CHINESE_LOOKUP = defaultdict(set)


def build_chinese_lookup(pinyin_in_list=()):
    """form -> candidate pinyin stems.

    A spelling that is itself the pinyin form of a surname carried by the
    watchlist is read literally (Wu is Wu, not cantonese Hu); otherwise it
    also stands for every stem it could romanise.
    """
    CHINESE_LOOKUP.clear()
    for py, forms in CHINESE_SURNAMES.items():
        for f in list(forms) + [py]:
            CHINESE_LOOKUP[basic_clean(f)].add('#' + py)
    for py in pinyin_in_list:
        if py in CHINESE_SURNAMES:
            CHINESE_LOOKUP[basic_clean(py)] = {'#' + py}


build_chinese_lookup(CHINESE_SURNAMES)


# ==========================================================================
# 5. Token / name parsing
# ==========================================================================

ARTICLES = frozenset(['al', 'el', 'ul', 'il', 'as', 'es', 'ash', 'esh', 'ar',
                      'er', 'an', 'en', 'ad', 'ed', 'at', 'et', 'az', 'ez',
                      'ath', 'us', 'ul'])
ARTICLE_PREFIXES = ('al', 'el', 'ul', 'il', 'as', 'es', 'ash', 'esh', 'ar',
                    'ad', 'at', 'az', 'ath', 'an')
NASAB = frozenset(['bin', 'ibn', 'ben', 'bint', 'bn', 'b', 'binti', 'binte',
                   'binit', 'ould', 'walad', 'veled'])
WEST_PARTICLES = frozenset(['de', 'del', 'della', 'di', 'da', 'das', 'dos',
                            'du', 'van', 'von', 'der', 'den', 'ten', 'ter',
                            'la', 'le', 'los', 'las', 'af', 'av', 'zu', 'mac',
                            'mc', 'st', 'saint', 'san', 'do', 'dello', 'op',
                            'vander', 'vanden'])
ABD_PREFIXES = ('abdul', 'abdel', 'abdal', 'abdol', 'abdur', 'abdar', 'abdoul',
                'abdo', 'abdu', 'abd')
ABD_BARE_RE = re.compile(r'^abd[aeiou]{0,2}l{0,2}[eh]?$')

PATRON_RE = re.compile(
    r'^.{3,}?(o|e|ie|ye|ee|a|i)(v|w|ff|f)(ich|itch|itsch|ic|ych|itsh|ish)$|'
    r'^.{3,}?(o|e|ie|ye|ee|a|i)(v|w|ff|f)(na|nna)$|'
    r'^.{4,}(ovna|ovich|evna|evich|ichna|inichna)$')

LEGAL_FORMS = frozenset("""llc lc llp lp ltd ltda limited plc inc incorporated
corp corporation co company companies gmbh mbh ag sa sas sarl srl spa nv bv
oy ab aps kg ohg kft jsc ojsc pjsc ao oao zao pao cjsc fze fzc fzco fzllc
establishment free zone sociedad anonima anonyme aktiengesellschaft joint
stock public private limitada pte pvt pty berhad bhd tbk pt gk kk se scs snc
eurl ug liability group holding trust intl international fz""".split())

ENTITY_DROP = frozenset(['the', 'and', 'of', 'for', '&'])

VESSEL_PREFIXES = frozenset("""mv mt ms mss ss sv fv rv nv msv lng lpg vessel
motor tanker the m v m t m s f v r v n v"""
                            .split())


def tokenize(name):
    n = name.strip().replace(u'’', "'").replace(u'‘', "'")
    n = n.replace('.', '')
    n = n.replace('-', ' ').replace('_', ' ').replace('/', ' ')
    n = n.replace("'", '')
    n = re.sub(r'\s+', ' ', n).strip()
    return [t for t in n.split(' ') if t]


def reorder_comma(name):
    """'Family, Given' -> 'Given Family' (trailing particles stay attached)."""
    name = name.replace(u'\u060c', ',').replace(u'\uff0c', ',')
    if ',' not in name:
        return name
    parts = [p.strip() for p in name.split(',')]
    head = parts[0]
    tail = ' '.join(p for p in parts[1:] if p)
    if not tail:
        return head
    return tail + ' ' + head


def is_initial(tok):
    return len(tok) == 1 and tok.isalpha()


PARTICLE_PREFIXES = ('de', 'del', 'della', 'di', 'da', 'dos', 'du', 'van',
                     'von', 'vander', 'vanden', 'la', 'le', 'mac', 'mc',
                     'ter', 'ten', 'der', 'den', 'dela')


PLAIN_ARTICLES = ('al', 'el', 'ul', 'il', 'ash', 'esh', 'ath')


def strip_article_prefix(tok):
    """Extra spellings for a token with a glued article or particle.

    'ElSayid' -> 'Sayid'.  A sun-letter article is only recognised when the
    consonant is doubled ('AnNajjar' -> 'Najjar') so that ordinary names such
    as 'Arkady' keep their first syllable.
    """
    out = []
    if len(tok) >= 6:
        for p in ARTICLE_PREFIXES:
            if not tok.startswith(p) or len(tok) - len(p) < 4:
                continue
            rest = tok[len(p):]
            if p in PLAIN_ARTICLES or rest[0] == p[-1]:
                out.append(rest)
    cur = tok
    for _ in range(3):
        nxt = None
        for p in PARTICLE_PREFIXES:
            if len(cur) - len(p) >= 4 and cur.startswith(p):
                if nxt is None or len(p) > len(nxt):
                    nxt = p
        if nxt is None:
            break
        cur = cur[len(nxt):]
        out.append(cur)
    return out


def abd_compound(tok_list):
    """Merge 'abd (al) X' into one unit; returns the merged spellings."""
    first = re.sub(r'[eh]$', '', tok_list[0]) or tok_list[0]
    rest = ''.join(tok_list[1:])
    out = set()
    for p in ABD_PREFIXES:
        if not first.startswith(p):
            continue
        body = first[len(p):] + rest
        body = body.lstrip('aeiou')
        for art in ('ll', 'l'):
            if body.startswith(art) and len(body) - len(art) >= 3:
                body = body[len(art):]
                break
        body = body.lstrip('aeiou')
        if body:
            out.add('abd' + body)
    return out


def unit_keys(tokens, use_nicks=True, extra_particles=(), slav=False):
    """Key set for one name unit built from one or more raw tokens."""
    keys = set()
    cleaned = [basic_clean(t) for t in tokens]
    cleaned = [c for c in cleaned if c]
    if not cleaned:
        return frozenset()
    joined = ''.join(cleaned)
    forms = set()
    forms.add(joined)
    is_abd = cleaned[0].startswith('abd') and (len(cleaned) > 1 or
                                                len(cleaned[0]) > 4)
    if is_abd:
        forms |= abd_compound(cleaned)
    else:
        forms.add(cleaned[-1])
        for p in extra_particles:
            forms.add(p + cleaned[-1])
            forms.add(p + joined)
    for f in list(forms):
        for extra in strip_article_prefix(f):
            forms.add(extra)
    for f in forms:
        if not f:
            continue
        keys |= phon_keys(f, slav)
        if use_nicks:
            for g in NICK_GROUPS.get(f, ()):
                if g != f:
                    keys |= phon_keys(g, slav)
    return frozenset(keys)


def org_unit_keys(token):
    """Keys for one organisation / vessel word: exact form, chinese stem
    equivalence, and (for longer words) a phonetic fallback."""
    c = basic_clean(token)
    if not c:
        return frozenset()
    keys = {'=' + c}
    zh = CHINESE_LOOKUP.get(c)
    if zh:
        keys |= zh
    elif len(c) >= 5:
        keys |= phon_keys(c)
    return frozenset(keys)


class PersonName(object):
    __slots__ = ('units', 'extras', 'tokens', 'raw', 'alt')

    def __init__(self, units, extras, tokens, raw):
        self.units = units      # list of frozenset, core name units
        self.extras = extras    # list of frozenset, droppable (father, patro)
        self.tokens = tokens    # cleaned token strings in order
        self.raw = raw
        self.alt = []           # alternative readings of an ambiguous name


def parse_person(name, lex=None):
    """Parse a personal name into core units plus droppable extras.

    A lone 'b' is read as the nasab 'bin', but it can also be a middle
    initial, so both readings are kept.
    """
    kind = script_kind(name)
    if kind:
        return parse_person_script(name, kind, lex)
    p = parse_person_latin(name, lex, True)
    if re.search(r'(?<![a-zA-Z])b\.?(?![a-zA-Z])', name, re.I):
        q = parse_person_latin(name, lex, False)
        if q.tokens != p.tokens:
            p.alt = [q]
    return p


def parse_person_latin(name, lex=None, b_nasab=True):
    raw = reorder_comma(name)
    toks = tokenize(raw)
    toks = [basic_clean(t) if not is_initial(t) else t.lower() for t in toks]
    toks = [t for t in toks if t]
    slav = any(token_is_slavic(t) for t in toks)
    units = []       # list of list-of-tokens
    extras = []
    pending_particles = []
    orphan_particles = []
    i = 0
    n = len(toks)
    while i < n:
        t = toks[i]
        if t in ('o', 'd') and i + 1 < n:
            pending_particles.append(t)
            i += 1
            continue
        if is_initial(t):
            if t == 'b' and b_nasab and i + 1 < n and i > 0:
                i += 1
                # nasab: take the father's name (skip an article)
                j = i
                while j < n and toks[j] in ARTICLES:
                    j += 1
                if j < n:
                    extras.append([toks[j]])
                    i = j + 1
                continue
            i += 1
            continue
        if t in NASAB and i > 0 and i + 1 < n:
            i += 1
            j = i
            while j < n and toks[j] in ARTICLES:
                j += 1
            if j < n:
                extras.append([toks[j]])
                i = j + 1
            continue
        if (t in ARTICLES or t in WEST_PARTICLES) and n > 1:
            if i + 1 < n:
                pending_particles.append(t)
            else:
                orphan_particles.append(t)
            i += 1
            continue
        if len(t) >= 7 and PATRON_RE.match(t):
            extras.append([t])
            pending_particles = []
            i += 1
            continue
        unit = list(pending_particles) + [t]
        pending_particles = []
        units.append(unit)
        i += 1
    orphan_particles.extend(pending_particles)
    # merge 'abd X' style compounds
    merged = []
    k = 0
    while k < len(units):
        u = units[k]
        base = ''.join(u)
        if ABD_BARE_RE.match(base) and k + 1 < len(units):
            merged.append(u + units[k + 1])
            k += 2
        else:
            merged.append(u)
            k += 1
    units = merged
    parts = tuple(orphan_particles) + tuple(
        p for u in units for p in u[:-1])
    ukeys = [unit_keys(u, extra_particles=parts, slav=slav) for u in units]
    ekeys = [unit_keys(e, use_nicks=False, slav=slav) for e in extras]
    ukeys2, units2 = [], []
    for kk, uu in zip(ukeys, units):
        if kk:
            ukeys2.append(kk)
            units2.append(uu)
    return PersonName(ukeys2, [e for e in ekeys if e],
                      [''.join(u) for u in units2], name)


ARA_NASAB = (u'بن', u'ابن', u'بنت', u'بنة')
ARA_ABD = (u'عبد',)


SCRIPT_PUNCT = re.compile(u'[\\s,\u060c\uff0c;\u061b]+')


def parse_person_script(name, kind, lex):
    name = reorder_comma(name)
    toks = [t for t in SCRIPT_PUNCT.split(name.strip()) if t]
    units = []
    extras = []
    i = 0
    n = len(toks)
    while i < n:
        t = toks[i]
        if kind == 'ar':
            if t in ARA_NASAB:
                if i + 2 < n and toks[i + 1] in ARA_ABD:
                    extras.append(script_token_keys(
                        toks[i + 1] + toks[i + 2], kind, lex, compound=True))
                    i += 3
                    continue
                if i + 1 < n:
                    extras.append(script_token_keys(toks[i + 1], kind, lex))
                    i += 2
                    continue
                i += 1
                continue
            if t in ARA_ABD and i + 1 < n:
                # theophoric compound: Abd al-X
                units.append(script_token_keys(toks[i] + toks[i + 1],
                                               kind, lex, compound=True))
                i += 2
                continue
        keys = script_token_keys(t, kind, lex)
        if kind == 'cy' and units and i == n - 2 and n >= 3:
            # a russian patronymic in the middle is droppable
            lat = lex.get(t) if lex else None
            latin = list(lat)[0] if lat else cyr_to_latin(t)
            lc = basic_clean(latin)
            if len(lc) >= 7 and PATRON_RE.match(lc):
                extras.append(keys)
                i += 1
                continue
        units.append(keys)
        i += 1
    if kind == 'ar' and len(units) >= 3:
        # allow the last two tokens to form one compound family name
        comp = script_token_keys(''.join(toks[-2:]), kind, lex, compound=True)
        if comp:
            units = units[:-2] + [frozenset(units[-1] | comp)]
    units = [u for u in units if u]
    return PersonName(units, [e for e in extras if e],
                      [basic_clean(t) for t in toks], name)


def script_token_keys(token, kind, lex, compound=False):
    slav = (kind == 'cy')
    if lex is not None:
        lat = lex.get(token)
        if lat:
            keys = set()
            for l in lat:
                keys |= unit_keys([l], slav=slav)
            return frozenset(keys)
    if kind == 'cy':
        return unit_keys([cyr_to_latin(token)], slav=True)
    keys = set()
    if compound:
        # Abd al-X / Nasr Allah: also index the pieces joined through the lexicon
        for split in range(2, len(token) - 1):
            a, b = token[:split], token[split:]
            la, lb = (lex or {}).get(a), (lex or {}).get(b)
            if la and lb:
                for x in la:
                    for y in lb:
                        keys |= unit_keys([x, y])
            elif la and b.startswith(u'ال') and (lex or {}).get(b[2:]):
                for x in la:
                    for y in lex[b[2:]]:
                        keys |= unit_keys([x, y])
    t = token
    if t.startswith(u'ال') and len(t) > 4:
        alt = t[2:]
        if lex is not None and alt in lex:
            for l in lex[alt]:
                keys |= unit_keys([l])
            return frozenset(keys)
        return frozenset(keys | ara_keys(t) | ara_keys(alt))
    return frozenset(keys | ara_keys(t))


class OrgName(object):
    __slots__ = ('units', 'raw', 'words')

    def __init__(self, units, words, raw):
        self.units = units
        self.words = words
        self.raw = raw


def parse_org(name, vessel=False):
    toks = tokenize(name)
    toks = [basic_clean(t) for t in toks]
    toks = [t for t in toks if t]
    out = []
    if vessel:
        idx = 0
        while idx < len(toks) and toks[idx] in VESSEL_PREFIXES:
            idx += 1
        rest = toks[idx:]
        out = [t for t in rest if t not in ENTITY_DROP]
    else:
        out = [t for t in toks
               if t not in LEGAL_FORMS and t not in ENTITY_DROP]
        if not out:
            out = [t for t in toks if t not in ENTITY_DROP]
    units = [org_unit_keys(t) for t in out]
    return OrgName([u for u in units if u], out, name)


# ==========================================================================
# 6. Matching
# ==========================================================================

def _bipartite(matrix, nleft, nright):
    """Maximum bipartite matching (Kuhn).  matrix[i] = set of right nodes."""
    match_r = [-1] * nright

    def try_k(u, seen):
        for v in matrix[u]:
            if v in seen:
                continue
            seen.add(v)
            if match_r[v] == -1 or try_k(match_r[v], seen):
                match_r[v] = u
                return True
        return False

    cnt = 0
    for u in range(nleft):
        if try_k(u, set()):
            cnt += 1
    return cnt, match_r


def person_match(cust, ent):
    """True when customer name and entry name denote the same person."""
    cu, eu = cust.units, ent.units
    if not cu or not eu:
        return False, 0
    ex = ent.extras
    # compatibility of every customer unit against every entry unit
    comp = []
    for ci, ck in enumerate(cu):
        s = set()
        for ei, ek in enumerate(eu):
            if ck & ek:
                s.add(ei)
        comp.append(s)
    if len(eu) == 1:
        if len(cu) == 1 and comp[0]:
            return True, 2
        return False, 0
    gi, fi = 0, len(eu) - 1
    # the entry's given name and family name must map to distinct customer units
    givens = [i for i in range(len(cu)) if gi in comp[i]]
    fams = [i for i in range(len(cu)) if fi in comp[i]]
    ok = False
    for a in givens:
        for b in fams:
            if a != b:
                ok = True
                break
        if ok:
            break
    if not ok:
        return False, 0
    # every customer unit must be accounted for by the entry
    for ci, ck in enumerate(cu):
        if comp[ci]:
            continue
        if any(ck & e for e in ex):
            continue
        return False, 0
    return True, 1


def org_match(cust, ent):
    cu, eu = cust.units, ent.units
    if not cu or not eu:
        return False, 0
    if len(cu) != len(eu):
        return False, 0
    if all(cu[i] & eu[i] for i in range(len(cu))):
        return True, (3 if cust.words == ent.words else 2)
    matrix = []
    for i, ck in enumerate(cu):
        matrix.append({j for j, ek in enumerate(eu) if ck & ek})
    cnt, _ = _bipartite(matrix, len(cu), len(eu))
    if cnt == len(cu):
        return True, 1
    return False, 0


DOB_RE = re.compile(r'^(\d{4})(?:[-/.](\d{1,2})(?:[-/.](\d{1,2}))?)?$')


def norm_dob(v):
    v = (v or '').strip()
    if not v:
        return ''
    m = DOB_RE.match(v)
    if not m:
        return v
    out = m.group(1)
    if m.group(2):
        out += '-%02d' % int(m.group(2))
    if m.group(3):
        out += '-%02d' % int(m.group(3))
    return out


def dob_compatible(cd, ed):
    """(compatible, corroborated)"""
    if not cd or not ed:
        return True, False
    c = norm_dob(cd)
    e = norm_dob(ed)
    n = min(len(c), len(e))
    if c[:n] == e[:n]:
        return True, True
    return False, False


def norm_id(v):
    return re.sub(r'[^A-Za-z0-9]', '', v or '').upper()


# ==========================================================================
# 7. Watchlist indexing
# ==========================================================================

class Entry(object):
    __slots__ = ('uid', 'etype', 'dob', 'ids', 'names', 'weak', 'raw')

    def __init__(self, uid, etype, dob):
        self.uid = uid
        self.etype = etype
        self.dob = dob
        self.ids = []
        self.names = []     # parsed strong names
        self.weak = []      # (token key list, raw) for weak aliases


def build_lexicon(entries_json):
    """script token -> set of latin tokens, learned from the watchlist."""
    lex = defaultdict(set)
    for e in entries_json:
        s = e.get('script_name')
        p = e.get('primary_name')
        if not s or not p or s == p:
            continue
        if script_kind(p):
            continue
        st = [t for t in re.split(r'[\s,]+', s.strip()) if t]
        pt = [t for t in re.split(r'[\s,]+', p.strip()) if t]
        if len(st) == len(pt):
            for a, b in zip(st, pt):
                lex[a].add(b)
            continue
        # try again after dropping nasab markers on both sides
        st2 = [t for t in st if t not in (u'بن', u'ابن')]
        pt2 = [t for t in pt if basic_clean(t) not in NASAB]
        if len(st2) == len(pt2):
            for a, b in zip(st2, pt2):
                lex[a].add(b)
    return lex


def build_slav_keys(data, lex):
    """Phonetic keys of latin tokens that spell cyrillic-culture names."""
    SLAV_KEYS.clear()
    toks = set()
    for rec in data:
        if script_kind(rec.get('script_name') or '') != 'cy':
            continue
        names = [rec.get('primary_name') or '']
        names += [a.get('name') or '' for a in rec.get('aliases') or []
                  if (a.get('strength') or '') == 'strong']
        for nm in names:
            if script_kind(nm):
                continue
            for t in tokenize(nm):
                c = basic_clean(t)
                if len(c) >= 4:
                    toks.add(c)
    for cyr, lats in lex.items():
        if script_kind(cyr) != 'cy':
            continue
        for l in lats:
            c = basic_clean(l)
            if len(c) >= 4:
                toks.add(c)
    for t in toks:
        SLAV_KEYS.update(unit_keys([t], slav=True))


def load_watchlist(path):
    with open(path, 'r', encoding='utf-8-sig') as fh:
        data = json.load(fh)
    stems = set()
    for rec in data:
        if rec.get('type') == 'entity':
            w = (rec.get('primary_name') or '').split()
            if w:
                stems.add(basic_clean(w[0]))
    build_chinese_lookup(stems)
    lex = build_lexicon(data)
    build_slav_keys(data, lex)
    entries = []
    for rec in data:
        e = Entry(rec['uid'], rec.get('type', 'individual'),
                  norm_dob(rec.get('dob')))
        for idrec in rec.get('ids') or []:
            e.ids.append(((idrec.get('type') or '').strip().lower(),
                          norm_id(idrec.get('number'))))
        names = []
        pn = rec.get('primary_name') or ''
        if pn:
            names.append(pn)
        sn = rec.get('script_name') or ''
        if sn and sn != pn:
            names.append(sn)
        for al in rec.get('aliases') or []:
            nm = (al.get('name') or '').strip()
            if not nm:
                continue
            if (al.get('strength') or '').lower() == 'weak':
                e.weak.append(nm)
            else:
                names.append(nm)
        for nm in names:
            if e.etype == 'individual':
                e.names.append(parse_person(nm, lex))
            else:
                e.names.append(parse_org(nm, vessel=(e.etype == 'vessel')))
        entries.append(e)
    return entries, lex


class Index(object):
    def __init__(self, entries):
        self.entries = entries
        self.by_id = defaultdict(list)
        self.by_num = defaultdict(list)
        self.by_key = defaultdict(set)
        self.by_weak = defaultdict(set)
        for idx, e in enumerate(entries):
            for t, num in e.ids:
                if num:
                    self.by_id[(t, num)].append(idx)
                    self.by_num[num].append(idx)
            for nm in e.names:
                for rd in [nm] + list(getattr(nm, 'alt', ())):
                    for u in rd.units:
                        for k in u:
                            self.by_key[k].add(idx)
            for w in e.weak:
                for k in weak_signature(w):
                    self.by_weak[k].add(idx)


def weak_signature(name):
    """Keys used to look up weak aliases (first token phonetics)."""
    toks = [basic_clean(t) for t in tokenize(name)]
    toks = [t for t in toks if t]
    if not toks:
        return frozenset()
    keys = set()
    for t in toks:
        keys |= phon_keys(t)
    return frozenset(keys)


def weak_equal(cust_name, alias_name):
    a = [basic_clean(t) for t in tokenize(cust_name)]
    b = [basic_clean(t) for t in tokenize(alias_name)]
    a = [t for t in a if t]
    b = [t for t in b if t]
    if len(a) != len(b) or not a:
        return False
    for x, y in zip(a, b):
        if x == y:
            continue
        if phon_keys(x) & phon_keys(y):
            continue
        return False
    return True


# ==========================================================================
# 8. Screening
# ==========================================================================

KNOWN_TYPES = ('individual', 'entity', 'vessel')


def screen_customer(cust, index, lex):
    """Return (decision, matched_uid) for one customer row."""
    ctype = (cust.get('type') or '').strip().lower()
    name = (cust.get('full_name') or '').strip()
    dob = norm_dob(cust.get('dob'))
    id_type = (cust.get('id_type') or '').strip().lower()
    id_num = norm_id(cust.get('id_number'))

    # ---- Rule 1: identifiers -------------------------------------------
    if id_num:
        hits = index.by_id.get((id_type, id_num))
        if not hits:
            hits = index.by_num.get(id_num)
        if hits:
            best = min(index.entries[i].uid for i in hits)
            return 'MATCH', best

    results = []
    types = [ctype] if ctype in KNOWN_TYPES else list(KNOWN_TYPES)
    for ctype in types:
        results.extend(name_matches(name, ctype, dob, index, lex))
    if not results:
        return 'NO_MATCH', ''
    results.sort(key=lambda r: (-r[0], -r[1], r[2]))
    return 'MATCH', results[0][2]


def name_matches(name, ctype, dob, index, lex):
    """All entries of one type whose name and date of birth fit the customer."""
    # ---- parse the customer name ---------------------------------------
    if ctype == 'individual':
        parsed = parse_person(name, lex)
    else:
        parsed = parse_org(name, vessel=(ctype == 'vessel'))

    readings = [parsed] + list(getattr(parsed, 'alt', ()))
    cand = defaultdict(int)
    for rd in readings:
        hit = defaultdict(int)
        for u in rd.units:
            seen = set()
            for k in u:
                for idx in index.by_key.get(k, ()):
                    seen.add(idx)
            for idx in seen:
                hit[idx] += 1
        for idx, h in hit.items():
            cand[idx] = max(cand[idx], h)

    results = []
    for idx, hits in cand.items():
        e = index.entries[idx]
        if e.etype != ctype:
            continue
        if hits < min(2, len(parsed.units)):
            continue
        ok, q = False, 0
        for nm in e.names:
            if ctype == 'individual':
                if not isinstance(nm, PersonName):
                    continue
                for cr in readings:
                    for er in [nm] + list(getattr(nm, 'alt', ())):
                        m, qq = person_match(cr, er)
                        if m:
                            ok = True
                            q = max(q, qq)
            else:
                if not isinstance(nm, OrgName):
                    continue
                m, qq = org_match(parsed, nm)
                if m:
                    ok = True
                    q = max(q, qq)
        if not ok:
            continue
        compat, corrob = dob_compatible(dob, e.dob)
        if not compat:
            continue
        results.append((1 if corrob else 0, q, e.uid))

    # ---- Rule 3: weak aliases ------------------------------------------
    if dob and len(dob) == 10:
        wcand = set()
        for k in weak_signature(name):
            wcand |= index.by_weak.get(k, set())
        for idx in wcand:
            e = index.entries[idx]
            if e.dob != dob or e.etype != ctype:
                continue
            for w in e.weak:
                if weak_equal(name, w):
                    results.append((1, 2, e.uid))
                    break
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description='Sanctions screening')
    ap.add_argument('--watchlist', required=True)
    ap.add_argument('--customers', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args(argv)

    entries, lex = load_watchlist(args.watchlist)
    index = Index(entries)

    with open(args.customers, 'r', encoding='utf-8-sig', newline='') as fh:
        rows = list(csv.DictReader(fh))

    out_rows = []
    for row in rows:
        try:
            dec, uid = screen_customer(row, index, lex)
        except Exception:
            dec, uid = 'NO_MATCH', ''
        out_rows.append((row.get('customer_id', ''), dec, uid))

    with open(args.out, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['customer_id', 'decision', 'matched_uid'])
        for r in out_rows:
            w.writerow(r)
    return 0


if __name__ == '__main__':
    sys.exit(main())
