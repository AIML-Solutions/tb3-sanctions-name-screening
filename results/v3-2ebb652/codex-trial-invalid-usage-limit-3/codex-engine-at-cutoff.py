#!/usr/bin/env python3
"""Offline sanctions screening under the policy in screening_policy.md.

The matcher is deliberately rule based.  It does not use edit-distance fuzzy
matching: that kind of matching accepts the policy's near-name decoys.  It
normalizes documented transliteration systems into equivalence classes and
then compares the semantic given-name and family-name parts of personal names.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict
from functools import lru_cache


WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
SPECIAL_FOLD = str.maketrans({
    "ı":"i", "İ":"I", "đ":"d", "Đ":"D", "ø":"o", "Ø":"O",
    "ł":"l", "Ł":"L", "ð":"d", "Ð":"D", "þ":"th", "Þ":"Th",
    "æ":"ae", "Æ":"Ae", "œ":"oe", "Œ":"Oe", "ß":"ss",
})


@lru_cache(maxsize=None)
def ascii_fold(text: str) -> str:
    """Lowercase and remove Latin diacritics, retaining non-Latin scripts."""
    text = text.translate(SPECIAL_FOLD)
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()


def words(text: str) -> list[str]:
    return WORD_RE.findall(ascii_fold(text))


def is_latin(text: str) -> bool:
    return any("a" <= ch <= "z" for ch in ascii_fold(text))


def is_cyrillic(text: str) -> bool:
    return any("\u0400" <= ch <= "\u052f" for ch in text)


def is_arabic(text: str) -> bool:
    return any("\u0600" <= ch <= "\u06ff" for ch in text)


def make_map(groups: list[tuple[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for canonical, variants in groups:
        out[canonical] = canonical
        for variant in variants.split():
            out[ascii_fold(variant)] = canonical
    return out


# These are equivalence classes, not approximate spelling rules.  In
# particular Hassan and Hussein, and Hamza and Hamid, remain different.
ARABIC_PERSIAN = make_map([
    ("muhammad", "mohammad mohammed mohamed mohamad mohd muhamad muhamed muhammed mochammad moehamad moehammad mehmet"),
    ("ahmad", "ahmed ahmet achmad achmed"),
    ("abdullah", "abdallah abdollah abdoollah abdulah abdulla"),
    ("abdulaziz", "abdulazez abdulazeez abdolaziz abdelaziz abdelazeez abdoelaziz abduazez"),
    ("abdulrahman", "abdulrahmen abdurrahman abdurrahmen abdolrahman abdolrahmen abdoelrahman abdoelrachman"),
    ("abdulkarim", "abdulkarem abdolkerim abdolkarem abdelkarim abdelkarem abdulkerim"),
    ("rahman", "rahmen rachman"),
    ("hussein", "hussain hussin husain husayn hosein hossein hoesein hoesain hoessein husein huseyin hüseyin"),
    ("hassan", "hasan hasen hassen"),
    ("yusuf", "yousuf yussuf yusef yusof yusoof yussof yussoof joesoef jusuf"),
    ("khalid", "khaled khaleed khalleed khalled chalid cholid halid halit"),
    ("jamal", "jammal djamal dschammal gamal cemal"),
    ("qasim", "kasim kassim kassem qassem qasseem qassim kasım"),
    ("mustafa", "mustafah mostafa moestafa"),
    ("saeed", "saed saeid sayeed said saaed saaid sait"),
    ("hamid", "hamed hammid hammed hammeed hamit"),
    ("hamza", "hamzah"),
    ("salim", "saleem salem sallem sallim salleem selim"),
    ("rashid", "rashed rasheed rasit rasjid rasyid"),
    ("nabil", "nabel nabeel"),
    ("ziad", "zied ziyad zeyad"),
    ("majid", "maged madjid majeed mecit"),
    ("marwan", "marwen marouane mervan"),
    ("adnan", "adnen"),
    ("samir", "sameer sammeer sammir semir"),
    ("samira", "sammira sammirah sameera"),
    ("sami", "sammi"),
    ("bilal", "billal"),
    ("ibrahim", "ibrahem ibraheem"),
    ("tariq", "tarik tarek tareq thariq"),
    ("kamal", "kammal kemal"),
    ("karim", "karem kareem kerim"),
    ("amina", "aminah amena ameena amenah ameenah emine"),
    ("salma", "salmah selma"),
    ("huda", "hudah"),
    ("huda", "houdah"),
    ("aisha", "aishah aichah ayesha ayse aisya aisyah aisjah"),
    ("fatima", "fatimah fatma fatema fatemeh fatemmeh fatimmih fatimih fatemah fateemma"),
    ("zainab", "zaynab zeinab zeynep"),
    ("leila", "layla laylah laila lailah lailla laillah leilla leillah leyla"),
    ("rania", "raniah"),
    ("khadija", "khadeja khadeejah khadijah hatice"),
    ("faisal", "faysal fayssal faissal feisal feysal"),
    ("walid", "waleed wallid velid"),
    ("yasser", "yaser yasir yassir"),
    ("anwar", "anwaar anwarr enver"),
    ("nizar", "nizaar nezar"),
    ("bashar", "bachar basyar"),
    ("hisham", "hisam"),
    ("mahmoud", "mahmut mahmud mahmoed machmoed"),
    ("mariam", "maryam meryem"),
    ("rami", "rammi"),
    ("taha", "tahah"),
    ("talal", "tallal"),
    ("nour", "noor nur"),
    ("omar", "omaar omare omer oemar umar"),
    ("sharif", "sjarif serif sherif"),
    ("dalal", "dallal"),
    ("farhad", "farhed ferhat"),
    ("ismail", "ismayl"),
    ("morteza", "mortezah mortizah murtaza"),
    ("omid", "omed omeed umit"),
    ("kamran", "kamren"),
    ("zahra", "zahrah zehra"),
    ("kaveh", "kavih"),
    ("parviz", "parveez parvez perviz"),
    ("shirin", "sheren shireen chirin"),
    ("ehsan", "ehsen ihsan"),
    ("mohsen", "mohsin muhsin"),
    ("reza", "rezah riza"),
    ("ramin", "ramen rammen rammin rammeen rameen"),
    ("masoud", "massoud masood mesut"),
    ("nasrin", "nasren nasreen nesrin"),
    ("parisa", "paresa paresah pareesa pareesah parissa parissah"),
    ("niloufar", "nilloufar niloofar"),
    ("mahsa", "mahsah"),
    ("javad", "javed gaved djavad djavade cevad"),
    ("bijan", "bijen bigen bidjan"),
    ("mehdi", "mehdy"),
    ("amir", "ameer amer"),
    ("dariush", "daryush"),
    ("sadeghi", "sadighi sadeqi"),
    ("ebrahimi", "ebrahemi ebrahemmi ebraheemmi ibrahimi"),
    ("ghasemi", "ghassemi ghassemmi ghasimi qasemi"),
    ("jafari", "gafari jaafari"),
    ("hosseini", "hoseini hosaini hossaini husseini"),
    ("karimi", "carimi karimmi kareemi karemmi"),
    ("bagheri", "baghiri"),
    ("salehi", "salihi sallihi sallehi"),
    ("rezaei", "rezeai rezaai rezai rezaey"),
    ("mousavi", "moussavi musavi"),
    ("rostami", "rostammi"),
    ("zamani", "zammani zammany"),
    ("rahimi", "rahemi rahemmi raheemi rahimmi"),
    ("shirazi", "sherazi sheerazi"),
    ("tabrizi", "tabrezi tabreezi"),
    ("mohammadi", "mohamadi"),
    ("rahmani", "rahmany"),
    ("kermani", "kermany"),
    ("farahani", "farahanie"),
    ("esfahani", "esfahany"),
    ("mahmoudi", "mahmoudy"),
    ("yazdani", "yazdany"),
    ("haddad", "hadad haded hadded"),
    ("hamdan", "hamden"),
    ("hakim", "hakem hakeem hekim"),
    ("hashimi", "hashemi hasheemi hashemmi hasheemmi haschimi hasjimi hashimmi hashimmy"),
    ("khatib", "khateb khateeb khateebe khatib hatip"),
    ("douri", "duri doury"),
    ("tikriti", "tikreti tikreeti takriti"),
    ("farsi", "farsy"),
    ("masri", "misri"),
    ("zahrani", "zahrany"),
    ("shamsi", "shamsy schamsi"),
    ("sabah", "saba sabaa"),
    ("sayed", "sayid sayed sayyid seyyid syed"),
    ("najjar", "najar nagar"),
    ("jabouri", "gabouri jaburi jabourie jaboury"),
    ("yassin", "yasin yasen yassen yaseen yasseen"),
    ("aziz", "azez azeez"),
    ("saleh", "salih sallih salleh"),
    ("abbas", "abas"),
    ("awad", "awed awade"),
    ("salman", "salmen"),
    ("ghanem", "ghanim"),
    ("darwish", "darwesh darweesh darwech"),
    ("kanaan", "kanaen kanen kanan"),
    ("shahin", "shaheen shahen"),
    ("nasser", "naser nasir nassir"),
    ("mansour", "mansur"),
    ("khoury", "khuri"),
    ("fares", "faris"),
    ("amin", "amen ameen"),
    ("attar", "atar"),
    ("zaidi", "zaydi"),
    ("sultan", "sulten"),
    ("nasrallah", "nasrala nasralah nasrullah"),
    ("bakr", "bakre"),
    ("barakat", "baracat baracate"),
])


RUSSIAN = make_map([
    ("aleksandr", "alexandr alexander aleksander alexandre"),
    ("aleksei", "alexei alexey aleksey alekseiy aleksej"),
    ("andrei", "andrey andrej"),
    ("anatoly", "anatoliy anatolij"),
    ("arkady", "arkadi arkadij"),
    ("artyom", "artem artiom"),
    ("dmitri", "dmitry dmitriy dmitrij"),
    ("ekaterina", "yekaterina jekaterina"),
    ("elena", "yelena jelena"),
    ("yevgeny", "evgeny yevgeniy evgeniy evgeni evgenij jevgenij eugene"),
    ("fedor", "fyodor feodor fjodor fiodor"),
    ("gennady", "gennadiy gennadi gennadij"),
    ("grigory", "grigoriy grigori grigorij"),
    ("kseniya", "ksenia ksenija"),
    ("maksim", "maxim maxime"),
    ("maria", "mariya marija"),
    ("natalia", "nataliya natalya natalija"),
    ("nikolai", "nikolay nikolaiy nikolaij nikolaj"),
    ("oksana", "oxana"),
    ("pavel", "pawel"),
    ("semyon", "semen semion semjon"),
    ("sergei", "sergey sergeiy sergej serguei"),
    ("tatiana", "tatyana tatjana"),
    ("viktoria", "victoria viktoriya viktorya viktorija"),
    ("yuri", "yury yuriy juriy jurij youri"),
    ("yulia", "yuliya julia julija ioulia"),
    ("anastasia", "anastasiya anastasya anastasija"),
    ("lyudmila", "ludmila liudmila ljudmila lioudmila lyoudmila"),
    ("vasily", "vassili vasili wasily"),
    ("vyacheslav", "viatcheslav vyatcheslav vyacheslaff vjaceslav"),
    ("ruslan", "rouslan"),
    ("timur", "timour"),
    ("valery", "valeri valerij"),
    ("mikhail", "michail michel mikhail"),
    ("yelizaveta", "elizaveta ielizaveta yelizaweta"),
    ("zhanna", "janna shanna zanna"),
    ("nadezhda", "nadezda"),
    ("darya", "darja"),
    ("ivan", "iwan"),
    ("stanislav", "stanislaw"),
    ("vladimir", "wladimir"),
    ("vasily", "vasilij"),
    ("darya", "daria daria"),
    ("chaikovsky", "tchaikovsky chaikovskiy chaikovskij cajkovskij cajkovsky chaykovsky"),
    ("zhukov", "zukov zhoukov"),
    ("shevchenko", "sevcenko shevcenko chevchenko"),
    ("shcherbakov", "scherbakov scerbakov shcherbakoff"),
    ("grishin", "grisin"),
    ("shishkin", "siskin"),
    ("chernov", "cernov"),
    ("kravchenko", "kravcenko"),
    ("tkachenko", "tkacenko"),
    ("tsoi", "tsoy tsoiy tzoiy tsoij coj"),
    ("kiselyov", "kiselev kiseliov kiselyev"),
    ("semyonov", "semenov semionov semjonov"),
    ("kozlov", "koslov koslow"),
    ("egorov", "yegorov jegorov"),
    ("fedorov", "fyodorov fedoroff fjodorov"),
    ("kuznetsov", "kuznecov"),
    ("tsvetkov", "cvetkov"),
    ("zaitsev", "zajcev zaytsev"),
    ("zakharov", "zaharov sakharov sacharov"),
    ("andreev", "andreyev andrejev"),
    ("yashin", "jasin"),
    ("yakovlev", "jakovlev"),
    ("sergeyevich", "sergeevich sergejevich"),
    ("aleksandrovich", "alexandrovich aleksandrovic alexandrovic"),
    ("nikolaevich", "nikolayevich nikolajevich"),
    ("mikhailovich", "mihailovich michailovich"),
    ("vladimirovich", "vladimirovic"),
    ("petrovich", "petrovic"),
    ("ivanovich", "ivanovic"),
    ("sergeyevna", "sergeevna sergejevna"),
    ("aleksandrovna", "alexandrovna"),
    ("nikolaevna", "nikolayevna"),
])


WESTERN_SURNAME = make_map([
    ("muller", "mueller"),
    ("schroeder", "schroder"),
    ("fernandez", "fernandes"),
    ("bianchi", "bianci"),
    ("larsen", "larson"),
    ("andersen", "anderson"),
    ("kowalski", "kowalsky"),
    ("nowak", "novak"),
    ("macdonald", "mcdonald"),
    ("lefevre", "fevre"),
    ("vanderberg", "vandenberg"),
    ("smithjones", "smith-jones"),
    ("delacruz", "cruz"),
    ("dasilva", "silva"),
    ("garcia", "garcía"),
    ("hernandez", "hernández"),
    ("rodriguez", "rodríguez"),
    ("sorensen", "sorenson"),
    ("petersen", "pedersen"),
    ("meyer", "mayer meier"),
    ("schmidt", "schmid schmitt"),
    ("olsen", "olson"),
    ("weiss", "weis"),
    ("johansson", "johansen"),
    ("lindqvist", "lindkvist"),
    ("obrien", "o'brien obrien"),
])


WESTERN_GIVEN_GROUPS = [
    {"william", "bill", "billy", "will"},
    {"james", "jim", "jimmy"},
    {"robert", "bob", "bobby", "rob", "robbie"},
    {"katherine", "catherine", "kate", "kathy", "katy", "kit"},
    {"rebecca", "becky", "becca"},
    {"elizabeth", "liz", "beth", "betty"},
    {"elizabeth", "elisabeth"},
    {"frederick", "fred", "freddie"},
    {"christopher", "chris", "kit"},
    {"thomas", "tom", "tommy"},
    {"henry", "hank"},
    {"daniel", "dan", "danny"},
    {"edward", "ed", "eddie"},
    {"jennifer", "jen", "jenny"},
    {"joseph", "joe", "joey"},
    {"nicholas", "nicolas", "nick", "nicky"},
    {"patricia", "pat", "patty"},
    {"margaret", "maggie", "peggy"},
    {"matthew", "matt"},
    {"steven", "stephen", "steve"},
    {"charles", "chuck", "charlie"},
    {"theodore", "theo", "ted", "teddy"},
    {"samuel", "sam", "sammy"},
    {"dorothy", "dot", "dottie"},
    {"jose", "pepe"},
    {"john", "jon", "johnny", "jack"},
    {"peter", "pete"},
    {"alexander", "aleksandr", "alex", "xander", "sandy"},
    {"victoria", "viktoria", "vicky", "tori"},
    {"richard", "rick", "ricky", "dick"},
    {"francisco", "frank", "paco"},
    {"anthony", "tony"},
    {"andrew", "andy", "drew"},
    {"michael", "mike"},
    {"susan", "sue", "susie"},
    {"donald", "don"},
    {"barbara", "barb"},
    {"benjamin", "ben"},
    {"william", "liam"},
]


CHINESE_SYLLABLE = make_map([
    ("xiao", "hsiao"), ("xiang", "hsiang"), ("xin", "hsin"),
    ("xie", "hsieh tse"), ("zhi", "chih"), ("zhang", "chang cheung teo"),
    ("zhou", "chou chow"), ("zhong", "chung"),
    ("jiang", "chiang"), ("jing", "ching"), ("jun", "chun"), ("juan", "chuan"),
    ("jie", "chieh"), ("rui", "juei"), ("xia", "hsia"), ("xue", "hsueh"),
    ("cui", "tsuei"), ("cai", "tsai chua"), ("cao", "tsao"),
    ("zeng", "tseng"), ("gang", "kang"), ("guo", "kuo kwok quek kwek"),
    ("gao", "kao koh ko"), ("gui", "kuei"), ("bao", "pao"), ("bo", "po"),
    ("bin", "pin"), ("qian", "chien chin"), ("dai", "tai"), ("deng", "teng"),
    ("tian", "tien"), ("de", "te"),
    ("rong", "jung"), ("yi", "i"),
    ("chen", "chan tan"), ("lin", "lam lim"), ("wang", "wong ong"),
    ("huang", "hwang"), ("li", "lee"), ("liang", "leung"),
    ("wu", "woo goh ng"), ("liu", "lau"), ("xu", "hsu tsui chui"),
    ("zhao", "chiu"), ("yuan", "yuen"), ("ma", "mah"),
    ("zeng", "tsang"), ("song", "sung"), ("yang", "yeung"),
    ("cai", "choi"), ("zhu", "chu"), ("du", "to"),
    ("peng", "pang"), ("han", "hon"),
    ("hu", "hoo"), ("xu", "sum"),
    ("he", "ho"), ("ye", "yeh yap yip"), ("feng", "fung"),
])


# Chinese surnames occurring in the source cultures plus conventional forms.
CHINESE_SURNAMES = {
    "ai", "an", "bai", "bao", "cai", "cao", "chen", "cheng", "cui", "dai",
    "deng", "fan", "fang", "feng", "fu", "gao", "gong", "gu", "guan", "guo",
    "han", "he", "hong", "hou", "hu", "hua", "huang", "jiang", "jin", "kong",
    "lai", "lan", "lei", "li", "liang", "lin", "liu", "long", "lu", "ma",
    "luo", "mao", "mo", "ou", "pan", "peng", "qian", "qin", "ren", "shen", "shi",
    "song", "su", "sun", "tan", "tang", "tao", "tian", "wan", "wang", "wei",
    "wen", "wu", "xia", "xiao", "xie", "xu", "xue", "yan", "yang", "yao",
    "ye", "yi", "yin", "yuan", "zeng", "zhang", "zhao", "zheng", "zhong",
    "zhou", "zhu", "zhuang",
}


RUSSIAN_FAMILY_ROOTS = {
    "andreev", "belousov", "bondarenko", "bykov", "chaikovsky", "chernov",
    "fedorov", "grishin", "ivanov", "kiselev", "kiselyov", "kovalenko", "kozlov",
    "kravchenko", "kuznetsov", "lebedev", "makarov", "morozov", "nikolaev",
    "novikov", "orlov", "pavlov", "petrov", "popov", "shcherbakov", "shevchenko",
    "shishkin", "smirnov", "sokolov", "semyonov", "stepanov", "tkachenko", "tsoi", "tsvetkov",
    "volkov", "yakovlev", "yashin", "zaitsev", "zhukov",
    "zakharov",
}


PARTICLES = {"al", "el", "an", "ar", "as", "ash", "at", "ad", "az"}
NASAB = {"bin", "ibn", "ben", "b"}


@lru_cache(maxsize=None)
def latin_word(token: str) -> str:
    token = ascii_fold(token).replace("'", "")
    maps = (ARABIC_PERSIAN, RUSSIAN, WESTERN_SURNAME)
    for mapping in maps:
        if token in mapping:
            return mapping[token]
    # Gulf/French renderings often add a final silent e.  Accept it only when
    # removal lands exactly in a declared equivalence class.
    if token.endswith("e") and len(token) > 4:
        shorter = token[:-1]
        for mapping in maps:
            if shorter in mapping:
                return mapping[shorter]
    return token


@lru_cache(maxsize=None)
def strip_attached_article(token: str) -> str:
    """Remove Arabic articles, including sun-letter assimilation, from surnames."""
    token = ascii_fold(token)
    if token in ARABIC_PERSIAN:
        return ARABIC_PERSIAN[token]
    # Ordinary al-/el- forms after punctuation has been removed.
    for prefix in ("al", "el"):
        if token.startswith(prefix) and len(token) > len(prefix) + 2:
            rest = token[len(prefix):]
            if rest in ARABIC_PERSIAN or latin_word(rest) in set(ARABIC_PERSIAN.values()):
                return latin_word(rest)
    # Assimilated Arabic article: an-Najjar, ar-Rashid, ash-Shamsi, etc.
    for prefix in ("an", "ar", "as", "ash", "at", "ad", "az"):
        if token.startswith(prefix) and len(token) > len(prefix) + 2:
            rest = token[len(prefix):]
            if rest and rest[0] * 2 == rest[:2]:
                rest = rest[1:]
            if rest in ARABIC_PERSIAN or latin_word(rest) in set(ARABIC_PERSIAN.values()):
                return latin_word(rest)
    return latin_word(token)


@lru_cache(maxsize=None)
def family_word(token: str) -> str:
    token = strip_attached_article(token)
    token = WESTERN_SURNAME.get(token, token)
    token = RUSSIAN.get(token, token)
    # French, German, Polish, and ISO renderings of Russian surnames.  Generate
    # only candidates that land on an actual Russian family lexeme; this avoids
    # turning general near-spellings into fuzzy matches.
    candidates = {token}
    for _ in range(3):
        for value in tuple(candidates):
            replacements = (
                ("schtch", "shch"), ("chtch", "shch"), ("tsch", "ch"),
                ("tch", "ch"), ("sch", "sh"), ("ch", "sh"),
                ("cz", "ch"), ("sz", "sh"), ("tz", "ts"),
                ("ou", "u"), ("w", "v"),
            )
            for old, new in replacements:
                if old in value:
                    candidates.add(value.replace(old, new))
            if value.startswith("j"):
                candidates.add("zh" + value[1:])
                candidates.add("y" + value[1:])
            if value.startswith("z") and not value.startswith("zh"):
                candidates.add("zh" + value[1:])
            if value.startswith("s") and not value.startswith("sh"):
                candidates.add("sh" + value[1:])
            if value.startswith("c"):
                candidates.add("ts" + value[1:])
                candidates.add("ch" + value[1:])
            if "h" in value and "kh" not in value:
                candidates.add(value.replace("h", "kh"))
            suffixes = (("off", "ov"), ("ow", "ov"), ("eff", "ev"),
                        ("ew", "ev"), ("skij", "sky"), ("skiy", "sky"),
                        ("skaja", "sky"))
            for old, new in suffixes:
                if value.endswith(old):
                    candidates.add(value[:-len(old)] + new)
    for value in sorted(candidates):
        value = RUSSIAN.get(value, value)
        if value in RUSSIAN_FAMILY_ROOTS:
            return value
        if value.endswith("a"):
            masculine = RUSSIAN.get(value[:-1], value[:-1])
            if masculine in RUSSIAN_FAMILY_ROOTS:
                return masculine
        if value.endswith("skaya"):
            masculine = RUSSIAN.get(value[:-5] + "sky", value[:-5] + "sky")
            if masculine in RUSSIAN_FAMILY_ROOTS:
                return masculine
    # Russian feminine surnames correspond to their masculine form.  Limit the
    # operation to known Russian families so that arbitrary final 'a' is not lost.
    if token.endswith("a"):
        masculine = token[:-1]
        masculine = RUSSIAN.get(masculine, masculine)
        if masculine in RUSSIAN_FAMILY_ROOTS:
            token = masculine
        elif masculine.endswith("sk") and masculine + "y" in RUSSIAN_FAMILY_ROOTS:
            token = masculine + "y"
    # -skaya is the feminine of -sky.
    if token.endswith("skaya"):
        candidate = token[:-5] + "sky"
        candidate = RUSSIAN.get(candidate, candidate)
        if candidate in RUSSIAN_FAMILY_ROOTS:
            token = candidate
    return token


def compound_family_at_end(toks: list[str]) -> str | None:
    """Canonicalize the compound Western surnames covered by the policy."""
    if len(toks) >= 3 and toks[-3:] in (["van", "der", "berg"], ["van", "den", "berg"]):
        return "vanderberg"
    if len(toks) >= 3 and toks[-3:] == ["de", "la", "cruz"]:
        return "delacruz"
    if len(toks) >= 2 and toks[-2:] == ["da", "silva"]:
        return "dasilva"
    if len(toks) >= 2 and toks[-2:] == ["le", "fevre"]:
        return "lefevre"
    if len(toks) >= 2 and toks[-2:] == ["smith", "jones"]:
        return "smithjones"
    if len(toks) >= 2 and toks[-2:] in (["o", "brien"], ["mac", "donald"], ["mc", "donald"]):
        return "obrien" if toks[-2:] == ["o", "brien"] else "macdonald"
    return None


def reversed_compound_family(toks: list[str]) -> str | None:
    """Recover compounds after displays like ``Berg, James van der``."""
    if len(toks) >= 4 and toks[0] == "berg" and toks[-2:] in (["van", "der"], ["van", "den"]):
        return "vanderberg"
    if len(toks) >= 3 and toks[0] == "cruz" and toks[-2:] == ["de", "la"]:
        return "delacruz"
    if len(toks) >= 3 and toks[0] == "silva" and toks[-1] == "da":
        return "dasilva"
    if len(toks) >= 3 and toks[0] == "fevre" and toks[-1] == "le":
        return "lefevre"
    if len(toks) >= 3 and toks[0] == "jones" and toks[-1] == "smith":
        return "smithjones"
    return None


COMPOUND_FAMILY_PREFIXES = [
    (("van", "der", "berg"), "vanderberg"),
    (("van", "den", "berg"), "vanderberg"),
    (("de", "la", "cruz"), "delacruz"),
    (("smith", "jones"), "smithjones"),
    (("mac", "donald"), "macdonald"),
    (("mc", "donald"), "macdonald"),
    (("da", "silva"), "dasilva"),
    (("le", "fevre"), "lefevre"),
    (("o", "brien"), "obrien"),
]


def leading_compound_family(toks: list[str]) -> tuple[str, int] | None:
    for prefix, canonical in COMPOUND_FAMILY_PREFIXES:
        if tuple(toks[:len(prefix)]) == prefix:
            return canonical, len(prefix)
    return None


def given_equiv(a: str, b: str) -> bool:
    a, b = latin_word(a), latin_word(b)
    if a == b:
        return True
    return any(a in group and b in group for group in WESTERN_GIVEN_GROUPS)


def given_variants(token: str) -> set[str]:
    token = latin_word(token)
    result = {token}
    for group in WESTERN_GIVEN_GROUPS:
        if token in group:
            result.update(group)
    return result


CYR_MAP = str.maketrans({
    "а":"a", "б":"b", "в":"v", "г":"g", "д":"d", "е":"e", "ё":"yo",
    "ж":"zh", "з":"z", "и":"i", "й":"y", "к":"k", "л":"l", "м":"m",
    "н":"n", "о":"o", "п":"p", "р":"r", "с":"s", "т":"t", "у":"u",
    "ф":"f", "х":"kh", "ц":"ts", "ч":"ch", "ш":"sh", "щ":"shch",
    "ы":"y", "э":"e", "ю":"yu", "я":"ya", "ь":"", "ъ":"",
    "і":"i", "ї":"yi", "є":"ye", "ґ":"g",
})


ARAB_MAP = str.maketrans({
    "ا":"a", "أ":"a", "إ":"i", "آ":"a", "ب":"b", "ت":"t", "ث":"th",
    "ج":"j", "ح":"h", "خ":"kh", "د":"d", "ذ":"dh", "ر":"r", "ز":"z",
    "س":"s", "ش":"sh", "ص":"s", "ض":"d", "ط":"t", "ظ":"z", "ع":"",
    "غ":"gh", "ف":"f", "ق":"q", "ك":"k", "ک":"k", "گ":"g", "ل":"l",
    "م":"m", "ن":"n", "ه":"h", "ة":"a", "و":"w", "ؤ":"w", "ي":"y",
    "ى":"a", "ی":"y", "ئ":"y", "ء":"", "چ":"ch", "پ":"p", "ژ":"zh",
    "ۀ":"h", "‌":"",
})


def transliterate_script_word(token: str) -> str:
    if is_cyrillic(token):
        return latin_word(ascii_fold(token).translate(CYR_MAP))
    if is_arabic(token):
        return latin_word(ascii_fold(token).translate(ARAB_MAP))
    return latin_word(token)


def collapse_compound_given(toks: list[str]) -> list[str]:
    """Collapse Abd + (article) + divine name to one semantic given name."""
    if not toks:
        return toks
    out = list(toks)
    if out[0] in {"abd", "abdel", "abdul", "abdol", "abdoel"}:
        pos = 1
        if pos < len(out) and out[pos] in PARTICLES:
            pos += 1
        if pos < len(out):
            second = latin_word(out[pos])
            if second in {"aziz", "rahman", "karim", "karem", "allah"}:
                suffix = {"karem":"karim"}.get(second, second)
                out = [latin_word("abdul" + suffix)] + out[pos + 1:]
    return out


def normalized_person_tokens(name: str) -> list[str]:
    toks = words(name)
    result: list[str] = []
    for token in toks:
        if len(token) == 1 and is_latin(token):
            continue
        value = transliterate_script_word(token) if not is_latin(token) else latin_word(token)
        if value in PARTICLES:
            continue
        result.append(value)
    return collapse_compound_given(result)


def endpoint_pairs(name: str, script_given: dict[str, set[str]] | None = None,
                   script_family: dict[str, set[str]] | None = None,
                   script_given_phrase: dict[tuple[str, ...], set[str]] | None = None
                   ) -> set[tuple[str, str]]:
    """Return plausible (given, family) pairs for a non-Chinese personal name."""
    raw = words(name)
    toks = normalized_person_tokens(name)
    if len(toks) < 2:
        return set()
    given_values = {latin_word(toks[0])}
    compound_family = compound_family_at_end(toks)
    if not compound_family:
        compound_family = compound_family_at_end([latin_word(t) for t in raw])
    family_values = {compound_family} if compound_family else {family_word(toks[-1])}
    if raw and raw[-1] == "jasin":
        family_values.update({"yassin", "yashin"})
    compound_script_given = False
    if raw and script_given_phrase is not None:
        for width in (3, 2):
            key = tuple(raw[:width])
            if key in script_given_phrase:
                given_values.update(script_given_phrase[key])
                compound_script_given = True
    if raw and not compound_script_given and script_given is not None and raw[0] in script_given:
        given_values.update(script_given[raw[0]])
    if raw and raw[0] == "jasin":
        given_values.add("yassin")
    if raw and script_family is not None and raw[-1] in script_family:
        family_values.update(script_family[raw[-1]])
    pairs = {(g, f) for g in given_values for f in family_values}
    # A two-token display is ambiguous in order.  In longer reversed displays
    # the given name is the second token (handled with the learned family
    # vocabulary in Engine._personal_pairs), not the final patronymic/nasab.
    if len(toks) == 2:
        reverse_given = {latin_word(toks[-1])}
        reverse_family = {family_word(toks[0])}
        if raw and raw[0] == "jasin":
            reverse_family.update({"yassin", "yashin"})
        if raw and script_given is not None and raw[-1] in script_given:
            reverse_given.update(script_given[raw[-1]])
        if raw and script_family is not None and raw[0] in script_family:
            reverse_family.update(script_family[raw[0]])
        pairs.update((g, f) for g in reverse_given for f in reverse_family)
    return pairs


@lru_cache(maxsize=None)
def chinese_syllable(token: str) -> str:
    token = ascii_fold(token)
    if token in CHINESE_SYLLABLE:
        return CHINESE_SYLLABLE[token]
    if token.startswith("pin") and not token.startswith("ping"):
        token = "bin" + token[3:]
    # Normalize Wade-Giles pieces inside joined given names.  Only nontrivial
    # multi-letter alternatives are replaced, so ordinary pinyin is untouched.
    joinable = {
        "hsia", "hsiao", "hsiang", "hsin", "hsieh", "chih", "chiang", "ching",
        "chun", "chuan", "chieh", "tsuei", "tsai", "tsao", "tseng",
        "kuei", "kuo", "pao", "jung",
    }
    rewrites = [(variant, canonical) for variant, canonical in CHINESE_SYLLABLE.items()
                if variant in joinable]
    for variant, canonical in sorted(rewrites, key=lambda item: len(item[0]), reverse=True):
        token = token.replace(variant, canonical)
    return token


def chinese_given_options(token: str) -> set[str]:
    token = ascii_fold(token)
    # Chien is Wade-Giles chien (modern jian) as a given-name syllable, but is
    # ch'ien/Qian when it occupies the surname position.
    special = {"chien": {"jian", "qian"}, "chiang": {"jiang", "qiang"},
               "chin": {"jin", "qin"}}
    if token in special:
        return special[token]
    return {chinese_syllable(token)}


def chinese_given_forms(tokens: list[str]) -> set[str]:
    forms = {""}
    for token in tokens:
        forms = {prefix + value for prefix in forms for value in chinese_given_options(token)}
    return forms


def chinese_pairs(name: str) -> set[tuple[str, str]]:
    raw = [t for t in words(name) if len(t) > 1 or ascii_fold(t) == "i"]
    if len(raw) < 2 or any(not is_latin(t) for t in raw):
        return set()
    pairs: set[tuple[str, str]] = set()
    # Only endpoints that are plausible surnames are used.  Concatenating the
    # remainder handles Xiao Ming/Xiaoming and hyphen/space variation.
    first_family = chinese_syllable(raw[0])
    last_family = chinese_syllable(raw[-1])
    if first_family in CHINESE_SURNAMES:
        pairs.update((given, first_family) for given in chinese_given_forms(raw[1:]))
    if last_family in CHINESE_SURNAMES:
        pairs.update((given, last_family) for given in chinese_given_forms(raw[:-1]))
    return pairs


def basic_name(name: str) -> str:
    return " ".join(words(name))


LEGAL_SUFFIXES = [
    ("public", "joint", "stock", "company"),
    ("limited", "liability", "company"), ("joint", "stock", "company"),
    ("free", "zone", "establishment"), ("sociedad", "anonima"),
    ("societe", "anonyme"), ("public", "limited", "company"),
    ("private", "limited"), ("proprietary", "limited"),
    ("pte", "ltd"), ("pty", "ltd"), ("sdn", "bhd"),
    ("l", "l", "c"), ("g", "m", "b", "h"), ("s", "a"),
    ("s", "a", "r", "l"), ("s", "p", "a"), ("s", "r", "l"),
    ("w", "l", "l"), ("a", "s"), ("k", "k"),
    ("f", "z", "e"), ("f", "z", "llc"),
    ("llc",), ("ltd",), ("limited",), ("sa",), ("gmbh",), ("jsc",),
    ("ao",), ("oao",), ("pao",), ("pjsc",), ("co",), ("company",),
    ("corp",), ("corporation",), ("inc",), ("incorporated",), ("fze",),
    ("fz", "llc"), ("plc",), ("ag",), ("nv",), ("bv",), ("lp",), ("llp",),
    ("sarl",), ("spa",), ("srl",), ("wll",), ("as",), ("kk",),
    ("berhad",), ("bhd",),
]
LEGAL_SUFFIXES.sort(key=len, reverse=True)


def entity_key(name: str) -> str:
    toks = words(name)
    if toks and toks[0] == "the":
        toks.pop(0)
    toks = [t for t in toks if t not in {"and"}]
    changed = True
    while changed and toks:
        changed = False
        for suffix in LEGAL_SUFFIXES:
            if len(toks) >= len(suffix) and tuple(toks[-len(suffix):]) == suffix:
                del toks[-len(suffix):]
                changed = True
                break
    return "".join(toks)


VESSEL_PREFIXES = [
    ("motor", "vessel"), ("motor", "tanker"), ("m", "v"), ("m", "t"),
    ("m", "s"), ("s", "s"), ("mv",), ("mt",), ("ms",), ("ss",), ("vessel",),
]


def vessel_key(name: str) -> str:
    toks = words(name)
    for prefix in VESSEL_PREFIXES:
        if tuple(toks[:len(prefix)]) == prefix:
            toks = toks[len(prefix):]
            break
    return "".join(toks)


def dob_compatible(customer: str, entry: str) -> bool:
    if not customer or not entry:
        return True
    # A partial value is information about the corresponding prefix.  Entry
    # dates are normally full/year and customer dates full/year-month/year.
    n = min(len(customer), len(entry))
    return customer[:n] == entry[:n]


def dob_support(customer: str, entry: str) -> bool:
    return bool(customer and entry and dob_compatible(customer, entry))


class Engine:
    def __init__(self, entries: list[dict]):
        self.entries = entries
        self.by_uid = {e["uid"]: e for e in entries}
        self.id_index: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self.entity_index: dict[str, set[str]] = defaultdict(set)
        self.vessel_index: dict[str, set[str]] = defaultdict(set)
        self.person_index: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.chinese_index: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.weak_index: dict[str, set[str]] = defaultdict(set)
        self.script_given: dict[str, set[str]] = defaultdict(set)
        self.script_family: dict[str, set[str]] = defaultdict(set)
        self.script_given_phrase: dict[tuple[str, ...], set[str]] = defaultdict(set)
        self._learn_script_words()
        self.known_families: set[str] = set()
        self._learn_families()
        self._index()

    @staticmethod
    def latin_sources(entry: dict) -> list[str]:
        sources: list[str] = []
        if is_latin(entry.get("primary_name", "")):
            sources.append(entry["primary_name"])
        sources.extend(a["name"] for a in entry.get("aliases", [])
                       if a.get("strength") == "strong" and is_latin(a.get("name", "")))
        return sources

    def _learn_script_words(self) -> None:
        """Learn script-token meanings from bilingual entries in this watchlist."""
        for entry in self.entries:
            script = entry.get("script_name") or ""
            st = words(script)
            if len(st) < 2:
                continue
            for source in self.latin_sources(entry):
                lt = normalized_person_tokens(source)
                if len(lt) < 2:
                    continue
                # Watchlist bilingual names are given-first.  Aliases that put a
                # known Chinese surname first are irrelevant here (Chinese has no
                # script_name in this data schema).
                self.script_given[st[0]].add(latin_word(lt[0]))
                self.script_family[st[-1]].add(family_word(lt[-1]))
                if st[0] == "عبد" and len(st) >= 2:
                    self.script_given_phrase[tuple(st[:2])].add(latin_word(lt[0]))

        # A token may appear only in an original-script feminine Russian name.
        # Deterministic Cyrillic transliteration supplies a safe fallback.
        for entry in self.entries:
            script = entry.get("script_name") or ""
            st = words(script)
            if len(st) >= 2 and is_cyrillic(script):
                self.script_given[st[0]].add(latin_word(st[0].translate(CYR_MAP)))
                self.script_family[st[-1]].add(family_word(st[-1].translate(CYR_MAP)))

    def _learn_families(self) -> None:
        """Collect watchlist family vocabulary for unambiguous reversed names."""
        for entry in self.entries:
            if entry.get("type") != "individual":
                continue
            primary = entry.get("primary_name", "")
            pt = normalized_person_tokens(primary)
            if len(pt) >= 2 and is_latin(primary):
                self.known_families.add(family_word(pt[-1]))
            script = entry.get("script_name") or ""
            st = words(script)
            if st:
                self.known_families.update(self.script_family.get(st[-1], ()))
            for source in self.latin_sources(entry):
                lt = normalized_person_tokens(source)
                if len(lt) >= 2:
                    self.known_families.add(family_word(lt[-1]))

    def _personal_pairs(self, name: str) -> set[tuple[str, str]]:
        cpairs = chinese_pairs(name)
        meaningful = [t for t in words(name) if len(t) > 1 or ascii_fold(t) == "i"]
        # Three-or-more-token Chinese names need all given-name syllables;
        # endpoint matching would incorrectly turn Lan Jing Hu into Lan Hu.
        if cpairs and len(meaningful) >= 3:
            pairs = set(cpairs)
        else:
            pairs = endpoint_pairs(name, self.script_given, self.script_family,
                                   self.script_given_phrase)
            pairs.update(cpairs)
        toks = normalized_person_tokens(name)
        if len(toks) >= 2 and family_word(toks[0]) in self.known_families:
            reversed_tail = collapse_compound_given(toks[1:])
            reversed_family = reversed_compound_family(toks) or family_word(toks[0])
            pairs.add((latin_word(reversed_tail[0]), reversed_family))
            raw = words(name)
            if raw and raw[0] == "jasin":
                pairs.add((latin_word(reversed_tail[0]), "yassin"))

        # Preserve a whole compound surname when it is the leading comma
        # segment ("Van der Berg, Matthew") or the leading words without a
        # comma.  WORD_RE intentionally exposes apostrophe compounds as O Brien.
        raw_latin = [latin_word(t) for t in words(name)]
        leading = leading_compound_family(raw_latin)
        if leading:
            family, width = leading
            remainder = normalized_person_tokens(" ".join(raw_latin[width:]))
            if remainder:
                given = collapse_compound_given(remainder)[0]
                pairs.add((latin_word(given), family))
        if "," in name:
            left, right = name.split(",", 1)
            left_raw = [latin_word(t) for t in words(left)]
            left_norm = normalized_person_tokens(left)
            right_norm = normalized_person_tokens(right)
            if left_norm and right_norm:
                leading_left = leading_compound_family(left_raw)
                family = leading_left[0] if leading_left else family_word(left_norm[-1])
                given = collapse_compound_given(right_norm)[0]
                pairs.add((latin_word(given), family))
        expanded: set[tuple[str, str]] = set()
        for given, family in pairs:
            expanded.update((variant, family) for variant in given_variants(given))
        return expanded

    def _index(self) -> None:
        for entry in self.entries:
            uid = entry["uid"]
            for ident in entry.get("ids", []):
                key = (ident.get("type", "").strip().casefold(), ident.get("number", "").strip().casefold())
                if key[0] and key[1]:
                    self.id_index[key].append(entry)

            names = [entry.get("primary_name", "")]
            script = entry.get("script_name") or ""
            if script and script not in names:
                names.append(script)
            names.extend(a["name"] for a in entry.get("aliases", []) if a.get("strength") == "strong")

            if entry.get("type") == "entity":
                for name in names:
                    key = entity_key(name)
                    if key:
                        self.entity_index[key].add(uid)
            elif entry.get("type") == "vessel":
                for name in names:
                    key = vessel_key(name)
                    if key:
                        self.vessel_index[key].add(uid)
            else:
                for name in names:
                    for pair in self._personal_pairs(name):
                        self.person_index[pair].add(uid)
                        if pair[1] in CHINESE_SURNAMES:
                            self.chinese_index[pair].add(uid)

            for alias in entry.get("aliases", []):
                if alias.get("strength") == "weak":
                    self.weak_index[basic_name(alias.get("name", ""))].add(uid)

    def screen(self, customer: dict) -> tuple[str, str]:
        id_type = customer.get("id_type", "").strip().casefold()
        id_number = customer.get("id_number", "").strip().casefold()
        customer_dob = customer.get("dob", "").strip()
        if id_type and id_number:
            hits = self.id_index.get((id_type, id_number), [])
            if hits:
                dated = [e for e in hits if dob_support(customer_dob, e.get("dob", ""))]
                choices = dated if dated else hits
                return "MATCH", min(e["uid"] for e in choices)

        name = customer.get("full_name", "")
        ctype = customer.get("type", "").strip().casefold()
        candidate_uids: set[str] = set()
        if ctype == "entity":
            candidate_uids.update(self.entity_index.get(entity_key(name), ()))
        elif ctype == "vessel":
            candidate_uids.update(self.vessel_index.get(vessel_key(name), ()))
        else:
            for pair in self._personal_pairs(name):
                candidate_uids.update(self.person_index.get(pair, ()))

        valid = [self.by_uid[uid] for uid in candidate_uids
                 if dob_compatible(customer_dob, self.by_uid[uid].get("dob", ""))]

        # Weak aliases require literal normalized equality and identical full DOB.
        if len(customer_dob) == 10:
            for uid in self.weak_index.get(basic_name(name), ()):
                entry = self.by_uid[uid]
                if entry.get("type") == ctype and entry.get("dob", "") == customer_dob:
                    valid.append(entry)

        if not valid:
            return "NO_MATCH", ""

        # De-duplicate and apply the mandated tie break: DOB support, then UID.
        unique = {e["uid"]: e for e in valid}
        supported = [e for e in unique.values() if dob_support(customer_dob, e.get("dob", ""))]
        choices = supported if supported else list(unique.values())
        return "MATCH", min(e["uid"] for e in choices)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Screen customers against a consolidated watchlist")
    parser.add_argument("--watchlist", required=True)
    parser.add_argument("--customers", required=True)
    parser.add_argument("--out", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    with open(args.watchlist, "r", encoding="utf-8") as handle:
        entries = json.load(handle)
    engine = Engine(entries)
    with open(args.customers, "r", encoding="utf-8-sig", newline="") as source, \
         open(args.out, "w", encoding="utf-8", newline="") as target:
        reader = csv.DictReader(source)
        writer = csv.DictWriter(target, fieldnames=["customer_id", "decision", "matched_uid"])
        writer.writeheader()
        for customer in reader:
            decision, uid = engine.screen(customer)
            writer.writerow({"customer_id": customer.get("customer_id", ""),
                             "decision": decision, "matched_uid": uid})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
