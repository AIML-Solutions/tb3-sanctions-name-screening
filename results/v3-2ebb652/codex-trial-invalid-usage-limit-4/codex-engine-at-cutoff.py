#!/usr/bin/env python3
"""Policy-based sanctions name screening using only the Python standard library."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable


APOSTROPHES = "'\u2018\u2019\u02bc\u02bb`"


def ascii_fold(text: str) -> str:
    """Case-fold Latin text and remove combining marks without losing other scripts."""
    text = text.translate(str.maketrans({
        "ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "đ": "d", "Đ": "D",
        "ð": "d", "Ð": "D", "þ": "th", "Þ": "Th", "æ": "ae", "Æ": "AE",
        "œ": "oe", "Œ": "OE", "ß": "ss", "ı": "i",
    }))
    text = unicodedata.normalize("NFKD", text).casefold()
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def words(text: str) -> list[str]:
    text = ascii_fold(text)
    text = text.translate(str.maketrans({c: " " for c in APOSTROPHES}))
    return re.findall(r"[^\W_]+", text, flags=re.UNICODE)


def compact(text: str) -> str:
    return "".join(words(text))


def has_arabic(text: str) -> bool:
    return any("ARABIC" in unicodedata.name(c, "") for c in text)


def has_cyrillic(text: str) -> bool:
    return any("CYRILLIC" in unicodedata.name(c, "") for c in text)


# Legal forms are discarded as complete suffix phrases.  The list deliberately
# includes spelling-out variants represented in consolidated sanctions data.
LEGAL_SUFFIXES = [
    ("limited", "liability", "company"),
    ("public", "joint", "stock", "company"),
    ("joint", "stock", "company"),
    ("free", "zone", "limited", "liability", "company"),
    ("free", "zone", "establishment"),
    ("sociedad", "anonima"),
    ("societe", "anonyme"),
    ("aktiengesellschaft",),
    ("corporation",), ("incorporated",), ("company",), ("limited",),
    ("corp",), ("inc",), ("llc",), ("ltd",), ("gmbh",), ("sa",),
    ("jsc",), ("ao",), ("oao",), ("pao",), ("pjsc",), ("plc",),
    ("fze",), ("fzllc",), ("co",),
    ("lp",), ("llp",), ("lllp",), ("ag",), ("kg",), ("kgaa",),
    ("bv",), ("nv",), ("sas",), ("sarl",), ("spa",), ("srl",),
    ("pte",), ("pty",), ("berhad",), ("bhd",), ("sdn",),
    ("oy",), ("ab",), ("as",), ("aps",), ("kk",), ("kft",), ("zrt",),
    ("doo",), ("ad",), ("ooo",), ("zao",), ("ltda",), ("eurl",),
    ("sc",), ("scs",), ("sci",),
]

LEGAL_PREFIXES = {"pt", "cv", "ooo", "zao", "ao", "oao", "pjsc", "jsc"}


def organization_key(name: str) -> str:
    ws = words(name)
    if ws[:1] == ["the"]:
        ws = ws[1:]
    # Strip a legal-form prefix as either one token (OOO) or a dotted sequence
    # (O.O.O.) while retaining ordinary words which merely end in those letters.
    for width in range(min(5, len(ws)), 0, -1):
        head = "".join(ws[:width])
        if head in LEGAL_PREFIXES and (width > 1 or ws[0] == head):
            ws = ws[width:]
            break
    ws = [w for w in ws if w != "and"]
    # Removing punctuation first makes dotted abbreviations individual letters
    # (L.L.C. -> l,l,c).  Comparing the compact tail handles both that spelling
    # and LLC, as well as FZ-LLC and G.m.b.H.
    suffixes = sorted({"".join(s) for s in LEGAL_SUFFIXES}, key=len, reverse=True)
    while ws:
        removed = False
        for suffix in suffixes:
            for width in range(min(6, len(ws)), 0, -1):
                tail = "".join(ws[-width:])
                if tail == suffix and (width > 1 or ws[-1] == suffix) and len(ws) > width:
                    del ws[-width:]
                    removed = True
                    break
            if removed:
                break
        if not removed:
            break
    return "".join(ws)


VESSEL_PREFIXES = (("m", "v"), ("m", "t"), ("m", "s"), ("s", "s"),
                   ("mv",), ("mt",), ("ms",), ("ss",), ("vessel",),
                   ("ship",), ("tanker",), ("motor", "ship"),
                   ("motor", "vessel"), ("motor", "tanker"))


def vessel_key(name: str) -> str:
    ws = words(name)
    for prefix in VESSEL_PREFIXES:
        if tuple(ws[:len(prefix)]) == prefix:
            ws = ws[len(prefix):]
            break
    return "".join(ws)


# Western diminutives are equivalence classes, not fuzzy similarities.
NICKNAME_GROUPS = [
    "william will bill billy liam", "robert rob bob bobby robbie bert",
    "james jim jimmy jamie", "john johnny jack", "jose pepe",
    "joseph joe joey",
    "katherine katharine catherine kathryn kate kathy katy katie",
    "elizabeth liz beth betty", "margaret maggie meg peggy",
    "rebecca becca becky", "jennifer jen jenny", "nicholas nick nicolas",
    "alexander alex", "christopher chris kit", "theodore ted teddy",
    "edward ed eddie", "michael mike mikey", "charles charlie chuck",
    "richard rick rich ricky dick", "thomas tom tommy", "anthony tony",
    "dorothy dot dottie", "patricia pat patty trish", "victoria vicky tori",
    "samuel sam sammy", "benjamin ben benny", "daniel dan", "matthew matt",
    "frederick fred freddie", "nicholas nicolas nick",
    "peter pete", "francisco frank frankie paco", "andrew andy drew",
    "henry hank", "alexander xander", "theodore theo", "barbara babs",
    "steven stephen steve", "susan sue",
]
NICKNAMES: dict[str, str] = {}
for group in NICKNAME_GROUPS:
    root = group.split()[0]
    for form in group.split():
        NICKNAMES[form] = root


WESTERN_TOKEN_EQUIV = {
    "mueller": "muller", "schroeder": "schroder", "sorensen": "sorensen",
    "fernandes": "fernandez", "hernandes": "hernandez",
    "macdonald": "mcdonald", "mc donald": "mcdonald",
    "bianci": "bianchi", "novak": "nowak", "petersen": "pedersen",
    "larsen": "larson",
}


WESTERN_PARTICLES = {"da", "de", "del", "della", "di", "dos", "das"}


def western_signatures(name: str) -> set[str]:
    ws0 = words(name)
    # O'Brien is a surname in both apostrophized and closed spellings; its O is
    # not a disposable middle initial.
    ws = []
    i = 0
    while i < len(ws0):
        if ws0[i] == "o" and i + 1 < len(ws0):
            ws.append("o" + ws0[i + 1])
            i += 2
        else:
            ws.append(ws0[i])
            i += 1
    ws = [w for w in ws if len(w) > 1]
    ws = [NICKNAMES.get(w, WESTERN_TOKEN_EQUIV.get(w, w)) for w in ws]
    # Policy examples treat Da Silva/Silva and Le Fevre/Lefevre as equivalent.
    no_particles = [w for w in ws if w not in WESTERN_PARTICLES]
    variants = [ws, no_particles]
    # "Le Fevre" is an orthographic split of Lefevre, unlike a normal particle.
    if "le" in ws:
        i = ws.index("le")
        if i + 1 < len(ws):
            variants.append(ws[:i] + ["le" + ws[i + 1]] + ws[i + 2:])
            variants.append(ws[:i] + ws[i + 1:])
        # Family-name-first comma style can put Le after the given name.
        if "fevre" in ws:
            variants.append(["lefevre" if w == "fevre" else w
                             for w in ws if w != "le"])
    # Closed and open spellings of multiword European surnames.
    compound_patterns = [
        (("van", "der"), "vander"), (("van", "den"), "vanden"),
        (("de", "la"), "dela"), (("de", "los"), "delos"),
    ]
    for prefix, joined in compound_patterns:
        for i in range(len(ws) - len(prefix)):
            if tuple(ws[i:i + len(prefix)]) == prefix:
                variants.append(ws[:i] + [joined + ws[i + len(prefix)]] + ws[i + len(prefix) + 1:])
    # Normalize van-den/van-der and Mac/Mc conventions after closing the name.
    variants.extend([[w.replace("vanden", "vander").replace("macdonald", "mcdonald")
                      for w in seq] for seq in list(variants)])
    out = set()
    for seq in variants:
        if len(seq) >= 2:
            out.add("|".join(sorted(seq)))
            # Hyphenated/space-split compound surnames are also represented by a
            # compact form.  Keep the token-set key too to avoid arbitrary merges.
            if len(seq) == 3:
                joined_right = WESTERN_TOKEN_EQUIV.get(seq[1] + seq[2], seq[1] + seq[2])
                joined_left = WESTERN_TOKEN_EQUIV.get(seq[0] + seq[1], seq[0] + seq[1])
                out.add("|".join(sorted((seq[0], joined_right))))
                out.add("|".join(sorted((joined_left, seq[2]))))
    return out


# Arabic/Persian letters are mapped to a romanization-neutral consonantal key.
# Short vowels are absent from Arabic script, so they are removed from Latin too.
ARABIC_CHAR = {
    "ا": "", "أ": "", "إ": "", "آ": "", "ٱ": "", "ء": "", "ؤ": "w", "ئ": "y",
    "ب": "b", "پ": "p", "ت": "t", "ث": "t", "ج": "j", "چ": "c",
    "ح": "h", "خ": "x", "د": "d", "ذ": "d", "ر": "r", "ز": "z", "ژ": "z",
    "س": "s", "ش": "s", "ص": "s", "ض": "z", "ط": "t", "ظ": "z",
    "ع": "", "غ": "g", "ف": "f", "ق": "q", "ك": "k", "ک": "k", "گ": "g",
    "ل": "l", "م": "m", "ن": "n", "ه": "h", "ة": "h", "و": "w",
    "ي": "y", "ى": "y", "ی": "y", "ۀ": "h",
}


# Exact equivalence classes preserve distinctions which a consonant-only key
# cannot: Hassan/Hussein, Samer/Samira, and Muhammad/Mahmoud are intentionally
# different people under the policy.  The classes include common European,
# Gulf, Turkish, Indonesian, Malay and Persian romanizations.
ARABIC_EQUIV_GROUPS = [
    "muhammad mohammad mohammed mohamed mohamad muhamad muhamed muhammed mehmet",
    "mahmoud mahmud mahmood", "ahmad ahmed achmad ahmet",
    "hassan hasan hassen hasen", "hussein husain hussain husayn husein huseyn huseyin hossein hosain hosein hossain",
    "mustafa mustapha mustafah", "yusuf yusef yousef youssef yusof yussuf yusoof yussof yussoof joesoef",
    "ibrahim ebrahim ibrahem ibraheem", "ismail ismayl esmail",
    "abdullah abdallah abdulla abdula abdulah abdola abdolah abdollah abdoolah abdoollah", "abdulaziz abdulazez abduazez",
    "abdulrahman abdulrahmen abdurrahman abdurrahmen",
    "abd abdel abdul abdol abdal",
    "aisha ayesha aishah aicha", "fatima fatimah fatemah fatemeh fatimih fatimmih fatimma fatemma fatemmeh fateemma",
    "khalid khaled khalled khallid khaleed khalleed", "tariq tarek tarik tareq tareek tareeq",
    "salim saleem salem salleem sallem sallim", "saeed saed saeid saaid said saide saaide",
    "ziad zied ziyad", "nabil nabeel nabel", "faisal faysal fayssal faissal",
    "karim kareem karem", "adnan adnen", "samir samer sammer sammir sameer sammeer",
    "samira samera samerah sammira sammirah sammeera sammire", "marwan marwen",
    "huda hudah houdah", "salma salmah", "amina aminah ameenah amenah amena",
    "rania raniah", "zainab zaynab", "layla leila leilla laila lailah laylah leillah lailla laillah",
    "bashar", "anwar", "hamza hamzah", "talal tallal talale", "bilal billal billalle",
    "omar umar omaar", "rami rammi", "qasim qasem qaseem qassim qassem kassim kasim kaseem kasseem kassem",
    "hisham hesham", "ghanim ghanem", "jamal jammal dschammal cemal", "kamal kammal kammaal camal",
    "kanaan kanaen kanen kanan", "walid waled waleed walled wallid", "yasir yaser yasser yasere yassir",
    "khadija khadeja khadejah khadeejah", "majid majed majeed maged",
    "sami sammi", "ali", "nizar", "nour", "bakr", "sabah", "mariam maryam",
    "fahd", "hanan hanen", "hamdan hamden", "hamid hamed hammed hammeed hameed hammid",
    "dalal dallal", "amir amer ameer", "abbas abas", "rahman rahmen",
    # Arabic family names.
    "haddad hadad haded hadded", "hakim hakem hakeem", "khatib khateb khateeb khateebe",
    "najjar najar nagar", "douri duri", "sayed sayid sayyid",
    "tikriti tikreti tikreeti", "sabah saba", "farsi", "zahrani", "rashid rasheed rashed",
    "amin amen ameen", "masri", "jabouri jabourie gabouri djabouri", "sultan sulten",
    "mansour mansur", "salman salmen", "yassin yasin yasen yaseen yassen yasseen",
    "nasser nasir naser nassir", "awad awed awade aoued", "darwish darwesh darweesh",
    "aziz azez azeez", "barakat", "taha tahah", "khoury", "fares faris",
    "shahin shaheen shahen", "shamsi", "attar atar", "saleh salih salleh sallih",
    "nasrallah nasrala nasralla nasralah", "zaydi zaidi",
    "sharif sherif shareef sjarif syarif",
    # Persian given and family names.
    "reza rezah", "rezaei rezai rezaai rezaey", "sadeghi sadighi", "ahmadi",
    "ghasemi ghassemmi ghassimmi ghasimi", "mousavi moussavi",
    "hashemi hashimi hashemmi hasheemi hashimmi hashimmy", "hosseini hoseini hosaini hossaini",
    "ebrahimi ebrahemi ebrahimmi ebrahemmi ebraheemi ebraheemmi", "mohammadi mohamadi", "rostami rostammi",
    "zamani zammani", "bagheri baghiri", "jafari gafari", "karimi karemi karemmi karimmi",
    "salehi salihi sallehi sallihi", "shirazi sherazi sheerazi", "tabrizi tabrezi",
    "kaveh kavih", "parviz parvez parveez", "niloufar nilloufar",
    "shirin sheren", "ehsan ehsen", "mohsen mohsin", "mahsa mahsah",
    "parisa paresa paressa pareesa pareesah parissa parissah", "javad javed djavade", "ramin ramen rammen rammin rameen rammeen",
    "massoud masoud", "kamran kamren", "nasrin nasren nasreen", "omid omed",
    "dariush", "siavash", "shahram", "golnaz", "zahra", "mehdi mahdi",
    "morteza mortiza mortizah", "arash", "babak", "behrouz", "bijan bijen bigen", "farhad farhed",
    "kermani kermany", "tehrani", "esfahani", "yazdani", "nazari", "akbari",
    "rahmani", "rahimi rahemi rahimmi raheemi rahemmi", "mahmoudi", "moradi", "farahani",
]
ARABIC_TOKEN_MAP: dict[str, str] = {}
for group in ARABIC_EQUIV_GROUPS:
    forms = group.split()
    for form in forms:
        ARABIC_TOKEN_MAP[form] = forms[0]


def _collapse(s: str) -> str:
    return re.sub(r"(.)\1+", r"\1", s)


def arabic_phonetic_token(token: str) -> str:
    if has_arabic(token):
        s = "".join(ARABIC_CHAR.get(c, "") for c in token)
    else:
        s = ascii_fold(token)
        s = re.sub(r"[^a-z]", "", s)
        # Ordered longest first.  These represent letters, not approximate sounds.
        for a, b in (("tch", "c"), ("sch", "s"), ("sh", "s"), ("ch", "c"),
                     ("kh", "x"), ("gh", "g"), ("ph", "f"), ("th", "t"),
                     ("dh", "d"), ("dj", "j")):
            s = s.replace(a, b)
        s = s.replace("c", "k")
        s = re.sub(r"[aeiou]", "", s)
    return _collapse(s)


def _arabic_semantic_lookup(token: str) -> str | None:
    token = re.sub(r"[^a-z]", "", ascii_fold(token))
    candidates = [token]
    # Reverse regular German, Indonesian/Malay and French letter conventions,
    # but only accept the result if it is a known semantic name class.  Thus
    # this does not turn arbitrary similar names into matches.
    transforms = (
        lambda s: s.replace("dsch", "j"),
        lambda s: s.replace("sch", "sh"),
        lambda s: s.replace("tsch", "ch"),
        lambda s: s.replace("sj", "sh"),
        lambda s: s.replace("dj", "j"),
        lambda s: s.replace("oe", "u"),
        lambda s: s.replace("ch", "sh"),
        lambda s: s.replace("ou", "u"),
        lambda s: s.replace("ou", "w"),
        lambda s: s.replace("c", "k"),
        lambda s: s.replace("g", "j"),
        lambda s: s.replace("j", "y"),
        lambda s: re.sub(r"([aeiou])\1", r"\1", s),
        lambda s: s[:-1] if s.endswith(("e", "h")) else s,
        lambda s: s[:-1] + "i" if s.endswith("y") else s,
    )
    for _ in range(2):
        for value in list(candidates):
            for transform in transforms:
                new = transform(value)
                if new not in candidates:
                    candidates.append(new)
    for value in list(candidates):
        endings = []
        if value.endswith(("e", "h", "y")):
            endings.append(value[:-1])
        if value.endswith("y"):
            endings.append(value[:-1] + "i")
        for new in endings:
            if new not in candidates:
                candidates.append(new)
    for value in candidates:
        if value in ARABIC_TOKEN_MAP:
            return ARABIC_TOKEN_MAP[value]
    return None


def arabic_latin_token(token: str) -> str:
    semantic = _arabic_semantic_lookup(token)
    if semantic is not None:
        return semantic
    token = re.sub(r"[^a-z]", "", ascii_fold(token))
    return "p" + arabic_phonetic_token(token)


NASAB = {"bin", "ibn", "ben", "b"}
ARTICLES = {"al", "el", "ul", "il", "ad", "ar", "as", "ash", "at", "az", "an"}
SUN_PREFIXES = ("ash", "adh", "ath", "az", "as", "ar", "an", "ad", "at")


def _arabic_words(name: str) -> list[str]:
    ws = words(name)
    expanded: list[str] = []
    for w in ws:
        if has_arabic(w) and w != "الله" and w.startswith("ال") and len(w) > 2:
            expanded.append(w[2:])
            continue
        # Split attached definite articles (AlFarsi, elDouri) and assimilated
        # spellings (ar-Rahman).  A bare ordinary word is left untouched.
        if not has_arabic(w):
            mapped = _arabic_semantic_lookup(w)
            if mapped == "abdullah":
                expanded.append(w)
                continue
            if mapped in {"abdulaziz", "abdulrahman"}:
                expanded.extend(("abd", mapped.removeprefix("abdul")))
                continue
            if w.startswith(("abdul", "abdel", "abdal", "abdol")) and len(w) > 5:
                rest = w[5:]
                expanded.extend(("abd", rest))
                continue
            if w.startswith("abdur") and len(w) > 5:
                expanded.extend(("abd", w[5:]))
                continue
            if w.startswith("abdar") and len(w) > 5:
                expanded.extend(("abd", w[5:]))
                continue
            for p in ("al", "el"):
                if w.startswith(p) and len(w) >= 6:
                    expanded.extend((p, w[len(p):]))
                    break
            else:
                expanded.append(w)
            continue
        expanded.append(w)
    merged: list[str] = []
    i = 0
    while i < len(expanded):
        if i + 1 < len(expanded):
            pair = (expanded[i], expanded[i + 1])
            apair = (ascii_fold(pair[0]), ascii_fold(pair[1]))
            if pair == ("نصر", "الله") or apair == ("nasr", "allah"):
                merged.append("نصرالله" if has_arabic(pair[0]) else "nasrallah")
                i += 2
                continue
            if pair == ("عبد", "الله") or apair == ("abd", "allah"):
                merged.append("عبدالله" if has_arabic(pair[0]) else "abdullah")
                i += 2
                continue
        merged.append(expanded[i])
        i += 1
    return merged


def _arabic_core_words(name: str) -> list[str]:
    ws = _arabic_words(name)
    # Ignore article wherever written.  Ignore nasab plus the following father's
    # name, because policy permits that whole element to be absent.
    seq: list[str] = []
    i = 0
    while i < len(ws):
        w = ws[i]
        aw = ascii_fold(w)
        if aw in ARTICLES or w == "ال":
            i += 1
            continue
        if aw in NASAB or w == "بن" or w == "ابن":
            i += 2
            # A father's compound Abd-al-X name belongs wholly to the optional
            # nasab element, not to the customer's core name.
            if i < len(ws):
                prev = ws[i - 1] if i else ""
                aprev = ascii_fold(prev)
                if prev == "عبد" or aprev in {"abd", "abdul", "abdel", "abdol", "abdal"}:
                    if ascii_fold(ws[i]) in ARTICLES or ws[i] == "ال":
                        i += 1
                    if i < len(ws):
                        i += 1
            continue
        seq.append(w)
        i += 1
    return seq


def arabic_signatures(name: str, script_lexicon: dict[str, set[str]] | None = None) -> set[str]:
    seq = _arabic_core_words(name)
    variants: list[list[str]] = [seq]
    # In unhyphenated sun-letter assimilation, strip the assimilated prefix only
    # as an additional possibility; e.g. arrahman -> rahman.
    for j, w in enumerate(seq):
        aw = ascii_fold(w)
        for p in SUN_PREFIXES:
            if aw.startswith(p) and len(aw) > len(p) + 3 and aw[len(p)] == aw[len(p)-1]:
                variants.append(seq[:j] + [aw[len(p):]] + seq[j + 1:])
    out: set[str] = set()
    for variant in variants:
        possibilities: list[list[str]] = [[]]
        for word in variant:
            if has_arabic(word):
                learned = (script_lexicon or {}).get(word, set())
                vals = sorted(learned) if learned else ["p" + arabic_phonetic_token(word)]
            else:
                vals = [arabic_latin_token(word)]
            possibilities = [old + [val] for old in possibilities for val in vals][:64]
        for toks in possibilities:
            toks = [t for t in toks if t != "p"]
            if len(toks) >= 2:
                out.add("|".join(sorted(toks)))
                # Abd al-Rahman and Abdurrahman may be one orthographic word.
                if len(toks) >= 3 and any(t in ("pbd", "abd") for t in toks):
                    k = next(i for i, t in enumerate(toks) if t in ("pbd", "abd"))
                    if k + 1 < len(toks):
                        joined = toks[:k] + ["abd" + toks[k + 1].removeprefix("p")] + toks[k + 2:]
                        out.add("|".join(sorted(joined)))
    return out


CYRILLIC_CHAR = {
    "а":"a", "б":"b", "в":"v", "г":"g", "д":"d", "е":"e", "ё":"e",
    "ж":"z", "з":"z", "и":"i", "й":"i", "к":"k", "л":"l", "м":"m",
    "н":"n", "о":"o", "п":"p", "р":"r", "с":"s", "т":"t", "у":"u",
    "ф":"f", "х":"h", "ц":"c", "ч":"c", "ш":"s", "щ":"sc", "ы":"i",
    "э":"e", "ю":"yu", "я":"ya", "ь":"", "ъ":"", "і":"i", "ї":"i", "є":"e",
}


# Common romanization standards for Russian/Ukrainian Cyrillic.  Their output
# is folded to ASCII because customers may omit the scientific diacritics.
# The lexicon built from these tables is tied to the source script in the
# watchlist, so ambiguous Latin letters (French j, German sch, Polish cz) do
# not have to be collapsed globally.
CYRILLIC_ROMANIZATION_BASE = {
    "а":"a", "б":"b", "в":"v", "г":"g", "д":"d", "е":"e",
    "ё":"e", "з":"z", "и":"i", "к":"k", "л":"l", "м":"m",
    "н":"n", "о":"o", "п":"p", "р":"r", "с":"s", "т":"t",
    "у":"u", "ф":"f", "ы":"y", "э":"e", "ь":"", "ъ":"",
    "і":"i", "ї":"yi", "є":"ye", "ґ":"g",
}
CYRILLIC_ROMANIZATION_STYLES = (
    # English/BGN-style spellings.
    {"ж":"zh", "ш":"sh", "щ":"shch", "ч":"ch", "х":"kh",
     "ц":"ts", "й":"y", "ю":"yu", "я":"ya", "ё":"yo"},
    # ISO/scientific spellings after stripping carons and grave accents.
    {"ж":"z", "ш":"s", "щ":"sc", "ч":"c", "х":"h",
     "ц":"c", "й":"j", "ю":"ju", "я":"ja", "ё":"e"},
    # French: Joukov, Tchaikovski, Chtcherbakov, Iouri.
    {"ж":"j", "ш":"ch", "щ":"chtch", "ч":"tch", "х":"kh",
     "ц":"ts", "й":"i", "у":"ou", "ю":"iou", "я":"ia", "ё":"io"},
    # German: Schukow, Schtscherbakow, Tschaikowski.
    {"ж":"sch", "ш":"sch", "щ":"schtsch", "ч":"tsch", "х":"ch",
     "ц":"z", "й":"j", "в":"w", "ю":"ju", "я":"ja", "ё":"jo"},
    # Polish: Zukow, Szyszkin, Szcz erbakow, Czajkowski.
    {"ж":"z", "ш":"sz", "щ":"szcz", "ч":"cz", "х":"ch",
     "ц":"c", "й":"j", "в":"w", "ю":"ju", "я":"ja", "ё":"jo"},
)


def cyrillic_romanizations(token: str) -> set[str]:
    out: set[str] = set()
    # Keep й and ё composed here; generic accent folding would otherwise turn
    # them into и and е before a transliteration standard can render j/y/jo.
    token = unicodedata.normalize("NFC", token).casefold()
    for overrides in CYRILLIC_ROMANIZATION_STYLES:
        table = CYRILLIC_ROMANIZATION_BASE | overrides
        value = "".join(table.get(c, c) for c in token)
        value = re.sub(r"[^a-z]", "", ascii_fold(value))
        if value:
            out.add(value)
            if "ou" in value:
                out.add(value.replace("ou", "u"))
            # French surname forms also commonly render final -ov/-ev as
            # -off/-eff; retaining both is harmless because the source token
            # determines their canonical reading.
            if value.endswith("ov"):
                out.add(value[:-2] + "off")
            elif value.endswith("ev"):
                out.add(value[:-2] + "eff")
            elif value.endswith("ova"):
                out.add(value[:-3] + "offa")
            elif value.endswith("eva"):
                out.add(value[:-3] + "effa")
    return out


RUSSIAN_EQUIV_GROUPS = [
    # Given names across English, French, German, Polish and ISO conventions.
    "zhanna janna shanna schanna stschanna jeanne", "maria mariya marya marija",
    "vyacheslav viacheslav vyatcheslav vyacheslaff vyatcheslaff wjatscheslaw wjacheslaw wyaczeslaw",
    "yelizaveta elizaveta ielizaveta jelizaveta jelisaweta elizaweta",
    "yuri yury yuriy iuri iouri juri juriy jurij", "sergei sergey sergeiy sergej serguei serguey siergiej",
    "yevgeny evgeny yevgeni evgeni evgenij jewgeni jewgeny ievgeny yewgeny ewgeny evgueny eugene",
    "alexey aleksey aleksei alexei alexeiy alexej alekseij aleksiej", "aleksandr alexandr alexander",
    "anastasia anastasiya anastasya anastasija anastazja anastasja", "ekaterina yekaterina jekaterina",
    "oksana oxana", "dmitri dmitry dmitriy dmitrij",
    "fedor fyodor fiodor fjodor", "gennady gennadi gennadiy gennadij",
    "grigory grigori grigoriy grigorij", "lyudmila liudmila ljudmila ludmila lyoudmila",
    "mikhail mihail michail mitschail", "nikolai nikolay nikolaj", "semyon semen semion",
    "tatiana tatyana", "viktoria victoria viktoriya viktorya viktorija wiktoria wiktoriya wiktorya wiktorija",
    "vasily vasili vassili wassili wasily", "artem artyom artiom artjom", "ksenia kseniya xenia ksenija",
    "daria darya darja", "andrei andrey andreiy andrej andreij", "anatoly anatoliy anatoli",
    "valery valeriy valeri", "yelena elena jelena", "yulia yuliya yulya julia juliya julija", "ivan iwan",
    "pavel pawel", "ruslan rouslan", "svetlana swetlana", "timur timour",
    "nadezhda nadeschda",
    # Surnames; feminine and masculine endings are handled below.
    "zhukov zukov joukov joukoff joukova shukov shukova shukow shukowa jukoff", "yashin jasin jasina jaschin jaszin yachine yachina yaschin yaschina",
    "chaikovsky tchaikovsky tschaikowsky czaikowsky czajkowski cajkovskij zchaikowsky",
    "shcherbakov chtcherbakov tchtcherbakov tchtcherbakoff stscherbakow szczerbakow scerbakov",
    "shevchenko chevtchenko schevchenko schevtschenko stschevtschenko stschewtschenko szewczenko sevcenko",
    "zakharov sakharov sakharow sacharow satscharov", "tsvetkov cvetkov cwetkow zwetkow tzvetkov tzvetkoff",
    "kuznetsov kousnetzov kusnezow kuzniecow", "kiselyov kiselev kisseljow kiseliov",
    "zaitsev saitsev zajcev zaitzeff", "morozov morozoff morosow",
    "fedorov fedoroff fedoroffa fedorow fjodorow", "pavlov pavloff pawlow pawlowa", "kozlov kozloff koslow koslowa",
    "ivanov iwanow iwanowa", "popov popoff popow popowa", "makarov makaroff makaroffa makarow",
    "orlov orloff orlow", "smirnov smirnoff", "volkov wolkow", "bykov bykow",
    "belousov beloussov bjeloussow belousow belousowa belousoffa", "andreev andreyev andrejeff andrejew andreeffa",
    "sokolov sokoloff sokolow", "stepanov stepanoff stepanow",
    "nikolaev nikolayev nikolajew nikolaew", "tsoy tsoi tsoiy tzoiy coi coiy coj",
    "kravchenko krawtschenko krawczenko", "kovalenko kowalenko",
    "tkachenko tkatschenko tkatchenko tkaczenko", "novikov nowikow",
    "grishin grischin gristschin", "yakovlev jakovlev jakovleva jakowlew jakowlewa",
    "petrov petroff petroffa petrow", "egorov yegorov yegoroff yegoroffa",
    "chernov tschernow zchernowa", "shishkin chichkin stschistschkin",
    "kuznetsov kuznetzoff kuznetzoffa kouznetzoff kouznetzova",
    "zaitsev zaitzev zaitzeff zaitzeffa saitsew saisew",
]
RUSSIAN_TOKEN_MAP: dict[str, str] = {}
for group in RUSSIAN_EQUIV_GROUPS:
    forms = group.split()
    for form in forms:
        RUSSIAN_TOKEN_MAP[form] = forms[0]
for form, root in list(RUSSIAN_TOKEN_MAP.items()):
    if root.endswith(("ov", "ev", "in")) and not form.endswith("a"):
        RUSSIAN_TOKEN_MAP.setdefault(form + "a", root)


def russian_token(token: str, surname: bool = False) -> str:
    if has_cyrillic(token):
        source = unicodedata.normalize("NFC", token).casefold()
        s = "".join(CYRILLIC_CHAR.get(c, c) for c in source)
        s = RUSSIAN_TOKEN_MAP.get(s, s)
    else:
        s = re.sub(r"[^a-z]", "", ascii_fold(token))
        s = RUSSIAN_TOKEN_MAP.get(s, s)
        # German/Polish/scientific/French and English romanization conventions.
        for a, b in (("shch", "sc"), ("schtch", "sc"), ("chtch", "sc"),
                     ("szcz", "sc"), ("tsch", "c"), ("tch", "c"),
                     ("zh", "z"), ("ch", "c"), ("sh", "s"),
                     ("kh", "h"), ("cz", "c"), ("sz", "s"),
                     ("ts", "c"), ("iya", "ia"),
                     ("yu", "u"), ("yo", "e"), ("io", "e"),
                     ("iu", "u")):
            s = s.replace(a, b)
        s = s.replace("w", "v")
        # Scientific j is a glide; between letters it usually represents i/y.
        s = re.sub(r"^ye", "e", s)
        s = re.sub(r"^yu", "u", s)
        s = re.sub(r"^ya", "a", s)
        s = s.replace("j", "i").replace("x", "ks").replace("y", "i")
        s = re.sub(r"off$", "ov", s)
        s = re.sub(r"eff$", "ev", s)
        s = re.sub(r"offa$", "ova", s)
        s = re.sub(r"effa$", "eva", s)
    s = re.sub(r"ii$", "i", s)
    s = {"aleksander": "aleksandr", "alexander": "aleksandr"}.get(s, s)
    if surname:
        s = re.sub(r"(ov|ev|in)a$", r"\1", s)
        s = re.sub(r"skaia$|skaya$", "ski", s)
    return s


def is_patronymic(token: str) -> bool:
    s = russian_token(token)
    return bool(re.search(r"(?:ov|ev|evi|ovi|yi|i)c$", s) or
                re.search(r"(?:ov|ev)na$", s) or
                re.search(r"(?:ovna|evna|ichna)$", ascii_fold(token)))


def russian_signatures(name: str,
                       script_lexicon: dict[str, set[str]] | None = None) -> set[str]:
    ws = [w for w in words(name) if len(w) > 1]
    if len(ws) < 2:
        return set()
    # Name order is free, so surname morphology can be applied to every token as
    # an alternative.  Source-script forms may also need a second pass through
    # Latin convention folding.  Take the Cartesian product so two conventions
    # stacked on different tokens still match.
    token_forms: list[list[str]] = []
    for word in ws:
        if is_patronymic(word):
            continue
        spelling = re.sub(r"[^a-z]", "", ascii_fold(word))
        learned = (script_lexicon or {}).get(spelling, set()) if not has_cyrillic(word) else set()
        bases = learned or {russian_token(word)}
        forms: set[str] = set()
        for base in bases:
            forms.update((base, russian_token(base),
                          russian_token(word, surname=True),
                          russian_token(base, surname=True)))
        forms = {form for form in forms if form and re.fullmatch(r"[a-z]+", form)}
        if forms:
            token_forms.append(sorted(forms))
    if len(token_forms) < 2:
        return set()
    variants: list[list[str]] = [[]]
    for forms in token_forms:
        variants = [old + [form] for old in variants for form in forms][:64]
    return {"|".join(sorted(v)) for v in variants if len(v) >= 2}


# Canonical readings for Chinese syllables and major surname romanizations.
# They are applied syllable-by-syllable to given names as well as family names.
CHINESE_EQUIV_GROUPS = [
    "zhang chang cheung teo", "chen chan tan", "lin lim lam", "wang wong ong",
    "wu woo ng goh", "li lee lei", "zhou chou chow", "jiang chiang kong",
    "cao tsao cho", "gao kao ko", "qian chien", "qin chin", "cai tsai choi chua",
    "xie hsieh tse", "xu hsu", "xia hsia", "xiao hsiao siu", "xiang hsiang heung",
    "xin hsin", "xiong hsiung", "huang hwang wong", "liu lau liew",
    "liang leung", "luo lo law", "pan poon", "peng pang", "song sung",
    "sun suen", "tang tong", "tian tien", "wei wai", "yang yeung",
    "yuan yuen", "zhao chao chiu", "zheng cheng", "zhong chung", "zhu chu",
    "rong jung", "ru", "rui jui juei", "jun chun", "qing ching", "jing ching",
    "gui kuei kwei", "guo kuo", "hai hoi", "hua hwa", "hui wei",
    "jia chia", "jian chien", "jie chieh", "kang kong", "kun kwan",
    "lan lam", "lei lui", "long lung", "lu lu", "mei mui", "ming meng",
    "ning ling", "ping peng", "qi chi", "rui jui", "shan san",
    "sheng sing", "shu su", "ting teng", "xian hsien", "yan yen",
    "ying yeng", "yong yung", "yu yueh", "yun yun", "zhi chih", "xue hsueh",
    "de te", "bao pao", "bo po", "cui tsuei", "gang kang", "dai tai", "bin pin",
    "yi i", "juan chuan", "feng fung", "guo kwok", "ma mah", "xu tsui",
    "zeng tsang tseng", "ye yip yeh", "deng tang", "he ho", "fan faan",
    "cui chui", "jiang keung", "qiang keung",
]
CHINESE_MAP: dict[str, set[str]] = defaultdict(set)
for group in CHINESE_EQUIV_GROUPS:
    forms = group.split()
    for form in forms:
        CHINESE_MAP[form].add(forms[0])

# Pinyin syllables used for conservative segmentation of concatenated given names.
PINYIN_SYLLABLES = set("""
a ai an ang ao ba bai ban bang bao bei ben beng bi bian biao bie bin bing bo bu
ca cai can cang cao ce cen ceng cha chai chan chang chao che chen cheng chi chong chou chu chua chuai chuan chuang chui chun chuo
ci cong cou cu cuan cui cun cuo da dai dan dang dao de dei den deng di dia dian diao die ding diu dong dou du duan dui dun duo
e ei en eng er fa fan fang fei fen feng fo fou fu ga gai gan gang gao ge gei gen geng gong gou gu gua guai guan guang gui gun guo
ha hai han hang hao he hei hen heng hong hou hu hua huai huan huang hui hun huo
ji jia jian jiang jiao jie jin jing jiong jiu ju juan jue jun
ka kai kan kang kao ke ken keng kong kou ku kua kuai kuan kuang kui kun kuo
la lai lan lang lao le lei leng li lia lian liang liao lie lin ling liu long lou lu luan lue lun luo
ma mai man mang mao me mei men meng mi mian miao mie min ming miu mo mou mu
na nai nan nang nao ne nei nen neng ni nian niang niao nie nin ning niu nong nou nu nuan nue nuo
o ou pa pai pan pang pao pei pen peng pi pian piao pie pin ping po pou pu
qi qia qian qiang qiao qie qin qing qiong qiu qu quan que qun
ran rang rao re ren reng ri rong rou ru rua ruan rui run ruo
sa sai san sang sao se sen seng sha shai shan shang shao she shen sheng shi shou shu shua shuai shuan shuang shui shun shuo
si song sou su suan sui sun suo ta tai tan tang tao te teng ti tian tiao tie ting tong tou tu tuan tui tun tuo
wa wai wan wang wei wen weng wo wu
xi xia xian xiang xiao xie xin xing xiong xiu xu xuan xue xun
ya yan yang yao ye yi yin ying yo yong you yu yuan yue yun
za zai zan zang zao ze zei zen zeng zha zhai zhan zhang zhao zhe zhen zheng zhi zhong zhou zhu zhua zhuai zhuan zhuang zhui zhun zhuo
zi zong zou zu zuan zui zun zuo
""".split())
PINYIN_SYLLABLES.update(CHINESE_MAP.keys())


def chinese_readings(syllable: str) -> set[str]:
    return CHINESE_MAP.get(syllable, {syllable})


def chinese_token_variants(token: str) -> set[tuple[str, ...]]:
    token = re.sub(r"[^a-z]", "", ascii_fold(token))
    if not token:
        return set()
    out = {(reading,) for reading in chinese_readings(token)}
    # Enumerate segmentations, preferring two or three real syllables. Long
    # arbitrary Western tokens are not segmented into single-letter accidents.
    n = len(token)
    for i in range(2, n - 1):
        a, b = token[:i], token[i:]
        if a in PINYIN_SYLLABLES and b in PINYIN_SYLLABLES:
            for aa in chinese_readings(a):
                for bb in chinese_readings(b):
                    out.add((aa, bb))
            for j in range(i + 2, n - 1):
                b2, c = token[i:j], token[j:]
                if b2 in PINYIN_SYLLABLES and c in PINYIN_SYLLABLES:
                    for aa in chinese_readings(a):
                        for bb in chinese_readings(b2):
                            for cc in chinese_readings(c):
                                out.add((aa, bb, cc))
    return out


def chinese_signatures(name: str) -> set[str]:
    ws = [w for w in words(name) if len(w) > 1 or w == "i"]
    if len(ws) < 2:
        return set()
    possibilities: list[list[str]] = [[]]
    for w in ws:
        nxt: list[list[str]] = []
        for prev in possibilities:
            for parts in chinese_token_variants(w):
                nxt.append(prev + list(parts))
        possibilities = nxt[:64]
    return {"|".join(sorted(p)) for p in possibilities if 2 <= len(p) <= 4}


def literal_signatures(name: str) -> set[str]:
    ws = [w for w in words(name) if len(w) > 1]
    if len(ws) < 2:
        return set()
    return {"|".join(sorted(ws))}


def date_compatible(customer_dob: str, entry_dob: str) -> bool:
    if not customer_dob or not entry_dob:
        return True
    return entry_dob.startswith(customer_dob)


def date_supported(customer_dob: str, entry_dob: str) -> bool:
    return bool(customer_dob and entry_dob and entry_dob.startswith(customer_dob))


def weak_key(name: str) -> str:
    return " ".join(words(name))


@dataclass(frozen=True)
class NameRef:
    uid: str
    weak: bool = False


class ScreeningEngine:
    def __init__(self, entries: list[dict]):
        self.entries = {str(e["uid"]): e for e in entries}
        self.id_index: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.entity_index: dict[str, set[str]] = defaultdict(set)
        self.vessel_index: dict[str, set[str]] = defaultdict(set)
        self.literal_index: dict[str, set[str]] = defaultdict(set)
        self.western_index: dict[str, set[str]] = defaultdict(set)
        self.arabic_index: dict[str, set[str]] = defaultdict(set)
        self.russian_index: dict[str, set[str]] = defaultdict(set)
        self.chinese_index: dict[str, set[str]] = defaultdict(set)
        self.weak_index: dict[str, set[str]] = defaultdict(set)

        # Learn script-token readings from records which contain both the source
        # script and a Latin primary/strong name.  This is not training on customer
        # labels: it is the watchlist's own stated transliteration evidence, and it
        # lets a script-only record benefit from spellings present elsewhere.
        self.arabic_script_lexicon: dict[str, set[str]] = defaultdict(set)
        self.russian_script_lexicon: dict[str, set[str]] = defaultdict(set)
        for e in entries:
            script = str(e.get("script_name") or "")
            if script and has_cyrillic(script):
                source_words = re.findall(
                    r"[^\W_]+", unicodedata.normalize("NFC", script).casefold(),
                    flags=re.UNICODE,
                )
                for source_word in source_words:
                    canonical = russian_token(source_word)
                    for spelling in cyrillic_romanizations(source_word):
                        self.russian_script_lexicon[spelling].add(canonical)
            if not script or not has_arabic(script):
                continue
            latin_names = []
            primary = str(e.get("primary_name", ""))
            if primary and not has_arabic(primary):
                latin_names.append(primary)
            latin_names.extend(str(a.get("name", "")) for a in e.get("aliases", [])
                               if a.get("strength") == "strong" and
                               not has_arabic(str(a.get("name", ""))))
            source = _arabic_core_words(script)
            for latin in latin_names:
                target = _arabic_core_words(latin)
                pairs: list[tuple[str, str]] = []
                if len(source) == len(target):
                    pairs.extend(zip(source, target))
                elif len(source) >= 2 and len(target) >= 2:
                    pairs.extend(((source[0], target[0]), (source[-1], target[-1])))
                for script_word, latin_word in pairs:
                    self.arabic_script_lexicon[script_word].add(arabic_latin_token(latin_word))

        for e in entries:
            uid = str(e["uid"])
            for ident in e.get("ids", []):
                typ = str(ident.get("type", "")).strip().casefold()
                num = str(ident.get("number", "")).strip().casefold()
                if typ and num:
                    self.id_index[(typ, num)].add(uid)

            names = [(str(e.get("primary_name", "")), "strong")]
            script = str(e.get("script_name") or "")
            if script:
                names.append((script, "strong"))
            names.extend((str(a.get("name", "")), str(a.get("strength", "")))
                         for a in e.get("aliases", []))
            for name, strength in names:
                if not name:
                    continue
                if strength == "weak":
                    self.weak_index[weak_key(name)].add(uid)
                    continue
                typ = e.get("type")
                if typ == "entity":
                    self.entity_index[organization_key(name)].add(uid)
                elif typ == "vessel":
                    self.vessel_index[vessel_key(name)].add(uid)
                else:
                    for key in literal_signatures(name):
                        self.literal_index[key].add(uid)
                    for key in western_signatures(name):
                        self.western_index[key].add(uid)
                    for key in arabic_signatures(name, self.arabic_script_lexicon):
                        self.arabic_index[key].add(uid)
                    for key in russian_signatures(name, self.russian_script_lexicon):
                        self.russian_index[key].add(uid)
                    for key in chinese_signatures(name):
                        self.chinese_index[key].add(uid)

    def _rank(self, uids: Iterable[str], customer: dict, id_match: bool = False) -> str | None:
        valid = []
        for uid in set(uids):
            e = self.entries[uid]
            if not id_match and not date_compatible(customer.get("dob", ""), str(e.get("dob", ""))):
                continue
            valid.append(uid)
        if not valid:
            return None
        return min(valid, key=lambda uid: (
            0 if id_match else 1,
            0 if date_supported(customer.get("dob", ""), str(self.entries[uid].get("dob", ""))) else 1,
            uid,
        ))

    def screen(self, customer: dict) -> tuple[str, str]:
        id_type = customer.get("id_type", "").strip().casefold()
        id_number = customer.get("id_number", "").strip().casefold()
        if id_type and id_number:
            uid = self._rank(self.id_index.get((id_type, id_number), ()), customer, id_match=True)
            if uid:
                return "MATCH", uid

        name = customer.get("full_name", "")
        typ = customer.get("type", "")
        candidates: set[str] = set()
        if typ == "entity":
            candidates.update(self.entity_index.get(organization_key(name), ()))
        elif typ == "vessel":
            candidates.update(self.vessel_index.get(vessel_key(name), ()))
        elif typ == "individual":
            for key in literal_signatures(name):
                candidates.update(self.literal_index.get(key, ()))
            for key in western_signatures(name):
                candidates.update(self.western_index.get(key, ()))
            for key in arabic_signatures(name, self.arabic_script_lexicon):
                candidates.update(self.arabic_index.get(key, ()))
            for key in russian_signatures(name, self.russian_script_lexicon):
                candidates.update(self.russian_index.get(key, ()))
            for key in chinese_signatures(name):
                candidates.update(self.chinese_index.get(key, ()))

        # A weak alias is eligible only when corroborated by the same complete
        # DOB.  Add eligible weak candidates before ranking so that the policy's
        # DOB tie-break can prefer one over an uncorroborated strong-name hit.
        dob = customer.get("dob", "")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", dob or ""):
            candidates.update(
                uid for uid in self.weak_index.get(weak_key(name), ())
                if self.entries[uid].get("type") == typ
                and str(self.entries[uid].get("dob", "")) == dob
            )

        uid = self._rank(candidates, customer)
        if uid:
            return "MATCH", uid
        return "NO_MATCH", ""


def load_watchlist(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("watchlist JSON must contain a top-level list")
    return data


def run(watchlist_path: str, customers_path: str, out_path: str) -> None:
    engine = ScreeningEngine(load_watchlist(watchlist_path))
    with open(customers_path, "r", encoding="utf-8-sig", newline="") as src:
        customers = list(csv.DictReader(src))
    required = {"customer_id", "full_name", "dob", "nationality", "id_type", "id_number", "type"}
    if customers and not required.issubset(customers[0]):
        raise ValueError("customers CSV is missing required columns")
    with open(out_path, "w", encoding="utf-8", newline="") as dst:
        writer = csv.DictWriter(dst, fieldnames=["customer_id", "decision", "matched_uid"])
        writer.writeheader()
        for customer in customers:
            decision, uid = engine.screen(customer)
            writer.writerow({"customer_id": customer["customer_id"], "decision": decision,
                             "matched_uid": uid})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Screen a customer CSV against a sanctions watchlist")
    parser.add_argument("--watchlist", required=True)
    parser.add_argument("--customers", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        run(args.watchlist, args.customers, args.out)
    except (OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        print(f"screen.py: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
