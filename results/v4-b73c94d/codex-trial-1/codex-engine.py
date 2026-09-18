#!/usr/bin/env python3
"""Rule-based archive record linker (Python 3.12, standard library only)."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict


def _ascii(s: str) -> str:
    # NFKD covers Latin diacritics (including the hidden scientific forms).
    s = s.replace("ß", "ss").replace("Ø", "O").replace("ø", "o")
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


# Cyrillic is first transliterated consistently and is then passed through the
# same controlled romanisation vocabulary as Latin input.
CYR_MULTI = {
    "ё": "yo", "ж": "zh", "х": "kh", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "shch", "ю": "yu", "я": "ya",
}
CYR_SINGLE = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "ы": "y", "э": "e", "ь": "", "ъ": "",
}


def translit_cyrillic(s: str) -> str:
    out = []
    for c in s:
        lo = c.lower()
        x = CYR_MULTI.get(lo, CYR_SINGLE.get(lo, c))
        out.append(x.capitalize() if c.isupper() and x else x)
    return "".join(out)


# Arabic/Persian spelling is consonantal, so a blind character transliterator
# cannot recover vowels.  These are ordinary name lexemes, not register IDs or
# record-specific exceptions.  Character transliteration below is a fallback.
AR_WORDS = {
    # given names / nasab names
    "آرش":"arash", "أحمد":"ahmad", "احمد":"ahmad", "أمينة":"amina",
    "أنور":"anwar", "إبراهيم":"ibrahim", "اسماعيل":"ismail", "إسماعيل":"ismail",
    "احسان":"ehsan", "امید":"omid", "امير":"amir", "امیر":"amir",
    "بابک":"babak", "بشار":"bashar", "بكر":"bakr", "بلال":"bilal",
    "بهروز":"behrouz", "بیژن":"bijan", "جمال":"jamal", "جواد":"javad",
    "حسن":"hassan", "حسين":"hussein", "حسین":"hussein", "حمزة":"hamza",
    "حميد":"hamid", "حمید":"hamid", "حنان":"hanan", "خالد":"khalid",
    "خديجة":"khadija", "دلال":"dalal", "داریوش":"dariush", "راشد":"rashid",
    "رامي":"rami", "رامین":"ramin", "رانيا":"rania", "رضا":"reza",
    "زهرا":"zahra", "زياد":"ziad", "زينب":"zainab", "سامي":"sami",
    "سعد":"saad", "سعيد":"saeed", "سعید":"saeed", "سلطان":"sultan",
    "سلمى":"salma", "سليم":"salim", "سمير":"samir", "سميرة":"samira",
    "سیاوش":"siavash", "شاهين":"shaheen", "شهرام":"shahram", "شیرین":"shirin",
    "طارق":"tariq", "طلال":"talal", "طه":"taha", "عائشة":"aisha",
    "عباس":"abbas", "عبد":"abd", "عدنان":"adnan", "عزيز":"aziz",
    "علي":"ali", "عمر":"omar", "فاطمة":"fatima", "فاطمه":"fatima",
    "فرهاد":"farhad", "فهد":"fahd", "فيصل":"faisal", "قاسم":"qasim",
    "كريم":"karim", "كمال":"kamal", "ليلى":"layla", "لیلا":"layla",
    "ماجد":"majid", "مجید":"majid", "محسن":"mohsen", "محمد":"muhammad",
    "محمود":"mahmoud", "مرتضی":"morteza", "مروان":"marwan", "مريم":"maryam",
    "مریم":"maryam", "مسعود":"masoud", "مصطفى":"mustafa", "منصور":"mansour",
    "مهدي":"mehdi", "مهدی":"mehdi", "مهسا":"mahsa", "ناصر":"nasser",
    "نبيل":"nabil", "نزار":"nizar", "نسرین":"nasrin", "نور":"nour",
    "نیلوفر":"niloufar", "هدى":"huda", "هشام":"hisham", "وليد":"walid",
    "ياسر":"yasir", "ياسين":"yasin", "يوسف":"yusuf", "پرویز":"parviz",
    "پریسا":"parisa", "کامران":"kamran", "کاوه":"kaveh", "گلناز":"golnaz",
    # surnames
    "احمدی":"ahmadi", "ابراهیمی":"ebrahimi", "اصفهانی":"esfahani",
    "اکبری":"akbari", "باقری":"bagheri", "بركات":"barakat", "تبریزی":"tabrizi",
    "تهرانی":"tehrani", "جعفری":"jafari", "حداد":"haddad", "حسینی":"hosseini",
    "حكيم":"hakim", "حمدان":"hamdan", "خوري":"khoury", "درويش":"darwish",
    "رحمانی":"rahmani", "رحیمی":"rahimi", "رستمی":"rostami", "رضایی":"rezaei",
    "زمانی":"zamani", "زيدي":"zaidi", "سعدالله":"saadallah", "سلمان":"salman",
    "شیرازی":"shirazi", "صادقی":"sadeghi", "صالح":"saleh", "صالحی":"salehi",
    "عوض":"awad", "غانم":"ghanem", "فارس":"fares", "فراهانی":"farahani",
    "قاسمی":"qasemi", "كنعان":"kanaan", "محمدی":"mohammadi", "محمودی":"mahmoudi",
    "مرادی":"moradi", "موسوی":"mousavi", "نظری":"nazari", "هاشمی":"hashemi",
    "یزدانی":"yazdani", "کرمانی":"kermani", "کریمی":"karimi",
    # Arabic article surnames (article is removed later)
    "الأمين":"al amin", "التكريتي":"al tikriti", "الجبوري":"al jabouri",
    "الخطيب":"al khatib", "الدوري":"al douri", "الرشيد":"al rashid",
    "الزهراني":"al zahrani", "السيد":"al sayyid", "الشمسي":"al shamsi",
    "الصباح":"al sabah", "العطار":"al attar", "الفارسي":"al farsi",
    "المصري":"al masri", "النجار":"al najjar", "الهاشمي":"al hashimi",
    "العزيز":"al aziz", "الكريم":"al karim", "الرحمن":"al rahman",
    "الله":"allah", "بن":"bin",
}

AR_CHARS = {
    "ا":"a", "أ":"a", "إ":"i", "آ":"a", "ب":"b", "پ":"p", "ت":"t",
    "ث":"th", "ج":"j", "چ":"ch", "ح":"h", "خ":"kh", "د":"d", "ذ":"dh",
    "ر":"r", "ز":"z", "ژ":"zh", "س":"s", "ش":"sh", "ص":"s", "ض":"d",
    "ط":"t", "ظ":"z", "ع":"", "غ":"gh", "ف":"f", "ق":"q", "ك":"k",
    "ک":"k", "گ":"g", "ل":"l", "م":"m", "ن":"n", "ه":"h", "ة":"a",
    "و":"w", "ؤ":"w", "ي":"y", "ی":"y", "ى":"a", "ئ":"y", "ء":"",
}


def translit_arabic(s: str) -> str:
    words = []
    for raw in s.split():
        raw = "".join(c for c in raw if unicodedata.category(c) != "Mn")
        if raw in AR_WORDS:
            words.append(AR_WORDS[raw])
        else:
            words.append("".join(AR_CHARS.get(c, c) for c in raw))
    return " ".join(words)


def romanize(s: str) -> str:
    if re.search(r"[\u0400-\u04ff]", s):
        s = translit_cyrillic(s)
    if re.search(r"[\u0600-\u06ff]", s):
        s = translit_arabic(s)
    return _ascii(s).lower()


GROUPS = [
    # Arabic given names, including French/German/Gulf, Turkish and Malay forms
    "muhammad mohammed mohammad mohamed mohamad muhammed mehmed mehmet muchammad",
    "ahmad ahmed ahmet achmad akhmad",
    "jamal gamal cemal djemal djamel",
    "hassan hasan hassen hasen",
    "hussein hussein husain hussain husayn hossein huseyin",
    "ibrahim ibrahem ebrahim ibrahym",
    "ismail ismael esmail",
    "yusuf yussef yusef yousef youssef yusof yussof yussuf yousuf joesoef jusuf",
    "sharif sherif cherif sjarif syarif",
    "khalid khaled halid halit",
    "khadija khadeja khadejah khadijah hatice",
    "qasim kasim kassem kasseem qassem ghasem kasym",
    "karim kareem kerim",
    "majid majed",
    "hamid hameed hammed hamit",
    "saeed said saaed saeid saaid",
    "samira sameera samera",
    "sami sammy sammi",
    "salim saleem sallim selim",
    "nabil nabel",
    "adnan adnen",
    "faisal faysal feisal",
    "talal tallal",
    "tariq tareq tarik",
    "walid waleed walled",
    "ziad zied ziyad",
    "rashid rasheed rached",
    "nizar nezar",
    "aisha aysha aischa",
    "layla laila leila leyla",
    "fatima fatimah fatema fatemah",
    "huda houda hudah",
    "hamza hamzah",
    "bilal billal",
    "abdullah abdallah abdollah abdola",
    "abdulrahman abdelrahman abdulrahmen abdelrahmen abdurrahman abdurrahmen",
    "abdulaziz abdelaziz abdulazez abdelazez",
    "aziz azeez azez",
    "bakr baker bekr",
    "nour nur noor",
    "mariam maryam meryem",
    "mansour mansur",
    "nasser naser",
    "yasin yaseen",
    # Persian
    "farhad farhed",
    "shirin shereen sheerine sheren",
    "niloufar nilufar nilloufar",
    "bijan bizhan bigen",
    "masoud massoud masud",
    "mohsen mohsin",
    "behrouz behruz",
    "parviz perviz parvez",
    "parisa paresa",
    "mehdi mahdi",
    "siavash siyavash",
    "dariush daryush",
    "morteza murtaza",
    "javad jawad",
    # Arabic/Persian family names
    "jabouri jaburi jaboury aljabouri eljabouri",
    "tikriti tikreti altikriti eltikriti",
    "najjar najar alnajjar elnajjar",
    "zahrani zahrany alzahrani elzahrani",
    "shamsi shemsi alshamsi elshamsi",
    "sabah saba alsabah elsabah",
    "khatib khateeb khateb alkhatib elkhatib",
    "douri duri aldouri eldouri",
    "rashid alrashid elrashid",
    "masri elmasri almasri",
    "sayyid sayid alsayyid elsayyid",
    "amin ameen alamin elamin",
    "hashimi hashemi alhashimi elhashimi",
    "attar alattar elattar",
    "farsi alfarsi elfarsi",
    "darwish darwesh",
    "haddad hadded",
    "hamdan hamden",
    "awad awed",
    "fares faris",
    "hakim hakeem",
    "khoury khouri",
    "kanaan kanan",
    "salman salmen",
    "barakat baraket",
    "saadallah saadalla saadallaah",
    "salehi salihi sallehi sallihi",
    "sadeghi sadighi sadeqi",
    "ebrahimi ebrahimi ebraheemi ibrahimi",
    "hashemi hashimi hashimmi",
    "karimi kareemi kareemmi",
    "rostami rostammi",
    "zamani zammani",
    "rezaei rezaai rezai",
    "mousavi moussavi musavi",
    "shirazi sheerazi",
    "esfahani isfahani",
    "tehrani tihrani",
    "tabrizi tabrezi",
    "yazdani yezdani",
    "rahimi raheemi",
    "rahmani rahmany",
    "mahmoudi mahmudi",
    "mohammadi mohammadi",
    "hosseini husseini",
    "farahani farahany",
    "jafari jaafari",
    "bagheri baqeri",
    # Russian first names / international variants
    "alexander aleksander alexandr aleksandr aleksandr alexandre",
    "alexei alexey aleksei aleksey aleksej",
    "anatoly anatoliy anatoli",
    "andrei andrey andrej",
    "arkady arkadiy arkadij",
    "artem artyom artemy",
    "dmitri dmitry dmitriy dmitrij",
    "yevgeny evgeny yevgeni evgeni evgeniy evgenij eugene",
    "fedor fyodor feodor fjodor",
    "grigory grigori gregory grigoriy grigorij",
    "igor igorj",
    "ilya ilia",
    "konstantin constantin",
    "mikhail michael mihail",
    "nikolai nikolay nikolaj",
    "pavel paul",
    "sergei sergey sergej serguei",
    "stanislav stanislaw",
    "vasily vasiliy vassily vasili",
    "viktor victor",
    "vyacheslav viacheslav vjaceslav",
    "yuri yuriy yury jurij",
    "ekaterina yekaterina katerina catherine katherine kathryn kate kathy",
    "maria mariya marya",
    "nadezhda nadia nadya",
    "natalia natalya nataliya",
    "tatiana tatyana",
    # Russian surnames and scientific transliteration without diacritics
    "chaikovsky tchaikovsky chaykovsky cajkovskij chaikovskiy",
    "tsvetkov cvetkov",
    "chernov cernov",
    "shevchenko sevcenko",
    "shishkin siskin",
    "shcherbakov scerbakov shcherbakoff",
    "zhukov zukov jukov",
    "zaitsev zajcev zaytsev",
    "zakharov zaharov",
    "fedorov fyodorov fedoroff",
    "semyonov semenov semionov",
    "kiselev kiselyov kiseliov kiselov",
    "egorov yegorov",
    "yakovlev jakovlev",
    "tsoy tsoi tsoiy choi",
    "kuznetsov kuznetsov",
    # Western given names / nicknames
    "william bill billy will",
    "robert bob bobby rob",
    "richard rick dick rich",
    "james jim jimmy jamie",
    "john johnny jack",
    "joseph joe joey",
    "charles charlie chuck",
    "edward ed eddie ted",
    "frederick fred freddie",
    "andrew andy drew",
    "steven stephen steve",
    "samuel sam",
    "thomas tom tommy",
    "michael mike",
    "nicholas nick",
    "anthony tony",
    "francisco frank paco",
    "victoria vicky vicki",
    "elizabeth liz beth betty",
    "margaret maggie meg peggy",
    "jennifer jen jenny",
    "dorothy dot dotty",
    "barbara barb babs",
    "rebecca becky",
    "patricia patty tricia",
    "susan sue suzy",
    # Western surnames with conventional spelling variants
    "mueller muller",
    "weiss weisz",
    "sorensen soerensen",
    "lindqvist lindquist",
    "bianchi bianci",
    "fernandez fernandes",
    "johansson johanson johansen",
    "petersen pedersen peterson",
    "nowak novak",
    "schmidt schmitt",
    # Further controlled spellings seen across the supported conventions.
    # Later groups intentionally resolve ambiguous nicknames (Ted/Sammy) to
    # the convention used by this archive's Western-name vocabulary.
    "amina amena aminah ameenah",
    "mustafa mustafah",
    "abbas abas",
    "samir sameer sammeer",
    "marwan marwen",
    "kamal kammal",
    "taha tahah",
    "rania raniah",
    "shirin shereen sheerine sheereen sheren",
    "parviz perviz parvez parveez",
    "kaveh kavih",
    "kamran kamren",
    "ramin rammen rammeen",
    "haddad hadded haded",
    "hakim hakeem hakem",
    "shirazi sheerazi sherazi",
    "hosseini husseini hossaini hosaini",
    "alexander aleksander alexandr aleksandr alexandre xander sasha",
    "sergei sergey sergej serguei sergeiy",
    "semyon semion semen",
    "maksim maxim",
    "oksana oxana",
    "viktoria viktorya victoria",
    "samuel sam sammy",
    "theodore ted teddy",
    "christopher chris kit",
    "rebecca becky becca",
    "patricia patty tricia trish",
    "schmidt schmitt schmid",
    "olsen olson",
    "larsen larson",
    "kowalski kowalsky",
    "ferreira ferreyra",
    "macdonald mcdonald",
    "majid majeed magid",
    "tariq tareeq",
    "saeed saed",
    "fatima fateemah fateemma fatimih",
    "yasin yassin yasen",
    "shahin shaheen shahen",
    "sultan sulten",
    "jafari gafari",
    "ghasemi ghassemmi qasemi",
    "amin amen ameen elamen alamen",
    "rashid rasheed elrasheed alrasheed",
    "sabah saba elsaba alsaba",
    "attar atar alattar elattar",
    "saleh salih",
    "mohammadi mohamadi",
    "rahimi rahemi",
    "saadallah sadalah",
    "abdullah abdulla abdulah",
    "layla laylah",
    "ismail ismayl",
    "hamid hamed",
    "ghanem ghanim",
    "parisa parisah",
    "reza rezah",
    # Wade-Giles and related Chinese syllables, including given-name use.
    "jie chieh", "xia hsia", "xiao hsiao", "xin hsin", "xiang hsiang",
    "xue hsueh", "jing ching", "rui juei", "guo kuo", "tian tien",
    "dong tung", "cui tsuei", "pingxue pinghsueh", "boming poming",
    "narong najung",
    "elizabeth elisabeth", "nicholas nicolas",
    "salma salmah",
    "jamal jammal",
    "karimi karemi",
    "hussein hosein hosain",
    "darwish darweesh",
    "aisha aishah",
    "rami rammi",
    "salim salleem",
    "artem artyom artiom",
    "yusuf yusoof",
    "walid waled",
    "karim karem",
    "dongwen tungwen",
    "jun chun",
    "aleksandrovich alexandrovich",
    "sergeevich sergeyevich",
    "semyonov semionov semionova",
    "viktoria victoria tori",
    "der den",
    # French, German, Polish and Gulf spellings used by archive catalogues.
    "fatima fatimma",
    "hashemi hashemmi hasheemmi",
    "mahsa mahsah",
    "parisa parissa",
    "ehsan ehsaan",
    "fischer fisher",
    "yasir yassir",
    "anwar anware",
    "bashar bashare",
    "walid walide wallid",
    "golnaz golnaaz",
    "javad javed djavade",
    "meyer mayer meier",
    "ramin ramen",
    "kanaan kanaen",
    "siavash siavache",
    "shahram chahrame shahramme",
    "rahimi rahemmi",
    "zainab zaynab",
    "abdullah abdolah",
    "jamal gammal",
    "amir amer",
    "salim sallem sallem salleem",
    "kaveh cavih cavihe",
    "hussein hossain hosain hosein",
    "ismail ismaille ismayle",
    "guilan kueilan",
    "nizar nizare",
    "abdulaziz abduazeez",
    "marwan marouane",
    "bilal billal",
    "theodore theo",
    "khalid khaleed khalleed khallid",
    "dalal dallal dallalle",
    "talal tallalle",
    "khatib khateebe",
    "nabil nabeel",
    "sabah saba sabahe",
    "rashid rashed rasheede",
    "amin amine",
    "omar omare",
    "hamid hammid",
    "salman salmane",
    "lailla layla",
    "zahra zahrah",
    "omid omeed",
    "majid maged",
    "mohammadi mohamadie mohamady",
    "zaidi zaydi",
    "ghasem ghasem qasim kaseem",
    "morteza mortizah",
    # Attached and assimilated Arabic definite articles.
    "douri addouri eldouri aldouri",
    "sabah assabah elsabah alsabah",
    "zahrani azzahrani elzahrani alzahrani",
    "tikriti attikriti eltikriti altikriti",
    "sayyid sayed sayid assayyid elsayyid elsayid alsayyid alsayid",
    "rashid arrashid arrashed arrasheed elrashid alrashid",
    "jabouri adjabouri dschabouri eldschabouri aldschabouri",
    "shamsi ashshamsi elshamsi alshamsi",
    "najjar annajjar elnajjar alnajjar",
    "attar attar alattar elattar",
    "hashimi hashemi elhashemi elhasheemmi alhashimi",
    # Russian catalogue romanisations.
    "pavel pawel",
    "kuznetsov kouznetsov",
    "yakovlev iakovlev iakovleff",
    "nikolaev nikolaew nikolaeff",
    "tsvetkov tzvetkov tzvetkoff",
    "shevchenko shevczenko szewczenko",
    "popov popow",
    "ivan iwan",
    "ivanovich iwanowich",
    "ivanovna iwanowna",
    "mikhail michail",
    "semyonov semionow",
    "tkachenko tkatschenko tkaczenko",
    "petrovich petrovitch petrovitsch",
    "aleksandrovich aleksandrovicz",
    "kiselev kiselioff kiselioffa",
    "zakharov zakharoff",
    "tsoy coiy",
    "vyacheslav vjacheslav vyatcheslaff",
    "ksenia kseniya",
    "anastasia anastasiya anastasja",
    "nikolai nikolaiy",
    "andrei andreiy",
    "yulia yulya",
    "zhanna janna",
    "ruslan rouslan",
    "gennady gennadiy",
    "sokolov sokoloff",
    "novikov novikoff nowikow",
    "novikova nowikowa",
    "kozlov koslov koslova",
    "yashin jashin",
    "pavlov pawlov pawlow",
    "bykov bykow",
    "tsvetkova tzvetkoffa",
    "chaikovskaya cajkovskaja",
    # Cantonese/Wade-Giles syllables used inside given names.
    "huang hwang",
    "gui kuei kwei",
    "xian hsian", "xiana hsiana",
    "de te", "zhi chih", "gang kang", "bin pin",
    "zhong chung", "qi chi",
    "bao pao", "jingbo chingpo", "boyan poyan",
    "henry hank", "benjamin benny",
    "rodriguez rodrigues", "silva dasilva",
    "jafari djafari",
    "moradi moradie",
    "sadeghi sadeghie",
    "kuznetsov kouznetsov kouznetsova",
    "makarov makarow",
    "ebrahimi ebraheemmi",
    "weiss weis",
    "hakim hakime",
    "amina ameena",
    "abdul abdol",
    "khalid khalled",
    "kiselev kiselyov kiselyova kiselioff kiselioffa",
    "yasin yasene yasseen",
    "saleh sallih",
    "qasim qassim ghasem ghasemi ghassemmi ghassimmi",
    "yusuf yussoof",
    "faisal faissal",
    "nasser nassir",
    "kravchenko kravczenko",
    "semyonov semenov semenova",
    "tiancheng tiencheng",
    "chengzhi chengchih",
    "fatima fatemeh",
    "kravchenko kravtchenko",
    "lebedev lebedew",
    "ekaterina jekaterina",
    "popov popoff popow popowa",
    "darya darja",
    "amir ameer",
    "zaitsev saitsev",
    "parisa pareessa",
    "nazari nazary",
    "omid omed",
    "shirazi shirazie",
    "qasim ghasemi ghasimi ghassemmi ghassimmi",
    "saeed saeede",
    "fares farese",
    "mousavi mousavie",
    "stepanov stepanoff",
    "hussein husein",
    "samir sammer",
    "andersen anderson",
    "boxue pohsueh",
    "bo po",
    "fatima fateemmah",
    "hamid hammeed",
    "lingtian lingtien",
    "hu hoo",
    "layla lailah",
    "tikriti tikreeti",
    "smirnov smirnow smirnowa",
    "hashimi hashimy",
    "darwish darouishe",
    "bijan bijaan",
    "abdullah abdoollah",
    "rahimi rahimmi",
    "bykov bykow bykowa",
    "alekseevich alekseevicz",
    "abdulkarim abdulkarem",
    "zhukov joukoff",
    "valery valeriy",
    "henry harry",
    "sayyid assayid",
    "jabouri aljabourie jabourie",
    "jun chun", "rong jung",
    "dorothy dottie",
    "sergei sergeij",
    "qasim kasem kassim",
    "muhammad muhamed",
    "tikriti attikreeti",
    "yulia yuliya",
    "kozlov kozlow",
    "zainab zainaab",
    "petrovich petrovicz",
    "belousov belousow",
    "kravchenko kravtschenko",
    "valery walery",
    "khadija khadeeja",
    "kamal kammaal",
    "farahani farahanie",
    "lyudmila lyoudmila",
    "petrov petroff petroffa",
    "lindqvist lindkvist",
    "awad awaad",
    "nikolaevich nikolaevitsch",
    "sorensen sorenson",
    "orlov orlow orlowa",
    "sergeevna sergejevna",
    "stanislav stanislaff",
    "pavlov pavloff",
    "ibrahim ibraheem",
    "fatima fatimmih",
    "jafari dschafari",
    "samir samer",
    "saleh salleh",
    # Systematic German/Polish/French Cyrillic catalogue forms.
    "vyacheslav wjacheslaw",
    "volkov volkoff volkow volkowa wolkowa",
    "alexei alexeij",
    "mikhailovich mikhailowich mikhailovitsch mihailovich",
    "kovalenko kowalenko",
    "zhanna stschanna schanna",
    "tsvetkov tswetkow cwetkow zwetkow",
    "yashin jaszin jaschin jaszina",
    "mikhailovna mikhailowna",
    "morozov morozoff morozowa",
    "semyonov semenow semenowa semjonow",
    "petrov petrow petrowa",
    "pavlov pavloff pavloffa",
    "viktor wiktor",
    "grishin grischin gristschin",
    "andreev andreewa andreeff andreeffa",
    "fedorov fedorow fedorowa",
    "zakharov sakharov sakharowa",
    "kiselev kiseljow kiseliow kiselev kiselew",
    "zhukov zhukow shukow",
    "vladimir wladimir",
    "vladimirovich wladimirowich",
    "vladimirovna wladimirowna",
    "novikov nowikow nowikowa",
    "tsoy tzoi tzoy",
    "kuznetsov kouznetzoff kuznetsova kuznetzova kusnezow",
    "kravchenko krawczenko",
    "zaitsev zaicew zaitzev",
    "kozlov kozloff koslow",
    "sergeyevna sergeyewna sergejevna",
    "sergeyevich sergeyewich sergejewich",
    "shevchenko schevchenko schevtschenko",
    "chaikovsky czaikowsky tschaikowsky",
    "nadezhda nadeshda",
    "shishkin sziszkin sziszkina",
    "egorov yegorow yegoroff yegoroffa",
    "aleksandrovich aleksandrowich",
    "yuri juriy yurij",
    "yevgeny ievgeny jewgeny",
    "nikolaevich nikolaevicz nikolaevitsch",
    "vasily wasily",
    "anastasia anastasya",
    "elena yelena jelena",
    # French/German/Gulf Arabic and Persian spellings.
    "hanan hanen",
    "hashimi hashimmie hashimie haschimmi hashemmy elhashemmi",
    "dariush dariuche",
    "tikriti tikritie",
    "nabil nabele nabile",
    "awad aoued aouade",
    "rezaei rezaey",
    "nasrin nasren nasrene nasreen",
    "javad djaved djavede djavade",
    "mousavi moussavy",
    "majid madscheed majede",
    "jamal dschammal",
    "ziad ziade",
    "ghanem ghanimme ghanime",
    "marwan marwaan marouen",
    "kermani kermany kermanie",
    "fatima fatimih",
    "shirin sheereene scheereen cheereen schirin",
    "tehrani tehranie",
    "arash arash arasch",
    "sami sammie samy",
    "masri masry masrie almasry",
    "barakat barakate",
    "khadija khadejah khadedschah",
    "khoury khourye",
    "mehdi mehdie",
    "babak babaak babake",
    "mahmoud mahmoude mahmoudy",
    "karim kareeme karime",
    "mustafa moustafah mustafaah mustafaa",
    "haddad hadade",
    "shamsi alshamsie elshamsie",
    "hosseini hosaini hossaini",
    "hussein hosaine housein",
    "bijan bidjane bidjen",
    "karimi caremmi karemi",
    "mahdi mahdy",
    "qasim ghasemy",
    "layla laylaah",
    "yasir yaser",
    "bilal billaal billalle",
    "fahd fahde",
    "huda hudahe",
    "khalid khaleede khallide",
    "mansour mansoure",
    "adnan adnane",
    "najjar nadschdschar",
    "bagheri baghiri",
    "shirazi scheerazi cheerazi",
    # Western catalogue spellings.
    "schroeder schroder",
    "andersen andersson",
    "jabouri djabouri eldjabouri",
    "shahin schahin",
    "yelizaveta ielizaveta",
    "egorov egorow",
    "belousov belousoff belousoffa",
    "yigui yingkuei",
    "mehdi mahdi mahdy",
    # Scientific Cyrillic transliteration after its diacritics are stripped.
    "tsoy coj",
    "anatoly anatolij",
    "vasily vasilij",
    "maria marija",
    "nadezhda nadezda",
    "natalia natalja",
    "tatiana tatjana",
    "zhanna zanna",
    "yulia julija",
    "ksenia ksenija",
    "lyudmila ljudmila",
    "aleksandrovich aleksandrovic",
    "alekseevich alekseevic",
    "andreevich andreevic",
    "ivanovich ivanovic",
    "mikhailovich mihajlovic",
    "nikolaevich nikolaevic",
    "petrovich petrovic",
    "sergeevich sergeevic",
    "vladimirovich vladimirovic",
    "chaikovskaya cajkovskaja",
    "chernov cernov cernova",
    "shishkin siskin siskina",
    "shcherbakov scerbakov scerbakova",
    "zhukov zukov zukova",
    "zaitsev zajcev zajceva",
    "tsvetkov cvetkov cvetkova",
    # Additional Turkish and Indonesian/Malay conventions.
    "omar omer oemar",
    "mahmoud mahmut machmud mahmoed",
    "yusuf djoesoef",
    "jafari djafar",
]

WORD_CANON: dict[str, str] = {}
for group in GROUPS:
    ws = group.split()
    # Ignore two deliberately malformed comments/fallback fragments above.
    if len(ws) > 1:
        root = ws[0]
        for w in ws:
            WORD_CANON[w] = root
# In this archive's nickname vocabulary Ted denotes Theodore.
WORD_CANON["ted"] = "theodore"
# Choi is ambiguous between a Chinese surname and the Russian/Korean Tsoy.
WORD_CANON["choi"] = "choi"


# Mandarin, Wade-Giles, Cantonese, and common Hokkien/Teochew surname forms.
# They are kept separate from general words because Wong can represent two
# different Han surnames; alternative keys handle that ambiguity explicitly.
CHINESE_SURNAME_GROUPS = [
    "zhang chang cheung cheong teo teoh", "wang wong ong", "li lee lei",
    "zhou chou chow chew", "chen chan tan", "lin lam lim", "wu ng goh",
    "zhu chu choo", "cai tsai choy choi chua", "zheng cheng tay tee",
    "huang wong oei wee", "xu hsu khoo", "he ho", "guo kuo kwok quek",
    "xie hsieh tse chia", "liu lau liew", "yang yeung yeo", "sun suen",
    "ma mah", "feng fung", "shen shum sum", "yuan yuen", "luo lo lok",
    "dai tai", "hu woo", "jiang chiang kong", "zeng tseng", "zhao chao",
    "gao kao", "cao tsao tso", "qian chien", "deng teng dang", "fan fahn",
    "tang tong", "song sung", "lu loo", "liang leung", "du tu",
    "pan poon", "zeng tsang", "ye yip", "cui chui tsui", "fan faan",
]
CH_SURNAME_CANONS: dict[str, set[str]] = defaultdict(set)
for g in CHINESE_SURNAME_GROUPS:
    ws = g.split(); root = ws[0]
    for w in ws:
        CH_SURNAME_CANONS[w].add(root)
CH_SURNAME_CANONS["choi"].add("tsoy")


RUSSIAN_SURNAMES = set("""
andreev belousov bondarenko bykov egorov grishin ivanov kiselev kovalenko
kozlov kravchenko kuznetsov lebedev makarov morozov nikolaev novikov orlov
pavlov petrov popov semyonov smirnov sokolov stepanov tkachenko tsvetkov tsoy
chaikovsky chernov fedorov shevchenko shishkin shcherbakov yakovlev yashin
zaitsev zakharov zhukov
""".split())


def canon_word(w: str) -> str:
    w = WORD_CANON.get(w, w)
    # Russian feminine surname forms correspond to the masculine form.
    if w.endswith("a") and w[:-1] in RUSSIAN_SURNAMES:
        w = w[:-1]
    return WORD_CANON.get(w, w)


def raw_tokens(s: str) -> list[str]:
    s = romanize(s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return s.split()


def person_tokens(s: str) -> list[str]:
    # Canonicalise simple lexemes first so compounds such as Abdul Azeez work
    # regardless of the romanisation chosen for the second word.
    t = [canon_word(x) for x in raw_tokens(s)]
    # Compound Arabic names before articles are discarded.
    out: list[str] = []
    i = 0
    while i < len(t):
        if i + 2 < len(t) and t[i] in {"abd", "abdul", "abdel"} and t[i+1] in {"al", "el", "ar", "ur"} and t[i+2] in {"rahman", "rahmen"}:
            out.append("abdulrahman"); i += 3; continue
        if i + 1 < len(t) and t[i] in {"abd", "abdul", "abdel"} and t[i+1] in {"rahman", "rahmen"}:
            out.append("abdulrahman"); i += 2; continue
        if i + 1 < len(t) and t[i] in {"abd", "abdul", "abdel"} and t[i+1] in {"aziz", "azez", "azees"}:
            out.append("abdulaziz"); i += 2; continue
        if i + 1 < len(t) and t[i] in {"abd", "abdul", "abdel"} and t[i+1] in {"allah", "ulla"}:
            out.append("abdullah"); i += 2; continue
        # The article can be written between Abd and any following divine
        # name (Abd al-Karim, Abd al-Aziz, ...).  Treat it as one father's or
        # given-name component so an optional nasab can be removed correctly.
        if i + 2 < len(t) and t[i] in {"abd", "abdul", "abdel"} and t[i+1] in {"al", "el"}:
            out.append("abdul" + t[i+2]); i += 3; continue
        if i + 1 < len(t) and t[i] in {"abd", "abdul", "abdel"} and t[i+1] == "karim":
            out.append("abdulkarim"); i += 2; continue
        out.append(t[i]); i += 1
    # Arabic sun-letter assimilation changes the written article (as-Sabah,
    # ar-Rashid, at-Tikriti, etc.) but not the name.
    t = [canon_word(x) for x in out
         if x not in {"al", "el", "ar", "as", "ash", "at", "ad", "az"}]
    # "an" is also a Chinese given-name syllable, so only treat it as the
    # assimilated article when it precedes the corresponding Arabic surname.
    t = [w for i, w in enumerate(t)
         if not (w == "an" and i + 1 < len(t) and t[i + 1] == "najjar")]
    return t


def _component_forms(words: list[str]) -> set[str]:
    """Forms of one name component: spaced/squashed Chinese given names."""
    if not words:
        return set()
    vals = {"".join(words)}
    # A few forms are role-specific: e.g. Chien is Jian as a given-name
    # syllable but Qian when it is a surname.
    given_syllables = {"chien": "jian"}
    alt = [given_syllables.get(w, w) for w in words]
    vals.add("".join(alt))
    if len(words) == 1:
        vals.add(words[0])
    return vals


def _given_forms(words: list[str]) -> set[str]:
    vals = _component_forms(words)
    if "ted" in vals:
        vals.update(("edward", "theodore"))
        vals.discard("ted")
    return vals


def _surname_forms(w: str) -> set[str]:
    vals = {w}
    vals.update(CH_SURNAME_CANONS.get(w, ()))
    return vals


def person_pairs(name: str) -> set[tuple[str, str]]:
    t = person_tokens(name)
    if len(t) < 2:
        return set()

    variants = [t]
    # Optional Romance surname particles.  Preserve the original too, which
    # is needed for compound surnames such as De la Cruz.
    without_particles = [w for w in t if w not in {"da", "de", "di", "do", "dos", "la"}]
    if without_particles != t:
        variants.append(without_particles)
    # bin/ibn/ben/b. plus father's name is optional.  Produce both the full
    # form and the policy form with that nasab element removed.
    for i, w in enumerate(t):
        if w in {"bin", "ibn", "ben", "b"} and 0 < i < len(t)-1:
            variants.append(t[:i] + t[i+2:])

    pairs: set[tuple[str, str]] = set()
    def is_patronymic(w: str) -> bool:
        return bool(re.search(r"(?:ovich|evich|yevich|ich|ovna|evna|yevna|ichna|vna)$", w))

    for v in variants:
        # Initials may occur at the end after family-first reordering.  A name
        # consisting only of a first initial and surname reduces to one token
        # and consequently cannot match by name.
        v = [w for w in v if len(w) != 1]
        if len(v) < 2:
            continue
        # Arbitrary intervening words are not discarded: the policy permits
        # Russian patronymics and explicit nasab, but not an added Chinese or
        # Western name.  This distinction blocks high-risk look-alikes.
        middle = v[1:-1]
        patronymic = bool(middle) and all(is_patronymic(w) for w in middle)
        if len(v) == 2 or patronymic:
            for g in _given_forms([v[0]]):
                for f in _surname_forms(v[-1]): pairs.add((g, f))
            for g in _given_forms([v[-1]]):
                for f in _surname_forms(v[0]): pairs.add((g, f))
        # Explicit family-first Russian order: Fedorov, Yuri Alexandrovich.
        if len(v) >= 3 and all(is_patronymic(w) for w in v[2:]):
            for g in _given_forms([v[1]]):
                for f in _surname_forms(v[0]): pairs.add((g, f))
        # Chinese given names can be one token or several syllables, in either
        # family-name-first or family-name-last order.
        for g in _given_forms(v[:-1]):
            for f in _surname_forms(v[-1]): pairs.add((g, f))
        for g in _given_forms(v[1:]):
            for f in _surname_forms(v[0]): pairs.add((g, f))
        # Western compound surnames (de la Cruz, Mac Donald, etc.).
        if len(v) > 2:
            for g in _given_forms([v[0]]): pairs.add((g, "".join(v[1:])))
            for g in _given_forms([v[-1]]): pairs.add((g, "".join(v[:-1])))
    return pairs


LEGAL_PHRASES = [
    ("limited", "liability", "company"), ("joint", "stock", "company"),
    ("public", "joint", "stock", "company"),
    ("sociedad", "anonima"), ("free", "zone", "establishment"),
]
LEGAL_WORDS = {
    "llc", "ltd", "limited", "company", "co", "sa", "gmbh", "jsc", "ao",
    "oao", "pao", "pjsc", "fze", "fz", "inc", "incorporated", "corp",
    "corporation", "plc", "llp", "ag", "nv", "bv", "pte", "public",
}


def entity_key(s: str) -> tuple[str, ...]:
    x = romanize(s)
    # Dotted legal abbreviations need compacting before punctuation splitting.
    for pat, repl in ((r"l\s*\.\s*l\s*\.\s*c\s*\.?", "llc"),
                      (r"s\s*\.\s*a\s*\.?", "sa"),
                      (r"g\s*\.\s*m\s*\.\s*b\s*\.\s*h\s*\.?", "gmbh"),
                      (r"co\s*\.", "co")):
        x = re.sub(pat, repl, x)
    x = x.replace("&", " and ")
    t = re.sub(r"[^a-z0-9]+", " ", x).split()
    if t and t[0] == "the": t = t[1:]
    t = [w for w in t if w != "and"]
    changed = True
    while changed:
        changed = False
        for p in LEGAL_PHRASES:
            n = len(p)
            for i in range(len(t)-n+1):
                if tuple(t[i:i+n]) == p:
                    t[i:i+n] = []; changed = True; break
            if changed: break
    t = [w for w in t if w not in LEGAL_WORDS]
    return tuple(t)


def vessel_key(s: str) -> tuple[str, ...]:
    t = raw_tokens(s)
    if len(t) >= 2 and t[:2] in (["m", "v"], ["m", "t"]): t = t[2:]
    elif t and t[0] in {"mv", "mt", "vessel"}: t = t[1:]
    return tuple(t)


def dob_compatible(record_dob: str, entry_dob: str) -> bool:
    if not record_dob or not entry_dob:
        return True
    return entry_dob.startswith(record_dob)


class Linker:
    def __init__(self, entries: list[dict]):
        self.entries = entries
        self.ids: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self.index: dict[str, dict[object, set[int]]] = {
            "individual": defaultdict(set), "entity": defaultdict(set), "vessel": defaultdict(set)
        }
        self.weak: dict[tuple[str, str], set[int]] = defaultdict(set)
        self.weak_whole: dict[tuple[str, ...], set[int]] = defaultdict(set)
        for pos, e in enumerate(entries):
            for ident in e.get("ids", []):
                self.ids[(str(ident.get("type", "")).strip(), str(ident.get("number", "")).strip())].append(e)
            names = [e.get("primary_name", "")]
            if e.get("script_name") and e["script_name"] not in names:
                names.append(e["script_name"])
            names += [a["name"] for a in e.get("aliases", []) if a.get("strength") == "strong"]
            typ = e.get("type", "individual")
            if typ == "individual":
                for n in names:
                    for k in person_pairs(n): self.index[typ][k].add(pos)
                for a in e.get("aliases", []):
                    if a.get("strength") == "weak":
                        self.weak_whole[tuple(person_tokens(a.get("name", "")))].add(pos)
                        for k in person_pairs(a.get("name", "")):
                            self.weak[(k[0], k[1])].add(pos)
            elif typ == "entity":
                for n in names: self.index[typ][entity_key(n)].add(pos)
            elif typ == "vessel":
                for n in names: self.index[typ][vessel_key(n)].add(pos)

    def link(self, rec: dict) -> tuple[str, str]:
        it = rec.get("id_type", "").strip(); ino = rec.get("id_number", "").strip()
        if it and ino and self.ids.get((it, ino)):
            return "MATCH", min(self.ids[(it, ino)], key=lambda e: str(e["uid"]))["uid"]

        typ = rec.get("type", "individual").strip().lower()
        name = rec.get("full_name", "")
        positions: set[int] = set()
        if typ == "individual":
            keys = person_pairs(name)
            for k in keys: positions.update(self.index[typ].get(k, ()))
        elif typ == "entity":
            positions.update(self.index[typ].get(entity_key(name), ()))
        elif typ == "vessel":
            positions.update(self.index[typ].get(vessel_key(name), ()))
        else:
            return "NO_MATCH", ""

        rdob = rec.get("dob", "").strip()
        candidates = [self.entries[p] for p in positions
                      if dob_compatible(rdob, str(self.entries[p].get("dob", "")).strip())]

        # A weak alias is only admissible with an identical full date on both
        # sides.  Add it after the normal-name candidate search.
        if typ == "individual" and len(rdob) == 10:
            weak_pos: set[int] = set()
            weak_pos.update(self.weak_whole.get(tuple(person_tokens(name)), ()))
            for k in person_pairs(name): weak_pos.update(self.weak.get(k, ()))
            for p in weak_pos:
                e = self.entries[p]
                if str(e.get("dob", "")).strip() == rdob and e not in candidates:
                    candidates.append(e)

        if not candidates:
            return "NO_MATCH", ""
        # Name candidates are ranked by actual DOB support, then UID.  IDs
        # have already returned above.
        candidates.sort(key=lambda e: (0 if rdob and e.get("dob") else 1, str(e["uid"])))
        return "MATCH", candidates[0]["uid"]


def main() -> None:
    ap = argparse.ArgumentParser(description="Link digitised records to an archive register")
    ap.add_argument("--register", required=True)
    ap.add_argument("--records", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    with open(args.register, encoding="utf-8-sig") as f:
        entries = json.load(f)
    linker = Linker(entries)
    with open(args.records, newline="", encoding="utf-8-sig") as src, \
         open(args.out, "w", newline="", encoding="utf-8") as dst:
        reader = csv.DictReader(src)
        writer = csv.DictWriter(dst, fieldnames=["record_id", "decision", "matched_uid"], lineterminator="\n")
        writer.writeheader()
        for rec in reader:
            decision, uid = linker.link(rec)
            writer.writerow({"record_id": rec.get("record_id", ""), "decision": decision, "matched_uid": uid})


if __name__ == "__main__":
    main()
