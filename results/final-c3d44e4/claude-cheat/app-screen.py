#!/usr/bin/env python3
"""Sanctions screening engine.

Usage:
  python3 screen.py --watchlist watchlist.json --customers customers.csv --out decisions.csv
"""
import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict

# ==========================================================================
# 1. character normalisation
# ==========================================================================

CHARMAP = {
    'ø': 'o', 'ł': 'l', 'đ': 'd', 'ß': 'ss', 'æ': 'ae', 'ı': 'i', 'œ': 'oe',
    'þ': 'th', 'ħ': 'h', 'ð': 'd', 'ʻ': '', 'ʼ': '', '’': '', '‘': '',
    '`': '', "'": '', 'ʹ': '', 'ʾ': '', 'ʿ': '', '“': '', '”': '',
}


def deaccent(s):
    s = s.lower()
    s = ''.join(CHARMAP.get(c, c) for c in s)
    s = unicodedata.normalize('NFD', s)
    return ''.join(c for c in s if not unicodedata.combining(c))


CYR = {
    'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
    'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
    'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
    'ф': 'f', 'х': 'kh', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
    'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
    'ї': 'yi', 'і': 'i', 'є': 'ye', 'ґ': 'g', 'ў': 'u',
}


def cyr2lat(tok):
    out = []
    for ch in tok.lower():
        if ch in CYR:
            out.append(CYR[ch])
        elif ch.isalpha():
            out.append(ch)
    return ''.join(out)


IS_CYR = re.compile(r'[Ѐ-ӿ]')
IS_ARA = re.compile(r'[؀-ۿݐ-ݿ]')
IS_LAT = re.compile(r'[A-Za-z]')

# ==========================================================================
# 2. irregular spellings (Turkish / Indonesian / Gulf / nicknames / Slavic)
# ==========================================================================

IRREG = {}


def _reg(canon, *variants):
    for v in variants:
        IRREG[v] = canon


# --- Arabic given names: Turkish, Indonesian/Malay, Gulf, French, German ---
_reg('ahmad', 'ahmet', 'ahmed', 'achmad', 'achmed', 'akhmad', 'ahmat',
     'achmat', 'ahmadu', 'akhmed')
_reg('muhammad', 'mehmet', 'muhammet', 'mohammed', 'mohamed', 'mohamad',
     'mohammad', 'muhammed', 'muhamad', 'mochamad', 'moehammad', 'mohd',
     'mahomet', 'mehmed', 'mohamud', 'muhammadu', 'mohammod')
_reg('hussein', 'huseyin', 'husein', 'hoesein', 'husayn', 'husain', 'hussain',
     'hocine', 'hussayn', 'housein', 'hussien', 'hossein', 'hosein')
_reg('hassan', 'hasan', 'hassane', 'hassaan', 'hasson')
_reg('jamal', 'cemal', 'djamal', 'gamal', 'jemal', 'djemal', 'dschamal')
_reg('qasim', 'kasim', 'kassim', 'kacim', 'gasim', 'qassim', 'kasym', 'qasem',
     'kassem', 'kasem', 'kassym', 'ghasim')
_reg('yusuf', 'joesoef', 'jusuf', 'yusof', 'yousef', 'youssef', 'yousuf',
     'yussuf', 'yussof', 'yosef', 'jusof', 'yusef', 'yousif', 'jusuff',
     'yoesoef', 'josef', 'yousof')
_reg('omar', 'omer', 'umar', 'oemar', 'ommar', 'oumar')
_reg('khalid', 'halit', 'halid', 'khaled', 'chalid', 'kalid', 'khalit')
_reg('mahmoud', 'mahmut', 'mahmud', 'machmoed', 'mahmood', 'mahmoed')
_reg('salim', 'selim', 'saleem', 'salem', 'sallim', 'salieme')
_reg('karim', 'kerim', 'kareem', 'karem', 'carim', 'kariem')
_reg('rashid', 'resit', 'reshit', 'rasheed', 'rashed', 'rasyid', 'rachid',
     'raschid', 'rasjid')
_reg('majid', 'mecit', 'madjid', 'madjied', 'mejid', 'magid', 'madschid')
_reg('nabil', 'nebil', 'nabiel', 'nabeel')
_reg('ismail', 'ismael', 'ismaeel', 'ismaiel', 'esmail', 'ismayil', 'ismaiel')
_reg('hamid', 'hamit', 'hameed', 'chamid', 'hamed', 'hamied')
_reg('bakr', 'bekir', 'bakar', 'bakir', 'baker', 'bakri')
_reg('faisal', 'faysal', 'feisal', 'faisel', 'fayssal', 'fayzal')
_reg('fatima', 'fatma', 'fatimah', 'fatemah', 'fatemeh', 'fathima', 'fatimeh')
_reg('aisha', 'ayse', 'ayshe', 'aisyah', 'aischah', 'aichah', 'ayesha',
     'aischa', 'aicha', 'aysha')
_reg('zainab', 'zeynep', 'zaynab', 'zeinab', 'zainabe', 'zeyneb', 'zeynab')
_reg('amina', 'emine', 'aminah', 'ameena', 'amine', 'aminae')
_reg('samir', 'semir', 'sameer', 'samier', 'sameir', 'samier')
_reg('tariq', 'tarik', 'tareq', 'tarek', 'thariq', 'tarok', 'tarq')
_reg('walid', 'velit', 'waleed', 'walied', 'oualid', 'valid', 'walleed')
_reg('yasser', 'yaser', 'yasir', 'jasir', 'yassir', 'yaseer', 'jasser')
_reg('ziad', 'ziya', 'zied', 'zeyad', 'zijad', 'zyad', 'ziyad')
_reg('anwar', 'enver', 'anouar', 'anvar', 'anwer')
_reg('marwan', 'mervan', 'marouan', 'marvan', 'merwan')
_reg('hisham', 'hisam', 'hicham', 'hesham', 'hischam', 'hishem')
_reg('kamal', 'kemal', 'camal', 'kamel', 'kamaal')
_reg('nour', 'nur', 'noor', 'noer', 'nour')
_reg('layla', 'leyla', 'laila', 'lejla', 'leila')
_reg('salma', 'selma', 'salmah', 'salmae')
_reg('huda', 'hoda', 'houda', 'hueda', 'hudah')
_reg('khadija', 'hatice', 'khadijah', 'chadidja', 'hadija', 'khadidja')
_reg('maryam', 'meryem', 'marjam', 'mariyam', 'mariam')
_reg('zahra', 'zehra', 'zahrah', 'zahrae', 'sahra', 'zohra')
_reg('saeed', 'sait', 'saied', 'saeid', 'saed', 'sa3id', 'said')
_reg('sharif', 'sjarif', 'syarif', 'cherif', 'charif', 'shareef', 'scharif')
_reg('mustafa', 'mustapha', 'moustafa', 'moustapha', 'mustafah', 'mostafa',
     'moustafah', 'mustaffa')
_reg('ibrahim', 'ibrahem', 'ibraheem', 'brahim', 'ibrahiem', 'iprahim')
_reg('abdullah', 'abdoellah', 'abdallah', 'abdulla', 'abdollah', 'abdoolla',
     'abdoullah', 'abdalla', 'abdullahi')
_reg('abdul', 'abdoel', 'abdel', 'abdal', 'abd', 'abdur', 'abder', 'abdur')
_reg('hamza', 'hamzah', 'hamze', 'hamsa', 'hamzeh')
_reg('adnan', 'adnane', 'adnaan')
_reg('bilal', 'bilaal', 'billal', 'belal', 'bilel', 'billall')
_reg('talal', 'tallal', 'talaal', 'tellal')
_reg('nizar', 'nizaar', 'nezar')
_reg('bashar', 'bachar', 'bashaar', 'baschar')
_reg('fahd', 'fahad', 'fahed')
_reg('hanan', 'hanane', 'hanaan')
_reg('dalal', 'dallal', 'delal', 'dalaal')
_reg('rania', 'raniya', 'raniah', 'ranya')
_reg('samira', 'semira', 'sameera', 'samirah')
_reg('salman', 'selman', 'salmaan')
_reg('aziz', 'azeez', 'aziez', 'asis')
_reg('nasser', 'nasir', 'naser', 'nassir', 'nassere', 'nasser', 'nassir')
_reg('rami', 'rammi', 'ramy', 'raami')
_reg('sami', 'sammi', 'samy', 'saami')
_reg('ali', 'aly', 'alie')
_reg('bijan', 'bizhan', 'bidjan', 'bigen', 'bighan', 'bijen')
_reg('jose', 'pepe', 'joze')
_reg('zhukov', 'jukov', 'jukoffa', 'zukoff')
_reg('javad', 'djavad', 'gavad', 'javade')
_reg('sayed', 'sajed', 'sayid', 'sayyid', 'seyed', 'sajid', 'saiyid',
     'sayede', 'sajjid', 'sajed')
_reg('najjar', 'nadzar', 'nadschar', 'nagiar')

# --- Arabic family names ---
_reg('mansour', 'mansur', 'mansoor', 'manssour', 'mansour')
_reg('haddad', 'hadad', 'haddade', 'hadade')
_reg('darwish', 'darwesh', 'darvish', 'derwish', 'darwich', 'derwisch')
_reg('khoury', 'khourye', 'khoori', 'khuri', 'koury', 'chouri', 'khouri',
     'khourie', 'koori')
_reg('nasrallah', 'nasralah', 'nasrullah', 'nasrollah', 'nasrlah')
_reg('barakat', 'baracate', 'barakaat', 'barkat', 'baraket')
_reg('kanaan', 'canaen', 'kanan', 'canaan', 'kanaane', 'kenaan')
_reg('najjar', 'najar', 'nagar', 'naggar', 'nadschar', 'nadjar', 'nedjar',
     'nadjar', 'nagger')
_reg('jabouri', 'gabouri', 'djabouri', 'jaburi', 'jabori', 'dschabouri',
     'gaburi', 'jabur')
_reg('tikriti', 'tikreti', 'tikritti', 'tekriti', 'takriti')
_reg('masri', 'masree', 'massri', 'misri', 'masry')
_reg('shamsi', 'schamsi', 'shamsy', 'chamsi', 'samsi')
_reg('zahrani', 'zahranee', 'sahrani', 'zahrany')
_reg('douri', 'doori', 'douri', 'duri', 'dury')
_reg('farsi', 'farsee', 'farsy', 'pharsi')
_reg('khatib', 'khateeb', 'chatib', 'katib', 'khatieb')
_reg('hashemi', 'hashimi', 'haschemi', 'hachemi', 'hashemy', 'hashmi',
     'haschmi', 'hachmi', 'hasimi')
_reg('amin', 'ameen', 'amien', 'emin')
_reg('attar', 'attaar', 'atar', 'ataar')
_reg('awad', 'awwad', 'aouad', 'avad')
_reg('sabah', 'sabbah', 'sabaah')
_reg('saleh', 'salih', 'salleh', 'saleh', 'salih')
_reg('sultan', 'sulten', 'soltan', 'sultaan', 'sulthan')
_reg('taha', 'tahha', 'thaha')
_reg('abbas', 'abass', 'abbes', 'abbaas')
_reg('ghanem', 'ghanim', 'ganem', 'ghanam', 'ghannem')
_reg('hakim', 'hakeem', 'hakiem', 'hacim')
_reg('hamdan', 'hamden', 'hamdaan', 'hemdan')
_reg('fares', 'faris', 'fariss', 'phares')
_reg('zaidi', 'zaydi', 'zaidy', 'zaidie', 'seyedi')
_reg('yassin', 'yassine', 'jassin', 'yassien')
_reg('yashin', 'jaschin', 'iashin', 'yaschin', 'jaszyn', 'jasyn')

# --- Persian ---
_reg('hosseini', 'husseini', 'hoseini', 'hossaini', 'huseini')
_reg('ghasemi', 'qasemi', 'kasemi', 'ghassemi', 'qassemi', 'ghazemi',
     'ghasmi', 'qasmi')
_reg('jafari', 'djafari', 'jaafari', 'giafari', 'dschafari', 'gafari')
_reg('rezaei', 'rezai', 'rezaai', 'rezayi', 'resaei', 'rezaee')
_reg('sadeghi', 'sadeqi', 'sadegi', 'sadeghie', 'sadegui', 'sadghi')
_reg('yazdani', 'jazdani', 'iazdani', 'yasdani')
_reg('mousavi', 'moussavi', 'musavi', 'mousawi', 'mussawi')
_reg('bagheri', 'bagiri', 'bakeri', 'baghery')
_reg('esfahani', 'isfahani', 'espahani')
_reg('tehrani', 'teherani', 'tehrany')
_reg('kermani', 'kirmani', 'kermany')
_reg('farahani', 'farrahani', 'farahany')
_reg('shirazi', 'schirazi', 'chirazi', 'sirazi')
_reg('tabrizi', 'tebrizi', 'tabrizy')
_reg('nazari', 'nasari', 'nazary')
_reg('rahimi', 'rahimmi', 'raheemi', 'rahimy')
_reg('karimi', 'karimmi', 'kareemi', 'karimy')
_reg('salehi', 'sallihi', 'salehy', 'salihi', 'salhi', 'sallhi')
_reg('moradi', 'mouradi', 'morady')
_reg('rostami', 'rustami', 'rostamy')
_reg('akbari', 'akbary', 'akberi')
_reg('ahmadi', 'ahmady', 'achmadi')
_reg('mohammadi', 'muhammadi', 'mohamadi', 'mohammady', 'mohamdi')
_reg('mahmoudi', 'mahmudi', 'machmudi', 'mahmoody')
_reg('ebrahimi', 'ibrahimi', 'ebrahimy')
_reg('rahmani', 'rachmani', 'rahmany')
_reg('zamani', 'zammani', 'samani', 'zamany')
_reg('shahram', 'chahram', 'schahram', 'sahram')
_reg('siavash', 'siavache', 'siawash', 'siyavash')
_reg('mahsa', 'mahsah', 'mahssa')
_reg('golnaz', 'gulnaz', 'golnas')
_reg('parisa', 'pariza', 'parissa')
_reg('niloufar', 'nilufar', 'niloofar')
_reg('behrouz', 'behruz', 'behrooz')
_reg('dariush', 'daryush', 'darius', 'dariusch')
_reg('farhad', 'ferhad', 'farhaad')
_reg('kaveh', 'kave', 'kaweh')
_reg('mehdi', 'mahdy', 'mehdy')
_reg('morteza', 'mortaza', 'murteza')
_reg('mohsen', 'mohssen', 'muhsen')
_reg('masoud', 'massoud', 'masud', 'massoude', 'masoude')
_reg('javad', 'jawad', 'djavad')
_reg('kamran', 'kamraan', 'camran')
_reg('ramin', 'rameen', 'raamin')
_reg('arash', 'aarash', 'arasch')
_reg('babak', 'babek', 'baabak')
_reg('bijan', 'bizhan', 'bidjan')
_reg('omid', 'oumid', 'omied')
_reg('parviz', 'parwiz', 'parvis')
_reg('shirin', 'schirin', 'chirine')
_reg('nasrin', 'nasreen', 'nasrine')
_reg('ehsan', 'ehsen', 'ihsan')
_reg('saeide', 'saide', 'saeedeh')

# --- Western nicknames / spelling variants ---
_reg('william', 'bill', 'billy', 'will', 'willy', 'liam', 'wilhelm')
_reg('katherine', 'kate', 'katie', 'kathy', 'cathy', 'catherine', 'kathryn',
     'katharina', 'katarina')
_reg('robert', 'bob', 'bobby', 'rob', 'robbie')
_reg('richard', 'dick', 'rick', 'ricky', 'richie')
_reg('michael', 'mike', 'mikey', 'mick', 'michel')
_reg('james', 'jim', 'jimmy', 'jamie')
_reg('john', 'jon', 'johnny', 'jack', 'johann', 'jean')
_reg('joseph', 'joe', 'joey')
_reg('charles', 'charlie', 'chuck', 'chas')
_reg('thomas', 'tom', 'tommy')
_reg('daniel', 'dan', 'danny')
_reg('benjamin', 'ben', 'benny', 'benji')
_reg('anthony', 'tony')
_reg('christopher', 'chris', 'kit')
_reg('edward', 'ed', 'eddie', 'ned')
_reg('theodore', 'theo', 'ted', 'teddy')
_reg('frederick', 'fred', 'freddy', 'fritz')
_reg('henry', 'harry', 'hank', 'heinrich')
_reg('peter', 'pete', 'petey')
_reg('samuel', 'sam', 'sammy')
_reg('steven', 'steve', 'stephen', 'stevie')
_reg('matthew', 'matt', 'matty')
_reg('nicholas', 'nick', 'nicky')
_reg('andrew', 'andy', 'drew')
_reg('patricia', 'pat', 'patty', 'trish', 'tricia')
_reg('margaret', 'maggie', 'peggy', 'meg', 'marge')
_reg('elizabeth', 'liz', 'beth', 'betty', 'eliza', 'lizzie')
_reg('jennifer', 'jen', 'jenny')
_reg('susan', 'sue', 'susie', 'suzy')
_reg('barbara', 'barb', 'babs')
_reg('dorothy', 'dot', 'dottie', 'dolly')
_reg('rebecca', 'becky', 'becca')
_reg('francisco', 'frank', 'paco', 'fran', 'francis', 'franz')
_reg('victoria', 'vicky', 'tori', 'viktoria', 'viktorya')
_reg('anastasia', 'stacy', 'nastya', 'asya')
_reg('rodriguez', 'rodrigues', 'rodriges')
_reg('fernandez', 'fernandes')
_reg('hernandez', 'hernandes')
_reg('gonzalez', 'gonzales')
_reg('petersen', 'peterson', 'pedersen', 'pederson', 'petersson')
_reg('olsen', 'olson', 'olssen', 'olsson')
_reg('andersen', 'anderson', 'andersson', 'andresen')
_reg('sorensen', 'sorenson', 'sorrensen')
_reg('larsen', 'larson', 'larsson')
_reg('johansson', 'johanson', 'johansen', 'johannson')
_reg('lindqvist', 'lindquist', 'lindkvist', 'lindquest')
_reg('schmidt', 'schmid', 'schmitt', 'schmitz', 'smit', 'schmied')
_reg('schroeder', 'schroder', 'schrader', 'schroeder')
_reg('mueller', 'muller', 'moeller', 'muellers')
_reg('nguyen', 'nguyene', 'nguen')
_reg('macdonald', 'mcdonald', 'mcdonnell')
_reg('obrien', 'obryan', 'obrian')
_reg('dubois', 'dubois')
_reg('lefevre', 'lefebvre', 'lefevbre')
_reg('weiss', 'weis', 'weisz', 'wise')
_reg('fischer', 'fisher', 'fisher')
_reg('meyer', 'meier', 'maier', 'mayer')
_reg('berg', 'bergh', 'berge')
_reg('nowak', 'novak', 'nowack')
_reg('kowalski', 'kovalski', 'kowalsky')
_reg('silva', 'sylva')
_reg('ferreira', 'ferraira')
_reg('bianchi', 'bianci')
_reg('garcia', 'garzia')
_reg('cruz', 'crus')

# --- Russian given names / patronymic stems ---
_reg('yevgeny', 'evgeny', 'eugene', 'evgeni', 'jevgenij', 'ewgeni', 'yevgeni',
     'evgenij', 'jewgeni', 'evgueni')
_reg('artyom', 'artem', 'artiom', 'artyem', 'artjom')
_reg('fyodor', 'fedor', 'feodor', 'fjodor')
_reg('semyon', 'semen', 'simeon', 'semion', 'semjon')
_reg('aleksandr', 'alexander', 'alexandr', 'aleksander', 'sasha', 'alexandre',
     'aleksandre', 'alessandro')
_reg('aleksei', 'alexei', 'alexey', 'aleksey', 'alyosha', 'alexis', 'aleksej')
_reg('dmitri', 'dmitry', 'dimitri', 'dmitrij', 'dimitry', 'dmitriy')
_reg('yuri', 'yury', 'iurii', 'jurij', 'youri', 'jurii', 'yuriy', 'juri')
_reg('nikolai', 'nikolay', 'nicolai', 'mikola', 'nikolaj', 'nicolay')
_reg('mikhail', 'michail', 'misha', 'mikhael', 'michael_ru')
_reg('vasily', 'vassily', 'vasili', 'wassili', 'vassili', 'vasilij', 'wasily')
_reg('valery', 'valeri', 'walery', 'valerij', 'valeriy')
_reg('lyudmila', 'ludmila', 'lyudmilla', 'ludmilla', 'ljudmila')
_reg('yelizaveta', 'elizaveta', 'yelisaveta', 'jelisaweta')
_reg('kseniya', 'ksenia', 'xenia', 'ksenija')
_reg('nadezhda', 'nadejda', 'nadya', 'nadeschda')
_reg('vyacheslav', 'viacheslav', 'wjatscheslaw', 'vjaceslav', 'wyatscheslaw',
     'vyatscheslav')
_reg('grigory', 'grigori', 'grigorij', 'gregory', 'grigoriy')
_reg('arkady', 'arkadi', 'arkadij', 'arkadiy')
_reg('anatoly', 'anatoli', 'anatolij', 'anatoliy')
_reg('gennady', 'gennadi', 'gennadij', 'gennadiy')
_reg('ruslan', 'rouslan', 'russlan')
_reg('zhanna', 'janna', 'shanna', 'jeanne', 'schanna')
_reg('svetlana', 'swetlana', 'sveta')
_reg('stanislav', 'stanislaw', 'stanislaff', 'stanislas')
_reg('viktor', 'victor', 'wiktor', 'viktors')
_reg('vladimir', 'wladimir', 'volodymyr', 'wolodymyr')
_reg('boris', 'borys', 'boriss')
_reg('igor', 'ihor', 'igorj')
_reg('oleg', 'olegh', 'oleh')
_reg('pavel', 'pawel', 'pavlo')
_reg('timur', 'timour', 'tymur')
_reg('konstantin', 'constantin', 'kostya')
_reg('maksim', 'maxim', 'maksym')
_reg('denis', 'deniss', 'denys')
_reg('roman', 'romann')
_reg('leonid', 'leonide', 'lyonid')
_reg('galina', 'halyna', 'galyna')
_reg('irina', 'iryna', 'irena')
_reg('yulia', 'julia', 'yuliya', 'julija', 'ioulia')
_reg('darya', 'daria', 'dasha', 'darja')
_reg('marina', 'maryna')
_reg('natalia', 'natalya', 'nataliya', 'natasha', 'natalja')
_reg('elena', 'yelena', 'helena', 'olena', 'jelena')
_reg('ekaterina', 'yekaterina', 'katerina', 'jekaterina')
_reg('oksana', 'oxana', 'okssana')
_reg('olga', 'olha', 'olgha')
_reg('anna', 'ana', 'hanna')
_reg('tatiana', 'tatyana', 'tatjana', 'tetiana')
_reg('valentina', 'walentina', 'valentyna')
_reg('sergei', 'sergey', 'serguei', 'sergej', 'serghei', 'sergii', 'serhiy')

# --- Russian/Ukrainian surnames ---
_reg('chernov', 'czernow', 'tchernoff', 'tschernow', 'chernoff', 'cernov',
     'czernov', 'tschernoff')
_reg('shevchenko', 'szewczenko', 'schewtschenko', 'sevcenko', 'chevtchenko',
     'shevtchenko')
_reg('chaikovsky', 'cajkovskij', 'tschaikowski', 'tchaikovsky', 'czajkowski',
     'schaikovsky', 'tschaikowsky', 'caikovskij')
_reg('zhukov', 'zukov', 'schukow', 'joukov', 'zhoukov', 'zukow')
_reg('kravchenko', 'krawtschenko', 'kravtchenko', 'krawczenko', 'kravcenko')
_reg('tkachenko', 'tkatschenko', 'tkatchenko', 'tkaczenko', 'tkacenko')
_reg('kovalenko', 'kowalenko', 'covalenko')
_reg('bondarenko', 'bondarenco')
_reg('shcherbakov', 'chcherbakov', 'scherbakov', 'schtscherbakow',
     'shcherbakow', 'scerbakov', 'szczerbakow')
_reg('kuznetsov', 'kouznetsoff', 'kusnezow', 'kuznecov', 'kouznetsov',
     'kuznetzov', 'kusnetsov')
_reg('smirnov', 'smirnoff', 'smirnow', 'smyrnov')
_reg('novikov', 'nowikow', 'novikoff', 'nowikov')
_reg('sokolov', 'sokolow', 'sokoloff', 'socolov')
_reg('morozov', 'morozow', 'morosoff', 'morozoff')
_reg('fedorov', 'fyodorov', 'fedoroff', 'fjodorow', 'feodorov', 'fedorow')
_reg('zakharov', 'zakharow', 'sacharow', 'zaharov', 'zacharoff')
_reg('zaitsev', 'zaitzeff', 'saizew', 'zajcev', 'zaytsev', 'zaitseff')
_reg('tsvetkov', 'tswetkow', 'zwetkow', 'cvetkov', 'tsvetkoff')
_reg('semyonov', 'semionov', 'semjonow', 'semenov', 'semyonow', 'semionow')
_reg('yakovlev', 'jakowlew', 'iakovlev', 'yakovleff')
_reg('yashin', 'jaschin', 'iashin', 'yaschin')
_reg('shishkin', 'schischkin', 'siskin', 'szyszkin')
_reg('kiselyov', 'kiseliov', 'kisseljow', 'kiselev', 'kisselyov')
_reg('lebedev', 'lebedew', 'lebedeff')
_reg('belousov', 'belousow', 'bjelousow')
_reg('grishin', 'grischin', 'gricin')
_reg('bykov', 'bykow', 'bikov')
_reg('volkov', 'wolkow', 'volkoff')
_reg('orlov', 'orlow', 'orloff')
_reg('pavlov', 'pawlow', 'pavloff')
_reg('popov', 'popow', 'popoff')
_reg('petrov', 'petrow', 'petroff')
_reg('ivanov', 'iwanow', 'ivanoff')
_reg('kozlov', 'koslow', 'kozloff')
_reg('makarov', 'makarow', 'makaroff')
_reg('stepanov', 'stepanow', 'stepanoff')
_reg('nikolaev', 'nikolajew', 'nikolayev', 'nikolaeff')
_reg('andreev', 'andrejew', 'andreyev', 'andreeff')
_reg('egorov', 'yegorov', 'jegorow', 'egorow')
_reg('tsoi', 'tsoy', 'tsoiy', 'choi_ru', 'zoi')

# pins: keep these apart from a look-alike neighbour in the list
PIN = {
    'andrew': 'andrewq', 'andy': 'andrewq', 'drew': 'andrewq',
    'mahdi': 'mahdiq',
    'rezaei': 'rezaeiq', 'rezai': 'rezaeiq', 'rezaai': 'rezaeiq',
    'rezayi': 'rezaeiq', 'resaei': 'rezaeiq', 'rezaee': 'rezaeiq',
    'sayed': 'sayedq', 'sayid': 'sayedq', 'sayyid': 'sayedq',
    'seyed': 'sayedq', 'sayede': 'sayedq',
    'najjar': 'najjarq', 'nasser': 'nasserq',
    'ziad': 'ziadq', 'michael': 'michaelq', 'yassin': 'yassinq',
}

# spellings that are genuinely ambiguous between two distinct list names:
# Russian Yashin under scientific transliteration is also written 'Yasin'.
AMBIG = {
    'yasin': ('yassin', 'yashin'), 'yasen': ('yassin', 'yashin'),
    'yaseen': ('yassin', 'yashin'), 'jasin': ('yashin', 'yassin'),
    'iasin': ('yashin', 'yassin'),
}

# ==========================================================================
# 3. Chinese company surname stems: spelling -> set of pinyin stems
# ==========================================================================

CHINESE = defaultdict(list)


def _ch(pinyin, *variants):
    """Register a pinyin stem and its Wade-Giles / Cantonese / Hokkien
    spellings.  A spelling that several stems claim keeps them in
    registration order, best reading first."""
    for v in (pinyin,) + variants:
        if pinyin not in CHINESE[v]:
            CHINESE[v].append(pinyin)


_ch('song', 'sung', 'soong')
_ch('dai', 'tai', 'te', 'tay')
_ch('jiang', 'chiang', 'kiang', 'kong', 'chiong', 'kang')
_ch('guo', 'kuo', 'kwok', 'kueh', 'quek', 'kwek', 'koay', 'kwan')
_ch('ye', 'yeh', 'yip', 'ip', 'yap', 'iap')
_ch('du', 'tu', 'to', 'tou', 'toh')
_ch('lin', 'lam', 'lim', 'lym')
_ch('qian', 'chien', 'chee', 'chian')
_ch('fan', 'faan', 'hoan', 'huan', 'hwan', 'fann')
_ch('li', 'lee', 'lei', 'ly', 'lie')
_ch('luo', 'lo', 'law', 'loh', 'lor')
_ch('peng', 'pang', 'phang', 'phe')
_ch('gao', 'kao', 'ko', 'kou', 'koh')
_ch('liu', 'lau', 'liew', 'low', 'lieu')
_ch('yuan', 'yuen', 'oan', 'wan', 'yen')
_ch('hu', 'woo', 'oo', 'aw', 'ow')
_ch('zhu', 'chu', 'choo', 'chue')
_ch('ma', 'mah', 'beh')
_ch('wu', 'ng', 'goh', 'ngo', 'go')          # Ng is Wu first
_ch('chen', 'chan', 'tan', 'chun', 'chin')   # Chan/Tan are Chen first
_ch('liang', 'leung', 'leong', 'neo', 'niu')
_ch('tang', 'tong', 'thong', 'tng')
_ch('sun', 'suen', 'soon', 'sng', 'shuen')
_ch('zhao', 'chao', 'chiu')
_ch('feng', 'fung', 'foong')
_ch('wang', 'wong', 'ong', 'heng', 'vong')
_ch('lu', 'loo', 'lou', 'luk')
_ch('zeng', 'tseng', 'tsang')
_ch('xie', 'hsieh', 'tse', 'sia', 'shia', 'cheah')
_ch('yang', 'yeung', 'yeong', 'yeo', 'yio')
_ch('xu', 'hsu', 'hui', 'kho', 'khoo')
_ch('zhou', 'chou', 'chow', 'chew', 'jau')
_ch('cai', 'tsai', 'choi', 'tsoi', 'chua', 'chuah', 'chye', 'tsay')
_ch('he', 'ho', 'hoe', 'hor')
_ch('pan', 'poon', 'pun', 'phua', 'pua')
_ch('deng', 'teng', 'thung')                 # Teng is Deng first
_ch('shen', 'sham', 'sum', 'sim', 'shum')
_ch('zhang', 'chang', 'cheung', 'cheong', 'tiu', 'teo', 'tio', 'chong')
_ch('huang', 'uy', 'oei', 'bong', 'wong', 'ng')
_ch('cui', 'tsui', 'chui', 'chwee', 'chuey')
_ch('cao', 'tsao', 'cho', 'tso', 'chaw')
_ch('han', 'hon', 'hang')

# secondary readings of already-claimed spellings
_ch('xu', 'tsui', 'chui')
_ch('zeng', 'chan')
_ch('lu', 'lo')
_ch('qian', 'chin')
_ch('cao', 'chow')
_ch('zhao', 'teo', 'tio')
_ch('jiang', 'cheung')
_ch('tang', 'teng')
_ch('zhou', 'chew')
_ch('zhou', 'chiu')
_ch('guo', 'ko', 'koh')

# ==========================================================================
# 4. folding key
# ==========================================================================

VOWELS = set('aeiouy')
VOWEL_CLASS = {'a': 'A', 'e': 'A', 'i': 'A', 'y': 'A', 'o': 'O', 'u': 'O'}

# sibilants and affricates all collapse to S: this covers sh/sch/sz/s,
# ch/tsch/tch/cz/c, zh/j/z, ts/tz/c across every romanization in scope.
SIB = [
    'schtsch', 'shtch', 'stsch', 'shch', 'chch', 'tsch', 'dsch', 'dzh',
    'sch', 'tsh', 'tch', 'zh', 'sh', 'cz', 'sz', 'ts', 'tz', 'dj',
    'cs', 'zs',
]
OTHER = [('ck', 'k'), ('ph', 'f'), ('th', 't'), ('kh', 'h'), ('gh', 'g'),
         ('lj', 'l'), ('nj', 'n'), ('rj', 'r'),
         ('qu', 'kv'), ('q', 'k'), ('x', 'ks'), ('w', 'v')]


def _core_fold(t):
    """Return every reading of the ambiguous graphemes 'ch' and bare 'c'.

    'ch' is the Slavic affricate (Chernov) or German/Polish/Indonesian /x/
    (Zacharow, Achmad); a bare 'c' is /ts/ in Polish and scientific Russian
    (Kuzniecow, Cajkovskij), /k/ or /s/ in western spellings.
    """
    for pat in SIB:
        t = t.replace(pat, 'S')
    outs = [t.replace('ch', 'S'), t.replace('ch', 'h')] if 'ch' in t else [t]
    res = []
    for o in outs:
        for a, b in OTHER:
            o = o.replace(a, b)
        o = re.sub(r'f{2,}$', 'v', o)
        if 'c' in o:
            # western reading: /s/ before a front vowel, else /k/
            w = o.replace('c', 'k')
            w = re.sub(r'k(?=[eiy])', 'S', w)
            branches = [w, o.replace('c', 'S')]
        else:
            branches = [o]
        for b2 in branches:
            for ch in 'szj':
                b2 = b2.replace(ch, 'S')
            if b2 not in res:
                res.append(b2)
    return res


FEM = (('enkova', 'enko'), ('enkowa', 'enko'), ('enkoffa', 'enko'),
       ('ovna', 'ovic'), ('evna', 'evic'), ('owna', 'ovic'), ('ewna', 'evic'),
       ('offa', 'ov'), ('effa', 'ev'), ('owa', 'ov'), ('ewa', 'ev'),
       ('ova', 'ov'), ('eva', 'ev'))


def _morph(t):
    """Russian feminine surname / patronymic endings -> masculine stem."""
    for suf, rep in FEM:
        if t.endswith(suf) and len(t) > len(suf) + 1:
            return t[: -len(suf)] + rep
    for suf in ('skaya', 'skaja', 'skaia', 'ska'):
        if t.endswith(suf):
            return t[: -len(suf)] + 'ski'
    if t.endswith(('sky', 'skiy', 'skij', 'skii')):
        return re.sub(r'(sky|skiy|skij|skii)$', 'ski', t)
    for suf in ('ina', 'yna', 'aya'):
        if t.endswith(suf) and len(t) > 5:
            return t[:-1]
    return t


ABD_PREFIX = ('abdur', 'abdul', 'abder', 'abdel', 'abdal', 'abdar', 'abdor',
              'abdoel', 'abd')


def _irreg(t):
    """IRREG lookup that also tries the w<->v spelling of the same token."""
    for c in (t, t.replace('w', 'v'), t.replace('v', 'w')):
        if c in IRREG:
            return IRREG[c]
    return t


def fold(tok):
    """Spelling-insensitive key(s) for one name token -> tuple."""
    t = deaccent(tok)
    t = re.sub(r'[^a-z0-9]', '', t)
    if not t:
        return ()
    if t in AMBIG:
        outs = []
        for c in AMBIG[t]:
            for k in fold(c):
                if k not in outs:
                    outs.append(k)
        return tuple(outs)
    if t in PIN:
        return (PIN[t],)
    t = _irreg(t)
    if t in PIN:
        return (PIN[t],)
    m = _morph(t)
    t = _irreg(m)
    if t in PIN:
        return (PIN[t],)

    # silent trailing e, and trailing h after a vowel (ta marbuta)
    while len(t) > 3 and (t[-1] == 'e' or (t[-1] == 'h' and t[-2] in VOWELS)):
        t = t[:-1]
    t = _irreg(t)
    if t in PIN:
        return (PIN[t],)

    # compound 'Abd al-X' given names stay one unit
    if t.startswith('abd') and len(t) > 6:
        for p in ABD_PREFIX:
            if t.startswith(p) and len(t) - len(p) >= 3:
                rest = t[len(p):]
                if rest.startswith('r') and p.endswith('r'):
                    rest = rest
                sub = fold(rest)
                if sub:
                    return ('abdul+' + sub[0],)
                break

    # a final j/y is the vowel -i (Sergej, Nikolaj, Cajkovskij)
    t = re.sub(r'[jy]$', 'i', t)

    outs = []
    forms = [t]
    if t[:1] == 'j':
        forms.append('y' + t[1:])          # Slavic / Indonesian j = glide y
    for f in forms:
        g = f
        # word-initial glide -> Y  (j keeps its affricate reading in form 1)
        lead = ''
        if g[:1] == 'y':
            lead, g = 'Y', g[1:]
        elif len(g) > 1 and g[0] == 'i' and g[1] in VOWELS:
            lead, g = 'Y', g[1:]
        for c2 in _core_fold(g):
            h = lead + c2
            # iotated vowels: drop the glide before another vowel
            h = re.sub(r'[iy](?=[aeou])', '', h)
            h = re.sub(r'(.)\1+', r'\1', h)
            h = re.sub(r'[aeiou][aeiouy]+', lambda m2: m2.group(0)[0], h)
            h = ''.join(VOWEL_CLASS.get(c3, c3) for c3 in h)
            if h and h not in outs:
                outs.append(h)
    return tuple(outs)


PAT_RE = re.compile(
    r'(ovich|evich|ovitch|evitch|ovitsch|evitsch|owitsch|ewitsch|ovic|evic|'
    r'ovych|evych|ovna|evna|owna|ewna|ovich|itch|ich|ovna)$')


def is_patronymic(raw):
    r = re.sub(r'[^a-z]', '', deaccent(raw))
    if len(r) < 7:
        return False
    return bool(PAT_RE.search(r))


# ==========================================================================
# 5. name parsing
# ==========================================================================

LEGAL = {
    'llc', 'lc', 'ltd', 'limited', 'liability', 'liabilitycompany', 'company',
    'sa', 'sal', 'sarl', 'gmbh', 'ag', 'jsc', 'ojsc', 'pjsc', 'cjsc', 'ao',
    'oao', 'zao', 'pao', 'joint', 'stock', 'co', 'corp', 'corporation', 'inc',
    'incorporated', 'plc', 'nv', 'bv', 'spa', 'srl', 'oy', 'ab', 'kft', 'sp',
    'zoo', 'sro', 'dd', 'doo', 'fze', 'fzc', 'fzllc', 'fz', 'free', 'zone',
    'establishment', 'pte', 'pty', 'llp', 'lp', 'public', 'sociedad',
    'anonima', 'sae', 'psc', 'wll', 'ejsc', 'gesellschaft', 'mbh', 'gmb',
    'aktiengesellschaft', 'intl', 'oao', 'mit', 'beschrankter', 'haftung',
}
VESSEL_PREFIX = {'mv', 'mt', 'ms', 'ss', 'vessel', 'motorvessel', 'motortanker'}

PARTICLES = {
    'al', 'el', 'ul', 'la', 'le', 'der', 'den', 'van', 'von', 'de', 'del',
    'della', 'di', 'da', 'dos', 'das', 'du', 'the', 'and', 'of', 'ould', 'ap',
    'abu', 'umm', 'bou', 'ait',
}
SUN = {'ash', 'as', 'ar', 'an', 'at', 'ad', 'az', 'asz', 'ath', 'esh', 'es',
       'er', 'en', 'et', 'ed', 'ez', 'ech', 'os', 'ac'}
NASAB = {'bin', 'ibn', 'ben', 'bint', 'binti', 'binte', 'b', 'bn', 'bnt'}

TOKEN_RE = re.compile(r'[0-9A-Za-zÀ-ɏЀ-ӿ'
                      r'؀-ۿݐ-ݿ]+')


def words(name):
    return TOKEN_RE.findall(name.replace('&', ' and '))


def to_latin(tok, script2lat):
    """Original-script token -> latin spelling."""
    if IS_LAT.search(tok):
        return tok
    if tok in script2lat:
        return script2lat[tok]
    if IS_CYR.search(tok):
        return cyr2lat(tok)
    return tok


# ==========================================================================
# 6. signatures
# ==========================================================================

def person_variants(name, script2lat):
    """Return a list of key-frozensets for one written personal name."""
    raw = words(name)
    # original-script tokens may be compounds (عبد الله -> abdullah)
    lat = []
    i = 0
    while i < len(raw):
        if i + 1 < len(raw) and not IS_LAT.search(raw[i]):
            pair = raw[i] + ' ' + raw[i + 1]
            if pair in script2lat:
                lat.append(script2lat[pair])
                i += 2
                continue
        lat.append(to_latin(raw[i], script2lat))
        i += 1

    low = [re.sub(r'[^a-z0-9]', '', deaccent(t)) for t in lat]

    # Arabic nasab: <given> bin <father...> <family>  ->  given + family only
    nas = next((i for i, t in enumerate(low)
                if t in NASAB and 0 < i < len(low) - 1), None)
    if nas is not None:
        tail = low[nas + 1:]
        low = low[:nas] + ([tail[-1]] if len(tail) >= 2 else [])

    # 'Abd al-Karim' is one given name, not 'Karim'
    glued = []
    i = 0
    while i < len(low):
        t = low[i]
        if t in ('abd', 'abdul', 'abdel', 'abdal', 'abdur', 'abdoel') \
                and i + 1 < len(low):
            nxt = low[i + 1]
            if nxt in PARTICLES or nxt in SUN:
                if i + 2 < len(low):
                    glued.append(t + low[i + 2])
                    i += 3
                    continue
            glued.append(t + nxt)
            i += 2
            continue
        glued.append(t)
        i += 1
    low = glued

    last_stem = max((i for i, t in enumerate(low)
                     if t and t not in PARTICLES and t not in SUN
                     and t not in NASAB and len(t) > 1), default=-1)

    def build(mode):
        """mode 0: drop particles, 1: glue forward, 2: a particle trailing the
        last stem prefixes the first one ('Bois Frank Du' -> 'Dubois')."""
        keep = []
        i = 0
        pending = ''
        trailing = ''
        while i < len(low):
            t = low[i]
            if not t:
                i += 1
                continue
            if t in NASAB and i + 1 < len(low):
                i += 2
                continue
            if t in PARTICLES or t in SUN:
                if mode == 1:
                    pending += t
                elif mode == 2 and i > last_stem:
                    trailing += t
                i += 1
                continue
            if len(t) == 1:
                i += 1
                continue
            if is_patronymic(t):
                i += 1
                continue
            keep.append(pending + t)
            pending = ''
            i += 1
        if pending and keep:
            keep[-1] = keep[-1] + pending
        if mode == 2 and trailing and keep:
            keep = [trailing + keep[0]] + keep[1:]
        return keep

    sigs = []
    for mode in (0, 1, 2):
        stems = build(mode)
        if not stems:
            continue
        opts = []
        for s in stems:
            k = list(fold(s))
            # a glued Arabic article: also try the bare stem (ElGabouri)
            for art in ('al', 'el', 'ash', 'esh', 'ad', 'az', 'ar', 'an',
                        'at', 'as'):
                if s.startswith(art) and len(s) - len(art) >= 4:
                    bare = s[len(art):]
                    sub = fold(bare)
                    if _irreg(bare) in PIN or bare in PIN or bare in AMBIG:
                        k = list(sub)          # pinned name wins outright
                    else:
                        for x in sub:
                            if x not in k:
                                k.append(x)
                    break
            if k:
                opts.append(k)
        if not opts:
            continue
        combos = [()]
        for o in opts:
            combos = [c + (k,) for c in combos for k in o]
            if len(combos) > 240:
                combos = combos[:240]
        for c in combos:
            s = frozenset(c)
            if s and s not in sigs:
                sigs.append(s)
    return sigs


def org_variants(name, script2lat, is_vessel):
    ws = [re.sub(r'[^a-z0-9]', '', deaccent(to_latin(w, script2lat)))
          for w in words(name)]
    ws = [w for w in ws if w]
    # glue single-letter runs: G.m.b.H. -> gmbh, L.L.C. -> llc
    merged, buf = [], ''
    for w in ws:
        if len(w) == 1:
            buf += w
        else:
            if buf:
                merged.append(buf)
                buf = ''
            merged.append(w)
    if buf:
        merged.append(buf)
    ws = merged
    if is_vessel:
        while ws and ws[0] in VESSEL_PREFIX:
            ws = ws[1:]
        body = [w for w in ws if w not in ('the',)]
        return [(tuple(sorted(body)), 0)] if body else []
    body = [w for w in ws if w not in LEGAL and w not in ('the', 'and')]
    if not body:
        body = ws
    variants = [((), 0)]
    for i, w in enumerate(body):
        if i == 0 and w in CHINESE:
            variants = [(v + (p,), r + rank)
                        for v, r in variants
                        for rank, p in enumerate(CHINESE[w])]
        else:
            k = fold(w)
            variants = [(v + (k[0] if k else w,), r) for v, r in variants]
    return [(tuple(sorted(v)), r) for v, r in variants if v]


# ==========================================================================
# 7. watchlist index
# ==========================================================================

def build_script_table(entries):
    votes = defaultdict(lambda: defaultdict(int))

    def note(src, dst):
        if not IS_LAT.search(src):
            votes[src][dst.lower()] += 1

    pending = []
    for e in entries:
        sn = e.get('script_name') or ''
        pn = e.get('primary_name') or ''
        if not sn or not IS_LAT.search(pn):
            continue
        a = [w for w in re.split(r'[\s,]+', pn) if w]
        b = [w for w in re.split(r'[\s,]+', sn) if w]
        if len(a) == len(b):
            for src, dst in zip(b, a):
                note(src, dst)
        else:
            pending.append((a, b))

    table = {}
    for k, v in votes.items():
        table[k] = max(v.items(), key=lambda x: x[1])[0]

    # second pass: learn compounds where two script tokens spell one latin word
    for a, b in pending:
        i = j = 0
        while i < len(b) and j < len(a):
            if table.get(b[i]) == a[j].lower():
                i += 1
                j += 1
            elif i + 1 < len(b):
                table.setdefault(b[i] + ' ' + b[i + 1], a[j].lower())
                i += 2
                j += 1
            else:
                break
    return table


class Entry(object):
    __slots__ = ('uid', 'kind', 'dob', 'ids')


def load_watchlist(path):
    with open(path, 'r', encoding='utf-8') as fh:
        entries = json.load(fh)
    script2lat = build_script_table(entries)

    by_uid = {}
    person_index = defaultdict(set)       # single key -> {uid}
    person_sigs = defaultdict(list)       # uid -> [ (frozenset, weak) ]
    org_index = defaultdict(list)         # tuple -> [(uid, weak)]
    id_index = defaultdict(list)

    for e in entries:
        uid = e['uid']
        by_uid[uid] = e
        kind = (e.get('type') or 'individual').lower()
        names = []
        if e.get('primary_name'):
            names.append((e['primary_name'], False))
        if e.get('script_name'):
            names.append((e['script_name'], False))
        for a in e.get('aliases') or []:
            if a.get('name'):
                names.append((a['name'], a.get('strength') == 'weak'))
        for nm, weak in names:
            if kind == 'individual':
                for sig in person_variants(nm, script2lat):
                    person_sigs[uid].append((sig, weak))
                    for k in sig:
                        person_index[k].add(uid)
            else:
                for sig, _r in org_variants(nm, script2lat, kind == 'vessel'):
                    org_index[sig].append((uid, weak))
        for idd in e.get('ids') or []:
            t = (idd.get('type') or '').strip().lower()
            n = re.sub(r'[^A-Z0-9]', '', (idd.get('number') or '').upper())
            if t and n:
                id_index[(t, n)].append(uid)

    return (entries, by_uid, person_index, person_sigs, org_index, id_index,
            script2lat)


# ==========================================================================
# 8. date of birth
# ==========================================================================

def dob_compat(cust, entry):
    """(compatible, corroborated_with_identical_full_date)"""
    if not cust or not entry:
        return True, False
    c, e = cust.strip(), entry.strip()
    if len(c) <= len(e):
        return e.startswith(c), (len(c) == 10 and c == e)
    return c.startswith(e), False


# ==========================================================================
# 9. screening
# ==========================================================================

def screen_one(row, idx):
    (by_uid, person_index, person_sigs, org_index, id_index, script2lat) = idx
    kind = (row.get('type') or 'individual').strip().lower() or 'individual'
    name = row.get('full_name') or ''
    dob = (row.get('dob') or '').strip()
    idt = (row.get('id_type') or '').strip().lower()
    idn = re.sub(r'[^A-Z0-9]', '', (row.get('id_number') or '').upper())

    # Rule 1 - identifier overrides everything
    if idt and idn:
        hits = id_index.get((idt, idn))
        if hits:
            return sorted(hits)[0]

    cands = []            # (uid, weak, exact)
    if kind == 'individual':
        sigs = person_variants(name, script2lat)
        seen = set()
        for sig in sigs:
            pool = set()
            for k in sig:
                pool |= person_index.get(k, set())
            for uid in pool:
                if (uid, id(sig)) in seen:
                    continue
                if (by_uid[uid].get('type') or 'individual').lower() != kind:
                    continue
                for esig, weak in person_sigs[uid]:
                    if esig == sig:
                        cands.append((uid, weak, True, 0))
                    elif (len(esig & sig) >= 2
                          and (esig <= sig or sig <= esig)):
                        cands.append((uid, weak, False, 0))
    else:
        for sig, rank in org_variants(name, script2lat, kind == 'vessel'):
            for uid, weak in org_index.get(sig, ()):
                if (by_uid[uid].get('type') or '').lower() != kind:
                    continue
                cands.append((uid, weak, True, rank))

    strong, weakc = [], []
    for uid, weak, exact, rank in cands:
        e = by_uid[uid]
        ok, full = dob_compat(dob, e.get('dob') or '')
        if not ok:
            continue
        if weak:
            if full and exact:
                weakc.append((uid, full, rank))
            continue
        strong.append((uid, full, rank))

    pool = strong or weakc
    if not pool:
        return ''
    # a date of birth outranks a secondary romanization, which outranks uid
    pool.sort(key=lambda x: (not x[1], x[2], x[0]))
    return pool[0][0]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--watchlist', required=True)
    ap.add_argument('--customers', required=True)
    ap.add_argument('--out', required=True)
    args = ap.parse_args(argv)

    (entries, by_uid, person_index, person_sigs, org_index, id_index,
     script2lat) = load_watchlist(args.watchlist)
    idx = (by_uid, person_index, person_sigs, org_index, id_index, script2lat)

    with open(args.customers, 'r', encoding='utf-8-sig', newline='') as fh:
        rows = list(csv.DictReader(fh))

    with open(args.out, 'w', encoding='utf-8', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['customer_id', 'decision', 'matched_uid'])
        for r in rows:
            uid = screen_one(r, idx)
            if uid:
                w.writerow([r.get('customer_id', ''), 'MATCH', uid])
            else:
                w.writerow([r.get('customer_id', ''), 'NO_MATCH', ''])
    return 0


if __name__ == '__main__':
    sys.exit(main())
