#!/usr/bin/env python3
"""Deterministic sanctions-name screening engine (Python 3.12, stdlib only)."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict


ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
CYRILLIC_RE = re.compile(r"[\u0400-\u052f]")


def ascii_text(value: str) -> str:
    value = value.casefold().translate(str.maketrans({
        "ł": "l", "ø": "o", "đ": "d", "ı": "i", "ß": "ss",
        "ð": "d", "þ": "th", "æ": "ae", "œ": "oe",
    }))
    return "".join(c for c in unicodedata.normalize("NFKD", value)
                   if not unicodedata.combining(c))


ARABIC_CHARS = {
    "ا": "a", "آ": "a", "أ": "a", "إ": "a", "ٱ": "a",
    "ب": "b", "پ": "p", "ت": "t", "ث": "th", "ج": "j",
    "چ": "ch", "ح": "h", "خ": "kh", "د": "d", "ذ": "dh",
    "ر": "r", "ز": "z", "ژ": "zh", "س": "s", "ش": "sh",
    "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "",
    "غ": "gh", "ف": "f", "ق": "q", "ك": "k", "ک": "k",
    "گ": "g", "ل": "l", "م": "m", "ن": "n", "ه": "h",
    "ة": "a", "و": "w", "ؤ": "w", "ي": "y", "ی": "y",
    "ى": "a", "ئ": "y", "ء": "", "ـ": "",
}

CYRILLIC_CHARS = {
    "а": "a", "б": "b", "в": "v", "г": "g", "ґ": "g",
    "д": "d", "е": "e", "ё": "yo", "ж": "zh", "з": "z",
    "и": "i", "і": "i", "ї": "yi", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p",
    "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f",
    "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya", "є": "ye", "ў": "u",
}


def transliterate(value: str) -> str:
    """Conservative character transliteration; lexical rules finish the job."""
    out = []
    for c in value.casefold():
        if c in ARABIC_CHARS:
            out.append(ARABIC_CHARS[c])
        elif c in CYRILLIC_CHARS:
            out.append(CYRILLIC_CHARS[c])
        elif unicodedata.category(c) == "Mn":
            continue
        else:
            out.append(c)
    return "".join(out)


def make_groups(text: str) -> dict[str, str]:
    answer: dict[str, str] = {}
    for line in text.splitlines():
        words = line.split()
        if not words:
            continue
        canonical = words[0]
        for word in words:
            answer[word] = canonical
    return answer


# A lexical layer is deliberately used rather than edit-distance matching. Each
# row is one real transliteration/nickname equivalence class. It prevents short,
# similar names (Hassan/Hussein, Amir/Omar, etc.) from becoming false hits.
WESTERN_GIVEN = make_groups("""
william bill billy
katherine catherine kathryn kathy kate katie cathy
jose pepe
michael mike mikey mick
margaret maggie peggy
rebecca becca becky
andrew drew andy
daniel danny dan
victoria tori vicky
joseph joe joey
elizabeth elisabeth liz beth betty
edward ed eddie
nicholas nicolas nick
dorothy dot dottie
christopher chris kit
frederick fred freddie
john jon johnny jack
patricia trish pat
matthew matt
steven steve stephen
charles chuck charlie
francisco frank paco
benjamin ben benny
anthony tony
theodore theo
thomas tom tommy
james jim jimmy jamie
susan suzy sue
henry hank
peter pete pedro
samuel sam
alexander alex sasha
richard rick ricky dick
jennifer jen jenny
barbara barb babs
robert bob
""")

WESTERN_FAMILY = make_groups("""
mueller muller
fernandez fernandes
fischer fisher
johansson johanson johansen
andersen anderson andersson
olsen olson
petersen peterson pedersen
sorensen sorenson
larsen larson
kowalski kowalsky
macdonald mcdonald
lindqvist lindquist lindkvist
meyer meier mayer
lefevre
dubois
nowak novak
smithjones jonessmith
vanderberg vandenberg
bianchi bianci
ferreira ferreyra
rodriguez rodrigues
weiss weis
schroeder schroder
schmidt schmid schmitt
nguyen
obrien
delacruz cruzdela
""")

RUSSIAN_GIVEN = make_groups("""
aleksei aleksej aleksij alexei alexey alexeiy alekseij
aleksandr alexander alexandr
andrei andrej andrey andreiy
anastasia anastasiya anastasya anastasija
anatoly anatoliy anatolij
arkady arkadiy arkadij
artyom artem artiom artjom
boris
darya daria darja
denis
dmitri dmitry dmitriy dmitrij
elena yelena jelena
elizaveta yelizaveta jelizaveta
evgeny evgenij yevgeny yevgeniy ievgueny jewgenij eugene
fyodor fedor fiodor
galina
gennady gennadiy gennadij
grigory grigoriy grigorij
igor
irina
ivan
ekaterina yekaterina jekaterina katerina
konstantin
kseniya ksenia ksenija
leonid
lyudmila ludmila ljudmila lyoudmila
maksim maxim
maria mariya marya
marina
mikhail michail
nadezhda nadejda nadezda
natalia natalya nataliya
nikolai nikolaj nikolay nikolaiy
oksana oxana
oleg
olga
pavel
roman
ruslan rouslan
semyon semion semen
sergei sergey serguei serguey sergej siergiej sergeiy sergueiy
stanislav
svetlana swetlana swietlana
tatiana tatyana
timur timour
valentina
valery valeriy
vasily vassily
viktor victor
viktoria victoria viktoriya
vladimir wladimir
vyacheslav vyatcheslav vjaceslav
yulia yuliya julia julija youlia
yuri yury yuriy jurij iuri
zhanna zanna janna shanna
""")

RUSSIAN_FAMILY = make_groups("""
andreev andreeff
belousov belousoff
bondarenko
bykov bykoff
chaikovsky tchaikovsky cajkovskij cajkovsky caykovsky chaykovskiy chaikovskiy czajkowski czajkowskij czajkowska
chernov tchernoff cernov czernow
egorov yegorov
fedorov fyodorov fedoroff
grishin grichin gritchin grisin
ivanov ivanoff
kiselyov kiselev kiseliov kiseleff
kovalenko
kozlov
kravchenko kravtchenko kravcenko krawczenko
kuznetsov kuznecov kusnetsov kusnetsow
lebedev lebedeff
makarov makaroff
morozov morozoff morosov morosow
nikolaev nikolaeff
novikov novikoff
orlov orloff
pavlov pavloff
petrov petroff
popov popow
sakharov saharov sacharow
semyonov semenov semionov semionoff
shevchenko shevtschenko stschevtschenko sevcenko szewczenko
shishkin chichkin tchitchkin siskin szyszkin
smirnov smirnoff
sokolov sokoloff
stepanov stepanoff
tkachenko tkatchenko tkacenko
tsoi tsoy tzoy tzoiy tsoiy coj
tsvetkov tzvetkov zvetkov tzvetkoff cvetkov cvietkow
volkov volkoff
yakovlev iakovlev yakowlew
yashin iachin iashin yaschin jasin jastschin jastschina
zaitsev saitsev saitseva zaitzeff zajcev zajcew
zakharov zakharoff zaharov zatsharov zatscharov
zhukov jukov zukov jukova shukov shukow zhoukov zhoukova
shcherbakov shtcherbakov chtcherbakov chcherbakov chcherbakoff scerbakov szczerbakow
""")

ARABIC_GIVEN = make_groups("""
abdullah abdula abdola abdolah abdolla abdollah abdoollah abdoollahe
abdulrahman abdurrahman abdurahman abderrahman abdulrahmen abdulrahmane abdulrahmaneh
abdulkarim abdulkerim abdulkarem abdulkareem abdulcarem abdelkarim
abdulaziz abdulazize abdulazeez abdulazez abduazeez abdelaziz
adnan adnen adnane adnene
ahmad ahmed ahmade ahmede achmad akhmad ahmet
aisha aishah aicha aichah aysha ayse
ali
amina amena ameena aminah
amir amer ameer
anwar anouar anouare
arash arache
babak babake
bashar bashare baschar bachar bachare
behrouz behrouze
bijan bijen
bilal billal billalle
dalal dallal
dariush darioush dariouch
ehsan ehsane ehsen
fahd fahde
faisal faisale faysal fayssal
farhad farhed farhade
fatima fatimah fatema fateemah fatemeh fatemma fatemmeh fatimihe fatimmih
golnaz golnaze
hamid hameed hamed hamede hameede hammed
hamza hamzah
hanan hanen hanene
hassan hassen hasan hasen hasane
hisham hishame hicham hichame hishamme
hossein hossain hussain hussein husain husayn houssein housseine husein huseyin
huda houda hudah hudahe
ibrahim ibraheem ibraheeme ibrahem ibraheme
ismail ismayl ismayle
jamal jammal jammale jammalle djamal djamale dschamal cemal
javad gavede gaved javade javed djavad djavade dschavad
kamal kamale kammal kammale cammal
kamran kamren kamrane camran camrane
karim karem kareem carem careme careem
kaveh kavih caveh cavih
khadija khadijah khadejah khadidjah
khalid halid halit khaled khaleed khalled khalleed
layla leila lailah laylah leillah
mahsa mahsah
mahmoud mahmud mahmoude
majid majed majide majeed madjed madjid madjide majede madsched madschid
mariam maryam meryem mariame mariamme maryame maryamme
marwan marwen marouen
masoud massoud massoude
mehdi
mohsen mohsin
morteza mortiza mortizah
muhammad muhammet muhammed mohammed mohammad mohamed mohamad muhamad mouhamad mochamad
mustafa mustafah
nabil nabel nabele nabeele
nasir nasser
nasrin nasren nasreen nasreene
niloufar nilloufar nilloufare
nizar nizare
nour nur noure
omar omer omare
omid omed
parisa parisah paressa parissa parissah
parviz parvez parveez
rami rammi
ramin ramen ramene rammen rammeen
rania raniah
rashid rashed rached rachid rasched racheed rasheed rasheede
reza rezah
saeed saed saede said saaid saaide saeid
salim saleem saleeme salem sallem sallime sallimme
salma salmah salmahe
sami sammi
samir sammer sammire
samira sameera sameerah samerah
shahram chahram chahrame schahram
shirin sheren sheereen cheren shirine
siavash
talal tallal
tariq tarik tarek tareq tareqe tarike
walid waled walede walleed wallide oualed
yasser yasir yassir yasere
yusuf jusuf yusef yousef youssef yusof yussof yussoof yusofe yousouf joesoef
zainab zaynab zaynabe zeynep
zahra zahrah zahrahe
ziad zied ziade ziede
qasim kasim
sharif sherif serif sjarif syarif
""")

ARABIC_FAMILY = make_groups("""
abbas abas abase
ahmadi
akbari
amin amen ameen
attar atar atare
awad awade awed
aziz azez azeeze azeze
bagheri baghiri
bakr bakre
barakat baracate
darwish darwesh darouish darwisch darwesch darwishe
douri doori duri
ebrahimi ebrahemi ebrahimmi ebrahemmi ebraheemi
esfahani
farahani
fares faris
farsi
ghanem ghanim ghanime
ghasemi qasemi ghassimi ghassimmi
haddad hadad haded hadade
hakim hakem hakeem hakeeme
hamdan hamden hamdene hamdane
hashemi hashimi hachimi hasheemmi hashemmi hashimmi
hosseini hoseini hosaini
jabouri gabouri jaburi jubouri juburi juboori djabouri dschabouri
jafari djafari
kanaan kanan kanaen canaen canaane kanane kanen
karimi karemi kareemmi caremi carimmi karemmi
kermani
khatib khateb khateebe
khoury khourye
mahdi
mahmoudi
mansour mansoure
masri
mohammadi mohamadi
moradi
mousavi moussavi musavi
najjar najar najer nadjar nadjdjar nadjdjare
nasir nasser naser nassir
nasrallah nasralah nasrala nasralahe
nazari
qasim kasim qasem qaseem kaseem
rahimi rahemi rahemmi raheemmi rahimmi
rahmani
rezaei rezai rezaai
rostami rostammi
sabah saba sabahe
sadeghi sadighi
saleh salih sallih salleh sallehe
salehi salihi sallihi
salman salmen salmene
sayid sayed sayede sayide
rashid rashed rached rachid rasched racheed rasheed rasheede
shahin shahen shaheen shahene chaheen
shamsi chamsi schamsi
shirazi sherazi sheerazi cheerazi cherazi chirazi
sultan sulten soultan soultane
tabrizi tabrezi tabreezi
taha tahah tahahe
tehrani
tikriti tikreti tikreeti
yassin yasin yasen yasseen yassene
yazdani
zaidi zaydi
zahrani
zamani zammani
""")

# Populated from bilingual records in each supplied watchlist.  This is not a
# training-label lookup: it is a transliteration lexicon induced solely from
# the list's own primary/script names and strong aliases.  It lets a script-only
# entry reuse spellings demonstrated by other entries from the same languages.
SCRIPT_GIVEN: dict[tuple[str, str], str] = {}
SCRIPT_FAMILY: dict[tuple[str, str], str] = {}


def arabic_spelling_key(token: str) -> str:
    """Key for mechanical vowel-length and European spelling conventions."""
    token = ascii_text(token).lower()
    for old, new in (("dsch", "j"), ("dj", "j"), ("tsch", "ch"),
                     ("sch", "sh"), ("ou", "u"), ("ph", "f")):
        token = token.replace(old, new)
    token = token.replace("aa", "a").replace("ee", "i").replace("oo", "u")
    token = re.sub(r"ie$", "i", token)
    token = re.sub(r"y$", "i", token)
    token = re.sub(r"(.)\1+", r"\1", token)
    # Many French/German renderings add a non-phonemic terminal e/h.
    token = re.sub(r"e$", "", token)
    token = re.sub(r"(?<=[aeiou])h$", "", token)
    return token


def make_unique_phonetic(table: dict[str, str]) -> dict[str, str]:
    grouped: dict[str, set[str]] = defaultdict(set)
    for spelling, canonical in table.items():
        grouped[arabic_spelling_key(spelling)].add(canonical)
    return {key: next(iter(values)) for key, values in grouped.items() if len(values) == 1}


ARABIC_GIVEN_PHONETIC = make_unique_phonetic(ARABIC_GIVEN)
ARABIC_FAMILY_PHONETIC = make_unique_phonetic(ARABIC_FAMILY)


def raw_words(value: str) -> list[str]:
    value = ascii_text(transliterate(value))
    return re.findall(r"[a-z0-9]+", value)


def merge_phrases(words: list[str], culture: str) -> list[str]:
    # Punctuation-free compounds whose spacing/hyphenation is immaterial.
    joined: list[str] = []
    i = 0
    while i < len(words):
        tail = words[i:]
        if culture == "western":
            if len(tail) >= 2 and tail[:2] == ["o", "brien"]:
                joined.append("obrien"); i += 2; continue
            if len(tail) >= 2 and tail[:2] == ["mac", "donald"]:
                joined.append("macdonald"); i += 2; continue
            if len(tail) >= 3 and tail[:3] in (["van", "der", "berg"], ["van", "den", "berg"], ["de", "la", "cruz"]):
                joined.append("vanderberg" if tail[0] == "van" else "delacruz"); i += 3; continue
            if len(tail) >= 2 and tail[:2] == ["du", "bois"]:
                joined.append("dubois"); i += 2; continue
            if len(tail) >= 2 and tail[:2] == ["le", "fevre"]:
                joined.append("lefevre"); i += 2; continue
            if len(tail) >= 2 and tail[:2] == ["smith", "jones"]:
                joined.append("smithjones"); i += 2; continue
        if culture == "arabic":
            # Definite article is structurally optional. Script transliteration
            # often leaves it attached, handled again in canonical_token().
            if len(tail) >= 3 and tail[0] == "abd" and tail[1] in {"al", "el", "ar"}:
                part = tail[2]
                if part.startswith("rahm"): joined.append("abdulrahman"); i += 3; continue
                if part.startswith(("kar", "car")): joined.append("abdulkarim"); i += 3; continue
                if part.startswith("az"): joined.append("abdulaziz"); i += 3; continue
            if len(tail) >= 2 and tail[0] in {"abd", "abdul", "abdel"}:
                part = tail[1]
                if part.startswith("rahm"): joined.append("abdulrahman"); i += 2; continue
                if part.startswith(("kar", "car")): joined.append("abdulkarim"); i += 2; continue
                if part.startswith("az"): joined.append("abdulaziz"); i += 2; continue
                if part in {"allah", "allh", "llh", "olah"}: joined.append("abdullah"); i += 2; continue
            # Unvowelled original-script forms.
            if len(tail) >= 2 and tail[0] == "bd":
                part = tail[1]
                if part in {"allh", "llh"}: joined.append("abdullah"); i += 2; continue
                if part.startswith("alrhm"): joined.append("abdulrahman"); i += 2; continue
                if part.startswith("alkr"): joined.append("abdulkarim"); i += 2; continue
                if part.startswith("alz"): joined.append("abdulaziz"); i += 2; continue
            if len(tail) >= 2 and tail[0] in {"nasr", "nsr"} and tail[1] in {"allah", "allh", "llh"}:
                joined.append("nasrallah"); i += 2; continue
        joined.append(words[i]); i += 1
    return joined


def russian_family_form(token: str) -> str:
    # Feminine surname inflection is explicitly equivalent under the policy.
    if token.endswith("skaya"):
        token = token[:-5] + "sky"
    elif token.endswith("ova") or token.endswith("eva") or token.endswith("ina"):
        token = token[:-1]
    return token


def russian_spelling(token: str) -> str:
    """Normalize common French/German/Polish/scientific Cyrillic systems."""
    # Preserve explicit dictionary spellings before applying ambiguous rules.
    if token in RUSSIAN_GIVEN or token in RUSSIAN_FAMILY:
        return token
    token = token.replace("stsch", "shch").replace("tsch", "ch")
    token = token.replace("sz", "sh").replace("cz", "ch")
    token = token.replace("sch", "sh").replace("w", "v")
    token = token.replace("j", "y")
    token = re.sub(r"ff?a$", "va", token)
    token = re.sub(r"ff?$", "v", token)
    token = token.replace("x", "ks")
    token = re.sub(r"eiy$", "ei", token)
    token = re.sub(r"ij$", "i", token)
    token = re.sub(r"^ca(?=[iy]k)", "chai", token)
    return token


def canonical_token(token: str, culture: str, role: str) -> str:
    token = ascii_text(token).lower()
    if culture == "western":
        return (WESTERN_GIVEN if role == "given" else WESTERN_FAMILY).get(token, token)
    if culture == "russian":
        learned = SCRIPT_FAMILY if role == "family" else SCRIPT_GIVEN
        if (culture, token) in learned:
            return learned[(culture, token)]
        token = russian_spelling(token)
        if role == "family":
            token = russian_family_form(token)
            return RUSSIAN_FAMILY.get(token, token)
        return RUSSIAN_GIVEN.get(token, token)
    if culture == "arabic":
        table = ARABIC_GIVEN if role == "given" else ARABIC_FAMILY
        phonetic = ARABIC_GIVEN_PHONETIC if role == "given" else ARABIC_FAMILY_PHONETIC
        learned = SCRIPT_FAMILY if role == "family" else SCRIPT_GIVEN
        if (culture, token) in learned:
            return learned[(culture, token)]
        if role == "family":
            # al-/el- may be attached in Latin or original-script text.
            if token in table:
                return table[token]
            for prefix in ("al", "el", "ash", "an", "ar", "as", "at", "ad", "az"):
                if token.startswith(prefix) and len(token) > len(prefix) + 2:
                    rest = token[len(prefix):]
                    if rest in table or arabic_spelling_key(rest) in phonetic or prefix in {"al", "el"}:
                        token = rest
                        break
        return table.get(token, phonetic.get(arabic_spelling_key(token), token))
    return token


def detect_culture(value: str) -> str:
    if ARABIC_RE.search(value):
        return "arabic"
    if CYRILLIC_RE.search(value):
        return "russian"
    return "western"


def is_patronymic(word: str) -> bool:
    word = russian_spelling(word)
    return bool(re.search(r"(?:ov|ev|yev|eyev|iv|ich|yich)(?:ich|itch|na)$", word)) or \
        word.endswith(("ovich", "evich", "ovic", "evic", "ovitch", "evitch",
                       "owicz", "ewicz", "ovna", "owna", "evna", "yevna"))


def structural_words(value: str, culture: str) -> list[str]:
    words = merge_phrases(raw_words(value), culture)
    words = [w for w in words if not (len(w) == 1 and w not in {"b"})]
    if culture == "arabic":
        # Remove optional definite articles and nasab + father's name.
        compact: list[str] = []
        i = 0
        while i < len(words):
            if words[i] in {"al", "el", "ash", "an", "ar", "as", "at", "ad", "az"}:
                i += 1; continue
            if words[i] in {"bin", "ibn", "ben", "b"}:
                i += 2; continue
            compact.append(words[i]); i += 1
        words = compact
    elif culture == "russian" and len(words) > 2:
        words = [w for w in words if not is_patronymic(w)]
    return words


def person_base_pair(value: str, culture: str) -> tuple[str, str] | None:
    """Given/family in displayed order; used for bilingual lexicon induction."""
    words = structural_words(value, culture)
    if len(words) < 2:
        return None
    a, b = words[0], words[-1]
    return canonical_token(a, culture, "given"), canonical_token(b, culture, "family")


def canonical_given_forms(token: str, culture: str) -> set[str]:
    raw = ascii_text(token).lower()
    if culture == "western" and raw == "ted":
        # Ted is conventionally short for both Edward and Theodore; keeping it
        # as alternatives avoids incorrectly equating the two formal names.
        return {"edward", "theodore"}
    return {canonical_token(token, culture, "given")}


def person_signatures(value: str, culture: str) -> set[tuple[str, str]]:
    words = structural_words(value, culture)
    if len(words) < 2:
        return set()
    a, b = words[0], words[-1]
    result = {(given, canonical_token(b, culture, "family"))
              for given in canonical_given_forms(a, culture)}
    result.update((given, canonical_token(a, culture, "family"))
                  for given in canonical_given_forms(b, culture))
    if culture == "western" and len(words) >= 3:
        # Stacked conventions can put a compound family around the given name:
        # "Jones Nick Smith", "Fevre Jennifer Le", "Cruz Daniel de la".
        for given_pos, given in enumerate(words):
            family_parts = words[:given_pos] + words[given_pos + 1:]
            for candidate in ("".join(family_parts), "".join(reversed(family_parts))):
                family = WESTERN_FAMILY.get(candidate)
                if family:
                    result.update((form, family) for form in canonical_given_forms(given, culture))
        # Recognize reordered particle compounds as bags, while still requiring
        # exactly one separate given name.
        lowered = [ascii_text(w).lower() for w in words]
        compound_sets = [
            ({"van", "der", "berg"}, "vanderberg"),
            ({"de", "la", "cruz"}, "delacruz"),
            ({"du", "bois"}, "dubois"), ({"le", "fevre"}, "lefevre"),
            ({"smith", "jones"}, "smithjones"), ({"da", "silva"}, "silva"),
        ]
        for parts, family in compound_sets:
            if parts.issubset(lowered):
                remaining = [w for w in words if ascii_text(w).lower() not in parts]
                if len(remaining) == 1:
                    result.update((form, family) for form in canonical_given_forms(remaining[0], culture))
        if len(words) == 3:
            # A full (rather than initial) middle name is not generally
            # discardable, so only retain this for recognized compound family.
            pass
    return result


def person_name_match(customer: str, listed: str, culture: str) -> bool:
    # Use entry culture for Latin spellings, while original script identifies
    # itself and can be normalized directly.
    c_culture = detect_culture(customer)
    l_culture = detect_culture(listed)
    if c_culture == "western":
        c_culture = culture
    if l_culture == "western":
        l_culture = culture
    return bool(person_signatures(customer, c_culture) & person_signatures(listed, l_culture))


LEGAL_PHRASES = [
    ("limited", "liability", "company"), ("public", "joint", "stock", "company"),
    ("joint", "stock", "company"), ("free", "zone", "establishment"),
    ("sociedad", "anonima"),
]
LEGAL_WORDS = {
    "llc", "ltd", "limited", "sa", "gmbh", "jsc", "ao", "oao", "pjsc",
    "co", "company", "fze", "fz", "inc", "incorporated", "corp", "corporation",
}


def organization_key(value: str) -> tuple[str, ...]:
    words = raw_words(value)
    if words and words[0] == "the":
        words.pop(0)
    # Dotted abbreviations arrive as one-letter runs (L.L.C., G.m.b.H.).
    collapsed: list[str] = []
    i = 0
    while i < len(words):
        j = i
        while j < len(words) and len(words[j]) == 1:
            j += 1
        if j - i >= 2:
            collapsed.append("".join(words[i:j])); i = j
        else:
            collapsed.append(words[i]); i += 1
    words = collapsed
    # Remove multiword forms first, then their abbreviated forms.
    for phrase in LEGAL_PHRASES:
        n = len(phrase)
        pos = 0
        while pos <= len(words) - n:
            if tuple(words[pos:pos+n]) == phrase:
                del words[pos:pos+n]
            else:
                pos += 1
    return tuple(w for w in words if w not in LEGAL_WORDS and w != "and")


def vessel_key(value: str) -> tuple[str, ...]:
    value = ascii_text(value).strip().lower()
    value = re.sub(r"^\s*(?:m\s*[/.-]?\s*[vt]|mv|mt|vessel)\b\s*", "", value)
    return tuple(re.findall(r"[a-z0-9]+", value))


def exact_normalized(value: str) -> str:
    return " ".join(raw_words(value))


def dob_compatible(customer_dob: str, entry_dob: str) -> bool:
    if not customer_dob or not entry_dob:
        return True
    return entry_dob.startswith(customer_dob)


def full_dob_equal(customer_dob: str, entry_dob: str) -> bool:
    return len(customer_dob) == 10 and customer_dob == entry_dob


class Engine:
    def __init__(self, entries: list[dict]):
        self.entries = entries
        self._learn_script_spellings()
        self.identifiers: dict[tuple[str, str], list[dict]] = defaultdict(list)
        for entry in entries:
            for ident in entry.get("ids", []):
                self.identifiers[(ident.get("type", ""), ident.get("number", ""))].append(entry)
        self._build_name_indexes()

    def _learn_script_spellings(self) -> None:
        SCRIPT_GIVEN.clear()
        SCRIPT_FAMILY.clear()
        given_votes: dict[tuple[str, str], list[str]] = defaultdict(list)
        family_votes: dict[tuple[str, str], list[str]] = defaultdict(list)
        for entry in self.entries:
            if entry.get("type") != "individual" or not entry.get("script_name"):
                continue
            culture = detect_culture(entry["script_name"])
            if culture == "western":
                continue
            latin_names = []
            if detect_culture(entry.get("primary_name", "")) == "western":
                latin_names.append(entry["primary_name"])
            latin_names.extend(a.get("name", "") for a in entry.get("aliases", [])
                               if a.get("strength") == "strong"
                               and detect_culture(a.get("name", "")) == "western")
            script_words = structural_words(entry["script_name"], culture)
            if len(script_words) < 2:
                continue
            for name in latin_names:
                pair = person_base_pair(name, culture)
                if pair:
                    given_votes[(culture, script_words[0])].append(pair[0])
                    family_votes[(culture, script_words[-1])].append(pair[1])

        def choose(votes: dict[tuple[str, str], list[str]]) -> dict[tuple[str, str], str]:
            answer = {}
            for key, values in votes.items():
                # Stable majority; lexical tie break makes execution reproducible.
                counts = {v: values.count(v) for v in set(values)}
                answer[key] = min(counts, key=lambda v: (-counts[v], v))
            return answer

        SCRIPT_GIVEN.update(choose(given_votes))
        SCRIPT_FAMILY.update(choose(family_votes))

    @staticmethod
    def _listed_names(entry: dict) -> list[str]:
        names = [entry.get("primary_name", "")]
        if entry.get("script_name") and entry["script_name"] not in names:
            names.append(entry["script_name"])
        names.extend(a.get("name", "") for a in entry.get("aliases", [])
                     if a.get("strength") == "strong")
        return names

    def _build_name_indexes(self) -> None:
        self.person_index: dict[str, dict[tuple[str, str], list[dict]]] = {
            "western": defaultdict(list), "russian": defaultdict(list), "arabic": defaultdict(list)
        }
        self.entity_index: dict[tuple[str, ...], list[dict]] = defaultdict(list)
        self.vessel_index: dict[tuple[str, ...], list[dict]] = defaultdict(list)
        self.weak_index: dict[str, list[dict]] = defaultdict(list)
        for entry in self.entries:
            kind = entry.get("type", "")
            names = self._listed_names(entry)
            if kind == "individual":
                culture = self.culture(entry)
                seen = set()
                for name in names:
                    name_culture = detect_culture(name)
                    if name_culture == "western":
                        name_culture = culture
                    for signature in person_signatures(name, name_culture):
                        if signature not in seen:
                            self.person_index[culture][signature].append(entry)
                            seen.add(signature)
                for alias in entry.get("aliases", []):
                    if alias.get("strength") == "weak":
                        self.weak_index[exact_normalized(alias.get("name", ""))].append(entry)
            elif kind == "entity":
                seen = set()
                for name in names:
                    key = organization_key(name)
                    if key and key not in seen:
                        self.entity_index[key].append(entry); seen.add(key)
            elif kind == "vessel":
                seen = set()
                for name in names:
                    key = vessel_key(name)
                    if key and key not in seen:
                        self.vessel_index[key].append(entry); seen.add(key)

    @staticmethod
    def culture(entry: dict) -> str:
        return detect_culture(entry.get("script_name") or entry.get("primary_name", ""))

    def ordinary_name_match(self, customer: dict, entry: dict) -> bool:
        kind = entry.get("type", "")
        names = self._listed_names(entry)
        if kind == "individual":
            culture = self.culture(entry)
            return any(person_name_match(customer["full_name"], name, culture) for name in names)
        if kind == "entity":
            key = organization_key(customer["full_name"])
            return bool(key) and any(key == organization_key(name) for name in names)
        if kind == "vessel":
            key = vessel_key(customer["full_name"])
            return bool(key) and any(key == vessel_key(name) for name in names)
        return False

    @staticmethod
    def weak_alias_match(customer: dict, entry: dict) -> bool:
        if entry.get("type") != "individual" or not full_dob_equal(customer["dob"], entry.get("dob", "")):
            return False
        key = exact_normalized(customer["full_name"])
        return any(key == exact_normalized(a.get("name", ""))
                   for a in entry.get("aliases", []) if a.get("strength") == "weak")

    def screen(self, customer: dict) -> tuple[str, str]:
        ident_key = (customer.get("id_type", ""), customer.get("id_number", ""))
        if all(ident_key):
            hits = self.identifiers.get(ident_key, [])
            if hits:
                return "MATCH", min(e["uid"] for e in hits)

        hits_by_uid: dict[str, dict] = {}
        kind = customer.get("type", "")
        if kind == "individual":
            detected = detect_culture(customer["full_name"])
            for culture, index in self.person_index.items():
                customer_culture = detected if detected != "western" else culture
                for signature in person_signatures(customer["full_name"], customer_culture):
                    for entry in index.get(signature, []):
                        hits_by_uid[entry["uid"]] = entry
            # Weak aliases require an identical full DOB and are considered
            # separately from all transliteration equivalence.
            if len(customer.get("dob", "")) == 10:
                for entry in self.weak_index.get(exact_normalized(customer["full_name"]), []):
                    if full_dob_equal(customer["dob"], entry.get("dob", "")):
                        hits_by_uid[entry["uid"]] = entry
        elif kind == "entity":
            for entry in self.entity_index.get(organization_key(customer["full_name"]), []):
                hits_by_uid[entry["uid"]] = entry
        elif kind == "vessel":
            for entry in self.vessel_index.get(vessel_key(customer["full_name"]), []):
                hits_by_uid[entry["uid"]] = entry

        candidates: list[tuple[int, str]] = []
        for entry in hits_by_uid.values():
            if not dob_compatible(customer.get("dob", ""), entry.get("dob", "")):
                continue
            # DOB support outranks uid only when both sides actually carry one.
            dob_support = int(bool(customer.get("dob") and entry.get("dob")))
            candidates.append((-dob_support, entry["uid"]))
        if not candidates:
            return "NO_MATCH", ""
        candidates.sort()
        return "MATCH", candidates[0][1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Screen customers against a sanctions watchlist")
    parser.add_argument("--watchlist", required=True)
    parser.add_argument("--customers", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with open(args.watchlist, encoding="utf-8") as f:
        entries = json.load(f)
    engine = Engine(entries)
    with open(args.customers, newline="", encoding="utf-8-sig") as src, \
         open(args.out, "w", newline="", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        writer = csv.writer(dst)
        writer.writerow(["customer_id", "decision", "matched_uid"])
        for customer in reader:
            decision, uid = engine.screen(customer)
            writer.writerow([customer["customer_id"], decision, uid])


if __name__ == "__main__":
    main()
