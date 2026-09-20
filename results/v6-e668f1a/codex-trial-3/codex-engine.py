#!/usr/bin/env python3
"""Rule-based sanctions name screening (Python 3.12, standard library only)."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict
from functools import lru_cache


ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
CYRILLIC_RE = re.compile(r"[\u0400-\u052f]")


CYRILLIC = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
        "е": "e", "ё": "yo", "ж": "zh", "з": "z", "и": "i",
        "й": "y", "к": "k", "л": "l", "м": "m", "н": "n",
        "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
        "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch",
        "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "yu", "я": "ya", "і": "i", "ї": "yi",
        "є": "ye", "ґ": "g", "ў": "u",
    }
)

# ISO/scientific Cyrillic romanization after its diacritics are removed, as
# specified for the unseen batch (e.g. Cajkovskij, Zukov, Sevcenko).
CYRILLIC_SCIENTIFIC = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
        "е": "e", "ё": "e", "ж": "z", "з": "z", "и": "i",
        "й": "j", "к": "k", "л": "l", "м": "m", "н": "n",
        "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
        "у": "u", "ф": "f", "х": "ch", "ц": "c", "ч": "c",
        "ш": "s", "щ": "sc", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "ju", "я": "ja", "і": "i", "ї": "ji",
        "є": "je", "ґ": "g", "ў": "u",
    }
)

# Conventional Polish rendering of Russian (Czernow, Szewczenko, Iwanow).
CYRILLIC_POLISH = str.maketrans(
    {
        "а": "a", "б": "b", "в": "w", "г": "g", "д": "d",
        "е": "e", "ё": "jo", "ж": "z", "з": "z", "и": "i",
        "й": "j", "к": "k", "л": "l", "м": "m", "н": "n",
        "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
        "у": "u", "ф": "f", "х": "ch", "ц": "c", "ч": "cz",
        "ш": "sz", "щ": "szcz", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "ju", "я": "ja", "і": "i", "ї": "ji",
        "є": "je", "ґ": "g", "ў": "u",
    }
)

# German- and French-library renderings used in international records
# (Kusnetsow, Tschernow, Schukow; Kouznetzov, Tchaikovski).
CYRILLIC_GERMAN = str.maketrans(
    {
        "а": "a", "б": "b", "в": "w", "г": "g", "д": "d",
        "е": "e", "ё": "jo", "ж": "sh", "з": "s", "и": "i",
        "й": "j", "к": "k", "л": "l", "м": "m", "н": "n",
        "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
        "у": "u", "ф": "f", "х": "ch", "ц": "ts", "ч": "tsch",
        "ш": "sch", "щ": "schtsch", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "ju", "я": "ja",
    }
)
CYRILLIC_GERMAN_LOOSE = str.maketrans(
    {
        "а": "a", "б": "b", "в": "w", "г": "g", "д": "d",
        "е": "e", "ё": "jo", "ж": "sh", "з": "s", "и": "i",
        "й": "j", "к": "k", "л": "l", "м": "m", "н": "n",
        "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
        "у": "u", "ф": "f", "х": "ch", "ц": "s", "ч": "tsch",
        "ш": "sch", "щ": "schtsch", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "ju", "я": "ja",
    }
)
CYRILLIC_FRENCH = str.maketrans(
    {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d",
        "е": "e", "ё": "io", "ж": "j", "з": "z", "и": "i",
        "й": "i", "к": "k", "л": "l", "м": "m", "н": "n",
        "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
        "у": "ou", "ф": "f", "х": "kh", "ц": "ts", "ч": "tch",
        "ш": "ch", "щ": "chtch", "ъ": "", "ы": "y", "ь": "",
        "э": "e", "ю": "iou", "я": "ia",
    }
)

# Arabic and Persian letters.  Long-vowel letters are deliberately retained;
# the Latin phonetic stage decides when they act as vowels.
ARABIC = str.maketrans(
    {
        "ا": "a", "ب": "b", "ت": "t", "ث": "th", "ج": "j",
        "ح": "h", "خ": "kh", "د": "d", "ذ": "dh", "ر": "r",
        "ز": "z", "س": "s", "ش": "sh", "ص": "s", "ض": "d",
        "ط": "t", "ظ": "z", "ع": "", "غ": "gh", "ف": "f",
        "ق": "q", "ك": "k", "ل": "l", "م": "m", "ن": "n",
        "ه": "h", "و": "w", "ي": "y", "پ": "p", "چ": "ch",
        "ژ": "zh", "گ": "g", "ڤ": "v",
    }
)


def latin_fold(value: str) -> str:
    """Lowercase Latin text and remove accents without losing special letters."""
    value = value.lower().translate(
        str.maketrans(
            {
                "ß": "ss", "ø": "o", "ł": "l", "đ": "d", "ð": "d",
                "þ": "th", "æ": "ae", "œ": "oe", "ı": "i",
                # Preserve the sound of letters whose marks NFKD would erase.
                "ş": "sh", "ș": "sh", "ç": "ch", "č": "ch",
                "ć": "ch", "ž": "zh", "š": "sh", "ğ": "g",
            }
        )
    )
    return "".join(
        c for c in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(c)
    )


def clean_unicode(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").lower()
    # Arabic presentation differences and vowel marks are not name letters.
    value = value.translate(
        str.maketrans(
            {
                "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه",
                "ى": "ي", "ؤ": "و", "ئ": "ي", "ک": "ك", "ی": "ي",
                "ۀ": "ه", "ـ": "",
            }
        )
    )
    value = "".join(c for c in value if not unicodedata.combining(c))
    return value


@lru_cache(maxsize=None)
def raw_tokens(value: str) -> tuple[str, ...]:
    """Tokenize punctuation, while treating apostrophes as internal joiners."""
    value = clean_unicode(value)
    out = []
    for c in value:
        cat = unicodedata.category(c)
        if c in "'’`\u02bc" or cat == "Cf":
            continue
        out.append(" " if cat[0] in "PZS" else c)
    return tuple(x for x in "".join(out).split() if x)


ARTICLE_WORDS = {"al", "el", "ad", "an", "ar", "as", "ash", "at", "az"}
ARABIC_ARTICLE_ROOTS = {
    "amin", "ameen", "attar", "atar", "douri", "duri", "jabouri", "jaburi",
    "khatib", "khateb", "masri", "najjar", "najar", "nagar", "rashid",
    "rasheed", "rashed", "rached", "sabah", "saba", "shamsi", "shamsie", "schamsi", "chamsi",
    "sayyid", "sayed", "tikriti", "tikreeti", "zahrani", "hashimi",
    "hashemi", "farsi", "farisi", "hakim", "hakeem", "rasheed", "djabouri",
}


def article_root_key(value: str) -> str:
    value = latin_fold(value)
    value = value.replace("dsch", "j").replace("dj", "j")
    value = value.replace("sch", "sh").replace("ou", "u")
    value = value.replace("kh", "h").replace("gh", "g")
    value = value.replace("q", "k")
    return re.sub(r"[aeiouy]", "", value)


ARABIC_ARTICLE_ROOT_KEYS = {article_root_key(x) for x in ARABIC_ARTICLE_ROOTS}


def strip_article(token: str) -> str | None:
    """Remove a free or attached Arabic definite article."""
    if token in ARTICLE_WORDS:
        return None
    if ARABIC_RE.search(token):
        if token == "الله":
            return token
        if token.startswith("ال") and len(token) > 3:
            return token[2:]
        return token
    folded = latin_fold(token)
    for prefix in ("ash", "al", "el", "ad", "an", "ar", "as", "at", "az"):
        if folded.startswith(prefix):
            root = folded[len(prefix):]
            assimilated = "sh" if prefix == "ash" else prefix[-1]
            if prefix not in {"al", "el"} and not root.startswith(assimilated):
                continue
            if root in ARABIC_ARTICLE_ROOTS or article_root_key(root) in ARABIC_ARTICLE_ROOT_KEYS:
                return token[len(prefix):]
    return token


def roman_for_structure(token: str) -> str:
    token = clean_unicode(token)
    if CYRILLIC_RE.search(token):
        token = token.translate(CYRILLIC)
    elif ARABIC_RE.search(token):
        token = token.translate(ARABIC)
    return re.sub(r"[^a-z]", "", latin_fold(token))


def is_patronymic(token: str) -> bool:
    r = roman_for_structure(token)
    if re.search(r"(?:owicz|ewicz|owitsch|ewitsch|owna|ewna)$", r):
        return True
    r = r.replace("w", "v")
    r = r.replace("tsch", "ch").replace("sch", "sh")
    return bool(
        re.search(
            r"(?:ovich|evich|yevich|ovitch|evitch|yevitch|ovitsch|evitsch|"
            r"yevitsch|ovich|evich|ovic|evic|ovicz|evicz|owicz|ewicz|ovna|evna|yevna|owna|ewna)$",
            r,
        )
    )


def _split_attached_abd(token: str) -> str | None:
    r = roman_for_structure(token)
    if not r.startswith("abd") or r == "abd":
        return None
    rest = r[3:]
    # Linking vowels and the assimilated r/l are spelling, not the root.
    for link in ("ullah", "allah"):
        if rest == link:
            return "abdallah"
    for link in ("ul", "el", "al", "ol", "oel"):
        if rest.startswith(link) and len(rest) > len(link) + 2:
            return "abd" + rest[len(link):]
    if rest.startswith("ur") and len(rest) > 4:
        return "abd" + rest[2:]
    return None


@lru_cache(maxsize=None)
def individual_core(value: str) -> tuple[str, ...]:
    tokens = []
    for token in raw_tokens(value):
        token = strip_article(token)
        if token:
            tokens.append(token)

    # Standard joined spellings for the few productive compounds in scope.
    expanded: list[str] = []
    i = 0
    while i < len(tokens):
        r = roman_for_structure(tokens[i])
        attached = _split_attached_abd(tokens[i])
        if attached:
            expanded.append(attached)
            i += 1
            continue
        if r in {"abd", "bd", "abdul", "abdel", "abdal", "abdol", "abdoel"} and i + 1 < len(tokens):
            expanded.append("abd" + roman_for_structure(tokens[i + 1]))
            i += 2
            continue
        # Nasr Allah / Nasrallah is another frequent lexical compound.
        if r == "nsr" and i + 1 < len(tokens) and roman_for_structure(tokens[i + 1]) in {"allh", "llh", "allah", "lh"}:
            expanded.append("nasrallah")
            i += 2
            continue
        expanded.append(tokens[i])
        i += 1
    tokens = expanded

    # A nasab is optional as a complete unit: marker plus the father's name.
    without_nasab = []
    skip = 0
    for pos, token in enumerate(tokens):
        if skip:
            skip -= 1
            continue
        marker = roman_for_structure(token)
        if marker in {"bin", "bn", "ibn", "ben"} or (marker == "b" and len(tokens) >= 4 and 0 < pos < len(tokens) - 1):
            skip = 1
            continue
        without_nasab.append(token)

    out = []
    for token in without_nasab:
        r = roman_for_structure(token)
        if len(r) == 1:  # middle initial
            continue
        if is_patronymic(token):
            continue
        # Compound surnames may be printed closed, hyphenated or spaced.
        if r in {"smithjones", "smithjoness"}:
            out.extend(["smith", "jones"])
        elif r == "dubois":
            out.extend(["du", "bois"])
        elif r in {"macdonald", "mcdonald"}:
            out.extend(["mac", "donald"])
        elif r == "lefevre":
            out.extend(["le", "fevre"])
        else:
            out.append(token)
    # Match the spaced forms Mac Donald and Le Fevre to their closed forms.
    return tuple(out)


@lru_cache(maxsize=None)
def literal_name_key(value: str) -> tuple[str, ...]:
    """Case/diacritic/punctuation normalization without nickname expansion."""
    out = []
    for token in raw_tokens(value):
        if ARABIC_RE.search(token) or CYRILLIC_RE.search(token):
            out.append(clean_unicode(token))
        else:
            out.append(re.sub(r"[^a-z0-9]", "", latin_fold(token)))
    return tuple(x for x in out if x)


# Lexical groups protect genuinely different names which share a consonant
# skeleton, while also implementing established nicknames and conventional
# renderings.  The remaining spelling work is handled productively below.
WORD_GROUPS = [
    ("william", "will", "bill", "billy"),
    ("katherine", "catherine", "kathryn", "kate", "kathy", "katie"),
    ("michael", "mike", "mick"),
    ("robert", "rob", "bob", "bobby"),
    ("richard", "rick", "ricky", "dick", "rich"),
    ("elizabeth", "elisabeth", "liz", "beth", "betty"),
    ("margaret", "maggie", "meg", "peggy"),
    ("jennifer", "jen", "jenny"),
    ("nicholas", "nick"), ("anthony", "tony"),
    ("andrew", "andy"), ("frederick", "fred", "freddie", "freddy"),
    ("samuel", "sam"), ("charles", "chuck", "charlie"),
    ("francisco", "paco"), ("joseph", "joe", "joey"),
    ("benjamin", "ben"), ("daniel", "dan"), ("donald", "don"),
    ("steven", "stephen", "steve"), ("christopher", "chris"),
    ("matthew", "matt"), ("ronald", "ron"), ("lawrence", "larry"),
    ("theodore", "ted", "teddy"), ("gerald", "jerry"),
    ("thomas", "tom", "tommy"), ("kenneth", "ken"),
    ("edward", "ed", "eddie"), ("james", "jim", "jimmy", "jamie"),
    ("john", "jack", "johnny"), ("patricia", "pat", "patty"),
    ("barbara", "barb"), ("dorothy", "dot", "dotty"),
    ("victoria", "vicki", "vicky", "tori"),
    ("andrew", "drew"), ("daniel", "danny"),
    ("benjamin", "benny"), ("rebecca", "becca", "becky"),
    ("barbara", "babs"), ("jose", "pepe"),
    ("francisco", "frank"), ("christopher", "kit"),
    ("aleksandr", "sasha", "alex", "xander"), ("susan", "suzy", "susie", "sue"),
    ("peter", "pedro"),
    ("ahmad", "ahmed", "ahmet", "achmad"),
    ("muhammad", "mohammad", "mohammed", "mohamed", "mohamad", "muhammed", "mehmet", "moehammad"),
    ("jamal", "jemal", "cemal", "djamal", "gamal"),
    ("hassan", "hasan"),
    ("hussein", "hussain", "husain", "husayn", "hossein", "hosein", "husein", "huseyin"),
    ("hamid", "hameed", "hamed"), ("hamad", "hamedh"),
    ("qasim", "kasim", "kassem", "qassem"),
    ("yusuf", "yousuf", "yousef", "youssef", "yusof", "yussof", "joesoef", "jusuf"),
    ("sharif", "sherif", "shareef", "sjarif"),
    ("rashid", "rashed", "rasheed", "rached"),
    ("majid", "majed", "maged", "majede", "majeed"), ("karim", "karem", "kareem"),
    ("salim", "salem", "saleem", "sallem"),
    ("samir", "sameer", "sameire", "sammir", "sammire"),
    ("aisha", "ayesha", "aicha", "aichah", "aischa", "aischah"),
    ("layla", "leila", "laila", "lailah", "laylah"),
    ("maryam", "mariam", "meryem", "mariame", "maryame"),
    ("fatima", "fatema", "fatimah", "fateemah"), ("hanan", "hanen", "hannan"),
    ("rania", "raniah", "raniyah"), ("zaynab", "zeinab", "zainab"),
    ("ismail", "ismayl", "ismael"), ("yasser", "yasir", "yassir"),
    ("nasser", "naser", "nasir"), ("khalid", "khaled"),
    ("hamza", "hamzah", "hamzahe"), ("talal", "tallal"), ("faisal", "faysal"),
    ("waleed", "walid", "waled"), ("hisham", "hesham"),
    ("tariq", "tarek", "tarik"), ("omar", "umar"),
    ("rami", "rammi"), ("mahmoud", "mahmud"), ("noor", "nur"),
    ("dalal", "dallal"), ("salma", "salmah"),
    ("dariush", "daryush", "daryoush"), ("farhad", "farhed"),
    ("kaveh", "caveh", "kavih"), ("parviz", "parvez", "parveez"),
    ("reza", "rezah"), ("behrouz", "behruz"),
    ("javad", "javed", "djavad", "dschavad", "gaved", "gawad"), ("omid", "omed"),
    ("masoud", "massoud", "masood"), ("nasrin", "nasren"),
    ("shirin", "shirine"), ("mahsa", "mahsah"),
    ("sergei", "sergey", "serguei", "sergej"),
    ("fyodor", "fedor", "fiodor", "fjodor"),
    ("yevgeny", "evgeny", "yevgeni", "evgeni", "eugene"),
    ("dmitri", "dmitry", "dmitriy"), ("nikolai", "nikolay", "nikolaj"),
    ("yuri", "yuriy", "iuri", "jurij"), ("yulia", "yuliya", "julia", "iulia", "joulia"),
    ("yelena", "elena", "jelena"), ("yelizaveta", "elizaveta", "jelizaveta"),
    ("artyom", "artem", "artiom"), ("vyacheslav", "viacheslav"),
    ("semyon", "semen", "semion"), ("grigory", "grigori", "grigoriy"),
    ("gennady", "gennadi", "gennadiy"), ("valery", "valeriy", "valeri"),
    ("anatoly", "anatoli", "anatoliy"), ("arkady", "arkadi", "arkadiy"),
    ("ksenia", "kseniya", "xenia"), ("natalia", "natalya"),
    ("maria", "mariya"), ("darya", "daria", "darja"),
    ("svetlana", "swetlana"), ("zhanna", "janna"),
    ("aleksandr", "alexander", "alexandr"),
    ("aleksei", "alexei", "alexey", "aleksey"),
    ("mueller", "muller"), ("andersen", "anderson", "andersson"),
    ("olsen", "olson"), ("sorensen", "soerensen"),
    ("bianchi", "bianci"),
    ("abdallah", "abdullah", "abdulla", "abdollah", "abdolla"),
    ("lindqvist", "lindquist"), ("schmidt", "schmid", "schmitt"),
    ("den", "der"), ("marwan", "marwen", "marouen"),
    ("fernandez", "fernandes"), ("ferreira", "ferreyra"),
    ("darwish", "darouish", "darwesh", "darouich"),
    ("jabouri", "gabouri", "djabouri"),
    ("najjar", "najar", "nagar", "nadjdjar", "nadschdschar"),
    ("khadija", "khadeegah", "khadijah", "khadidja"),
    ("mohammadi", "mohamadi", "mohammedi"),
    ("mahmoudi", "mahmudi", "mahmoodi"),
    ("huda", "hudah", "hoda"),
    ("ekaterina", "yekaterina", "yekaterine"),
    ("lyudmila", "liudmila", "ljudmila"),
    ("shishkin", "shishkina", "chichkin", "chichkina", "tchitchkin", "tchitchkina", "schischkin", "schischkina"),
    ("yashin", "yashina", "iaschin", "iaschina", "iachin", "iachina", "jaschin", "jaschina", "jastschin", "jastschina"),
    ("morozov", "morozova", "morosow", "morosowa", "morosov", "morosova"),
    ("zakharov", "zakharova", "zakharoff", "zakharoffa", "sacharow", "sacharowa", "zatscharov", "zatscharova"),
    ("shevchenko", "stschevtschenko"),
    ("zhanna", "shanna"),
    ("tsvetkov", "tsvetkova", "tzvetkoff", "tzvetkoffa"),
    ("vladimir", "wladimir"), ("mikhail", "michail", "mihail"),
    ("maksim", "maxim", "maksym"),
    ("tatiana", "tatyana", "tatjana"),
    ("vasily", "vasiliy", "vassily", "wassily", "wasily"),
    ("andrei", "andrey", "andrej"), ("pavel", "pawel"),
    ("ivan", "iwan"), ("viktor", "victor"),
    ("konstantin", "constantin"), ("anastasia", "anastasiya", "anastasija"),
    ("stanislav", "stanislaff"), ("nadezhda", "nadeschda"),
    # Turkish conventional equivalents of Arabic names.
    ("aisha", "ayse", "ayshe"), ("zaynab", "zeynep"),
    ("khadija", "hatice", "hadice"), ("javad", "cevat"),
    ("anwar", "anouar", "anouare", "enver"), ("amin", "emin"), ("amir", "emir"),
    ("khalid", "halit", "halid"), ("tariq", "tarik"),
    ("rashid", "resit", "reshit"), ("layla", "leyla"),
    ("fatima", "fatma"), ("mahmoud", "mahmut"),
    ("karim", "kerim"), ("salim", "selim"),
    ("majid", "mecit", "macit"), ("ziad", "ziyad"),
    ("zhukov", "zhukova", "zukov", "zukova"),
    ("chernov", "chernova", "cernov", "cernova", "czernow", "czernowa", "tchernoff", "tchernoffa"),
    ("shevchenko", "sevcenko", "szewczenko", "schewtschenko", "shevtschenko"),
    ("chaikovsky", "chaikovskaya", "tchaikovsky", "tchaikovskaya", "cajkovskij", "cajkovskaja"),
    ("yakovlev", "yakovleva", "jakowlew", "jakowlewa"),
    ("tsvetkov", "tsvetkova", "tzvetkov", "tzvetkova", "zvetkov", "zvetkova"),
]

LEXICAL: dict[str, str] = {}
for group in WORD_GROUPS:
    canonical = group[0]
    for spelling in group:
        LEXICAL[latin_fold(spelling)] = canonical

# Vowel-less comparison is useful for romanization, but these are distinct
# common personal names/titles that must not collapse merely because their
# consonants happen to agree.  Variants already grouped above take priority.
PROTECTED_WORDS = {
    "ali", "taha", "sheikh", "the", "oleg", "olga", "amir", "omar",
    "amina", "amin", "anwar", "adnan", "bilal", "fahd", "hadi", "huda",
    "hudah", "karim", "kamal", "khalid", "nabil", "nizar", "noor", "nur",
    "rami", "sami", "salma", "yasin", "ziad", "ziyad", "faris", "hakim",
    "hashem", "hisham", "abbas", "aziz", "awad", "bakr", "barakat",
    "darwish", "douri", "jabouri", "kanaan", "khoury", "mahdi", "mansour",
    "nasser", "rashid", "sabah", "salman", "shahin", "sultan", "zaidi",
    "zahrani", "akbari", "ahmadi", "bagheri", "ebrahimi", "esfahani",
    "farahani", "hashemi", "hosseini", "jafari", "karimi", "mousavi",
    "nazari", "rahimi", "rahmani", "rezaei", "rostami", "salehi",
    "shirazi", "tabrizi", "tehrani", "yazdani", "zamani",
    "vladimir", "mikhail", "maksim", "tatiana", "vasily", "andrei",
    "pavel", "ivan", "viktor", "konstantin", "leonid", "nadezhda",
    "anastasia", "irina", "marina", "galina", "oksana", "valentina",
    "boris", "roman", "timur", "stanislav", "igor", "ruslan",
    "arash", "bijan", "kamran", "babak", "morteza", "ehsan", "parisa",
    "golnaz", "niloufar", "siavash", "shahram", "mohsen",
}
for word in PROTECTED_WORDS:
    LEXICAL.setdefault(word, word)

AMBIGUOUS_LEXICAL = {
    # Ted is established for both Edward and Theodore.  The full name and DOB
    # still have to satisfy the ordinary matching rules.
    "ted": {"edward", "theodore"},
    "teddy": {"edward", "theodore"},
}


def prepared_latin(token: str) -> str:
    token = clean_unicode(token)
    if CYRILLIC_RE.search(token):
        token = token.translate(CYRILLIC)
    elif ARABIC_RE.search(token):
        token = token.translate(ARABIC)
    token = latin_fold(token)
    token = re.sub(r"[^a-z]", "", token)
    # Old Indonesian/Malay and Turkish conventions.
    token = token.replace("dsch", "j").replace("dj", "j")
    token = token.replace("sjer", "sher").replace("sj", "sh")
    token = token.replace("tj", "ch")
    token = token.replace("oe", "u")
    if token == "joesoef":
        token = "yusuf"
    token = token.replace("achmad", "ahmad")
    return token


def lexical_identity(token: str) -> str | None:
    p = prepared_latin(token)
    return LEXICAL.get(p)


@lru_cache(maxsize=None)
def phonetic_keys(token: str) -> frozenset[str]:
    """Conservative consonantal keys across the stated romanizations."""
    raw = clean_unicode(token)
    p = prepared_latin(token)
    if not p:
        return frozenset()
    lex = LEXICAL.get(p)
    keys = {"L:" + lex} if lex else set()
    keys.update("L:" + x for x in AMBIGUOUS_LEXICAL.get(p, ()))

    bases = {p}
    if CYRILLIC_RE.search(raw):
        for table in (
            CYRILLIC_SCIENTIFIC, CYRILLIC_POLISH, CYRILLIC_GERMAN,
            CYRILLIC_GERMAN_LOOSE, CYRILLIC_FRENCH,
        ):
            rendered = re.sub(r"[^a-z]", "", latin_fold(raw.translate(table)))
            if rendered:
                bases.add(rendered)
                bases.add(rendered.replace("j", "y"))
    elif not ARABIC_RE.search(raw):
        # Preserve a pre-convention Latin form too: "tj" is /ch/ in old
        # Indonesian spelling but /tj/ in diacritic-free scientific Russian.
        unfolded = re.sub(r"[^a-z]", "", latin_fold(raw))
        if unfolded:
            bases.add(unfolded)
    # Polish/German scientific conventions.  Keep the unconverted form as an
    # alternative because these digraphs also occur in native Latin names.
    bases.add(p.replace("cz", "ch").replace("sz", "sh").replace("w", "v"))
    if "j" in p:
        bases.add(p.replace("j", "y"))
    if "c" in p:
        bases.add(p.replace("c", "ch"))
    if "ch" in p:
        bases.add(p.replace("ch", "sh"))
        # Old Indonesian/Malay uses ch in Arabic loans where modern spelling
        # commonly has h or kh (Achmad, Machmud, Mochtar, Chalid).
        bases.add(p.replace("ch", "h"))
    if p.startswith(("ia", "io", "iu")):
        bases.add("y" + p[1:])
    if p.endswith("h") and len(p) > 3:
        bases.add(p[:-1])
    if p.endswith("ff"):
        bases.add(p[:-2] + "v")

    for base in bases:
        base = re.sub(r"offa?$", "ov", base)
        base = re.sub(r"owa$", "ova", base)
        base = re.sub(r"ew(a)?$", lambda m: "ev" + ("a" if m.group(1) else ""), base)
        base = base.replace("schtsch", "Q").replace("shtch", "Q")
        base = base.replace("shch", "Q").replace("chch", "Q")
        base = base.replace("sch", "S")
        base = base.replace("tsch", "C").replace("tch", "C")
        base = base.replace("cz", "C").replace("ch", "C")
        base = base.replace("dzh", "J").replace("zh", "J")
        base = base.replace("sh", "S").replace("sz", "S")
        base = base.replace("kh", "h").replace("gh", "g")
        base = base.replace("ph", "f").replace("th", "t").replace("dh", "d")
        base = base.replace("ck", "k").replace("qu", "k").replace("q", "k")
        base = base.replace("w", "v")
        base = base.replace("x", "ks")
        base = base.replace("j", "J")
        # Optional initial ye- in Russian (Egorov/Yegorov etc.).
        base = re.sub(r"^y(e[vgln])", r"\1", base)
        initial_y = base.startswith("y")
        body = re.sub(r"[aeiouy]", "", base)
        if initial_y:
            body = "Y" + body
        body = body.replace("c", "k")
        body = re.sub(r"(.)\1+", r"\1", body)
        if body:
            keys.add("P:" + body)
    return frozenset(keys)


class NameMatcher:
    def __init__(self, entries: list[dict]):
        self.script_map: dict[str, set[str]] = defaultdict(set)
        self._learn_script_lexicon(entries)
        self._token_cache: dict[str, frozenset[str]] = {}

    def _learn_script_lexicon(self, entries: list[dict]) -> None:
        """Learn letter-token correspondences from bilingual list records."""
        for entry in entries:
            if entry.get("type") != "individual" or not entry.get("script_name"):
                continue
            script = entry["script_name"]
            primary = entry.get("primary_name", "")
            if not (ARABIC_RE.search(script) or CYRILLIC_RE.search(script)):
                continue
            if ARABIC_RE.search(primary) or CYRILLIC_RE.search(primary):
                continue
            left = individual_core(script)
            right = individual_core(primary)
            if len(left) == len(right):
                for a, b in zip(left, right):
                    self.script_map[clean_unicode(a)].add(b)

    def token_keys(self, token: str) -> frozenset[str]:
        cached = self._token_cache.get(token)
        if cached is not None:
            return cached
        keys = set(phonetic_keys(token))
        for mapped in self.script_map.get(clean_unicode(token), ()):
            keys.update(phonetic_keys(mapped))
        result = frozenset(keys)
        self._token_cache[token] = result
        return result

    def token_equivalent(self, a: str, b: str) -> bool:
        if clean_unicode(a) == clean_unicode(b):
            return True
        ka = self.token_keys(a)
        kb = self.token_keys(b)
        la = {x for x in ka if x.startswith("L:")}
        lb = {x for x in kb if x.startswith("L:")}
        if la and lb:
            # Protected lexical names (notably Hassan/Hussein, Hamad/Hamid)
            # must agree as lexical names, not merely as vowel-less skeletons.
            return bool(la & lb)
        return bool(ka & kb)

    def individual_match(self, customer: str, listed: str) -> bool:
        a = individual_core(customer)
        b = individual_core(listed)
        if len(a) < 2 or len(b) < 2 or len(a) != len(b):
            return False
        # Name order is immaterial.  Tiny lists make exact bipartite matching
        # simpler and safer than a greedy token sort.
        used = [False] * len(b)

        def assign(pos: int) -> bool:
            if pos == len(a):
                return True
            for j, target in enumerate(b):
                if not used[j] and self.token_equivalent(a[pos], target):
                    used[j] = True
                    if assign(pos + 1):
                        return True
                    used[j] = False
            return False

        return assign(0)

    def weak_alias_match(self, customer: str, alias: str) -> bool:
        # Rule 3 says "equals the alias", rather than granting a weak alias
        # all of Rule 2's nickname and reordering expansions.
        key = literal_name_key(customer)
        return bool(key) and key == literal_name_key(alias)


LEGAL_WORDS = {
    "the", "and", "llc", "ltd", "limited", "liability", "company", "co",
    "corp", "corporation", "inc", "incorporated", "gmbh", "sa", "jsc",
    "joint", "stock", "ao", "oao", "pao", "pjsc", "public", "plc", "fze",
    "fz", "free", "zone", "establishment", "sociedad", "anonima",
    "societe", "anonyme", "ag", "aktiengesellschaft", "bv", "nv", "kg",
    "kgaa", "sarl", "srl", "spa", "pte", "pty", "private", "pvt", "llp",
    "lp", "lllp", "oy", "oyj", "ab", "asa", "aps", "ooo", "zao", "cjsc",
    "closed", "open",
}

LEGAL_INITIALISMS = sorted(
    {
        ("f", "z", "l", "l", "c"), ("g", "m", "b", "h"),
        ("p", "j", "s", "c"), ("l", "l", "c"), ("j", "s", "c"),
        ("o", "a", "o"), ("f", "z", "e"), ("s", "a"), ("a", "g"),
        ("b", "v"), ("n", "v"), ("a", "o"), ("p", "l", "c"),
        ("s", "p", "a"),
    },
    key=len,
    reverse=True,
)


@lru_cache(maxsize=None)
def plain_words(value: str) -> tuple[str, ...]:
    return tuple(latin_fold(x) for x in raw_tokens(value))


@lru_cache(maxsize=None)
def entity_key(value: str) -> tuple[str, ...]:
    source = list(plain_words(value))
    words = []
    i = 0
    while i < len(source):
        consumed = 0
        for initials in LEGAL_INITIALISMS:
            if tuple(source[i:i + len(initials)]) == initials:
                consumed = len(initials)
                break
        if consumed:
            i += consumed
            continue
        word = source[i]
        i += 1
        if word in LEGAL_WORDS:
            continue
        words.append(word)
    return tuple(words)


VESSEL_PREFIXES = {"mv", "mt", "vessel"}


@lru_cache(maxsize=None)
def vessel_key(value: str) -> tuple[str, ...]:
    words = list(plain_words(value))
    # M/V and M/T tokenize to two one-letter words.
    if len(words) >= 2 and words[0] == "m" and words[1] in {"v", "t"}:
        words = words[2:]
    elif words and words[0] in VESSEL_PREFIXES:
        words = words[1:]
    return tuple(words)


def dob_compatible(customer: str, listed: str) -> bool:
    if not customer or not listed:
        return True
    return listed.startswith(customer)


def full_dob_equal(customer: str, listed: str) -> bool:
    return len(customer) == 10 and len(listed) == 10 and customer == listed


def screening_forms(entry: dict, strength: str = "strong") -> list[str]:
    forms = [entry.get("primary_name", "")]
    script = entry.get("script_name")
    if script and script not in forms:
        forms.append(script)
    forms.extend(
        alias.get("name", "")
        for alias in entry.get("aliases", [])
        if alias.get("strength") == strength
    )
    return [x for x in forms if x]


def choose(candidates: list[tuple[dict, bool, bool]]) -> dict | None:
    """identifier, then DOB support, then lowest UID."""
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: (
            0 if item[1] else 1,
            0 if item[2] else 1,
            str(item[0].get("uid", "")),
        ),
    )[0]


def screen(watchlist: list[dict], customers: list[dict]) -> list[dict[str, str]]:
    matcher = NameMatcher(watchlist)
    id_index: dict[tuple[str, str], list[dict]] = defaultdict(list)
    by_uid: dict[str, dict] = {}
    prepared_forms: dict[str, list[str]] = {}
    weak_forms: dict[str, list[str]] = {}
    individual_index: dict[str, set[str]] = defaultdict(set)
    weak_index: dict[str, set[str]] = defaultdict(set)
    entity_index: dict[tuple[str, ...], set[str]] = defaultdict(set)
    vessel_index: dict[tuple[str, ...], set[str]] = defaultdict(set)
    for entry in watchlist:
        uid = entry["uid"]
        by_uid[uid] = entry
        prepared_forms[entry["uid"]] = screening_forms(entry, "strong")
        weak_forms[entry["uid"]] = [
            a.get("name", "") for a in entry.get("aliases", [])
            if a.get("strength") == "weak" and a.get("name")
        ]
        for ident in entry.get("ids", []):
            id_index[(ident.get("type", ""), ident.get("number", ""))].append(entry)
        if entry.get("type") == "individual":
            for form in prepared_forms[uid]:
                for token in individual_core(form):
                    for key in matcher.token_keys(token):
                        individual_index[key].add(uid)
            for form in weak_forms[uid]:
                for token in individual_core(form):
                    for key in matcher.token_keys(token):
                        weak_index[key].add(uid)
        elif entry.get("type") == "entity":
            for form in prepared_forms[uid]:
                key = entity_key(form)
                if key:
                    entity_index[key].add(uid)
        elif entry.get("type") == "vessel":
            for form in prepared_forms[uid]:
                key = vessel_key(form)
                if key:
                    vessel_index[key].add(uid)

    rows = []
    for customer in customers:
        candidates: dict[str, tuple[dict, bool, bool]] = {}
        ctype = customer.get("type", "")
        cname = customer.get("full_name", "")
        cdob = customer.get("dob", "")
        id_type = customer.get("id_type", "")
        id_number = customer.get("id_number", "")
        if id_type and id_number:
            for entry in id_index.get((id_type, id_number), []):
                edob = entry.get("dob", "")
                dob_support = bool(cdob and edob and dob_compatible(cdob, edob))
                candidates[entry["uid"]] = (entry, True, dob_support)

        possible: set[str] = set()
        if ctype == "individual":
            for token in individual_core(cname):
                for key in matcher.token_keys(token):
                    possible.update(individual_index.get(key, ()))
                    if len(cdob) == 10:
                        possible.update(weak_index.get(key, ()))
        elif ctype == "entity":
            possible.update(entity_index.get(entity_key(cname), ()))
        elif ctype == "vessel":
            possible.update(vessel_index.get(vessel_key(cname), ()))

        for uid in possible:
            entry = by_uid[uid]
            edob = entry.get("dob", "")
            if not dob_compatible(cdob, edob):
                continue
            matched = False
            if ctype == "individual":
                matched = any(
                    matcher.individual_match(cname, form)
                    for form in prepared_forms[uid]
                )
                if not matched and full_dob_equal(cdob, edob):
                    matched = any(
                        matcher.weak_alias_match(cname, form)
                        for form in weak_forms[uid]
                    )
            elif ctype == "entity":
                key = entity_key(cname)
                matched = bool(key) and any(key == entity_key(form) for form in prepared_forms[uid])
            elif ctype == "vessel":
                key = vessel_key(cname)
                matched = bool(key) and any(key == vessel_key(form) for form in prepared_forms[uid])
            if matched:
                dob_support = bool(cdob and edob)
                old = candidates.get(uid)
                candidates[uid] = (entry, bool(old and old[1]), dob_support)

        selected = choose(list(candidates.values()))
        rows.append(
            {
                "customer_id": customer.get("customer_id", ""),
                "decision": "MATCH" if selected else "NO_MATCH",
                "matched_uid": selected.get("uid", "") if selected else "",
            }
        )
    return rows


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Screen a customer CSV against a JSON watchlist")
    parser.add_argument("--watchlist", required=True)
    parser.add_argument("--customers", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    with open(args.watchlist, "r", encoding="utf-8") as handle:
        watchlist = json.load(handle)
    with open(args.customers, "r", encoding="utf-8-sig", newline="") as handle:
        customers = list(csv.DictReader(handle))
    decisions = screen(watchlist, customers)
    with open(args.out, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["customer_id", "decision", "matched_uid"])
        writer.writeheader()
        writer.writerows(decisions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
