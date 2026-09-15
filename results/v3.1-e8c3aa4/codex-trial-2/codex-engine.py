#!/usr/bin/env python3
"""Policy-based sanctions name screening (Python 3.12, standard library only)."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict
from itertools import product
from pathlib import Path


# Each group is an equivalence class, not an edit-distance hint. This keeps
# near names such as Hassan/Hussein and Hamid/Ahmad distinct.
TOKEN_GROUPS = r"""
william bill
katherine kate kathy
james jim jimmy jamie
joseph joe joey
theodore ted theo
dorothy dot dottie
robert bob rob robbie
charles charlie chuck
elizabeth elisabeth liz beth babs
edward ed eddie
frederick fred freddie
henry hank
john johnny
margaret maggie meg
michael mike
nicholas nicolas nick
patricia patty trish
peter pete
rebecca becca
richard rich ricky
samuel sam sammy
stephen steven steve
susan suzy susie
thomas tom tommy
victoria viktoria vicky tori
anthony tony
alexander xander sasha
andrew drew
christopher chris kit
francisco frank paco
jennifer jen
jose pepe

aleksandr alexandr alexander aleksander
aleksei aleksey alexei alexey aleksej
anastasia anastasiya anastasya
anatoly anatolii anatoliy anatolij
andrei andrey andreiy andrej
arkady arkadi arkadiy
artem artyom artiom
dmitri dmitry dmitriy dmitrij
ekaterina yekaterina
elena yelena
elizaveta yelizaveta
evgeny yevgeny evgeni evgeniy evgenij eugene
fedor fyodor feodor fiodor fjodor
kseniya ksenia ksenija
lyudmila liudmila ljudmila
maria mariya marya marija
maksim maxim
mikhail mihail
natalia nataliya natalya
nikolai nikolay nikolaiy nikolaj
oksana oxana
semen semyon semion
sergei sergey serguei sergeiy sergej
tatiana tatyana
vasily vasili vasiliy vasilij
viktoriya viktorya viktoria victoria
vyacheslav viacheslav vjaceslav
yulia yuliya yulya julia julija
yuri yuriy jurij

andreev andreyev
belousov
bondarenko
bykov
chaikovsky tchaikovsky tschaikowsky cajkovskij cajkovsky cajkovski
chernov tschernow
egorov yegorov jegorov
fedorov fyodorov fedoroff fjodorov
grishin
ivanov
kiselyov kiseliov kiselev kiseljov
kovalenko
kozlov
kravchenko
kuznetsov kusnezov
lebedev
makarov
morozov
nikolaev nikolayev
novikov
orlov
pavlov
petrov
popov
shcherbakov scherbakov shtcherbakov scerbakov
shevchenko sevcenko schewtschenko
shishkin siskin
smirnov
sokolov
stepanov
tkachenko
tsoi tsoy tsoiy coj
tsvetkov cvetkov
volkov
yakovlev jakovlev
yashin jasin
zaitsev zaytsev
zakharov sacharow
zhukov zukov jukov

abbas abas
adnan adnen
ahmad ahmed achmad ahmet
aisha aishah ayesha
akbari
ali
amina aminah ameenah
amir ameer
amin amen ameen
anwar
arash
babak
bagheri baghiri
bakr baker
barakat
bashar
behrouz behruz
bijan bijen bigen bizhan
bilal billal
dalal
dariush darioush
darwish darwesh darweesh
ebrahimi ebrahimi ebrahemi ebrahemmi
ehsan ehsen
esfahani isfahani
fahd fahad
faisal faysal fayssal
farahani
fares faris
farhad farhed
fatima fateemma fatemeh fatimmih
ghanem ghanim
ghasemi ghassimmi ghassemi
golnaz
haddad haded hadded
hakim hakem hakeem
hamdan hamden
hamid hamed hammed hammeed hameed
hamza hamzah
hanan hanen
hassan hasan hasen hassen
hashemi hashemmi hashimi hasheemmi
hisham
hussein husain hussain husayn hossein hosein hosain huseyin
hosseini hosaini hossaini hussaini
huda hudah
ibrahim ibrahem ibraheem
ismail ismayl ismael
jafari jaafari djafari
jamal jammal cemal djamal
javad javed jawad djavad
kamal kammal
kamran kamren
kanaan kanan
karim karem kareem
karimi karemmi kareemmi
kaveh kavih
kermani
khadija khadejah khadeejah khadijah
khalid khalleed khaleed
khoury khouri
layla lailah laylah leila leillah laila lailla
mahdi mehdi
mahmoud mahmud
mahmoudi mahmudi
mahsa
majid majed majeed
mansour mansur
mariam maryam
marwan marwen
masoud massoud masud
mohammadi mohamadi muhammadi
mohsen mohsin
moradi
morteza murtaza
mousavi moussavi musavi
mustafa mustafah mustapha
nabil nabel nabeel
nasir naseer
nasrin nasreen nasren
nasser naser
nazari
niloufar nilloufar niloofar
nizar
nour noor nur
omar umar
omid omed
parisa paresa pareesah parisah
parviz parvez parveez
qasim kasim kaseem kasseem
rami rammi
ramin rammen rammeen
rania raniah
rashed rasheed rashid
reza rezah
rezaei rezai rezaai
rostami rostammi
saeed said saeid saaid
sadeghi sadighi
saleh salih
salehi salihi sallihi sallehi
salim sallim salleem sallem
salma salmah
salman salmen
samera samerah samira
samir sammeer
sami sammi
shahin shaheen shahen
shahram
sharif sjarif sherif
shirazi sheerazi sherazi
shirin sheereen sheren
siavash siavach
sultan sulten
tabrizi tabrezi
taha tahah
talal tallal
tariq tareq tarek tareeq
tehrani
walid waled walled
yaseen yasen yassin
yasir yasser
yusuf yussof yussoof yusoof yusof joesoef
zahra
zaidi zaydi
zainab zaynab
zamani zammani
ziad zied

bianchi bianci
fernandez fernandes
ferreira ferreyra
johansson johansen johanson
kowalski kowalsky
larsen larson
lefevre
lindqvist lindquist
meyer meier mayer
mueller muller
novak nowak
olsen olson
rodriguez rodrigues
schmidt schmid
schroeder schroder
sorensen sorenson
weiss
"""


TOKEN_CANON: dict[str, str] = {}
for _line in TOKEN_GROUPS.splitlines():
    _words = _line.split()
    if _words:
        for _word in _words:
            TOKEN_CANON[_word] = _words[0]

# In the data's nickname vocabulary Babs is Barbara (not Elizabeth).
TOKEN_CANON["babs"] = "barbara"


# Direct word translations are semantic. Arabic/Persian short vowels are
# normally unwritten, so character transliteration cannot distinguish all names.
ARABIC_GROUPS = {
    "arash": "آرش", "ahmad": "أحمد احمد", "amina": "أمينة", "anwar": "أنور",
    "ibrahim": "إبراهيم", "ismail": "إسماعيل", "ebrahimi": "ابراهیمی",
    "ehsan": "احسان", "ahmadi": "احمدی", "esfahani": "اصفهانی",
    "amin": "الأمين", "tikriti": "التكريتي", "jabouri": "الجبوري",
    "khatib": "الخطيب", "douri": "الدوري", "rahman": "الرحمن",
    "rashid": "الرشيد", "zahrani": "الزهراني", "sayid": "السيد",
    "shamsi": "الشمسي", "sabah": "الصباح", "aziz": "العزيز عزيز",
    "atar": "العطار", "farsi": "الفارسي", "karim": "الكريم كريم کریم",
    "karimi": "کریمی",
    "allah": "الله", "masri": "المصري", "najjar": "النجار",
    "hashemi": "الهاشمي هاشمی", "omid": "امید", "amir": "امیر",
    "akbari": "اکبری", "babak": "بابک", "bagheri": "باقری",
    "barakat": "بركات", "bashar": "بشار", "bakr": "بكر", "bilal": "بلال",
    "bin": "بن", "behrouz": "بهروز", "bijan": "بیژن", "tabrizi": "تبریزی",
    "tehrani": "تهرانی", "jafari": "جعفری", "jamal": "جمال", "javad": "جواد",
    "haddad": "حداد", "hassan": "حسن", "hussein": "حسين حسین",
    "hosseini": "حسینی", "hakim": "حكيم", "hamdan": "حمدان",
    "hamza": "حمزة", "hamid": "حميد حمید", "hanan": "حنان",
    "khalid": "خالد", "khadija": "خديجة", "khoury": "خوري",
    "dariush": "داریوش", "darwish": "درويش", "dalal": "دلال",
    "rashed": "راشد", "rami": "رامي", "ramin": "رامین", "rania": "رانيا",
    "rahmani": "رحمانی", "rahimi": "رحیمی", "rostami": "رستمی",
    "reza": "رضا", "rezaei": "رضایی", "zamani": "زمانی", "zahra": "زهرا",
    "ziad": "زياد", "zaidi": "زيدي", "zainab": "زينب", "sami": "سامي",
    "saeed": "سعيد سعید", "sultan": "سلطان", "salman": "سلمان",
    "salma": "سلمى", "salim": "سليم", "samir": "سمير", "samira": "سميرة",
    "siavash": "سیاوش", "shahin": "شاهين", "shahram": "شهرام",
    "shirazi": "شیرازی", "shirin": "شیرین", "sadeghi": "صادقی",
    "saleh": "صالح", "salehi": "صالحی", "tariq": "طارق", "talal": "طلال",
    "taha": "طه", "aisha": "عائشة", "abbas": "عباس", "abd": "عبد",
    "adnan": "عدنان", "ali": "علي", "omar": "عمر", "awad": "عوض",
    "ghanem": "غانم", "fares": "فارس", "fatima": "فاطمة فاطمه",
    "farahani": "فراهانی", "farhad": "فرهاد", "fahd": "فهد",
    "faisal": "فيصل", "qasim": "قاسم", "ghasemi": "قاسمی", "kamal": "كمال",
    "kanaan": "كنعان", "layla": "ليلى لیلا", "majid": "ماجد مجید",
    "mohsen": "محسن", "muhammad": "محمد", "mohammadi": "محمدی",
    "mahmoud": "محمود", "mahmoudi": "محمودی", "moradi": "مرادی",
    "morteza": "مرتضی", "marwan": "مروان", "mariam": "مريم مریم",
    "masoud": "مسعود", "mustafa": "مصطفى", "mansour": "منصور",
    "mahdi": "مهدي مهدی", "mahsa": "مهسا", "mousavi": "موسوی",
    "nasser": "ناصر", "nabil": "نبيل", "nizar": "نزار", "nasrin": "نسرین",
    "nasr": "نصر", "nazari": "نظری", "nour": "نور", "niloufar": "نیلوفر",
    "parviz": "پرویز", "parisa": "پریسا", "kamran": "کامران", "kaveh": "کاوه",
    "kermani": "کرمانی", "golnaz": "گلناز", "yazdani": "یزدانی",
    "huda": "هدى", "hisham": "هشام", "walid": "وليد", "yasir": "ياسر",
    "yaseen": "ياسين", "yusuf": "يوسف",
}
for _canon, _forms in ARABIC_GROUPS.items():
    for _form in _forms.split():
        # Store both the written form and its Unicode decomposition. Arabic
        # hamza/madda marks may decompose during accent folding.
        TOKEN_CANON[_form] = _canon
        _folded_form = "".join(
            ch for ch in unicodedata.normalize("NFKD", _form.casefold())
            if not unicodedata.combining(ch)
        )
        TOKEN_CANON[_folded_form] = _canon

# Additional common renderings whose consonants/vowels differ by convention.
for _canon, _forms in {
    "aziz": "azez azeez",
    "ghasemi": "ghassemmi",
    "morteza": "mortizah mortaza",
    "muhammad": "muhammad mohammed mohamed mohamad muhamed muhamad muhammed",
    "nasser": "nassir nasir naseer",
    "najjar": "najar",
    "rahman": "rahmen",
    "sabah": "saba",
    "khatib": "khateb khateeb",
    "yasir": "yassir",
    "yusuf": "yussuf",
    "arkady": "arkadiy",
    "evgeny": "yevgeniy evgeniy",
    "grigory": "grigoriy",
    "valery": "valeriy valeri",
    "yuri": "yurii",
    "semyonov": "semionov semenov",
    "william": "billy",
    "bao": "pao",
    "gang": "kang",
    "amir": "amer",
    "anwar": "anware",
    "bashar": "bashare",
    "darwish": "darouishe",
    "dalal": "dallal dallalle",
    "ebrahimi": "ebraheemi ebraheemmi",
    "ehsan": "ehsaan",
    "fares": "faris faris",
    "faisal": "faissal",
    "fatima": "fateemah fateemmah fatimih",
    "golnaz": "golnaaz",
    "hisham": "hicham hichame",
    "ismail": "ismaille ismayle",
    "jafari": "djafari",
    "javad": "djavade javade",
    "kanaan": "kanaen",
    "kaveh": "cavih cavihe",
    "khadija": "khadeega khadiga khadijah",
    "khalid": "khallid khaled",
    "mahsa": "mahsah",
    "marwan": "marouane",
    "mohammadi": "muhammadi mohamady mohamadie",
    "nizar": "nizare",
    "omid": "omeed",
    "parisa": "parissa paressa",
    "qasim": "qasem qassim kassim",
    "ramin": "ramen",
    "rahimi": "rahemi rahimmi rahemmi",
    "rashid": "rashed rasheed rasheede",
    "sadeghi": "sadeghie",
    "saleh": "sallih",
    "shahram": "shahramme",
    "taha": "tahah",
    "talal": "tallalle",
    "tariq": "tareegh",
    "walid": "walide wallid",
    "yaseen": "yasseen yasene yasin",
    "zahrani": "zahranie",
    "abd": "abdul abdel abdol abdool",
    "abdallah": "abdolah abdollah abdulla abdoollah abdoolla",
    "awad": "awed aoued",
    "hashemi": "hashimmi hachemi haschimi",
    "jabouri": "gabouri djabouri dschabouri jabourie jaboury",
    "tikriti": "tikreti tikreeti",
    "pavel": "pawel",
    "mikhail": "michail",
    "ivan": "iwan",
    "gennady": "gennadiy",
    "nadezhda": "nadejda",
    "darya": "darja",
    "ruslan": "rouslan",
    "vyacheslav": "vyatcheslaff",
    "zhanna": "janna",
    "chaikovsky": "chaykovskiy",
    "kuznetsov": "kouznetsov kuznezov",
    "kravchenko": "krawtschenko kravczenko kravtchenko",
    "shishkin": "chichkin",
    "tkachenko": "tkatschenko tkatchenko",
    "tsvetkov": "tzvetkov",
    "zakharov": "zaharov zakharoff",
    "yashin": "jashin jaszin",
    "fischer": "fisher",
    "petersen": "peterson",
    "weiss": "weis",
    "benjamin": "benny",
    "elizabeth": "betty",
    "henry": "harry",
    "matthew": "matt",
    "amina": "aminah ameenah ameena",
    "abdkarim": "abdulkareem",
    "jingbo": "chingpo",
    "jun": "chun",
    "saeed": "saed",
}.items():
    TOKEN_CANON[_canon] = _canon
    for _form in _forms.split():
        TOKEN_CANON[_form] = _canon

# Further system-level romanizations used by French, German, Polish, Gulf,
# Turkish, Indonesian/Malay and scientific schemes.
for _canon, _forms in {
    # Arabic and Persian
    "abdallah": "abdula abdulah abdoellah",
    "abdaziz": "abduaziz abduazize",
    "adnan": "adnane",
    "ahmadi": "ahmady",
    "amina": "amena ameena",
    "anwar": "anouar anouare",
    "awad": "aouad aouade",
    "barakat": "baracat",
    "bijan": "bidjan bidjane bijaan",
    "dalal": "dallalle",
    "dariush": "dariuche",
    "douri": "doury",
    "ehsan": "ehsaan",
    "farahani": "farahany",
    "fatima": "fatimah fateemah fateemmah fatimih fatma",
    "ghasemi": "ghasimi ghasemy",
    "haddad": "hadad hadade",
    "hashemi": "hachimi hachimmi haschimi",
    "hisham": "hicham hichame",
    "hosseini": "hoseini",
    "jamal": "gammal djamal cemal",
    "kamal": "cammal cammalle kamaal kammaal",
    "kamran": "camran camrane camren",
    "kanaan": "kanen kanaen",
    "karimi": "karemi kareemi caremmi",
    "mahsa": "mahsah mahsahe",
    "majid": "maged mecit",
    "marwan": "marouen marouane",
    "masri": "masrie masry",
    "morteza": "mortiza mortezah",
    "muhammad": "mouhammad mouhammade moehammad muhammet mehmet",
    "najjar": "nagar naggar",
    "nasrallah": "nasrallaa nasrala",
    "nizar": "nizare",
    "omar": "omare omer",
    "omid": "omeed",
    "parisa": "paressa paressah",
    "qasim": "qasem qassim kassim kasim",
    "rahimi": "rahimmi rahemmi",
    "rezaei": "rezaey",
    "sadeghi": "sadeghie",
    "salim": "salem selim",
    "saleh": "sallih",
    "samir": "sammer",
    "sami": "sammie",
    "shirazi": "cherazi cheerazi",
    "siavash": "siavache",
    "tariq": "tareegh tarik",
    "tehrani": "teherani",
    "walid": "walide wallid",
    "yaseen": "yasene yasin",
    "yasir": "yaser yassir",
    "yazdani": "yazdany",
    "zahrani": "zahranie",
    "zahra": "zahrah",
    "zainab": "zeynep",
    "yusuf": "jusuf yusup joesoef joesoep",
    "sharif": "syarif sjarif",
    "farsi": "farsy",
    # Turkish and Indonesian/Malay forms not produced by the visible batch.
    "abd": "abdoel",
    "aisha": "ayse aischa",
    "hussein": "housein hosaine husein huseyin hoessein hoesain husin",
    "javad": "djaved djavede javade cevad",
    "karim": "kareme kareem kerim",
    "khadija": "khadeeja chadijah chadidjah",
    "khalid": "khallid khaled chalid halit",
    "mahmoud": "mahmut",
    "mariam": "maryame meryem",
    "mustafa": "moustafa moustafah moestafa",
    "rashid": "rasjid",
    "reza": "riza",
    "shahin": "sahin",
    "shamsi": "chamsi shamsie sjamsi syamsi",
    "shirin": "cheren cheereen sirin",
    # Cyrillic through German, Polish, French, or scientific conventions
    "aleksei": "alexeij",
    "anastasia": "anastasja",
    "arkady": "arkadij",
    "darya": "darja",
    "elizaveta": "elisaveta ielizaveta jelisaweta",
    "evgeny": "ievgeny jevgeny jewgeny evgenij",
    "gennady": "gennadij",
    "grigory": "grigorij",
    "nadezhda": "nadejda nadeshda",
    "natalia": "natalja",
    "nikolai": "nikolaij",
    "ruslan": "rouslan",
    "stanislav": "stanislaff stanislaw",
    "tatiana": "tatjana",
    "timur": "timour",
    "viktor": "wiktor",
    "viktoriya": "viktorija",
    "valery": "valerij",
    "vladimir": "wladimir",
    "svetlana": "swetlana",
    "elena": "jelena",
    "maria": "marja",
    "yuri": "juriy yurij",
    "vyacheslav": "wjacheslaw vyatcheslaff",
    "zhanna": "janna schanna shanna stschanna",
    "chaikovsky": "zchaikowsky cajkovskij cajkovski",
    "chernov": "czernow cernov",
    "grishin": "grischin grisin",
    "kozlov": "koslov",
    "kravchenko": "kravcenko",
    "kuznetsov": "kuznecov kuznetzov kouznetzoff kouznetsov",
    "morozov": "morosov",
    "shcherbakov": "chcherbakov tchtcherbakov",
    "semyonov": "semjonow semionow",
    "shevchenko": "schevtschenko shevczenko sevczenko",
    "shishkin": "sziszkin chichkin",
    "tkachenko": "tkacenko",
    "tsvetkov": "svetkov zwetkow tzvetkov",
    "tsoi": "coiy zoy coj",
    "yashin": "jashin jaszin",
    "zaitsev": "saisev zaicew zaitzev zajcev",
    "zakharov": "sakharov sacharow zaharov",
    "zhukov": "shukov shukow zukov",
    # Western nickname and surname conventions
    "andrew": "andy",
    "barbara": "barb",
    "daniel": "dan danny",
    "jennifer": "jenny",
    "john": "jon",
    "michael": "mick mikey",
    "patricia": "pat",
    "richard": "rick dick",
    "robert": "bobby",
    "susan": "sue",
    "petersen": "peterson pedersen",
    "schmidt": "schmitt",
    "lindqvist": "lindkvist",
    "peter": "pedro",
    "alexander": "alex",
    # Chinese romanization (surname forms plus recurring compound syllables)
    "cai": "choi",
    "cui": "chui",
    "dai": "tai tay",
    "du": "to tu",
    "fan": "faan",
    "gao": "ko kao",
    "jiang": "keung",
    "liang": "leung",
    "ma": "mah",
    "pan": "poon",
    "qian": "chin",
    "xu": "tsui",
    "zeng": "tsang",
    "zhao": "chiu",
    "zhi": "chi",
    "rong": "jung",
    "jingbo": "chingpo",
    "baoxia": "paohsia",
    "boyan": "poyan",
    "fengrong": "fengjung",
    "mingrong": "mingjung",
    "rongjun": "jungchun",
    "junjing": "kunching",
    "zhicheng": "chihcheng",
    "zhixin": "chihhsin",
    "jieping": "chiehping",
}.items():
    TOKEN_CANON[_canon] = _canon
    for _form in _forms.split():
        TOKEN_CANON[_form] = _canon


CYRILLIC_TABLE = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ё": "yo", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
})


CHINESE_SYLLABLES = {
    "chang": "zhang", "cheung": "zhang", "teo": "zhang",
    "wong": "wang", "ong": "wang", "lee": "li", "chou": "zhou",
    "chow": "zhou", "hsiao": "xiao", "siu": "xiao", "hsia": "xia",
    "hsieh": "xie", "tse": "xie", "chan": "chen", "tan": "chen",
    "lam": "lin", "lim": "lin", "ng": "wu", "goh": "wu",
    "hwang": "huang", "chu": "zhu", "teng": "deng", "tsao": "cao",
    "tsai": "cai", "kuo": "guo", "kwok": "guo", "ho": "he",
    "yeh": "ye", "yip": "ye", "tseng": "zeng", "lau": "liu",
    "suen": "sun", "fung": "feng", "hsu": "xu", "lo": "luo",
    "chien": "qian", "chiang": "jiang", "chao": "zhao", "ching": "jing",
    "chieh": "jie", "chih": "zhi", "hsiang": "xiang", "hsin": "xin",
    "hsueh": "xue", "tien": "tian", "juei": "rui", "tsuei": "cui",
    "najung": "narong", "poming": "boming",
    "dang": "deng", "tung": "dong", "te": "de", "po": "bo",
    "pin": "bin", "kang": "gang", "chung": "zhong", "poyan": "boyan",
    "keung": "jiang", "yuen": "yuan", "yeung": "yang", "hoo": "hu",
    "loo": "luo", "sung": "song", "sum": "shen", "chuan": "juan",
    "choi": "cai", "tso": "cao", "kuei": "gui",
}


ARABIC_ARTICLES = {"al", "el", "ad", "ar", "as", "ash", "at", "az", "an"}
NASAB = {"bin", "ibn", "ben", "b"}
ARABIC_FAMILIES = {
    "amin", "tikriti", "jabouri", "khatib", "douri", "rashid", "zahrani",
    "sayid", "shamsi", "sabah", "aziz", "atar", "farsi", "masri", "najjar",
    "hashemi", "rashed",
}
PATRONYMIC_RE = re.compile(
    r"(?:ovich|evich|yevich|ovitch|evitch|ovitsch|evitsch|owicz|ewicz|"
    r"owich|ewich|ovna|owna|evna|ewna|yevna|ichna|vich|vitch|vicz|wicz|vic|vna)$"
)

# Ted is conventionally short for either Theodore or Edward. Keep that
# ambiguity until the family name and DOB rules disambiguate it.
TOKEN_CANON["ted"] = "ted"
TOKEN_CANON["chien"] = "chien"
TOKEN_CANON["chi"] = "chi"
TOKEN_OPTIONS = {
    "ted": ("theodore", "edward"),
    "ben": ("ben", "benjamin"),
    # Apostrophes distinguishing aspiration are commonly dropped in Wade-Giles.
    "chien": ("qian", "jian"),
    "chi": ("zhi", "qi"),
}


def fold_text(value: str) -> str:
    """Case/diacritic fold while retaining letters from non-Latin scripts."""
    value = value.casefold().replace("ı", "i").replace("ø", "o").replace("ł", "l")
    value = value.replace("đ", "d").replace("ð", "d").replace("þ", "th")
    return "".join(ch for ch in unicodedata.normalize("NFKD", value) if not unicodedata.combining(ch))


def raw_words(name: str) -> list[str]:
    # Transliterate before generic accent removal: Cyrillic й and ё otherwise
    # decompose and lose information needed for conventional romanization.
    value = fold_text(name.casefold().translate(CYRILLIC_TABLE))
    return re.findall(r"[^\W\d_]+", value, flags=re.UNICODE)


def canonical_token(token: str) -> str:
    direct = TOKEN_CANON.get(token)
    if direct is not None:
        token = direct
    else:
        # French, German, Polish and Gulf transliterations often apply several
        # mechanical conventions at once. Explore only convention-based forms,
        # and accept one only when it reaches a known name token.
        queue = [token]
        seen = {token}
        for _ in range(4):
            next_queue: list[str] = []
            for form in queue:
                variants = {
                    re.sub(r"(.)\1+", r"\1", form),
                    form.replace("dsch", "j").replace("tsch", "ch"),
                    form.replace("sch", "sh"),
                    form.replace("cz", "ch").replace("sz", "sh"),
                    form.replace("ou", "u"),
                    form.replace("w", "v"),
                }
                if form.endswith("offa"):
                    variants.add(form[:-4] + "ov")
                if form.endswith("effa"):
                    variants.add(form[:-4] + "ev")
                if form.endswith("off"):
                    variants.add(form[:-3] + "ov")
                if form.endswith("eff"):
                    variants.add(form[:-3] + "ev")
                if form.endswith(("ova", "eva")) and len(form) > 5:
                    variants.add(form[:-1])
                if form.endswith("ina") and len(form) > 6:
                    variants.add(form[:-1])
                if form.startswith("tz"):
                    variants.add("ts" + form[2:])
                if form.endswith("ie"):
                    variants.add(form[:-2] + "i")
                if form.endswith("y"):
                    variants.add(form[:-1] + "i")
                if form.endswith("e"):
                    variants.add(form[:-1])
                if form.endswith("le"):
                    variants.add(form[:-2])
                for variant in variants - seen:
                    known = TOKEN_CANON.get(variant)
                    if known is not None:
                        token = known
                        queue = []
                        next_queue = []
                        break
                    seen.add(variant)
                    next_queue.append(variant)
                else:
                    continue
                break
            if not next_queue:
                break
            queue = next_queue
    scientific = {
        "cajkovskaja": "chaikovsky", "sevcenko": "shevchenko",
        "sevcenkova": "shevchenko", "zukova": "zhukov",
        "scerbakova": "shcherbakov", "cvetkova": "tsvetkov",
        "jakovleva": "yakovlev", "jasina": "yashin",
    }
    token = scientific.get(token, token)
    if token.endswith(("ova", "eva")) and len(token) > 5:
        masculine = token[:-1]
        token = TOKEN_CANON.get(masculine, masculine)
    elif token.endswith("ina") and len(token) > 6:
        masculine = token[:-1]
        token = TOKEN_CANON.get(masculine, masculine)
    elif token.endswith(("skaya", "skaja")):
        token = TOKEN_CANON.get(token[:-5] + "sky", token[:-5] + "sky")
    if token in TOKEN_OPTIONS:
        return token
    token = CHINESE_SYLLABLES.get(token, token)
    for old, new in (
        ("hsiang", "xiang"), ("hsiao", "xiao"), ("hsueh", "xue"),
        ("hsin", "xin"), ("hsia", "xia"), ("ching", "jing"),
        ("chih", "zhi"), ("chieh", "jie"), ("tien", "tian"),
    ):
        token = token.replace(old, new)
    # The same Wade-Giles substitutions can be embedded in a compound token.
    for old, new in (("pao", "bao"), ("poyan", "boyan"), ("ching", "jing"),
                     ("chung", "zhong"), ("tung", "dong")):
        token = token.replace(old, new)
    return TOKEN_CANON.get(token, token)


def split_attached_article(token: str) -> str:
    """Strip Arabic article, including common sun-letter assimilation."""
    direct = canonical_token(token)
    if direct in ARABIC_FAMILIES:
        return direct
    for prefix in ("al", "el"):
        if token.startswith(prefix) and len(token) > len(prefix) + 2:
            rest = canonical_token(token[len(prefix):])
            if rest in ARABIC_FAMILIES:
                return rest
    for prefix in ("ash", "ar", "as", "at", "az", "an", "ad"):
        if token.startswith(prefix) and len(token) > len(prefix) + 2:
            rest = token[len(prefix):]
            rest = canonical_token(rest)
            if rest in ARABIC_FAMILIES:
                return rest
    return direct


COMPOUND_CANON = {
    "abdulrahman": "abdrahman", "abdulrahmen": "abdrahman",
    "abdurrahman": "abdrahman", "abdurrahmen": "abdrahman", "abdurahman": "abdrahman",
    "abdelrahman": "abdrahman", "abdelrahmen": "abdrahman",
    "abdulaziz": "abdaziz", "abdulazez": "abdaziz", "abdelaziz": "abdaziz",
    "abdulkarim": "abdkarim", "abdulkarem": "abdkarim",
    "abdullah": "abdallah", "abdolla": "abdallah", "abdola": "abdallah",
    "nasrallah": "nasrallah", "nasralah": "nasrallah", "nasralla": "nasrallah",
    "nasrala": "nasrallah",
    "delacruz": "cruz", "macdonald": "macdonald", "mcdonald": "macdonald",
    "obrien": "obrien", "dubois": "bois", "lefevre": "lefevre",
    "vanderberg": "berg", "vandenberg": "berg", "smithjones": "smithjones",
    "dasilva": "silva",
}


def join_known_compounds(tokens: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    joins = {
        ("abd", "rahman"): "abdrahman", ("abd", "aziz"): "abdaziz",
        ("abd", "karim"): "abdkarim", ("abd", "allah"): "abdallah",
        ("nasr", "allah"): "nasrallah",
    }
    while i < len(tokens):
        if i + 1 < len(tokens) and (tokens[i], tokens[i + 1]) in joins:
            out.append(joins[(tokens[i], tokens[i + 1])])
            i += 2
        else:
            out.append(tokens[i])
            i += 1
    return out


def collapse_person_phrases(tokens: list[str]) -> list[str]:
    """Normalize multi-token surnames without deleting Chinese syllables."""
    replacements = {
        ("de", "la", "cruz"): ("cruz",),
        ("da", "silva"): ("silva",),
        ("du", "bois"): ("bois",),
        ("le", "fevre"): ("lefevre",),
        ("mac", "donald"): ("macdonald",),
        ("mc", "donald"): ("macdonald",),
        ("o", "brien"): ("obrien",),
        ("van", "der", "berg"): ("berg",),
        ("van", "den", "berg"): ("berg",),
        ("smith", "jones"): ("smithjones",),
    }
    result: list[str] = []
    i = 0
    keys = sorted(replacements, key=len, reverse=True)
    while i < len(tokens):
        for phrase in keys:
            if tuple(tokens[i:i + len(phrase)]) == phrase:
                result.extend(replacements[phrase])
                i += len(phrase)
                break
        else:
            result.append(tokens[i])
            i += 1
    # Family-first comma renderings can leave the particle at the end.
    if len(result) >= 2 and result[-2:] == ["de", "la"]:
        result = result[:-2]
    elif len(result) >= 2 and result[-2:] in (["van", "der"], ["van", "den"]):
        result = result[:-2]
    elif result and result[-1] == "da":
        result = result[:-1]
    if len(result) >= 3 and result[-1] == "o" and result[0] == "brien":
        result = ["obrien", *result[1:-1]]
    if len(result) >= 3 and result[-1] == "le" and result[0] == "fevre":
        result = ["lefevre", *result[1:-1]]
    return result


def individual_tokens(name: str) -> list[str]:
    tokens = collapse_person_phrases(raw_words(name))
    result: list[str] = []
    i = 0
    while i < len(tokens):
        raw_tok = tokens[i]
        tok = split_attached_article(raw_tok)
        tok = COMPOUND_CANON.get(tok, tok)
        is_nasab = raw_tok in NASAB or (tok in NASAB and any(ord(ch) > 127 for ch in raw_tok))
        if is_nasab and i > 0 and i + 1 < len(tokens):
            i += 1
            if i < len(tokens):
                father = canonical_token(tokens[i])
                i += 1
                if father in {"abd", "abdul", "abdel"} and i < len(tokens):
                    i += 1
            continue
        if len(tok) == 1:
            i += 1
            continue
        if tok in {"al", "el"}:
            i += 1
            continue
        if tok in ARABIC_ARTICLES and i + 1 < len(tokens):
            # Standalone assimilated articles are only articles in front of a
            # compatible Arabic family name; e.g. An Ping remains Chinese.
            following = canonical_token(tokens[i + 1])
            if following in ARABIC_FAMILIES:
                i += 1
                continue
        if PATRONYMIC_RE.search(tok):
            i += 1
            continue
        result.append(tok)
        i += 1
    result = [COMPOUND_CANON.get(x, x) for x in result]
    return join_known_compounds(result)


def individual_signatures(name: str) -> frozenset[tuple[str, str]]:
    """Return possible unordered (given-name, family-name) component pairs."""
    toks = individual_tokens(name)
    if len(toks) < 2:
        return frozenset()
    signatures: set[tuple[str, str]] = set()
    alternatives = [TOKEN_OPTIONS.get(tok, (tok,)) for tok in toks]
    for realized in product(*alternatives):
        for split in range(1, len(realized)):
            left = "".join(realized[:split])
            right = "".join(realized[split:])
            if left and right:
                signatures.add(tuple(sorted((left, right))))
    return frozenset(signatures)


LEGAL_SINGLE = {
    "llc", "ltd", "limited", "gmbh", "jsc", "ao", "oao", "pao", "pjsc",
    "co", "company", "corp", "corporation", "inc", "incorporated", "fze",
    "fz", "fzllc", "sa", "ag", "plc", "llp", "lp", "bv", "nv", "pte", "pty",
    "bhd", "sdn", "sarl", "sas", "srl", "spa", "kk", "oy", "ab", "as",
    "kg", "kgaa",
}


def entity_key(name: str) -> str:
    words = raw_words(name)
    if words and words[0] == "the":
        words = words[1:]
    words = [w for w in words if w != "and"]
    # Period-separated abbreviations tokenize as individual letters.
    dotted_forms = {
        ("g", "m", "b", "h"): "gmbh",
        ("l", "l", "c"): "llc",
        ("p", "j", "s", "c"): "pjsc",
        ("j", "s", "c"): "jsc",
        ("o", "a", "o"): "oao",
        ("s", "a"): "sa",
        ("a", "s"): "as",
        ("a", "g"): "ag",
        ("n", "v"): "nv",
        ("b", "v"): "bv",
        ("s", "p", "a"): "spa",
        ("a", "o"): "ao",
        ("f", "z", "e"): "fze",
    }
    for letters, joined in sorted(dotted_forms.items(), key=lambda x: len(x[0]), reverse=True):
        if tuple(words[-len(letters):]) == letters:
            words[-len(letters):] = [joined]
            break
    phrases = [
        ("limited", "liability", "company"),
        ("public", "joint", "stock", "company"),
        ("joint", "stock", "company"),
        ("private", "limited", "company"),
        ("public", "limited", "company"),
        ("limited", "liability", "partnership"),
        ("sociedad", "anonima"), ("societe", "anonyme"),
        ("free", "zone", "establishment"), ("free", "zone", "company"),
    ]
    changed = True
    while changed and words:
        changed = False
        for phrase in phrases:
            if tuple(words[-len(phrase):]) == phrase:
                del words[-len(phrase):]
                changed = True
                break
        if words and words[-1] in LEGAL_SINGLE:
            words.pop()
            changed = True
    return "".join(words)


def vessel_key(name: str) -> str:
    words = raw_words(name)
    if len(words) >= 2 and words[0] == "m" and words[1] in {"v", "t", "s"}:
        words = words[2:]
    elif len(words) >= 2 and words[:2] in (["motor", "vessel"], ["motor", "tanker"]):
        words = words[2:]
    elif words and words[0] in {"mv", "mt", "ms", "ss", "vessel"}:
        words = words[1:]
    return "".join(words)


def simple_alias_key(name: str) -> str:
    return "".join(raw_words(name))


def dob_compatible(customer_dob: str, entry_dob: str) -> bool:
    if not customer_dob or not entry_dob:
        return True
    if len(customer_dob) == 10:
        return customer_dob == entry_dob
    return entry_dob.startswith(customer_dob)


def dob_support(customer_dob: str, entry_dob: str) -> bool:
    return bool(customer_dob and entry_dob and dob_compatible(customer_dob, entry_dob))


class ScreeningEngine:
    def __init__(self, entries: list[dict]):
        self.by_uid = {str(e["uid"]): e for e in entries}
        self.ids: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self.ordinary: dict[tuple[str, object], set[str]] = defaultdict(set)
        self.weak: dict[tuple[str, str], set[str]] = defaultdict(set)
        for entry in entries:
            uid = str(entry["uid"])
            typ = entry.get("type", "")
            for ident in entry.get("ids", []):
                self.ids[(str(ident.get("type", "")), str(ident.get("number", "")))].append(entry)
            names = [entry.get("primary_name", "")]
            if entry.get("script_name"):
                names.append(entry["script_name"])
            names.extend(a.get("name", "") for a in entry.get("aliases", []) if a.get("strength") == "strong")
            for name in names:
                if not name:
                    continue
                if typ == "individual":
                    for sig in individual_signatures(name):
                        self.ordinary[(typ, sig)].add(uid)
                elif typ == "entity":
                    self.ordinary[(typ, entity_key(name))].add(uid)
                elif typ == "vessel":
                    self.ordinary[(typ, vessel_key(name))].add(uid)
            for alias in entry.get("aliases", []):
                if alias.get("strength") == "weak" and alias.get("name"):
                    self.weak[(typ, simple_alias_key(alias["name"]))].add(uid)

    def screen(self, customer: dict[str, str]) -> tuple[str, str]:
        id_type = customer.get("id_type", "")
        id_number = customer.get("id_number", "")
        if id_type and id_number:
            hits = self.ids.get((id_type, id_number), [])
            if hits:
                chosen = min(
                    hits,
                    key=lambda e: (
                        not dob_support(customer.get("dob", ""), str(e.get("dob", ""))),
                        str(e["uid"]),
                    ),
                )
                return "MATCH", str(chosen["uid"])
        typ = customer.get("type", "")
        name = customer.get("full_name", "")
        customer_dob = customer.get("dob", "")
        uids: set[str] = set()
        if typ == "individual":
            for sig in individual_signatures(name):
                uids.update(self.ordinary.get((typ, sig), ()))
        elif typ == "entity":
            uids.update(self.ordinary.get((typ, entity_key(name)), ()))
        elif typ == "vessel":
            uids.update(self.ordinary.get((typ, vessel_key(name)), ()))
        candidates = [self.by_uid[uid] for uid in uids if dob_compatible(customer_dob, str(self.by_uid[uid].get("dob", "")))]
        if len(customer_dob) == 10:
            for uid in self.weak.get((typ, simple_alias_key(name)), ()):
                entry = self.by_uid[uid]
                if str(entry.get("dob", "")) == customer_dob:
                    candidates.append(entry)
        if not candidates:
            return "NO_MATCH", ""
        unique = {str(e["uid"]): e for e in candidates}
        chosen = min(unique.values(), key=lambda e: (not dob_support(customer_dob, str(e.get("dob", ""))), str(e["uid"])))
        return "MATCH", str(chosen["uid"])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Screen customer names against a sanctions watchlist")
    parser.add_argument("--watchlist", required=True, type=Path)
    parser.add_argument("--customers", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    with args.watchlist.open("r", encoding="utf-8") as handle:
        entries = json.load(handle)
    if not isinstance(entries, list):
        raise ValueError("watchlist JSON must contain a list")
    engine = ScreeningEngine(entries)
    with args.customers.open("r", encoding="utf-8-sig", newline="") as source, args.out.open("w", encoding="utf-8", newline="") as dest:
        reader = csv.DictReader(source)
        required = {"customer_id", "full_name", "dob", "nationality", "id_type", "id_number", "type"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("customer CSV is missing required columns")
        writer = csv.writer(dest, lineterminator="\n")
        writer.writerow(["customer_id", "decision", "matched_uid"])
        for customer in reader:
            decision, uid = engine.screen(customer)
            writer.writerow([customer["customer_id"], decision, uid])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"screen.py: {exc}", file=sys.stderr)
        raise SystemExit(2)
