#!/usr/bin/env python3
"""Sanctions screening engine.

Matches customer records against a watchlist under the rules in
screening_policy.md: identifier matches, transliteration-tolerant name
equivalence (Arabic / Persian / Cyrillic romanisations, name order,
particles, patronymics, nicknames), strong and weak aliases, company
suffixes, vessel prefixes and date-of-birth corroboration.

How a name is compared
----------------------
Every name token is turned into a *set* of phoneme keys.  A key is a
string of consonant symbols with the class of the first vowel (A front /
U back) kept, later vowels reduced to a slot '.', a final i/y kept (so
Mahmoudi stays apart from Mahmoud) and other trailing vowels dropped (so
Ivanova meets Ivanov).  Where a spelling is genuinely ambiguous - c, ch,
g, j, q, s, w, z, sch, kh ... - every reading is generated, so Cemal,
Djamal, Dschamal and Jamal share a key, as do Sevcenko, Szewczenko,
Schewtschenko and Shevchenko.  Readings that only exist in Cyrillic
romanisation (z = zh, s = sh before a consonant, intervocalic s = z) are
allowed to reach cyrillic-script entries only, which keeps Smith away
from Schmidt and Saed away from Ziad.

Names of individuals then match when their mandatory tokens (everything
but patronymics, nasab elements and initials) line up one-to-one in any
order, with at most one extra element on one side; a patronymic or a
father's name present on both sides must agree.  Entity and vessel names
match word for word after legal forms and vessel prefixes are removed.

Original-script entries are read through a transliteration lexicon that
is learnt at run time from the watchlist itself: every entry that has
both a latin primary name and a script name teaches one script token.

Standard library only.  Usage:

    python3 screen.py --watchlist watchlist.json \
                      --customers customers.csv --out decisions.csv
"""

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict

# --------------------------------------------------------------------------
# text normalisation
# --------------------------------------------------------------------------

_TRANS = {
    "ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "å": "a", "đ": "dj", "ð": "d",
    "þ": "th", "ı": "i", "ł": "l", "ħ": "h", "ʻ": "", "ʼ": "", "’": "",
    "`": "", "´": "", "'": "", "ẚ": "a",
    # turkish / slavic / scientific transliteration letters
    "ş": "sh", "ç": "ch", "ğ": "g", "ü": "u", "ö": "o",
    "š": "sh", "ž": "zh", "č": "ch", "ć": "ch", "ś": "sh", "ź": "zh",
    "ż": "zh", "ř": "rzh", "ľ": "l", "ď": "d", "ť": "t", "ņ": "n",
    "ń": "n", "ñ": "n", "ç": "ch", "ǧ": "gh", "ḥ": "h", "ḫ": "kh",
    "ẖ": "kh", "ṣ": "s", "ḍ": "d", "ṭ": "t", "ẓ": "z", "ʿ": "", "ʾ": "",
    "ġ": "gh", "ǎ": "a", "ě": "ye", "ō": "o", "ū": "u", "ī": "i",
    "ā": "a", "ē": "e", "ŷ": "y", "ǰ": "zh", "ĵ": "zh",
}


def fold(s):
    """Lower-case, expand special letters, drop combining marks."""
    s = unicodedata.normalize("NFC", s).lower()
    out = []
    for ch in s:
        if ch in _TRANS:
            out.append(_TRANS[ch])
        else:
            out.append(ch)
    s = "".join(out)
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s


def is_cyrillic(s):
    return any(0x0400 <= ord(c) <= 0x04FF for c in s)


def is_arabic(s):
    return any(0x0600 <= ord(c) <= 0x06FF for c in s)


def is_script(s):
    return is_cyrillic(s) or is_arabic(s)


# --------------------------------------------------------------------------
# phonetic canonicalisation
# --------------------------------------------------------------------------
# Symbols: consonants b p t d k g f v s z m n l r h y
#          X = sh, J = zh, C = ch, D = dj, Q = gh/q, T? none
#          Z is "ts"  -> use '7'
#          vowels: 'a' front class, 'u' back class (collapsed later)

TS = "7"

# english names whose final w is a vowel, not the slavic /v/
ENGLISH_W = {"andrew", "matthew", "drew", "bartholomew", "shaw", "crow",
             "snow", "lew", "huw"}

# rules: prefix -> list of emitted options.  Longest prefix wins.
_RULES = [
    ("schtsch", ["X"]),
    ("stsch", ["X"]),
    ("shch", ["X", "XC"]),
    ("szcz", ["X", "XC"]),
    ("tsch", ["C", "X", "h"]),
    ("dsch", ["D", "J"]),
    ("dzh", ["D", "J"]),
    ("sch", ["X", "J", "sC"]),
    ("tch", ["C", "X", "h"]),
    ("tsh", ["C"]),
    ("zsch", ["J"]),
    ("sh", ["X", "J"]),
    ("sz", ["X", "s"]),
    ("sj", ["X", "sy"]),
    ("zh", ["J"]),
    ("cz", ["C", "7"]),
    ("ch", ["C", "h", "X"]),
    ("dt", ["d", "t"]),
    ("kh", ["h", "k"]),
    ("gh", ["Q", "g"]),
    ("ph", ["f"]),
    ("th", ["t", "s", "z"]),
    ("dh", ["d", "z"]),
    ("ck", ["k"]),
    ("cc", ["k"]),
    ("ts", [TS, "ts"]),
    ("tz", [TS]),
    ("djdj", ["D"]),
    ("dj", ["D"]),
    ("qu", ["k", "kv"]),
    ("qv", ["k", "kv"]),
    ("x", ["ks"]),
    ("q", ["k", "Q"]),
    ("c", ["k", TS, "C", "D"]),
    ("z", ["z", TS]),
    ("s", ["s"]),
    ("g", ["g", "D", "Q"]),
    ("j", ["D", "J", "y"]),
    ("b", ["b"]),
    ("p", ["p"]),
    ("t", ["t"]),
    ("d", ["d"]),
    ("k", ["k"]),
    ("ff", ["f", "v"]),      # Ivanoffa = Ivanova
    ("f", ["f"]),
    ("v", ["v"]),
    ("m", ["m"]),
    ("n", ["n"]),
    ("l", ["l"]),
    ("r", ["r"]),
    ("h", ["h"]),
]

_RULES_BY_FIRST = defaultdict(list)
for _pat, _opt in _RULES:
    _RULES_BY_FIRST[_pat[0]].append((_pat, _opt))

CAP = 400

# digraphs only valid before a vowel (Arkadj is not Arka-dj)
NEEDS_VOWEL = {"dj", "dzh", "dsch"}


# endings that mark a name as cyrillic beyond reasonable doubt
SLAVIC_RE = re.compile(
    r"(ov|ev|ow|ew|off|eff|ova|eva|owa|ewa|offa|effa|ovna|evna|owna|ewna"
    r"|sky|ski|skiy|skij|skaya|skaja|skii|enko|vich|vitch|vitsch|witsch"
    r"|wich|vic|wicz|tsev|tzev|zev|tsov)$")


def _context_opts(pat, nxt, prev, slavic=False, initial=False):
    """Context sensitive extra readings.

    Scientific transliteration of Cyrillic with the diacritics dropped
    writes s/z/c for s-hacek/z-hacek/c-hacek, but only before a vowel do we
    accept that reading, so that Smith cannot become Schmidt.  German
    romanisation writes intervocalic s for Cyrillic z (Morosowa/Morozova).
    """
    vn = nxt != "" and nxt in "aeiouy"
    vp = prev != "" and prev in "aeiouy"
    # s-hacek / z-hacek survive as plain s / z; accept that reading before a
    # vowel, and before a consonant only inside the word or in a name whose
    # ending looks slavic (Siskin = Shishkin, Nadezda = Nadezhda).
    if pat == "s":
        out = []
        if vn or nxt in ("", "c") or slavic:
            out.append("X")
        if slavic and (vn or vp):
            out.append("z")
        return out
    elif pat == "z":
        if slavic:
            return ("J",)
    elif pat == "ch":
        if nxt in ("r", "l"):
            return ("k",)
    return ()


def _vowel_sym(ch):
    if ch in "ou":
        return "u"
    if ch in "iyj":
        return "i"
    return "a"


def _expand(tok, ctx=False):
    """Expand a folded latin token into a set of raw phoneme strings."""
    raw_tok = tok
    tok = re.sub(r"([^faeiou])\1+", r"\1", tok)  # Rostammi -> Rostami
    n = len(tok)
    out = set()
    slavic = ctx or bool(SLAVIC_RE.search(tok))

    def rec(i, acc):
        if len(out) >= CAP:
            return
        if i >= n:
            out.add("".join(acc))
            return
        ch = tok[i]
        # ---- vowel-ish handling -------------------------------------
        if ch in "aeiou":
            nxt = tok[i + 1] if i + 1 < n else ""
            if i == 0 and ch in "ieo" and nxt in ("a", "e", "o", "u"):
                rec(i + 1, acc + ["y"])     # Iachina = Yashina, Iuri = Yuri
            # hiatus: u/o/ou followed by another vowel may be a consonant /w/
            if tok[i:i + 2] in ("ou", "oo", "uo") and \
                    tok[i + 2:i + 3] in ("a", "e", "i", "y"):
                rec(i + 2, acc + ["v"])
            if tok[i:i + 2] == "ee":            # Bagheree = Bagheri
                rec(i + 2, acc + ["i"])
            if ch in "ou" and nxt in ("a", "e", "i"):
                rec(i + 1, acc + ["v"])
            rec(i + 1, acc + [_vowel_sym(ch)])
            return
        if ch in "yjiw":
            prev = tok[i - 1] if i else ""
            nxt = tok[i + 1] if i + 1 < n else ""
            if ch == "w":
                if i == n - 1 and raw_tok in ENGLISH_W:
                    rec(i + 1, acc + ["u"])     # Andrew, Matthew
                else:
                    rec(i + 1, acc + ["v"])     # Smirnow, Jakowlew, Anwar
                return
            # y / j
            if nxt != "" and nxt in "aeiou":
                rec(i + 1, acc + ["y"])
                if ch == "j":
                    rec(i + 1, acc + ["D"])
                    rec(i + 1, acc + ["J"])
                if not i:
                    # Yegorov = Egorov, Yelena = Elena
                    if nxt == "e":
                        rec(i + 1, acc + ["i"])
                elif prev not in "aeiou" or ch != "j":
                    # Fyodor = Fedor, Mariya = Maria, Huseyin = Hussein
                    rec(i + 1, acc + ["i"])
            else:
                rec(i + 1, acc + ["i"])
                if ch == "j" and not prev:
                    rec(i + 1, acc + ["D"])
            return
        if ch == "h" and i and tok[i - 1] in "aeiouy" and \
                not any(c not in "aeiouy" for c in tok[i + 1:]):
            rec(i + 1, acc + ["h"])         # silent final -h  (Salmah/Salma)
            rec(i + 1, acc)
            return
        # ---- consonant rules ----------------------------------------
        for pat, opts in _RULES_BY_FIRST.get(ch, ()):
            if tok.startswith(pat, i):
                if pat in NEEDS_VOWEL and \
                        tok[i + len(pat):i + len(pat) + 1] not in \
                        ("a", "e", "i", "o", "u", "y"):
                    continue
                nxt = tok[i + len(pat):i + len(pat) + 1]
                extra = _context_opts(pat, nxt, tok[i - 1] if i else "",
                                      slavic, i == 0)
                for o in opts:
                    rec(i + len(pat), acc + [o])
                for o in extra:
                    rec(i + len(pat), acc + [o])
                return
        rec(i + 1, acc)             # unknown character: skip

    rec(0, [])
    return out


def _postprocess(raw):
    """Collapse vowel runs, mark first vowel class, drop trailing vowels."""
    # collapse duplicate adjacent symbols
    res = []
    for ch in raw:
        if res and res[-1] == ch:
            continue
        res.append(ch)
    s = "".join(res)
    # split into runs
    out = []
    i = 0
    first_vowel = True
    n = len(s)
    variants = [""]
    while i < n:
        if s[i] in "aui":
            j = i
            kinds = set()
            while j < n and s[j] in "aui":
                kinds.add(s[j])
                j += 1
            if j >= n:
                # trailing vowel run: dropped, but a final i/y is part of
                # the name (Mahmoudi is not Mahmoud, Karimi is not Karim)
                if "i" in kinds:
                    variants = [v + "I" for v in variants]
                i = j
                continue
            if first_vowel:
                first_vowel = False
                syms = []
                if "a" in kinds or "i" in kinds:
                    syms.append("A")
                if "u" in kinds:
                    syms.append("U")
                variants = [v + sy for v in variants for sy in syms]
            else:
                variants = [v + "." for v in variants]
            i = j
        else:
            variants = [v + s[i] for v in variants]
            i += 1
    return variants


def _final_devoice(keys):
    """Turkish-style final devoicing / voicing variants."""
    pairs = {"t": "d", "d": "t", "p": "b", "b": "p", "k": "g", "g": "k",
             "s": "z", "z": "s", "C": "D", "D": "C", "f": "v", "v": "f"}
    out = set()
    for k in keys:
        out.add(k)
        if k and k[-1] in pairs:
            out.add(k[:-1] + pairs[k[-1]])
    return out


_pcache = {}


def phon(tok, ctx=False):
    """Canonical phoneme-key set for one latin token."""
    if (tok, ctx) in _pcache:
        return _pcache[(tok, ctx)]
    keys = set()
    for raw in _expand(tok, ctx):
        for v in _postprocess(raw):
            if v:
                keys.add(v)
    keys = _final_devoice(keys)
    if len(tok) > 3:
        keys = set(k for k in keys if len(k) >= 2)
    _pcache[(tok, ctx)] = keys
    return keys


# --------------------------------------------------------------------------
# lexicons
# --------------------------------------------------------------------------

NICK = {
    # western short forms -> canonical
    "bill": "william", "billy": "william", "will": "william", "willy": "william",
    "bob": "robert", "bobby": "robert", "rob": "robert", "robbie": "robert",
    "dick": "richard", "rick": "richard", "ricky": "richard", "rich": "richard",
    "jack": "john", "johnny": "john", "jon": "john", "jonny": "john",
    "joe": "joseph", "joey": "joseph", "jos": "joseph", "jo": "joseph",
    "jim": "james", "jimmy": "james", "jamie": "james",
    "tom": "thomas", "tommy": "thomas",
    "tony": "anthony", "ant": "anthony",
    "nick": "nicholas", "nicky": "nicholas", "klaus": "nicholas",
    "chris": "christopher", "kit": "christopher", "topher": "christopher",
    "sam": "samuel", "sammy": "samuel",
    "dan": "daniel", "danny": "daniel",
    "fred": "frederick", "freddie": "frederick", "freddy": "frederick",
    "ted": ("edward", "theodore"), "teddy": ("edward", "theodore"),
    "theo": "theodore",
    "xander": "alexander", "sander": "alexander", "lex": "alexander",
    "jose": "joseph", "josef": "joseph", "giuseppe": "joseph",
    "jozef": "joseph",
    "ed": "edward", "eddie": "edward", "ned": "edward",
    "matt": "matthew", "matty": "matthew",
    "pete": "peter", "petey": "peter",
    "steve": "steven", "stevie": "steven", "stephen": "steven",
    "mike": "michael", "mikey": "michael", "mick": "michael",
    "micky": "michael", "mickey": "michael",
    "andy": "andrew", "drew": "andrew",
    "ben": "benjamin", "benny": "benjamin", "benji": "benjamin",
    "charlie": "charles", "chuck": "charles", "chas": "charles",
    "hank": "henry", "harry": "henry", "hal": "henry",
    "larry": "lawrence", "lawrie": "lawrence",
    "nate": "nathaniel", "nathan": "nathaniel",
    "ron": "ronald", "ronnie": "ronald", "don": "donald",
    "donnie": "donald", "bart": "bartholomew", "cindy": "cynthia",
    "debby": "deborah", "judy": "judith", "sally": "sarah",
    "molly": "mary", "polly": "mary", "peg": "margaret",
    "fran": "frances", "lou": "louis", "nell": "helen",
    "tess": "teresa", "vi": "violet", "gabe": "gabriel",
    "walt": "walter", "wally": "walter",
    "gus": "august", "augie": "august",
    "paco": "francisco", "pancho": "francisco", "curro": "francisco",
    "pepe": ("jose", "joseph"), "pepito": "jose", "chepe": "jose",
    "pedro": "peter", "pierre": "peter", "pietro": "peter",
    "piotr": "peter", "pyotr": "peter", "petr": "peter", "pekka": "peter",
    "michel": "michael", "michele": "michael", "micheal": "michael",
    "miguel": "michael", "mischa": "michael",
    "juan": "john", "jean": "john", "hans": "john", "johann": "john",
    "giovanni": "john", "joao": "john", "jan": "john",
    "guillermo": "william", "guilherme": "william", "wilhelm": "william",
    "carlos": "charles", "karl": "charles", "carl": "charles",
    "antonio": "anthony", "anton": "anthony", "antoine": "anthony",
    "ricardo": "richard", "roberto": "robert", "eduardo": "edward",
    "enrique": "henry", "heinrich": "henry", "henri": "henry",
    "jorge": "george", "georg": "george", "georgy": "george",
    "felipe": "philip", "philippe": "philip", "filip": "philip",
    "esteban": "steven", "stefan": "steven", "stephan": "steven",
    "tomas": "thomas", "thoma": "thomas",
    "nicolas": "nicholas", "nikolaus": "nicholas", "niklas": "nicholas",
    "alejandro": "alexander", "alessandro": "alexander",
    "andres": "andrew", "andre": "andrew", "andreas": "andrew",
    "jacques": "james", "diego": "james", "jaime": "james",
    "guillaume": "william", "wilhelmina": "william",
    "frank": "francisco", "fran": "francisco", "francis": "francisco",
    "alex": "alexander", "sasha": "alexander", "sacha": "alexander",
    "sandy": "alexander", "shura": "alexander", "aleks": "alexander",
    "max": "maksim",
    "peggy": "margaret", "maggie": "margaret", "meg": "margaret",
    "margie": "margaret", "greta": "margaret", "rita": "margaret",
    "kate": "katherine", "katie": "katherine", "kathy": "katherine",
    "cathy": "katherine", "kat": "katherine", "kitty": "katherine",
    "catherine": "katherine", "ekaterina": "katherine",
    "yekaterina": "katherine", "katya": "katherine", "kasia": "katherine",
    "becca": "rebecca", "becky": "rebecca", "reba": "rebecca",
    "betty": "elizabeth", "beth": "elizabeth", "liz": "elizabeth",
    "lizzie": "elizabeth", "eliza": "elizabeth", "bess": "elizabeth",
    "betsy": "elizabeth", "elisabeth": "elizabeth", "lisa": "elizabeth",
    "yelizaveta": "elizabeth", "elizaveta": "elizabeth",
    "dot": "dorothy", "dottie": "dorothy", "dolly": "dorothy",
    "jen": "jennifer", "jenny": "jennifer", "jenna": "jennifer",
    "sue": "susan", "susie": "susan", "suzy": "susan", "suzanne": "susan",
    "susanna": "susan", "susannah": "susan",
    "trish": "patricia", "patty": "patricia", "pat": "patricia",
    "tricia": "patricia",
    "barb": "barbara", "barbie": "barbara", "babs": "barbara",
    "vicky": "victoria", "vicki": "victoria", "tori": "victoria",
    "viktoria": "victoria", "viktoriya": "victoria", "victoriya": "victoria",
    "nancy": "ann", "nan": "ann", "annie": "ann", "anne": "ann",
    "mandy": "amanda", "bella": "isabella", "josie": "josephine",
    "abby": "abigail", "gabe": "gabriel", "vinny": "vincent",
    "tim": "timothy", "timmy": "timothy",
    "art": "arthur", "bert": "albert", "al": "albert",
    "jerry": "gerald", "gerry": "gerald",
    "greg": "gregory", "phil": "philip", "raj": "rajesh",
    "sal": "salvatore", "vic": "victor", "gene": "eugene",
    # russian short forms
    "dima": "dmitri", "mitya": "dmitri", "dimitri": "dmitri",
    "vova": "vladimir", "volodya": "vladimir",
    "kolya": "nikolai", "nikolay": "nikolai", "nicolai": "nikolai",
    "zhenya": "evgeny", "yevgeny": "evgeny", "eugene": "evgeny",
    "evgeni": "evgeny", "yevgeni": "evgeny", "ievgueny": "evgeny",
    "tolya": "anatoly", "misha": "mikhail", "masha": "maria",
    "natasha": "natalia", "tanya": "tatiana", "sveta": "svetlana",
    "lyuda": "lyudmila", "luda": "lyudmila", "olya": "olga",
    "ira": "irina", "vika": "victoria", "yulya": "yulia",
    "ksyusha": "kseniya", "nastya": "anastasia", "sonya": "sofia",
    "yura": "yuri", "vasya": "vasily", "pasha": "pavel",
    "borya": "boris", "grisha": "grigory", "kostya": "konstantin",
    "stas": "stanislav", "vitya": "victor", "slava": "vyacheslav",
    "senya": "semyon", "semen": "semyon", "fedya": "fyodor",
    "lyonya": "leonid", "roma": "roman", "dasha": "darya",
    "nadya": "nadezhda", "galya": "galina", "valya": "valentina",
    "lena": "elena", "alyosha": "aleksei", "lyosha": "aleksei",
    "artem": "artyom", "artiom": "artyom",
    # turkish / indonesian / other conventions for arabic names
    "mehmet": "muhammad", "mehmed": "muhammad", "memet": "muhammad",
    "mohd": "muhammad", "mohamad": "muhammad", "mochamad": "muhammad",
    "hatice": "khadija", "hatije": "khadija", "chadidjah": "khadija",
    "fatma": "fatima", "fatmah": "fatima",
    "ayse": "aisha", "aysha": "aisha", "aisjah": "aisha",
    "zeynep": "zainab", "zeinep": "zainab", "zeyneb": "zainab",
    "osman": "othman", "usman": "othman", "oesman": "othman",
    "uthman": "othman", "ousmane": "othman",
    "iskandar": "alexander", "eskandar": "alexander",
    "yusof": "yusuf", "joesoef": "yusuf", "youssef": "yusuf",
    "sulayman": "sulaiman", "suleyman": "sulaiman", "suleiman": "sulaiman",
    "solomon": "sulaiman",
    "ibrahim": "ibrahim", "brahim": "ibrahim",
    "isa": "isa", "musa": "musa",
    "ahmet": "ahmad", "achmad": "ahmad", "ahmed": "ahmad",
    "kasim": "qasim", "kassem": "qasim",
    "cemal": "jamal", "kemal": "kamal",
    "enver": "anwar", "esat": "asad", "esad": "asad",
    "recep": "rajab", "cafer": "jafar", "haydar": "haidar",
    "resit": "rashid", "mecit": "majid", "hamit": "hamid",
    "mahmut": "mahmoud", "davut": "dawud", "yakup": "yaqub",
    "halil": "khalil", "halit": "khalid", "halid": "khalid",
    "riza": "reza", "seyit": "sayyid", "sait": "saeed",
    "abdurrahman": "abdulrahman", "abdurahman": "abdulrahman",
}

# names whose phonetic key must stay distinct even though the generic
# rules would merge them are not needed here; the table above only adds.

_tokcache = {}


def token_keys(tok, ctx=False):
    """Phonetic key set for a name token, including nickname expansion.

    The nickname table is looked up on the literal spelling (not on the
    phonetic key) so that unrelated names which happen to share a key
    (Sam/Sami, Kit/Kate) cannot chain into each other.
    """
    if (tok, ctx) in _tokcache:
        return _tokcache[(tok, ctx)]
    keys = set(phon(tok, ctx))
    roots = NICK.get(tok)
    if roots:
        if not isinstance(roots, tuple):
            roots = (roots,)
        for r in roots:
            keys |= phon(r, ctx)
            r2 = NICK.get(r)
            if r2 and not isinstance(r2, tuple):
                keys |= phon(r2, ctx)
            elif r2:
                for x in r2:
                    keys |= phon(x, ctx)
    _tokcache[(tok, ctx)] = keys
    return keys


# --------------------------------------------------------------------------
# name parsing
# --------------------------------------------------------------------------

ARTICLES = {"al", "el", "ul", "il", "ol", "as", "ash", "an", "ar", "at", "ad",
            "az", "ath", "adh", "es", "er", "en", "am", "asz"}
WEST_PARTICLES = {"de", "del", "della", "der", "den", "di", "da", "das",
                  "dos", "du", "la", "le", "van", "von", "ten", "ter",
                  "mac", "mc", "st", "o", "d", "af", "av", "bin_west"}
NASAB = {"bin", "ibn", "ben", "bn", "bint", "binti", "binte", "ibne", "b",
         "ould", "veled", "walad"}
COMPOUND_HEADS = {"abd", "abdu", "abdul", "abdel", "abdal", "abdol", "abdoul",
                  "abed", "abdil", "abduh", "abdo"}
KUNYA = {"abu", "abou", "bou", "umm", "om"}
TITLES = {"mr", "mrs", "ms", "dr", "prof", "sheikh", "shaykh", "haj", "hajj",
          "hajji", "sayyid", "eng", "capt", "gen", "col", "maj", "the"}

LEGAL = [
    "limited liability company", "public joint stock company",
    "joint stock company", "free zone establishment", "sociedad anonima",
    "private limited company", "private limited", "sendirian berhad",
    "open joint stock company", "closed joint stock company",
    "societe anonyme", "aktiengesellschaft", "incorporated",
    "anonim sirketi", "limited sirketi", "ltd sti", "perseroan terbatas",
    "spolka akcyjna", "sp z oo", "sp zoo", "obshchestvo s ogranichennoy"
    " otvetstvennostyu", "naamloze vennootschap", "besloten vennootschap",
    "societa per azioni", "societe a responsabilite limitee",
    "corporation", "company", "limited", "llc", "lc", "ltd", "ltda",
    "sa", "gmbh", "jsc", "pjsc", "ojsc", "cjsc", "ao", "oao", "zao", "pao",
    "co", "corp", "inc", "fze", "fzco", "fzllc", "fz", "plc", "llp", "lp",
    "sarl", "srl", "spa", "bv", "nv", "ag", "kg", "ab", "as", "oy", "oyj",
    "pte", "pvt", "sdn", "bhd", "tbk", "pt", "ooo", "too", "cv", "ug",
    "aps", "kft", "doo", "dd", "sas", "sasu", "eurl", "snc", "scs",
    "sti", "spzoo", "kgaa", "se", "asa", "ans", "kk", "yk", "berhad",
]
LEGAL_SET = set(LEGAL)

VESSEL_PREFIX = {"mv", "mt", "ms", "ss", "msv", "mtv", "vessel", "the",
                 "m/v", "m/t", "m/s", "s/s", "fv", "tv", "lpg", "lng"}


def split_tokens(name):
    name = fold(name)
    name = name.replace("&", " and ")
    # L.L.C. -> llc , G.m.b.H. -> gmbh , M/V -> mv
    name = re.sub(r"(?:[a-z]\.){2,}",
                  lambda m: m.group(0).replace(".", ""), name)
    name = re.sub(r"(?<=[a-z])/(?=[a-z])", "", name)
    name = re.sub(r"(?<=[a-z])-(?=[a-z])", "", name)   # al-Douri, Smith-Jones
    name = re.sub(r"[^a-z0-9Ѐ-ӿ؀-ۿ]+", " ", name)
    return [t for t in name.split() if t]


def strip_article(tok):
    """Variants of a token with a leading arabic article removed."""
    out = {tok}
    if len(tok) > 4 and tok[0] in "aeiu" and tok[1] == "l":
        rest = tok[2:]                         # al-/el-/ul- + name
        if len(rest) >= (4 if rest[0] in "aeiou" else 3):
            out.add(rest)
    # sun-letter assimilation: ar-rashid -> arrashid, an-najjar -> annajjar
    if len(tok) > 4 and tok[0] in "ae":
        for c in ("sh", "th", "l", "r", "n", "s", "d", "t", "z"):
            rest = tok[1 + len(c):]
            if tok[1:].startswith(c) and rest.startswith(c) and len(rest) >= 3:
                out.add(rest)
                break
    # mac / mc prefixes are interchangeable
    if tok.startswith("mc") and len(tok) > 3:
        out.add("mac" + tok[2:])
    elif tok.startswith("mac") and len(tok) > 4:
        out.add("mc" + tok[3:])
    return out


class Tok(object):
    __slots__ = ("keys", "kind", "raw")

    def __init__(self, keys, kind, raw):
        self.keys = keys
        self.kind = kind          # core | patro | nasab | initial
        self.raw = raw


PATRO_STRONG = re.compile(
    r".*(?:(?:ov|ev|iv|yv|ow|ew|off|eff|av)"
    r"(?:ich|itch|itsch|isch|ic|itz|ych|yc|na|nna)"
    r"|ogly|oglu|kyzy|qizi)$")


def _keys_for(tok, ctx=False):
    keys = set()
    for v in strip_article(tok):
        keys |= token_keys(v, ctx)
    return keys


def parse_person(name, ctx=True):
    """Return a list of Tok for an individual name.

    ``ctx`` licenses the cyrillic-only readings (z=zh, s=sh before a
    consonant, intervocalic s=z).  Watchlist entries use it only when the
    entry really is a cyrillic-script name; customer names always try both
    so that an unknown spelling can still reach the right entry.
    """
    toks = split_tokens(name)
    toks = [t for t in toks if t not in TITLES or len(toks) <= 2]
    if not toks:
        return []
    # trailing western particles attach to the first token
    trailing = []
    while len(toks) > 1 and toks[-1] in WEST_PARTICLES:
        trailing.insert(0, toks.pop())
    head = None
    if trailing:
        head = toks[0]
        toks[0] = "".join(trailing) + toks[0]
    # merge leading western particles onto the following token
    merged = []
    bare = {}
    if head is not None:
        bare[toks[0]] = head
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in WEST_PARTICLES and i + 1 < len(toks):
            j = i
            pref = []
            while j < len(toks) - 1 and toks[j] in WEST_PARTICLES:
                pref.append(toks[j])
                j += 1
            glued = "".join(pref) + toks[j]
            merged.append(glued)
            bare[glued] = toks[j]
            i = j + 1
            continue
        merged.append(t)
        i += 1
    toks = merged
    # arabic compounds: abd (al) X  /  nasr allah  /  abu X
    out = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in COMPOUND_HEADS and i + 1 < len(toks):
            j = i + 1
            while j + 1 < len(toks) and (toks[j] in ARTICLES or
                                         len(toks[j]) == 1):
                j += 1
            out.append(("abd", toks[j]))
            i = j + 1
            continue
        if t in KUNYA and i + 1 < len(toks):
            out.append(("abu", toks[i + 1]))
            i += 2
            continue
        if t == "nasr" and i + 1 < len(toks) and toks[i + 1] in (
                "allah", "alah", "ullah", "ollah", "lah"):
            out.append((None, "nasrallah"))
            i += 2
            continue
        if t.startswith("abd") and len(t) > 5:
            out.append(("abd", t[3:]))
            i += 1
            continue
        out.append((None, t))
        i += 1
    ctx = ctx or any(SLAVIC_RE.search(x) for p, x in out if p is None)
    # classify
    res = []
    n = len(out)
    idx = 0
    skip_next = 0
    for idx in range(n):
        if skip_next:
            skip_next -= 1
            continue
        pre, t = out[idx]
        if pre is None and t in ARTICLES and idx + 1 < n:
            nxt = out[idx + 1][1]
            if t in ("al", "el", "ul", "il", "ol") or (
                    nxt and nxt.startswith(t[1:])):
                continue                       # article: as-Sabah, an-Najjar
        if pre is None and t in NASAB and idx + 1 < n and idx > 0:
            # father's name follows (possibly behind an article)
            j = idx + 1
            if out[j][0] is None and out[j][1] in ARTICLES and j + 1 < n:
                j += 1
            core_left = sum(1 for k, (p, x) in enumerate(out)
                            if k not in range(idx, j + 1) and not (
                                p is None and (x in ARTICLES or len(x) == 1)))
            if core_left >= 2:
                p2, t2 = out[j]
                res.append(Tok(_compound_keys(p2, t2, ctx), "nasab", t2))
                skip_next = j - idx
                continue
        if pre is None and len(t) == 1:
            res.append(Tok(set(), "initial", t))
            continue
        kind = "core"
        if pre is None and PATRO_STRONG.match(t) and len(t) > 6:
            kind = "patro"
        keys = _compound_keys(pre, t, ctx)
        if t in bare:               # van der Berg ~ Berg
            keys = keys | _compound_keys(pre, bare[t], ctx)
        res.append(Tok(keys, kind, t))
    # a patronymic is only droppable when a given name and a family name
    # remain; otherwise it is the family name (Popovic, Ivanovich)
    ncore = sum(1 for r in res if r.kind == "core")
    if ncore < 2:
        for r in res:
            if r.kind == "patro" and ncore < 2:
                r.kind = "core"
                ncore += 1
    return res


ALLAH_RE = re.compile(r"^[aeiou]*l+[aeiou]*h?[ei]?$")


def _tail_variants(t):
    """Candidate spellings for the second half of an arabic compound."""
    out = {t}
    if ALLAH_RE.match(t) and len(t) > 2:
        return {"allah"}
    s = t.lstrip("aeiou")
    if s != t and len(s) >= 3:
        out.add(s)
        for c in ("sh", "l", "r", "n", "s", "d", "t", "z"):
            if s.startswith(c):
                rest = s[len(c):]
                if len(rest) >= 3:
                    out.add(rest)
                break
    return out


def _compound_keys(pre, t, ctx=False):
    if pre is None:
        return _keys_for(t, ctx)
    base = set()
    for v in _tail_variants(t):
        base |= _keys_for(v, ctx)
    return set(pre + "|" + k for k in base)


def parse_org(name, vessel=False):
    toks = split_tokens(name)
    if vessel:
        while toks and toks[0] in VESSEL_PREFIX:
            toks.pop(0)
        return [t for t in toks if t]
    out = []
    for t in toks:
        if t in ("and",):
            continue
        if out and out[-1] in ("al", "el", "ul"):
            out[-1] = out[-1] + t          # "Al Noor" == "Al-Noor"
            continue
        out.append(t)
    while out and out[0] == "the":
        out.pop(0)
    # drop legal designators (multiword first)
    joined = " ".join(out)
    changed = True
    while changed:
        changed = False
        for lg in LEGAL:
            if " " in lg:
                if joined.endswith(" " + lg):
                    joined = joined[: -(len(lg) + 1)]
                    changed = True
                elif joined.startswith(lg + " "):
                    joined = joined[len(lg) + 1:]
                    changed = True
    out = [t for t in joined.split() if t]
    while out and out[-1] in LEGAL_SET:
        out.pop()
    while out and out[0] in LEGAL_SET and len(out) > 1:
        out.pop(0)
    return out


# --------------------------------------------------------------------------
# script handling
# --------------------------------------------------------------------------

AR_MAP = {
    "ا": "a", "أ": "a", "إ": "i", "آ": "aa", "ء": "", "ؤ": "u", "ئ": "i",
    "ب": "b", "پ": "p", "ت": "t", "ث": "th", "ج": "j", "چ": "ch", "ح": "h",
    "خ": "kh", "د": "d", "ذ": "dh", "ر": "r", "ز": "z", "ژ": "zh", "س": "s",
    "ش": "sh", "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "a", "غ": "gh",
    "ف": "f", "ق": "q", "ك": "k", "ک": "k", "گ": "g", "ل": "l", "م": "m",
    "ن": "n", "ه": "h", "ة": "a", "و": "w", "ی": "y", "ي": "y", "ى": "a",
    "ّ": "", "َ": "a", "ُ": "u", "ِ": "i", "ْ": "", "ً": "an", "ٌ": "un",
    "ٍ": "in", "ـ": "",
}

CY_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "і": "i", "ї": "yi", "є": "ye", "ґ": "g", "ў": "u",
}


def translit_script(tok):
    out = []
    for ch in tok.lower():
        if ch in CY_MAP:
            out.append(CY_MAP[ch])
        elif ch in AR_MAP:
            out.append(AR_MAP[ch])
        elif ch.isalnum():
            out.append(ch)
    return "".join(out)


AR_DIACRITICS = dict.fromkeys(
    [0x640] + list(range(0x64B, 0x653)) + [0x654, 0x655, 0x670], None)


def script_norm(tok):
    """Fold away arabic diacritics and the cyrillic yo, for lookups."""
    tok = tok.lower().translate(AR_DIACRITICS)
    return tok.replace("\u0451", "\u0435").replace("\u0439\u0439", "\u0439")


def merge_script_tokens(toks):
    out = []
    i = 0
    while i < len(toks):
        t = toks[i]
        if t in ("عبد", "نصر") and i + 1 < len(toks):
            out.append(t + " " + toks[i + 1])
            i += 2
        elif t.startswith("عبد") and len(t) > 3:
            out.append("عبد " + t[3:])      # written as one word
            i += 1
        elif t.startswith("نصر") and len(t) > 3:
            out.append("نصر " + t[3:])
            i += 1
        else:
            out.append(t)
            i += 1
    return out


class ScriptLex(object):
    """script token -> latin spelling, learnt from the watchlist itself."""

    def __init__(self):
        self.m = {}

    @staticmethod
    def _latin_units(pn):
        """Group a latin name the same way script names group (abd X)."""
        toks = pn.split()
        out = []
        i = 0
        while i < len(toks):
            t = fold(toks[i]).strip("-")
            if (t in COMPOUND_HEADS or (t.startswith("abd") and len(t) <= 5)) \
                    and i + 1 < len(toks):
                j = i + 1
                if fold(toks[j]).strip("-") in ARTICLES and j + 1 < len(toks):
                    j += 1
                out.append(" ".join(toks[i:j + 1]))
                i = j + 1
                continue
            if t == "nasr" and i + 1 < len(toks):
                out.append(" ".join(toks[i:i + 2]))
                i += 2
                continue
            out.append(toks[i])
            i += 1
        return out

    def learn(self, entries):
        votes = defaultdict(lambda: defaultdict(int))
        for e in entries:
            sn = e.get("script_name")
            pn = e.get("primary_name")
            if not sn or not pn or pn == sn or is_script(pn):
                continue
            a = self._latin_units(pn)
            b = merge_script_tokens(sn.split())
            if len(a) != len(b):
                continue
            for x, y in zip(b, a):
                votes[script_norm(x)][y.lower()] += 1
        for k, v in votes.items():
            self.m[k] = max(v.items(), key=lambda kv: kv[1])[0]

    def latin(self, script_name):
        """Convert a whole script name into a latin name string."""
        toks = merge_script_tokens(script_norm(script_name).split())
        out = []
        for t in toks:
            if t in self.m:
                out.append(self.m[t])
            elif " " in t:
                parts = t.split()
                head = parts[0]
                rest = " ".join(parts[1:])
                if head == "عبد":
                    tail = (self.m.get(rest) or self.m.get("ال" + rest)
                            or (rest.startswith("ال") and self.m.get(rest[2:]))
                            or translit_script(rest))
                    out.append("abdul " + tail)
                elif head == "نصر":
                    out.append("nasrallah")
                else:
                    out.append(translit_script(t.replace(" ", "")))
            else:
                # feminine cyrillic forms of a known masculine surname
                done = False
                if is_cyrillic(t) and t.endswith("а") and t[:-1] in self.m:
                    out.append(self.m[t[:-1]] + "a")
                    done = True
                if not done:
                    out.append(translit_script(t))
        return " ".join(out)


# --------------------------------------------------------------------------
# name matching
# --------------------------------------------------------------------------

def _demote(key):
    """Turn a key into its non word-initial form (first vowel class -> '.')."""
    for i, ch in enumerate(key):
        if ch in "AU":
            return key[:i] + "." + key[i + 1:]
    return key


def glue(ka, kb, cap=240):
    """Keys for two tokens written as one word (Smith Jones/Smith-Jones)."""
    out = set()
    for a in ka:
        if "|" in a:
            continue
        for b in kb:
            if "|" in b:
                continue
            out.add(a + _demote(b))
            if len(out) >= cap:
                return out
    return out


def _bipartite(cs, es):
    """Maximum matching size between two lists of key-sets (tiny lists)."""
    n, m = len(cs), len(es)
    if not n or not m:
        return 0
    adj = [[j for j in range(m) if cs[i] & es[j]] for i in range(n)]
    matchR = [-1] * m

    def try_k(i, seen):
        for j in adj[i]:
            if seen[j]:
                continue
            seen[j] = True
            if matchR[j] == -1 or try_k(matchR[j], seen):
                matchR[j] = i
                return True
        return False

    cnt = 0
    for i in range(n):
        if try_k(i, [False] * m):
            cnt += 1
    return cnt


def _merge_variants(keysets):
    """Yield alternative groupings where two tokens are glued together."""
    yield keysets
    n = len(keysets)
    if n < 2 or n > 4:
        return
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            glued = glue(keysets[i], keysets[j])
            if not glued:
                continue
            rest = [keysets[k] for k in range(n) if k not in (i, j)]
            yield rest + [glued]


def person_match(ctoks, etoks):
    """True when two parsed individual names refer to the same person."""
    ccore = [t.keys for t in ctoks if t.kind == "core"]
    ecore = [t.keys for t in etoks if t.kind == "core"]
    if len(ccore) < 2 or len(ecore) < 2:
        return False
    # patronymic / nasab consistency
    cp = [t.keys for t in ctoks if t.kind == "patro"]
    ep = [t.keys for t in etoks if t.kind == "patro"]
    if cp and ep and not any(a & b for a in cp for b in ep):
        return False
    cn = [t.keys for t in ctoks if t.kind == "nasab"]
    en = [t.keys for t in etoks if t.kind == "nasab"]
    if cn and en and not any(a & b for a in cn for b in en):
        return False
    # every mandatory element must line up, apart from at most one extra
    # middle element on one side; two elements have to match at all times
    # (a single shared given or family name is never a match)
    for cv in _merge_variants(ccore):
        for ev in _merge_variants(ecore):
            m = _bipartite(cv, ev)
            if m >= 2 and (len(cv) - m) + (len(ev) - m) <= 1:
                return True
    return False


def alias_equal(ctoks, etoks):
    """Strict equality used for weak aliases."""
    c = [t.keys for t in ctoks if t.kind in ("core", "nasab", "patro")]
    e = [t.keys for t in etoks if t.kind in ("core", "nasab", "patro")]
    if len(c) != len(e) or not c:
        return False
    return _bipartite(c, e) == len(c)


def org_match(cwords, ewords):
    """Entity / vessel names correspond word for word.

    Long words are also compared phonetically so that a transliterated
    element (Al-Hijaz / Al-Hidjaz) still lines up, while short ones
    (Shen, Chen, Zhao, Zhu, Dai) must match exactly.
    """
    if not cwords or not ewords:
        return False
    if len(cwords) != len(ewords):
        return False
    for a, b in zip(cwords, ewords):
        if a == b:
            continue
        if len(a) >= 6 and len(b) >= 6 and (token_keys(a) & token_keys(b)):
            continue
        return False
    return True


# --------------------------------------------------------------------------
# dates
# --------------------------------------------------------------------------

def parse_dob(s):
    s = (s or "").strip().replace("/", "-").replace(".", "-")
    if not s:
        return None
    m = re.match(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?$", s)
    if not m:
        m2 = re.match(r"^(\d{4})$", s[:4])
        if not m2:
            return None
        return (s[:4],)
    parts = [m.group(1)]
    if m.group(2):
        parts.append("%02d" % int(m.group(2)))
    if m.group(3):
        parts.append("%02d" % int(m.group(3)))
    return tuple(parts)


def dob_compatible(c, e):
    """(compatible, corroborated)"""
    if not c or not e:
        return True, False
    n = min(len(c), len(e))
    for i in range(n):
        if c[i] != e[i]:
            return False, False
    return True, True


# --------------------------------------------------------------------------
# entry preparation
# --------------------------------------------------------------------------

class Form(object):
    """One spelling of an entry: parsed person tokens or org words."""

    __slots__ = ("toks", "words")

    def __init__(self, toks, words):
        self.toks = toks
        self.words = words


class Entry(object):
    __slots__ = ("uid", "type", "dob", "forms", "weak", "ids", "weakforms",
                 "cyr")

    def __init__(self, uid, typ, dob):
        self.uid = uid
        self.type = typ
        self.dob = dob
        self.forms = []
        self.weak = []
        self.weakforms = []
        self.ids = []
        self.cyr = False


def build_entries(raw, lex):
    entries = []
    for e in raw:
        typ = norm_type(e.get("type"))
        ent = Entry(e["uid"], typ, parse_dob(e.get("dob")))
        cyr = is_cyrillic(e.get("script_name") or "")
        ent.cyr = cyr
        names = []
        pn = e.get("primary_name") or ""
        sn = e.get("script_name") or ""
        if pn:
            names.append(pn)
        if sn:
            names.append(lex.latin(sn))
        for a in e.get("aliases") or []:
            nm = a.get("name") or ""
            if not nm:
                continue
            if is_script(nm):
                nm = lex.latin(nm)
            if (a.get("strength") or "strong").lower() == "weak":
                ent.weak.append(nm)
            else:
                names.append(nm)
        seen = set()
        for nm in names:
            if is_script(nm):
                nm = lex.latin(nm)
            key = fold(nm)
            if key in seen:
                continue
            seen.add(key)
            if typ == "individual":
                ent.forms.append(Form(parse_person(nm, cyr), None))
            else:
                ent.forms.append(Form(None, parse_org(nm, typ == "vessel")))
        ent.weakforms = [parse_person(n, cyr) if typ == "individual" else None
                         for n in ent.weak]
        for i in e.get("ids") or []:
            t = norm_idtype(i.get("type"))
            num = re.sub(r"[^A-Z0-9]", "", (i.get("number") or "").upper())
            if num:
                ent.ids.append((t, num))
        entries.append(ent)
    return entries


# --------------------------------------------------------------------------
# main screening
# --------------------------------------------------------------------------

def build_index(entries):
    idx = defaultdict(set)
    for ent in entries:
        for f in ent.forms:
            if f.toks is not None:
                units = []
                for t in f.toks:
                    if t.kind in ("core", "nasab"):
                        units.append(t.keys)
                allk = set()
                for u in units:
                    allk |= u
                # glued pairs (hyphenated surnames written apart)
                core = [t.keys for t in f.toks if t.kind == "core"]
                if 2 <= len(core) <= 4:
                    for i in range(len(core)):
                        for j in range(len(core)):
                            if i != j:
                                allk |= glue(core[i], core[j], 120)
                for k in allk:
                    idx[k].add(ent.uid)
            else:
                for w in f.words:
                    idx["W:" + w].add(ent.uid)
                    if len(w) >= 6:
                        for k in token_keys(w):
                            idx["P:" + k].add(ent.uid)
    return idx


def weak_index(entries):
    idx = defaultdict(set)
    for ent in entries:
        for ftoks in ent.weakforms:
            if not ftoks:
                continue
            for t in ftoks:
                for k in t.keys:
                    idx[k].add(ent.uid)
    return idx


def id_index(entries):
    idx = defaultdict(set)
    for ent in entries:
        for t, num in ent.ids:
            idx[(t, num)].add(ent.uid)
            idx[(None, num)].add(ent.uid)
    return idx


TYPE_ALIASES = {
    "individual": "individual", "person": "individual", "natural person":
    "individual", "individuals": "individual", "ind": "individual",
    "entity": "entity", "company": "entity", "organisation": "entity",
    "organization": "entity", "corporate": "entity", "org": "entity",
    "business": "entity", "legal entity": "entity",
    "vessel": "vessel", "ship": "vessel", "boat": "vessel",
    "aircraft": "vessel",
}


ID_ALIASES = {"passportnumber": "passport", "passportno": "passport",
              "passportnr": "passport", "pass": "passport",
              "registrationnumber": "registration", "reg": "registration",
              "registrationno": "registration", "companyregistration":
              "registration", "imonumber": "imo", "imono": "imo",
              "imnumber": "imo", "nationalid": "national id"}


def norm_idtype(t):
    t = re.sub(r"[^a-z]", "", (t or "").lower())
    return ID_ALIASES.get(t, t)


def norm_type(t):
    t = (t or "").strip().lower()
    return TYPE_ALIASES.get(t, t or "individual")


def screen(customers, entries, lex):
    by_uid = {e.uid: e for e in entries}
    idx = build_index(entries)
    widx = weak_index(entries)
    iidx = id_index(entries)
    results = []
    for c in customers:
        cid = c.get("customer_id") or ""
        name = (c.get("full_name") or "").strip()
        typ = norm_type(c.get("type"))
        dob = parse_dob(c.get("dob"))
        idt = norm_idtype(c.get("id_type"))
        idn = re.sub(r"[^A-Z0-9]", "", (c.get("id_number") or "").upper())
        decision = "NO_MATCH"
        uid = ""
        # ---- rule 1: identifiers ------------------------------------
        if idn:
            hits = iidx.get((idt, idn)) if idt else None
            if not hits:
                hits = iidx.get((None, idn))
            if hits:
                uid = sorted(hits)[0]
                results.append((cid, "MATCH", uid))
                continue
        # ---- rule 2/5: names ----------------------------------------
        if is_script(name):
            name = lex.latin(name)
        cands = set()
        if typ == "individual":
            ctoks = parse_person(name, True)
            ctoks_n = parse_person(name, False)
            units = [t.keys for t in ctoks if t.kind in ("core", "nasab")]
            core = [t.keys for t in ctoks if t.kind == "core"]
            keysets = list(units)
            if 2 <= len(core) <= 4:
                glued = set()
                for i in range(len(core)):
                    for j in range(len(core)):
                        if i != j:
                            glued |= glue(core[i], core[j], 120)
                if glued:
                    keysets.append(glued)
            hit = defaultdict(int)
            for ks in keysets:
                seen = set()
                for k in ks:
                    for u in idx.get(k, ()):
                        seen.add(u)
                for u in seen:
                    hit[u] += 1
            cands = {u for u, n in hit.items() if n >= 2}
        else:
            words = parse_org(name, typ == "vessel")
            if words:
                sets = []
                for w in words:
                    s = set(idx.get("W:" + w, ()))
                    if len(w) >= 6:
                        for k in token_keys(w):
                            s |= idx.get("P:" + k, set())
                    sets.append(s)
                cands = set.intersection(*sets) if sets else set()
        # evaluate candidates
        strong_hits = []
        for u in cands:
            ent = by_uid[u]
            if ent.type != typ:
                continue
            ok = False
            for f in ent.forms:
                if typ == "individual":
                    # cyrillic-only readings may only reach a cyrillic entry
                    if person_match(ctoks if ent.cyr else ctoks_n, f.toks):
                        ok = True
                        break
                elif org_match(words, f.words):
                    ok = True
                    break
            if not ok:
                continue
            comp, corr = dob_compatible(dob, ent.dob)
            if not comp:
                continue
            strong_hits.append((0 if corr else 1, u))
        # ---- rule 3: weak aliases -----------------------------------
        if not strong_hits and typ == "individual" and dob and len(dob) == 3:
            hit = defaultdict(int)
            for t in ctoks:
                if t.kind not in ("core", "nasab"):
                    continue
                seen = set()
                for k in t.keys:
                    for u in widx.get(k, ()):
                        seen.add(u)
                for u in seen:
                    hit[u] += 1
            for u, n in hit.items():
                ent = by_uid[u]
                if ent.type != typ or not ent.dob or len(ent.dob) != 3:
                    continue
                if ent.dob != dob:
                    continue
                for wf in ent.weakforms:
                    if wf and alias_equal(ctoks if ent.cyr else ctoks_n, wf):
                        strong_hits.append((0, u))
                        break
        if strong_hits:
            strong_hits.sort(key=lambda x: (x[0], x[1]))
            decision = "MATCH"
            uid = strong_hits[0][1]
        results.append((cid, decision, uid))
    return results


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--watchlist", required=True)
    ap.add_argument("--customers", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    with open(args.watchlist, "r", encoding="utf-8-sig") as fh:
        raw = json.load(fh)
    lex = ScriptLex()
    lex.learn(raw)
    entries = build_entries(raw, lex)
    with open(args.customers, "r", encoding="utf-8-sig",
              newline="") as fh:
        customers = list(csv.DictReader(fh))
    rows = screen(customers, entries, lex)
    with open(args.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["customer_id", "decision", "matched_uid"])
        for r in rows:
            w.writerow(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
