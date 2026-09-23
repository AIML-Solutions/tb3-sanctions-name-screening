#!/usr/bin/env python3
"""Offline sanctions name screening engine (Python 3.12, standard library only)."""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict


CYRILLIC = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "shch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "і": "i", "ї": "yi", "є": "ye", "ґ": "g",
})

ARABIC = str.maketrans({
    "ا": "a", "آ": "a", "أ": "a", "إ": "a", "ٱ": "a", "ب": "b", "پ": "p",
    "ت": "t", "ث": "th", "ج": "j", "چ": "ch", "ح": "h", "خ": "kh",
    "د": "d", "ذ": "dh", "ر": "r", "ز": "z", "ژ": "zh", "س": "s", "ش": "sh",
    "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "a", "غ": "gh",
    "ف": "f", "ق": "q", "ك": "k", "ک": "k", "گ": "g", "ل": "l", "م": "m",
    "ن": "n", "ه": "h", "ۀ": "h", "ة": "h", "و": "w", "ؤ": "w", "ي": "y",
    "ی": "y", "ى": "y", "ئ": "y", "ء": "", "ـ": "",
})


def fold_text(value: str) -> str:
    """Lowercase, transliterate supported scripts, and remove accents."""
    value = (value or "").strip().lower().replace("ı", "i").replace("ł", "l").replace("ß", "ss").replace("ø", "o")
    value = value.translate(CYRILLIC).translate(ARABIC)
    value = "".join(
        ch for ch in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(ch)
    )
    return value


def words(value: str) -> list[str]:
    # Apostrophes in O'Brien and Wade-Giles are orthographic, not word breaks.
    value = fold_text(value).replace("'", "").replace("’", "")
    return re.findall(r"[a-z0-9]+", value)


def _alias_groups() -> list[tuple[str, ...]]:
    """Known conventional spellings. Each tuple has one semantic value."""
    return [
        # Western given names and conventional nicknames.
        ("william", "will", "bill", "billy", "liam"), ("katherine", "catherine", "kate", "kathy"),
        ("michael", "mike", "mikey"), ("jose", "pepe"),
        ("francisco", "paco", "frank"), ("andrew", "drew"),
        ("benjamin", "ben", "benny"), ("elizabeth", "elisabeth", "beth"),
        ("charles", "chuck", "charlie"), ("richard", "dick", "rick", "ricky"),
        ("robert", "bob", "bobby", "robbie"), ("frederick", "fred", "freddie"),
        ("theodore", "ted", "theo"), ("patricia", "trish", "pat", "patty"), ("victoria", "tori", "vicky"),
        ("jennifer", "jenny", "jen"), ("james", "jamie"), ("joseph", "joe", "joey"),
        ("peter", "pete"), ("steven", "stephen", "steve"),
        ("rebecca", "becca", "becky"), ("anthony", "tony"), ("christopher", "chris"),
        ("thomas", "tom", "tommy"), ("alexander", "alex", "sasha"),
        ("daniel", "dan", "danny"), ("samuel", "sam", "sammy"),
        ("margaret", "meg", "maggie", "peggy"), ("dorothy", "dot"),
        ("henry", "hank", "harry"), ("susan", "suzy"), ("john", "jon", "johnny", "jack"),
        ("barbara", "babs", "barb"), ("matthew", "matt"),
        ("nicholas", "nicolas", "nick"), ("pedro", "peter"),

        # Arabic and Persian given names, including Turkish/Indonesian forms.
        ("abbas", "abas", "abase", "abbase"),
        ("abdulrahman", "abdulrahmane", "abdolrahman", "abdulrahmen", "abdurrahman", "abdelrahman", "abdoelrahman"),
        ("abdulkarim", "abdulcarem", "abdulkarem", "abdulkerim", "abdelkarim", "abdoelkarim"), ("abdulaziz", "abdulazez", "abdelaziz", "abdoelaziz"),
        ("abdullah", "abdola", "abdolah", "abdolla", "abdoolah", "abdoolla", "abdoollah", "abdollah", "abdoullah", "abdula"),
        ("adnan", "adnane", "adnen"), ("ahmad", "ahmed", "ahmede", "ahmet", "achmad"),
        ("aisha", "aishah", "aichah", "aischah", "ayesha", "ayse"), ("amina", "aminah", "amena", "ameena", "amenah", "emine"),
        ("amir", "ameer", "amer"), ("anwar", "anouar", "anouare"), ("arash", "arache"),
        ("bashar", "bachar", "bachare", "baschar"), ("behrouz", "behrouze"),
        ("bijan", "bijen", "bigen"), ("bilal", "billal", "billalle"),
        ("dalal", "dallal", "dallale"),
        ("dariush", "darioush", "darioushe", "dariouch", "dariusch", "daroueesh"),
        ("ehsan", "ehsen", "ehsane", "ihsan"), ("fahd", "fahde"),
        ("faisal", "fayssal", "faissal", "faysal"), ("farhad", "farhed", "farhede"),
        ("fatima", "fatema", "fatimah", "fatemah", "fatemma", "fateemma", "fatemmah", "fatemeh", "fatimmah", "fatimmih", "fatimmihe", "fatma"),
        ("hamid", "hamed", "hameed", "hamede", "hammeed", "hamide", "hammed", "hammid"), ("hamza", "hamzah", "hamzahe"),
        ("hassan", "hasan", "hasen", "hassen"),
        ("hussein", "husein", "husain", "hussain", "husayn", "hossein", "hosain", "hossain", "housein", "housseine", "huseine", "hussaine", "huseyin", "hoesain", "hoesein", "hoessein"),
        ("hisham", "hicham", "hichame", "hischam", "hishamme"), ("huda", "hudah", "hudahe", "houdah"),
        ("ibrahim", "ibrahem", "ibraheme", "ibraheeme"), ("omar", "omer", "oemar"),
        ("ismail", "ismayl", "ismayle", "ismaile"), ("jamal", "djamal", "djamale", "dschammal", "cemal", "cammal"),
        ("javad", "javed", "dschaved", "djavade", "cevat"), ("kamal", "camal", "camale"),
        ("kamran", "kamren"), ("karim", "karem", "kareem", "kareme"),
        ("kaveh", "kavih"), ("khadija", "khadeja", "khadeejah", "khadejah", "khadijah", "khadidjah", "khadedja"),
        ("khalid", "khaled", "khalede", "khaleed", "khalleed", "khalled", "halid", "halit", "chalid"),
        ("layla", "leila", "laila", "lailla", "laylah", "leyla"), ("majed", "majid", "maged", "majeed", "madjed", "madsched", "madjeed", "madjide"),
        ("mahsa", "mahsah", "mahsahe"), ("mahmoud", "mahmoude"), ("mariam", "mariaam", "mariame", "maryam", "maryamme", "mariamme", "meryem"),
        ("marwan", "marwen"), ("masoud", "massoud", "massoude"),
        ("mohsen", "mohsin", "mohsine"), ("muhammad", "mohammad", "mohammed", "mohamed", "mohamad", "muhamed", "muhammed", "muhamaad", "muhamade", "mouhamad", "moehammad", "mochamad", "mehmet"),
        ("mustafa", "mustafah", "moustafa", "moustafah", "moustafahe", "moestafa"),
        ("nabil", "nabeel", "nabel", "nabele", "nabeele", "nabille"),
        ("morteza", "mortezah", "mortezahe", "mortiza", "mortizah"), ("nasrin", "nasren", "nasrene", "nasreen"), ("niloufar", "nilloufar"), ("nizar", "nizare"),
        ("nour", "noure"), ("omid", "omeed", "omed", "omede"), ("parisa", "paresa", "parissah", "parisah", "parissa", "paressah", "pareessa"),
        ("parviz", "parveez", "parvez"), ("ramin", "ramen", "ramene", "rammen", "rammin"), ("rami", "rammi"), ("rania", "raniah"),
        ("reza", "rezah", "rezahe", "riza"), ("saeid", "saeed", "said", "saaid", "saed", "saede", "saaide", "sait"),
        ("salim", "saleem", "sallem", "selim"), ("salma", "salmah", "salmahe"),
        ("sami", "samy", "sammi"), ("samir", "samer", "sammer", "sammeer", "sammir", "sammire"), ("samira", "samirah", "sammera", "sammirah"), ("sharif", "sjarif"),
        ("shahram", "chahram", "chahrame"), ("shirin", "sheren", "sheereen"), ("siavash", "siavasch", "siavashe"),
        ("taha", "tahah", "tahahe"), ("talal", "tallal", "tallale", "tallalle"),
        ("tariq", "tareq", "tarek", "tareqe", "tarik", "tarike", "tareek"),
        ("walid", "waled", "walleed", "walled", "wallid", "oualed"),
        ("yasser", "yasir", "yassir", "yasere", "yassire"),
        ("yusuf", "yusof", "yusoof", "yusoofe", "yussof", "yussuf", "yussoof", "joesoef"),
        ("zainab", "zaynab", "zaynabe", "zeynep"), ("zahra", "zahrah", "zahrahe"), ("ziad", "zied", "ziade"), ("golnaz", "golnaze"),

        # Arabic/Persian family names and their common romanizations.
        ("akbari", "akbarie", "akbary"), ("amin", "amen", "ameen", "ameene"), ("attar", "atar", "atare"), ("awad", "awed"), ("bagheri", "baghiri"),
        ("aziz", "azez", "azeez", "azeeze"), ("bakr", "bakre"), ("barakat", "barakaat", "baracate"), ("darwish", "darwesh", "darweesh", "darwisch"),
        ("douri", "dourie", "dury"), ("ebrahimi", "ebrahemi", "ebraheemi", "ebrahemmi", "ebraheemmi"), ("esfahani", "esfahany"),
        ("fares", "faris", "faresse", "farise"), ("ghanem", "ghanim", "ghanime", "ghaneme"),
        ("ghasemi", "ghasemy", "ghassimi", "ghassimmi", "qasemi"), ("haddad", "hadad", "haded", "hadade", "haddede"),
        ("hakim", "hakem", "hakeem", "hakeeme"), ("hamdan", "hamden", "hamdane", "hamdene"),
        ("hashemi", "hasheemmi", "hashimi", "hashimy", "hachemi"), ("jafari", "djafari", "gafari", "jafarie"),
        ("jabouri", "djabouri", "dschabouri", "gabouri"), ("kanaan", "kanan", "kanaen", "kanen", "canaan", "canaen", "canaane"),
        ("karimi", "caremi", "careemi", "kareimi", "kareemi", "karemmi", "karimmi", "kareemmi"), ("khatib", "khateb", "khateeb", "khateebe"),
        ("khoury", "khourye"), ("mansour", "mansoure"),
        ("masri",), ("mousavi", "moussavi"),
        ("najjar", "najar", "najare", "naggar", "nagar", "nadjdjar", "nadjdjare", "nadschdschar", "nadschar"),
        ("mohammadi", "mohamadi"), ("nasrallah", "nasrala", "nasralah", "nasralla"), ("nasser", "naser", "nasir", "nassir", "nassire"),
        ("nazari", "nazary", "nazarie"),
        ("qasim", "kassem", "kaseem", "qaseem", "qaseeme", "qasem", "qassem", "qasseem", "kasim", "gasim", "gasem", "gassem"),
        ("rahimi", "rahemi", "rahimmie", "rahimmi", "rahemmi", "raheemmi"), ("rahmani", "rahmanie", "rahmany"), ("rashid", "rashed", "rashede", "rasheed", "rasched", "raschid", "rached", "rachid", "rachide"),
        ("rezaei", "rezai", "rezaai"), ("rostami", "rostammi"),
        ("sadeghi", "sadighi"), ("saleh", "salih", "sallih", "salleh", "salihe"), ("salehi", "salihi", "sallihi", "sallehie"),
        ("salman", "salmane", "salmen", "salmene"), ("sayed", "sayid", "sayide"),
        ("shahin", "shahen", "shahene", "shaheen", "schahin", "chahin", "chahine", "chaheen", "chahen", "sahin"), ("shamsi", "chamsi", "schamsi"),
        ("hosseini", "hosaini", "hoseini"),
        ("shirazi", "sherazi", "chirazi", "cheerazi"), ("sultan", "sulten", "soultane"),
        ("tabrizi", "tabrezi", "tabreezi"), ("tikriti", "tikreti", "tikreeti"),
        ("sabah", "saba"), ("yassin", "yasen"), ("zahrani",), ("zaidi", "zaydi"), ("zamani", "zammani"),

        # Russian and other Cyrillic given names.
        ("aleksandr", "alexandr", "alexander", "aleksander"),
        ("aleksei", "alekseiy", "alexei", "alexey", "aleksej", "aleksiej"), ("andrei", "andrey", "andreiy", "andrej", "andriej"),
        ("artyom", "artem", "artiom", "artjom"), ("dmitri", "dmitry", "dmitriy", "dmitrij"),
        ("fedor", "fyodor", "fiodor", "fjodor"), ("grigory", "grigoriy", "grigorij"), ("gennady", "gennadiy", "gennadij", "giennadij"), ("arkady", "arkadiy", "arkadij"), ("maksim", "maxim"),
        ("mikhail", "mihail", "michail", "mitschail"), ("nikolai", "nikolay", "nikolaiy", "nikolaj"), ("sergei", "sergey", "sergeiy", "sergej", "serguei", "siergiej"),
        ("ruslan", "rouslan"), ("stanislav", "stanislaff", "stanislaw"), ("timur", "timour"),
        ("vasily", "vasili", "vasiliy", "vasilij", "wasily", "wasilij", "wassili"), ("valery", "valerij", "walery", "walerij"), ("viktor", "wiktor"),
        ("vladimir", "wladimir"), ("vyacheslav", "vyatcheslav", "vyatcheslaff", "vyatscheslav", "wyatscheslaw", "vjaceslav", "wiaczeslaw"),
        ("yevgeny", "evgeny", "evgeniy", "evgueny", "ievgueny", "jewgeny", "jewgienij", "yewgeny", "evgenij", "eugene"),
        ("yuri", "yuriy", "yury", "iuri", "jurij", "juriy"),
        ("anastasia", "anastasiya", "anastasija"), ("anatoly", "anatolij"), ("darya", "daria", "darja"),
        ("ekaterina", "yekaterina"), ("elena", "yelena"),
        ("maria", "mariya", "marya", "marja", "marija"), ("lyudmila", "lyoudmila", "ljudmila", "ludmila"), ("semyon", "semen", "semjon", "siemion"),
        ("nadezhda", "nadeshda", "nadejda", "nadezda", "nadiezda"),
        ("natalia", "nataliya", "natalya", "natalja", "natalija"), ("oksana", "oxana"), ("svetlana", "swetlana", "swietlana"),
        ("tatiana", "tatjana"), ("valentina", "walentina"), ("viktoria", "viktoriya", "viktorya", "viktorija", "victoria", "wiktoria"),
        ("yelizaveta", "elizaveta", "ielizaveta", "jelisaveta", "jelizaveta", "jelizaweta", "jelizawieta", "yelizaweta"), ("hanan", "hanene"),
        ("yulia", "yuliya", "yulya", "julija", "julia"), ("kseniya", "ksenija", "ksenia"), ("zhanna", "shanna", "schanna", "janna", "zanna"), ("hanan", "hanen", "hanene"),

        # Russian surnames. Masculine and feminine forms intentionally share roots.
        ("andreev", "andreeva", "andreeff", "andreew", "andrejew", "andrejewa"),
        ("belousov", "belousova", "belousoff", "belousow", "bielousow", "bielousowa"),
        ("bykov", "bykova", "bykoffa", "bykow", "bykowa"),
        ("chaikovsky", "chaikovskaya", "chaikowsky", "chaikowskaya", "tchaikovsky", "tchaikovskaya", "schaikovskaya", "cajkovskij", "cajkovskaja", "czajkowski", "czajkowska"),
        ("chernov", "chernova", "tchernov", "tchernova", "tchernoff", "cernov", "cernova", "czernow", "czernowa"),
        ("egorov", "egorova", "egoroff", "egorow", "egorowa", "yegorov", "yegorova", "yegoroff", "yegorowa", "jegorov", "jegorova", "jegorowa"),
        ("fedorov", "fedorova", "fyodorov", "fyodorova", "fedoroff", "fedoroffa", "fedorow", "fedorowa", "fiodorow", "fiodorowa"),
        ("grishin", "grishina", "grichin", "gritchin", "gritchina", "grischin", "grischina", "gristschina", "grisin", "grisina", "griszin", "griszyn"),
        ("ivan", "iwan"), ("ivanov", "ivanova", "ivanoff", "ivanoffa", "iwanow", "iwanowa"),
        ("kiselyov", "kiselyova", "kiselyow", "kiselyowa", "kiselev", "kiseleva", "kiseliov", "kiseliova", "kiseljov", "kiseljova", "kiseljowa", "kiseleff", "kiseleffa"),
        ("kovalenko", "kowalenko"), ("kozlov", "kozlova", "kozloff", "kozlow", "kozlowa", "koslow"),
        ("kravchenko", "kravtchenko", "kravcenko", "krawchenko", "krawczenko", "krawtschenko"),
        ("kuznetsov", "kuznetsova", "kuznetsow", "kuznetsowa", "kuznecov", "kuznecova", "kuzniecow", "kuzniecowa", "kouznetsoff", "kouznetzova"),
        ("lebedev", "lebedeva", "lebedeffa", "lebedew", "lebedewa", "lebiediew", "lebiediewa"),
        ("makarov", "makarova", "makaroff", "makarow", "makarowa"),
        ("morozov", "morozova", "morosow", "morozoff", "morozoffa", "morozow"),
        ("nikolaev", "nikolaeva", "nikolaew", "nikolaewa", "nikolaeff", "nikolaeffa", "nikolajew", "nikolajewa"),
        ("novikov", "novikova", "novikoff", "novikoffa", "nowikow"),
        ("orlov", "orlova", "orlowa", "orloff", "orloffa", "orlow"),
        ("pavlov", "pavlova", "pavloff", "pavloffa", "pawlow"),
        ("pavel", "pawel"), ("petrov", "petrova", "petroff", "petrow", "petrowa", "pietrow", "pietrowa"), ("popov", "popova", "popoff", "popow", "popowa"),
        ("shcherbakov", "shcherbakova", "shtcherbakov", "shtcherbakova", "chtcherbakov", "chtcherbakova", "chcherbakov", "chcherbakoff", "scerbakov", "scerbakova", "scerbakow", "scerbakowa", "szczerbakow", "szczerbakowa", "schtscherbakov", "schtscherbakow"),
        ("shevchenko", "tchevtchenko", "schewchenko", "schewtschenko", "shewtschenko", "sevcenko", "szewczenko"),
        ("shishkin", "shishkina", "schischkin", "schischkina", "tchitchkin", "siskin", "siskina", "szyszkin", "szyszkina"),
        ("smirnov", "smirnova", "smirnoff", "smirnow"),
        ("sokolov", "sokolova", "sokoloff", "sokolow"),
        ("stepanov", "stepanova", "stepanoff", "stepanow", "stiepanow", "stiepanowa"),
        ("semyonov", "semyonova", "semyonow", "semjonov", "semenov", "semenova", "semenow", "semenoff", "semenoffa", "semionov", "semionova", "semionoff", "semionow"),
        ("tkachenko", "tkatchenko", "tkatschenko", "tkazchenko", "tkacenko", "tkaczenko"),
        ("tsoi", "tsoy", "tsoiy", "soiy", "tzoi", "tzoy", "tzoiy", "coj"),
        ("tsvetkov", "tsvetkova", "cvetkov", "cvetkova", "cwietkow", "cwietkowa", "tswetkow", "tswetkowa", "zwetkow"),
        ("volkov", "volkova", "volkoff", "volkoffa", "wolkow"),
        ("yakovlev", "yakovleva", "iakovlev", "iakovleff", "jakovlev", "jakovleva", "jakowlew", "jakowlewa", "yakowlew", "yakowlewa"),
        ("yashin", "yashina", "iachin", "iachina", "iashin", "jashin", "jashina", "jasin", "jasina", "yaschin", "yastschina", "yaszin", "jaszin", "jaszina", "jaschin", "yatchina"),
        ("zaitsev", "zaitseva", "zaitzeff", "saisev", "zajcev", "zajceva", "zajcew", "zajcewa", "zaitsew", "zaitsewa", "saitsew"),
        ("zakharov", "zakharova", "zakharoff", "zakharoffa", "zakharow", "zaharov", "zaharova", "zacharow", "zacharowa", "sacharow", "sacharowa", "sakharov", "sakharowa"),
        ("zhukov", "zhukova", "zhukow", "zhukowa", "jukov", "joukov", "shukow", "jukoff", "jukoffa", "joukoffa", "zukov", "zukova", "zukow", "zukowa"),

        # European surname spelling conventions.
        ("andersen", "anderson", "andersson"),
        ("bianchi", "bianci"), ("fernandez", "fernandes"), ("ferreira", "ferreyra"),
        ("fischer", "fisher"), ("johansson", "johansen", "johanson"),
        ("larsen", "larson"), ("lindqvist", "lindkvist", "lindquist"),
        ("kowalski", "kowalsky"), ("meyer", "meier", "mayer"), ("mueller", "muller"), ("novak", "nowak"),
        ("olsen", "olson"), ("petersen", "peterson", "pedersen"),
        ("rodriguez", "rodrigues"), ("schmidt", "schmitt", "schmid"),
        ("schroeder", "schroder"), ("sorensen", "sorenson"),
        ("weiss", "weis"),
    ]


TOKEN_CANON: dict[str, str] = {}
for _group in _alias_groups():
    _canonical = _group[0]
    for _item in _group:
        TOKEN_CANON[_item] = _canonical
# A few legitimate equivalence groups overlap (for example Peter/Pedro and
# Victoria/Viktoria). Resolve those links transitively so nicknames land on
# the same final value as the formal name.
for _item in list(TOKEN_CANON):
    _value = TOKEN_CANON[_item]
    _seen = {_item}
    while _value in TOKEN_CANON and TOKEN_CANON[_value] != _value and _value not in _seen:
        _seen.add(_value)
        _value = TOKEN_CANON[_value]
    TOKEN_CANON[_item] = _value


PATRONYMICS = {
    "aleksandrovich", "aleksandrovna", "alexandrovich", "alexandrovna",
    "aleksandrovitch", "alexandrovitch", "aleksandrovic", "aleksandrowich", "aleksandrowicz", "alekseevich", "alexeevich", "alekseevic", "alekseevitch", "alekseevitsch",
    "andreevich", "andreevic", "ivanovich", "ivanovitch", "ivanovitsch", "ivanovic", "ivanovna", "iwanowich", "iwanowna",
    "mikhailovich", "mikhaylovich", "mikhailovitch", "mikhailovitsch", "mikhailowich", "mikhailovna", "mikhailowna", "mikhaylovna", "michailovich", "michailovna",
    "mihajlovic", "mihajlovna", "nikolaevich", "nikolaevitch", "nikolaevitsch", "nikolaevic", "nikolaevna", "nikolaewich", "nikolaewna",
    "petrovich", "petrovitch", "petrovitsch", "petrovic", "petrowich", "petrovna", "petrowna",
    "sergeevich", "sergeevic", "sergeevna", "sergejevna", "sergeyevich", "sergeyevitsch", "sergeyevitch", "sergeyevna", "sergeyewich", "sergeyewna", "sergueyevich", "sergueyevna",
    "vladimirovich", "vladimirovitch", "vladimirovitsch", "vladimirovic", "vladimirovna", "wladimirowich", "wladimirowna",
}

ARABIC_FAMILIES = {
    "amin", "amen", "attar", "awad", "bagheri", "bakr", "barakat", "darwish", "douri",
    "ebrahimi", "esfahani", "farahani", "fares", "farsi", "ghanem", "ghasemi", "haddad",
    "hakim", "hamdan", "hashemi", "hashimi", "jafari", "jabouri", "kanaan", "karimi",
    "kermani", "khatib", "khoury", "mahdi", "mahmoudi", "mansour", "masri", "moradi",
    "mousavi", "najjar", "nasrallah", "nasser", "nazari", "qasim", "rahimi", "rahmani",
    "rashid", "rezaei", "rostami", "sadeghi", "saleh", "salehi", "salman", "sayed", "shahin",
    "shamsi", "shirazi", "sultan", "tabrizi", "tehrani", "tikriti", "yazdani", "zahrani",
    "sabah", "yassin", "hosseini", "zaidi", "zamani",
}


def canon_token(token: str) -> str:
    token = fold_text(token)
    token = re.sub(r"[^a-z0-9]", "", token)
    if not token:
        return ""
    if token in TOKEN_CANON:
        return TOKEN_CANON[token]

    # Attached Arabic article, including sun-letter assimilated spellings.
    candidates = []
    for prefix in ("al", "el"):
        if token.startswith(prefix) and len(token) > len(prefix) + 2:
            candidates.append(token[len(prefix):])
    for prefix in ("ash", "an", "ar", "as", "at", "ad", "az"):
        if token.startswith(prefix) and len(token) > len(prefix) + 2:
            rest = token[len(prefix):]
            candidates.append(rest)
    for rest in candidates:
        rest = TOKEN_CANON.get(rest, rest)
        if rest in ARABIC_FAMILIES:
            return rest

    # Conservative productive rules used by the source romanizations: an added
    # doubled consonant or a terminal epenthetic e is not a new name.  Apply the
    # rule only if it lands on a name already present in the explicit table.
    dedoubled = re.sub(r"([a-z])\1+", r"\1", token)
    for form in (dedoubled, token[:-1] if token.endswith("e") else token):
        if form in TOKEN_CANON:
            return TOKEN_CANON[form]

    return TOKEN_CANON.get(token, token)


def _prepare_person_words(name: str) -> list[str]:
    text = fold_text(name)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    # Normalize compound given names and surnames before punctuation is discarded.
    text = re.sub(r"\b(?:abd(?:ul|ol|ool|ur)?|abdel|abdoel)\s+(?:(?:al|el|ar)\s+)?rahm[ae]+n[e]?\b", "abdulrahman", text)
    text = re.sub(r"\babd\s+(?:al|el)\s+rahm[ae]n[e]?\b", "abdulrahman", text)
    text = re.sub(r"\b(?:abd(?:ul|ol|ool)?|abdel|abdoel)\s+(?:(?:al|el)\s+)?kar(?:i|ee?)m[e]?\b", "abdulkarim", text)
    text = re.sub(r"\babd\s+(?:al|el)\s+kar(?:i|e)m[e]?\b", "abdulkarim", text)
    text = re.sub(r"\b(?:abd(?:ul|ol|ool)?|abdel|abdoel)\s+(?:(?:al|el)\s+)?az(?:i|ee?)z[e]?\b", "abdulaziz", text)
    text = re.sub(r"\bdu\s+bois\b", "dubois", text)
    text = re.sub(r"\bde\s+la\s+cruz\b", "delacruz", text)
    text = re.sub(r"\bvan\s+(?:der|den)\s+berg\b", "vanberg", text)
    text = re.sub(r"\bvanderberg\b", "vanberg", text)
    text = re.sub(r"\bmac\s+donald\b", "macdonald", text)
    text = re.sub(r"\bmc\s*donald\b", "macdonald", text)
    text = re.sub(r"\bo[\s'\u2019-]*brien\b", "obrien", text)
    text = re.sub(r"\bdasilva\b", "silva", text)
    raw = re.findall(r"[a-z0-9]+", text.replace("'", ""))

    # The same surname particles may follow the family name in comma/reversed order.
    raw_set = set(raw)
    if {"du", "bois"}.issubset(raw_set):
        raw.remove("du"); raw.remove("bois"); raw.append("dubois")
    if {"de", "la", "cruz"}.issubset(raw_set):
        raw.remove("de"); raw.remove("la"); raw.remove("cruz"); raw.append("delacruz")
    if {"o", "brien"}.issubset(raw_set):
        raw.remove("o"); raw.remove("brien"); raw.append("obrien")
    if "da" in raw and "silva" in raw:
        raw.remove("da")
    if "le" in raw and "fevre" in raw:
        raw.remove("le"); raw.remove("fevre"); raw.append("lefevre")
    if "berg" in raw and "van" in raw and ("der" in raw or "den" in raw):
        raw.remove("berg"); raw.remove("van")
        raw.remove("der" if "der" in raw else "den"); raw.append("vanberg")

    # Join split Arabic definite articles to nothing; the family word remains.
    out: list[str] = []
    i = 0
    while i < len(raw):
        t = raw[i]
        if t in {"al", "el", "an", "ar", "as", "ash", "at", "ad", "az"}:
            i += 1
            continue
        # Nasab (bin/ibn/ben/b + father's name) is optional under the policy.
        if (t in {"bin", "ibn", "b"} or (t == "ben" and i > 0)) and i + 1 < len(raw):
            i += 2
            continue
        if len(t) == 1:  # middle initial
            i += 1
            continue
        if t in PATRONYMICS:
            i += 1
            continue
        c = canon_token(t)
        if c:
            out.append(c)
        i += 1
    return out


def person_key(name: str, script_lexicon: dict[str, str] | None = None) -> tuple[str, ...]:
    # Exact original-script words can be mapped from parallel list records.
    original = (name or "").lower()
    for source, replacement in (
        ("نصر الله", "nasrallah"), ("عبد الله", "abdullah"),
        ("عبد الرحمن", "abdulrahman"), ("عبد العزيز", "abdulaziz"),
        ("عبد الكريم", "abdulkarim"), ("عبد الکریم", "abdulkarim"),
    ):
        original = original.replace(source, replacement)
    has_script = bool(re.search(r"[\u0400-\u052f\u0600-\u06ff]", original))
    raw_original = re.findall(r"[\u0400-\u052f\u0600-\u06ff]+|[a-z]+", original)
    if has_script and raw_original and script_lexicon:
        converted = []
        for token in raw_original:
            if re.fullmatch(r"[a-z]+", token):
                converted.append(token)
            else:
                key = _script_word_key(token)
                converted.append(script_lexicon.get(key, token))
        if len(converted) >= 2:
            return tuple(sorted(_prepare_person_words(" ".join(converted))))
    return tuple(sorted(_prepare_person_words(name)))


def _script_word_key(token: str) -> str:
    # Arabic vowel marks and Cyrillic case differences must not affect dictionary lookup.
    return "".join(ch for ch in unicodedata.normalize("NFKD", token.lower()) if not unicodedata.combining(ch) and ch != "ـ")


def build_script_lexicon(entries: list[dict]) -> dict[str, str]:
    """Learn original-script first/family words from parallel names on this list."""
    votes: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for entry in entries:
        script = entry.get("script_name") or ""
        primary = entry.get("primary_name") or ""
        if re.search(r"[\u0400-\u052f\u0600-\u06ff]", primary):
            primary = next((
                alias.get("name", "") for alias in entry.get("aliases", [])
                if alias.get("strength") == "strong" and not re.search(r"[\u0400-\u052f\u0600-\u06ff]", alias.get("name", ""))
            ), "")
        if not script or not primary:
            continue
        st = re.findall(r"[\u0400-\u052f\u0600-\u06ff]+", script)
        lt = _prepare_person_words(primary)
        if len(st) >= 2 and len(lt) >= 2:
            votes[_script_word_key(st[0])][lt[0]] += 1
            votes[_script_word_key(st[-1])][lt[-1]] += 1
            # Cyrillic parallel names are positionally aligned; learn the middle too.
            if len(st) == len(words(primary)):
                for a, b in zip(st, words(primary)):
                    cb = canon_token(b)
                    if b not in PATRONYMICS and cb:
                        votes[_script_word_key(a)][cb] += 1
    return {
        token: max(counts, key=lambda x: (counts[x], x))
        for token, counts in votes.items()
    }


LEGAL_PATTERNS = [
    ("limited", "liability", "company"), ("public", "joint", "stock", "company"),
    ("joint", "stock", "company"), ("free", "zone", "establishment"),
    ("sociedad", "anonima"), ("societe", "anonyme"), ("sendirian", "berhad"),
    ("sdn", "bhd"),
]
LEGAL_WORDS = {
    "llc", "ltd", "limited", "gmbh", "sa", "jsc", "ao", "oao", "pjsc", "fze", "fz", "fzllc",
    "co", "company", "corp", "corporation", "inc", "incorporated", "plc", "ag", "bv", "nv", "se",
    "spa", "sarl", "llp", "lp", "pte", "pty", "berhad",
}

# Same Chinese surname under Pinyin, Wade-Giles, Cantonese, and common Hokkien forms.
CHINESE_GROUPS = [
    ("li", "lee", "lei"), ("zhao", "chao", "chiu", "teo", "teoh", "tio"),
    ("song", "sung"), ("feng", "fung"), ("wang", "wong", "ong"),
    ("cai", "tsai", "choi", "chua", "chai", "choy"), ("shen", "sham", "shum", "sum", "sim"),
    ("du", "tu", "to", "toh"), ("ma", "mah"), ("zhang", "chang", "cheung", "chong"),
    ("dai", "tai", "tay"), ("ye", "yeh", "yip", "yap"), ("he", "ho"),
    ("wu", "woo", "ng", "goh", "go"), ("guo", "kuo", "kwok", "quek", "kwee", "kwek"),
    ("fan", "faan", "hoan"), ("qian", "chien", "chin", "chiam"),
    ("luo", "lo", "law", "loh"), ("peng", "pang", "phang"),
    ("gao", "kao", "ko", "koh"), ("liu", "lau", "liew", "low"),
    ("tang", "tong", "tng", "thng"), ("lin", "lam", "lim"), ("hu", "woo", "oh", "ow"),
    ("liang", "leung", "neo", "nio"), ("yang", "yeung", "yeo", "yong"),
    ("chen", "chen", "chan", "tan"), ("yuan", "yuen", "oan"),
    ("xie", "hsieh", "tse", "sia", "chia"), ("xu", "hsu", "tsui"),
    ("zeng", "tseng", "tsang"), ("pan", "poon", "phua", "phoa"),
    ("sun", "suen", "soon", "sng"), ("zhou", "chou", "chow", "chew", "chiu"),
    ("zhu", "chu", "chue", "choo"), ("huang", "wong", "ooi", "wee"),
    ("lu", "loo", "luk"), ("cao", "tsao", "cho"), ("deng", "teng", "tang", "teh"),
    ("han", "hon", "hang"), ("jiang", "chiang", "kong", "kang"),
]
CHINESE_CANON: dict[str, set[str]] = defaultdict(set)
for group in CHINESE_GROUPS:
    root = group[0]
    for spelling in group:
        CHINESE_CANON[spelling].add(root)


def entity_key(name: str) -> tuple[frozenset[str] | str, ...]:
    toks = words(name)
    if toks and toks[0] == "the":
        toks.pop(0)
    toks = [x for x in toks if x not in {"and"}]
    # Dotted legal forms arrive as separate letters.
    joined: list[str] = []
    i = 0
    while i < len(toks):
        if len(toks[i]) == 1:
            end = i
            while end < len(toks) and len(toks[end]) == 1:
                end += 1
            run = toks[i:end]
            collapsed = "".join(run)
            if collapsed in LEGAL_WORDS:
                joined.append(collapsed); i = end
                continue
        joined.append(toks[i]); i += 1
    toks = joined
    changed = True
    while changed:
        changed = False
        for pat in LEGAL_PATTERNS:
            if len(toks) >= len(pat) and tuple(toks[-len(pat):]) == pat:
                del toks[-len(pat):]
                changed = True
        while toks and toks[-1] in LEGAL_WORDS:
            toks.pop(); changed = True
    result: list[frozenset[str] | str] = []
    for j, token in enumerate(toks):
        if j == 0 and token in CHINESE_CANON:
            result.append(frozenset(CHINESE_CANON[token]))
        else:
            result.append(token)
    return tuple(result)


def entity_keys_equal(a: tuple, b: tuple) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if isinstance(x, frozenset) or isinstance(y, frozenset):
            xs = x if isinstance(x, frozenset) else frozenset((x,))
            ys = y if isinstance(y, frozenset) else frozenset((y,))
            if not xs.intersection(ys):
                return False
        elif x != y:
            return False
    return True


def vessel_key(name: str) -> tuple[str, ...]:
    toks = words(name)
    if not toks:
        return ()
    # M/V and M/T may tokenize as [m,v] or appear as mv/mt.
    if len(toks) >= 2 and toks[:2] in (["m", "v"], ["m", "t"], ["m", "s"], ["s", "s"]):
        toks = toks[2:]
    elif toks[0] in {"mv", "mt", "ms", "ss", "vessel"}:
        toks = toks[1:]
    return tuple(toks)


def weak_alias_key(name: str) -> tuple[str, ...]:
    return tuple(words(name))


def dob_compatible(customer_dob: str, entry_dob: str) -> bool:
    customer_dob = (customer_dob or "").strip()
    entry_dob = (entry_dob or "").strip()
    if not customer_dob or not entry_dob:
        return True
    return entry_dob.startswith(customer_dob)


def full_dob_equal(a: str, b: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", a or "") and a == b)


class Screener:
    def __init__(self, entries: list[dict]):
        self.entries = entries
        self.script_lexicon = build_script_lexicon(entries)
        self.by_id: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self.by_type: dict[str, list[dict]] = defaultdict(list)
        self.prepared: dict[str, list[tuple[object, bool]]] = {}
        for entry in entries:
            for ident in entry.get("ids", []):
                key = ((ident.get("type") or "").strip().lower(), (ident.get("number") or "").strip())
                if key[0] and key[1]:
                    self.by_id[key].append(entry)
            self.by_type[entry.get("type", "")].append(entry)
            names: list[tuple[object, bool]] = []
            strong_names = [entry.get("primary_name", "")]
            if entry.get("script_name") and entry.get("script_name") not in strong_names:
                strong_names.append(entry["script_name"])
            strong_names += [a.get("name", "") for a in entry.get("aliases", []) if a.get("strength") == "strong"]
            if entry.get("type") == "individual":
                names.extend((person_key(n, self.script_lexicon), False) for n in strong_names if n)
                names.extend((weak_alias_key(a.get("name", "")), True) for a in entry.get("aliases", []) if a.get("strength") == "weak")
            elif entry.get("type") == "entity":
                names.extend((entity_key(n), False) for n in strong_names if n)
            elif entry.get("type") == "vessel":
                names.extend((vessel_key(n), False) for n in strong_names if n)
            self.prepared[entry["uid"]] = names

    def screen(self, customer: dict) -> tuple[str, str]:
        id_key = ((customer.get("id_type") or "").strip().lower(), (customer.get("id_number") or "").strip())
        if id_key[0] and id_key[1] and self.by_id.get(id_key):
            cdob = (customer.get("dob") or "").strip()
            ranked_ids = []
            for entry in self.by_id[id_key]:
                edob = (entry.get("dob") or "").strip()
                dob_support = int(bool(cdob and edob and dob_compatible(cdob, edob)))
                ranked_ids.append((dob_support, entry["uid"]))
            best_support = max(x[0] for x in ranked_ids)
            return "MATCH", min(x[1] for x in ranked_ids if x[0] == best_support)

        kind = (customer.get("type") or "").strip().lower()
        name = customer.get("full_name", "")
        if kind == "individual":
            customer_key = person_key(name, self.script_lexicon)
            customer_weak_key = weak_alias_key(name)
        elif kind == "entity":
            customer_key = entity_key(name)
            customer_weak_key = ()
        elif kind == "vessel":
            customer_key = vessel_key(name)
            customer_weak_key = ()
        else:
            return "NO_MATCH", ""

        candidates: list[tuple[int, str]] = []
        cdob = (customer.get("dob") or "").strip()
        for entry in self.by_type.get(kind, []):
            edob = (entry.get("dob") or "").strip()
            if not dob_compatible(cdob, edob):
                continue
            matched = False
            for target_key, is_weak in self.prepared[entry["uid"]]:
                if is_weak:
                    if customer_weak_key == target_key and full_dob_equal(cdob, edob):
                        matched = True
                        break
                elif kind == "entity":
                    if entity_keys_equal(customer_key, target_key):
                        matched = True
                        break
                elif customer_key and customer_key == target_key:
                    matched = True
                    break
            if matched:
                # An actual DOB comparison outranks a name-only candidate.
                dob_support = int(bool(cdob and edob))
                candidates.append((dob_support, entry["uid"]))
        if not candidates:
            return "NO_MATCH", ""
        best_support = max(x[0] for x in candidates)
        uid = min(x[1] for x in candidates if x[0] == best_support)
        return "MATCH", uid


def main() -> None:
    parser = argparse.ArgumentParser(description="Screen customers against a sanctions watchlist")
    parser.add_argument("--watchlist", required=True)
    parser.add_argument("--customers", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    with open(args.watchlist, "r", encoding="utf-8") as handle:
        entries = json.load(handle)
    screener = Screener(entries)
    with open(args.customers, "r", encoding="utf-8-sig", newline="") as source, \
         open(args.out, "w", encoding="utf-8", newline="") as destination:
        reader = csv.DictReader(source)
        writer = csv.DictWriter(destination, fieldnames=["customer_id", "decision", "matched_uid"])
        writer.writeheader()
        for customer in reader:
            decision, uid = screener.screen(customer)
            writer.writerow({"customer_id": customer.get("customer_id", ""), "decision": decision, "matched_uid": uid})


if __name__ == "__main__":
    main()
