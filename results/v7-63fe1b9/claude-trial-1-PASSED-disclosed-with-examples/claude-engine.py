#!/usr/bin/env python3
"""Sanctions screening engine.

Usage:
    python3 screen.py --watchlist watchlist.json --customers customers.csv --out decisions.csv

Standard library only.  The engine implements the screening policy:

  Rule 1  identifiers (passport / registration / imo)
  Rule 2  name equivalence across romanisation conventions, name order,
          particles, patronymics, nicknames
  Rule 3  strong / weak aliases
  Rule 4  date of birth
  Rule 5  entities (legal form designators, Chinese romanisations) and vessels
  Rule 6  nationality is informational

Every name word is reduced to a *set* of phonetic codes.  Ambiguous letters
fan out into several readings (``c`` can be k, s, ch, ts or j; ``j`` can be j,
zh or y; ``s`` can be s, sh or z ...) and two words correspond when their code
sets intersect.  One canonical routine therefore absorbs English, French,
German, Turkish, Indonesian, Polish, Malay, scientific-Cyrillic and Gulf
spellings at once, instead of enumerating the conventions seen in a sample.
Original-script (Arabic / Persian / Cyrillic) names are folded into the same
code space, partly from a transliteration table mined out of the watchlist
itself, partly from a rule based transliterator.
"""

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict

# --------------------------------------------------------------------------
# character level normalisation
# --------------------------------------------------------------------------

PREMAP = {
    "ß": "ss",
    "æ": "ae", "œ": "oe",
    "ø": "o", "å": "a",
    "ä": "a", "ö": "o", "ü": "u",
    "ı": "i", "İ": "i",          # Turkish dotless / dotted i
    "ş": "sh", "Ş": "sh",
    "ç": "ch", "Ç": "ch",
    "ğ": "g", "Ğ": "g",          # Turkish soft g
    "ñ": "n", "ń": "n",
    "ł": "l", "Ł": "l",
    "ż": "zh", "ź": "zh", "ž": "zh",
    "ś": "sh", "š": "sh",
    "ć": "ch", "č": "ch",
    "ř": "r", "ě": "e",
    "đ": "d", "ð": "d", "þ": "th",
}

CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
    "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i",
    "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
    "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
    "і": "i", "ї": "yi", "є": "ye", "ґ": "g", "ў": "u",
}

# arabic / persian letters -> phoneme alternatives ("V" = unknown vowel slot)
ARABIC = {
    "ا": ["V"], "أ": ["V"], "إ": ["V"], "آ": ["V"], "ٱ": ["V"],
    "ب": ["B"], "پ": ["P"],
    "ت": ["T"], "ث": ["T", "S"], "ة": ["", "T"],
    "ج": ["J"], "چ": ["C"],
    "ح": ["H"], "خ": ["K", "H"],
    "د": ["D"], "ذ": ["D", "Z"],
    "ر": ["R"], "ز": ["Z"], "ژ": ["J"],
    "س": ["S"], "ش": ["X"], "ص": ["S"], "ض": ["D", "Z"],
    "ط": ["T"], "ظ": ["Z", "D"],
    "ع": ["", "V"], "غ": ["G"],
    "ف": ["F"], "ق": ["K"], "ك": ["K"], "ک": ["K"], "گ": ["G"],
    "ل": ["L"], "م": ["M"], "ن": ["N"],
    "ه": ["H", ""], "و": ["F", "V"], "ي": ["Y", "V"],
    "ی": ["Y", "V"], "ى": ["Y", "V"], "ئ": ["Y", ""],
    "ء": [""], "ؤ": ["F", "V"], "ـ": [""],
}
ARABIC_DIACRITICS = set("ًٌٍَُِّْٰٕٓٔ")
ARABIC_NASAB = ("بن", "ابن", "بنت", "أبن")
ARABIC_ABD = ("عبد", "عبدال")
ARABIC_ALLAH = ("الله", "لله")


def _premap(s):
    return "".join(PREMAP.get(ch, ch) for ch in s)


def strip_accents(s):
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def is_cyrillic(s):
    return any("Ѐ" <= c <= "ӿ" for c in s)


def is_arabic(s):
    return any("؀" <= c <= "ۿ" or "ݐ" <= c <= "ݿ" for c in s)


def is_latin(s):
    return any("a" <= c.lower() <= "z" for c in s)


def clean_latin(tok):
    tok = strip_accents(_premap(tok.lower())).lower()
    return re.sub(r"[^a-z]", "", tok)


def cyr_to_latin(tok):
    out = []
    for i, ch in enumerate(tok.lower()):
        if ch == "е" and i == 0:
            out.append("ye")
        else:
            out.append(CYRILLIC.get(ch, ch if ch.isalpha() else ""))
    return "".join(out)


def clean_arabic(tok):
    tok = "".join(c for c in tok if c not in ARABIC_DIACRITICS)
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ٱ", "ا"),
                 ("ي", "ی"), ("ى", "ی"), ("ك", "ک")):
        tok = tok.replace(a, b)
    return "".join(c for c in tok if c.isalpha())


# --------------------------------------------------------------------------
# phonetic encoder
# --------------------------------------------------------------------------

# consonant rewrites, longest pattern first.  Alternatives are strings over
# the phoneme alphabet  B P T D K G F S Z X(sh) C(ch) J(zh) Q(ts) M N L R H Y
CONS_RULES = [
    ("schtsch", ["XC"]), ("shtsch", ["XC"]), ("chtch", ["XC"]),
    ("stsch", ["X", "XC"]), ("shch", ["XC"]), ("stch", ["XC"]),
    ("szcz", ["XC"]), ("zhch", ["XC"]),
    ("dsch", ["J"]), ("tsch", ["C", "X", "K", "H"]), ("sch", ["X", "J"]),
    ("tch", ["C", "X", "K", "H"]), ("dzh", ["J"]),
    ("cz", ["C"]), ("sz", ["X", "S"]), ("rz", ["J", "RJ"]),
    ("zh", ["J"]), ("dj", ["J", "DY"]), ("dz", ["J", "DS"]),
    ("chr", ["KR", "CR", "XR", "HR"]), ("chl", ["KL", "CL", "XL", "HL"]),
    ("ch", ["C", "X", "H"]), ("sh", ["X", "J"]), ("sy", ["X", "SY"]),
    ("sj", ["X", "SY"]), ("tj", ["C", "TY"]), ("nj", ["NY", "N"]),
    ("kh", ["K", "H"]), ("gh", ["G"]), ("ph", ["F"]), ("th", ["T"]),
    ("ck", ["K"]), ("cc", ["K", "C"]), ("ts", ["Q"]), ("tz", ["Q"]),
    ("x", ["KS"]), ("q", ["K"]), ("w", ["F"]), ("v", ["F"]), ("f", ["F"]),
    ("j", ["J", "Y"]), ("z", ["Z", "J", "Q"]), ("s", ["S", "X", "Z"]),
    ("b", ["B"]), ("p", ["P"]), ("t", ["T"]), ("d", ["D"]), ("k", ["K"]),
    ("g", ["G"]), ("m", ["M"]), ("n", ["N"]), ("l", ["L"]), ("r", ["R"]),
]
CONS_BY_FIRST = defaultdict(list)
for _pat, _alt in CONS_RULES:
    CONS_BY_FIRST[_pat[0]].append((_pat, _alt))

VOWELS = set("aeiou")
MAX_CODES = 600

def _vowel_class(ch):
    return "a" if ch in "aeiy" else "o"


# a word shaped like a cyrillic name: only there do a bare s / z / c stand
# for sh / zh / ch (scientific transliteration with the diacritics dropped)
SLAVIC = re.compile(
    r"(ov|ev|av|iv|ow|ew|aw|iw|off|eff|iff|in|yn|sky|ski|skij|skiy|ska"
    r"|skaja|skaya|skaia|enko|uk|ich|itch|ic|ova|eva|ina|owa|ewa|kow|wa"
    r"|witsch|wicz|vna|wna|ij|aja|oi|oj|aj|ej|uj)$"
    r"|kov|kow|cenk|tsch|schtsch|zd|jev|jew|jov|jow")

# a final vowel belongs to the name (Salma vs Salim, Olga vs Oleg, Amina vs
# Amin) -- except on a russian feminine surname, where -a / -aya is only the
# gender ending (Ivanova = Ivanov, Chaikovskaya = Chaikovsky)
FEM_SURNAME = re.compile(
    r"(ov|ev|av|iv|ow|ew|off|eff|ff|yn|sk|ck|zk|nk|ts)[aeo]$"
    r"|(k|s|z|c|sh|ch|zh|sch|cz|sz|tsch|szcz)in[aeo]$"
    r"|(sk|ck|zk|tsk|tzk)(aya|aja|aia)$")


def _final_vowel(w):
    """True when the word ends in a vowel that belongs to the name."""
    s = w
    if len(s) >= 4 and s.endswith("e"):
        s = s[:-1]                                # silent final -e
    if len(s) >= 4 and s.endswith("j") and s[-2] not in "stnd":
        s = s[:-1] + "i"                          # -ij / -j spell -i
    if len(s) >= 4 and s.endswith("h") and s[-2] in "aeiouy":
        s = s[:-1]                                # -ah / -eh
    if s[-1] not in "aou":
        return False        # a final -i / -y / -e needs no marker of its own
    flat = re.sub(r"(.)\1+", r"\1", s)            # Shishkinna = Shishkina
    return not (FEM_SURNAME.search(s) or FEM_SURNAME.search(flat))


def _run_alts(run, is_first, is_final, is_whole):
    """Phoneme alternatives for one vowel run."""
    base = _vowel_class(run[0]) if is_first else ""
    alts = {base}
    if is_final and run[-1] in "iy" and not is_whole:
        alts = {base + "Y"}                        # nisba / final -i or -y
    if len(run) >= 2 and run[-1] in "iey":
        alts.add(base + "Y")                       # falling diphthong
    if len(run) >= 3 and any(c in "iy" for c in run[1:-1]):
        alts.add(base + "Y")                       # -aia- / -aya-
    if len(run) >= 2 and run[0] in "iey":
        glide = "Y" + (_vowel_class(run[1]) if is_first else "")
        if run[0] == "i" and run[1] != "i":
            alts.discard(base)                     # i + other vowel is a glide
            alts.discard(base + "Y")
        alts.add(glide)
    if len(run) >= 2 and run[0] in "ou":
        alts.add("F" + (_vowel_class(run[1]) if is_first else ""))
    return alts or {base}


_code_cache = {}


def encode_word(word):
    """Phonetic code set of one latin word."""
    cached = _code_cache.get(word)
    if cached is not None:
        return cached
    w = clean_latin(word)
    if not w:
        _code_cache[word] = frozenset()
        return _code_cache[word]

    n = len(w)
    y_cons = [False] * n
    for i, ch in enumerate(w):
        if ch == "y":
            prv = w[i - 1] if i > 0 else ""
            nxt = w[i + 1] if i + 1 < n else ""
            if (nxt and nxt in VOWELS) or (prv and prv in VOWELS):
                y_cons[i] = True
    is_vowel = [(w[i] in VOWELS) or (w[i] == "y" and not y_cons[i])
                for i in range(n)]
    tail = "E" if _final_vowel(w) else ""
    german = "w" in w or "sch" in w              # german writes russian z as s
    slavic = bool(SLAVIC.search(w))

    slots = []
    i = 0
    seen_vowel = False
    while i < n:
        if is_vowel[i]:
            j = i
            while j < n and is_vowel[j]:
                j += 1
            slots.append(sorted(_run_alts(w[i:j], not seen_vowel, j >= n,
                                          i == 0 and j >= n)))
            seen_vowel = True
            i = j
            continue
        ch = w[i]
        if ch == "y":
            slots.append(["Y"])
            i += 1
            continue
        if ch == "h":
            slots.append(["H"] if i == 0 else ["H", ""])
            i += 1
            continue
        if ch == "g" and n > 2 and not w.startswith("gh", i):
            slots.append(["G", "J"])       # egyptian g spells jim (Gamal)
            i += 1
            continue
        matched = False
        for pat, alt in CONS_BY_FIRST.get(ch, ()):
            if w.startswith(pat, i):
                if any(is_vowel[k] for k in range(i, min(i + len(pat), n))):
                    continue
                if pat == "s":
                    alt = ["S"]
                    if slavic:
                        alt.append("X")
                    if german or i == n - 1:
                        alt.append("Z")
                elif pat == "z" and not slavic:
                    alt = ["Z", "Q"]
                slots.append(alt)
                i += len(pat)
                matched = True
                break
        if not matched:
            if ch == "c":
                nxt = w[i + 1] if i + 1 < n else ""
                if nxt in "eiy":
                    slots.append(["S", "J", "C", "Q"])
                elif slavic:
                    slots.append(["K", "C", "Q"])
                else:
                    slots.append(["K"])
            i += 1

    codes = [""]
    for alts in slots:
        if len(codes) * len(alts) > MAX_CODES:
            alts = alts[:1]
        codes = [c + a for c in codes for a in alts]

    out = set()
    for c in codes:
        s = _squeeze(c)
        if not s:
            continue
        s += tail
        if not tail:
            if s[-1] == "T":                        # final t/d devoicing
                s = _squeeze(s[:-1] + "D")
            elif s[-1] == "P":                      # final p/b devoicing
                s = _squeeze(s[:-1] + "B")
        out.add(s)
        if (len(s) > 2 and s[0] == "Y" and s[1] in "ao"
                and w[0] in "yij" and w[1:2] == "e"):
            out.add(s[1:])                          # optional initial y-glide
    res = frozenset(out)
    _code_cache[word] = res
    return res


def _squeeze(c):
    s = []
    for ch in c:
        if not s or s[-1] != ch:
            s.append(ch)
    return "".join(s)


def encode_arabic(tok):
    """Fallback codes for an arabic-script word (short vowels unwritten)."""
    t = clean_arabic(tok)
    if not t:
        return frozenset()
    bare = t[2:] if (t.startswith("ال") and len(t) > 4) else None
    tail = "E" if t[-1] in "ةىاه" else ""
    codes = [""]
    for ch in t:
        alts = ARABIC.get(ch, [""])
        if len(codes) * len(alts) > MAX_CODES:
            alts = alts[:1]
        codes = [c + a for c in codes for a in alts]
    out = set()
    for base in codes:
        if "V" in base:
            first = base.index("V")
            heads = {base[:first] + v + base[first + 1:].replace("V", "")
                     for v in ("a", "o", "")}
        else:
            heads = {base[:1] + v + base[1:] for v in ("a", "o")}
            heads.add(base)
        for s in heads:
            s = _squeeze(re.sub(r"[^A-Zao]", "", s))
            if not s:
                continue
            if not tail and s[-1] == "T":
                s = _squeeze(s[:-1] + "D")
            s += tail
            out.add(s)
            if len(s) > 2 and s[0] == "Y" and s[1] in "ao":
                out.add(s[1:])
    if bare:
        out |= encode_arabic(bare)
    return frozenset(out)


# --------------------------------------------------------------------------
# nicknames, short forms and cross language equivalents
# --------------------------------------------------------------------------

NICK_GROUPS = [
    ("william", "bill", "billy", "will", "willy", "liam", "guillermo",
     "guillaume", "wilhelm", "willem"),
    ("robert", "bob", "bobby", "rob", "robbie", "roberto"),
    ("richard", "rick", "ricky", "dick", "rich", "richie", "ricardo"),
    ("james", "jim", "jimmy", "jamie", "jimmie", "jaime", "jacques"),
    ("john", "johnny", "jon", "jack", "juan"),
    ("joseph", "joe", "joey"),
    ("jose", "pepe", "joselito"),
    ("michael", "mike", "mikey", "mick", "mickey", "mikhail", "miguel",
     "michel", "misha"),
    ("thomas", "tom", "tommy", "tomas"),
    ("charles", "charlie", "chuck", "chas", "carlos", "karl", "carl"),
    ("christopher", "chris", "kit", "cristopher"),
    ("daniel", "dan", "danny", "danilo"),
    ("matthew", "matt", "matty", "mateo"),
    ("anthony", "tony", "antonio", "antoine", "anton"),
    ("andrew", "andy", "drew", "andres", "andre"),
    ("benjamin", "ben", "benny", "benji"),
    ("samuel", "sam", "sammy"),
    ("nicholas", "nick", "nicky", "nico", "nicolas", "nikolas", "niklas"),
    ("theodore", "theo"),
    ("edward", "ed", "eddie", "ted", "teddy", "ned", "eduardo"),
    ("frederick", "fred", "freddie", "freddy", "federico"),
    ("henry", "hank", "harry", "hal", "enrique", "heinrich"),
    ("peter", "pete", "pedro", "pierre", "pietro", "petr"),
    ("steven", "stephen", "steve", "stevie", "esteban", "stefan"),
    ("donald", "don", "donnie"),
    ("gregory", "greg", "gregorio"),
    ("timothy", "tim", "timmy"),
    ("kenneth", "ken", "kenny"),
    ("ronald", "ron", "ronnie"),
    ("patrick", "pat", "paddy", "patricio"),
    ("david", "dave", "davey"),
    ("jonathan", "jon", "jonny"),
    ("francisco", "frank", "paco", "pancho", "cisco", "fran", "francis",
     "francois", "franz"),
    ("elizabeth", "liz", "lizzie", "beth", "betty", "betsy", "eliza",
     "libby", "elisabeth", "isabel"),
    ("katherine", "kate", "katie", "kathy", "cathy", "kay", "kat",
     "catherine", "katarina", "catalina"),
    ("margaret", "maggie", "peggy", "meg", "madge", "marge", "margarita",
     "marguerite", "greta"),
    ("patricia", "patty", "trish", "tricia", "patsy"),
    ("rebecca", "becca", "becky", "becki"),
    ("susan", "sue", "susie", "suzy", "suzie", "susanna"),
    ("dorothy", "dot", "dottie", "dolly"),
    ("jennifer", "jen", "jenny", "jenna", "jennie"),
    ("victoria", "vicky", "vickie", "tori"),
    ("barbara", "barb", "barbie", "babs"),
    ("alexander", "alex", "xander", "sasha", "sanya", "alejandro"),
    ("alexandra", "alex", "sandra", "sasha"),
    ("eugene", "yevgeny", "evgeny", "gene", "zhenya"),
    ("helen", "elena", "helena", "ellen"),
    ("joshua", "josh"), ("jacob", "jake"), ("zachary", "zach"),
    ("vincent", "vince"), ("arthur", "art"), ("raymond", "ray"),
    ("walter", "walt"), ("russell", "russ"), ("gerald", "jerry", "gerry"),
    ("jeffrey", "jeff"), ("philip", "phil", "felipe"), ("douglas", "doug"),
    ("cynthia", "cindy"), ("deborah", "debbie"), ("kimberly", "kim"),
    ("pamela", "pam"), ("teresa", "theresa", "terry", "tess"),
    ("nathaniel", "nathan", "nate"), ("emmanuel", "manny"),
    ("manuel", "manolo"), ("george", "jorge", "georges", "georg"),
    ("lawrence", "larry", "lorenzo", "laurent"),
    ("paul", "pablo", "paolo"),
    # russian short forms that appear as aliases on this kind of list
    ("nikolai", "kolya"), ("anatoly", "tolya"), ("dmitri", "dima"),
    ("vladimir", "vova"),
    # arabic / persian names whose turkish (or other) form no letter rule
    # can reach
    ("muhammad", "mohammed", "muhammet"),
    ("qasim", "kasim"), ("khadija", "hatice", "khadijah"),
    ("zainab", "zeynep", "zaynab"), ("fatima", "fatma"),
    ("aisha", "ayshe", "ayesha", "aishah"), ("amina", "emine"),
    ("samira", "semire"), ("khadija", "hatije"), ("salma", "selme"), ("maryam", "meryem", "mariam"),
    ("uthman", "osman", "othman"), ("jafar", "cafer", "jaafar"),
    ("jafari", "caferi"),
    ("jabouri", "caburi", "jaburi"), ("najjar", "neccar", "nacar"),
    ("ziad", "ziya"), ("saeed", "sait", "said"), ("walid", "velit"),
    ("rashid", "reshit"), ("khalid", "halit", "halid"),
    ("mahmoud", "mahmut"), ("ahmad", "ahmet"), ("hussein", "huseyin"),
    ("anwar", "enver"), ("marwan", "mervan"),     ("amin", "emin"), ("sharif", "sherif"), ("bashar", "beshar"),
    ("nabil", "nebil"), ("salman", "selman"), ("samir", "semir"),
    ("mansour", "mansur"), ("darwish", "dervish", "darwis"),
    ("hashimi", "hashimi"), ("khatib", "hatip", "hatib"),
    ("abbas", "abas"), ("barakat", "bereket"), ("kanaan", "kenan"),
    ("haddad", "haddat"), ("saleh", "salih"), ("salehi", "salihi"),
    ("ghanem", "ganim"), ("awad", "avat"), ("faisal", "faysal"),
    ("hamid", "hamit"),     ("yusuf", "joesoef", "yousuf"), ("sultan", "soeltan"),
]
NICKS = defaultdict(set)
for _g in NICK_GROUPS:
    for _w in _g[1:]:
        NICKS[_w].add(_g[0])

# --------------------------------------------------------------------------
# chinese surname romanisations (pinyin -> wade-giles / cantonese / hokkien)
# --------------------------------------------------------------------------

CN_TABLE = {
    "cai": "cai tsai tsay choi choy chua chuah chai chye tzai",
    "cao": "cao tsao tso chaw cow tow",
    "chen": "chen chan tan chin chun ting chern chern",
    "cui": "cui tsui chui chwee tsuei",
    "dai": "dai tai tay te toy tee",
    "deng": "deng teng tang dang thang then",
    "fan": "fan faan fann huan hoan hwan",
    "feng": "feng fung foong fong phang pang",
    "gao": "gao kao ko go kou gow kow koh kaw",
    "guo": "guo kuo kwok kwock quek kwek kueh koay kok keh",
    "han": "han hon hahn hann",
    "he": "he ho hoh hor hoo",
    "hu": "hu hoo woo oh aw ow oo",
    "huang": "huang hwang wong ooi uy oei whang ng wee bong",
    "jiang": "jiang chiang kong keung chiong cheong kang",
    "li": "li lee lei ly lie lay ree",
    "liang": "liang leung leong neo niu liong nio",
    "lin": "lin lam lim lum ling liem",
    "liu": "liu lau low lew liew lieu lao",
    "lu": "lu loo look luk lok lou",
    "luo": "luo law lo loh lor lowe",
    "ma": "ma mah beh bey mar",
    "pan": "pan poon pun phua phuah ban",
    "peng": "peng pang phang pheng phee",
    "qian": "qian chien chin tsin chee chian",
    "shen": "shen sham sum sim shum",
    "song": "song sung soong seng",
    "tang": "tang tong thong tng",
    "wang": "wang wong ong heng vong",
    "wu": "wu ng goh go ngo woo ou eng",
    "xie": "xie hsieh tse che chia sia seah cheah shia tsia",
    "xu": "xu hsu tsui hui chui koh kho khoo kor shui",
    "yang": "yang yeung yeong yeo yio iu young yong",
    "ye": "ye yeh yip ip yap yeap iap",
    "yuan": "yuan yuen yean oan woon",
    "zeng": "zeng tseng tsang tzeng chng",
    "zhang": "zhang chang cheung cheong teo tiu tio diong jang chong tiong",
    "zhao": "zhao chao chiu chieu jiu",
    "zhou": "zhou chou chow chau chew jow chiew",
    "zhu": "zhu chu choo chee gee jue ju",
}

# --------------------------------------------------------------------------
# name structure
# --------------------------------------------------------------------------

NASAB = {"bin", "ibn", "ben", "bint", "binti", "bn", "b", "ould", "walad",
         "bte", "binte"}
PARTICLES = {"de", "del", "della", "di", "da", "dos", "das", "du", "la", "le",
             "les", "van", "von", "der", "den", "ter", "af", "av"}
ARTICLES = {"al", "el", "ul", "as", "ash", "es", "ad", "az", "ar", "an",
            "at", "asch", "ech", "esh", "ed"}
ABD_WORD = re.compile(r"^abd[aeiou]*[lr]*[aeiou]*$")
PATRONYMIC = re.compile(
    r"^.{3,}(vich|vitch|vic|witch|wicz|witsch|vych|wych|vna|wna|ichna|itchna)$"
    r"|^.{3,}[aeio][vw](ich|itch|isch|ic|icz|itsch|ych|is|ish)$"
    r"|^.{3,}[aeio][vw]na$")

ENT_SUFFIX_PHRASES = [
    ("public", "joint", "stock", "company"),
    ("open", "joint", "stock", "company"),
    ("closed", "joint", "stock", "company"),
    ("limited", "liability", "company"),
    ("free", "zone", "establishment"),
    ("joint", "stock", "company"),
    ("private", "limited", "company"),
    ("public", "limited", "company"),
    ("sociedad", "anonima"),
    ("limited", "liability"),
    ("free", "zone", "company"),
]
ENT_SUFFIX_WORDS = {
    "llc", "lc", "ltd", "limited", "sa", "gmbh", "jsc", "ao", "oao", "zao",
    "pjsc", "ojsc", "co", "company", "corp", "corporation", "inc",
    "incorporated", "fze", "fzllc", "fzco", "establishment", "group",
    "holding", "plc", "ag", "nv", "bv", "srl", "spa", "kft", "pte", "pty",
    "llp", "lp", "gk", "kk", "sas", "sarl", "sl", "oy", "ab", "aps",
    "dd", "doo", "sro", "zoo", "ooo", "pao", "tov", "cjsc", "psc", "wll",
    "sae", "saog", "saoc", "bsc", "qsc", "jscb", "sdnbhd", "bhd", "trust",
    "joint", "stock", "public", "liability", "sociedad", "anonima", "open",
    "closed", "private", "est", "estab", "free", "zone",
}
KNOWN_TYPES = ("individual", "entity", "vessel")
VESSEL_PREFIX = {"mv", "mt", "ms", "ss", "fv", "rv", "tv", "lpg", "lng",
                 "vessel", "the", "tug", "my", "sv", "nb", "mts"}
STOPWORDS = {"the", "and", "of"}
ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6",
         "vii": "7", "viii": "8", "ix": "9", "x": "10"}
NUMWORD = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
           "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}


def split_raw(name):
    name = name.replace("’", "'").replace("‘", "'")
    name = re.sub(r"[,;]", " ", name)
    return [p for p in name.split() if p.strip()]


def article_variants(tok):
    """Spellings of a word with the arabic article attached / removed."""
    out = {tok}
    if "-" in tok:
        head, _, rest = tok.partition("-")
        if len(rest) >= 3 and head in (
                "al", "el", "ul", "as", "ash", "es", "ad", "az", "ar", "an",
                "at", "asch", "a", "ech", "esh", "er", "en", "ed"):
            out.add(rest)
        out.add(tok.replace("-", ""))
    t = tok.replace("-", "")
    out.add(t)
    if len(t) >= 5:
        if t[:2] in ("al", "el", "ul") and len(t) - 2 >= 4:
            out.add(t[2:])
        if t[0] in "aeu":                       # sun letter assimilation
            for ln in (1, 2):
                c = t[1:1 + ln]
                if len(t) - 1 - ln >= 3 and t[1 + ln:1 + 2 * ln] == c:
                    out.add(t[1 + ln:])
    return out


_wc_cache = {}


def word_codes(tok, allow_nick=True):
    key = (tok, allow_nick)
    hit = _wc_cache.get(key)
    if hit is not None:
        return hit
    codes = set()
    for v in article_variants(tok):
        codes |= encode_word(v)
        if allow_nick:
            for root in NICKS.get(v, ()):
                codes |= encode_word(root)
        if v.startswith("mc") and len(v) > 4:
            codes |= encode_word(v[2:])
        elif v.startswith("mac") and len(v) > 5:
            codes |= encode_word(v[3:])
        elif v.startswith("o'") and len(v) > 4:
            codes |= encode_word(v[2:])
    for v in list(codes and article_variants(tok) or ()):
        for a, b in (("yo", "e"), ("io", "e"), ("jo", "e")):
            if a in v[1:]:
                codes |= encode_word(v[0] + v[1:].replace(a, b))
    bare = tok.replace("-", "").replace("'", "")
    if bare.startswith("abd") and len(bare) > 5:
        for i in (3, 4, 5, 6):
            rest = bare[i:]
            if len(rest) >= 3:
                for c in encode_word(rest):
                    codes.add("@" + c)
    res = frozenset(codes)
    _wc_cache[key] = res
    return res


def abd_codes(codes):
    return frozenset("@" + c for c in codes)


class Unit(object):
    __slots__ = ("codes", "raw")

    def __init__(self, codes, raw):
        self.codes = codes
        self.raw = raw

    def __repr__(self):
        return "<%s>" % self.raw


def _tokenize_person(name):
    """-> list of (kind, text) with arabic 'X allah' glued together."""
    toks = []
    for p in split_raw(name):
        if is_arabic(p) or is_cyrillic(p):
            toks.append(("s", p))
            continue
        c = strip_accents(_premap(p.lower())).lower()
        c = re.sub(r"[^a-z'\-\.]", "", c)
        if c.strip(".-'"):
            toks.append(("l", c))
    out = []
    i = 0
    while i < len(toks):
        k, t = toks[i]
        if (k == "s" and i + 1 < len(toks) and toks[i + 1][0] == "s"
                and clean_arabic(toks[i + 1][1]) in ARABIC_ALLAH):
            out.append(("s", t + toks[i + 1][1]))
            i += 2
            continue
        if (k == "l" and t.strip("-.") in ("al", "el", "ul")
                and i + 1 < len(toks) and toks[i + 1][0] == "l"):
            out.append(("l", t.strip("-.") + "-" + toks[i + 1][1]))
            i += 2
            continue
        out.append((k, t))
        i += 1
    return out


def _is_abd(tok):
    """Is this token the 'Abd' of a compound given name?"""
    kind, t = tok
    if kind == "s":
        return clean_arabic(t) in ARABIC_ABD
    flat = t.replace(".", "").replace("-", "").replace("'", "")
    return bool(ABD_WORD.match(flat))


def parse_person(name, script_codes):
    """Return a list of alternative unit lists for a personal name."""
    toks = _tokenize_person(name)
    n = len(toks)
    drop = set()
    ambiguous_b = None
    for idx, (k, t) in enumerate(toks):
        if idx in drop:
            continue
        if k == "l":
            bare = t.replace(".", "").replace("-", "").replace("'", "")
            if bare in NASAB and 0 < idx < n - 1:
                drop.add(idx)
                drop.add(idx + 1)
                if _is_abd(toks[idx + 1]) and idx + 2 < n:
                    drop.add(idx + 2)          # bin Abdul Aziz ...
                if bare in ("b", "ben"):
                    ambiguous_b = idx          # "B." / "Ben" may be a name
            elif len(bare) <= 1:
                drop.add(idx)
            elif PATRONYMIC.match(bare):
                drop.add(idx)
        else:
            ct = clean_arabic(t)
            if ct in ARABIC_NASAB and 0 < idx < n - 1:
                drop.add(idx)
                drop.add(idx + 1)
                if _is_abd(toks[idx + 1]) and idx + 2 < n:
                    drop.add(idx + 2)          # bin Abd al-Aziz ...
            elif is_cyrillic(t) and PATRONYMIC.match(cyr_to_latin(t)):
                drop.add(idx)

    keep = [(i, k, t) for i, (k, t) in enumerate(toks) if i not in drop]
    alt_keep = None
    if ambiguous_b is not None:
        alt = drop - {ambiguous_b, ambiguous_b + 1}
        alt.add(ambiguous_b)                      # read it as a middle initial
        alt_keep = [(i, k, t) for i, (k, t) in enumerate(toks) if i not in alt]
    variants = _units_from(keep, script_codes)
    if alt_keep is not None:
        variants += _units_from(alt_keep, script_codes)
    return variants


def _units_from(keep, script_codes):
    """Build the unit lists for one reading of the token sequence."""
    # particles glue onto the word that follows them (or, when a comma moved
    # them to the end, onto the first word)
    core = []
    trailing = ""
    pending = ""
    for pos, (i, k, t) in enumerate(keep):
        bare = t.replace(".", "").replace("-", "").replace("'", "")
        if k == "l" and bare in PARTICLES:
            if pos == len(keep) - 1 and core:
                trailing = trailing + bare
            else:
                pending += bare
            continue
        core.append((pos, k, t, pending))
        pending = ""

    def build_units(merge_ambiguous):
        units = []
        i = 0
        while i < len(core):
            pos, k, t, pre = core[i]
            if k == "l":
                bare = t.replace(".", "").replace("'", "")
                flat = bare.replace("-", "")
                if (ABD_WORD.match(flat) and i + 1 < len(core)
                        and (merge_ambiguous or flat[-1] not in "aeiou")):
                    nxt = core[i + 1]
                    nraw = nxt[2].replace(".", "").replace("'", "")
                    if nxt[1] == "l":
                        units.append(Unit(abd_codes(word_codes(nraw, False)),
                                          bare + nraw))
                    else:
                        units.append(Unit(abd_codes(script_codes(nxt[2])),
                                          bare + nraw))
                    i += 2
                    continue
                codes = set(word_codes(bare))
                for cut in range(len(pre)):
                    codes |= word_codes(pre[cut:] + flat, False)
                units.append(Unit(frozenset(codes), bare))
            else:
                ct = clean_arabic(t)
                if ct in ARABIC_ABD and i + 1 < len(core):
                    nxt = core[i + 1]
                    units.append(Unit(abd_codes(script_codes(nxt[2])),
                                      t + nxt[2]))
                    i += 2
                    continue
                units.append(Unit(script_codes(t), t))
            i += 1
        if trailing and units:
            u = units[0]
            extra = set()
            for cut in range(len(trailing)):
                extra |= word_codes(trailing[cut:] + u.raw.replace("-", ""),
                                    False)
            units[0] = Unit(u.codes | extra, u.raw)
        return units

    units = build_units(True)
    ambiguous = any(k == "l" and ABD_WORD.match(
        t.replace(".", "").replace("'", "").replace("-", ""))
        and t.replace(".", "").replace("'", "").replace("-", "")[-1] in "aeiou"
        and j + 1 < len(core) for j, (pos, k, t, pre) in enumerate(core))

    variants = [units]
    if ambiguous:
        variants.append(build_units(False))
    # hyphenated compound surnames may be written as two words
    for idx, (pos, k, t, pre) in enumerate(core):
        if k == "l" and "-" in t.strip("-"):
            a, _, b = t.partition("-")
            if len(a) > 2 and len(b) > 2 and idx < len(units):
                split = (units[:idx] + [Unit(word_codes(a, False), a),
                                        Unit(word_codes(b, False), b)] +
                         units[idx + 1:])
                variants.append(split)
    # two adjacent words may be one word on the other side
    if len(units) >= 3:
        for idx in range(len(units) - 1):
            ra, rb = units[idx].raw, units[idx + 1].raw
            if ra.isalpha() and rb.isalpha():
                joined = ra + rb
                variants.append(units[:idx] + [Unit(word_codes(joined, False),
                                                    joined)] + units[idx + 2:])
    return variants


def parse_org(name, is_vessel, cn_map):
    name = re.sub(r"\b([A-Za-z])\s*/\s*([A-Za-z])\b", r"\1\2", name)
    name = name.replace("/", " ")
    toks = []
    for p in split_raw(name):
        c = strip_accents(_premap(p.lower().replace("-", ""))).lower()
        c = re.sub(r"[^a-z0-9&]", "", c)
        if c:
            toks.append(c)
    if is_vessel:
        while len(toks) > 1 and toks[0] in VESSEL_PREFIX:
            toks = toks[1:]
    toks = [t for t in toks if t not in STOPWORDS and t != "&"]
    changed = True
    while changed and len(toks) > 1:
        changed = False
        for phrase in ENT_SUFFIX_PHRASES:
            L = len(phrase)
            for s in range(len(toks) - L + 1):
                if tuple(toks[s:s + L]) == phrase and len(toks) - L >= 1:
                    toks = toks[:s] + toks[s + L:]
                    changed = True
                    break
            if changed:
                break
    body = [t for t in toks if t not in ENT_SUFFIX_WORDS]
    if not body:
        body = toks[:1] or ["x"]
    units = []
    for i, t in enumerate(body):
        if t in ROMAN:
            units.append(Unit(frozenset(["#" + ROMAN[t]]), t))
        elif t in NUMWORD:
            units.append(Unit(frozenset(["#" + NUMWORD[t]]), t))
        elif t.isdigit():
            units.append(Unit(frozenset(["#" + t.lstrip("0")]), t))
        elif i == 0 and t in cn_map:
            units.append(Unit(frozenset("CN:" + c for c in cn_map[t]), t))
        else:
            units.append(Unit(word_codes(t, False), t))
    return [units]


# --------------------------------------------------------------------------
# matching
# --------------------------------------------------------------------------

def units_match(a, b, max_extra=1):
    """Injective correspondence between two lists of name words.  Up to
    `max_extra` words may stay unmatched, and never the leading one, so an
    extra middle or father's name is tolerated while a different first word
    is not."""
    if len(a) > len(b):
        a, b = b, a
    if not a or len(b) - len(a) > max_extra:
        return False
    nb = len(b)
    used = [False] * nb

    def rec(i):
        if i == len(a):
            extra = [j for j in range(nb) if not used[j]]
            return len(extra) <= max_extra and 0 not in extra
        for j in range(nb):
            if used[j] or not (a[i].codes & b[j].codes):
                continue
            used[j] = True
            if rec(i + 1):
                return True
            used[j] = False
        return False

    return rec(0)


def name_match(cust_variants, entry_variants, exact_size, max_extra=1):
    """Number of unmatched words of the best correspondence, or None."""
    for allow in range(max_extra + 1):
        for cu in cust_variants:
            for eu in entry_variants:
                if exact_size:
                    if len(cu) != len(eu):
                        continue
                elif min(len(cu), len(eu)) < 2:
                    continue
                if units_match(cu, eu, allow):
                    return allow
    return None


def dob_compatible(cd, ed):
    if not cd or not ed:
        return True, False
    k = min(len(cd), len(ed))
    ok = cd[:k] == ed[:k]
    return ok, ok


# --------------------------------------------------------------------------
# watchlist preparation
# --------------------------------------------------------------------------

class Entry(object):
    __slots__ = ("uid", "type", "dob", "names", "weak", "stems")

    def __init__(self, uid, typ, dob):
        self.uid = uid
        self.type = typ
        self.dob = dob
        self.names = []
        self.weak = []
        self.stems = set()


def _script_token_list(script):
    """Split a script name, gluing 'X allah'."""
    toks = split_raw(script)
    out = []
    i = 0
    while i < len(toks):
        if (i + 1 < len(toks)
                and clean_arabic(toks[i + 1]) in ARABIC_ALLAH):
            out.append(toks[i] + toks[i + 1])
            i += 2
            continue
        out.append(toks[i])
        i += 1
    return out


def mine_script_table(entries_json):
    """script word -> latin words, learned from the watchlist itself."""
    table = defaultdict(set)
    for e in entries_json:
        script = e.get("script_name") or ""
        if not script:
            if not (is_arabic(e["primary_name"]) or is_cyrillic(e["primary_name"])):
                continue
            script = e["primary_name"]
        forms = [split_raw(script), _script_token_list(script)]
        cands = [e["primary_name"]]
        cands += [a["name"] for a in e.get("aliases", ())
                  if a.get("strength") == "strong"]
        for nm in cands:
            if not is_latin(nm):
                continue
            ltoks = [t for t in split_raw(nm)
                     if len(re.sub(r"[^a-zA-Z]", "", t)) > 1]
            for stoks in forms:
                if len(ltoks) != len(stoks):
                    continue
                for s, l in zip(stoks, ltoks):
                    lc = re.sub(r"[^a-z'\-]", "",
                                strip_accents(_premap(l.lower())).lower())
                    if lc:
                        table["".join(s.split())].add(lc)
                break
    return table


def build(entries_json):
    entries = []
    id_index = defaultdict(list)
    code_index = defaultdict(set)
    script_table = mine_script_table(entries_json)

    present = set()
    for e in entries_json:
        if e["type"] == "entity":
            toks = split_raw(e["primary_name"])
            if toks:
                t = re.sub(r"[^a-z]", "", toks[0].lower())
                if t in CN_TABLE:
                    present.add(t)
    cn_map = defaultdict(set)
    cn_rank = defaultdict(dict)
    for py in present:
        for r, v in enumerate(CN_TABLE[py].split()):
            cn_map[v].add(py)
            if py not in cn_rank[v] or r < cn_rank[v][py]:
                cn_rank[v][py] = r

    _sc_cache = {}

    def script_codes(tok):
        key = "".join(tok.split())
        hit = _sc_cache.get(key)
        if hit is not None:
            return hit
        codes = set()
        for l in script_table.get(key, ()):
            codes |= word_codes(l)
        if is_cyrillic(key):
            codes |= word_codes(cyr_to_latin(key))
            if "ё" in key.lower():               # Fyodor / Fedor, Kiselyov / Kiselev
                codes |= word_codes(cyr_to_latin(key.lower().replace("ё", "е")))
        elif is_arabic(key) and not codes:
            codes |= encode_arabic(key)
        codes = frozenset(codes)
        _sc_cache[key] = codes
        return codes

    for e in entries_json:
        en = Entry(e["uid"], e["type"], (e.get("dob") or "").strip())
        idx = len(entries)
        names = [e["primary_name"]]
        names += [a["name"] for a in e.get("aliases", ())
                  if a.get("strength") == "strong"]
        if e.get("script_name"):
            names.append(e["script_name"])
        seen = set()
        for nm in names:
            if not nm or nm in seen:
                continue
            seen.add(nm)
            if en.type == "individual":
                variants = parse_person(nm, script_codes)
            else:
                variants = parse_org(nm, en.type == "vessel", cn_map)
            if not variants or not variants[0]:
                continue
            if en.type == "entity" and variants[0][0].raw in cn_map:
                en.stems |= cn_map[variants[0][0].raw]
            en.names.append(variants)
            for var in variants:
                for u in var:
                    for c in u.codes:
                        code_index[c].add(idx)
        for a in e.get("aliases", ()):
            if a.get("strength") == "weak":
                if en.type == "individual":
                    v = parse_person(a["name"], script_codes)
                else:
                    v = parse_org(a["name"], en.type == "vessel", cn_map)
                if v and v[0]:
                    en.weak.append(v[0])
        for ident in e.get("ids", ()):
            t = (ident.get("type") or "").strip().lower()
            num = re.sub(r"[\s\-]", "", (ident.get("number") or "")).upper()
            if t and num:
                id_index[(t, num)].append(idx)
        entries.append(en)
    return entries, id_index, code_index, cn_map, script_codes, cn_rank


# --------------------------------------------------------------------------
# screening
# --------------------------------------------------------------------------

def screen(watchlist_path, customers_path, out_path):
    with open(watchlist_path, "r", encoding="utf-8") as fh:
        wl = json.load(fh)
    (entries, id_index, code_index, cn_map, script_codes,
     cn_rank) = build(wl)

    weak_index = defaultdict(set)
    for i, en in enumerate(entries):
        for units in en.weak:
            for u in units:
                for c in u.codes:
                    weak_index[c].add(i)

    with open(customers_path, "r", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))

    out_rows = []
    for row in rows:
        cid = (row.get("customer_id") or "").strip()
        name = (row.get("full_name") or "").strip()
        ctype = (row.get("type") or "").strip().lower()
        cdob = (row.get("dob") or "").strip()
        idt = (row.get("id_type") or "").strip().lower()
        idn = re.sub(r"[\s\-]", "", (row.get("id_number") or "")).upper()

        # ---- Rule 1: identifier
        if idt and idn:
            hits = id_index.get((idt, idn))
            if hits:
                uid = min(entries[i].uid for i in hits)
                out_rows.append((cid, "MATCH", uid))
                continue

        # ---- Rule 2 / 5: name
        reading = {}                 # entry type -> (unit variants, exact)
        if ctype in ("", "individual") or ctype not in KNOWN_TYPES:
            reading["individual"] = (parse_person(name, script_codes), False)
        if ctype in ("", "entity") or ctype not in KNOWN_TYPES:
            reading["entity"] = (parse_org(name, False, cn_map), True)
        if ctype in ("", "vessel") or ctype not in KNOWN_TYPES:
            reading["vessel"] = (parse_org(name, True, cn_map), True)
        cvars = reading.get(ctype or "individual",
                            reading[sorted(reading)[0]])[0]
        cunits = cvars[0]
        ent = reading.get("entity")
        stem_ranks = (cn_rank.get(ent[0][0][0].raw)
                      if ent and ent[0][0] else None)

        cands = set()
        for var in cvars:
            counts = defaultdict(int)
            for u in var:
                hit = set()
                for c in u.codes:
                    s = code_index.get(c)
                    if s:
                        hit |= s
                for ei in hit:
                    counts[ei] += 1
            need = 2 if len(var) >= 2 else 1
            for ei, cnt in counts.items():
                if cnt >= need:
                    cands.add(ei)

        scored = []
        for ei in cands:
            en = entries[ei]
            if en.type not in reading:
                continue
            evars, exact = reading[en.type]
            extra = None
            for ev in en.names:
                q = name_match(evars, ev, exact)
                if q is not None and (extra is None or q < extra):
                    extra = q
                if extra == 0:
                    break
            if extra is None:
                continue
            compat, support = dob_compatible(cdob, en.dob)
            if not compat:
                continue
            rank = 0
            if stem_ranks and en.stems:
                rank = min([stem_ranks.get(p, 9) for p in en.stems] or [9])
            scored.append((0 if support else 1, extra, rank, en.uid))

        # ---- Rule 3: weak alias, needs an identical full date of birth
        if len(cdob) == 10:
            wunits = reading.get("individual", (cvars, False))[0][0]
            whit = defaultdict(int)
            for u in wunits:
                h = set()
                for c in u.codes:
                    s = weak_index.get(c)
                    if s:
                        h |= s
                for ei in h:
                    whit[ei] += 1
            for ei, cnt in whit.items():
                en = entries[ei]
                if en.type not in reading:
                    continue
                if en.dob != cdob:
                    continue
                units_c = wunits if en.type == "individual" else cunits
                for units in en.weak:
                    if len(units) == len(units_c) and units_match(units_c, units):
                        scored.append((0, 0, 0, en.uid))
                        break

        if scored:
            scored.sort()
            out_rows.append((cid, "MATCH", scored[0][3]))
        else:
            out_rows.append((cid, "NO_MATCH", ""))

    with open(out_path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["customer_id", "decision", "matched_uid"])
        for r in out_rows:
            w.writerow(r)
    return out_rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="sanctions screening")
    ap.add_argument("--watchlist", required=True)
    ap.add_argument("--customers", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    screen(args.watchlist, args.customers, args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
