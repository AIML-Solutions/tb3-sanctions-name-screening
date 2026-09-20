#!/usr/bin/env python3
"""Deterministic sanctions-name screening engine (Python 3.12 stdlib only)."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict


SCRIPT_RE = re.compile(r"[\u0400-\u052f\u0600-\u06ff]")
ARABIC_RE = re.compile(r"[\u0600-\u06ff]")
CYRILLIC_RE = re.compile(r"[\u0400-\u052f]")


def is_script(s: str) -> bool:
    return bool(SCRIPT_RE.search(s or ""))


def fold_latin(s: str) -> str:
    s = ((s or "").lower().replace("ß", "ss").replace("ø", "o")
         .replace("ł", "l").replace("ı", "i").replace("đ", "d"))
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def words(s: str) -> list[str]:
    """Unicode letter/digit words, retaining non-Latin scripts."""
    s = unicodedata.normalize("NFKC", (s or "").lower())
    return re.findall(r"[^\W\d_]+|\d+", s, re.UNICODE)


# These are equivalence classes, not a list of sanctioned people. They encode
# ordinary nicknames and romanization conventions. Exact pair matching below
# still requires both a given name and a family name.
GROUPS = r"""
william bill billy
katherine kate kathy
margaret peggy maggie
michael mike mick mikey
rebecca becca becky
daniel dan danny
andrew andy drew
jose pepe
peter pedro pete
nicholas nick
steven steve stephen
frederick fred freddie freddy
samuel sam
francisco frank paco
elizabeth betty liz elisabeth
alexander alex xander sasha
john jack johnny
christopher chris kit
richard dick rick ricky
joseph joe joey
barbara babs barb
benjamin ben benny
dorothy dottie dot
henry hank
susan sue suzy
jennifer jen jenny
anthony tony
theodore theo ted
victoria tori vicky
james jim jimmy jamie
robert bob bobby
charles chuck
edward ed eddie
patricia pat patty patti
matthew matt

mueller muller
andersen anderson andersson
johansson johanson johansen
lindqvist lindquist lindkvist
weiss weisz
sorensen sorenson
larsen larson
olsen olson
petersen peterson
meyer meier mayer
schmidt schmid schmitt
schroeder schroder
macdonald mcdonald
ferreira ferreyra
fernandez fernandes
rodriguez rodrigues
nowak novak
bianchi bianci
fischer fisher
lefevre fevre
delacruz cruz
vandenberg vanderberg berg

abdullah abdola abdolah abdolla abdollah abdoollah abdoolla abdoollahe abdula abdulah
abdulrahman abdulrahmen abdulrahmane abdelrahman abdelrahmen abdelrahmane abdurrahman abdurrahmen
abdulaziz abdulazez abdulazeez abdulazeze abdulazize abdelaziz abdelazez abdelazeez abduazeez
abdulkarim abdulkarem abdulkareem abdalkarim abdalkarem abdelkarim abdelkarem abdulcarem
adnan adnen adnane adnene
ahmad ahmed ahmade ahmet achmad
aisha aishah aischa aicha aichah aischah aysha
ali aly
amina amena ameena aminahe aminah amenah ameenah
amir amer amire ameer ameere
anwar anwaar anouar anouare
arash arasch arache
babak babaak babake
bashar baschar bachar bachare bashare
behrouz behrouze behruz
bijan bijen bizhan
bilal billal billaal billale billalle
dalal dallal
dariush dariusch darioush dariouch daryush
ehsan ehsen ehsene ehsane
fahd fahed fahde
faisal faysal fayssal faisale faissal faisaal
farhad farhed farhade
fatemeh fatemmeh fatemmehe fatimmih fatimih fateme
fatima fatimah fatemah fatema fateemah fateemma fatemma
golnaz golnaze
hamid hamed hameed hameede hamede hammed hammid
hamza hamzah hamzahe
hanan hanen hanene
hassan hasan hasen hasane hassen
hussein husein houssein housseine husain hussain husayn hossein hosseine hosein hossain huseyin
hisham hicham hishame
huda houda hudah hudahe
ibrahim ibraheem ibrahem ibraheme
ismail ismayl ismayle
jamal djamal djamale dschamal dschammal cemal gamal jammal jammale jammalle
javad javed javade javede djavad djavade djavede dschavad gaved
kamal kammal cammal kamale
kamran kamren kamrane camran camrane
karim karem kareem carem careme
kaveh kavih caveh cavehe cavih
khadija khadijah khadidjah khadejah khadeja khadeegah
khalid khaled khaleed khaleede khalled khallede
layla leila laila leilah leillah laylah
mahmoud mahmud mahmoude
mahsa mahsah
majid majide majed majede majeed madjid madjide madjed madschid madsched
mariam maryam mariame mariamme maryame maryamme
marwan marwaan marwen marouen
masoud massoud massoude
mehdi mehdie mahdi mahdie
mohsen mohsin
morteza mortezah mortiza mortizah mortaza
muhammad mohammed mohamed mohamad mohammad muhamad muhamed muhammed mouhamad muhamade
mustafa mustapha mustafah
nabil nabel nabeel nabeele
nasrin nasreen nasren nasreene
niloufar nilufar nilloufar nilloufare
nizar nizaar nizare
nour noor nur noure
omar omare
omid omed
parisa parissa parisah paressa paresa pareesa
parviz parvez parveez parveze
rami rammi
ramin ramen ramine ramene rameen rameene rammeen rammen rammin
rania raniah
rashid rashed rasheed racheed rachid rasched
reza rezah
saeed saeid saed said saaid saaide
salim salem saleem salleem salime sallem sallim sallimme
salma salmah salmahe
sami sammi
samir samer samere samire sameer sammer sammeer sammire
samira samera sameera sameerah sammera
shahram schahram chahram chahrame
shirin sheereen sherine sheren cheren shirine
siavash siyavash
talal talaal tallal tallaal talale
tariq tarik tarek tareq tareek tarike tareqe
walid waled walede wallede waleed walled walleed oualed wallide
yasser yaser yasir yassir yasere
yusuf yusof yusoof yousuf yousouf yousef youssef yussef yussof yussoof joesoef
zahra zahrah zahrahe
zainab zaynab zaynabe zeinab
ziad zied ziede ziade
qasim kasim kasem kaseem qaseem qassem qassim gassim gasim
sharif sherif sjarif syarif

abbas abas abaas abase
ahmadi ahmadie ahmedi
akbari akberi
amin ameen amen amene elamen elamene
attar atar atare attaar attare elatar elatare
awad awaad awed awade
aziz azeez azez azeze
bagheri baghiri
bakr bakre baker
barakat baracat baracate
darwish darouish darwesh darweshe darwishe darwesch
douri dourie duri
ebrahimi ebrahemi ebraheemi ebraheemmi ebrahemmi ebrahimmi
esfahani esfahany
fares faris
farsi
farahani farahanie
ghanem ghaneme ghanim ghanime
ghasemi ghasimi ghassemmi ghassimi ghassimmi
haddad hadad hadade hadded haded
hakim hakeem hakem hakime hakeme hakeeme
hamdan hamdaan hamden hamdane hamdene
hashemi hashimi hashemmi hashimmi hachimi
hosseini hoseini hosaini hossaini husseini
jabouri jabourie jaburi djabouri dschabouri gabouri
jafari djafari dschafari
kanaan kanan kanen kanaen canaan canaen canaane kanane
karimi karimy karimie karimmi karemi kareemi carimi carimmi karemmi kareemmi
kermani
khatib khateb khateeb khatebe khateebe
khoury khouri khourye
mahmoudi mahmoudie mahmudi
mansour mansur mansoure
masri masry
mohammadi mohamadi
moradi moradie morady
mousavi musavi moussavi
najjar nagar najar najare nadjdjar nadjdjare nadschdschar nadschar
nasrallah nasralla nasralah nasrala nasralahe
nasser naser nasir nassir nassire
nazari
rahimi rahemi raheemi rahimmi rahemmi raheemmi
rahmani
rezaei rezai rezaai
rostami rostammi rostammie
sabah saba sabahe
sadeghi sadeghy sadighi
saleh salih sallih salleh sallehe
salehi salehie salihi sallihi
salman salmaan salmane salmen salmene
sayed sayid sayede sayedh
shahin schahen shahen shahene shaheen chaheen
shamsi shamsie schamsi chamsi
shirazi sheerazi sherazi chirazi cherazi cheerazi
sultan sultaan sultane sulten sultene soultan
tabrizi tabrezi tabreezi
taha tahaah tahah tahahe
tehrani tehranie
tikriti tikreeti tikreti
yassin yasin yasen yassen yaseen yasseen yassene yasseene
yazdani yazdany
zahrani zahrany
zaidi zaidy zaydi
zamani zammani
rahman rahmen rahmane

aleksandr alexandr alexander aleksander alex xander sasha
aleksei aleksey alekseiy alexei alexey aleksej alekseij aleksiej alexeiy alexeij
anastasia anastasiya anastasya anastasja anastasija
anatoly anatoliy anatolij
andrei andrey andreiy andrej andriej
anna
arkady arkadi arkadij
artyom artem artiom artjom
boris
darya daria darja dara
denis
dmitri dmitry dmitriy dmitrij
ekaterina yekaterina
elena yelena
fyodor fedor fjodor fiodor
galina
gennady gennadi gennadij
grigory grigori grigorij
igor
irina
ivan
konstantin
kseniya ksenia ksenija
leonid
lyudmila liudmila ljudmila lyoudmila ludmila
maksim maxim
maria mariya marija marya
marina
mikhail michail mihail
nadezhda nadejda nadezda nadiezda
natalia natalya nataliya natalja natala
nikolai nikolay nikolaiy nikolaj
oksana oxana
oleg
olga
pavel pawel
roman
ruslan rouslan
semyon semen semion semjon
sergei sergey sergej serguei serguey sergeiy sergueiy
stanislav stanislaff
svetlana swetlana
tatiana tatyana tatana tatjana
timur timour
valentina walentina
valery valeriy valeri valerij walery
vasily vasili vasiliy vasilij wasily
viktor victor
viktoria viktorija viktoriya viktorya victoria tori vicky
vladimir wladimir
vyacheslav viacheslav vyatcheslav vyatcheslaff vaceslav vjaczeslav wjaczeslaw wiaczeslaw
yelizaveta elizaveta jelizawieta
yevgeny evgeny yevgeni evgeni evgenij jewgienij eugene
yulia yuliya julia julija yulya youlia ulia
yuri yury yuriy iuri jurij juriy urij
zhanna janna shanna zanna

andreev andreew andreeff
belousov belousoff belousow
bondarenko
bykov bykoff bykow
chaikovsky tchaikovsky tschaikovsky cajkovskij cajkovsky cajkovskaja cajkovskaa czajkowski czajkowska czajkovskij czajkovskaja
chernov tchernov tchernoff tschernov tschernow cernov czernov czernow
egorov yegorov
fedorov fedoroff fedorow fjodorov
grishin grichin grischin grisin griszin
ivanov ivanoff
kiselyov kiselev kiseliov kiseljov kiselov kiselioff
kovalenko kowalenko
kozlov
kravchenko kravtchenko kravcenko krawczenko
kuznetsov kusnetsov kuznecov kuznjecov
lebedev lebedew lebedeff
makarov makaroff
morozov morosov morosow morozoff
nikolaev nikolaew nikolaeff
novikov novikoff
orlov orlow
pavlov pavloff pawlow
petrov petroff
popov popoff popow
semyonov semenov semionov semionoff semjonov
shcherbakov shtcherbakov schcherbakov chcherbakov chcherbakoff scerbakov serbakov szczerbakov szczerbakow
shevchenko shevtchenko shevtschenko stschevtschenko sevchenko sevcenko szewczenko
shishkin tchitchkin chichkin schischkin siskin sziszkin szyszkin
smirnov smirnoff
sokolov sokoloff
stepanov stepanoff
tkachenko tkatchenko tkacenko tkaczenko
tsoi tsoy tsoiy tzoiy tzoy zoij coj
tsvetkov tzvetkov tzvetkoff zvetkov swetkov svetkov cvetkov cvietkov
volkov volkoff
yakovlev iakovlev jakovlev yakowlew yakovleff iakovleff akovlev
yashin iashin jashin jaschin jaszin yaschin iachin jastschin jastschina asin jaszyn
zaitsev saitsev zaitzev zaitzeff zajcev zajcew
zakharov zakharoff zatscharov zaharov zacharov zacharow
zhukov jukov zukov shukov zhoukov
"""


TOKEN_CANON: dict[str, str] = {}
for _line in GROUPS.splitlines():
    _items = _line.split()
    if _items:
        for _item in _items:
            TOKEN_CANON[_item] = _items[0]


CYRILLIC_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ё": "yo", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya", "і": "i", "ї": "yi", "є": "ye",
    "ґ": "g",
}


def translit_cyrillic(token: str) -> str:
    return "".join(CYRILLIC_MAP.get(ch, ch) for ch in token.lower())


def script_kind(s: str) -> str:
    if ARABIC_RE.search(s or ""):
        return "arab"
    if CYRILLIC_RE.search(s or ""):
        return "cyr"
    return "west"


def build_script_dictionary(entries: list[dict]) -> dict[str, str]:
    """Learn token readings from bilingual rows in the supplied watchlist."""
    votes: dict[str, Counter[str]] = defaultdict(Counter)
    for e in entries:
        sn = e.get("script_name") or ""
        if not is_script(sn):
            continue
        latin_names = []
        if not is_script(e.get("primary_name", "")):
            latin_names.append(e["primary_name"])
        latin_names.extend(
            a.get("name", "") for a in e.get("aliases", [])
            if a.get("strength") == "strong" and not is_script(a.get("name", ""))
        )
        st = words(sn)
        for ln in latin_names:
            lt = words(fold_latin(ln))
            if len(st) == len(lt):
                for a, b in zip(st, lt):
                    votes[a][b] += 1
            # Arabic's definite article is attached in script but may be a
            # separate Latin word.  Align a second, article-free view.
            ast = [x[2:] if x.startswith("ال") and len(x) > 2 else x for x in st]
            alt = [x for x in lt if x not in ARTICLES]
            if len(ast) == len(alt):
                for a, b in zip(ast, alt):
                    votes[a][b] += 1
    result = {}
    for token, counts in votes.items():
        result[token] = min(counts, key=lambda x: (-counts[x], len(x), x))
    return result


ARTICLES = {"al", "el"}
ARABIC_ARTICLES = ARTICLES | {"ad", "an", "ar", "as", "ash", "at", "az"}
NASAB = {"bin", "ibn", "ben", "b", "bn"}
PATRONYMIC_RE = re.compile(r"(?:ov|ev|yev|eyev|iv|in)?(?:ich|itch|itsch|icz)$|(?:ov|ev|yev|eyev|in)na$")

ARABIC_SCRIPT_COMPOUNDS = {
    ("عبد", "الله"): "abdullah",
    ("عبد", "الرحمن"): "abdulrahman",
    ("عبد", "العزيز"): "abdulaziz",
    ("عبد", "الكريم"): "abdulkarim",
    ("نصر", "الله"): "nasrallah",
}

RUS_GIVENS = {
    "aleksandr", "aleksei", "anastasia", "anatoly", "andrei", "anna", "arkady",
    "artyom", "boris", "darya", "denis", "dmitri", "ekaterina", "elena", "fyodor",
    "galina", "gennady", "grigory", "igor", "irina", "ivan", "konstantin", "kseniya",
    "leonid", "lyudmila", "maksim", "maria", "marina", "mikhail", "nadezhda",
    "natalia", "nikolai", "oksana", "oleg", "olga", "pavel", "roman", "ruslan",
    "semyon", "sergei", "stanislav", "svetlana", "tatiana", "timur", "valentina",
    "valery", "vasily", "viktor", "viktoria", "vladimir", "vyacheslav", "yelizaveta",
    "yevgeny", "yulia", "yuri", "zhanna",
}


def raw_person_tokens(name: str, mode: str, script_dict: dict[str, str]) -> tuple[list[str], bool]:
    comma = "," in (name or "")
    out: list[str] = []
    raws = words(name)
    if mode == "arab":
        compacted: list[str] = []
        i = 0
        while i < len(raws):
            pair = tuple(raws[i:i + 2])
            if pair in ARABIC_SCRIPT_COMPOUNDS:
                compacted.append(ARABIC_SCRIPT_COMPOUNDS[pair])
                i += 2
            else:
                compacted.append(raws[i])
                i += 1
        raws = compacted
    for raw in raws:
        if is_script(raw):
            stripped = raw[2:] if raw.startswith("ال") and len(raw) > 2 else raw
            val = script_dict.get(raw) or script_dict.get(stripped)
            if val is None and CYRILLIC_RE.search(raw):
                val = translit_cyrillic(raw)
            elif val is None:
                val = raw
        else:
            val = fold_latin(raw)
        if mode == "arab" and val.isascii() and len(val) > 4 and val not in TOKEN_CANON:
            for prefix in sorted(ARABIC_ARTICLES, key=len, reverse=True):
                if val.startswith(prefix) and TOKEN_CANON.get(val[len(prefix):]) is not None:
                    out.extend([prefix, val[len(prefix):]])
                    break
            else:
                out.append(val)
            continue
        out.append(val)

    def combine_sequence(seq: list[str], pattern: tuple[str, ...], replacement: str) -> list[str]:
        i = 0
        ans: list[str] = []
        while i < len(seq):
            if tuple(seq[i:i + len(pattern)]) == pattern:
                ans.append(replacement)
                i += len(pattern)
            else:
                ans.append(seq[i])
                i += 1
        return ans

    out = combine_sequence(out, ("o", "brien"), "obrien")
    out = combine_sequence(out, ("mac", "donald"), "macdonald")
    out = combine_sequence(out, ("mc", "donald"), "macdonald")
    out = combine_sequence(out, ("le", "fevre"), "lefevre")
    out = combine_sequence(out, ("de", "la", "cruz"), "delacruz")
    out = combine_sequence(out, ("van", "der", "berg"), "vandenberg")
    if "smith" in out and "jones" in out:
        first = min(out.index("smith"), out.index("jones"))
        out = [x for x in out if x not in {"smith", "jones"}]
        out.insert(min(first, len(out)), "smithjones")

    if mode == "arab":
        # Articles may occur inside a compound ("Abd al Rahman").
        out = [x for x in out if x not in ARABIC_ARTICLES]
        joined: list[str] = []
        i = 0
        while i < len(out):
            x = out[i]
            if x in {"abd", "abdel", "abdal", "abdul", "abdol"} and i + 1 < len(out):
                y = TOKEN_CANON.get(out[i + 1], out[i + 1])
                if y in {"rahman", "aziz", "karim"}:
                    joined.append("abdul" + y)
                    i += 2
                    continue
            joined.append(x)
            i += 1
        out = joined
    elif mode == "west":
        # These particles are represented inside the normalized compound
        # surname; discard stray/reordered copies (e.g. "Cruz Daniel de la").
        out = [x for x in out if x not in {"de", "la", "le", "van", "der", "den"}]

    result = []
    for x in out:
        if x in ARABIC_ARTICLES:
            continue
        if len(x) == 1 and not (mode == "arab" and x in NASAB):
            continue
        # Structural "ben" must not turn into the Western nickname for Benjamin.
        result.append(x if mode == "arab" and x in NASAB else TOKEN_CANON.get(x, x))
    return result, comma


def russian_family(token: str) -> str:
    token = TOKEN_CANON.get(token, token)
    if token in RUS_GIVENS:
        return token
    token = token.replace("w", "v")
    if token.endswith("offa"):
        token = token[:-4] + "ov"
    elif token.endswith("effa"):
        token = token[:-4] + "ev"
    elif token.endswith("owa"):
        token = token[:-3] + "ov"
    elif token.endswith("ewa"):
        token = token[:-3] + "ev"
    token = TOKEN_CANON.get(token, token)
    if token.endswith("skaya"):
        token = token[:-5] + "sky"
    elif token.endswith("ova") or token.endswith("eva") or token.endswith("ina"):
        token = token[:-1]
    return TOKEN_CANON.get(token, token)


def is_patronymic(token: str) -> bool:
    probe = token.replace("w", "v")
    return bool(PATRONYMIC_RE.search(probe)) or probe in {
        "aleksandrovich", "alekseevich", "ivanovich", "mikhailovich",
        "nikolaevich", "petrovich", "sergeyevich", "vladimirovich",
        "aleksandrovna", "alekseevna", "ivanovna", "mikhailovna",
        "nikolaevna", "petrovna", "sergeyevna", "vladimirovna",
    }


def person_core(name: str, mode: str, script_dict: dict[str, str]) -> tuple[str, str] | None:
    ts, comma = raw_person_tokens(name, mode, script_dict)
    if not ts:
        return None
    ts = ["bin" if x in NASAB else x for x in ts]

    if comma:
        left_name, right_name = (name.split(",", 1) + [""])[:2]
        left, _ = raw_person_tokens(left_name, mode, script_dict)
        right, _ = raw_person_tokens(right_name, mode, script_dict)
        left = [x for x in left if x not in NASAB]
        right = [x for x in right if x not in NASAB]
        right = [x for x in right if not (mode == "cyr" and is_patronymic(x))]
        if left and right:
            given, family = right[0], left[-1]
            if mode == "cyr":
                family = russian_family(family)
            return tuple(sorted((given, family)))

    if "bin" in ts:
        i = ts.index("bin")
        if i == 1 and len(ts) >= 3:
            given, family = ts[0], ts[-1]
        elif i >= 2:
            given, family = ts[i - 1], ts[0]
        else:
            return None
        return tuple(sorted((given, family)))

    if mode == "cyr":
        ts = [x for x in ts if not is_patronymic(x)]
    if len(ts) < 2:
        return None
    a, b = ts[0], ts[-1]
    if mode == "cyr":
        a, b = russian_family(a), russian_family(b)
    return tuple(sorted((a, b)))


LEGAL_TOKENS = {
    "the", "and", "llc", "ltd", "limited", "liability", "company", "co",
    "sa", "sociedad", "anonima", "gmbh", "jsc", "joint", "stock", "ao",
    "oao", "pjsc", "fze", "fz", "inc", "incorporated", "corp",
    "corporation", "plc", "public", "private", "establishment", "free", "zone",
}


def entity_key(name: str) -> tuple[str, ...]:
    ts = words(fold_latin(name).replace("&", " and "))
    for dotted in (["g", "m", "b", "h"], ["l", "l", "c"], ["s", "a"]):
        while True:
            try:
                i = next(i for i in range(len(ts) - len(dotted) + 1) if ts[i:i + len(dotted)] == dotted)
            except StopIteration:
                break
            ts[i:i + len(dotted)] = []
    return tuple(x for x in ts if x not in LEGAL_TOKENS)


VESSEL_PREFIX_WORDS = {"mv", "mt", "vessel"}


def vessel_key(name: str) -> tuple[str, ...]:
    ts = words(fold_latin(name))
    if len(ts) >= 2 and ts[0] == "m" and ts[1] in {"v", "t"}:
        ts = ts[2:]
    elif ts and ts[0] in VESSEL_PREFIX_WORDS:
        ts = ts[1:]
    return tuple(ts)


def weak_key(name: str) -> tuple[str, ...]:
    return tuple(words(fold_latin(name)))


def dob_compatible(customer_dob: str, entry_dob: str) -> bool:
    c, e = (customer_dob or "").strip(), (entry_dob or "").strip()
    return not c or not e or e.startswith(c)


def dob_support(customer_dob: str, entry_dob: str) -> bool:
    return bool((customer_dob or "").strip() and (entry_dob or "").strip() and dob_compatible(customer_dob, entry_dob))


def prepare(entries: list[dict]) -> tuple[dict, dict, dict, dict]:
    script_dict = build_script_dictionary(entries)
    id_index: dict[tuple[str, str], list[dict]] = defaultdict(list)
    name_index: dict[tuple, list[dict]] = defaultdict(list)
    weak_index: dict[tuple[str, ...], list[dict]] = defaultdict(list)
    for e in entries:
        for ident in e.get("ids", []):
            typ = (ident.get("type") or "").strip().lower()
            num = (ident.get("number") or "").strip()
            if typ and num:
                id_index[(typ, num)].append(e)
        typ = (e.get("type") or "").strip().lower()
        names = [e.get("primary_name", ""), e.get("script_name") or ""]
        names.extend(a.get("name", "") for a in e.get("aliases", []) if a.get("strength") == "strong")
        seen = set()
        if typ == "individual":
            mode = script_kind(e.get("script_name") or e.get("primary_name", ""))
            for name in names:
                core = person_core(name, mode, script_dict) if name else None
                key = (typ, mode, core)
                if core is not None and key not in seen:
                    name_index[key].append(e)
                    seen.add(key)
        elif typ == "entity":
            for name in names:
                core = entity_key(name) if name else ()
                key = (typ, core)
                if core and key not in seen:
                    name_index[key].append(e)
                    seen.add(key)
        elif typ == "vessel":
            for name in names:
                core = vessel_key(name) if name else ()
                key = (typ, core)
                if core and key not in seen:
                    name_index[key].append(e)
                    seen.add(key)
        for alias in e.get("aliases", []):
            if alias.get("strength") == "weak":
                key = weak_key(alias.get("name", ""))
                if key:
                    weak_index[key].append(e)
    return script_dict, id_index, name_index, weak_index


def entry_name_matches(customer: dict, entry: dict, script_dict: dict[str, str]) -> bool:
    typ = (customer.get("type") or "").strip().lower()
    if typ != (entry.get("type") or "").strip().lower():
        return False
    names = [entry.get("primary_name", ""), entry.get("script_name") or ""]
    names.extend(a.get("name", "") for a in entry.get("aliases", []) if a.get("strength") == "strong")
    names = [n for n in names if n]
    cname = customer.get("full_name", "")
    if typ == "entity":
        ck = entity_key(cname)
        return bool(ck) and any(ck == entity_key(n) for n in names)
    if typ == "vessel":
        ck = vessel_key(cname)
        return bool(ck) and any(ck == vessel_key(n) for n in names)
    if typ != "individual":
        return False
    mode = script_kind(entry.get("script_name") or entry.get("primary_name", ""))
    ck = person_core(cname, mode, script_dict)
    return ck is not None and any(ck == person_core(n, mode, script_dict) for n in names)


def weak_alias_matches(customer: dict, entry: dict) -> bool:
    c_dob = (customer.get("dob") or "").strip()
    e_dob = (entry.get("dob") or "").strip()
    if not c_dob or len(c_dob) != 10 or c_dob != e_dob:
        return False
    ck = weak_key(customer.get("full_name", ""))
    return any(
        a.get("strength") == "weak" and ck == weak_key(a.get("name", ""))
        for a in entry.get("aliases", [])
    )


def choose(candidates: list[tuple[dict, bool, bool]]) -> dict | None:
    if not candidates:
        return None
    return min(candidates, key=lambda x: (not x[1], not x[2], str(x[0].get("uid", ""))))[0]


def screen_one(customer: dict, entries: list[dict], script_dict: dict[str, str], id_index: dict,
               name_index: dict, weak_index: dict) -> dict | None:
    id_type = (customer.get("id_type") or "").strip().lower()
    id_number = (customer.get("id_number") or "").strip()
    if id_type and id_number:
        hits = id_index.get((id_type, id_number), [])
        if hits:
            return choose([(e, True, dob_support(customer.get("dob", ""), e.get("dob", ""))) for e in hits])

    typ = (customer.get("type") or "").strip().lower()
    cname = customer.get("full_name", "")
    name_hits: list[dict] = []
    if typ == "individual":
        for mode in ("arab", "cyr", "west"):
            core = person_core(cname, mode, script_dict)
            if core is not None:
                name_hits.extend(name_index.get((typ, mode, core), []))
    elif typ == "entity":
        name_hits.extend(name_index.get((typ, entity_key(cname)), []))
    elif typ == "vessel":
        name_hits.extend(name_index.get((typ, vessel_key(cname)), []))

    candidates: list[tuple[dict, bool, bool]] = []
    seen_uids = set()
    for e in name_hits:
        uid = e.get("uid")
        if uid in seen_uids or not dob_compatible(customer.get("dob", ""), e.get("dob", "")):
            continue
        seen_uids.add(uid)
        candidates.append((e, False, dob_support(customer.get("dob", ""), e.get("dob", ""))))

    # Weak aliases are deliberately a separate, exact-name path and require an
    # identical full DOB. They never enter the ordinary name index.
    for e in weak_index.get(weak_key(cname), []):
        uid = e.get("uid")
        if uid in seen_uids or (e.get("type") or "").strip().lower() != typ:
            continue
        if weak_alias_matches(customer, e):
            seen_uids.add(uid)
            candidates.append((e, False, True))
    return choose(candidates)


def run(watchlist_path: str, customers_path: str, out_path: str) -> None:
    with open(watchlist_path, encoding="utf-8") as f:
        entries = json.load(f)
    if not isinstance(entries, list):
        raise ValueError("watchlist JSON must contain a list")
    script_dict, id_index, name_index, weak_index = prepare(entries)
    with open(customers_path, newline="", encoding="utf-8-sig") as f:
        customers = list(csv.DictReader(f))
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["customer_id", "decision", "matched_uid"])
        writer.writeheader()
        for customer in customers:
            hit = screen_one(customer, entries, script_dict, id_index, name_index, weak_index)
            writer.writerow({
                "customer_id": customer.get("customer_id", ""),
                "decision": "MATCH" if hit else "NO_MATCH",
                "matched_uid": hit.get("uid", "") if hit else "",
            })


def main() -> None:
    p = argparse.ArgumentParser(description="Screen customer records against a sanctions watchlist")
    p.add_argument("--watchlist", required=True)
    p.add_argument("--customers", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    run(args.watchlist, args.customers, args.out)


if __name__ == "__main__":
    main()
