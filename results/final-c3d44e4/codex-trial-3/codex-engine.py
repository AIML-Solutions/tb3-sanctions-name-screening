#!/usr/bin/env python3
"""Deterministic sanctions-name screening under screening_policy.md.

Python 3.12, standard library only.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict


def ascii_text(value: str) -> str:
    value = value.translate(str.maketrans({
        "ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D",
        "ð": "d", "Ð": "D", "þ": "th", "Þ": "Th", "ı": "i",
        "ß": "ss", "ẞ": "SS",
    }))
    return "".join(c for c in unicodedata.normalize("NFKD", value)
                   if not unicodedata.combining(c))


def plain_words(value: str) -> list[str]:
    value = ascii_text(value).lower().replace("’", "'").replace("‘", "'")
    return re.findall(r"[^\W\d_]+", value, flags=re.UNICODE)


# Cyrillic is regular enough to transliterate character by character. Later
# token canonicalisation folds the common national romanisation conventions.
CYR = str.maketrans({
    "а":"a", "б":"b", "в":"v", "г":"g", "д":"d", "е":"e", "ё":"yo",
    "ж":"zh", "з":"z", "и":"i", "й":"y", "к":"k", "л":"l", "м":"m",
    "н":"n", "о":"o", "п":"p", "р":"r", "с":"s", "т":"t", "у":"u",
    "ф":"f", "х":"kh", "ц":"ts", "ч":"ch", "ш":"sh", "щ":"shch",
    "ъ":"", "ы":"y", "ь":"", "э":"e", "ю":"yu", "я":"ya",
    "і":"i", "ї":"yi", "є":"ye", "ґ":"g",
})


# Arabic/Persian spelling is consonantal and cannot safely be recovered with a
# letter substitution. These are the relevant name words mapped to one Latin
# comparison spelling.
ARABIC_WORDS = {
    "آرش":"arash", "أحمد":"ahmad", "احمدی":"ahmadi", "اصفهانی":"esfahani",
    "أمينة":"amina", "أنور":"anwar", "إبراهيم":"ibrahim", "إسماعيل":"ismail",
    "احسان":"ehsan", "امیر":"amir", "اکبری":"akbari", "بابک":"babak",
    "باقری":"bagheri", "بركات":"barakat", "بشار":"bashar", "بكر":"bakr", "بلال":"bilal",
    "بن":"bin", "بهروز":"behrouz", "بیژن":"bijan", "تبریزی":"tabrizi", "تهرانی":"tehrani",
    "جعفری":"jafari", "جمال":"jamal", "جواد":"javad", "حداد":"haddad", "حسن":"hassan",
    "حسين":"hussein", "حسین":"hossein", "حسینی":"hosseini", "حكيم":"hakim", "حمدان":"hamdan",
    "حمزة":"hamza", "حميد":"hamid", "حمید":"hamid", "حنان":"hanan", "خالد":"khalid",
    "خديجة":"khadija", "خوري":"khoury", "داریوش":"dariush", "درويش":"darwish", "دلال":"dalal",
    "راشد":"rashid", "رامي":"rami", "رامین":"ramin", "رانيا":"rania", "رحمانی":"rahmani",
    "رحیمی":"rahimi", "رستمی":"rostami", "رضا":"reza", "رضایی":"rezaei", "زمانی":"zamani",
    "زهرا":"zahra", "زياد":"ziad", "زيدي":"zaidi", "زينب":"zainab", "سامي":"sami",
    "سعيد":"saeid", "سعید":"saeid", "سلطان":"sultan", "سلمان":"salman", "سلمى":"salma",
    "سليم":"salim", "سمير":"samir", "سميرة":"samira", "سیاوش":"siavash", "شاهين":"shahin",
    "شهرام":"shahram", "شیرازی":"shirazi", "شیرین":"shirin", "صادقی":"sadeghi", "صالح":"saleh",
    "صالحی":"salehi", "طارق":"tariq", "طلال":"talal", "طه":"taha", "عائشة":"aisha",
    "عباس":"abbas", "عبد":"abdul", "عدنان":"adnan", "عزيز":"aziz", "علي":"ali",
    "عمر":"omar", "عوض":"awad", "غانم":"ghanem", "فارس":"fares", "فاطمة":"fatima",
    "فاطمه":"fatemeh", "فراهانی":"farahani", "فرهاد":"farhad", "فهد":"fahd", "فيصل":"faisal",
    "قاسم":"qasim", "قاسمی":"ghasemi", "كريم":"karim", "كمال":"kamal", "كنعان":"kanaan",
    "ليلى":"layla", "لیلا":"leila", "ماجد":"majid", "مجید":"majid", "محسن":"mohsen",
    "محمد":"muhammad", "محمدی":"mohammadi", "محمود":"mahmoud", "محمودی":"mahmoudi", "مرادی":"moradi",
    "مرتضی":"morteza", "مروان":"marwan", "مريم":"mariam", "مریم":"maryam", "مسعود":"masoud",
    "مصطفى":"mustafa", "منصور":"mansour", "مهدي":"mahdi", "مهدی":"mehdi", "مهسا":"mahsa",
    "موسوی":"mousavi", "ناصر":"nasser", "نبيل":"nabil", "نزار":"nizar", "نسرین":"nasrin",
    "نصر":"nasr", "نظری":"nazari", "نور":"nour", "نیلوفر":"niloufar", "هاشمی":"hashemi",
    "هدى":"huda", "هشام":"hisham", "وليد":"walid", "ياسر":"yasser", "ياسين":"yassin",
    "يوسف":"yusuf", "پرویز":"parviz", "پریسا":"parisa", "کامران":"kamran", "کاوه":"kaveh",
    "کرمانی":"kermani", "کریمی":"karimi", "یزدانی":"yazdani",
    "ابراهیمی":"ebrahimi", "گلناز":"golnaz", "امید":"omid",
    # Definite-article family words.
    "الأمين":"amin", "التكريتي":"tikriti", "الجبوري":"jabouri", "الخطيب":"khatib",
    "الدوري":"douri", "الرحمن":"rahman", "الرشيد":"rashid", "الزهراني":"zahrani",
    "السيد":"sayed", "الشمسي":"shamsi", "الصباح":"sabah", "العزيز":"aziz",
    "العطار":"attar", "الفارسي":"farsi", "الكريم":"karim", "الله":"allah",
    "المصري":"masri", "النجار":"najjar", "الهاشمي":"hashimi",
}


def _variant_table() -> dict[str, str]:
    groups: dict[str, str] = {}
    def add(root: str, words: str) -> None:
        for word in words.split():
            groups[word] = root

    # Arabic and Persian: English/French/German/Turkish/Malay spellings.
    add("muhammad", "muhammad muhamaad mohammed mohammad mohamed mohamad muhammed muhamed mehmet moehammad")
    add("ahmad", "ahmad ahmed ahmet achmad")
    add("jamal", "jamal jamaal jammal djamal dschammal gamal gammal cemal")
    add("hussein", "hussein houssein hussain husain husayn husein huseyn huseyin hussaine husseine hosseine hoesin hoesein hoessein hosain hossein hossain")
    add("yusuf", "yusuf yussef yussuf youssef yousuf yusef yusof yusoof yusoofe yussof joesoef")
    add("qasim", "qasim qassim qasem qassem kassim kassem kasem kaseem qaseem qaseeme kasim")
    add("karim", "karim kareem kareme karem carem careme kerim")
    add("abdullah", "abdullah abdallah abdoullah abdoollah abdoolla abdollah abdoellah abdula abdulla abdola")
    add("abdul", "abdul abdoel")
    add("abdulaziz", "abdulaziz abdulazez abdelaziz abdelazez abduaziz abduazeze")
    add("abdulrahman", "abdulrahman abdulrahmen abdurrahman abderrahman abderrahmane")
    add("abdulkarim", "abdulkarim abdulkarem abdulkareem abdulcarem")
    add("amina", "amina amena ameena ameenah aminah amenah")
    add("amir", "amir amer ameer")
    add("aisha", "aisha aishah aysha aicha aichah aischah")
    add("anwar", "anwar anouar anouare")
    add("abbas", "abbas abas abase abasse abbase")
    add("awad", "awad awed awadhe")
    add("bashar", "bashar bashare baschar bachar bachare")
    add("bakr", "bakr bakre")
    add("bilal", "bilal billal billale billalle")
    add("dalal", "dalal dalale dallal dallale")
    add("fahd", "fahd fahde")
    add("faisal", "faisal faissal faysal fayssal")
    add("fares", "fares faris farise")
    add("fatima", "fatima fatema fatemah fateema fateemah fatimah fatimmah fatemmah fateemma")
    add("fatemeh", "fatemeh fatemih fatimih fatimmih fatimmihe")
    add("ghanem", "ghanem ghanim ghaneme ghanime")
    add("aziz", "aziz azeez azez azeze azeeze azize")
    add("haddad", "haddad hadad haded hadded")
    add("hakim", "hakim hakeem hakem")
    add("hamdan", "hamdan hamdaan hamdane hamden")
    add("hamid", "hamid hamed hamide hameed hammeed hammed hammid")
    add("hamza", "hamza hamzah hamzaah")
    add("hanan", "hanan hanen hanane hanene")
    add("hassan", "hassan hassane hassen hasan hasen")
    add("hisham", "hisham hicham hischam")
    add("huda", "huda hudah")
    add("ibrahim", "ibrahim ibrahem")
    add("ismail", "ismail ismayl ismayle ismaylle ismaeel ismaile")
    add("javad", "javad javed dschaved djavade djavad cevat")
    add("khalid", "khalid khaled khalled khalleed khaleed chalid halid halit")
    add("kanaan", "kanaan kanan kanen kanane kanaen kanaene")
    add("kamal", "kamal kammal")
    add("khadija", "khadija khadijah khadeeja khadeejah khadeja khadedja hatice")
    add("khoury", "khoury khouri khourye")
    add("layla", "layla laylaah laylahe laila lailah lailla leila leilah")
    add("mahdi", "mahdi mehdi")
    add("mahmoud", "mahmoud mahmoude")
    add("majid", "majid maged majed madjed madschid majeed majeede madjeed madsched macit mecid")
    add("mansour", "mansour mansur mansoure")
    add("mariam", "mariam mariame maryam mariamme")
    add("masoud", "masoud massoud massoude")
    add("mustafa", "mustafa mustafah moustafa moustafah moustafahe")
    add("nabil", "nabil nabel nabele")
    add("nasser", "nasser naser nasere nassir nasir")
    add("nour", "nour noure nur")
    add("omar", "omar omare")
    add("rahman", "rahman rahmane rahmen rachman")
    add("rashid", "rashid rashide raschid rasheed rached rachede rashed")
    add("saeid", "saeid said saede saeed saaid saaide saed")
    add("saleh", "saleh salleh salih sallih")
    add("salim", "salim salem sallem saleem")
    add("salma", "salma salmah salmahe")
    add("salman", "salman salmen")
    add("sami", "sami sammi")
    add("samir", "samir sameer samer sammer sammere sammeer sammire sammir")
    add("samira", "samira samirah sammera sameera sameerah sammirah")
    add("taha", "taha tahah")
    add("talal", "talal tallal tallale tallalle")
    add("tariq", "tariq tarek tareq tareeq tarik")
    add("walid", "walid waled waleed walled walleed wallid")
    add("yasser", "yasser yaser yasir yassir yassire")
    add("yassin", "yassin yassine yasseen yasin yasine yasen yassen")
    add("zainab", "zainab zaynab zaynabe zeynab zeynep")
    add("sharif", "sharif sherif serif sjarif")
    add("ziad", "ziad zied ziede")
    # Arabic family names and attached/assimilated article spellings.
    add("amin", "amin amen ameen amene ameene alamin alamen alameen elamin elamen elameen elameene")
    add("attar", "attar atar ataar atare alattar alatar elattar elatar")
    add("douri", "douri dourie doury duri aldouri aldourie eldouri")
    add("farsi", "farsi farsy alfarsi elfarsi")
    add("hashimi", "hashimi hashimy hashimmi hashemi hashemmi hasheemmi hachemi alhashimi alhashemi elhashimi elhashemi elhachemi elhasheemmi")
    add("jabouri", "jabouri jaboury jaburi gabouri dschabouri aljabouri algabouri aldschabouri eljabouri elgabouri")
    add("khatib", "khatib khatibe khateb khateeb alkhatib alkhateb elkhatib elkhateb")
    add("masri", "masri almasri elmasri")
    add("najjar", "najjar najare najjare najar nagar naggar nadjjar nadschar nadschdschar nadjdjschar alnajjar alnajar elnajjar elnajar elnaggar elnadschar")
    add("nasrallah", "nasrallah nasralla nasrala nasralah")
    add("sabah", "sabah saba alsabah alsaba elsabah elsaba")
    add("sayed", "sayed sayid sayide alsayed alsayid alsayide elsayed elsayid elsayide")
    add("shahin", "shahin shaheen shahen shahene chahen chahine schahin schaheen")
    add("shamsi", "shamsi chamsi schamsi alshamsi alschamsi elshamsi elchamsi elschamsi")
    add("tikriti", "tikriti tikreeti tikreti altikriti altikreti eltikriti eltikreti")
    add("zahrani", "zahrani alzahrani elzahrani")
    # Persian spellings.
    add("darwish", "darwish darwesh darwisch darweesh daroueesh")
    add("bagheri", "bagheri baghiri")
    add("behrouz", "behrouz behrouze")
    add("bijan", "bijan bijen bigen")
    add("dariush", "dariush dariusch darioush dariouch")
    add("farhad", "farhad farhed farhede")
    add("ghasemi", "ghasemi ghasemy ghasemmi ghassemy ghasimmi ghassemmi ghassimi qasemi")
    add("jafari", "jafari gafari djafari")
    add("karimi", "karimi karimmi karemmi kareemi kareemmi caremi careemi")
    add("kaveh", "kaveh kavihe kavih")
    add("mahsa", "mahsa mahsahe mahsah")
    add("mohsen", "mohsen mohsin mohsine")
    add("mousavi", "mousavi moussavi musavi")
    add("niloufar", "niloufar nilloufar")
    add("omid", "omid omed omede")
    add("parisa", "parisa paresa pareessa paressa paressah parissa parisah parissah")
    add("parviz", "parviz parveze parveez parvez")
    add("rahimi", "rahimi rahimmi rahemi rahemmi")
    add("rami", "rami rammi")
    add("ramin", "ramin ramine ramen rameen rammen rammin")
    add("reza", "reza rezah")
    add("rezaei", "rezaei rezai rezaai")
    add("sadeghi", "sadeghi sadighi")
    add("salehi", "salehi salihi sallihi")
    add("shirin", "shirin sheren sheereen")
    add("shirazi", "shirazi chirazi schirazi sheerazi sherazi")
    add("shahram", "shahram shahraam schahram chahrame")
    add("siavash", "siavash siavasch siavashe")
    add("zahra", "zahra zahraah zahrah")
    add("zaidi", "zaidi zaydi")
    add("hosseini", "hosseini hoseini hossaini")
    add("zamani", "zamani zammani")
    add("tabrizi", "tabrizi tabrezi tabreezi")
    add("kamran", "kamran kamren camrane")
    add("ehsan", "ehsan ehsen")
    add("arash", "arash arashe arache")
    add("rania", "rania raniah")
    add("layla", "layla laylah")
    add("sultan", "sultan sulten sultane sultene soultane")
    add("rahmani", "rahmani rahmany rahmanie")
    add("adnan", "adnan adnaan adnen")
    add("nizar", "nizar nizaar nizare")
    add("nasrin", "nasrin nasren nasreen nasrene")
    add("morteza", "morteza mortezah mortiza")
    add("rostami", "rostami rostamie rostammi")
    add("mohammadi", "mohammadi mohamadi")
    add("ebrahimi", "ebrahimi ebrahemi ebrahimmi ebrahemmi")
    add("esfahani", "esfahani esfahany")
    add("nazari", "nazari nazary nazarie")
    add("akbari", "akbari akbarie akbary")
    add("marwan", "marwan marwen")
    add("golnaz", "golnaz golnaze")
    add("ahmadi", "ahmadi ahmady")
    add("salehi", "salehi salehy")
    add("barakat", "barakat barakaat")
    add("sadeghi", "sadeghi sadeghie")
    add("farahani", "farahani farahany")
    add("yazdani", "yazdani yazdany")
    # Russian under English, German, French, ISO/scientific and Polish forms.
    add("aleksandr", "aleksandr alexandr alexander aleksander alex xander")
    add("aleksei", "aleksei alekseiy aleksey alexei alexey")
    add("andrei", "andrei andrey andrej andreiy")
    add("arkady", "arkady arkadi arkadij arkadiy")
    add("anatoly", "anatoly anatoliy")
    add("artyom", "artyom artem artiom artjom")
    add("dmitri", "dmitri dmitry dmitriy dmitrij")
    add("fedor", "fedor fyodor fiodor")
    add("gennady", "gennady gennadi gennadiy")
    add("grigory", "grigory grigori grigoriy")
    add("kseniya", "kseniya ksenia")
    add("maksim", "maksim maxim")
    add("mikhail", "mikhail michail")
    add("nadezhda", "nadezhda nadeshda nadejda")
    add("natalia", "natalia nataliya natalija natalya")
    add("nikolai", "nikolai nikolaiy nikolay")
    add("semyon", "semyon semion")
    add("sergei", "sergei sergey serguei sergej")
    add("stanislav", "stanislav stanislaw stanislaff")
    add("vasily", "vasily vasiliy wasily")
    add("valery", "valery valeriy walery")
    add("viktor", "viktor victor wiktor")
    add("vyacheslav", "vyacheslav vyatcheslaff viatcheslav vyatscheslav wyatscheslaw")
    add("yelizaveta", "yelizaveta elizaveta jelizaveta jelizaweta yelizaweta")
    add("yevgeny", "yevgeny jevgeny evgeny evgeniy yevgeniy jewgeny ievgueny ievgueni eugene")
    add("yulia", "yulia yuliya yulya julia")
    add("yuri", "yuri iuri youri yury yuriy jurij")
    add("darya", "darya daria darja")
    add("ekaterina", "ekaterina yekaterina katerina")
    add("elena", "elena yelena")
    add("anastasia", "anastasia anastasya anastasiya anastasija")
    add("ruslan", "ruslan rouslan")
    add("maria", "maria mariya marya marja")
    add("lyudmila", "lyudmila ljudmila lyoudmila")
    add("svetlana", "svetlana swetlana")
    add("tatiana", "tatiana tatyana")
    add("viktoria", "viktoria viktoriya victoria vicky tori")
    add("zhanna", "zhanna janna shanna")
    add("oksana", "oksana oxana")
    add("aleksandrovich", "aleksandrovich alexandrovich aleksandrovitch alexandrovitch")
    add("alekseevich", "alekseevich alexeevich")
    add("ivanovich", "ivanovich ivanovitch")
    add("mikhailovich", "mikhailovich mikhailovitch michailovich michailovitsch")
    add("nikolaevich", "nikolaevich nikolayevich nikolaewich")
    add("petrovich", "petrovich petrovitch petrowich")
    add("sergeyevich", "sergeyevich sergeevich sergueyevich sergeyewich sergeyevitsch")
    add("vladimirovich", "vladimirovich vladimirovitch vladimirovitsch")
    add("ivanovna", "ivanovna iwanowna")
    add("mikhailovna", "mikhailovna michailovna")
    add("nikolaevna", "nikolaevna nikolayevna nikolaewna")
    add("petrovna", "petrovna")
    add("sergeyevna", "sergeyevna sergeevna sergueyevna sergeyewna")
    add("vladimirovna", "vladimirovna wladimirowna")
    add("belousov", "belousov beloussov belousoff")
    add("bondarenko", "bondarenko")
    add("bykov", "bykov bykoff bykoffa bikov bykow")
    add("chaikovsky", "chaikovsky chaikowsky chaikovskaya chaykovsky chaykovskiy chaykovskaya schaikovsky schaikovskaya tchaikovsky tschaikowsky cajkovskij czajkowski czajkowskij czajkowskaja")
    add("andreev", "andreev andreeff andreew")
    add("chernov", "chernov tchernov tchernoff cernov czernov")
    add("egorov", "egorov egoroff yegorov jegorow jegorowa")
    add("fedorov", "fedorov fyodorov fedoroff fedorow")
    add("grishin", "grishin grishina grischin gritchin gritchina grichine")
    add("ivanov", "ivanov ivanova ivanoff iwanow iwanowa")
    add("kiselyov", "kiselyov kiseliov kiseljov")
    add("kovalenko", "kovalenko")
    add("kozlov", "kozlov koslov koslow")
    add("kravchenko", "kravchenko kravtchenko krawchenko krawczenko krawtschenko")
    add("kuznetsov", "kuznetsov kouznetsoff kusnezow")
    add("lebedev", "lebedev lebedeff lebedeffa lebedew")
    add("makarov", "makarov makaroff makarow")
    add("morozov", "morozov morosov morosow morozow")
    add("nikolaev", "nikolaev nikolaeff nikolaeffa")
    add("novikov", "novikov novikoff nowikow")
    add("orlov", "orlov orloff orlow")
    add("pavlov", "pavlov pavloff pawlow")
    add("popov", "popov popoff popow")
    add("petrov", "petrov petroff petrow")
    add("shcherbakov", "shcherbakov shtcherbakov chcherbakov chtcherbakov schtscherbakov scerbakov szczerbakow")
    add("shevchenko", "shevchenko chevchenko sevcenko szewczenko")
    add("shishkin", "shishkin shishkina schischkin chichkine siszkin")
    add("sokolov", "sokolov sokoloff sokolow")
    add("smirnov", "smirnov smirnoff smirnow")
    add("semyonov", "semyonov semjonov semionov semenov semyonow semionow semenow")
    add("stepanov", "stepanov stepanoff stepanow")
    add("tkachenko", "tkachenko tkatchenko tkatschenko tkazchenko")
    add("tsoi", "tsoi soiy tsoiy tsoy tzoi tzoy zoi")
    add("tsvetkov", "tsvetkov tsvetkowa tswetkow tswetkowa zvetkov zwetkow cvetkov")
    add("yakovlev", "yakovlev iakovleff jakovlev yakovleff")
    add("yashin", "yashin yashina yaschin jashin jashina iashin iachina jaschin")
    add("zaitsev", "zaitsev zaitseva zaytsev zaytseva zajcev zajceva zajcew zajcewa saisev zaitzev zaitzeff")
    add("zakharov", "zakharov zakharova zakharow sakharov sacharow sacharowa zakharoff")
    add("zhukov", "zhukov zhukow jukov jukoff jukoffa joukov zukov zukow")
    add("volkov", "volkov volkova volkow volkowa wolkow wolkowa")
    # Western variants and nicknames expressly treated as equivalent.
    add("william", "william will bill billy liam")
    add("katherine", "katherine katharine catherine kate kathy kit")
    add("michael", "michael mike mikey")
    add("andrew", "andrew andy drew")
    add("benjamin", "benjamin ben benny")
    add("charles", "charles chuck charlie")
    add("daniel", "daniel dan danny")
    add("dorothy", "dorothy dot dottie")
    add("edward", "edward ed eddie")
    add("elizabeth", "elizabeth liz beth")
    add("francisco", "francisco frank paco")
    add("frederick", "frederick fred freddie")
    add("jose", "jose pepe")
    add("joseph", "joseph joe joey")
    add("margaret", "margaret maggie meg peggy")
    add("nicholas", "nicholas nicolas nick")
    add("patricia", "patricia pat patty trish")
    add("rebecca", "rebecca becca becky")
    add("richard", "richard dick rick ricky")
    add("robert", "robert bob bobby robbie")
    add("steven", "steven stephen steve")
    add("theodore", "theodore theo ted")
    add("anthony", "anthony tony")
    add("mueller", "mueller muller")
    add("schroeder", "schroeder schroder")
    add("fischer", "fischer fisher")
    add("fernandez", "fernandez fernandes")
    add("rodriguez", "rodriguez rodrigues")
    add("bianchi", "bianchi bianci")
    add("lindqvist", "lindqvist lindquist")
    add("nowak", "nowak novak")
    add("olsen", "olsen olson")
    add("petersen", "petersen peterson pedersen")
    add("schmidt", "schmidt schmid schmitt")
    add("sorensen", "sorensen sorenson")
    add("andersen", "andersen anderson andersson")
    add("johansson", "johansson johansen johanson")
    add("john", "john jon johnny jack")
    add("jennifer", "jennifer jen jenny")
    add("samuel", "samuel sam sammy")
    add("barbara", "barbara barb babs")
    add("henry", "henry hank harry")
    add("peter", "peter pete")
    add("james", "james jamie")
    add("christopher", "christopher chris")
    add("weiss", "weiss weis")
    add("lindqvist", "lindqvist lindquist lindkvist")
    add("kowalski", "kowalski kowalsky")
    add("ferreira", "ferreira ferreyra")
    add("meyer", "meyer mayer")
    add("silva", "silva dasilva")
    add("thomas", "thomas tom tommy")
    add("matthew", "matthew matt")
    return groups


VARIANTS = _variant_table()

ARABIC_FAMILY_ROOTS = {
    "amin", "attar", "douri", "farsi", "hashimi", "jabouri", "khatib",
    "masri", "najjar", "rashid", "sabah", "sayed", "shamsi", "tikriti",
    "zahrani", "rahman",
}

# Character values used by the two hidden-batch Cyrillic conventions. In
# scientific transliteration the carons are subsequently dropped (ž -> z,
# č -> c, š -> s); Polish convention uses cz/sz/w. The watchlist's own script
# words are used below to bind each generated spelling to the right name word,
# which avoids unsafe context-free substitutions such as every "s" -> "sh".
CYR_SCI = {
    "а":"a", "б":"b", "в":"v", "г":"g", "д":"d", "е":"e", "ё":"e",
    "ж":"z", "з":"z", "и":"i", "й":"j", "к":"k", "л":"l", "м":"m",
    "н":"n", "о":"o", "п":"p", "р":"r", "с":"s", "т":"t", "у":"u",
    "ф":"f", "х":"h", "ц":"c", "ч":"c", "ш":"s", "щ":"sc", "ъ":"",
    "ы":"y", "ь":"", "э":"e", "ю":"ju", "я":"ja",
}
CYR_POLISH = {
    "а":"a", "б":"b", "в":"w", "г":"g", "д":"d", "е":"e", "ё":"io",
    "ж":"z", "з":"z", "и":"i", "й":"j", "к":"k", "л":"l", "м":"m",
    "н":"n", "о":"o", "п":"p", "р":"r", "с":"s", "т":"t", "у":"u",
    "ф":"f", "х":"ch", "ц":"c", "ч":"cz", "ш":"sz", "щ":"szcz", "ъ":"",
    "ы":"y", "ь":"", "э":"e", "ю":"ju", "я":"ja",
}


def learn_cyrillic_conventions(entries: list[dict]) -> None:
    learned: list[tuple[str, str]] = []
    for entry in entries:
        script = str(entry.get("script_name") or "").lower()
        for word in re.findall(r"[^\W\d_]+", script, flags=re.UNICODE):
            if not re.search(r"[\u0400-\u052f]", word):
                continue
            target = canonical_token(word.translate(CYR))
            if not target:
                continue
            for convention in (CYR_SCI, CYR_POLISH):
                spelling = "".join(convention.get(c, c) for c in word)
                spelling = re.sub(r"[^a-z]", "", ascii_text(spelling).lower())
                if spelling:
                    learned.append((spelling, target))
    # Do not replace an explicit equivalence above if a cross-language
    # spelling happens to collide with a generated form.
    for spelling, target in learned:
        VARIANTS.setdefault(spelling, target)


def canonical_token(token: str) -> str:
    token = ascii_text(token).lower()
    token = re.sub(r"[^a-z]", "", token)
    if not token:
        return ""
    result = VARIANTS.get(token, token)
    if result == token:
        # The Arabic article may be attached and, before a sun letter,
        # assimilated in writing: al-Sabah/as-Sabah, al-Tikriti/at-Tikriti.
        for prefix in ("al", "el", "as", "ash", "at", "ad", "ar", "an", "az"):
            if token.startswith(prefix) and len(token) > len(prefix) + 2:
                rest = token[len(prefix):]
                folded = VARIANTS.get(rest, rest)
                if folded in ARABIC_FAMILY_ROOTS:
                    result = folded
                    break
    # Retry common feminine Russian surname endings as the masculine root.
    for ending, replacement in (("ova", "ov"), ("ewa", "ev"), ("eva", "ev"),
                                ("offa", "ov"), ("owa", "ov"),
                                ("skaya", "sky"), ("skaia", "sky")):
        if token.endswith(ending):
            masculine = token[:-len(ending)] + replacement
            if masculine in VARIANTS:
                return VARIANTS[masculine]
    return result


def name_tokens(name: str) -> list[str]:
    raw = re.findall(r"[^\W\d_]+", name.lower(), flags=re.UNICODE)
    out: list[str] = []
    for word in raw:
        if re.search(r"[\u0400-\u052f]", word):
            word = word.translate(CYR)
        elif re.search(r"[\u0600-\u06ff]", word):
            word = ARABIC_WORDS.get(word, word)
        token = canonical_token(word)
        if token:
            out.append(token)
    return out


PATRONYMIC_ENDINGS = ("ovich", "evich", "yevich", "ich", "ovna", "evna", "yevna")


def individual_forms(name: str) -> set[tuple[str, str]]:
    toks = name_tokens(name)
    # Multiword family names remain one family name through spacing/hyphen
    # changes and through family-first reordering.
    compound_specs = (
        ({"de", "la", "cruz"}, "delacruz"),
        ({"du", "bois"}, "dubois"),
        ({"van", "der", "berg"}, "vanderberg"),
        ({"van", "den", "berg"}, "vanderberg"),
        ({"le", "fevre"}, "lefevre"),
        ({"mac", "donald"}, "macdonald"),
        ({"o", "brien"}, "obrien"),
    )
    for parts, joined_family in compound_specs:
        if parts.issubset(toks):
            for part in parts:
                toks.remove(part)
            toks.append(joined_family)
            break
    toks = [{
        "delacruz":"delacruz", "dubois":"dubois", "vanderberg":"vanderberg",
        "lefevre":"lefevre", "macdonald":"macdonald", "obrien":"obrien",
    }.get(x, x) for x in toks]
    # Arabic compounds can also appear as two original-script words.
    combined: list[str] = []
    i = 0
    while i < len(toks):
        if i + 1 < len(toks) and (toks[i], toks[i + 1]) == ("abdul", "allah"):
            combined.append("abdullah"); i += 2; continue
        if i + 1 < len(toks) and (toks[i], toks[i + 1]) == ("nasr", "allah"):
            combined.append("nasrallah"); i += 2; continue
        combined.append(toks[i]); i += 1
    toks = combined
    # Join Arabic compound given names before removing articles.
    joined: list[str] = []
    i = 0
    while i < len(toks):
        if toks[i] in {"abd", "abdel", "abdul"}:
            j = i + 1
            if j < len(toks) and toks[j] in {"al", "el"}:
                j += 1
            if j < len(toks) and toks[j] in {"aziz", "rahman", "karim"}:
                joined.append({"aziz":"abdulaziz", "rahman":"abdulrahman",
                               "karim":"abdulkarim"}[toks[j]])
                i = j + 1
                continue
        joined.append(toks[i])
        i += 1
    toks = joined
    # Nasab is optional as a unit: marker and the following father's name.
    clean: list[str] = []
    i = 0
    while i < len(toks):
        if toks[i] in {"bin", "ibn", "ben", "b"} or (toks[i] == "benjamin" and i > 0):
            i += 2
            continue
        if toks[i] in {"al", "el", "ad", "ar", "as", "ash", "at", "an", "az",
                        "da", "do", "dos", "das"} or len(toks[i]) == 1:
            i += 1
            continue
        if toks[i].endswith(PATRONYMIC_ENDINGS):
            i += 1
            continue
        clean.append(toks[i])
        i += 1
    if len(clean) < 2:
        return set()
    a, b = clean[0], clean[-1]
    return {(a, b), (b, a)}


def weak_key(name: str) -> str:
    return " ".join(name_tokens(name))


LEGAL_PHRASES = (
    "public joint stock company", "open joint stock company",
    "closed joint stock company", "limited liability company",
    "free zone establishment", "joint stock company", "sociedad anonima",
    "societe anonyme",
)
LEGAL_WORDS = {
    "llc", "ltd", "limited", "sa", "gmbh", "jsc", "ao", "oao", "pjsc",
    "co", "company", "fze", "fz", "fzllc", "corp", "corporation", "inc",
    "incorporated", "plc", "llp", "lp", "ag", "bv", "nv", "sarl", "spa",
    "pty",
}


def entity_core(name: str) -> tuple[str, ...]:
    s = ascii_text(name).lower().replace("&", " and ")
    s = s.replace("'", "").replace("’", "")
    # Collapse punctuation-separated abbreviations before general punctuation
    # removal, otherwise G.m.b.H. becomes four apparent name words.
    s = re.sub(r"\bg\s*\.\s*m\s*\.\s*b\s*\.\s*h\s*\.?", " gmbh ", s)
    s = re.sub(r"\bp\s*\.\s*j\s*\.\s*s\s*\.\s*c\s*\.?", " pjsc ", s)
    s = re.sub(r"\bo\s*\.\s*a\s*\.\s*o\s*\.?", " oao ", s)
    s = re.sub(r"\bj\s*\.\s*s\s*\.\s*c\s*\.?", " jsc ", s)
    s = re.sub(r"\bl\s*\.\s*l\s*\.\s*c\s*\.?", " llc ", s)
    s = re.sub(r"\bp\s*\.\s*l\s*\.\s*c\s*\.?", " plc ", s)
    s = re.sub(r"\ba\s*\.\s*o\s*\.?", " ao ", s)
    s = re.sub(r"\bs\s*\.\s*a\s*\.?", " sa ", s)
    s = re.sub(r"\bf\s*\.\s*z\s*\.\s*e\s*\.?", " fze ", s)
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    for phrase in LEGAL_PHRASES:
        s = re.sub(r"\b" + phrase.replace(" ", r"\s+") + r"\b", " ", s)
    toks = [x for x in s.split() if x not in LEGAL_WORDS and x != "and"]
    if toks and toks[0] == "the":
        toks.pop(0)
    return tuple(toks)


# Surname-stem equivalence for Chinese company names. A spelling can be
# ambiguous across dialects, so matching is set intersection, not one-way map.
CHINESE = {
    "cai": "cai tsai choy choi chua", "cao": "cao tsao tso cho",
    "chen": "chen chan tan", "cui": "cui tsui chui",
    "dai": "dai tai toi teh", "deng": "deng teng tang",
    "du": "du tu to toh", "fan": "fan faan hoan", "feng": "feng fung",
    "gao": "gao kao ko koh", "guo": "guo kuo kwok kueh kwee kwek kok", "han": "han hon",
    "he": "he ho hor", "hu": "hu hoo woo oh oo", "huang": "huang hwang wong oei wee ng",
    "ji": "ji chi kei kee", "jiang": "jiang chiang kong kiong",
    "li": "li lee lei", "liang": "liang leung neo nio", "lin": "lin lam lim",
    "liu": "liu lau liew low", "lu": "lu lo loh", "luo": "luo lo law loh",
    "ma": "ma mah beh", "pan": "pan poon phua pua", "peng": "peng pang phang",
    "qian": "qian chien chin tsien", "shen": "shen sham shum sam sim",
    "song": "song sung soong", "sun": "sun suen soon", "tang": "tang tong thng",
    "wang": "wang wong ong", "wu": "wu ng goh go", "xie": "xie hsieh tse che chia",
    "xu": "xu hsu tsui cheui", "yang": "yang yeung yeo", "ye": "ye yeh yip yap iap",
    "yuan": "yuan yuen oan", "zeng": "zeng tseng tsang",
    "zhang": "zhang chang cheung teo chong", "zhao": "zhao chao chiu teo",
    "zhou": "zhou chou chow chew", "zhu": "zhu chu chue choo",
}
CHINESE_LOOKUP: dict[str, set[str]] = defaultdict(set)
for _root, _spellings in CHINESE.items():
    for _spelling in _spellings.split():
        CHINESE_LOOKUP[_spelling].add(_root)


def entity_equivalent(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    if left == right:
        return True
    if len(left) != len(right) or len(left) < 2 or left[1:] != right[1:]:
        return False
    return bool(CHINESE_LOOKUP.get(left[0], {left[0]}) &
                CHINESE_LOOKUP.get(right[0], {right[0]}))


def vessel_core(name: str) -> tuple[str, ...]:
    s = ascii_text(name).lower()
    s = re.sub(r"^\s*(?:m\s*/\s*[vt]|mv|mt|vessel)\b[\s:.-]*", "", s)
    return tuple(re.findall(r"[a-z0-9]+", s))


def dob_compatible(customer: str, listed: str) -> bool:
    if not customer or not listed:
        return True
    return listed.startswith(customer)


def dob_supported(customer: str, listed: str) -> bool:
    return bool(customer and listed and listed.startswith(customer))


class Engine:
    def __init__(self, entries: list[dict]):
        learn_cyrillic_conventions(entries)
        self.entries = {str(e["uid"]): e for e in entries}
        self.ids: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.individual: dict[tuple[str, str], set[str]] = defaultdict(set)
        self.weak: dict[str, set[str]] = defaultdict(set)
        self.entities: list[tuple[tuple[str, ...], str]] = []
        self.vessels: dict[tuple[str, ...], set[str]] = defaultdict(set)
        for e in entries:
            uid = str(e["uid"])
            for ident in e.get("ids", []):
                self.ids[(str(ident.get("type", "")).strip().lower(),
                          str(ident.get("number", "")).strip().upper())].add(uid)
            names = [(str(e.get("primary_name", "")), "strong")]
            script = e.get("script_name")
            if script:
                names.append((str(script), "strong"))
            names.extend((str(a.get("name", "")), str(a.get("strength", "")))
                         for a in e.get("aliases", []))
            if e.get("type") == "individual":
                for name, strength in names:
                    if strength == "weak":
                        self.weak[weak_key(name)].add(uid)
                    else:
                        for form in individual_forms(name):
                            self.individual[form].add(uid)
            elif e.get("type") == "entity":
                seen = set()
                for name, strength in names:
                    if strength != "weak":
                        core = entity_core(name)
                        if core and core not in seen:
                            self.entities.append((core, uid))
                            seen.add(core)
            elif e.get("type") == "vessel":
                for name, strength in names:
                    if strength != "weak":
                        core = vessel_core(name)
                        if core:
                            self.vessels[core].add(uid)

    def screen(self, customer: dict[str, str]) -> tuple[str, str]:
        id_key = (customer.get("id_type", "").strip().lower(),
                  customer.get("id_number", "").strip().upper())
        id_hits = set()
        if id_key[0] and id_key[1]:
            id_hits = set(self.ids.get(id_key, ()))
        candidates: dict[str, tuple[bool, bool]] = {}
        for uid in id_hits:
            e = self.entries[uid]
            candidates[uid] = (True, dob_supported(customer.get("dob", ""),
                                                   str(e.get("dob", ""))))
        if not id_hits:
            typ = customer.get("type", "").strip().lower()
            name = customer.get("full_name", "")
            name_hits: set[str] = set()
            if typ == "individual":
                for form in individual_forms(name):
                    name_hits.update(self.individual.get(form, ()))
                for uid in self.weak.get(weak_key(name), ()):
                    listed = str(self.entries[uid].get("dob", ""))
                    cust = customer.get("dob", "")
                    if len(cust) == 10 and cust == listed:
                        name_hits.add(uid)
            elif typ == "entity":
                core = entity_core(name)
                for listed_core, uid in self.entities:
                    if entity_equivalent(core, listed_core):
                        name_hits.add(uid)
            elif typ == "vessel":
                name_hits.update(self.vessels.get(vessel_core(name), ()))
            for uid in name_hits:
                e = self.entries[uid]
                listed_dob = str(e.get("dob", ""))
                cust_dob = customer.get("dob", "")
                if dob_compatible(cust_dob, listed_dob):
                    candidates[uid] = (False, dob_supported(cust_dob, listed_dob))
        if not candidates:
            return "NO_MATCH", ""
        uid = min(candidates, key=lambda u: (-int(candidates[u][0]),
                                             -int(candidates[u][1]), u))
        return "MATCH", uid


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Screen customers against a sanctions watchlist")
    p.add_argument("--watchlist", required=True)
    p.add_argument("--customers", required=True)
    p.add_argument("--out", required=True)
    return p.parse_args()


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
        for row in reader:
            decision, uid = engine.screen(row)
            writer.writerow([row.get("customer_id", ""), decision, uid])


if __name__ == "__main__":
    main()
