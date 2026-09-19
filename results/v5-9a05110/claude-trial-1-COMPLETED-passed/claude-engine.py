#!/usr/bin/env python3
"""
Sanctions screening engine.

Decides, for every customer row, whether it refers to the same person,
company or vessel as an entry on the watchlist, applying the rules of
screening_policy.md: transliteration from Arabic / Persian / Cyrillic under
any common romanization convention, name order, particles, nasab elements,
patronymics, nicknames, strong and weak aliases, company legal-form
designators, vessel prefixes, dates of birth and identifiers.

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

# --------------------------------------------------------------------------
# 0.  character folding
# --------------------------------------------------------------------------

# Letters whose plain de-accented form would lose the sound they carry.
_PREMAP = {
    'ß': 'ss',                      # ss
    'æ': 'ae', 'œ': 'oe',      # ae oe
    'ø': 'o', 'đ': 'd', 'ð': 'd', 'þ': 'th',
    'ħ': 'h',
    'ı': 'i', 'İ': 'i',        # Turkish dotless / dotted i
    'ş': 'sh', 'Ş': 'sh',      # s-cedilla  (Turkish)
    'ç': 'ch', 'Ç': 'ch',      # c-cedilla  (Turkish)
    'ğ': 'g', 'Ğ': 'g',        # g-breve
    'ł': 'l', 'Ł': 'l',        # l-stroke   (Polish)
    'ż': 'zh', 'ź': 'zh',      # z-dot / z-acute (Polish)
    'ś': 'sh', 'ć': 'ch',      # s-acute / c-acute (Polish)
    'ń': 'n',
    'č': 'ch', 'š': 'sh', 'ž': 'zh',   # c/s/z-caron
    'ę': 'e', 'ą': 'a',
    'ñ': 'n',
}

_COMBINING = dict.fromkeys(range(0x300, 0x370))


def fold(text):
    """Lower-case, expand special letters, drop diacritics."""
    out = []
    for ch in text.lower():
        out.append(_PREMAP.get(ch, ch))
    s = ''.join(out)
    s = unicodedata.normalize('NFD', s).translate(_COMBINING)
    return unicodedata.normalize('NFC', s)


CYRILLIC_RE = re.compile(r'[Ѐ-ӿ]')
ARABIC_RE = re.compile(r'[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]')


def script_of(text):
    if ARABIC_RE.search(text):
        return 'ar'
    if CYRILLIC_RE.search(text):
        return 'cy'
    return 'la'


# --------------------------------------------------------------------------
# 1.  Cyrillic -> latin
# --------------------------------------------------------------------------

_CYR = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd',
    'е': 'e', 'ё': 'yo', 'ж': 'zh', 'з': 'z', 'и': 'i',
    'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm', 'н': 'n',
    'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't',
    'у': 'u', 'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch',
    'ш': 'sh', 'щ': 'shch', 'ъ': '', 'ы': 'y', 'ь': '',
    'э': 'e', 'ю': 'yu', 'я': 'ya',
    'є': 'ye', 'і': 'i', 'ї': 'yi', 'ґ': 'g',
}


def cyr_to_latin(text):
    return ''.join(_CYR.get(ch, ch) for ch in text.lower())


# --------------------------------------------------------------------------
# 2.  phoneme alphabet
#
#     consonants : b p f m n l r k g t d s z h y  j(sibilant/affricate) c(ts)
#     vowels     : A I U O
#
#     f  covers f / v / w        j covers sh ch zh j shch
#     h  covers h / kh           c covers ts / tz
# --------------------------------------------------------------------------

VOWELS = set('AIUO')

# multigraph -> list of (phoneme tuple, weak?)   weak = aggressive reading
# that is only allowed to meet a *plain* reading on the other side.
_RULES = [
    ('schtsch', [(('j',), 0)]),
    ('stsch', [(('j',), 0)]),
    ('shtch', [(('j',), 0)]),
    ('shch', [(('j',), 0)]),
    ('szcz', [(('j',), 0)]),
    ('tsch', [(('j',), 0)]),
    ('zsch', [(('j',), 0)]),
    ('dsch', [(('j',), 0)]),
    ('sch', [(('j',), 0)]),
    ('tch', [(('j',), 0)]),
    ('dzh', [(('j',), 0)]),
    ('tsh', [(('j',), 0)]),
    ('sh', [(('j',), 0)]),
    ('zh', [(('j',), 0)]),
    ('cz', [(('j',), 0), (('c',), 0)]),
    ('sz', [(('j',), 0), (('s',), 0)]),
    ('rz', [(('j',), 0), (('r', 'z'), 0)]),
    ('ch', [(('j',), 0), (('h',), 0), (('k',), 0)]),
    ('sj', [(('j',), 0)]),
    ('sc', [(('j',), 0), (('s', 'k',), 0)]),
    ('stch', [(('j',), 0)]),
    ('scz', [(('j',), 0)]),
    ('stj', [(('j',), 0)]),
    ('ssch', [(('j',), 0)]),
    ('ssh', [(('j',), 0)]),
    ('tc', [(('j',), 0), (('t', 'k'), 0), (('t', 'c'), 0)]),
    ('dc', [(('j',), 0), (('d', 'k'), 0)]),
    ('sy', [(('j',), 0), (('s', 'y'), 0)]),
    ('dj', [(('j',), 0)]),
    ('tj', [(('j',), 0)]),
    ('nj', [(('n', 'j'), 0), (('n', 'y'), 0), (('n',), 0)]),
    ('ts', [(('c',), 0), (('t', 's'), 0)]),
    ('tz', [(('c',), 0)]),
    ('ck', [(('k',), 0), (('j', 'k'), 0)]),
    ('kh', [(('h',), 0)]),
    ('gh', [(('g',), 0), (('k',), 0)]),
    ('ph', [(('f',), 0)]),
    ('th', [(('t',), 0), (('s',), 0)]),
    ('dh', [(('d',), 0), (('z',), 0)]),
    ('qu', [(('k',), 0), (('k', 'f'), 0)]),
    ('qv', [(('k', 'f'), 0), (('k',), 0)]),
    ('kv', [(('k', 'f'), 0)]),
    ('x', [(('k', 's'), 0)]),
    ('q', [(('k',), 0), (('g',), 0)]),
    ('c', [(('k',), 0), (('c',), 0), (('s',), 0), (('j',), 0)]),
    ('j', [(('j',), 0), (('y',), 0)]),
    ('w', [(('f',), 0)]),
    ('v', [(('f',), 0)]),
    ('z', [(('z',), 0), (('c',), 0), (('j',), 1)]),
    ('s', [(('s',), 0), (('j',), 1), (('z',), 2), (('c',), 2)]),
    ('g', [(('g',), 0), (('j',), 0)]),
    ('b', [(('b',), 0)]),
    ('p', [(('p',), 0)]),
    ('f', [(('f',), 0)]),
    ('m', [(('m',), 0)]),
    ('n', [(('n',), 0)]),
    ('l', [(('l',), 0)]),
    ('r', [(('r',), 0)]),
    ('k', [(('k',), 0)]),
    ('t', [(('t',), 0)]),
    ('d', [(('d',), 0)]),
    ('h', [(('h',), 0)]),
]
_RULE_MAP = {}
for _pat, _alts in _RULES:
    _RULE_MAP[_pat] = _alts
_MAXRULE = max(len(k) for k, _ in _RULES)

_VOWEL_LETTERS = set('aeiouy')


def _base_classes(core):
    if core in ('oe', 'ue', 'uo', 'ou', 'oo', 'uu'):
        return {'U'}
    if core == 'eu':
        return {'U', 'I'}
    has_a = 'a' in core
    has_b = any(ch in 'ou' for ch in core)
    has_f = any(ch in 'ei' for ch in core)
    if has_b and has_f:
        return {'O'}
    if has_b and has_a:
        return {'A', 'U'}
    if has_b:
        return {'U'}
    if has_a and has_f:
        return {'I', 'A'} if 'e' in core else {'I'}
    if has_a:
        return {'A'}
    if has_f:
        return {'I', 'A'} if core == 'e' else {'I'}
    return {'A'}


def _letter_class(ch):
    if ch == 'a':
        return ('A',)
    if ch == 'e':
        return ('A', 'I')
    if ch in 'iy':
        return ('I',)
    return ('U',)


def _run_options(run, final_h, initial, final=False):
    """Vowel run -> list of (phonemes, deletable flags).

    A short (single letter) vowel is 'deletable': arabic script does not
    write it.  Word initial and word final vowels are always written."""
    r = run.replace('j', 'y')
    core = r.replace('y', 'i')
    glide = False
    while len(core) >= 2 and core[0] == 'i' and r[len(r) - len(core) + 1] in 'aeou':
        glide = True
        core = core[1:]
    cls = set(_base_classes(core))
    if glide and core[0] in 'oe' and not initial:
        cls |= {'A', 'I'}          # cyrillic io / e
    if final_h and len(r) <= 2:
        cls |= {'A', 'I'}          # trailing -ah / -eh / -ih
    # a back vowel written with two letters is usually a short /u/ that
    # arabic script does not write either:  Soulten = Sultan
    short = (len(core) == 1 or core in ('ou', 'oo', 'oe', 'ue')) and not final
    deletable = short and not initial
    opts = []
    for c in sorted(cls):
        opts.append(((c,), (deletable,)))
    if glide or r[0] == 'y':
        for c in sorted(cls):
            opts.append((('y', c), (False, short)))
    if r[0] == 'y' and len(r) > 1:
        rest = r[1:].replace('y', 'i')
        for c in sorted(_base_classes(rest)):
            opts.append((('y', c), (False, len(rest) == 1)))
    if initial and len(r) > 2 and r.startswith('ou'):
        # french writes the arabic waw as 'ou':  Oualed = Walid
        for c in sorted(_base_classes(r[2:])):
            opts.append((('f', c), (False, len(r) == 3)))
    if len(r) >= 2:
        # letter by letter: two syllables, or a spelled out glide
        seqs = [()]
        for i, ch in enumerate(r):
            if ch == 'y' and i:
                nxt = [('y',), ('I',)]
            else:
                nxt = [(c,) for c in _letter_class(ch)]
            seqs = [s + n for s in seqs for n in nxt]
            if len(seqs) > 16:
                seqs = seqs[:16]
        for s in seqs:
            if len(s) >= 2:
                opts.append((s, tuple(False for _ in s)))
    return opts


def _segment(word):
    """Split a folded latin word into consonant chunks and vowel runs."""
    segs = []
    i = 0
    n = len(word)
    while i < n:
        if word[i] in _VOWEL_LETTERS:
            j = i
            while j < n and word[j] in _VOWEL_LETTERS:
                j += 1
            segs.append(('V', word[i:j]))
            i = j
        else:
            j = i
            while j < n and word[j] not in _VOWEL_LETTERS:
                j += 1
            segs.append(('C', word[i:j]))
            i = j
    return segs


def _cons_options(chunk, inner=False, final=False):
    """Expand a consonant chunk into alternative (phonemes, strength) pairs.

    inner: the chunk sits between two vowels (t and d trade places there:
    Petersen / Pedersen).  final: last chunk of the word (spanish -ez / -es)."""
    states = [((), 0)]
    i = 0
    n = len(chunk)
    if inner and chunk in ('t', 'd'):
        return [(('t',), 0), (('d',), 0)]
    if final and chunk == 'z':
        return [(('z',), 0), (('c',), 0), (('s',), 0)]   # spanish -ez / -es
    while i < n:
        alts = None
        k = 0
        for k in range(min(_MAXRULE, n - i), 0, -1):
            alts = _RULE_MAP.get(chunk[i:i + k])
            if alts:
                break
        if not alts:
            i += 1
            continue
        new = []
        for seq, w in states:
            for ph, wk in alts:
                new.append((seq + ph, w | wk))
        states = new
        if len(states) > 128:
            states = states[:128]
        i += k
    return states


MAX_KEYS = 700


def _phoneme_seqs(word):
    """folded latin word -> list of (phonemes, deletable flags, strength)"""
    if not word:
        return []
    segs = _segment(word)
    variants = [segs]
    if len(segs) >= 2 and segs[-1] == ('C', 'h') and segs[-2][0] == 'V':
        variants = [segs[:-1], segs]          # silent / pronounced final h
    out = []
    for vsegs in variants:
        final_h_idx = len(vsegs) - 1 if vsegs is not segs else -1
        states = [((), (), 0)]
        for idx, (kind, chunk) in enumerate(vsegs):
            if kind == 'C':
                opts = [(o, tuple(False for _ in o), w)
                        for o, w in _cons_options(
                            chunk, 0 < idx < len(vsegs) - 1,
                            idx == len(vsegs) - 1)]
            else:
                opts = [(o, f, 0) for o, f in
                        _run_options(chunk, idx == final_h_idx, idx == 0,
                                     idx == len(vsegs) - 1)]
            new = []
            for seq, fl, w in states:
                for o, f, w2 in opts:
                    new.append((seq + o, fl + f, w | w2))
            states = new
            if len(states) > MAX_KEYS:
                states = states[:MAX_KEYS]
        out.extend(states)
    return out


def _collapse(seq):
    out = []
    for p in seq:
        if out and out[-1] == p:
            continue
        out.append(p)
    return out


def _collapse_flagged(seq, flags):
    out = []
    ofl = []
    for p, f in zip(seq, flags):
        if out and out[-1] == p:
            ofl[-1] = ofl[-1] or f
            continue
        out.append(p)
        ofl.append(f)
    return out, ofl


def _latin_keys(word):
    """-> (strict, loose); each a dict  reading-strength -> set of keys"""
    strict = {}
    loose = {}
    for seq, flags, weak in _phoneme_seqs(word):
        s, f = _collapse_flagged(seq, flags)
        strict.setdefault(weak, set()).add(''.join(s))
        idxs = [i for i, x in enumerate(f) if x]
        if len(idxs) > 5:
            idxs = idxs[:5]
        dest = loose.setdefault(weak, set())
        for mask in range(1 << len(idxs)):
            drop = {idxs[b] for b in range(len(idxs)) if mask >> b & 1}
            dest.add(''.join(_collapse(
                [p for i, p in enumerate(s) if i not in drop])))
    return strict, loose


# --------------------------------------------------------------------------
# 3.  Arabic / Persian -> phonemes (long vowels only)
# --------------------------------------------------------------------------

_AR = {
    'ا': [('A',)],
    'آ': [('A',)],
    'أ': [('A',)], 'إ': [('A',)],
    'ء': [(), ('A',)],
    'ؤ': [(), ('f',), ('A',)],
    'ئ': [(), ('y',), ('I',)],
    'ب': [('b',)],
    'پ': [('p',)],
    'ت': [('t',)],
    'ث': [('t',), ('s',)],
    'ج': [('j',)],
    'چ': [('j',)],
    'ح': [('h',)],
    'خ': [('h',)],
    'د': [('d',)],
    'ذ': [('d',), ('z',)],
    'ر': [('r',)],
    'ز': [('z',)],
    'ژ': [('j',)],
    'س': [('s',)],
    'ش': [('j',)],
    'ص': [('s',)],
    'ض': [('d',), ('z',)],
    'ط': [('t',)],
    'ظ': [('z',), ('d',)],
    'ع': [(), ('A',)],
    'غ': [('g',), ('k',)],
    'ف': [('f',)],
    'ق': [('k',), ('g',)],
    'ك': [('k',)], 'ک': [('k',)],
    'گ': [('g',)],
    'ل': [('l',)],
    'م': [('m',)],
    'ن': [('n',)],
    'ه': [('h',)],
    'ة': [('A',), ('t',)],
    'و': [('f',), ('U',)],
    'ي': [('y',), ('I',)], 'ی': [('y',), ('I',)],
    'ى': [('A',)],
    'ـ': [()],
}
_AR_DIAC = set('ًٌٍَُِّْٰٓ')


def _arabic_keys(word):
    """Arabic-script word -> set of loose keys."""
    word = ''.join(ch for ch in word if ch not in _AR_DIAC)
    if not word:
        return set()
    n = len(word)
    states = [()]
    for i, ch in enumerate(word):
        opts = _AR.get(ch)
        if opts is None:
            continue
        if i == 0 and ch in 'اآأإ':
            opts = [('A',), ('I',), ('U',)]
        elif i == 0 and ch == 'و':
            opts = [('f',), ('U',)]
        elif i == n - 1 and ch in 'هح':
            opts = [('h',), (), ('A',)]
        new = []
        for st in states:
            for o in opts:
                new.append(st + o)
        states = new
        if len(states) > MAX_KEYS:
            states = states[:MAX_KEYS]
    return {''.join(_collapse(s)) for s in states}


# --------------------------------------------------------------------------
# 4.  token -> key sets (with spelling variants)
# --------------------------------------------------------------------------

_ARTICLE_CONS = ('sh', 'th', 'dh', 'l', 'n', 'r', 's', 'z', 'd', 't')
_NAME_PREFIXES = ('vander', 'vanden', 'vonder', 'dela', 'della', 'van', 'von',
                  'mac', 'mc', 'del', 'dos', 'das', 'den', 'der', 'ter',
                  'ten', 'du', 'de', 'da', 'do', 'di', 'le', 'la')


def _article_variants(t):
    """al-/el-/ash-/ar-... written attached to the name."""
    out = set()
    if len(t) > 5 and t[0] in 'aeiu':
        rest = t[1:]
        if rest.startswith('l') and len(rest) >= 5:
            out.add(rest[1:])
        for art in _ARTICLE_CONS:
            if art == 'l':
                continue
            if (rest.startswith(art) and rest[len(art):].startswith(art[0])
                    and len(rest) - len(art) >= 4):
                out.add(rest[len(art):])
    return out


_ABD_RE = re.compile(r'^(abd|abed|abt)(.*)$')


def abd_cores(rest):
    """Everything that may follow 'abd' -> possible core names."""
    out = set()
    r = rest
    if r and r[0] in 'aeiou':
        r = r[1:]
    out.add(r)
    if r.startswith('l') and len(r) > 2:
        out.add(r[1:])
    m = re.match(r'^[aeiou]{0,2}l[aeiou]{0,2}(.+)$', rest)
    if m and len(m.group(1)) > 2:
        out.add(m.group(1))
    for art in _ARTICLE_CONS:
        if art == 'l':
            continue
        if r.startswith(art) and r[len(art):].startswith(art[0]):
            out.add(r[len(art):])
    out.add(rest)
    return {x for x in out if x}


def _variant_round(forms):
    """One pass of spelling rewrites over a set of forms."""
    out = set(forms)
    for base in list(out):
        m = _ABD_RE.match(base)
        if m and m.group(2):
            for core in abd_cores(m.group(2)):
                out.add('abd' + core)
    for base in list(out):
        out |= _article_variants(base)
    for base in list(out):
        for pre in _NAME_PREFIXES:
            if base.startswith(pre) and len(base) - len(pre) >= 4:
                out.add(base[len(pre):])
        if base.endswith('son') and len(base) > 4:
            out.add(base[:-3] + 'sen')
        elif base.endswith('sen') and len(base) > 4:
            out.add(base[:-3] + 'son')
        if base.endswith('e') and len(base) > 3:
            out.add(base[:-1])
        if base.endswith('aya') and len(base) > 4:
            out.add(base[:-3] + 'y')
        elif base.endswith('aja') and len(base) > 4:
            out.add(base[:-3] + 'y')
        elif base.endswith('a') and len(base) > 4:
            if re.search(r'(ov|ev|off|ow|eff|ew|in|yn|uk|enko|ko)a$', base):
                out.add(base[:-1])
        if base.endswith('d') and len(base) > 3:
            out.add(base[:-1] + 't')
        elif base.endswith('t') and len(base) > 3:
            out.add(base[:-1] + 'd')
        if 'j' in base:
            out.add(base.replace('j', 'y'))
        m = re.search(r'[bcdfgjklmnprstvwxz][eo]([rln])$', base)
        if m:
            out.add(base[:-2] + m.group(1))
        if 'sy' in base:
            out.add(base.replace('sy', 'sh'))
        if 'ny' in base:
            out.add(base.replace('ny', 'n'))
        if re.search(r'[^aeiouy]j[^aeiouy]', base):
            out.add(re.sub(r'(?<=[^aeiouy])j(?=[^aeiouy])', 'i', base))
        if re.search(r'([a-z])\1', base):
            out.add(re.sub(r'([a-z])\1', r'\1', base))
        if 'qu' in base:
            out.add(base.replace('qu', 'qv'))
            out.add(base.replace('qu', 'q'))
        if re.search(r'gu[eiy]', base):
            out.add(re.sub(r'gu([eiy])', r'g\1', base))
    return out


def token_variants(tok):
    """Spelling-level variants of a folded latin token.  Two rounds, so that
    conventions stacked on one name (sy for sh plus a trailing vowel, say)
    still reduce to the plain form."""
    out = {tok}
    if "'" in tok:
        out.add(tok.replace("'", ''))
        m = re.match(r"^[od]'(.+)$", tok)
        if m:
            out.add(m.group(1))
        out.discard(tok)
    m = _ABD_RE.match(tok)
    if m and m.group(2):
        for core in abd_cores(m.group(2)):
            out.add('abd' + core)
    out = _variant_round(out)
    return _variant_round(out)


_key_cache = {}


def token_keys(tok):
    """-> (strict keys, loose keys, is_arabic).

    Both key sets are dicts keyed by reading strength: 0 plain, 1 a bare
    s/z read as a caron letter, 2 a german s read as /z/ or /ts/, 3 both."""
    hit = _key_cache.get(tok)
    if hit is not None:
        return hit
    sc = script_of(tok)
    if sc == 'ar':
        base = tok
        if base.startswith('ال') and len(base) > 3:
            base = base[2:]
        loose = _arabic_keys(base)
        if base != tok:
            loose |= _arabic_keys(tok)
        res = ({}, {0: frozenset(loose)}, True)
    else:
        if sc == 'cy':
            word = fold(cyr_to_latin(tok))
        else:
            word = fold(tok)
        word = re.sub(r"[^a-z']", '', word)
        strict, loose = {}, {}
        for v in token_variants(word):
            if not v:
                continue
            a, b = _latin_keys(v)
            for fl, ks in a.items():
                strict.setdefault(fl, set()).update(ks)
            for fl, ks in b.items():
                loose.setdefault(fl, set()).update(ks)
        caron = len(word) > 3 and CARON_RE.search(word) is not None
        for d in (strict, loose):
            plain = d.get(0, set())
            for fl in list(d):
                if not fl:
                    continue
                keys = d.pop(fl) - plain
                if fl & 1 and not caron:
                    fl |= 2        # only usable in a slavic looking name
                if keys:
                    d[fl] = d.get(fl, set()) | keys
        res = ({k: frozenset(v) for k, v in strict.items() if v},
               {k: frozenset(v) for k, v in loose.items() if v}, False)
    _key_cache[tok] = res
    return res


# A bare s / z read as the caron letters of scientific transliteration only
# makes sense on a slavic-looking word.
CARON_RE = re.compile(
    r'(ov|ev|ow|ew|off|eff|ova|eva|owa|ewa|offa|effa|ovna|evna|in|ina|yn'
    r'|yna|sky|ski|skij|skiy|skaya|skaja|skaia|enko|chenko|ko|uk|ich|itch'
    r'|itsch|ij|yj|ej|oj|aj|nna|iy|ovich|evich)$')


SLAVIC_RE = re.compile(
    r'(ov|ev|off|ow|eff|ew|ova|eva|offa|owa|ewa|effa|ovna|evna|ovich|evich'
    r'|ovitch|evitch|yn|yna|sky|ski|skij|skiy|skaja|skaya|skaia|enko|chenko'
    r'|uk|ich|itch|itsch)$')


def looks_slavic(toks):
    for t in toks:
        if script_of(t) == 'la' and len(t) > 3 and SLAVIC_RE.search(fold(t)):
            return True
    return False


def _plain_match(ka, kb):
    """Both names written in latin script, no aggressive reading needed."""
    if ka[2] or kb[2]:
        return False
    pa = ka[0].get(0)
    pb = kb[0].get(0)
    return bool(pa and pb and (pa & pb))


def _match_keys(ka, kb, ga, gb):
    """At most one side may use a non-plain reading, and a germanic reading
    needs slavic/germanic context on its own side."""
    i = 1 if (ka[2] or kb[2]) else 0
    da, db = ka[i], kb[i]
    pa = da.get(0)
    pb = db.get(0)
    if pa and pb and (pa & pb):
        return True
    if pb:
        for fl, ks in da.items():
            if fl and (fl & 2 == 0 or ga) and (ks & pb):
                return True
    if pa:
        for fl, ks in db.items():
            if fl and (fl & 2 == 0 or gb) and (ks & pa):
                return True
    return False


def tokens_match(a, b, wa=True, wb=True, plain=False):
    """Do two (possibly multi-word, already joined) tokens correspond?"""
    if a == b:
        return True
    ka, kb = token_keys(a), token_keys(b)
    if plain:
        return _plain_match(ka, kb)
    return _match_keys(ka, kb, wa, wb)


# --------------------------------------------------------------------------
# 5.  nicknames and given-name equivalences
# --------------------------------------------------------------------------

# Western given names.  Names in this list are a closed world: two of them
# refer to the same person only when they sit in the same group.
NICK_GROUPS = [
    "william bill billy will willie liam",
    "katherine catherine kathryn kate katie kathy cathy kit kitty",
    "elizabeth elisabeth liz lizzy beth betty betsy eliza",
    "robert bob bobby rob robbie roberto",
    "richard dick rick ricky richie ricardo",
    "michael mike mikey mick micky miguel",
    "john jack johnny jon jonny johann",
    "james jim jimmy jamie jaime",
    "joseph joe joey josef giuseppe",
    "jose pepe",
    "charles charlie chuck carlos",
    "thomas tom tommy tomas",
    "anthony tony antonio",
    "christopher chris kit christoph",
    "nicholas nick nicky nicolas niklas",
    "peter pete petey pedro pierre",
    "edward ed eddie eduardo ted teddy",
    "theodore ted teddy theo",
    "frederick fred freddie freddy federico",
    "francisco frank paco francis franz",
    "andrew andy drew andre andres",
    "samuel sam sammy",
    "benjamin ben benny benji",
    "daniel dan danny dani",
    "matthew matt matty mateo",
    "henry hank harry henri enrique",
    "margaret maggie peggy marge margarita",
    "barbara barb barbie babs",
    "rebecca becca becky becki",
    "dorothy dot dottie dolly",
    "patricia pat patty patti trish tricia",
    "susan sue susie suzy suzanne",
    "victoria vicky vickie tori",
    "jennifer jen jenny jenn",
    "steven stephen steve stefan esteban",
    "anne ann anna annie ana",
    "alexander alex",
    "yevgeny evgeny eugene evgeniy",
]

# Equivalences that no spelling rule produces (turkish and local forms of
# arabic names).  Unlike NICK_GROUPS these only widen a name, they never
# keep two names apart.
EQUIV_GROUPS = [
    "fatima fatma fatimah fatemeh fatme",
    "zaynab zainab zeynep zeinab zeyneb",
    "maryam meryem mariam merjem",
    "aisha ayse aysha aishah aise",
    "khadija hatice khadijah hatidje",
    "amina emine aminah emina",
    "muhammad mehmet muhammet mohammed mohammad",
    "ismail ismael ismayl isma'il",
    "yusuf yusof joesoef jusuf yousuf",
    "ibrahim ibrahem ibrohim",
    "hussein huseyin husein hussain",
    "salim selim saleem",
    "karim kerim kareem",
    "rashid resat resit rasyid",
    "majid mecit madjid",
    "hamid hamit hameed",
    "omar omer umar",
    "khalid halit halid chalid",
    "mahmoud mahmut mahmud",
    "walid velit valid",
    "saeed sait said",
    "nabil nebil nabeel",
    "tariq tarik tarek",
    "marwan mervan marwen",
    "bashar besar beshir bachar",
    "layla leyla laila leila",
    "huda huda hoeda",
    "sharif sjarif syarif",
    "ahmad ahmet achmad ahmed",
]

_NICK_KEY_TO_GROUP = {}          # equivalence groups, looked up by sound
_NICK_GROUP_KEYS = []
_NICK_WORD_TO_GROUP = {}         # western names, looked up by spelling


def _build_nicknames():
    if _NICK_GROUP_KEYS:
        return
    for gi, line in enumerate(NICK_GROUPS + EQUIV_GROUPS):
        keys = set()
        lkeys = set()
        for w in line.split():
            k = token_keys(w)
            keys |= k[0].get(0, frozenset())
            lkeys |= k[1].get(0, frozenset())
        _NICK_GROUP_KEYS.append((frozenset(keys), frozenset(lkeys)))
        if gi < len(NICK_GROUPS):
            # a western short form is recognised by its spelling; going by
            # sound would drag unrelated names into the group
            for w in line.split():
                _NICK_WORD_TO_GROUP.setdefault(w, set()).add(gi)
        else:
            for k in keys:
                _NICK_KEY_TO_GROUP.setdefault(k, set()).add(gi)


def given_keys(tok):
    """Keys of a given name, widened with nickname equivalents."""
    k = token_keys(tok)
    groups = set(_NICK_WORD_TO_GROUP.get(tok, ()))
    for key in k[0].get(0, ()):
        g = _NICK_KEY_TO_GROUP.get(key)
        if g:
            groups |= g
    if not groups:
        return k
    strict = dict(k[0])
    loose = dict(k[1])
    extra = set(strict.get(0, ()))
    lextra = set(loose.get(0, ()))
    for gi in groups:
        extra |= _NICK_GROUP_KEYS[gi][0]
        lextra |= _NICK_GROUP_KEYS[gi][1]
    strict[0] = frozenset(extra)
    loose[0] = frozenset(lextra)
    return (strict, loose, k[2])


def given_match(a, b, wa=True, wb=True, plain=False):
    if a == b:
        return True
    ga = _NICK_WORD_TO_GROUP.get(a)
    if ga:
        gb = _NICK_WORD_TO_GROUP.get(b)
        if gb:
            return bool(ga & gb)
    ka, kb = given_keys(a), given_keys(b)
    if plain:
        return _plain_match(ka, kb)
    return _match_keys(ka, kb, wa, wb)


# --------------------------------------------------------------------------
# 6.  name parsing
# --------------------------------------------------------------------------

PARTICLES = {
    'al', 'el', 'ul', 'il', 'la', 'le', 'de', 'del', 'della', 'di', 'da',
    'do', 'du', 'van', 'von', 'der', 'den', 'ter', 'ten', 'dos', 'das',
    'bin', 'ibn', 'bint', 'binti', 'binte', 'bn', 'ben', 'ould', 'abu',
    'umm', 'af', 'av', 'y', 'ap', 'ال',
}
# sun-letter forms of the article: only before a name starting with that letter
SUN_ARTICLES = {
    'ash': 'sh', 'esh': 'sh', 'ath': 'th', 'adh': 'dh', 'as': 's', 'es': 's',
    'ar': 'r', 'er': 'r', 'ad': 'd', 'ed': 'd', 'at': 't', 'et': 't',
    'an': 'n', 'en': 'n', 'az': 'z', 'ez': 'z', 'asz': 'sz',
}
SUFFIX_WORDS = {'jr', 'sr', 'junior', 'senior'}
NASAB = {'bin', 'ibn', 'bint', 'ben', 'bn', 'binti', 'binte', 'ould', 'b',
         'بن', 'ابن', 'بنت', 'ولد'}
PATRONYMIC_RE = re.compile(
    r'(ovich|evich|ivich|ovitch|evitch|avitch|owitsch|ewitsch|ovitsch'
    r'|evitsch|ovic|evic|owicz|ewicz|ovna|evna|ivna|owna|ewna'
    r'|ович|евич|овна|евна|ична)$')

_ARABIC_ABD = {'عبد', 'عبدال'}
_ABD_TOKENS = ('abd', 'abdu', 'abdul', 'abdel', 'abdal', 'abdol', 'abdoul',
               'abde', 'abdur', 'abdo', 'abed', 'abdi', 'abt', 'abdal')


def _split_camel(tok):
    """ElDouri -> ['el', 'douri']"""
    if len(tok) > 3 and tok[0].isupper():
        m = re.match(r'^(Al|El|Ul|Il|Ash|Ad|Ar|As|At|Az|Abd|Abu|Mac|Mc|Van|'
                     r'De|Du|La|Le|Bin|Ben|O)([A-Z][a-z].*)$', tok)
        if m:
            return [m.group(1), m.group(2)]
    return [tok]


def raw_tokens(name):
    """Split a raw name into parts (comma separated), each a token list."""
    name = name.replace('’', "'")
    parts = []
    for chunk in name.split(','):
        toks = []
        for t in chunk.replace('/', ' ').replace('\\', ' ').split():
            t = t.strip('.;:()[]"')
            t = t.replace('-', '').replace('.', '').replace('‐', '')
            if not t:
                continue
            for piece in _split_camel(t):
                toks.append(piece)
        if toks:
            parts.append(toks)
    return parts


def clean_person_tokens(parts):
    """Drop particles / initials / patronymics, merge abd-compounds."""
    out_parts = []
    total = sum(len(p) for p in parts)
    for part in parts:
        toks = []
        skip_next = 0
        for i, raw in enumerate(part):
            if skip_next:
                skip_next -= 1
                continue
            sc = script_of(raw)
            if sc == 'la':
                low = re.sub(r"[^a-z']", '', fold(raw))
            else:
                low = raw
            if not low:
                continue
            if sc == 'la' and len(low) == 1:
                continue                                     # initial
            if low in SUFFIX_WORDS and toks:
                continue
            if low in SUN_ARTICLES and i + 1 < len(part):
                nxt = part[i + 1]
                if (script_of(nxt) == 'la'
                        and fold(nxt).lower().startswith(SUN_ARTICLES[low])):
                    continue
            if low in PARTICLES and i == 0 and low in NASAB:
                toks.append(low)                     # 'Ben' as a given name
                continue
            if low in NASAB and i > 0 and i + 1 < len(part):
                skip_next = 1                                # nasab element
                nxt = part[i + 1]
                nxt_low = (re.sub(r"[^a-z]", '', fold(nxt))
                           if script_of(nxt) == 'la' else nxt)
                if ((nxt_low in _ABD_TOKENS or nxt_low in _ARABIC_ABD)
                        and i + 2 < len(part)):
                    skip_next = 2
                continue
            if sc == 'la' and low in PARTICLES and (i + 1 < len(part) or toks):
                continue
            probe = low if sc == 'la' else fold(cyr_to_latin(low))
            if total >= 3 and PATRONYMIC_RE.search(probe):
                continue
            toks.append(low)
        if toks:
            out_parts.append(toks)
    merged = []
    for part in out_parts:
        mt = []
        i = 0
        while i < len(part):
            t = part[i]
            if (t in _ABD_TOKENS or t in _ARABIC_ABD) and i + 1 < len(part):
                nxt = part[i + 1]
                if script_of(nxt) == 'ar' and nxt.startswith('ال'):
                    nxt = nxt[2:]
                mt.append(t + nxt)
                i += 2
                continue
            mt.append(t)
            i += 1
        merged.append(mt)
    return merged


def person_forms(name, canonical=False):
    """-> (list of (given tuple, family tuple) hypotheses, weak-ok flag)

    A watchlist name is written given-name first; a customer name may be in
    any order, so both readings are produced for it."""
    parts = clean_person_tokens(raw_tokens(name))
    if not parts:
        return [], False
    flat = [t for p in parts for t in p]
    forms = []
    if len(parts) >= 2 and parts[0] and parts[1]:
        fam, giv = parts[0], parts[1]
        forms.append((tuple(giv), tuple(fam)))
        if len(giv) > 1:
            forms.append((tuple(giv[:-1]), tuple(giv[-1:]) + tuple(fam)))
    n = len(flat)
    if n == 1:
        forms.append(((), (flat[0],)))
    else:
        for k in (1, 2):
            if n - k >= 1:
                forms.append((tuple(flat[:n - k]), tuple(flat[n - k:])))
                if not canonical:
                    forms.append((tuple(flat[k:]), tuple(flat[:k])))
    out = []
    seen = set()
    for giv, fam in forms:
        for f in ((giv, fam), (giv[:1], fam) if len(giv) > 1 else None):
            if f and f not in seen:
                seen.add(f)
                out.append(f)
    return out, looks_slavic(flat)


def phrase_match(a, b, matcher):
    """Do two token sequences correspond, allowing adjacent tokens to be
    written as one word on either side?"""
    if not a or not b:
        return False
    na, nb = len(a), len(b)
    reach = [(0, 0)]
    done = set()
    while reach:
        i, j = reach.pop()
        if (i, j) in done:
            continue
        done.add((i, j))
        if i == na and j == nb:
            return True
        for k in range(1, min(3, na - i) + 1):
            for m in range(1, min(3, nb - j) + 1):
                if k > 1 and m > 1:
                    continue
                if matcher(''.join(a[i:i + k]), ''.join(b[j:j + m])):
                    reach.append((i + k, j + m))
    return False


def person_match(cust, entry, plain=False):
    cforms, cw = cust
    eforms, ew = entry

    def fam_m(x, y):
        return tokens_match(x, y, cw, ew, plain)

    def giv_m(x, y):
        return given_match(x, y, cw, ew, plain)

    for cg, cf in cforms:
        if not cg or not cf:
            continue
        for eg, ef in eforms:
            if not eg or not ef:
                continue
            if phrase_match(cf, ef, fam_m) and phrase_match(cg, eg, giv_m):
                return True
    return False


# --------------------------------------------------------------------------
# 7.  entities and vessels
# --------------------------------------------------------------------------

LEGAL_SUFFIX_PHRASES = [
    ('limited', 'liability', 'company'), ('limited', 'liability', 'co'),
    ('joint', 'stock', 'company'), ('public', 'joint', 'stock', 'company'),
    ('open', 'joint', 'stock', 'company'), ('closed', 'joint', 'stock', 'company'),
    ('free', 'zone', 'establishment'), ('free', 'zone', 'company'),
    ('sociedad', 'anonima'), ('anonim', 'sirketi'), ('limited', 'sirketi'),
    ('sendirian', 'berhad'), ('perseroan', 'terbatas'),
    ('public', 'limited', 'company'), ('private', 'limited'),
    ('and', 'partners'), ('and', 'sons'), ('and', 'co'), ('and', 'company'),
    ('societe', 'anonyme'), ('aktiengesellschaft',),
]
LEGAL_SUFFIX_PHRASES.sort(key=len, reverse=True)
LEGAL_SUFFIX_WORDS = {
    'llc', 'lc', 'ltd', 'limited', 'plc', 'llp', 'lp', 'inc', 'incorporated',
    'corp', 'corporation', 'co', 'company', 'sa', 'gmbh', 'ag', 'jsc', 'ao',
    'oao', 'zao', 'pao', 'ooo', 'pjsc', 'ojsc', 'cjsc', 'fze', 'fzco', 'fzllc',
    'fzelc', 'bv', 'nv', 'as', 'aş', 'sas', 'sarl', 'srl', 'spa', 'sl',
    'pte', 'pvt', 'pt', 'tbk', 'bhd', 'sdn', 'berhad', 'kk', 'kg', 'ohg',
    'mbh', 'eood', 'ood', 'dd', 'doo', 'sp', 'zoo', 'oy', 'ab', 'aps', 'asa',
    'sociedad', 'anonima', 'anonyme', 'societe', 'gmbhco',
}
DROP_WORDS = {'the', 'and', 'of', 'a'}

VESSEL_PREFIXES = {
    'mv', 'm', 'v', 't', 's', 'mt', 'ms', 'ss', 'mts', 'sv', 'fv', 'rv',
    'lng', 'lpg', 'vessel', 'the', 'motor', 'tanker', 'ship', 'mtv',
}
ROMAN = {'i': '1', 'ii': '2', 'iii': '3', 'iv': '4', 'v': '5', 'vi': '6',
         'vii': '7', 'viii': '8', 'ix': '9', 'x': '10',
         'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5',
         'six': '6', 'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10'}


def org_tokens(name):
    toks = []
    for part in raw_tokens(name):
        toks.extend(part)
    out = []
    for t in toks:
        sc = script_of(t)
        low = fold(t) if sc == 'la' else t
        if sc == 'la':
            low = re.sub(r"[^a-z0-9]", '', low)
        if not low or low == '&':
            continue
        out.append(low)
    # strip legal-form phrases / words from the tail
    changed = True
    while changed and out:
        changed = False
        for ph in LEGAL_SUFFIX_PHRASES:
            n = len(ph)
            if len(out) > n and tuple(out[-n:]) == ph:
                out = out[:-n]
                changed = True
                break
        if changed:
            continue
        if len(out) > 1 and out[-1] in LEGAL_SUFFIX_WORDS:
            out = out[:-1]
            changed = True
    out = [t for t in out if t not in DROP_WORDS]
    if not out:
        out = [t for t in toks if t]
    return out


def vessel_tokens(name):
    toks = []
    for part in raw_tokens(name):
        toks.extend(part)
    out = []
    for t in toks:
        low = fold(t)
        low = re.sub(r"[^a-z0-9]", '', low)
        if low:
            out.append(low)
    while len(out) > 1 and out[0] in VESSEL_PREFIXES:
        out = out[1:]
    out = [ROMAN.get(t, t) for t in out]
    return out


def _org_tok_match(x, y):
    return tokens_match(x, y, False, False)


def org_match(a, b):
    """order-insensitive correspondence of all words"""
    if len(a) != len(b):
        return phrase_match(a, b, _org_tok_match)
    used = [False] * len(b)
    for ta in a:
        hit = False
        for i, tb in enumerate(b):
            if not used[i] and _org_tok_match(ta, tb):
                used[i] = True
                hit = True
                break
        if not hit:
            return False
    return True


def vessel_match(a, b):
    if len(a) != len(b):
        return False
    return all(_org_tok_match(x, y) for x, y in zip(a, b))


# --------------------------------------------------------------------------
# 8.  dates
# --------------------------------------------------------------------------

def norm_dob(s):
    """'1975', '1975-3', '1975/03/07' -> '1975', '1975-03', '1975-03-07'"""
    s = (s or '').strip().replace('/', '-').replace('.', '-')
    m = re.match(r'^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?$', s)
    if not m:
        return ''
    y, mo, d = m.group(1), m.group(2), m.group(3)
    out = y
    if mo:
        out += '-%02d' % int(mo)
        if d:
            out += '-%02d' % int(d)
    return out


def dob_check(cdob, edob):
    """-> 'conflict' | 'support' | 'unknown'"""
    if not cdob or not edob:
        return 'unknown'
    n = min(len(cdob), len(edob))
    if cdob[:n] == edob[:n]:
        return 'support'
    return 'conflict'


# --------------------------------------------------------------------------
# 9.  watchlist preparation
# --------------------------------------------------------------------------

class Entry(object):
    __slots__ = ('uid', 'type', 'dob', 'ids', 'strong', 'weak', 'strong_names',
                 'weak_names', 'org', 'vessel')

    def __init__(self):
        self.strong = []
        self.weak = []
        self.strong_names = []
        self.weak_names = []
        self.org = []
        self.vessel = []


def prepare(entries):
    prepared = []
    for e in entries:
        ent = Entry()
        ent.uid = e.get('uid')
        ent.type = e.get('type')
        ent.dob = norm_dob(e.get('dob') or '')
        ent.ids = set()
        for idd in e.get('ids') or []:
            t = (idd.get('type') or '').strip().lower()
            n = re.sub(r'[^a-z0-9]', '', (idd.get('number') or '').lower())
            if n:
                ent.ids.add((t, n))
        names_strong = []
        pn = e.get('primary_name')
        if pn:
            names_strong.append(pn)
        sn = e.get('script_name')
        if sn and sn != pn:
            names_strong.append(sn)
        names_weak = []
        for a in e.get('aliases') or []:
            nm = a.get('name')
            if not nm:
                continue
            if (a.get('strength') or '').lower() == 'weak':
                names_weak.append(nm)
            else:
                names_strong.append(nm)
        ent.strong_names = names_strong
        ent.weak_names = names_weak
        if ent.type == 'individual':
            for nm in names_strong:
                ent.strong.append(person_forms(nm, canonical=True))
            for nm in names_weak:
                ent.weak.append(person_forms(nm, canonical=True))
        elif ent.type == 'vessel':
            for nm in names_strong:
                ent.vessel.append(vessel_tokens(nm))
            for nm in names_weak:
                ent.weak.append(vessel_tokens(nm))
        else:
            for nm in names_strong:
                ent.org.append(org_tokens(nm))
            for nm in names_weak:
                ent.weak.append(org_tokens(nm))
        prepared.append(ent)
    return prepared


def build_index(prepared):
    """key -> set of entry indexes.  Keys are tagged by provenance so a latin
    name can only meet an arabic-script name through the loose keys."""
    idx = defaultdict(set)
    idx_id = defaultdict(set)
    for i, ent in enumerate(prepared):
        toks = set()
        if ent.type == 'individual':
            for forms, _w in ent.strong + ent.weak:
                for giv, fam in forms:
                    toks.update(giv)
                    toks.update(fam)
                    if 1 < len(fam) <= 2:
                        toks.add(''.join(fam))
                    if 1 < len(giv) <= 2:
                        toks.add(''.join(giv))
        else:
            for group in (ent.org or ent.vessel):
                toks.update(group)
            for group in ent.weak:
                toks.update(group)
        for t in toks:
            strict, loose, is_ar = token_keys(t)
            if is_ar:
                for ks in loose.values():
                    for k in ks:
                        idx[('AR', k)].add(i)
            else:
                for ks in strict.values():
                    for k in ks:
                        idx[('L', k)].add(i)
                for ks in loose.values():
                    for k in ks:
                        idx[('AL', k)].add(i)
        for t, num in ent.ids:
            for form in _id_forms(num):
                idx_id[(t, form)].add(i)
    return idx, idx_id


def candidates(idx, toks):
    out = set()
    for t in toks:
        if not t:
            continue
        strict, loose, is_ar = token_keys(t)
        if is_ar:
            for ks in loose.values():
                for k in ks:
                    for ns in ('AL', 'AR'):
                        s = idx.get((ns, k))
                        if s:
                            out |= s
        else:
            for ks in strict.values():
                for k in ks:
                    s = idx.get(('L', k))
                    if s:
                        out |= s
            for ks in loose.values():
                for k in ks:
                    s = idx.get(('AR', k))
                    if s:
                        out |= s
    return out


# --------------------------------------------------------------------------
# 10.  screening
# --------------------------------------------------------------------------

def exact_name_match(cust, entry):
    """Customer name equals an alias (weak alias rule)."""
    cforms, cw = cust
    eforms, ew = entry
    cset = {tuple(sorted(giv + fam)) for giv, fam in cforms}
    eset = {tuple(sorted(giv + fam)) for giv, fam in eforms}
    for a in cset:
        for b in eset:
            if len(a) != len(b):
                continue
            if all(tokens_match(x, y, cw, ew) for x, y in zip(a, b)):
                return True
    return False


def has_latin_name(ent):
    return any(re.search(r'[A-Za-z]', n) for n in ent.strong_names)


def same_person_name(a, b):
    """Do two watchlist entries carry the same name?  Two entries that are
    both written in latin script have to agree letter for letter; when one of
    them exists only in its original script the looser reading is all there
    is."""
    plain = has_latin_name(a) and has_latin_name(b)
    for fa in a.strong:
        for fb in b.strong:
            if person_match(fa, fb, plain) or person_match(fb, fa, plain):
                return True
    return False


def pick_best(results, prepared):
    """Identifier, then date of birth, then - between entries that are not
    the same name - the closer reading, then the lowest uid."""
    results.sort(key=lambda r: (r[0], r[2]))
    best_rank = results[0][0]
    group = [r for r in results if r[0] == best_rank]
    low = group[0]
    minq = min(r[1] for r in group)
    if low[1] == minq:
        return low[2]
    for r in group:
        if r[1] == minq and same_person_name(prepared[low[3]],
                                             prepared[r[3]]):
            return low[2]
    return min(r[2] for r in group if r[1] == minq)


def _id_forms(num):
    """An IMO number may or may not carry its 'imo' prefix."""
    out = [num]
    if num.startswith('imo'):
        out.append(num[3:])
    elif num.isdigit():
        out.append('imo' + num)
    return out


def screen_customer(row, prepared, idx, idx_id):
    ctype = (row.get('type') or '').strip().lower()
    name = row.get('full_name') or ''
    cdob = norm_dob(row.get('dob') or '')
    id_type = (row.get('id_type') or '').strip().lower()
    id_num = re.sub(r'[^a-z0-9]', '', (row.get('id_number') or '').lower())

    # rule 1 -- identifiers
    if id_type and id_num:
        for num in _id_forms(id_num):
            hits = idx_id.get((id_type, num))
            if hits:
                return 'MATCH', min(prepared[i].uid for i in hits)

    if ctype not in ('individual', 'entity', 'vessel'):
        for guess in ('individual', 'entity', 'vessel'):
            row2 = dict(row)
            row2['type'] = guess
            decision, uid = screen_customer(row2, prepared, idx, idx_id)
            if decision == 'MATCH':
                return decision, uid
        return 'NO_MATCH', ''

    if ctype == 'individual':
        cust = person_forms(name)
        toks = set()
        for giv, fam in cust[0]:
            toks.update(giv)
            toks.update(fam)
            for seq in (giv, fam):
                for a in range(len(seq) - 1):
                    toks.add(seq[a] + seq[a + 1])
        results = []
        for i in candidates(idx, toks):
            ent = prepared[i]
            if ent.type != 'individual':
                continue
            dc = dob_check(cdob, ent.dob)
            hit = False
            quality = 1
            if dc != 'conflict':
                for eforms in ent.strong:
                    if person_match(cust, eforms):
                        hit = True
                        if person_match(cust, eforms, plain=True):
                            quality = 0
                        break
            if not hit and len(cdob) == 10 and ent.dob == cdob:
                for eforms in ent.weak:
                    if exact_name_match(cust, eforms):
                        hit = True
                        break
            if hit:
                results.append((0 if dc == 'support' else 1, quality,
                                ent.uid, i))
        if results:
            return 'MATCH', pick_best(results, prepared)
        return 'NO_MATCH', ''

    if ctype == 'vessel':
        vt = vessel_tokens(name)
        best = []
        for i in candidates(idx, vt):
            ent = prepared[i]
            if ent.type != 'vessel':
                continue
            for group in ent.vessel:
                if vessel_match(vt, group):
                    best.append(ent.uid)
                    break
        if best:
            return 'MATCH', min(best)
        return 'NO_MATCH', ''

    ot = org_tokens(name)
    best = []
    for i in candidates(idx, ot):
        ent = prepared[i]
        if ent.type == 'individual':
            continue
        for group in (ent.org or ent.vessel):
            if org_match(ot, group):
                best.append(ent.uid)
                break
    if best:
        return 'MATCH', min(best)
    return 'NO_MATCH', ''


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--watchlist', required=True)
    ap.add_argument('--customers', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args(argv)

    with open(args.watchlist, 'r', encoding='utf-8-sig') as fh:
        entries = json.load(fh)
    if isinstance(entries, dict):                  # tolerate a wrapper object
        for v in entries.values():
            if isinstance(v, list):
                entries = v
                break
    _build_nicknames()
    prepared = prepare(entries)
    idx, idx_id = build_index(prepared)

    with open(args.customers, 'r', encoding='utf-8-sig', newline='') as fh:
        rows = list(csv.DictReader(fh))

    with open(args.out, 'w', encoding='utf-8', newline='') as fh:
        wr = csv.writer(fh)
        wr.writerow(['customer_id', 'decision', 'matched_uid'])
        for row in rows:
            try:
                decision, uid = screen_customer(row, prepared, idx, idx_id)
            except Exception:
                decision, uid = 'NO_MATCH', ''
            wr.writerow([row.get('customer_id', ''), decision, uid])
    return 0


if __name__ == '__main__':
    sys.exit(main())
