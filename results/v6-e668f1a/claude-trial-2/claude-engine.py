#!/usr/bin/env python3
"""Sanctions screening engine.

Decides, for every customer record, whether it matches a watchlist entry under
the rules of screening_policy.md:

  * romanization of Arabic, Persian and Cyrillic names under any common
    convention (English, French, German, Turkish, Indonesian/Malay, Polish,
    scientific-with-diacritics-dropped, Gulf, sun-letter assimilation, ...)
  * name order, Arabic nasab elements, the Arabic article, Russian patronymics,
    feminine Russian surnames, compound/hyphenated surnames, particles
  * western nicknames and diacritic variants
  * strong aliases (full participants) and weak aliases (need corroboration)
  * company legal-form designators and vessel prefixes
  * date-of-birth and identifier rules

How it works
------------
Every name token is reduced to a *spelling skeleton*: consonants are folded
into phoneme classes per language family (so sh/sch/sz/cz/ch/s all collapse for
Cyrillic names, gh/q/k/c for Arabic ones) while vowels keep their position and
a coarse front/back class, which is what separates Hassan from Hussein or Omar
from Amir.  Graphemes that two conventions read differently (j, c, ch, x, bare
s, g) produce several alternative skeletons, so a name matches if any reading
agrees.  A curated table adds the irregular equivalences that no rule derives
(nicknames, Turkish Mehmet/Muhammad, Indonesian Joesoef/Yusuf, anglicisations),
one-directionally so a variant spelling can never merge two distinct names.

A name is parsed into slots - given, family, patronymic, nasab father, initials
- and two names correspond when every required slot on each side finds a
distinct partner on the other, which makes matching insensitive to name order
while still rejecting a name that carries an extra or different element.
Entries written only in Arabic, Persian or Cyrillic script are romanized with a
dictionary mined from the watchlist itself at run time, backed by a
character-level transliterator that enumerates the unwritten short vowels.

Standard library only.
"""

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict

# ---------------------------------------------------------------------------
# folding
# ---------------------------------------------------------------------------

_SPECIAL_FOLD = {
    "ß": "ss", "æ": "ae", "œ": "oe", "ø": "o", "å": "a", "đ": "d",
    "ł": "l", "þ": "th", "ð": "d", "ı": "i", "ʹ": "", "ʺ": "",
    "’": "", "‘": "", "ʿ": "", "ʾ": "", "'": "", "`": "", "´": "",
}


def fold(text):
    out = []
    for ch in text:
        low = ch.lower()
        out.append(_SPECIAL_FOLD.get(low, low))
    s = unicodedata.normalize("NFD", "".join(out))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s


def has_latin(text):
    return bool(re.search(r"[A-Za-z]", text))


def is_cyrillic(text):
    return bool(re.search(r"[Ѐ-ӿ]", text))


def is_arabic(text):
    return bool(re.search(r"[؀-ۿ]", text))


# ---------------------------------------------------------------------------
# script transliteration
# ---------------------------------------------------------------------------

CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "і": "i", "ї": "yi", "є": "ye", "ґ": "g", "ў": "u", "ђ": "d", "џ": "dzh",
}

AR_MAP = {
    "ب": ("b",), "پ": ("p",), "ت": ("t",), "ث": ("th",), "ج": ("j",),
    "چ": ("ch",), "ح": ("h",), "خ": ("kh",), "د": ("d",), "ذ": ("dh",),
    "ر": ("r",), "ز": ("z",), "ژ": ("zh",), "س": ("s",), "ش": ("sh",),
    "ص": ("s",), "ض": ("d",), "ط": ("t",), "ظ": ("z",), "غ": ("gh",),
    "ف": ("f",), "ق": ("q",), "ک": ("k",), "ك": ("k",), "گ": ("g",),
    "ل": ("l",), "م": ("m",), "ن": ("n",), "ه": ("h", "a"), "ة": ("a",),
    "ھ": ("h",), "ی": ("i", "y"), "ي": ("i", "y"), "و": ("u", "w"),
    "ا": ("a",), "آ": ("a",), "ى": ("a",), "ء": ("", "a"), "أ": ("a",),
    "إ": ("a",), "ؤ": ("u", "w"), "ئ": ("i", "y"), "ع": ("a", ""),
    "ـ": ("",), "ً": ("an",), "ٌ": ("",), "ٍ": ("",), "َ": ("a",),
    "ُ": ("u",), "ِ": ("i",), "ّ": ("",), "ْ": ("",), "ٰ": ("a",),
}

def translit_cyr(word):
    return "".join(CYR.get(c, c if c.isascii() else "") for c in fold(word))


def translit_arab(word):
    """Plausible latin spellings of an arabic/persian-script token.

    Short vowels are not written, so every consonant-consonant junction gets
    an optional short vowel.  The canonical reading comes first.
    """
    units = [AR_MAP[ch] for ch in word if ch in AR_MAP]
    if not units:
        return []
    forms = [[]]
    for alts in units:
        nxt = []
        for a in alts:
            for f in forms:
                nxt.append(f + [a])
        forms = nxt
        if len(forms) > 24:
            forms = forms[:24]
    out = []
    seen = set()
    for f in forms:
        for cand in _vowelize_units(f):
            if cand and cand not in seen:
                seen.add(cand)
                out.append(cand)
    return out


def _vowelize_units(units, cap=300):
    """Insert optional short vowels between consonant units."""
    slots = []
    for i in range(1, len(units)):
        prev, cur = units[i - 1], units[i]
        if not prev or not cur:
            continue
        if prev[-1] in "aeiou" or cur[0] in "aeiou":
            continue
        slots.append(i)
    results = [units]
    for pos in reversed(slots):
        nxt = []
        for r in results:
            nxt.append(r)
            nxt.append(r[:pos] + ["a"] + r[pos:])
            nxt.append(r[:pos] + ["u"] + r[pos:])
        results = nxt
        if len(results) > cap:
            results = results[:cap]
    return ["".join(r) for r in results]


# ---------------------------------------------------------------------------
# skeletons
# ---------------------------------------------------------------------------

MODE_SEM = "sem"
MODE_RU = "ru"
MODE_WEST = "west"
MODES = (MODE_SEM, MODE_RU, MODE_WEST)

VOW = set("aeiouy")

# consonant graphemes -> skeleton symbol, longest first, per mode
TAB = {
    MODE_SEM: [
        ("shch", "S"), ("dsch", "J"), ("tsch", "S"), ("dzh", "J"),
        ("sch", "S"), ("sh", "S"), ("sj", "S"), ("tch", "S"),
        ("ch", "S"), ("cz", "S"), ("sz", "S"), ("zh", "J"), ("dj", "J"),
        ("kh", "h"), ("gh", "k"), ("ph", "v"), ("th", "t"), ("dh", "d"),
        ("ck", "k"), ("x", "ks"), ("q", "k"), ("g", "k"), ("c", "k"),
        ("w", "v"), ("f", "v"), ("v", "v"), ("z", "z"), ("s", "s"),
        ("j", "J"),
    ],
    MODE_RU: [
        ("shch", "S"), ("stsch", "S"), ("chtch", "S"), ("szcz", "S"),
        ("sch", "S"), ("tsch", "S"), ("tch", "S"), ("sh", "S"), ("ch", "S"),
        ("cz", "S"), ("sz", "S"), ("zh", "S"), ("ts", "S"), ("tz", "S"),
        ("sc", "S"), ("kh", "h"), ("gh", "g"), ("ph", "v"), ("th", "t"),
        ("ck", "k"), ("q", "k"), ("c", "S"),
        ("w", "v"), ("f", "v"), ("v", "v"), ("z", "S"), ("s", "S"),
        ("j", "S"),
    ],
    MODE_WEST: [
        ("sch", "S"), ("sh", "S"), ("ch", "S"), ("zh", "S"), ("kh", "h"),
        ("gh", "g"), ("ph", "v"), ("th", "t"), ("ck", "k"),
        ("q", "k"), ("c", "k"), ("w", "v"), ("f", "v"),
        ("v", "v"), ("z", "s"), ("s", "s"), ("j", "J"),
    ],
}


_GLIDES = {MODE_SEM: "yj", MODE_RU: "yji", MODE_WEST: "yi"}


def _vowel_unit(cluster, mode):
    """Map a vowel cluster to an optional glide plus a vowel class."""
    c = cluster
    keep = ""
    glides = _GLIDES[mode]
    had = False
    while len(c) > 1 and c[0] in glides:
        c = c[1:]
        had = True
    if had:
        if mode == MODE_RU and c[0] == "o" and not c.startswith(("ou", "oo")):
            return "", "A"          # cyrillic yo, alternates with e
        if mode == MODE_SEM or (mode == MODE_RU and c[0] in "aou"):
            keep = "y"
    if mode == MODE_WEST:
        first = c[0]
        if first == "y":
            first = "i"
        if first in "ou" and c.startswith(("ou", "oo")):
            first = "o"
        return keep, first.upper()
    if c[0] in "ou":
        return keep, "O"
    if c[0] == "e" and "o" in c:
        return keep, "A"
    if c[0] == "a" and "u" in c:
        return keep, "O"
    return keep, "A"


def _scan(word, mode):
    tab = TAB[mode]
    out = []
    i, n = 0, len(word)
    while i < n:
        if word[i] in VOW:
            j = i
            while j < n and word[j] in VOW:
                j += 1
            g, cls = _vowel_unit(word[i:j], mode)
            out.append(g + cls)
            i = j
            continue
        for g, sym in tab:
            if word.startswith(g, i):
                out.append(sym)
                i += len(g)
                break
        else:
            out.append(word[i])
            i += 1
    s = "".join(out)
    return re.sub(r"(.)\1+", r"\1", s)


def _spelling_variants(w, mode):
    """Ordered list of spelling variants for one token.

    Everything here is deterministic: the result depends only on the input
    string, never on set iteration order.
    """
    w = re.sub(r"([^aeiouy])\1+", r"\1", w)     # doubled consonants only
    w = w.replace("qu", "kv")
    if "x" in w:
        if mode == MODE_RU:
            res = [w.replace("x", "ks"), w.replace("x", "kh")]
        else:
            res = [w.replace("x", "ks")]
    else:
        res = [w]
    if mode == MODE_SEM:
        base = []
        for v in res:
            v = re.sub(r"gu([ei])", r"g\1", v)
            v = re.sub(r"ou([aeiou])", r"w\1", v)
            v = re.sub(r"^oe", "u", v)
            v = v.replace("oe", "u")
            v = v.replace("sy", "sh").replace("tj", "ch")
            base.append(v)
        res = base
        # j  : arabic jim  /  indonesian y-glide
        res = _expand(res, r"j", ["j", "y"])
        # ch : sh (french, english)  /  kh (german, indonesian)
        res = _expand(res, r"ch", ["ch", "kh"])
        # c  : k  /  turkish j
        res = _expand(res, r"c(?!h)", ["k", "j"])
        # a bare s may be a turkish s-cedilla (= sh)
        res = _expand(res, r"s(?![hjy])", ["s", "sh"], cap=8)
        extra = []
        for v in res:                       # trailing epenthetic -e / -h
            cur = v
            dropped_e = dropped_h = False
            for _ in range(2):
                if len(cur) > 3 and cur.endswith("e") and not dropped_e:
                    cur = cur[:-1]
                    dropped_e = True
                    extra.append(cur)
                elif (len(cur) > 3 and cur.endswith("h") and cur[-2] in VOW
                        and not dropped_h):
                    cur = cur[:-1]
                    dropped_h = True
                    extra.append(cur)
                else:
                    break
        res = res + extra
        res = res + [v[:-1] + "d" for v in res if v.endswith("t")]
    elif mode == MODE_RU:
        base = []
        for v in res:
            v = re.sub(r"gu([ei])", r"g\1", v)
            v = re.sub(r"(sk|ck|zk)(aya|aja|aia)$", r"\1y", v)
            base.append(v)
        res = base
        res = _expand(res, r"j", ["zh", "y"])
        res = _expand(res, r"(?:stsch|chtch|tsch|shch|sch|tch|ch)",
                      ["ch", "kh"], cap=8)
        res = _expand(res, r"c(?![hz])", ["ts", "k"])
        res = _expand(res, r"g(?![hu])", ["g", "kh"], cap=8)
    else:
        base = []
        for v in res:
            v = re.sub(r"^mac(?=[bcdfgklmnprstvwz])", "mc", v)
            v = re.sub(r"(sson|sen|son|zon|zen)$", "sn", v)
            v = re.sub(r"(dt|tt|th)$", "t", v)
            if len(v) > 3 and v.endswith("e") and v[-2] not in VOW:
                v = v[:-1]
            base.append(v)
        res = base
        res = _expand(res, r"ch", ["ch", "k"])
        res = _expand(res, r"c(?![hk])", ["k", "s"])
    out = []
    seen = set()
    for v in res:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _expand(forms, pattern, repls, cap=16):
    """Replace every occurrence of pattern by each replacement (all combos).

    Deterministic: inputs are visited in sorted order and every truncation
    keeps a fixed prefix, so the result never depends on set iteration order.
    """
    rx = re.compile(pattern)
    out = []
    seen = set()
    for f in sorted(forms):
        parts = rx.split(f)
        hits = rx.findall(f)
        if not hits:
            cur = [f]
        else:
            cur = [parts[0]]
            for idx, _h in enumerate(hits):
                nxt = []
                for c in cur:
                    for r in repls:
                        nxt.append(c + r + parts[idx + 1])
                cur = nxt
                if len(cur) > cap:
                    cur = cur[:cap]
        for c in cur:
            if c not in seen:
                seen.add(c)
                out.append(c)
        if len(out) >= 96:
            break
    return out[:96]


_skel_cache = {}


def skeletons(token, mode):
    key = (token, mode)
    hit = _skel_cache.get(key)
    if hit is not None:
        return hit
    w = re.sub(r"[^a-z]", "", fold(token))
    if not w:
        res = frozenset()
    else:
        out = set()
        for v in _spelling_variants(w, mode):
            s = _scan(v, mode)
            if s:
                out.add(s)
                if mode == MODE_RU and len(s) >= 5:
                    t = re.sub(r"[AO]+$", "", s)
                    if len(t) >= 4:
                        out.add(t)
        res = frozenset(out)
    _skel_cache[key] = res
    return res


# ---------------------------------------------------------------------------
# synonym groups (nicknames, anglicisations, irregular conventions)
# ---------------------------------------------------------------------------

# Each group: first element is the canonical head, the rest are variants.
# Expansion is one-directional (variant -> head) so that a variant spelling
# that happens to coincide with another canonical name cannot merge the two.

WEST_GROUPS = [
    ["alexander", "alex", "sasha", "alejandro", "alessandro",
     "alexandre", "aleksander", "sander"],
    ["andrew", "drew", "andy", "andre", "andres", "andreas", "andrea",
     "andrei", "anders"],
    ["anthony", "tony", "antonio", "antoine", "anton", "antonius"],
    ["barbara", "barb", "babs", "barbie", "barbro"],
    ["benjamin", "ben", "benny", "benji", "benito"],
    ["katherine", "catherine", "kate", "kathy", "cathy", "katie", "kat",
     "kitty", "katarina", "catalina", "caterina", "katrin", "kathryn",
     "ekaterina", "katja", "katya"],
    ["charles", "chuck", "charlie", "chas", "carlos", "carlo", "karl",
     "carl", "charlot"],
    ["christopher", "chris", "kit", "topher", "cristobal", "christoph",
     "cristoforo", "christophe"],
    ["daniel", "danny", "dan", "dani", "daniele", "danilo"],
    ["dorothy", "dot", "dottie", "dolly", "dora", "dorothea", "dorotea"],
    ["edward", "ed", "ted", "eddie", "teddy", "ned", "eduardo", "edouard",
     "eduard"],
    ["elizabeth", "elisabeth", "liz", "beth", "betty", "betsy", "eliza",
     "libby", "lizzie", "elsie", "isabel", "isabella", "elisa", "elise",
     "elisabetta", "yelizaveta", "elizaveta"],
    ["francisco", "francis", "frank", "fran", "paco", "pancho", "cisco",
     "frankie", "francois", "franz", "francesco", "franco"],
    ["frederick", "fred", "freddie", "freddy", "fritz", "federico",
     "frederic", "friedrich", "fredrik"],
    ["henry", "hank", "harry", "hal", "enrique", "enrico", "henri",
     "heinrich", "henrique"],
    ["james", "jim", "jimmy", "jamie", "jimmie", "jaime", "giacomo",
     "jacques", "diego", "santiago", "tiago", "jakob", "jacob"],
    ["jennifer", "jen", "jenny", "jenn", "jennie", "jenifer"],
    ["john", "johnny", "jon", "jack", "jackie", "johnnie", "juan",
     "johann", "giovanni", "ivan", "hans"],
    ["joseph", "joe", "joey", "jos", "jose", "giuseppe", "josef", "pepe"],
    ["margaret", "maggie", "peggy", "meg", "marge", "margie", "greta",
     "margarita", "margarete", "margherita"],
    ["matthew", "matt", "matty", "mateo", "matteo", "mathieu", "matthias",
     "mateus"],
    ["michael", "mike", "mikey", "mick", "micky", "mickey", "miguel",
     "michel", "michele", "mikhail"],
    ["nicholas", "nick", "nicky", "nicolas", "klaus", "nikolaus", "niccolo",
     "nicolau", "nikolai"],
    ["patricia", "patty", "trish", "tricia", "patsy", "patrizia"],
    ["peter", "pete", "pedro", "pierre", "pietro", "pyotr", "petr",
     "peder", "piotr", "petrus"],
    ["rebecca", "becca", "becky", "beck", "reba", "rebekah"],
    ["richard", "rick", "dick", "richie", "rich", "ricky", "ricardo",
     "riccardo"],
    ["robert", "rob", "bob", "bobby", "robbie", "roberto", "rupert"],
    ["samuel", "sam", "sammy", "samu"],
    ["steven", "stephen", "steve", "stevie", "esteban", "etienne", "stefan",
     "stefano", "stephan", "estevao"],
    ["susan", "sue", "suzy", "susie", "suzie", "suzanne", "susanna"],
    ["theodore", "theo", "teodoro", "theodor"],
    ["thomas", "tom", "tommy", "thom", "tomas", "tommaso"],
    ["victoria", "vicky", "tori", "vickie", "viktoria", "vittoria"],
    ["william", "bill", "will", "billy", "willie", "willy", "liam",
     "guillermo", "guillaume", "wilhelm", "guglielmo", "vilhelm"],
    ["donald", "don", "donny"],
    ["george", "georgie", "jorge", "georges", "georg", "giorgio", "yuri"],
    ["david", "dave", "davey", "davide"],
    ["lawrence", "larry", "laurence", "lorenzo", "laurent"],
    ["ronald", "ron", "ronnie"],
    ["kenneth", "ken", "kenny"],
    ["walter", "walt"],
    ["raymond", "ray", "raimundo", "ramon"],
    ["philip", "phillip", "felipe", "philippe", "filippo"],
    ["gregory", "greg", "gregorio", "grigory"],
    ["vincent", "vince", "vincenzo", "vicente"],
    ["eugene", "gene", "yevgeny", "evgeny", "eugenio"],
    ["albert", "bert", "alberto"],
    ["alfred", "alf"],
    ["arthur", "art", "arturo"],
    ["harold"],
    ["howard", "howie"],
    ["jeffrey", "jeff", "geoffrey"],
    ["leonard", "leo", "len", "lenny", "leonardo", "leonid"],
    ["martin", "marty", "martino"],
    ["timothy", "tim", "timmy"],
    ["paul", "pablo", "paolo", "paulo", "pawel", "pavel"],
    ["louis", "luis", "luigi", "ludwig", "lewis"],
    ["mark", "marc", "marco", "marcos", "marcus"],
    ["simon", "simone"],
    ["stanley", "stan"],
    ["maria", "mary", "marie", "mariya", "marya", "mara"],
    ["anna", "anne", "ann", "annie", "anita"],
    ["helen", "helena", "nell", "elena", "yelena"],
    ["natalia", "natalie", "natalya", "nathalie"],
    ["irina", "irene", "irena"],
    ["sofia", "sophia", "sofya", "sophie"],
    ["deborah", "debbie", "deb"],
    ["kimberly", "kim"],
    ["pamela", "pam"],
    ["sandra", "sandy"],
    ["teresa", "terry", "theresa", "tess"],
    ["angela", "angie", "angelina"],
    ["caroline", "carolyn", "carol", "carolina"],
    ["janet"],
    ["judith", "judy"],
    ["laura", "laurie"],
    ["linda", "lindy"],
    ["nancy", "nan"],
    ["sarah", "sally", "sadie", "sara"],
    ["valentina", "valentine"],
    # western surnames
    ["petersen", "pedersen", "peterson", "pederson"],
    ["schmidt", "schmid", "schmitt", "schmitz"],
    ["mueller", "muller", "moller", "mueler"],
    ["meyer", "meier", "mayer", "maier"],
    ["fischer", "fisher"],
    ["weiss", "weis"],
    ["lindqvist", "lindquist", "lindkvist"],
    ["nowak", "novak"],
    ["schroeder", "schroder", "schrader"],
    ["macdonald", "mcdonald", "mcdonnell"],
    ["fernandez", "fernandes"],
    ["rodriguez", "rodrigues"],
    ["ferreira", "ferreyra"],
    ["hernandez", "hernandes"],
    ["gonzalez", "gonzales"],
    ["johansson", "johanson", "johansen", "johnson"],
    ["andersson", "anderson", "andersen"],
    ["larsson", "larson", "larsen"],
    ["olsson", "olson", "olsen"],
    ["sorensen", "sorenson", "sorense"],
    ["kowalski", "kowalsky"],
    ["bianchi", "bianci"],
    ["lefevre", "fevre", "lefebvre"],
    ["dubois", "bois"],
    ["delacruz", "cruz"],
    ["silva", "dasilva"],
]

RU_GROUPS = [
    # cross-language equivalents and spelling variants only; russian
    # diminutives are deliberately absent (the lists carry nicknames as weak
    # aliases, never as name variants)
    ["yevgeny", "evgeny", "eugene", "evgeni", "jewgenij", "evgueni"],
    ["aleksandr", "alexander", "alexandr", "aleksander", "alessandro"],
    ["mikhail", "michael", "mihail", "michel"],
    ["nikolai", "nicholas", "nikolay", "nicolai", "nikolaus"],
    ["pyotr", "peter", "petr", "piotr", "pierre"],
    ["ekaterina", "catherine", "yekaterina", "katherine"],
    ["yelizaveta", "elizabeth", "elizaveta", "elisabeth"],
    ["ivan", "john", "johann"],
    ["pavel", "paul", "pawel"],
    ["georgy", "george", "georgi", "georges"],
    ["vasily", "basil", "vasili", "wassily"],
    ["iosif", "joseph", "josef"],
    ["natalia", "natalie", "natalya", "nathalie"],
    ["irina", "irene", "irena"],
    ["sofia", "sophia", "sofya"],
    ["stepan", "stephen", "stefan"],
    ["fyodor", "theodore", "fedor", "theodor"],
    ["andrei", "andrew", "andreas"],
    ["grigory", "gregory", "gregor"],
    ["anton", "anthony", "antonio"],
    ["daniil", "daniel"],
    ["timofey", "timothy"],
    ["yakov", "jacob"],
    ["maria", "mary", "marie"],
    ["anna", "anne", "ann"],
    ["konstantin", "constantine"],
    ["vladimir", "waldemar"],
    ["viktor", "victor"],
    ["valentina", "valentine"],
    ["nadezhda", "nadine"],
    ["olga", "helga"],
    ["oksana", "roxana"],
    ["zhanna", "joan"],
    ["semyon", "simon", "semen"],
    ["yulia", "julia", "julie"],
    ["elena", "helen", "yelena"],
    ["tatiana", "tatyana"],
    ["denis", "dennis"],
    ["roman", "romain"],
    ["maksim", "maxim", "maximilian"],
    ["leonid", "leonidas"],
    ["arkady", "arcadius"],
    ["lyudmila", "ludmilla"],
    ["svetlana", "svjetlana"],
    ["ruslan", "rouslan"],
    ["stanislav", "stanislaus"],
    ["vyacheslav", "viatcheslav"],
    ["valery", "valeri"],
    ["kseniya", "ksenia"],
    ["darya", "daria"],
    ["viktoria", "victoria"],
    ["galina", "halina"],
    ["artyom", "artem"],
    ["anastasia", "anastasiya"],
    ["yuri", "yury", "youri"],
    ["boris", "borys"],
    ["igor", "ihor"],
    ["oleg", "olek"],
    ["timur", "timour"],
    ["marina", "maryna"],
    # ukrainian / belarusian forms of the same names
    ["aleksei", "oleksiy", "oleksii", "alexey"],
    ["aleksandr", "oleksandr"],
    ["mikhail", "mykhailo", "mikhas"],
    ["vladimir", "volodymyr"],
    ["sergei", "serhiy", "siarhei"],
    ["dmitri", "dmytro"],
    ["yevgeny", "yevhen"],
    ["pyotr", "petro"],
    ["pavel", "pavlo"],
    ["grigory", "hryhoriy"],
    ["nikolai", "mykola"],
    ["vasily", "vasyl"],
    ["irina", "iryna"],
    ["elena", "olena"],
    ["ekaterina", "kateryna"],
    ["tatiana", "tetyana"],
    ["svetlana", "svitlana"],
    ["galina", "halyna"],
    ["nadezhda", "nadiya"],
    ["olga", "olha"],
    ["yulia", "yuliya"],
    ["maria", "mariya"],
    ["anastasia", "anastasiia"],
    ["oleg", "oleh"],
    ["igor", "ihor"],
    ["timofey", "tymofiy"],
    ["anatoly", "anatoliy"],
    ["valery", "valeriy"],
    ["yuri", "yuriy"],
]

SEM_GROUPS = [
    ["muhammad", "mehmet", "mohammed", "mahomet", "mohd", "muhamed",
     "mahammad", "mohamad"],
    ["ahmad", "ahmet", "achmad", "achmed", "ahmed"],
    ["mahmoud", "mahmut", "machmud", "mahmood"],
    ["hussein", "huseyin", "husein", "hoesein", "husayn", "hossein"],
    ["hassan", "hasan", "hassane"],
    ["qasim", "kasim", "kassim", "gasim", "qassim"],
    ["kamal", "kemal", "kamil", "kemel"],
    ["khalid", "halit", "halid", "chalid", "khaled"],
    ["tariq", "tarik", "tarek", "tariw"],
    ["omar", "omer", "umar", "oemar", "ömer"],
    ["yusuf", "yusof", "joesoef", "jusuf", "youssef", "yousif", "yousuf",
     "yoesoef"],
    ["ibrahim", "ibrahem", "brahim", "ibragim"],
    ["ismail", "ismayil", "ismael", "esmail", "ismaeel"],
    ["mustafa", "mustapha", "moestafa", "mostafa"],
    ["fatima", "fatma", "fatimah", "fatemeh", "fatme"],
    ["aisha", "ayse", "aysha", "aisyah", "aischa", "ayesha"],
    ["zainab", "zeynep", "zeinab", "zainap"],
    ["salim", "selim", "saleem", "salem"],
    ["saeed", "said", "sayeed", "seyit", "saeid"],
    ["jafar", "cafer", "djafar"],
    ["bakr", "bekir", "baker", "bakir"],
    ["amin", "emin", "ameen"],
    ["nour", "nur", "noer", "noor"],
    ["sharif", "syarif", "sjarif", "serif"],
    ["reza", "riza", "rida"],
    ["masoud", "mesut", "masud", "massoud"],
    ["farhad", "ferhat", "farhat"],
    ["golnaz", "gulnaz"],
    ["shirin", "sirin", "shereen"],
    ["javad", "cevat", "javed", "jawad"],
    ["mahdi", "mehdi", "mahdy"],
    ["yassin", "yasin", "jasin", "yaseen"],
    ["dariush", "daryush", "dariyus", "darius"],
    ["parviz", "perviz"],
    ["marwan", "mervan", "marouan"],
    ["walid", "velid", "oualid", "waleed"],
    ["hamza", "hamzah", "hamze"],
    ["anwar", "anvar", "enver", "anouar"],
    ["adnan", "adnen"],
    ["majid", "mecit", "madjid", "majeed"],
    ["karim", "kerim", "carim", "kareem"],
    ["rashid", "rasid", "rashed", "rasheed"],
    ["bilal", "belal"],
    ["hisham", "hicham", "hesham"],
    ["nizar", "nezar"],
    ["faisal", "faysal", "feysal", "fayssal"],
    ["ramin", "remin"],
    ["mohsen", "muhsin", "mohsin"],
    ["morteza", "mortaza", "murtaza"],
    ["siavash", "siyavash"],
    ["behrouz", "behruz"],
    ["bijan", "bizhan"],
    ["kaveh", "kave", "kavih"],
    ["parisa", "pariza"],
    ["niloufar", "nilufar"],
    ["mahsa", "mehsa"],
    ["zahra", "zehra"],
    ["maryam", "meryem", "mariam", "mariyam"],
    ["samira", "semira", "sameera"],
    ["amina", "ameena"],
    ["khadija", "hatice", "hadija", "khadijah"],
    ["salma", "selma"],
    ["layla", "leyla", "leila", "laila"],
    ["huda", "hoda"],
    ["rania", "raniya"],
    ["dalal", "dalel"],
    ["hanan", "henan"],
    ["sabah", "sabbah"],
    ["sultan", "soltan"],
    ["attar", "atar"],
    ["haddad", "hadad"],
    ["khoury", "khuri", "houry", "khouri"],
    ["masri", "misri"],
    ["najjar", "nadjar", "najar"],
    ["nasser", "nasir", "naser", "nassir"],
    ["shahin", "sahin", "chahine"],
    ["shamsi", "samsi"],
    ["zahrani", "zehrani"],
    ["zaidi", "zeydi", "zaydi"],
    ["barakat", "berakat"],
    ["darwish", "dervis", "darwich", "darweesh"],
    ["ghanem", "ganim", "ghanim"],
    ["hakim", "hakem", "hakeem"],
    ["hamdan", "hamdane"],
    ["hashimi", "hasimi", "hashemi"],
    ["kanaan", "kenan", "canaan"],
    ["khatib", "hatip", "hatib", "khateeb"],
    ["mansour", "mansur", "mansoor"],
    ["salman", "selman"],
    ["sayed", "seyyed", "sayyid", "sayid"],
    ["tikriti", "tikritli"],
    ["esfahani", "isfahani"],
    ["ebrahimi", "ibrahimi"],
    ["sadeghi", "sadighi", "sadiqi"],
    ["salehi", "salihi"],
    ["tabrizi", "tebrizi"],
    ["tehrani", "tahrani"],
    ["rahimi", "rehimi"],
    ["rahmani", "rehmani"],
    ["mousavi", "musavi", "mousawi"],
    ["mohammadi", "muhammadi"],
    ["moradi", "muradi"],
    ["nazari", "nezari"],
    ["rezaei"],
    ["rostami", "rustami"],
    ["yazdani", "yezdani"],
    ["akbari", "ekberi"],
    ["bagheri", "bakeri", "baqeri"],
    ["ghasemi", "kasemi", "qasemi"],
    ["hosseini", "huseyni", "hoseini"],
    ["jafari", "caferi", "djafari"],
    ["karimi", "kerimi", "carimi"],
    ["kermani", "kirmani"],
    ["mahmoudi", "mahmudi"],
    ["farahani", "ferahani"],
    ["ahmadi", "ahmedi"],
    ["talal", "tallal"],
    ["fares", "faris"],
    ["taha", "toha"],
    ["awad", "awwad"],
    ["aziz", "azeez"],
    ["abbas", "abas"],
    ["ali", "aly"],
    ["amir", "ameer"],
    ["sami", "samih"],
    ["samir", "sameer"],
    ["rami", "ramy"],
    ["ziad", "zeyad"],
    ["nabil", "nabeel"],
    ["bashar", "beshar"],
    ["hamid", "hameed"],
    ["fahd", "fahad"],
    ["saleh", "salih"],
    ["kamran", "kamran"],
    ["arash", "arache"],
    ["babak", "babek"],
    ["ehsan", "ihsan"],
    ["omid", "omeed"],
    ["nasrin", "nasreen"],
    ["shahram", "shahrom"],
    ["zamani", "zemani"],
    ["shirazi", "shirazy"],
    ["douri", "doori"],
    ["jabouri", "jaburi"],
]

_GROUPS_BY_MODE = {
    MODE_WEST: WEST_GROUPS,
    MODE_RU: RU_GROUPS,
    MODE_SEM: SEM_GROUPS,
}

_SYN = {}


def _build_synonyms():
    if _SYN:
        return
    for mode, groups in _GROUPS_BY_MODE.items():
        heads = set()
        for group in groups:
            heads |= skeletons(group[0], mode)
        owners = defaultdict(set)
        cand = defaultdict(set)
        for gi, group in enumerate(groups):
            head_keys = skeletons(group[0], mode)
            for name in group[1:]:
                for k in skeletons(name, mode):
                    if k in heads and k not in head_keys:
                        continue        # would merge two canonical names
                    owners[k].add(gi)
                    cand[k] |= head_keys
        for k in owners:
            _SYN.setdefault((mode, k), set()).update(cand[k])


# ---------------------------------------------------------------------------
# name tokens
# ---------------------------------------------------------------------------

ARTICLES = {"al", "el", "ul", "ash", "ar", "as", "an", "ad", "at", "az",
            "ath", "adh", "es", "il", "ale"}
NASAB = {"bin", "ibn", "ben", "bn", "bint", "binti", "binte", "b", "bnt",
         "ould", "wld"}
# nasab markers that are also ordinary names / initials
AMBIG_NASAB = {"b", "ben"}
PARTICLES = {"de", "la", "le", "du", "da", "di", "del", "della", "van",
             "von", "der", "den", "dos", "das", "do", "of", "the", "des",
             "ter", "te", "st", "abu", "umm", "lo", "los", "las"}
PREFIXES = {"mac", "mc", "mck", "mcc", "fitz", "o"}
TITLES = {"mr", "mrs", "ms", "miss", "mister", "dr", "prof", "eng",
          "sheikh", "shaykh", "sheik", "shaikh", "hajj", "hajji", "haji",
          "gen", "col", "capt", "lt", "sgt", "maj", "sir", "madam", "madame",
          "mme", "mlle", "herr", "frau", "senor", "senora", "srta", "hon"}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v", "phd", "md", "esq"}

ABD_RE = re.compile(r"^ab+d+[aeou]*[lr]*[aeou]*$")
ABD_WHOLE_RE = re.compile(r"^ab+d+[aeou]*l+[aeou]*h?$")
PATRO_RE = re.compile(
    r"(ov|ev|iv|ow|ew|of|ef|off|eff)"
    r"(ich|itch|itsch|ic|ich|ych|icz|itz|ytch|iz)$"
    r"|(ov|ev|ow|ew|of|ef)(na|nna)$"
    r"|(ivna|ovna|evna|owna|ewna|itch|yevich)$")


def _split_raw(name):
    """Split a raw name string into whitespace tokens (comma is a separator)."""
    s = name.replace(",", " ")
    s = re.sub(r"[‌‍]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return [t for t in s.split(" ") if t]


def _clean_tok(t):
    return re.sub(r"[.·]+$", "", t)


def strip_article(tok, mode=None):
    """Return alternative forms of a token with the arabic article removed."""
    alts = {tok}
    if mode is not None and mode != MODE_SEM:
        return alts
    low = fold(tok)
    low = re.sub(r"[^a-z\-]", "", low)
    if "-" in low:
        head, _, rest = low.partition("-")
        if len(head) == 1 and rest[:1] == head and len(rest) >= 3:
            return {rest}
        if head in ARTICLES and len(rest) >= 2:
            alts.add(rest)
            alts.discard(tok)
            return {rest}
    bare = low.replace("-", "")
    # attached article written with a capital: ElMasri, AlNoor
    m = re.match(r"^(al|el|ul)(.+)$", tok.replace("-", ""))
    if m and len(m.group(2)) >= 3 and m.group(2)[0].isupper():
        return {m.group(2)}
    m = re.match(r"^(al|el|ul)(.+)$", bare)
    if m and len(m.group(2)) >= 3:
        alts.add(m.group(2))
    # sun-letter assimilation with doubling: arrashid, annajjar, ashshamsi
    m = re.match(r"^[aeu](l|r|s|n|d|t|z|c|sh|th|ss|nn|rr|ll|dd|tt|zz)(.+)$",
                 bare)
    if m and len(m.group(2)) >= 3:
        cons = m.group(1)
        rest = m.group(2)
        if rest.startswith(cons[0]) or cons in ("l",):
            alts.add(rest)
    return alts


class Slot:
    __slots__ = ("keys", "optional", "kind")

    def __init__(self, keys, optional=False, kind="core"):
        self.keys = keys
        self.optional = optional
        self.kind = kind


def token_keys(tok, mode):
    """Skeleton key set for one name token (article variants, synonyms)."""
    keys = set()
    for form in sorted(strip_article(tok, mode)):
        keys |= skeletons(form, mode)
    extra = set()
    for k in keys:
        syn = _SYN.get((mode, k))
        if syn:
            extra |= syn
    return frozenset(keys | extra)


def _abd_key(theo_tok, mode):
    """Key for an 'abd al-X' theophoric compound."""
    keys = set()
    for form in sorted(strip_article(theo_tok, mode)):
        for s in skeletons(form, mode):
            keys.add("abd#" + s)
        for k in list(skeletons(form, mode)):
            syn = _SYN.get((mode, k))
            if syn:
                for s in syn:
                    keys.add("abd#" + s)
    return frozenset(keys)


def _is_allah(tok):
    w = re.sub(r"[^a-z]", "", fold(tok))
    return bool(re.match(r"^(a|u)?l*[aeou]*h$", w)) and "l" in w


def _mk_tokens(name):
    """Latin name -> list of (display, [spelling alternatives])."""
    out = []
    for t in _split_raw(name):
        t = _clean_tok(t)
        if t:
            out.append((t, [t]))
    return out


def parse_tokens(tokens, mode, no_join=frozenset()):
    """Return a list of parses; each parse is a list of Slots.

    `tokens` is a list of (display, alternatives) pairs.
    """
    ambiguous = []
    def keys_of(alts):
        ks = set()
        for a in alts[:400]:
            ks |= token_keys(a, mode)
        return ks

    slots = []
    i = 0
    n = len(tokens)
    pending_optional = False
    while i < n:
        tok, alts = tokens[i]
        low = re.sub(r"[^a-z]", "", fold(tok))
        if not low:
            i += 1
            continue
        if low in NASAB and i not in no_join:
            if i + 1 < n:
                if low in AMBIG_NASAB:
                    ambiguous.append(i)    # "B." initial, "Ben" given name
                i += 1
                pending_optional = True
                continue
            if low not in AMBIG_NASAB:
                i += 1
                continue                   # dangling nasab marker
        if len(low) == 1:
            i += 1
            continue                       # middle initial
        if (low in TITLES or low in SUFFIXES) and n > 2:
            i += 1
            continue
        if low in ARTICLES and "-" not in tok:
            i += 1
            continue                   # standalone arabic article
        if low in PARTICLES or low in PREFIXES:
            j = i + 1
            chain = [low]
            while j < n:
                nxt = re.sub(r"[^a-z]", "", fold(tokens[j][0]))
                if nxt in PARTICLES or nxt in PREFIXES:
                    chain.append(nxt)
                    j += 1
                else:
                    break
            if j < n:
                keys = set()
                if low not in PREFIXES:
                    keys |= keys_of(tokens[j][1])
                pre = "".join(chain)
                keys |= keys_of([pre + fold(a) for a in tokens[j][1][:16]])
                slots.append(Slot(frozenset(keys), pending_optional, "core"))
                pending_optional = False
                i = j + 1
                continue
            i = j
            continue
        if ABD_RE.match(low) and i + 1 < n and i not in no_join:
            if ABD_WHOLE_RE.match(low):
                ambiguous.append(i)
            j = i + 1
            nxt = re.sub(r"[^a-z]", "", fold(tokens[j][0]))
            if nxt in ARTICLES and j + 1 < n:
                j += 1
            keys = set()
            for cand in tokens[j][1][:32]:
                if _is_allah(cand):
                    keys |= _abd_key("allah", mode)
                else:
                    keys |= _abd_key(cand, mode)
            slots.append(Slot(frozenset(keys), pending_optional, "core"))
            pending_optional = False
            i = j + 1
            continue
        if re.match(r"^ab+d", low) and len(low) > 4:
            theos = _theo_parts(low)
            if theos:
                keys = set()
                for theo in theos:
                    keys |= _abd_key(theo, mode)
                slots.append(Slot(frozenset(keys), pending_optional, "core"))
                pending_optional = False
                i += 1
                continue
        if _is_allah(tok) and slots and mode == MODE_SEM:
            prev = slots.pop()             # nasr + allah -> one family name
            merged = set()
            for pk in prev.keys:
                merged.add(pk + "AlA")
                merged.add(pk + "AlAh")
            slots.append(Slot(frozenset(merged), prev.optional, "core"))
            i += 1
            continue
        kind = "core"
        opt = pending_optional
        pending_optional = False
        keys = keys_of(alts)
        if mode == MODE_RU and PATRO_RE.search(low) and n >= 2:
            kind = "patro"
            opt = True
            roots = []
            for a in alts[:16]:
                r = PATRO_RE.sub("", re.sub(r"[^a-z]", "", fold(a)))
                if len(r) >= 3:
                    roots.append(r)
            if roots:
                keys = keys | keys_of(roots)
        slots.append(Slot(frozenset(keys), opt, kind))
        i += 1

    parses = [slots]
    for idx in ambiguous:
        for alt in parse_tokens(tokens, mode, no_join | {idx}):
            parses.append(alt)
    if any("-" in t for t, _ in tokens):
        alt = _resplit(tokens, mode)
        if alt and len(alt) != len(slots):
            parses.append(alt)
    core_idx = [k for k, s in enumerate(slots) if s.kind == "core"
                and not s.optional]
    if 2 <= len(core_idx) <= 4:
        for a, b in zip(core_idx, core_idx[1:]):
            merged = []
            for k, s in enumerate(slots):
                if k == a:
                    ks = set()
                    for x in sorted(slots[a].keys)[:24]:
                        for y in sorted(slots[b].keys)[:24]:
                            ks.add(x + y)
                    merged.append(Slot(frozenset(ks), False, "core"))
                elif k == b:
                    continue
                else:
                    merged.append(s)
            parses.append(merged)
    return parses


def parse_person(name, mode):
    return parse_tokens(_mk_tokens(name), mode)


def _theo_parts(low):
    """Candidate theophoric elements of a joined 'abd...' token."""
    body = re.sub(r"^ab+d+", "", low)
    cands = set()
    stripped = [body]
    cur = body
    for _ in range(2):
        if cur and cur[0] in "aeou":
            cur = cur[1:]
            stripped.append(cur)
        else:
            break
    for s in list(stripped):
        if not s:
            continue
        if re.match(r"^l+[aeou]*h?$", s) or s in ("ah", "h"):
            cands.add("allah")
            continue
        cands.add(s)
        m = re.match(r"^(.)\1(.*)$", s)
        if m and len(m.group(2)) >= 2:
            cands.add(m.group(1) + m.group(2))
        if s[0] in "lr" and len(s) > 2:
            cands.add(s[1:])
    return sorted(c for c in cands if len(c) >= 2)


def _resplit(tokens, mode):
    slots = []
    for t, alts in tokens:
        low = re.sub(r"[^a-z]", "", fold(t))
        if not low or len(low) == 1 or low in NASAB or low in ARTICLES \
                or low in PARTICLES:
            continue
        if "-" in t:
            parts = [p for p in t.split("-") if p]
            head = re.sub(r"[^a-z]", "", fold(parts[0]))
            if head not in ARTICLES:
                for p in parts:
                    if len(re.sub(r"[^a-z]", "", fold(p))) > 1:
                        slots.append(Slot(token_keys(p, mode), False, "core"))
                continue
        kind = "core"
        opt = False
        if mode == MODE_RU and PATRO_RE.search(low):
            kind, opt = "patro", True
        ks = set()
        for a in alts[:64]:
            ks |= token_keys(a, mode)
        slots.append(Slot(frozenset(ks), opt, kind))
    return slots


# ---------------------------------------------------------------------------
# entity / vessel names
# ---------------------------------------------------------------------------

DESIGNATORS = [
    ["public", "joint", "stock", "company"],
    ["closed", "joint", "stock", "company"],
    ["limited", "liability", "company"],
    ["free", "zone", "establishment"],
    ["joint", "stock", "company"],
    ["sociedad", "anonima"],
    ["private", "limited"],
    ["limited", "liability"],
    ["public", "company"],
    ["and", "partners"],
    ["fz", "llc"], ["fz", "co"], ["fz", "e"],
    ["l", "l", "c"], ["s", "a"], ["g", "m", "b", "h"], ["a", "g"],
    ["b", "v"], ["n", "v"], ["s", "l"], ["s", "p", "a"], ["p", "l", "c"],
    ["llc"], ["ltd"], ["limited"], ["inc"], ["incorporated"], ["corp"],
    ["corporation"], ["company"], ["co"], ["gmbh"], ["ag"], ["sa"], ["sas"],
    ["jsc"], ["ojsc"], ["oao"], ["ao"], ["pjsc"], ["zao"], ["pao"],
    ["fze"], ["fzco"], ["fzllc"], ["plc"], ["bv"], ["nv"], ["srl"], ["spa"],
    ["pte"], ["llp"], ["lp"], ["kg"], ["ohg"], ["oy"], ["ab"], ["as"],
    ["sarl"], ["sl"], ["establishment"], ["trust"], ["pvt"], ["cjsc"],
]
VESSEL_PREFIX = {"mv", "m/v", "mt", "m/t", "ms", "m/s", "ss", "s/s",
                 "vessel", "the", "mtv", "fv", "f/v", "tug", "sv"}

_STOP_ENTITY = {"the", "and", "&", "of", "al", "el"}


def norm_org(name, is_vessel=False):
    s = fold(name)
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    words = [w for w in s.split() if w]
    if is_vessel:
        while words and words[0] in VESSEL_PREFIX:
            words = words[1:]
        while words and words[0] in ("m", "v", "t", "s") and len(words) > 1 \
                and words[1] in ("v", "t", "s"):
            words = words[2:]
    words = [w for w in words if w not in _STOP_ENTITY]
    # drop legal designators anywhere in the name
    changed = True
    while changed and words:
        changed = False
        for des in DESIGNATORS:
            L = len(des)
            if L <= len(words) and words[-L:] == des:
                words = words[:-L]
                changed = True
                break
        if not changed and len(words) > 1:
            for des in DESIGNATORS:
                L = len(des)
                if L < len(words) and words[:L] == des:
                    words = words[L:]
                    changed = True
                    break
    out = []
    for w in words:
        m = re.match(r"^(al|el)(.+)$", w)
        if m and len(m.group(2)) >= 3:
            w = m.group(2)
        out.append(w)
    return tuple(out)


# ---------------------------------------------------------------------------
# dates and identifiers
# ---------------------------------------------------------------------------

def parse_dob(s):
    s = (s or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{4})(?:[-/.](\d{1,2}))?(?:[-/.](\d{1,2}))?$", s)
    if m:
        parts = [m.group(1)]
        if m.group(2):
            parts.append("%02d" % int(m.group(2)))
        if m.group(3):
            parts.append("%02d" % int(m.group(3)))
        return tuple(parts)
    # day-first formats: keep only what is unambiguous
    m = re.match(r"^(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})$", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if a > 12 >= b:
            return (y, "%02d" % b, "%02d" % a)
        if b > 12 >= a:
            return (y, "%02d" % a, "%02d" % b)
        return (y,)
    m = re.match(r"^(\d{1,2})[-/.](\d{4})$", s)
    if m:
        return (m.group(2), "%02d" % int(m.group(1)))
    return None


def dob_compare(cust, entry):
    """Return 'agree', 'conflict' or 'unknown'."""
    if not cust or not entry:
        return "unknown"
    k = min(len(cust), len(entry))
    for i in range(k):
        if cust[i] != entry[i]:
            return "conflict"
    return "agree"


def dob_support(cust, entry):
    """How strongly a date of birth backs a candidate (0 = not at all)."""
    if dob_compare(cust, entry) != "agree":
        return 0
    return min(len(cust), len(entry))


TYPE_ALIASES = {
    "individual": "individual", "person": "individual", "natural": "individual",
    "naturalperson": "individual", "human": "individual", "ind": "individual",
    "entity": "entity", "company": "entity", "organisation": "entity",
    "organization": "entity", "org": "entity", "corporate": "entity",
    "legalentity": "entity", "business": "entity", "firm": "entity",
    "vessel": "vessel", "ship": "vessel", "boat": "vessel",
    "aircraft": "vessel", "tanker": "vessel",
}


def norm_type(value):
    s = re.sub(r"[^a-z]", "", fold(value or ""))
    return TYPE_ALIASES.get(s, s)


def norm_id(value):
    return re.sub(r"[^a-z0-9]", "", fold(value or ""))


def norm_idtype(value):
    s = re.sub(r"[^a-z]", "", fold(value or ""))
    if not s:
        return ""
    if "passport" in s or s in ("ppt", "pp", "passeport", "pasaporte"):
        return "passport"
    if "imo" in s:
        return "imo"
    if s.startswith("reg") or "registration" in s or "regno" in s:
        return "registration"
    if "national" in s and "id" in s:
        return "nationalid"
    return s


# ---------------------------------------------------------------------------
# watchlist model
# ---------------------------------------------------------------------------

class NameForm:
    __slots__ = ("slots", "mode", "weak", "text")

    def __init__(self, slots, mode, weak, text):
        self.slots = slots
        self.mode = mode
        self.weak = weak
        self.text = text


class Entry:
    __slots__ = ("uid", "etype", "dob", "ids", "forms", "org_names",
                 "weak_names", "mode")

    def __init__(self, uid, etype, dob, ids, forms, org_names, weak_names,
                 mode):
        self.uid = uid
        self.etype = etype
        self.dob = dob
        self.ids = ids
        self.forms = forms
        self.org_names = org_names
        self.weak_names = weak_names
        self.mode = mode


def entry_mode(entry):
    script = entry.get("script_name") or ""
    name = entry.get("primary_name") or ""
    blob = script + " " + name
    if is_cyrillic(blob):
        return MODE_RU
    if is_arabic(blob):
        return MODE_SEM
    return MODE_WEST


def build_script_dict(watchlist):
    """Mine a script-token -> latin-token dictionary from the watchlist."""
    pairs = defaultdict(lambda: defaultdict(int))
    for e in watchlist:
        if e.get("type") != "individual":
            continue
        script = e.get("script_name")
        primary = e.get("primary_name") or ""
        if not script or not has_latin(primary):
            continue
        lat = [t for t in _split_raw(primary)
               if re.sub(r"[^a-z]", "", fold(_clean_tok(t))) not in
               (NASAB | ARTICLES) and
               len(re.sub(r"[^a-z]", "", fold(_clean_tok(t)))) > 1]
        scr = [t for t in _split_raw(script) if t not in ("بن", "ابن", "ال")]
        if len(lat) == len(scr):
            for s, l in zip(scr, lat):
                pairs[s][_clean_tok(l)] += 1
    out = {}
    for s, cands in pairs.items():
        out[s] = max(cands.items(), key=lambda kv: (kv[1], -len(kv[0])))[0]
    return out


def script_to_latin_tokens(name, script_dict):
    """Turn a (possibly mixed-script) name into latin token alternatives."""
    res = []
    for tok in _split_raw(name):
        if tok in ("بن", "ابن"):
            res.append(["bin"])
            continue
        if tok == "ال":
            res.append(["al"])
            continue
        hit = script_dict.get(tok)
        if hit:
            res.append([hit])
        elif is_cyrillic(tok):
            res.append([translit_cyr(tok)])
        elif is_arabic(tok):
            forms = translit_arab(tok)
            res.append(forms or [tok])
        else:
            res.append([tok])
    return res


def build_forms_from_script(name, script_dict, mode):
    """Build NameForm slot lists for a name written in its original script."""
    alts = script_to_latin_tokens(name, script_dict)
    tokens = [(a[0], a) for a in alts]
    return parse_tokens(tokens, mode)


def build_entries(watchlist, script_dict):
    entries = []
    for e in watchlist:
        uid = e.get("uid")
        etype = e.get("type")
        mode = entry_mode(e)
        dob = parse_dob(e.get("dob"))
        ids = set()
        for ident in e.get("ids") or []:
            t = norm_idtype(ident.get("type"))
            v = norm_id(ident.get("number"))
            if v:
                ids.add((t, v))
        forms = []
        org_names = set()
        weak_names = set()
        names = []
        primary = e.get("primary_name") or ""
        if primary:
            names.append((primary, False))
        script = e.get("script_name") or ""
        if script and script != primary:
            names.append((script, False))
        for a in e.get("aliases") or []:
            nm = a.get("name") or ""
            if not nm:
                continue
            if a.get("strength") == "strong":
                names.append((nm, False))
            else:
                names.append((nm, True))
        for nm, weak in names:
            if etype in ("entity", "vessel"):
                if weak:
                    weak_names.add(" ".join(norm_org(nm, etype == "vessel")))
                else:
                    org_names.add(norm_org(nm, etype == "vessel"))
                continue
            if weak:
                weak_names |= _weak_keys(nm)
                continue
            if is_cyrillic(nm) or is_arabic(nm):
                parses = build_forms_from_script(nm, script_dict, mode)
            else:
                parses = parse_person(nm, mode)
            for p in parses:
                if p:
                    forms.append(NameForm(p, mode, False, nm))
        entries.append(Entry(uid, etype, dob, ids, forms, org_names,
                             weak_names, mode))
    return entries


def _weak_keys(name):
    """Keys under which a weak alias (a nom de guerre) is indexed."""
    s = fold(name)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    words = [w for w in s.split() if w and w not in ("the", "al", "el")]
    if not words:
        return frozenset()
    out = {" ".join(words)}
    skel = []
    for w in words:
        ks = sorted(skeletons(w, MODE_WEST))
        skel.append(ks[0] if ks else w)
    out.add("|".join(skel))
    return frozenset(out)


# ---------------------------------------------------------------------------
# matching
# ---------------------------------------------------------------------------

def slots_match(cust_slots, entry_slots):
    """True if required slots on both sides correspond."""
    creq = [s for s in cust_slots if not s.optional]
    ereq = [s for s in entry_slots if not s.optional]
    if len(creq) < 2 or len(ereq) < 2:
        return False
    call = cust_slots
    eall = entry_slots
    ekeys = set()
    for s in eall:
        ekeys |= s.keys
    ckeys = set()
    for s in call:
        ckeys |= s.keys
    for s in creq:
        if not (s.keys & ekeys):
            return False
    for s in ereq:
        if not (s.keys & ckeys):
            return False
    # patronymics, when present on both sides, must agree
    cpat = [s for s in call if s.kind == "patro"]
    epat = [s for s in eall if s.kind == "patro"]
    if cpat and epat:
        ok = False
        for a in cpat:
            for b in epat:
                if a.keys & b.keys:
                    ok = True
        if not ok:
            return False
    # require a one-to-one assignment of the required slots
    if not _bipartite(creq, eall) or not _bipartite(ereq, call):
        return False
    return True


def _bipartite(left, right):
    """Every slot in left matched to a distinct slot in right."""
    n = len(left)
    m = len(right)
    if n > m:
        return False
    adj = []
    for s in left:
        row = [j for j in range(m) if s.keys & right[j].keys]
        if not row:
            return False
        adj.append(row)
    match = [-1] * m

    def try_assign(i, seen):
        for j in adj[i]:
            if j in seen:
                continue
            seen.add(j)
            if match[j] == -1 or try_assign(match[j], seen):
                match[j] = i
                return True
        return False

    for i in range(n):
        if not try_assign(i, set()):
            return False
    return True


class Screener:
    def __init__(self, watchlist):
        _build_synonyms()
        self.script_dict = build_script_dict(watchlist)
        self.entries = build_entries(watchlist, self.script_dict)
        self.by_id = defaultdict(list)
        self.by_id_digits = defaultdict(set)
        self.by_key = defaultdict(set)
        self.by_org = defaultdict(list)
        self.by_org_fuzzy = defaultdict(list)
        self.by_weak = defaultdict(list)
        # organisation words: a long word may be matched by its skeleton, but
        # only where that cannot merge two different words of this watchlist
        counts = {MODE_WEST: defaultdict(set), MODE_SEM: defaultdict(set)}
        for ent in self.entries:
            for org in ent.org_names:
                for w in org:
                    if len(w) >= 4:
                        for m in (MODE_WEST, MODE_SEM):
                            ks = sorted(skeletons(w, m))
                            if ks:
                                counts[m][ks[0]].add(w)
        self.org_ambiguous = {
            m: {k for k, v in counts[m].items() if len(v) > 1}
            for m in counts}
        digit_owner = defaultdict(set)
        for idx, ent in enumerate(self.entries):
            for key in ent.ids:
                self.by_id[key].append(idx)
                digits = re.sub(r"\D", "", key[1])
                if len(digits) >= 5:
                    digit_owner[(key[0], digits)].add(key[1])
                    self.by_id_digits[(key[0], digits)].add(idx)
            for fi, form in enumerate(ent.forms):
                for s in form.slots:
                    for k in s.keys:
                        self.by_key[k].add((idx, fi))
            for org in ent.org_names:
                if org:
                    self.by_org[tuple(sorted(org))].append(idx)
                    for m in (MODE_WEST, MODE_SEM):
                        self.by_org_fuzzy[self.org_canon(org, m)].append(idx)
            for wk in ent.weak_names:
                if wk:
                    self.by_weak[wk].append(idx)
        for key, numbers in digit_owner.items():
            if len(numbers) > 1:            # ambiguous: keep it strict
                self.by_id_digits.pop(key, None)

    def org_canon(self, words, mode=MODE_WEST):
        """Order-insensitive key for an organisation / vessel name.

        Words of five characters or more are reduced to a spelling skeleton,
        but only when that cannot merge two different words of this watchlist
        (which keeps short chinese syllables and near-identical words apart).
        """
        out = []
        for w in words:
            if len(w) >= 4:
                ks = sorted(skeletons(w, mode))
                if ks and ks[0] not in self.org_ambiguous[mode]:
                    out.append(ks[0])
                    continue
            out.append(w)
        return (mode,) + tuple(sorted(out))

    # -- name candidates ---------------------------------------------------
    def name_candidates(self, cust_parses_by_mode, allow):
        hits = defaultdict(set)
        for mode, parses in cust_parses_by_mode.items():
            for pi, slots in enumerate(parses):
                for si, s in enumerate(slots):
                    for k in s.keys:
                        for (idx, fi) in self.by_key.get(k, ()):
                            hits[(idx, fi)].add((mode, pi, si))
        cands = []
        for (idx, fi), touched in hits.items():
            ent = self.entries[idx]
            if ent.etype not in allow:
                continue
            slots_touched = defaultdict(set)
            for (mode, pi, si) in touched:
                slots_touched[(mode, pi)].add(si)
            best = max(len(v) for v in slots_touched.values())
            if best >= 2:
                cands.append((idx, fi))
        return cands

    def screen(self, cust):
        ctype = norm_type(cust.get("type"))
        if ctype in ("individual", "entity", "vessel"):
            allow = {ctype}
        else:
            allow = {"individual", "entity", "vessel"}
        name = (cust.get("full_name") or "").strip()
        dob = parse_dob(cust.get("dob"))
        idt = norm_idtype(cust.get("id_type"))
        idv = norm_id(cust.get("id_number"))
        id_hits = set()
        if idt and idv:
            for idx in self.by_id.get((idt, idv), ()):
                id_hits.add(idx)
            if not id_hits:
                digits = re.sub(r"\D", "", idv)
                if len(digits) >= 5:
                    id_hits |= self.by_id_digits.get((idt, digits), set())
        candidates = {}

        def add(idx, id_sup, dob_state):
            prev = candidates.get(idx)
            score = (1 if id_sup else 0,
                     dob_support(dob, self.entries[idx].dob)
                     if dob_state == "agree" else 0)
            if prev is None or score > prev:
                candidates[idx] = score

        for idx in id_hits:
            add(idx, True, dob_compare(dob, self.entries[idx].dob))

        if allow & {"entity", "vessel"}:
            for vessel in (False, True):
                if vessel and "vessel" not in allow:
                    continue
                if not vessel and "entity" not in allow:
                    continue
                words = norm_org(name, vessel)
                hits = list(self.by_org.get(tuple(sorted(words)), ()))
                for m in (MODE_WEST, MODE_SEM):
                    hits += list(self.by_org_fuzzy.get(
                        self.org_canon(words, m), ()))
                for idx in hits:
                    ent = self.entries[idx]
                    if ent.etype not in allow:
                        continue
                    state = dob_compare(dob, ent.dob)
                    if state == "conflict":
                        continue
                    add(idx, idx in id_hits, state)
        if "individual" in allow:
            parses_by_mode = {}
            script = is_cyrillic(name) or is_arabic(name)
            for mode in MODES:
                if script:
                    parses_by_mode[mode] = build_forms_from_script(
                        name, self.script_dict, mode)
                else:
                    parses_by_mode[mode] = parse_person(name, mode)
            for idx, fi in self.name_candidates(parses_by_mode, allow):
                ent = self.entries[idx]
                form = ent.forms[fi]
                ok = False
                for slots in parses_by_mode[form.mode]:
                    if slots_match(slots, form.slots):
                        ok = True
                        break
                if not ok:
                    continue
                state = dob_compare(dob, ent.dob)
                if state == "conflict":
                    continue
                add(idx, idx in id_hits, state)

        # weak aliases: only with an identical full date of birth
        if dob and len(dob) == 3:
            keys = set()
            if "individual" in allow:
                keys |= set(_weak_keys(name))
            if allow & {"entity", "vessel"}:
                keys.add(" ".join(norm_org(name, "vessel" in allow)))
            for k in keys:
                for idx in self.by_weak.get(k, ()):
                    ent = self.entries[idx]
                    if ent.etype not in allow:
                        continue
                    if ent.dob and len(ent.dob) == 3 and ent.dob == dob:
                        add(idx, idx in id_hits, "agree")

        if not candidates:
            return ("NO_MATCH", "")
        best = sorted(candidates.items(),
                      key=lambda kv: (-kv[1][0], -kv[1][1],
                                      self.entries[kv[0]].uid))[0][0]
        return ("MATCH", self.entries[best].uid)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

FIELD_ALIASES = {
    "customerid": "customer_id", "customer": "customer_id", "cid": "customer_id",
    "id": "customer_id", "recordid": "customer_id", "rowid": "customer_id",
    "fullname": "full_name", "name": "full_name", "customername": "full_name",
    "partyname": "full_name", "subjectname": "full_name",
    "dob": "dob", "dateofbirth": "dob", "birthdate": "dob", "birth": "dob",
    "nationality": "nationality", "country": "nationality",
    "idtype": "id_type", "identifiertype": "id_type", "doctype": "id_type",
    "documenttype": "id_type",
    "idnumber": "id_number", "identifiernumber": "id_number",
    "docnumber": "id_number", "documentnumber": "id_number",
    "idno": "id_number",
    "type": "type", "partytype": "type", "entitytype": "type",
    "recordtype": "type", "subjecttype": "type",
}


def read_customers(path):
    """Read the customer CSV tolerantly; keep the file order."""
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh)
        try:
            header = next(reader)
        except StopIteration:
            return []
        cols = {}
        for i, h in enumerate(header):
            key = re.sub(r"[^a-z0-9]", "", (h or "").lower())
            field = FIELD_ALIASES.get(key)
            if field and field not in cols:
                cols[field] = i
        rows = []
        for raw in reader:
            if not raw or all(not (c or "").strip() for c in raw):
                continue
            rec = {}
            for field, i in cols.items():
                rec[field] = raw[i] if i < len(raw) else ""
            rows.append(rec)
        return rows


def load_watchlist(path):
    with open(path, encoding="utf-8-sig") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        for key in ("entries", "results", "data", "watchlist", "records"):
            if isinstance(data.get(key), list):
                return data[key]
        for value in data.values():
            if isinstance(value, list):
                return value
        return []
    return data


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="screen customers against a sanctions watchlist")
    ap.add_argument("--watchlist", required=True)
    ap.add_argument("--customers", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    watchlist = load_watchlist(args.watchlist)
    screener = Screener(watchlist)
    rows = read_customers(args.customers)

    with open(args.out, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["customer_id", "decision", "matched_uid"])
        for row in rows:
            try:
                decision, uid = screener.screen(row)
            except Exception:                       # never drop a customer
                decision, uid = "NO_MATCH", ""
            writer.writerow([row.get("customer_id", ""), decision, uid])
    return 0


if __name__ == "__main__":
    sys.exit(main())
