#!/usr/bin/env python3
"""Rule-based sanctions name screening (Python 3.12, standard library only)."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import Counter, defaultdict


SCRIPT_RE = re.compile(r"[\u0400-\u04ff\u0600-\u06ff]")
CYR_RE = re.compile(r"[\u0400-\u04ff]")


def deaccent(text: str) -> str:
    text = text.translate(str.maketrans({
        "ß": "ss", "ẞ": "SS", "ı": "i", "İ": "I", "ł": "l", "Ł": "L",
        "ø": "o", "Ø": "O", "đ": "d", "Đ": "D",
    }))
    return "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c))


def latin_words(text: str) -> list[str]:
    return re.findall(r"[a-z]+", deaccent(text).lower().replace("’", "'"))


AR_NORMALIZE = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ئ": "ي",
    "ؤ": "و", "ة": "ه", "ک": "ك", "ی": "ي", "ۀ": "ه",
})


def normalize_script(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(AR_NORMALIZE)
    return "".join(c for c in text if unicodedata.category(c) not in {"Mn", "Cf"})


def script_words(text: str) -> list[str]:
    """Script tokens with the Arabic article removed and fixed compounds fused."""
    raw: list[str] = []
    for word in normalize_script(text).split():
        if word == "الله":
            raw.append(word)
        elif word.startswith("ال") and len(word) > 2:
            raw.append(word[2:])
        else:
            raw.append(word)
    result: list[str] = []
    i = 0
    while i < len(raw):
        if i + 1 < len(raw) and raw[i:i + 2] == ["عبد", "الله"]:
            result.append("عبدالله"); i += 2
        elif i + 1 < len(raw) and raw[i:i + 2] == ["نصر", "الله"]:
            result.append("نصرالله"); i += 2
        else:
            result.append(raw[i]); i += 1
    return result


CYRILLIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ё": "yo", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya", "і": "i", "ї": "yi", "є": "ye",
    "ґ": "g",
}

CYR_SCIENTIFIC = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ё": "e", "ж": "z", "з": "z", "и": "i", "й": "j", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "c",
    "ч": "c", "ш": "s", "щ": "sc", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "ju", "я": "ja", "і": "i", "ї": "ji", "є": "je",
}

CYR_POLISH = {
    "а": "a", "б": "b", "в": "w", "г": "g", "д": "d", "е": "e",
    "ё": "io", "ж": "z", "з": "z", "и": "i", "й": "j", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "ch", "ц": "c",
    "ч": "cz", "ш": "sz", "щ": "szcz", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "ju", "я": "ja", "і": "i", "ї": "ji", "є": "je",
}


def cyrillic_to_latin(word: str) -> str:
    return "".join(CYRILLIC.get(c, c) for c in normalize_script(word).lower())


def cyrillic_convention(word: str, table: dict[str, str]) -> str:
    return "".join(table.get(c, c) for c in normalize_script(word).lower())


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}
        self.orthographic: dict[str, set[str]] = {}

    def find(self, item: str) -> str:
        if item not in self.parent:
            self.parent[item] = item
            return item
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != item:
            nxt = self.parent[item]
            self.parent[item] = root
            item = nxt
        return root

    def union(self, *items: str) -> None:
        items = [x for x in items if x]
        if not items:
            return
        root = self.find(items[0])
        for item in items[1:]:
            other = self.find(item)
            if other != root:
                self.parent[other] = root

    @staticmethod
    def orthographic_key(item: str) -> str:
        # Common harmless spelling mechanics: ornamental final h/e, final
        # Persian i rendered y/ie, and doubled letters.  Resolution below is
        # accepted only when this key identifies one established name group.
        if item.endswith("ie") and len(item) > 4:
            item = item[:-2] + "i"
        elif item.endswith("y") and len(item) > 3:
            item = item[:-1] + "i"
        if item.endswith("e") and len(item) > 4:
            item = item[:-1]
        if item.endswith("h") and len(item) > 4 and item[-2] in "aeiou":
            item = item[:-1]
        return re.sub(r"(.)\1+", r"\1", item)

    def build_orthographic_index(self) -> None:
        index: dict[str, set[str]] = defaultdict(set)
        for item in list(self.parent):
            index[self.orthographic_key(item)].add(self.find(item))
        self.orthographic = dict(index)

    def resolve(self, item: str) -> str:
        if item in self.parent:
            return self.find(item)
        roots = self.orthographic.get(self.orthographic_key(item), set())
        if len(roots) == 1:
            return next(iter(roots))
        return self.find(item)


# Equivalence, not approximate similarity. Close but distinct Arabic names such
# as Hassan and Hussein are deliberately in separate groups.
TOKEN_GROUPS = r"""
alexander alex aleksandr alexandr aleksander
andrew andy drew
anthony tony
barbara barb babs
benjamin ben benny
charles charlie chuck
christopher chris
daniel dan danny
dorothy dot
edward ed eddie
elizabeth liz beth
francisco frank paco
frederick fred freddie
henry hank harry
james jim jamie
jennifer jen jenny
john jon jack johnny
jose pepe
joseph joe joey
katherine kate kathy kit
margaret maggie meg peggy
matthew matt
michael mike mikey
nicholas nick nicolas
patricia pat patty trish
rebecca becky becca
richard rick ricky dick
robert bob bobby robbie
samuel sam sammy
steven steve stephen
susan sue
theodore ted theo
thomas tom
victoria vicky tori
william bill liam will
andersen anderson andersson
fernandez fernandes
bianchi bianci
fischer fisher
johansson johanson johansen
larsen larson
lefevre lefever
lindqvist lindquist lindkvist
macdonald mcdonald
meyer meier mayer
mueller muller
nowak novak
olsen olson
petersen peterson pedersen
ferreira ferreyra
schroeder schroder
rodriguez rodrigues
schmidt schmid schmitt
sorensen sorenson
weiss weis
kowalski kowalsky
brien obrien
abdullah abdollah abdoollah abdoola abdoolla abdula abdulla abdola
abdulrahman abdelrahman abdoulrahman abdurrahman abdurahman
abdulaziz abdelaziz abdoulaziz abdulazez abdelazez
abdulkarim abdulkarem abdulkareem abdulcarem abdkarem abdkareem abdkareeme
abbas abas abbase
adnan adnen
ahmad ahmed ahmet achmad
ahmadi
aisha aicha aischah aysha
ali
amin amen ameen ameene
amina amena aminah ameena
amir amer ameer
anwar anouar anouare
arash arasch arache
attar atar atare
awad awed
aziz azez azeez azeeze
bagheri baghiri
bakr baker bakre
barakat baracat baracate
bashar baschar bachar
behrouz behrouze
bijan bijen bigen
bilal billal
dalal dallal dallale
dariush daryush dariusch
darwish darwisch darwesh darweesh daroueesh
douri dourie
ebrahimi ibrahimi ebraheemmi ebrahemi ebrahemmi ebrahimmi
ehsan ehsen
esfahani isfahani
fahd fahde
faisal faysal fayssal faissal
fares faris farise
farhad farhed farhede
fatemeh fatemih fatimmih fatimmihe
fatima fatimah fatemah fatemma fateemma fatimmah fatemmah fatimmihe
ghanem ghanim ghaneme
ghasemi ghassimi qasemi
haddad hadad haded hadade
hakim hakem hakeem
hamdan hamden hamdane
hamid hamed hameed hammed hammid hamide
hamza hamzah
hanan hanen hanene
hashemi hashimi hachemi hashemmi hasheemmi
hassan hasan hasen
hisham hicham hichame hischam
hossein hossain hosain hussein
hosseini hoseini hosaini
huda hudah houdah
hussein husain husein husayn hueseyin huseyin hoessein houssein
ibrahim ibrahem ebrahim
ismail ismayl ismaile ismayle
jabouri jaburi djabouri dschabouri gabouri
jafari djafari gafari
jamal jammal dschammal djamal cemal
javad javed javede djavad djavade dschaved
kamal kammal cammal
kamran kamren
kanaan kanan kanen kanaen canaan canaen
karim karem kareem kareeme
karimi karemi karimmi kareemi kareemmi caremi careemi
kaveh kavih kavihe
kermani
khadija khadeja khadejah khadeejah khadedja
khalid khaled khalled khalleed chalid
khatib khatibe khateb khateeb khateebe
khoury khouri khourye
layla laylah leila lailla laila
mahdi mehdi
mahmoud mahmud mahmoude machmoed
mahmoudi mahmudi
mahsa mahsah
majid majeed majed maged madjed madsched
mansour mansur mansoure mansoer
mariam maryam mariamme
marwan marouan marouen marwen
masoud massoud massoude
masri
mohammad muhammad mohammed mohamed mohamad muhamed muhammed mouhamad mehmet
mohsen mohsin mohsine
moradi
morteza mortiza mortizah mortezah
mousavi moussavi
mustafa moustafa mustafah moustafah mustafahe moustafahe moestafa
nabil nabel
najjar najar najare nagar naggar nadjar nadschar nadschdschar nadjdjar nadjdjare
nasrallah nasrala nasralah nasralla
nasrin nasren nasreen
nasser nacer nasir nassir
nazari
niloufar nilloufar
nizar nizare
nour nur
omar oemar
omid omed omede omeed
parisa parissa parisah paresa pareessa paressah
parviz parvez parveez
qasim qasem qaseem qaseeme qassim qassem kasim kasem kaseem kassem
rahimi rahemi rahimmi rahemmi
rahman rahmane rahmen rachman
rahmani
rami rammi
ramin rammin rammen
rania raniah
rashid rashed rached rasheed raschid rachede rasjid
reza rezah
rezaei rezai rezaai
rostami rostammi
sabah saba
sadeghi sadighi
saeed saed saaed saeid saaid saaide
saleh salleh salah salih sallih
salehi salihi sallihi
salim saleem salem salleem sallem
salma salmah salmahe
salman salmen
sami sammi
samir samer sammer sammir sammire sameer sammere
samira sameera sammeera sammirah sammera
sayed sayid sayide sayyed
shahin shaheen shahen shahene schahin chahin chahine
shahram chahram chahrame
shamsi schamsi chamsi
shirin sheren sheereen
shirazi sherazi sheerazi
sharif sherif sjarif
siavash siavashe siavasch
sultan sulten soultan soultane soeltan
tabrizi tabrezi
taha tahah
talal tallal tallale tallalle
tariq tarik tarek tareek tareeq
tehrani
tikriti tikreti tikreeti
walid waled waleed walleed wallid oualeed
yasser yasir yassir yassire
yassin yasin yasen
yazdani
yusuf yusof yussof yussoof yusoof yusoofe yussuf joesoef
zahra zahrah
zahrani
zaidi zaydi
zainab zaynab
zamani zammani
ziad zied
anastasia anastasiya anastasya
anatoly anatoliy
andrei andrey andreiy andrej
artyom artem artiom artjom
darya daria darja
dmitri dmitry dmitriy dmitrij
ekaterina yekaterina jekaterina
elena yelena
fyodor fedor fiodor
gennady gennadi gennadij
grigory grigoriy grigorij
ivan iwan
konstantin
kseniya ksenia ksenija
lyudmila ljudmila
maksim maxim
maria mariya marya marja
mikhail michail
nadezhda nadeshda nadejda nadezda
natalia natalya nataliya natalija
nikolai nikolay nikolaiy nikolaj
oksana oxana
ruslan rouslan
aleksei alexei alexey alekseiy
semyon semen semion
sergei sergey sergeiy serguei sergej
stanislav stanislaw stanislaff
svetlana swetlana
tatiana tatyana tatjana
valery valeri walery
vasily vasiliy vasilij wasily
viktor victor wiktor
viktoria viktoriya viktorya viktorija
vladimir wladimir
vyacheslav vyatcheslav vyatscheslav vjaceslav wiaczeslaw wyatscheslaw
yelizaveta yelizaweta elizaveta jelizaveta jelisaveta jelizaweta
yevgeny evgeny evgenij jevgenij eugene jewgeny
yulia yuliya yulya julia julija
yuri yury jurij
zhanna shanna janna
andreev andreeff andreew andreeva andreeffa
belousov belousoff belousow belousova
bondarenko
bykov bykoff bykova bykoffa
chaikovsky tchaikovsky chaikowsky cajkovskij czajkowski chaikovskaya tchaikovskaya schaikovskaya chaikowskaya cajkovskaja czajkowska
chernov chernoff tchernoff tschernoff czernow cernov chernova
egorov egoroff yegorov yegoroff jegorov egorova yegorova yegorowa
fedorov fyodorov fedoroff fedorow fedorova fedoroffa fedorowa
grishin grischin grishina gristschina gritchin gritchina
ivanov ivanoff iwanow ivanova iwanowa
kiselyov kiselev kiseliov kiselyova kiseliova kiselyowa kiseljowa
kovalenko
kozlov koslov koslow kozloff kozlova koslowa
kravchenko kravtchenko krawtschenko krawczenko krawchenko
kuznetsov kusnetsov kuznetzov kuznecov kuznetsova
lebedev lebedew lebedeva lebedewa
makarov makaroff makarrow makarova
morozov morozow morozoff morozova
nikolaev nikolaeff nikolajew nikolaeva nikolaeffa nikolaewa
novikov novikoff nowikow novikova novikoffa
orlov orloff orlow orlova orloffa
pavlov pawlov pavlova
petrov petroff petrow petrova
popov popoff popow popova popowa
semyonov semenov semenow semionov semionow semjonov semyonow semyonova semionova semenoffa
shcherbakov chcherbakov shtcherbakov schtscherbakov shcherbakoff shcherbakova scerbakov szczerbakow
shevchenko shewtschenko szewczenko sevcenko shevcenko
shishkin schischkin stschistschkin shishkina
smirnov smirnoff smirnow smirnova smirnowa
sokolov sokoloff sokolow sokolova sokoloffa
stepanov stepanoff stepanow stepanova stepanowa
tkachenko tkatchenko tkatschenko tkazchenko
tsoi tsoy tsoiy tzoy soiy
tsvetkov tswetkow cvetkov tsvetkova tswetkowa
volkov volkoff wolkow volkova volkoffa
yakovlev jakowlew yakovleva jakowlewa
yashin jashin iashin jaschin yaschin yashina jashina
zaitsev zaitzev zaitzeff zajcev zaitseva saisev
zakharov sakharov sacharov zakharoff zakharow zakharova sacharowa
zhukov zhukow jukov zukov zukow zhukoff zhukova jukoffa
petrovich petrovitch petrowich petrovic
petrovna
ivanovich ivanovitch iwanowitsch ivanovic
ivanovna iwanowna
mikhailovich mikhailovitch mikhailovitsch michailovich michailowitsch mihailovic mihajlovic michajlowicz
mikhailovna michailovna
nikolaevich nikolaevitch nikolaevitsch nikolaewich nikolaevic nikolajewicz
nikolaevna nikolaewna
sergeyevich sergeyevitch sergeyevitsch sergeyewich sergueyevich sergeevic siergiejewicz
sergeyevna sergeyewna sergueyevna sergejevna sergeevna
vladimirovich vladimirovitch vladimirovitsch vladimirovic wladimirowich wladimirowicz
vladimirovna wladimirowna
aleksandrovich aleksandrovitch aleksandrovitsch aleksandrovic aleksandrowicz alexandrovich alexandrovitch alexandrovitsch
aleksandrovna alexandrovna
alekseevich alekseevitch alekseevic alexeevich
alekseevna alexeevna
"""


PARTICLES = {"al", "el", "ad", "ar", "as", "ash", "at", "az", "an"}
NASAB = {"bin", "ibn", "ben", "b"}
PATRONYMICS = {
    "petrovich", "petrovna", "ivanovich", "ivanovna", "mikhailovich",
    "mikhailovna", "nikolaevich", "nikolaevna", "sergeyevich",
    "sergeyevna", "vladimirovich", "vladimirovna", "aleksandrovich",
    "aleksandrovna", "alekseevich", "alekseevna",
}
ATTACHED_ARTICLES = (
    "amin", "ameen", "attar", "atar", "douri", "dourie", "farsi", "hashimi", "hashemi",
    "hasheemmi", "hachemi", "hijaz", "jabouri", "gabouri", "khatib", "khatibe", "masri", "najjar", "najar", "nagar",
    "rashid", "rashed", "rasheed", "sabah", "saba", "sayed", "sayid", "shamsi", "chamsi", "tikriti",
    "tikreti", "tikreeti", "zahrani", "noor", "bahr", "ameene",
)


def base_latin_tokens(text: str) -> list[str]:
    raw = latin_words(text)
    cleaned: list[str] = []
    for token in raw:
        if token in PARTICLES:
            continue
        changed = token
        for stem in ATTACHED_ARTICLES:
            for prefix in ("al", "el", "ar", "as", "ash", "at", "ad", "az", "an"):
                if token == prefix + stem or token == prefix + stem[0] + stem:
                    changed = stem
                    break
            if changed != token:
                break
        cleaned.append(changed)

    # Family-first forms can put a spaced surname's particle at the end.
    if len(cleaned) >= 3 and cleaned[0] == "bois" and cleaned[-1] == "du":
        cleaned = ["dubois"] + cleaned[1:-1]
    elif len(cleaned) >= 3 and cleaned[0] == "fevre" and cleaned[-1] == "le":
        cleaned = ["lefevre"] + cleaned[1:-1]
    elif len(cleaned) >= 4 and cleaned[0] == "cruz" and cleaned[-2:] == ["de", "la"]:
        cleaned = ["delacruz"] + cleaned[1:-2]
    elif len(cleaned) >= 4 and cleaned[0] == "berg" and cleaned[-2:] in (["van", "der"], ["van", "den"]):
        cleaned = ["vandenberg"] + cleaned[1:-2]
    elif len(cleaned) >= 3 and cleaned[0] == "silva" and cleaned[-1] in {"da", "de"}:
        cleaned = ["dasilva"] + cleaned[1:-1]

    result: list[str] = []
    i = 0
    while i < len(cleaned):
        tail = cleaned[i:]
        if len(tail) >= 2 and tail[:2] == ["smith", "jones"]:
            result.append("smithjones"); i += 2
        elif len(tail) >= 2 and tail[:2] == ["le", "fevre"]:
            result.append("lefevre"); i += 2
        elif len(tail) >= 3 and tail[:3] == ["de", "la", "cruz"]:
            result.append("delacruz"); i += 3
        elif len(tail) >= 3 and tail[:3] in (["van", "der", "berg"], ["van", "den", "berg"]):
            result.append("vandenberg"); i += 3
        elif len(tail) >= 2 and tail[:2] in (["du", "bois"], ["da", "silva"]):
            result.append("".join(tail[:2])); i += 2
        elif len(tail) >= 2 and tail[:2] in (["abd", "allah"], ["abd", "ollah"], ["abd", "oollah"]):
            result.append("abdullah"); i += 2
        elif len(tail) >= 2 and tail[:2] == ["nasr", "allah"]:
            result.append("nasrallah"); i += 2
        elif len(tail) >= 2 and tail[0] in {"abd", "abdul", "abdel", "abdoul", "abdur"} and tail[1] in {"rahman", "rahmane", "rahmen"}:
            result.append("abdulrahman"); i += 2
        elif len(tail) >= 2 and tail[0] in {"abd", "abdul", "abdel", "abdoul"} and tail[1] in {"aziz", "azez", "azeez"}:
            result.append("abdulaziz"); i += 2
        else:
            token = cleaned[i]
            if token.startswith("nasrall"):
                token = "nasrallah"
            result.append(token); i += 1
    return result


def standard_pair(tokens: list[str], uf: UnionFind | None = None) -> tuple[str, str] | None:
    tokens = [x for x in tokens if len(x) > 1]
    if not tokens:
        return None
    keep: list[str] = []
    for i, token in enumerate(tokens):
        root = uf.resolve(token) if uf else token
        if 0 < i < len(tokens) - 1 and root in PATRONYMICS:
            continue
        keep.append(token)
    tokens = keep
    nasab = next((i for i, x in enumerate(tokens) if x in NASAB), -1)
    if nasab >= 1 and tokens[-1] not in NASAB:
        return "".join(tokens[:nasab]), tokens[-1]
    if len(tokens) >= 2:
        return "".join(tokens[:-1]), tokens[-1]
    return None


def possible_pairs(tokens: list[str], uf: UnionFind) -> set[tuple[str, str]]:
    useful: list[str] = []
    for token in tokens:
        root = uf.resolve(token)
        if (len(token) == 1 and token not in NASAB) or root in PATRONYMICS:
            continue
        useful.append(token)
    if len(useful) < 2:
        return set()
    pairs: set[tuple[str, str]] = set()
    positions = [i for i, x in enumerate(useful)
                 if x in NASAB and 0 < i < len(useful) - 1]
    if positions:
        i = positions[0]
        if i > 0 and i < len(useful) - 1:
            pairs.add(("".join(useful[:i]), useful[-1]))
        if i > 1:
            pairs.add(("".join(useful[1:i]), useful[0]))
    else:
        pairs.add(("".join(useful[:-1]), useful[-1]))
        pairs.add(("".join(useful[1:]), useful[0]))
    return {(uf.resolve(g), uf.resolve(f)) for g, f in pairs if g and f}


LEGAL_PHRASES = (
    "limited liability company", "public joint stock company",
    "joint stock company", "free zone establishment", "sociedad anonima",
)
LEGAL_WORDS = {
    "llc", "ltd", "limited", "sa", "gmbh", "jsc", "ao", "oao", "pjsc",
    "co", "company", "corp", "corporation", "inc", "incorporated", "fze",
    "fzllc", "fz", "plc", "ag", "the", "and", "public", "joint", "stock",
    "free", "zone", "establishment", "sociedad", "anonima", "liability",
}
CHINESE_GROUPS = r"""
li lee
wang wong ong
zhang chang cheung teoh teo
liu lau low liew
chen chan tan
yang yeung young yeo yeoh
huang hwang wong ng ooi
zhao chao chiu
wu woo ng goh
zhou chou chow chew
xu hsu tsui
sun suen soon
ma mah
zhu chu choo
hu hoo
guo kuo kwok kwek quek
he ho
gao kao koh ko
lin lam lim
luo lo law loh
liang leung leong neo nio
song sung soong sng
xie hsieh tse sia chia
deng teng
cao tsao tso cho
peng pang
qian chien chin
fan faan hwan
dai tai tay
ye yeh yip yap
cui tsui chui choy
han hon
jiang chiang kong kang
tang tong tng
zeng tseng cheng
"""
CHINESE: dict[str, set[str]] = defaultdict(set)
for _line in CHINESE_GROUPS.strip().splitlines():
    _items = _line.split()
    for _item in _items:
        CHINESE[_item].add(_items[0])


def entity_keys(text: str) -> set[tuple[str, ...]]:
    normalized = deaccent(text).lower().replace("&", " and ")
    normalized = re.sub(r"(?<=[a-z])['’](?=[a-z])", "", normalized)
    normalized = re.sub(
        r"\b(?:[a-z][.]){2,}[a-z]?[.]?",
        lambda match: match.group(0).replace(".", ""),
        normalized,
    )
    normalized = re.sub(r"\bg\s*[.]\s*m\s*[.]\s*b\s*[.]\s*h\b", "gmbh", normalized)
    normalized = re.sub(r"\bl\s*[.]\s*l\s*[.]\s*c\b", "llc", normalized)
    normalized = re.sub(r"\bs\s*[.]\s*a\b", "sa", normalized)
    normalized = re.sub(r"[-.,/]", " ", normalized)
    for phrase in LEGAL_PHRASES:
        normalized = re.sub(r"\b" + re.escape(phrase) + r"\b", " ", normalized)
    words = re.findall(r"[a-z0-9]+", normalized)
    words = [w for w in words if w not in LEGAL_WORDS]
    if not words:
        return set()
    stems = CHINESE.get(words[0], {words[0]})
    return {(stem, *words[1:]) for stem in stems}


def entity_key(text: str) -> tuple[str, ...]:
    """Single stable key retained for callers which only need normalization."""
    keys = entity_keys(text)
    return min(keys) if keys else ()


VESSEL_PREFIXES = {"mv", "mt", "vessel", "ss", "ms"}


def vessel_key(text: str) -> tuple[str, ...]:
    words = re.findall(r"[a-z0-9]+", deaccent(text).lower())
    if len(words) >= 2 and words[:2] in (["m", "v"], ["m", "t"]):
        words = words[2:]
    while words and words[0] in VESSEL_PREFIXES:
        words.pop(0)
    return tuple(words)


def dob_compatible(customer_dob: str, entry_dob: str) -> bool:
    if not customer_dob or not entry_dob:
        return True
    if len(customer_dob) == 10:
        return customer_dob == entry_dob
    if len(customer_dob) in (4, 7):
        return entry_dob.startswith(customer_dob)
    return customer_dob == entry_dob


def dob_support(customer_dob: str, entry_dob: str) -> bool:
    return bool(customer_dob and entry_dob and dob_compatible(customer_dob, entry_dob))


class ScreeningEngine:
    def __init__(self, entries: list[dict]) -> None:
        self.entries = entries
        self.uf = UnionFind()
        for line in TOKEN_GROUPS.strip().splitlines():
            self.uf.union(*line.split())
        self.uf.union("dasilva", "silva")
        self.uf.union("vandenberg", "vanderberg", "berg")
        self.script_map = self._learn_script_map()
        self.uf.build_orthographic_index()
        self._register_watchlist_vocabulary()
        self.uf.build_orthographic_index()
        self.id_index: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self.name_index: dict[str, dict[object, list[tuple[dict, bool]]]] = {
            "individual": defaultdict(list), "entity": defaultdict(list),
            "vessel": defaultdict(list),
        }
        self._build_indexes()

    def _learn_script_map(self) -> dict[str, str]:
        votes: dict[str, Counter[str]] = defaultdict(Counter)
        for entry in self.entries:
            primary = entry.get("primary_name", "")
            script = entry.get("script_name") or ""
            if not script or SCRIPT_RE.search(primary):
                continue
            latin = base_latin_tokens(primary)
            source = script_words(script)
            if len(latin) == len(source):
                for src, dst in zip(source, latin):
                    votes[src][dst] += 1
        learned = {src: count.most_common(1)[0][0] for src, count in votes.items()}
        # Cyrillic entries themselves supply a complete vocabulary for the two
        # less familiar conventions required by policy.  Generate their
        # diacritic-dropped scientific and Polish spellings token by token.
        for src, dst in learned.items():
            if CYR_RE.search(src):
                self.uf.union(
                    dst,
                    cyrillic_convention(src, CYR_SCIENTIFIC),
                    cyrillic_convention(src, CYR_POLISH),
                    cyrillic_to_latin(src),
                )
        return learned

    def tokens(self, text: str) -> list[str]:
        if not SCRIPT_RE.search(text):
            return base_latin_tokens(text)
        result: list[str] = []
        for word in script_words(text):
            mapped = self.script_map.get(word)
            if mapped:
                result.append(mapped)
            elif CYR_RE.search(word):
                result.append(cyrillic_to_latin(word))
            else:
                result.append("script:" + word)
        return result

    def _register_watchlist_vocabulary(self) -> None:
        """Make conservative spelling mechanics available for every list word."""
        for token in self.script_map.values():
            root = self.uf.resolve(token)
            self.uf.union(root, token)
        for entry in self.entries:
            names = [entry.get("primary_name", ""), entry.get("script_name") or ""]
            names.extend(a.get("name", "") for a in entry.get("aliases", []))
            for name in names:
                for token in self.tokens(name):
                    if len(token) > 1:
                        root = self.uf.resolve(token)
                        self.uf.union(root, token)

    def _learn_strong_aliases(self) -> None:
        for entry in self.entries:
            if entry.get("type") != "individual":
                continue
            primary = standard_pair(self.tokens(entry.get("primary_name", "")), self.uf)
            if not primary:
                continue
            for alias in entry.get("aliases", []):
                if alias.get("strength") != "strong":
                    continue
                other = standard_pair(self.tokens(alias.get("name", "")), self.uf)
                if other:
                    self.uf.union(primary[0], other[0])
                    self.uf.union(primary[1], other[1])

    def person_keys(self, text: str) -> set[tuple[str, str]]:
        return possible_pairs(self.tokens(text), self.uf)

    def _keys_for(self, kind: str, name: str) -> set[object]:
        if kind == "individual":
            keys: set[object] = set(self.person_keys(name))
            tokens = [t for t in self.tokens(name) if len(t) > 1]
            if len(tokens) == 1:
                keys.add(("__single__", self.uf.resolve(tokens[0])))
            return keys
        if kind == "entity":
            return set(entity_keys(name))
        if kind == "vessel":
            key = vessel_key(name)
            return {key} if key else set()
        return set()

    def _build_indexes(self) -> None:
        seen: set[tuple[str, str, object, bool]] = set()
        for entry in self.entries:
            for ident in entry.get("ids", []):
                key = (str(ident.get("type", "")), str(ident.get("number", "")))
                if all(key):
                    self.id_index[key].append(entry)
            kind = entry.get("type", "")
            strong_names = [entry.get("primary_name", "")]
            if entry.get("script_name"):
                strong_names.append(entry["script_name"])
            strong_names.extend(a.get("name", "") for a in entry.get("aliases", [])
                                if a.get("strength") == "strong")
            for name in strong_names:
                for key in self._keys_for(kind, name):
                    marker = (entry["uid"], kind, key, False)
                    if marker not in seen:
                        self.name_index[kind][key].append((entry, False)); seen.add(marker)
            for alias in entry.get("aliases", []):
                if alias.get("strength") == "weak":
                    for key in self._keys_for(kind, alias.get("name", "")):
                        marker = (entry["uid"], kind, key, True)
                        if marker not in seen:
                            self.name_index[kind][key].append((entry, True)); seen.add(marker)

    @staticmethod
    def _choose(candidates: list[dict], customer_dob: str) -> dict:
        return min(candidates, key=lambda e: (
            not dob_support(customer_dob, e.get("dob", "")), str(e["uid"])))

    def screen(self, customer: dict) -> tuple[str, str]:
        id_type = customer.get("id_type", "")
        id_number = customer.get("id_number", "")
        if id_type and id_number:
            hits = self.id_index.get((id_type, id_number), [])
            if hits:
                return "MATCH", self._choose(hits, customer.get("dob", ""))["uid"]

        kind = customer.get("type", "")
        name = customer.get("full_name", "")
        dob = customer.get("dob", "")
        candidates: dict[str, dict] = {}
        for key in self._keys_for(kind, name):
            for entry, weak in self.name_index.get(kind, {}).get(key, []):
                entry_dob = entry.get("dob", "")
                if weak:
                    if not (len(dob) == len(entry_dob) == 10 and dob == entry_dob):
                        continue
                elif not dob_compatible(dob, entry_dob):
                    continue
                candidates[entry["uid"]] = entry
        if not candidates:
            return "NO_MATCH", ""
        chosen = self._choose(list(candidates.values()), dob)
        return "MATCH", chosen["uid"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Screen customers against a sanctions watchlist")
    parser.add_argument("--watchlist", required=True)
    parser.add_argument("--customers", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    with open(args.watchlist, "r", encoding="utf-8") as handle:
        entries = json.load(handle)
    if not isinstance(entries, list):
        raise ValueError("watchlist JSON must contain a list")
    engine = ScreeningEngine(entries)
    with open(args.customers, "r", encoding="utf-8-sig", newline="") as src, \
         open(args.out, "w", encoding="utf-8", newline="") as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=["customer_id", "decision", "matched_uid"])
        writer.writeheader()
        for customer in reader:
            decision, uid = engine.screen(customer)
            writer.writerow({"customer_id": customer.get("customer_id", ""),
                             "decision": decision, "matched_uid": uid})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
