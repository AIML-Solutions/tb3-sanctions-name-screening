#!/usr/bin/env python3
"""Policy-driven sanctions name screening (Python 3.12, standard library only)."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict


CYRILLIC = str.maketrans({
    "а":"a", "б":"b", "в":"v", "г":"g", "д":"d", "е":"e",
    "ё":"yo", "ж":"zh", "з":"z", "и":"i", "й":"y", "к":"k",
    "л":"l", "м":"m", "н":"n", "о":"o", "п":"p", "р":"r",
    "с":"s", "т":"t", "у":"u", "ф":"f", "х":"kh", "ц":"ts",
    "ч":"ch", "ш":"sh", "щ":"shch", "ъ":"", "ы":"y", "ь":"",
    "э":"e", "ю":"yu", "я":"ya", "і":"i", "ї":"yi", "є":"ye",
    "ґ":"g",
})

ARABIC_CHARS = {
    "ا":"a", "أ":"a", "إ":"a", "آ":"a", "ٱ":"a", "ب":"b",
    "پ":"p", "ت":"t", "ث":"th", "ج":"j", "چ":"ch", "ح":"h",
    "خ":"kh", "د":"d", "ذ":"dh", "ر":"r", "ز":"z", "ژ":"zh",
    "س":"s", "ش":"sh", "ص":"s", "ض":"d", "ط":"t", "ظ":"z",
    "ع":"a", "غ":"gh", "ف":"f", "ق":"q", "ك":"k", "ک":"k",
    "گ":"g", "ل":"l", "م":"m", "ن":"n", "ه":"h", "ة":"a",
    "ۀ":"a", "و":"w", "ؤ":"w", "ي":"y", "ى":"a", "ی":"y",
    "ئ":"y", "ء":"a", "ﻻ":"la",
}


def _groups(spec: str) -> dict[str, str]:
    """Make a spelling -> canonical dictionary from newline separated groups."""
    out: dict[str, str] = {}
    for line in spec.splitlines():
        words = line.strip().split()
        if words:
            for word in words:
                out[word] = words[0]
    return out


# Lexical equivalences, not edit-distance guesses. The less familiar forms
# include French/German/Polish/Gulf, Turkish, and Malay/Indonesian forms.
WORD_EQ = _groups(r"""
william bill billy will
robert bob bobby rob
richard rick dick rich
edward eddie ed
theodore ted theo
frederick fred freddie
charles charlie chuck
joseph joe joey
thomas tom tommy
margaret maggie meg peggy
elizabeth liz beth betty
katherine catherine kathryn catharine kate katie kathy
patricia pat trish
dorothy dot dottie
victoria vicky vicki
alexander alex aleksandr aleksander

muhammad mohammad mohammed mohamed mohamad muhammed muhammat mehmet
ahmad ahmed achmad akhmad ahmet
mahmud mahmoud mahmut
mustafa moustafa mostafa mustapha
yusuf yousuf yousef yusef yussef yusof yussof joesoef
hussein husain hussain husayn hossein hosain huseyin hüseyin
hassan hasan
jamal gamal jemal cemal
qasim kasim kassem kasseem qassem kaseem kasım
khalid khaled khaleed halid
hamid hameed hamit
hamza hamzah
abdullah abdallah abdollah
ibrahim ebrahim
ismail ismael ismayl esmail
ishaq eshak
ilyas elias
idriss idris
osman uthman othman
omar umar
ali aly
amin ameen
amina ameenah aminah
fatima fatimah fateema fateemah
khadija khadijah khadeeja khadeejah
layla leila laila leyla
mariam maryam maryem meryem
rania raniah raniya
salma salmah
samira sameera samerah samera
zainab zaynab zeinab
zahra zehra
huda hudah hoda
hanan hanen
nabil nabel nabill
bilal billal
tariq tarek tarik tareq
faisal faysal feisal
kamal kamel
karim kareem
salim saleem salleem salem
saeed saeid said saed sayed
rami ramy
walid waleed waled
anwar anwarr
faris fares
farah ferah
abdulrahman abdurrahman abdelrahman abdrahman
abdulaziz abdelaziz abdulazez abdaziz

hosseini hossaini hosaini hussaini
ahmadi ahmedi
mohammadi mohamadi mohammady
mahmoudi mahmudi
mousavi moussavi musavi moosavi
rezai rezaei rezayi
salehi salehee sallehi sallihi
sadeghi sadighi sadeqi
rahimi raheemi
rahmani rahmany
karimi kareemi
kermani kirmani
tehrani tihrani
tabrizi tabrezi
esfahani isfahani
sharif sherif shareef sjarif
shirazi sheerazi
rostami rostammi
hashemi hashimi hashimmi
bagheri baghiri
jafari jaafari
nazari nazary
farahani farahany

nasrallah nasralla nasrulah
zahrani zahrany
jabouri jaburi jaboori
tikriti tikreti
douri duri
shamsi shamsy
rashid rasheed rached rashed
khatib khateeb khateb
najjar najar
attar atar
masri masry
khoury khouri
ghanem ghanim
nasser naser
kanaan kanan kanen
barakat barekat
haddad hadad
hamdan hamden
mansour mansur
sultan sulten
darwish darwesh
yassin yaseen yasin
awad awed
aziz azeez
hakim hakeem
mahdi mehdi
salman salmen

sergei sergey serguei sergej
yevgeny evgeny yevgeni evgeni eugene evgenii
alexei aleksei alexey aleksey
andrei andrey andrej
dmitri dmitry dmitriy
nikolai nikolay nikolaj
anatoly anatoliy anatoli anatolij
vitaly vitali vitaliy
valery valeri valeriy
vasily vasili vasiliy
yuri yuriy yurii jurij
grigory grigori grigoriy
gennady gennadi gennadiy
arkady arkadi arkadiy
stanislav stanislaw
vyacheslav viacheslav
ekaterina yekaterina katerina
natalia natalya nataliya
anastasia anastasiya
victoria viktoria viktoriya
maria mariya
daria darya dariya
julia yulia yuliya
tatiana tatyana
nadia nadezhda
fedor fyodor feodor
oksana oxana
artem artyom
mikhail mihail

mueller muller
weiss weis
schroeder schroder
schmidt schmid
bianci bianchi
lindqvist lindkvist lindquist
sorensen sorenson
olsen olson
lefevre lefeber
obrien o'brien
""")

# Further conventional forms kept separate here so they remain easy to audit.
WORD_EQ.update(_groups(r"""
james jim jimmy jamie
rebecca becca becky
christopher chris kit
samuel sam sammy
andrew andy drew
steven stephen steve
nicholas nicolas nick
barbara barb babs
francisco frank
susan sue susie suzy
alexander sasha xander
anthony tony
benjamin ben benny
henry hank harry
jennifer jen jenny
michael mike mikey
matthew matt
john jon johnny jack
jose pepe paco
patricia patty
elizabeth elisabeth
fernandez fernandes
ferreira ferreyra
meyer mayer
larsen larson
johansson johansen
nowak novak
mcdonald macdonald
kowalski kowalsky
den der
fischer fisher
petersen peterson pedersen
rodriguez rodrigues
schmidt schmitt
andersen anderson andersson

muhammad muhamad muhamed
hassan hassen hasen
hamid hamed
walid walled
morteza mortizah
jabouri gabouri
rami rammi
mustafa mustafah
ramin rammen
abdullah abdolah abdola abdollah
saeed saaid
masoud massoud
tariq tareeq
talal tallal
sami sammi
ibrahim ibrahem ibraheem
karim karem
amin amen ameen
nasser nassir
sabah saba
samir sammeer
haddad hadded
kaveh kavih
reza rezah
ghasemi ghassemmi ghassemi qasemi
adnan adnen
abdulrahman abdurrahmen abdulrahmen abdelrahmen
aisha aishah
ziad zied
bijan bigen bijen
zaidi zaydi
khadija khadeega
parisa paresa parisah
rezai rezaai
karimi kareemmi

artem artyom artiom
kiselyov kiseliov kiselev kiseliov
maria marya
semyon semion
alexander alexandr
yevgeny evgeniy

bao pao
boming poming
cui tsuei
jie chieh
narong najung
xiana hsiana
salehi salihi
layla laylah
rahman rahmen
abdullah abdulla
taha tahah
khadija khadejah
yusuf yusoof
hussein hosein
ebrahimi ebraheemi ebraihimi ebrahemmi ebraheemmi
parviz parvez
victoria tori
semyonova semionova
fedorov fyodorov
zaitsev zaytsev
maxim maksim
hamid hammeed hammed
saleh sallih salleh
mahsa mahsah
zahra zahrah
aisha aischa
fatima fateemmah fateemmah fatimih
hashemi hashimy hachemi haschimi haschimmi
marwan marouane
darwish darouishe
amir amer
kaveh cavih cavihe
layla lailla lailah laillah leilla leillah
hussein hossain housein
morteza mortezah mortiza
mariam maryame
javad javed javade
qasim qassim
abdullah abdoolla
abdul abdool abdoel
faisal faissal
majid maged madscheed
jabouri jaboury dschabouri
arash arasch

mikhail michail
nadezhda nadejda
stanislav stanislaff
vyacheslav wjacheslaw vyatcheslaff
viktor wiktor
vasily wasily
yuri yury
ruslan rouslan
timur timour
fedor fiodor
shishkin chichkin
shishkina chichkina
kiselyov kiselyova kiseliov kiseliova kiselev kiseleva kiselioff kiselioffa
kuznetsov kuznetsova kuznezov kuznezova kouznetsov kouznetsova
semyon semion semen
semyonov semionov semenov semionow
semyonova semionova semenova
tariq tareegh
qasim ghasim gassim
yassin yacine
marwan marwane
hisham hicham hichame
majid majeed
nabil nabeel
parisa parissa paressa pareesah
nasrin nasrene
zaidi zaidy
mohammadi mohamady
mahmoudi mahmoudy mahmoude
rezai rezaey
ramin rammeen
najjar nagar
hamid hammeed hammed hammid
hussein husein
amin amine
fatima fatemeh
fatima fatemmeh
fatima fatimmih
abdullah abdulah
kamal kamaal
douri doury
marwan marouen
samir samer sammer
huda houdah
ebrahimi ebrahimmie
elizaveta yelizaveta ielizaveta jelizaveta
anastasia anastasja anastasya
zhanna janna schanna shanna
maria marja
daria darja
yulia yulya

# Turkish renderings of Arabic names
omar omer
aisha ayse
amina emine
amir emir
anwar enver
fatima fatma
hamid hamit
kamal kemal
karim kerim
khalid halit
khadija hatice
mahmud mahmut
majid macit mecit
marwan mervan
nabil nebil
nasser nasir
rashid resit
saeed sait
salim selim
salman selman
walid velid
zainab zeynep
zahra zehra

# Indonesian/Malay, including the older Van Ophuijsen spellings
ahmad achmat
aisha aisyah
amina aminah
faisal faizal
jamal djamal
khadija chadidjah
khalid chalid
mahmud machmud
muhammad moehammad
mustafa moestafa
osman oesman usman
omar oemar
rahman rachman
rashid rasyid
sharif syarif
yusuf jusuf
abdullah abdoellah

# Diacritic-free scientific transliteration of Russian given names
alexei aleksej
evgeny evgenij
sergei sergej
natalia natalja
maria marija
julia julija
anastasia anastasija
victoria viktorija
tatiana tatjana
nadezhda nadezda
"""))
# Sayed/Sayyid is not Saeed, despite their superficially close spelling.
WORD_EQ.update({"sayed": "sayyid", "sayid": "sayyid", "seyed": "sayyid"})
WORD_EQ.update({"den": "der", "der": "der", "vanderberg": "vanderberg"})
WORD_EQ.update({"azez": "aziz", "salih": "saleh", "nasrala": "nasrallah"})
WORD_EQ.update({"mahmoude": "mahmud", "abduazize": "abdulaziz", "dasilva": "silva"})
WORD_EQ["paco"] = "francisco"
# In Arabic names ben is a structural nasab marker; Western Ben is handled in
# western_signatures so the two uses do not interfere.
WORD_EQ["ben"] = "ben"


CHINESE_SURNAME = _groups(r"""
zhang chang cheung chong teo
wang wong ong
li lee
zhou chou chow
chen chan tan
lin lim lam
wu woo ng goh
liu lau liew
huang hwang
zhao chao chiu
yang yeung yong
xu hsu tsui khoo
xiao hsiao siu
xie hsieh tse chia
cai tsai chua choy
zheng cheng tay teh
guo kuo kwok
jiang chiang kong keung
qian chien
sun soon suen
feng fung
ye yeh yip
liang leung nio
gao kao ko
deng teng dang
zeng tseng tsang
he ho
ma mah
cao tsao cho
lu loh loo
fan hoan faan
shen shum sum
zhu chu chue
peng phang
pan poon
yuan yuen
cui tsuei chui
luo lo
dai tai
song sung
hu hoo
du to
cao tso tsao
cai choi
chen chin
tang tong
""")

CHINESE_SYLLABLE = _groups(r"""
xiao hsiao
xiang hsiang
xian hsien
xin hsin
xing hsing
xu hsu
xue hsueh
zhi chih
zhong chung
zhang chang
zhao chao
qian chien
guo kuo
deng teng
cao tsao
zeng tseng
rui juei
jing ching
ji chi
zhou chou
""")
CHINESE_SYLLABLE.update(_groups(r"""
tian tien
xia hsia
xi hsi
jie chieh
cui tsuei
bao pao
gang kang
bo po
bin pin
de te
dong tung
gui kuei
juan chuan
jun chun
rong jung
hong hung
long lung
yong yung
yan yen
zhi chih
zhong chung
qi chi
qiang chiang
sheng sheng
jian chien
"""))
# Yong is a common given-name syllable, not a spelling of Yang.
CHINESE_SURNAME["yong"] = "yong"


def _script_map(spec: str) -> dict[str, str]:
    out = {}
    for line in spec.splitlines():
        parts = line.split()
        if len(parts) == 2:
            out[parts[0]] = parts[1]
    return out


# Arabic/Persian writing normally omits short vowels.  Whole-word mappings
# retain distinctions such as Hassan/Hussein and Ibrahim/Ebrahimi that a bare
# consonant skeleton would erase.  Unknown words still use the character map.
ARABIC_WORDS = _script_map(r"""
بن bin
عبد abd
الله allah
عمر omar
كريم karim
الكريم karim
عوض awad
أحمد ahmad
احمدی ahmadi
يوسف yusuf
الزهراني zahrani
بلال bilal
طلال talal
كمال kamal
الصباح sabah
ياسين yassin
فهد fahd
عزيز aziz
الرشيد rashid
سليم salim
مروان marwan
الدوري douri
مهدي mahdi
مهدی mehdi
سلمان salman
رحمانی rahmani
جمال jamal
سعيد saeed
سعید saeed
غانم ghanem
هدى huda
سمير samir
نبيل nabil
رامي rami
شاهين shaheen
مصطفى mustafa
صادقی sadeghi
حكيم hakim
ياسر yasser
حداد haddad
هشام hisham
أنور anwar
الرحمن rahman
العزيز aziz
سلطان sultan
درويش darwish
فارس faris
طه taha
الأمين amin
زياد ziad
السيد sayyid
محمود mahmud
بشار bashar
صالحی salehi
موسوی mousavi
بركات barakat
خوري khoury
سامي sami
وليد walid
الخطيب khatib
الجبوري jabouri
حمزة hamza
التكريتي tikriti
إسماعيل ismail
الهاشمي hashemi
نور nour
ناصر nasser
کرمانی kermani
المصري masri
طارق tariq
إبراهيم ibrahim
سلمى salma
نزار nizar
خالد khalid
حسن hassan
حسين hussein
حمدان hamdan
نیلوفر niloufar
محمد muhammad
كنعان kanaan
شیرین shirin
رضا reza
زمانی zamani
ماجد majid
قاسم qasim
الشمسي shamsi
مسعود masoud
عدنان adnan
کاوه kaveh
صالح saleh
نظری nazari
رانيا rania
تهرانی tehrani
خديجة khadija
اصفهانی esfahani
عباس abbas
علي ali
العطار attar
بكر bakr
بیژن bijan
رامین ramin
منصور mansour
شهرام shahram
یزدانی yazdani
سیاوش siavash
هاشمی hashemi
حميد hamid
سميرة samira
أمينة amina
رحیمی rahimi
نصر nasr
فراهانی farahani
تبریزی tabrizi
مريم mariam
مریم mariam
عائشة aisha
رضایی rezai
داریوش dariush
پرویز parviz
کامران kamran
حسین hussein
فاطمه fatima
کریمی karimi
زيدي zaidi
امیر amir
راشد rashid
حنان hanan
شیرازی shirazi
الفارسي farsi
مرادی moradi
حمید hamid
رستمی rostami
قاسمی ghasemi
محمودی mahmoudi
زهرا zahra
مهسا mahsa
ليلى layla
محمدی mohammadi
فيصل faisal
اکبری akbari
ابراهیمی ebrahimi
محسن mohsen
لیلا layla
آرش arash
حسینی hosseini
مجید majid
فرهاد farhad
النجار najjar
پریسا parisa
امید omid
زينب zainab
جعفری jafari
فاطمة fatima
مرتضی morteza
باقری bagheri
بهروز behrouz
دلال dalal
احسان ehsan
نسرین nasrin
گلناز golnaz
بابک babak
جواد javad
""")


PATRONYMIC_RE = re.compile(r"(?:ovich|evich|yevich|ich|ovna|evna|yevna|ichna)$")
NASAB = {"bin", "ibn", "ben", "b"}
AR_ARTICLES = {"al", "el", "ul", "as", "ash", "ar", "ad", "at", "an", "az"}


def has_arabic(s: str) -> bool:
    return any("\u0600" <= c <= "\u06ff" for c in s)


def has_cyrillic(s: str) -> bool:
    return any("\u0400" <= c <= "\u052f" for c in s)


def latinize(s: str) -> str:
    s = s.casefold().translate(CYRILLIC)
    if has_arabic(s):
        pieces = re.split(r"([\u0600-\u06ff]+)", s)
        s = "".join(ARABIC_WORDS.get(piece,
                    "".join(ARABIC_CHARS.get(c, c) for c in piece))
                    if has_arabic(piece) else piece for piece in pieces)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.translate(str.maketrans({"ł":"l", "ø":"o", "ð":"d", "þ":"th",
                                      "đ":"d", "ı":"i", "ß":"ss"}))


def raw_tokens(name: str) -> list[str]:
    s = latinize(name).replace("&", " and ")
    return re.findall(r"[a-z0-9]+", s)


def canonical_word(w: str) -> str:
    if w in WORD_EQ:
        return WORD_EQ[w]
    w = w.replace("dzh", "j").replace("dj", "j").replace("sj", "sh").replace("oe", "u")
    return WORD_EQ.get(w, w)


def strip_ar_article(w: str) -> str:
    if w in AR_ARTICLES:
        return ""
    for p in ("al", "el"):
        if w.startswith(p) and len(w) >= len(p) + 4:
            return w[len(p):]
    for p in ("assh", "ash", "arr", "ar", "ass", "as", "add", "ad",
              "att", "at", "ann", "an", "azz", "az"):
        if w.startswith(p) and len(w) >= len(p) + 4:
            rest = w[len(p):]
            if rest[0] in "rsdtnz":
                return rest
    return w


def rotations(words: list[str]) -> set[str]:
    if not words:
        return set()
    ans = set()
    for seq in (words, list(reversed(words))):
        for i in range(len(seq)):
            ans.add("".join(seq[i:] + seq[:i]))
    return ans


def russian_word(w: str) -> str:
    w = canonical_word(w)
    w = re.sub(r"^jou", "zhu", w)
    w = w.replace("ou", "u")
    w = w.replace("yo", "e")
    w = re.sub(r"^(?:jew|yev)", "yev", w)
    w = re.sub(r"^ye", "e", w)
    w = re.sub(r"^je", "e", w)
    w = re.sub(r"^ju", "yu", w)
    w = re.sub(r"^ja", "ya", w)
    w = re.sub(r"^vj", "vy", w)
    w = w.replace("w", "v")
    w = w.replace("fyo", "fe")
    w = w.replace("kh", "h")
    w = w.replace("ks", "x")
    w = re.sub(r"(?:schtsch|schtch|shtch|chch|shh|shch)", "Q", w)
    w = re.sub(r"(?:tsch|tch|cz)", "C", w)
    w = w.replace("sch", "S").replace("sz", "S")
    w = w.replace("zh", "Z").replace("ch", "C").replace("sh", "S")
    w = w.replace("tz", "ts").replace("ts", "c")
    w = w.replace("Z", "z").replace("C", "c").replace("S", "s").replace("Q", "sc")
    w = w.replace("aj", "ai").replace("ay", "ai")
    w = w.replace("j", "y")
    w = w.replace("iy", "i").replace("yy", "y")
    w = re.sub(r"ij$", "i", w)
    w = re.sub(r"j$", "y", w)
    w = re.sub(r"y$", "i", w)
    w = re.sub(r"([bcdfghjklmnpqrstvwxz])\1+", r"\1", w)
    return w


def russian_surname(w: str) -> str:
    w = russian_word(w)
    w = re.sub(r"ofa$", "ova", w)
    w = re.sub(r"efa$", "eva", w)
    w = re.sub(r"off$", "ov", w)
    w = re.sub(r"eff$", "ev", w)
    w = re.sub(r"of$", "ov", w)
    w = re.sub(r"ef$", "ev", w)
    if len(w) > 5 and re.search(r"(?:ov|ev|in)a$", w):
        w = w[:-1]
    w = re.sub(r"skaya$", "ski", w)
    w = re.sub(r"skaia$", "ski", w)
    return w


def arabic_word(w: str) -> str:
    w = canonical_word(w)
    protected = {
        "hassan":"HASN", "hussein":"HUSN", "ahmad":"AHMD", "hamid":"HAMD",
        "jamal":"JML", "kamal":"KML", "salim":"SLM", "sami":"SMY",
        "samir":"SAMIR", "samira":"SAMIRA", "amira":"AMIRA", "amir":"AMIR", "amin":"AMN",
        "mahmud":"MAHUD", "mahmoudi":"MAHUDI", "muhammad":"MUHMD",
        "ebrahiim":"EBRHM", "ebrahimi":"EBRHM", "ibrahimi":"EBRHM",
        "faris":"FARIS", "farsi":"FARSI", "salma":"SALMA",
        "salehi":"SALEHI", "saleh":"SALEH", "salih":"SALIH",
        "sayyid":"SAYD", "saeed":"SAED",
    }
    if w in protected:
        return protected[w].lower()
    w = w.replace("dsch", "j").replace("sch", "sh")
    w = (w.replace("kh", "X").replace("gh", "G").replace("sh", "S")
          .replace("ch", "S").replace("zh", "J").replace("th", "T")
          .replace("dh", "D").replace("ph", "f"))
    w = w.replace("q", "k").replace("c", "j")
    if w.endswith("t") and len(w) > 4:
        w = w[:-1] + "d"
    w = re.sub(r"[aeiou]", "", w).replace("y", "i")
    w = re.sub(r"([bcdfghjklmnpqrstvwxzSDTGXJ])\1+", r"\1", w)
    return w.lower()


def _base_individual_words(name: str) -> list[str]:
    toks = raw_tokens(name)
    if len(toks) >= 2 and toks[-1] == "o":
        # Comma-reversed O'Brien occasionally arrives as "Brien, Given O".
        toks = ["o" + toks[0]] + toks[1:-1]
    elif len(toks) >= 2 and toks[-1] in {"mac", "mc"}:
        toks = ["mac" + toks[0]] + toks[1:-1]
    merged: list[str] = []
    i = 0
    while i < len(toks):
        # Apostrophized/space-separated O'Brien and Mac Donald.
        if i + 1 < len(toks) and toks[i] == "o":
            merged.append("o" + toks[i + 1])
            i += 2
        elif i + 1 < len(toks) and toks[i] in {"mac", "mc"}:
            merged.append("mac" + toks[i + 1])
            i += 2
        elif len(toks[i]) > 1:
            merged.append(toks[i])
            i += 1
        else:
            i += 1                    # middle initial
    return [canonical_word(x) for x in merged]


def arabic_signatures(name: str) -> set[str]:
    # Keep "b." here: it is a nasab marker, whereas single-letter tokens in
    # other cultures are middle initials.
    toks = [canonical_word(x) for x in raw_tokens(name) if len(x) > 1 or x == "b"]
    merged: list[str] = []
    i = 0
    while i < len(toks):
        w = toks[i]
        if w in {"abd", "abdul", "abdel", "abdal", "abdur", "abdol", "abdoul", "abdool"} and i + 1 < len(toks):
            j = i + 1
            if toks[j] in AR_ARTICLES and j + 1 < len(toks):
                j += 1
            link = "r" if w == "abdur" else ""
            merged.append("abd" + link + toks[j])
            i = j + 1
            continue
        m = re.match(r"^abd(?:ul|oul|ool|ol|el|al|ur)(.+)$", w)
        if m:
            merged.append("abd" + m.group(1))
            i += 1
            continue
        merged.append(w)
        i += 1
    toks = merged

    def without_nasab(xs: list[str]) -> list[str]:
        out: list[str] = []
        skip = False
        for w in xs:
            if skip:
                skip = False
            elif w in NASAB:
                skip = True
            else:
                out.append(w)
        return out

    ans: set[str] = set()
    for variant in (toks, without_nasab(toks)):
        cleaned = []
        for w in variant:
            w = strip_ar_article(w)
            if w:
                cleaned.append(arabic_word(w))
        ans.update("A:" + sig for sig in rotations(cleaned) if sig)
    return ans


def russian_signatures(name: str) -> set[str]:
    toks = _base_individual_words(name)
    ans: set[str] = set()
    normalized = [russian_surname(w) for w in toks]
    no_pat_raw = [russian_surname(w) for w in toks if not PATRONYMIC_RE.search(w)]
    no_pat = [w for w in normalized if not re.search(r"(?:ovic|evic|yevic|ic|ovna|evna|yevna|ichna)$", w)]
    for ys in (normalized, no_pat_raw, no_pat):
        ans.update("R:" + sig for sig in rotations(ys) if sig)
    return ans


def chinese_token(w: str) -> str:
    w = canonical_word(w)
    if w in CHINESE_SYLLABLE:
        return CHINESE_SYLLABLE[w]
    for old in sorted(CHINESE_SYLLABLE, key=len, reverse=True):
        if old != CHINESE_SYLLABLE[old]:
            w = w.replace(old, CHINESE_SYLLABLE[old])
    return w


def chinese_signatures(name: str) -> set[str]:
    raw = [w for w in raw_tokens(name) if len(w) > 1]
    variants: list[list[str]] = []
    # The surname can occur at either end (and comma punctuation is not
    # required), so try each recognizable surname position. Other tokens use
    # the Wade-Giles/given-syllable table, resolving Chien=Jian versus the
    # surname Chien=Qian without conflating the two roles.
    for pos, word in enumerate(raw):
        cw = canonical_word(word)
        if cw in CHINESE_SURNAME:
            words = [chinese_token(w) for w in raw]
            words[pos] = CHINESE_SURNAME[cw]
            variants.append(words)
    if not variants:
        variants.append([chinese_token(w) for w in raw])
    return {"C:" + x for words in variants for x in rotations(words)}


def western_signatures(name: str) -> set[str]:
    toks = _base_individual_words(name)
    toks = ["benjamin" if w == "ben" else w for w in toks]
    variants = [toks, [w for w in toks if w != "da"]]
    return {"W:" + x for words in variants for x in rotations(words)}


def basic_alias_key(name: str) -> str:
    # Equality for weak aliases is deliberately narrower than Rule 2 name
    # equivalence: fold script/case/diacritics/punctuation, but not nicknames.
    return "".join(raw_tokens(name))


LEGAL_FORMS = [
    "limited liability company", "public joint stock company", "joint stock company",
    "closed joint stock company", "free zone company",
    "sociedad anonima", "societe anonyme", "limited liability co",
    "free zone establishment",
    "fz llc", "f z llc", "l l c", "g m b h", "s a", "p j s c", "o a o",
    "llc", "limited", "ltd", "gmbh", "jsc", "pjsc", "cjsc", "oao", "zao", "ao", "fze", "fzc", "fzco", "sa",
    "incorporated", "inc", "corporation", "corp", "company", "co", "plc",
    "ag", "nv", "bv", "spa", "pte", "sarl", "srl", "sas", "llp", "lp", "oy", "ab", "as", "kk",
]


def entity_key(name: str) -> str:
    toks = raw_tokens(name)
    if toks and toks[0] == "the":
        toks.pop(0)
    toks = [w for w in toks if w != "and"]
    s = " ".join(toks)
    changed = True
    while changed:
        changed = False
        for form in LEGAL_FORMS:
            if s == form:
                s, changed = "", True
                break
            if s.endswith(" " + form):
                s, changed = s[:-(len(form) + 1)].strip(), True
                break
    return "E:" + "".join(s.split())


def vessel_key(name: str) -> str:
    toks = raw_tokens(name)
    if toks and toks[0] == "vessel":
        toks.pop(0)
    elif toks[:2] in (["m", "v"], ["m", "t"], ["s", "s"]):
        toks = toks[2:]
    elif toks and toks[0] in {"mv", "mt", "ms", "ss", "tanker"}:
        toks.pop(0)
    return "V:" + "".join(toks)


def entry_culture(entry: dict) -> str:
    script = (entry.get("script_name") or "") + " " + entry.get("primary_name", "")
    if has_arabic(script):
        return "arabic"
    if has_cyrillic(script):
        return "russian"
    toks = raw_tokens(entry.get("primary_name", ""))
    if toks and (toks[-1] in CHINESE_SURNAME or toks[0] in CHINESE_SURNAME) and len(toks) == 2:
        return "chinese"
    return "western"


def individual_signatures(name: str, culture: str) -> set[str]:
    if culture == "arabic":
        return arabic_signatures(name)
    if culture == "russian":
        return russian_signatures(name)
    if culture == "chinese":
        return chinese_signatures(name)
    return western_signatures(name)


def dob_compatible(customer_dob: str, entry_dob: str) -> bool:
    return not customer_dob or not entry_dob or entry_dob.startswith(customer_dob)


class Engine:
    def __init__(self, entries: list[dict]):
        self.entries = entries
        self.id_index: dict[tuple[str, str], list[int]] = defaultdict(list)
        self.name_index: dict[str, set[int]] = defaultdict(set)
        self.weak_index: dict[str, set[int]] = defaultdict(set)
        self.cultures: set[str] = set()
        for i, entry in enumerate(entries):
            for ident in entry.get("ids", []):
                self.id_index[(ident.get("type", ""), ident.get("number", ""))].append(i)
            typ = entry.get("type", "")
            names = [entry.get("primary_name", "")]
            names += [a.get("name", "") for a in entry.get("aliases", []) if a.get("strength") == "strong"]
            if typ == "individual":
                culture = entry_culture(entry)
                entry["_culture"] = culture
                self.cultures.add(culture)
                if entry.get("script_name"):
                    names.append(entry["script_name"])
                for name in names:
                    for sig in individual_signatures(name, culture):
                        self.name_index[sig].add(i)
                for alias in entry.get("aliases", []):
                    if alias.get("strength") == "weak":
                        self.weak_index[basic_alias_key(alias.get("name", ""))].add(i)
            elif typ == "entity":
                for name in names:
                    self.name_index[entity_key(name)].add(i)
            elif typ == "vessel":
                for name in names:
                    self.name_index[vessel_key(name)].add(i)

    def screen(self, customer: dict) -> tuple[str, str]:
        id_key = (customer.get("id_type", ""), customer.get("id_number", ""))
        if id_key[0] and id_key[1] and id_key in self.id_index:
            dob = customer.get("dob", "")
            def id_rank(i: int) -> tuple[int, str]:
                edob = self.entries[i].get("dob", "")
                supported = bool(dob and edob and edob.startswith(dob))
                return (0 if supported else 1, self.entries[i]["uid"])
            winner = self.entries[min(self.id_index[id_key], key=id_rank)]
            return "MATCH", winner["uid"]
        typ, name, dob = customer.get("type", ""), customer.get("full_name", ""), customer.get("dob", "")
        candidates: set[int] = set()
        if typ == "individual":
            for culture in self.cultures:
                for sig in individual_signatures(name, culture):
                    candidates.update(self.name_index.get(sig, ()))
        elif typ == "entity":
            candidates.update(self.name_index.get(entity_key(name), ()))
        elif typ == "vessel":
            candidates.update(self.name_index.get(vessel_key(name), ()))
        candidates = {i for i in candidates if self.entries[i].get("type") == typ and
                      dob_compatible(dob, self.entries[i].get("dob", ""))}
        if len(dob) == 10:
            for i in self.weak_index.get(basic_alias_key(name), ()):
                entry = self.entries[i]
                if entry.get("type") == typ and entry.get("dob") == dob:
                    candidates.add(i)
        if not candidates:
            return "NO_MATCH", ""
        def rank(i: int) -> tuple[int, str]:
            edob = self.entries[i].get("dob", "")
            supported = bool(dob and edob and edob.startswith(dob))
            return (0 if supported else 1, self.entries[i]["uid"])
        winner = min(candidates, key=rank)
        return "MATCH", self.entries[winner]["uid"]


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Screen a customer CSV against a watchlist JSON")
    p.add_argument("--watchlist", required=True)
    p.add_argument("--customers", required=True)
    p.add_argument("--out", required=True)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    with open(args.watchlist, encoding="utf-8") as f:
        watchlist = json.load(f)
    engine = Engine(watchlist)
    with open(args.customers, newline="", encoding="utf-8-sig") as src, \
         open(args.out, "w", newline="", encoding="utf-8") as dst:
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
