#!/usr/bin/env python3
"""Deterministic data generator for the sanctions-name-screening task.

Produces:
  tasks/sanctions-name-screening/environment/data/watchlist.json
  tasks/sanctions-name-screening/environment/data/customers.csv
  tasks/sanctions-name-screening/environment/data/dev/customers_dev.csv
  tasks/sanctions-name-screening/environment/data/dev/labels_dev.csv
  tasks/sanctions-name-screening/tests/data/labels.csv          (hidden truth)

Everything is synthetic. Name pools are modelled on real transliteration
practice (Arabic, Persian, Russian, Chinese, Western) and sanctions-list
conventions (strong/weak aliases, partial DOBs, identifiers, vessels,
legal-entity suffixes). The generator is the single source of truth for the
variation classes described in the screening policy.
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "tasks" / "sanctions-name-screening"
ENV = TASK / "environment" / "data"
TESTS = TASK / "tests" / "data"

SEED_HIDDEN = 20260909
SEED_DEV = 7

# --------------------------------------------------------------------------- name pools
# (canonical Latin, original script, [Latin variants])
ARABIC_GIVEN = [
    ("Muhammad", "محمد", ["Mohammed", "Mohamed", "Mohammad", "Muhamad", "Mohamad"]),
    ("Ahmad", "أحمد", ["Ahmed", "Achmed", "Ahmet"]),
    ("Abdullah", "عبد الله", ["Abdallah", "Abd Allah", "Abdulla", "Abdellah"]),
    ("Abdul Rahman", "عبد الرحمن", ["Abdurrahman", "Abd al-Rahman", "Abdel Rahman", "Abdulrahman"]),
    ("Ali", "علي", ["Aly", "Alee"]),
    ("Hassan", "حسن", ["Hasan", "Hassane"]),
    ("Hussein", "حسين", ["Husain", "Hussain", "Husayn", "Hussien"]),
    ("Khalid", "خالد", ["Khaled", "Halid"]),
    ("Omar", "عمر", ["Umar", "Omer", "Oumar"]),
    ("Yusuf", "يوسف", ["Youssef", "Yousef", "Yusef", "Yousuf"]),
    ("Ibrahim", "إبراهيم", ["Ebrahim", "Ibraheem", "Brahim"]),
    ("Mustafa", "مصطفى", ["Mostafa", "Moustafa", "Mustapha"]),
    ("Tariq", "طارق", ["Tarek", "Tareq", "Tarik"]),
    ("Saeed", "سعيد", ["Said", "Sa'id", "Saeid", "Sayid"]),
    ("Fatima", "فاطمة", ["Fatimah", "Fatma", "Fathima"]),
    ("Aisha", "عائشة", ["Aysha", "Ayesha", "Aicha"]),
    ("Layla", "ليلى", ["Leila", "Laila", "Leyla"]),
    ("Mahmoud", "محمود", ["Mahmud", "Mahmood"]),
    ("Jamal", "جمال", ["Gamal", "Jamaal"]),
    ("Walid", "وليد", ["Waleed", "Oualid"]),
]
ARABIC_SURNAME = [
    ("al-Farsi", "الفارسي", ["Farsi", "El Farsi", "Alfarsi", "Al Farsi"]),
    ("al-Masri", "المصري", ["Masri", "Elmasry", "El-Masri", "Al Masry"]),
    ("al-Hashimi", "الهاشمي", ["Hashemi", "Hashimi", "Al Hashemi"]),
    ("al-Sayed", "السيد", ["Elsayed", "Sayed", "El Sayed", "Al Sayyid"]),
    ("Haddad", "حداد", ["Hadad", "Haddade"]),
    ("Nasser", "ناصر", ["Nasir", "Naser", "Nacer"]),
    ("Saleh", "صالح", ["Salah", "Saleh"]),
    ("al-Rashid", "الرشيد", ["Rashid", "Rasheed", "Al Rashed", "Arrashid"]),
    ("Mansour", "منصور", ["Mansur", "Mansoor", "Mansour"]),
    ("Qasim", "قاسم", ["Kassem", "Qassem", "Kasim", "Qasem"]),
    ("Zaidi", "زيدي", ["Zaydi", "Zeidi"]),
    ("al-Amin", "الأمين", ["Amin", "El Amin", "Alamin"]),
    ("Barakat", "بركات", ["Barakat", "Barkat"]),
    ("Shahin", "شاهين", ["Shaheen", "Chahine"]),
]
PERSIAN_GIVEN = [
    ("Reza", "رضا", ["Reza", "Rida"]),
    ("Hossein", "حسین", ["Hosein", "Hossain", "Hoseyn"]),
    ("Mehdi", "مهدی", ["Mahdi", "Mehdy"]),
    ("Amir", "امیر", ["Ameer", "Amir"]),
    ("Javad", "جواد", ["Jawad", "Djavad"]),
    ("Ehsan", "احسان", ["Ihsan", "Ehsaan"]),
    ("Farhad", "فرهاد", ["Farhaad"]),
    ("Nasrin", "نسرین", ["Nasreen", "Nassrin"]),
    ("Maryam", "مریم", ["Mariam", "Meryem"]),
    ("Kaveh", "کاوه", ["Kave", "Kaveh"]),
    ("Shirin", "شیرین", ["Shireen", "Chirine"]),
    ("Babak", "بابک", ["Babac"]),
]
PERSIAN_SURNAME = [
    ("Ahmadi", "احمدی", ["Ahmady", "Ahmadee"]),
    ("Mohammadi", "محمدی", ["Mohamadi", "Muhammadi"]),
    ("Hosseini", "حسینی", ["Hoseini", "Husseini", "Hosseiny"]),
    ("Karimi", "کریمی", ["Karimy", "Kareemi"]),
    ("Rezaei", "رضایی", ["Rezaee", "Rezai", "Rezaie"]),
    ("Moradi", "مرادی", ["Muradi", "Morady"]),
    ("Tehrani", "تهرانی", ["Teherani", "Tehrany"]),
    ("Esfahani", "اصفهانی", ["Isfahani", "Esfahany"]),
    ("Sadeghi", "صادقی", ["Sadeqi", "Sadegi"]),
    ("Jafari", "جعفری", ["Jafary", "Djafari"]),
]
RUSSIAN_GIVEN_M = [
    ("Sergei", "Сергей", ["Sergey", "Serguei", "Sergej"]),
    ("Aleksandr", "Александр", ["Alexander", "Alexandr", "Aleksander"]),
    ("Dmitri", "Дмитрий", ["Dmitry", "Dmitriy", "Dimitri"]),
    ("Yevgeny", "Евгений", ["Evgeny", "Evgeni", "Evgeniy", "Eugene"]),
    ("Vladimir", "Владимир", ["Wladimir", "Volodymyr"]),
    ("Mikhail", "Михаил", ["Michail", "Mihail", "Mikhael"]),
    ("Nikolai", "Николай", ["Nikolay", "Nicolai", "Nikolaj"]),
    ("Yuri", "Юрий", ["Yury", "Iurii", "Youri", "Jurij"]),
    ("Igor", "Игорь", ["Igor", "Ihor"]),
    ("Andrei", "Андрей", ["Andrey", "Andrej", "Andriy"]),
    ("Pavel", "Павел", ["Pavel", "Paul"]),
    ("Viktor", "Виктор", ["Victor", "Viktor"]),
]
RUSSIAN_GIVEN_F = [
    ("Olga", "Ольга", ["Olha", "Olga"]),
    ("Natalia", "Наталья", ["Natalya", "Nataliya", "Natasha"]),
    ("Elena", "Елена", ["Yelena", "Helena"]),
    ("Svetlana", "Светлана", ["Svitlana", "Swetlana"]),
    ("Tatiana", "Татьяна", ["Tatyana", "Tatjana"]),
    ("Irina", "Ирина", ["Iryna", "Irena"]),
]
RUSSIAN_SURNAME = [
    ("Ivanov", "Иванов", ["Ivanoff", "Iwanow"]),
    ("Petrov", "Петров", ["Petroff", "Petrow"]),
    ("Kuznetsov", "Кузнецов", ["Kuznetsoff", "Kusnezow"]),
    ("Smirnov", "Смирнов", ["Smirnoff"]),
    ("Volkov", "Волков", ["Volkoff", "Wolkow"]),
    ("Sokolov", "Соколов", ["Sokoloff"]),
    ("Fedorov", "Фёдоров", ["Fyodorov", "Feodorov", "Fedoroff"]),
    ("Kozlov", "Козлов", ["Kozloff"]),
    ("Yakovlev", "Яковлев", ["Iakovlev", "Jakowlew"]),
    ("Zaitsev", "Зайцев", ["Zaytsev", "Zaicev"]),
    ("Shevchenko", "Шевченко", ["Chevtchenko", "Schewtschenko"]),
    ("Tkachenko", "Ткаченко", ["Tkatchenko"]),
]
RUSSIAN_PATRONYMIC_M = [("Petrovich", "Петрович"), ("Ivanovich", "Иванович"), ("Sergeyevich", "Сергеевич"),
                        ("Nikolaevich", "Николаевич"), ("Aleksandrovich", "Александрович")]
RUSSIAN_PATRONYMIC_F = [("Petrovna", "Петровна"), ("Ivanovna", "Ивановна"), ("Sergeyevna", "Сергеевна"),
                        ("Nikolaevna", "Николаевна")]
CHINESE_GIVEN = [("Wei", ["Wei"]), ("Jun", ["Jun", "Chun"]), ("Ming", ["Ming"]), ("Hua", ["Hua"]),
                 ("Lei", ["Lei"]), ("Yan", ["Yan", "Yen"]), ("Xiaoming", ["Xiao Ming", "Xiao-Ming", "Hsiao-Ming"]),
                 ("Jianguo", ["Jian Guo", "Jian-Guo", "Chien-Kuo"]), ("Xiaojun", ["Xiao Jun", "Hsiao-Chun"]),
                 ("Zhiqiang", ["Zhi Qiang", "Chih-Chiang"]), ("Feng", ["Feng", "Fung"]), ("Ling", ["Ling"]),
                 ("Yong", ["Yong", "Yung"]), ("Tao", ["Tao"]), ("Xiang", ["Xiang", "Hsiang"]), ("Bo", ["Bo", "Po"]),
                 ("Qiang", ["Qiang", "Chiang"]), ("Ping", ["Ping"]), ("Guoqiang", ["Guo Qiang", "Kuo-Chiang"]),
                 ("Meiling", ["Mei Ling", "Mei-Ling"])]
CHINESE_SURNAME = [("Zhang", ["Chang"]), ("Wang", ["Wong"]), ("Li", ["Lee"]), ("Liu", ["Lau", "Liou"]),
                   ("Chen", ["Chan", "Tchen"]), ("Yang", ["Yeung"]), ("Huang", ["Hwang"]),
                   ("Zhao", ["Chao"]), ("Zhou", ["Chou", "Chow"]), ("Wu", ["Ng", "Woo"]), ("Xu", ["Hsu"]),
                   ("Sun", ["Suen"]), ("Ma", ["Mah"]), ("Zhu", ["Chu"]), ("Hu", ["Hoo"]), ("Guo", ["Kuo", "Kwok"]),
                   ("Lin", ["Lam"]), ("Gao", ["Kao"]), ("Luo", ["Lo"]), ("Cai", ["Tsai", "Choi"])]
WESTERN_GIVEN = [("William", ["Bill", "Will", "Billy"]), ("Robert", ["Bob", "Rob", "Bobby"]),
                 ("Alexander", ["Alex", "Xander"]), ("Katherine", ["Kate", "Catherine", "Kathy"]),
                 ("John", ["Jon", "Johnny"]), ("James", ["Jim", "Jamie"]), ("Jose", ["José", "Pepe"]),
                 ("Elizabeth", ["Liz", "Beth", "Elisabeth"]), ("Michael", ["Mike", "Mikey"]),
                 ("Thomas", ["Tom", "Tommy"]), ("Margaret", ["Maggie", "Peggy"]), ("Charles", ["Charlie", "Chuck"]),
                 ("Daniel", ["Dan", "Danny"]), ("Richard", ["Rick", "Dick", "Rich"]), ("Patricia", ["Pat", "Trish"]),
                 ("Susan", ["Sue", "Suzy"]), ("Andrew", ["Andy", "Drew"]), ("Edward", ["Ed", "Ted", "Eddie"]),
                 ("Anthony", ["Tony"]), ("Jennifer", ["Jen", "Jenny"])]
WESTERN_SURNAME = [("Mueller", ["Müller", "Muller"]), ("Nguyen", ["Nguyễn", "Nguyen"]), ("O'Brien", ["OBrien", "O Brien"]),
                   ("Garcia", ["García"]), ("Schroeder", ["Schröder", "Schroder"]), ("Dubois", ["Du Bois"]),
                   ("Smith-Jones", ["Smith Jones", "Smithjones"]), ("Andersen", ["Anderson", "Andersson"]),
                   ("Ferreira", ["Ferreyra"]), ("Kowalski", ["Kowalsky"]), ("Larsen", ["Larson"]), ("Fischer", ["Fisher"]),
                   ("Schmidt", ["Schmitt", "Schmid"]), ("Lefevre", ["Lefèvre", "Le Fevre"]), ("Silva", ["Da Silva", "DaSilva"]),
                   ("Bianchi", ["Bianci"]), ("Nowak", ["Novak"]), ("Petersen", ["Peterson", "Pedersen"]),
                   ("Hernandez", ["Hernández"]), ("Sorensen", ["Sørensen", "Sorenson"])]

ENTITY_STEMS = ["Al-Noor", "Golden Crescent", "Eastern Star", "Silk Road", "Blue Horizon", "Caspian", "Meridian",
                "Northern Lights", "Pacific Rim", "Atlas", "Zenith", "Emerald Bay", "Crystal", "Sahara", "Volga",
                "Orion", "Phoenix", "Summit", "Harbor Point", "Delta", "Amber", "Falcon", "Lotus", "Titan",
                "Al-Bahr", "Red Sea", "Nile Valley", "Zagros", "Ural", "Baltic", "Tigris", "Euphrates", "Sinai",
                "Damavand", "Altai", "Kamchatka", "Aral", "Onyx", "Ivory Coast", "Jade Dragon"]
ENTITY_LINES = ["Trading", "Shipping", "Holdings", "Engineering", "Logistics", "Petroleum", "Industries",
                "Import Export", "Technologies", "Investments", "Construction", "Aviation", "Textiles", "Minerals",
                "Maritime", "Chemicals", "Agro", "Electronics", "Steel", "Pharma"]
SUFFIX_FAMILIES = [
    ["LLC", "L.L.C.", "Limited Liability Company"],
    ["Ltd", "Ltd.", "Limited"],
    ["S.A.", "SA", "Sociedad Anonima"],
    ["GmbH", "G.m.b.H."],
    ["JSC", "Joint Stock Company", "AO", "OAO"],
    ["PJSC", "Public Joint Stock Company"],
    ["Co.", "Company", "Co"],
    ["FZE", "FZ-LLC", "Free Zone Establishment"],
]
VESSEL_NAMES = ["Sea Lion", "Aurora", "Nordic Star", "Golden Wave", "Blue Whale", "Silver Crest", "Ocean Pearl",
                "Grand Voyager", "Coral Queen", "Amber Sky", "Black Tide", "Iron Duke", "Sun Dancer", "Sapphire",
                "Wind Runner", "Lady Fortune", "Star of Aden", "Red Falcon", "Kestrel", "Crimson Dawn",
                "Polar Bear", "Desert Rose", "Green Meadow", "Storm Petrel", "Atlantic Hope", "Pacific Glory",
                "Bosporus", "Hormuz Pride", "Caspian Moon", "Baltic Swan", "Tiger Lily", "Marlin", "Albatross",
                "Ocean Titan", "Silver Lining", "Golden Anchor", "Sea Breeze", "Night Hawk", "Morning Glory", "Andromeda"]
VESSEL_PREFIX = ["", "M/V ", "MV ", "MT ", "M/T "]
NATIONALITIES = {"arabic": ["SY", "IQ", "EG", "LB", "JO", "YE", "SA", "AE"], "persian": ["IR", "AF"],
                 "russian": ["RU", "UA", "BY", "KZ"], "chinese": ["CN", "HK", "TW", "SG"],
                 "western": ["US", "GB", "DE", "FR", "MX", "BR", "CA", "AU"]}
WEAK_NICKNAMES = ["Abu Salem", "The Engineer", "Al-Hakim", "Doctor", "Abu Layth", "The Accountant", "Sasha", "Zhenya",
                  "Dima", "Kolya", "Abu Omar", "Al-Ustadh", "Big Mo", "The Broker"]


# --------------------------------------------------------------------------- helpers
def pick(rng, seq):
    return seq[rng.randrange(len(seq))]


def random_dob(rng, year_lo=1950, year_hi=2000):
    y = rng.randint(year_lo, year_hi)
    m = rng.randint(1, 12)
    d = rng.randint(1, 28)
    return f"{y:04d}-{m:02d}-{d:02d}"


def passport(rng, cc):
    return f"{cc}{rng.randint(10**7, 10**8 - 1)}"


def imo(rng):
    return f"IMO{rng.randint(9000000, 9999999)}"


def regno(rng):
    return f"REG-{rng.randint(100000, 999999)}"


def latin_variant(rng, entry):
    """A different Latin transliteration of the same (canonical, script, variants) name."""
    canonical, _script, variants = entry
    options = [v for v in variants if v != canonical]
    return pick(rng, options) if options else canonical


class Person:
    def __init__(self, culture, given, surname, script_given, script_surname, gender="m", patronymic=None):
        self.culture = culture
        self.given = given
        self.surname = surname
        self.script_given = script_given
        self.script_surname = script_surname
        self.gender = gender
        self.patronymic = patronymic  # (latin, script) or None
        self.father = None  # arabic nasab (latin, script) or None

    def latin(self):
        parts = [self.given[0]]
        if self.father:
            parts += ["bin", self.father[0]]
        if self.patronymic:
            parts.append(self.patronymic[0])
        parts.append(self.surname[0])
        return " ".join(parts)

    def script(self):
        if self.culture == "arabic":
            parts = [self.given[1]]
            if self.father:
                parts += ["بن", self.father[1]]
            parts.append(self.surname[1])
            return " ".join(parts)
        if self.culture == "persian":
            return f"{self.given[1]} {self.surname[1]}"
        if self.culture == "russian":
            parts = [self.given[1]]
            if self.patronymic:
                parts.append(self.patronymic[1])
            parts.append(self.surname[1])
            return " ".join(parts)
        return None


def make_person(rng, culture):
    if culture == "arabic":
        g, s = pick(rng, ARABIC_GIVEN), pick(rng, ARABIC_SURNAME)
        p = Person(culture, g, s, g[1], s[1], gender="f" if g[0] in ("Fatima", "Aisha", "Layla") else "m")
        if rng.random() < 0.35:
            f = pick(rng, [x for x in ARABIC_GIVEN if x[0] not in ("Fatima", "Aisha", "Layla")])
            p.father = (f[0], f[1])
        return p
    if culture == "persian":
        g, s = pick(rng, PERSIAN_GIVEN), pick(rng, PERSIAN_SURNAME)
        return Person(culture, g, s, g[1], s[1], gender="f" if g[0] in ("Nasrin", "Maryam", "Shirin") else "m")
    if culture == "russian":
        female = rng.random() < 0.3
        g = pick(rng, RUSSIAN_GIVEN_F if female else RUSSIAN_GIVEN_M)
        s = pick(rng, RUSSIAN_SURNAME)
        if female and not s[0].endswith("ko"):  # -enko surnames do not inflect
            s = (s[0] + "a", s[1] + "а", [v + "a" for v in s[2]])
        p = Person(culture, g, s, g[1], s[1], gender="f" if female else "m")
        if rng.random() < 0.6:
            p.patronymic = pick(rng, RUSSIAN_PATRONYMIC_F if female else RUSSIAN_PATRONYMIC_M)
        return p
    if culture == "chinese":
        g, s = pick(rng, CHINESE_GIVEN), pick(rng, CHINESE_SURNAME)
        # store as (canonical, script(None), variants)
        return Person(culture, (g[0], None, g[1]), (s[0], None, s[1]), None, None)
    g, s = pick(rng, WESTERN_GIVEN), pick(rng, WESTERN_SURNAME)
    return Person("western", (g[0], None, g[1]), (s[0], None, s[1]), None, None,
                  gender="f" if g[0] in ("Katherine", "Elizabeth", "Margaret") else "m")


def person_name_variant(rng, p, kind):
    """Render a customer-side name for a true match of the given class."""
    given, surname = p.given, p.surname
    if kind == "T1_translit":
        gv = latin_variant(rng, given)
        sv = latin_variant(rng, surname) if rng.random() < 0.7 else surname[0]
        parts = [gv]
        if p.father and rng.random() < 0.5:
            parts += [pick(rng, ["bin", "ibn", "ben"]), latin_variant(rng, p.father + ([],) if len(p.father) == 2 else p.father) if False else p.father[0]]
        if p.patronymic and rng.random() < 0.5:
            parts.append(p.patronymic[0])
        parts.append(sv)
        return " ".join(parts)
    if kind == "T3_structure":
        if p.culture == "russian":
            # surname-first, patronymic dropped or kept, comma optional
            gv = pick(rng, [given[0]] + given[2])
            if rng.random() < 0.5:
                return f"{surname[0]}, {gv}"
            return f"{surname[0]} {gv}" + (f" {p.patronymic[0]}" if p.patronymic and rng.random() < 0.5 else "")
        if p.culture == "chinese":
            gv = pick(rng, [given[0]] + given[2])
            return f"{gv} {surname[0]}"  # given-first order
        if p.culture == "arabic":
            # drop the article / drop bin-father / collapse 'al-'
            sv = surname[0].replace("al-", "").replace("Al-", "")
            gv = pick(rng, [given[0]] + given[2])
            if p.father and rng.random() < 0.5:
                return f"{gv} {p.father[0]} {sv}"
            return f"{gv} {sv}"
        if p.culture == "western":
            gv = pick(rng, given[2])  # nickname
            mid = pick(rng, ["", " A.", " J.", " M."])
            return f"{gv}{mid} {surname[0]}"
        gv = pick(rng, [given[0]] + given[2])
        return f"{surname[0]} {gv}"
    if kind == "T2_script":
        # customer uses a romanization; list side may be script-only
        gv = pick(rng, given[2] if given[2] else [given[0]])
        sv = pick(rng, surname[2] if surname[2] else [surname[0]])
        return f"{gv} {sv}"
    return p.latin()


def entity_variant(rng, name, family):
    stem, line, suffix = name
    new_suffix = pick(rng, [s for s in family if s != suffix] or family)
    forms = [
        f"{stem} {line} {new_suffix}",
        f"{stem} {line}, {new_suffix}",
        f"{stem.upper()} {line.upper()} {new_suffix}",
        f"The {stem} {line} {new_suffix}",
        f"{stem.replace('-', ' ')} {line} {new_suffix}",
        f"{stem} {line.replace('Import Export', 'Import & Export')} {new_suffix}",
        f"{stem} {line}",
    ]
    return pick(rng, forms)


# --------------------------------------------------------------------------- watchlist
def build_watchlist(rng, n_ind=1100, n_ent=520, n_ves=180):
    entries, people = [], []
    uid = 10000
    cultures = ["arabic"] * 32 + ["persian"] * 16 + ["russian"] * 26 + ["chinese"] * 12 + ["western"] * 14
    seen_people = set()  # every listed individual is a distinct identity (canonical given + surname)
    made_people = 0
    while made_people < n_ind:
        culture = pick(rng, cultures)
        p = make_person(rng, culture)
        core = (p.given[0].lower(), p.surname[0].lower().rstrip("a") if (p.culture == "russian" and p.gender == "f") else p.surname[0].lower())
        if core in seen_people:
            continue
        seen_people.add(core)
        made_people += 1
        nat = pick(rng, NATIONALITIES[culture])
        r = rng.random()
        dob = random_dob(rng) if r < 0.70 else (str(rng.randint(1950, 2000)) if r < 0.85 else "")
        aliases = []
        # strong alias: alternate transliteration
        if p.culture in ("arabic", "persian", "russian") and rng.random() < 0.5:
            aliases.append({"name": f"{latin_variant(rng, p.given)} {latin_variant(rng, p.surname)}", "strength": "strong"})
        if p.culture in ("chinese", "western") and rng.random() < 0.5:
            aliases.append({"name": f"{pick(rng, p.given[2])} {pick(rng, p.surname[2])}", "strength": "strong"})
        if rng.random() < 0.3:
            aliases.append({"name": pick(rng, WEAK_NICKNAMES), "strength": "weak"})
        script_name = p.script()
        script_only = script_name is not None and rng.random() < 0.22
        if script_only and rng.random() < 0.6:
            aliases = [a for a in aliases if a["strength"] != "strong"]
        entry = {
            "uid": f"SDN-{uid}",
            "type": "individual",
            "primary_name": script_name if script_only else p.latin(),
            "script_name": script_name,
            "aliases": aliases,
            "dob": dob,
            "nationalities": [nat],
            "ids": [],
            "programs": [pick(rng, ["SDGT", "SYRIA", "IRAN", "RUSSIA-EO14024", "CYBER", "DPRK", "SDNTK"])],
        }
        if rng.random() < 0.3:
            entry["ids"].append({"type": "passport", "number": passport(rng, nat)})
        entries.append(entry)
        people.append((entry, p, dob, nat))
        uid += 1
    entity_names = []
    seen_entities = set()
    while len(entity_names) < n_ent:
        stem, line = pick(rng, ENTITY_STEMS), pick(rng, ENTITY_LINES)
        if (stem, line) in seen_entities:
            continue
        seen_entities.add((stem, line))
        family = pick(rng, SUFFIX_FAMILIES)
        suffix = pick(rng, family)
        name = (stem, line, suffix)
        entry = {
            "uid": f"SDN-{uid}", "type": "entity", "primary_name": f"{stem} {line} {suffix}", "script_name": None,
            "aliases": ([{"name": f"{stem} {line}", "strength": "strong"}] if rng.random() < 0.4 else []),
            "dob": "", "nationalities": [pick(rng, sum(NATIONALITIES.values(), []))],
            "ids": ([{"type": "registration", "number": regno(rng)}] if rng.random() < 0.5 else []),
            "programs": [pick(rng, ["SYRIA", "IRAN", "RUSSIA-EO14024", "NPWMD", "DPRK"])],
        }
        entries.append(entry)
        entity_names.append((entry, name, family))
        uid += 1
    vessels = []
    seen_vessels = set()
    while len(vessels) < n_ves:
        vname = pick(rng, VESSEL_NAMES) + pick(rng, ["", " II", " III", " Star", " One"])
        if vname in seen_vessels:
            continue
        seen_vessels.add(vname)
        entry = {
            "uid": f"SDN-{uid}", "type": "vessel", "primary_name": vname, "script_name": None, "aliases": [],
            "dob": "", "nationalities": [pick(rng, ["PA", "LR", "MH", "IR", "RU", "KM", "CM"])],
            "ids": [{"type": "imo", "number": imo(rng)}], "programs": [pick(rng, ["IRAN", "DPRK", "SYRIA", "VENEZUELA"])],
        }
        entries.append(entry)
        vessels.append((entry, vname))
        uid += 1
    return entries, people, entity_names, vessels


# --------------------------------------------------------------------------- customers
def build_customers(rng, wl, prefix, n_random=4200):
    entries, people, entity_names, vessels = wl
    rows, labels = [], []
    cid = 1
    listed_people = {(lp.given[0].lower(), lp.surname[0].lower().rstrip("a") if (lp.culture == "russian" and lp.gender == "f") else lp.surname[0].lower()) for _e, lp, _d, _n in people}
    listed_entities = {(nm[0], nm[1]) for _e, nm, _f in entity_names}

    def add(name, dob, nat, id_type, id_number, ctype, decision, uid, klass):
        nonlocal cid
        rows.append({"customer_id": f"{prefix}{cid:06d}", "full_name": name, "dob": dob, "nationality": nat,
                     "id_type": id_type, "id_number": id_number, "type": ctype})
        labels.append({"customer_id": f"{prefix}{cid:06d}", "expected_decision": decision,
                       "expected_uid": uid or "", "class": klass})
        cid += 1

    # ---- true matches, individuals
    classes = ["T1_translit", "T2_script", "T3_structure", "T4_alias_strong", "T5_alias_weak_corroborated",
               "T6_id_exact", "T9_dob_partial"]
    for entry, p, dob, nat in people:
        n_matches = 1 if rng.random() < 0.55 else 0
        for _ in range(n_matches):
            script_only = entry["primary_name"] == entry.get("script_name")
            k = pick(rng, ["T2_script"] * 4 + classes) if script_only else pick(rng, classes)
            name, cdob, cnat, idt, idn = None, dob, nat, "", ""
            if k == "T4_alias_strong":
                strong = [a for a in entry["aliases"] if a["strength"] == "strong"]
                if not strong:
                    k = "T1_translit"
                else:
                    name = pick(rng, strong)["name"]
            if k == "T5_alias_weak_corroborated":
                weak = [a for a in entry["aliases"] if a["strength"] == "weak"]
                if not weak or not dob or len(dob) < 10:
                    k = "T1_translit"
                else:
                    name = pick(rng, weak)["name"]
                    cdob = dob  # full DOB corroborates the weak alias
            if k == "T6_id_exact":
                if not entry["ids"]:
                    k = "T1_translit"
                else:
                    idt, idn = entry["ids"][0]["type"], entry["ids"][0]["number"]
                    # deliberately garbled name: only the ID links them
                    name = f"{pick(rng, p.given[2] or [p.given[0]])} {pick(rng, ['K.', 'A.', 'M.'])}"
                    cdob = "" if rng.random() < 0.5 else dob
            if k == "T9_dob_partial":
                if not dob or len(dob) < 10:
                    k = "T1_translit"
                else:
                    cdob = dob[:4] if rng.random() < 0.6 else dob[:7]
                    name = person_name_variant(rng, p, "T1_translit")
            if k == "T2_script":
                if not script_only:
                    k = "T1_translit"
                else:
                    name = person_name_variant(rng, p, "T2_script")
            if name is None:
                name = person_name_variant(rng, p, k)
            if cdob and rng.random() < 0.15 and k not in ("T5_alias_weak_corroborated", "T9_dob_partial"):
                cdob = ""  # missing customer DOB neither confirms nor denies
            if rng.random() < 0.2:
                cnat = pick(rng, sum(NATIONALITIES.values(), []))
            add(name, cdob, cnat, idt, idn, "individual", "MATCH", entry["uid"], k)

    # ---- decoys, individuals
    for entry, p, dob, nat in people:
        r = rng.random()
        if r < 0.22 and dob and len(dob) == 10:
            # D1: same name, conflicting full DOB
            other = random_dob(rng)
            while other[:4] == dob[:4]:
                other = random_dob(rng)
            add(person_name_variant(rng, p, "T1_translit"), other, nat, "", "", "individual", "NO_MATCH", "", "D1_name_dob_conflict")
        elif r < 0.34:
            # D2: near-name confusable — a different given name on the same family name,
            # guaranteed not to coincide with any other listed identity
            for _attempt in range(20):
                q = make_person(rng, p.culture)
                if q.given[0] == p.given[0]:
                    continue
                q.surname = p.surname
                q.gender = p.gender
                core = (q.given[0].lower(), q.surname[0].lower().rstrip("a") if (q.culture == "russian" and q.gender == "f") else q.surname[0].lower())
                if core in listed_people:
                    continue
                add(q.latin(), dob if rng.random() < 0.5 else "", nat, "", "", "individual", "NO_MATCH", "", "D2_near_name")
                break
        elif r < 0.44:
            weak = [a for a in entry["aliases"] if a["strength"] == "weak"]
            if weak:
                # D3: weak alias alone, no corroboration
                add(weak[0]["name"], "", pick(rng, sum(NATIONALITIES.values(), [])), "", "", "individual", "NO_MATCH", "", "D3_weak_alias_alone")
        elif r < 0.52 and dob and len(dob) == 10:
            # D5: partial DOB that conflicts (wrong year)
            add(person_name_variant(rng, p, "T1_translit"), str(int(dob[:4]) + rng.choice([-3, -2, 2, 3])), nat, "", "", "individual", "NO_MATCH", "", "D5_partial_dob_conflict")

    # ---- entities
    for entry, name, family in entity_names:
        r = rng.random()
        if r < 0.5:
            add(entity_variant(rng, name, family), "", entry["nationalities"][0], "", "", "entity", "MATCH", entry["uid"], "T7_entity_suffix")
        elif r < 0.62 and entry["ids"]:
            add(f"{name[0]} Group", "", entry["nationalities"][0], "registration", entry["ids"][0]["number"], "entity", "MATCH", entry["uid"], "T6_id_exact")
        elif r < 0.85:
            free_lines = [line for line in ENTITY_LINES if line != name[1] and (name[0], line) not in listed_entities]
            if free_lines:
                other_line = pick(rng, free_lines)
                add(f"{name[0]} {other_line} {name[2]}", "", entry["nationalities"][0], "", "", "entity", "NO_MATCH", "", "D4_entity_near_name")

    # ---- vessels
    for entry, vname in vessels:
        r = rng.random()
        if r < 0.45:
            add(pick(rng, VESSEL_PREFIX) + vname, "", entry["nationalities"][0], "", "", "vessel", "MATCH", entry["uid"], "T8_vessel_prefix")
        elif r < 0.7:
            add("Vessel " + pick(rng, VESSEL_NAMES) + " Alpha", "", entry["nationalities"][0], "imo", entry["ids"][0]["number"], "vessel", "MATCH", entry["uid"], "T6_id_exact")
        elif r < 0.9:
            add(vname + " " + pick(rng, ["Express", "Trader", "Spirit"]), "", entry["nationalities"][0], "", "", "vessel", "NO_MATCH", "", "D4_entity_near_name")

    # ---- random non-matches (fresh combinations; guaranteed not on the list by construction check below)
    listed_cores = {f"{lp.given[0]} {lp.surname[0]}".lower() for _e, lp, _d, _n in people}
    listed_cores |= {f"{lp.given[0]} {lp.surname[0][:-1]}".lower() for _e, lp, _d, _n in people if lp.gender == "f" and lp.culture == "russian"}
    listed_aliases = {a["name"].lower() for e in entries for a in e["aliases"]}
    made = 0
    while made < n_random:
        culture = pick(rng, ["arabic", "persian", "russian", "chinese", "western"])
        p = make_person(rng, culture)
        name = person_name_variant(rng, p, pick(rng, ["T1_translit", "T3_structure"]))
        core = f"{p.given[0]} {p.surname[0]}".lower()
        core_m = f"{p.given[0]} {p.surname[0][:-1]}".lower() if p.gender == "f" and p.culture == "russian" else core
        if core in listed_cores or core_m in listed_cores or name.lower() in listed_aliases:
            continue
        add(name, random_dob(rng) if rng.random() < 0.8 else "", pick(rng, NATIONALITIES[culture]), "", "", "individual", "NO_MATCH", "", "R0_random")
        made += 1

    rng.shuffle(rows)
    order = {r["customer_id"]: i for i, r in enumerate(rows)}
    labels.sort(key=lambda l: order[l["customer_id"]])
    return rows, labels


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def main():
    rng = random.Random(SEED_HIDDEN)
    wl = build_watchlist(rng)
    entries = wl[0]
    ENV.mkdir(parents=True, exist_ok=True)
    (ENV / "watchlist.json").write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")

    customers, labels = build_customers(random.Random(SEED_HIDDEN + 1), wl, "C")
    fields = ["customer_id", "full_name", "dob", "nationality", "id_type", "id_number", "type"]
    write_csv(ENV / "customers.csv", customers, fields)
    write_csv(TESTS / "labels.csv", labels, ["customer_id", "expected_decision", "expected_uid", "class"])

    dev_customers, dev_labels = build_customers(random.Random(SEED_DEV), wl, "D", n_random=600)
    write_csv(ENV / "dev" / "customers_dev.csv", dev_customers, fields)
    write_csv(ENV / "dev" / "labels_dev.csv", dev_labels, ["customer_id", "expected_decision", "expected_uid", "class"])

    from collections import Counter
    c = Counter(l["class"] for l in labels)
    print(f"watchlist: {len(entries)} entries; hidden customers: {len(customers)}; dev customers: {len(dev_customers)}")
    for k, v in sorted(c.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
