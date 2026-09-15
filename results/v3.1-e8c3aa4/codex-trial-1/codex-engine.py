#!/usr/bin/env python3
"""Deterministic, standard-library sanctions name screening.

The program deliberately uses linguistic equivalence rules rather than a
general edit-distance threshold. A close spelling of a different substantive
name word is not a match.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from collections import defaultdict


# Each row is an equivalence class. The first spelling is the internal form.
# These include English/French/German/Polish/Gulf spellings, Turkish and
# Malay/Indonesian forms, and unaccented scientific Russian transliteration.
TOKEN_GROUPS = r"""
muhammad mohammed mohammad mohamed mohamad muhamed muhammed muhamad mehmet
ahmad ahmed achmad ahmet
jamal jammal gamal cemal djamal
hassan hasan hasen hassen
hussein husain hussain husayn hossein hosein hosain huseyin
yusuf yusof yusoof yussof yussoof yussuf youssef yousef yusef yousuf joesoef
sharif shareef sherif shereef sjarif serif
qasim kasim kaseem kasseem kasem
khalid khaled khalleed
khadija khadejah khadeejah khadijah
abdullah abdulla abdollah abdolla abdola abdolah
abdulaziz abdelaziz abdolaziz abdulazez abduazez
abdulkarim abdulkarem abdelkarim abdelkarem abdolkarem
abdulrahman abdulrahmen abdelrahman abdelrahmen abdolrahman abdolrahmen abdurrahman abdurrahmen abdalrahman
salim saleem salem salleem sallem
hamid hamed hameed hammed hammeed
walid waled walled waleed
tariq tarik tarek tareq tareeq
rashid rashed rasheed
ziad zied ziyad
faisal faysal fayssal
ismail ismayl
mustafa mustafah
kamal kammal
karim karem kareem
marwan marwen
bilal billal
samir sameer sammeer
sami sammy sammi
fatima fatimah fatema fatemah fateemma fatimmih
aisha aishah ayesha
amina aminah ameenah
salma salmah
huda hudah
layla laylah laila lailah leila leillah
rania raniah
hanan hanen
nabil nabel nabeel
adnan adnen
saeed saaid saed saeid said sayeed
majed majeed majid
nour noor nur
zaynab zainab
nasser naser nasir nassir
talal tallal
ibrahim ibrahem ibraheem ebrahim
hamza hamzah
aziz azeez azez
amin amen ameen amine
sayed sayid
mahmud mahmoud
mansur mansour
omar umar
yasser yasir
parviz parvez parveez
shirin sheren sheereen
niloufar nilloufar nilufar
kaveh kavih
bijan bigen bijen
reza rezah
ramin rammen rammeen
mohsen mohsin
morteza mortizah murtaza
samira samerah samera
javad javed jawad
rami rammi
dariush darioush
siavash siyavash
kamran kamren
parisa pareesah parisah paresa
abbas abas
masoud massoud
farhad farhed
dalal dallal
kanaan kanan
khadija khadeega khadiga
zaydi zaidi
taha tahah
salman salmen
ghanem ghanim
hamdan hamden
awad awed awaad aouad aoued
fares faris
farsi farsy
darwish darwesh darweesh
sabah saba sabahe
najjar najar nagar
haddad hadad haded hadded
yassin yasin yasen yaseen yasseen
shaheen shahin shahen
khatib khateb khateeb
nasrallah nasrala nasralla nasralah
tikriti tikreti takriti
masri masry
zahrani zahrany
douri duri
jabouri gabouri jabury
barakat barakaat
sultan sulten
hakim hakem
saleh salih sallih
sadeghi sadighi sadeqi
rezaei rezai rezaai
ghasemi ghassemi ghassemmi ghassimmi qasemi
karimi karemmi kareemi kareemmi
rahimi rahemi rahemmi
hosseini hosaini hossaini husseini
rostami rostammi
salehi salihi sallihi sallehi
shirazi sherazi sheerazi
ebrahimi ebrahemi ebrahemmi ebraheemi
hashemi hashimi hashemmi hashimmi khashimi
mohammadi mohamadi
mousavi musavi moosavi moussavi
tabrizi tabrezi
bagheri baghiri
zamani zammani
esfahani isfahani
yazdani yazdany
tehrani tihrani
kermani kirmani
mahmoudi mahmudi
moradi muradi
nazari nazary
alexander aleksandr alexandr xander sasha
aleksei alexei alexey aleksey
yevgeny evgeny eugene evgeni evgeniy jewgeni
sergei sergey serguei sergej sergeiy
dmitri dmitry dmitriy dmitrii
yuri yuriy yurii jurij
artyom artem artiom
semyon semen semion
fedor fyodor fiodor fjodor
ekaterina yekaterina katerina
yulia yuliya julia yulya
maria mariya marya
viktoria viktoriya victoria
anastasia anastasiya anastasya
natalia nataliya natalya
oksana oxana
kseniya ksenia
nikolai nikolay nikolaiy
andrei andrey andreiy
maksim maxim
vasily vasili vassily
vyacheslav viacheslav
gennady gennadi gennadiy
grigory grigori grigorii
arkady arkadi arkadiy
tatiana tatyana
elena yelena
elizaveta yelizaveta
zhanna janna
valery valeriy
zhukov zhukoff zukov zukoff schukow
shevchenko sevcenko schewtschenko
chaikovsky tchaikovsky chaikovskiy cajkovskij cajkovskiy cajkovsky czajkowski tschaikowsky czaikowsky zchaikowsky
tsoy tsoi tsoiy coj
shcherbakov scerbakov sherbakov
chernov cernov
tsvetkov cvetkov
yashin jasin
kiselyov kiselev kiseliov kiseljov
semyonov semenov semionov
fedorov fyodorov fedoroff fjodorow
egorov yegorov jegorov
zaitsev zajtsev
zakharov zaharov
shishkin siskin shischkin
tkachenko tkacenko
grishin grisin
kuznetsov kuznecov
novikov nowikow
smirnov smirnoff
popov popoff
volkov volkoff
ivanov ivanoff
petrov petroff
pavlov pawlow
orlov orloff
nikolaev nikolajew
belousov beloussov
bykov bykow
kozlov koslov koslow
makarov makaroff
morozov morosov
sokolov sokoloff
stepanov stepanoff
kovalenko kowalenko
kravchenko kravcenko krawtschenko
lebedev lebedew
william bill billy will
katherine catherine kathryn kate kathy katie cathy
theodore ted theo
frederick fred freddie
victoria vicky tori
rebecca becca
christopher chris kit
james jim jimmy jamie
samuel sam
elizabeth elisabeth liz beth
robert bob rob robbie
joseph joe joey
margaret maggie meg
susan suzy susie
nicholas nick nicolas
richard rich ricky
dorothy dot dottie
andrew drew andy
francisco frank paco
charles charlie chuck
patricia patty trish
peter pete
henry hank
michael mike
jennifer jen jenny
anthony tony
barbara babs
steven stephen steve
edward ed eddie
weiss weisz
mueller muller
fernandez fernandes
schmidt schmid schmitt
novak nowak
kowalski kowalsky
andersen anderson andersson
johansson johanson johansen
larsen larson
olsen olson
petersen peterson pedersen
lindqvist lindquist lindkvist
sorensen sorenson srensen
rodriguez rodrigues
ferreira ferreyra
bianchi bianci
mayer meier meyer
schroder schroeder
macdonald mcdonald

# Additional systematic French, German, Polish, Gulf and Malay spellings.
abdullah abdulah abdula abdoolla abdoollah
abdulaziz abduazize
abdulkarim abdulkareem
adnan adnane
amir ameer amer
amina amena ameena
anwar anware
arash arasch
babak babake babaak
bijan bijaan bidjane
bilal billaal billale billalle
bashar bashare
dalal dallalle
dariush dariuche darouishe
ehsan ehsen ehsaan ehsane
fahd fahde
faisal faissal faissale
farhad farhade
fatima fateemah fateemmah fatemmeh fatimma fatimih
fatima fatemeh
aisha aischa
golnaz golnaze golnaaz
hamid hammid hamede hammeede
hassan hassaan
hisham hicham
huda houdah hudahe
hussein hosaine hossain housein husein
ismail ismaille ismayle
jamal gammal dschammal
javad djaved djavede djavade
kamal kamaal kammaal cammalle
kamran camren camrane
kaveh cavih cavihe
khadija khadeeja khadedjah khadedschah
khalid khaleed khallid khallide
layla lailla leilla laylaah laillah
mahdi mahdy
mehdi mehdie
mahmoud mahmoude
mahsa mahsah mahsahe
majed maged madscheed majeede majede
mansour mansoure
maryam mariam maryame maryaam mariame
marwan marwaan marouen marouane
mohsen mohsine
morteza mortiza mortezah
mustafa mustafaa moustafah
nabil nabele
nasrin nasreen nasrene
nizar nizare
omid omed omeed omide
omar omare
parisa parissa paressa paressah pareesa parissah
parviz parveze
ramin ramen
rashid rasheede
saeed saede
salim sallim
saleh salleh
samir samire sammer
samira sameerah sammeera
sami samy sammie
shahram schahram shahraam shahramme
shirin schirin shirine scheereen sheereene cheereen cheren
siavash siavache siavach
talal tallalle
tariq tareek tareegh
walid wallid
yasser yaser yassir
zahra zahrah
zaynab zainaab
ziad ziade
barakat baracat barakate
darwish darweshe darouishe
douri doury
ebrahimi ebrahimmie ebraheemmi
esfahani esfahanie
farahani farahanie farahany
ghanem ghanime ghanimme
ghasemi ghasemy ghasimi
haddad hadade
hakim hakeem hakeeme hakime hakimme
hashemi hachemi hachimi haschimi haschimmi hasheemmi hashemmy hashimy hashimmie
hashemi hasyimi hasjimi
hosseini hoseini hosaine
jabouri jaboury jabourie aljabourie djabouri dschabouri
jafari djafari dschafari
kanaan kanaen kanen
karimi karemi karimmi caremmi
kermani kermany kermanie
khatib khatibe khateebe
khoury khourye
mahmoudi mahmoudy
masri masrie
mohammadi mohamady mohamadie
moradi moradie
mousavi moussavy mousavie
nasrallah nasrallaa
najjar naggar nadschdschar
attar atar
nazari nazarie
qasim qassem qassim qasem kassim
rahimi rahimmmi rahimmie raheemi rahimie
rahimi rahimmi
rezaei rezaey
sadeghi sadeghie
salman salmane
sayid sayed elsayid
shaheen schahin
shamsi chamsi shamsie
shirazi shirazie scheerazi cheerazi
tabrizi tabreezi
tehrani tehranie
tikriti tikreeti tikritie
yassin yassene yasene
zahrani zahranie
zaydi zaidy zaidie

# Continental European and scientific Cyrillic romanization.
aleksei alexeij
anastasia anastasja
andreev andreeff
darya darja
dmitri dmitrij
yevgeny jewgeny jevgeny ievgeny
fedorov fedorow
grishin grischin gristschin
ivan iwan
kiselyov kiselyow kiselyoff kiseliow kiselew kiseljow kiselioff
kozlov kozlow kozloff
kravchenko kravtchenko kravtschenko krawczenko kravczenko
kuznetsov kusnezow kouznetzoff kuznetsoff
lebedev lebedeff
lyudmila lyoudmila
makarov makarow
mikhail mihail michail
morozov morozoff
nadezhda nadeshda nadejda
nikolaev nikolaew nikolaeff
novikov nowikow novikoff
orlov orlow
pavel pawel
pavlov pawlow pavloff
petrov petrow
popov popow
ruslan rouslan
semyonov semionow semjonow semenow
sergei serguey
shcherbakov shtcherbakov tchtcherbakov chcherbakov
shevchenko schevchenko szevchenko shevczenko
shishkin chichkin sziszkina
sokolov sokolow
stanislav stanislaw stanislaff
svetlana swetlana
tkachenko tkatchenko tkatschenko
tsvetkov tzvetkov tswetkow zwetkow cwetkow svetkov
tsoy tso tzoy zoy coiy
valery walery
vasily wasily
viktor wiktor
viktoria wiktorya
vladimir wladimir
vyacheslav wjacheslaw vyatcheslaff
yashin jashin jaschin jaszin
elena yelena jelena
elizaveta yelizaveta jelisaweta ielizaveta
yuri yury yurij juriy
zaitsev zaitzev zaicew
zakharov zakharow zakharoff sacharow
zhanna schanna shanna stschanna
zhukov shukov zhukow joukoff
andreev andreew
belousov belousow belousoff
egorov egorow yegorow yegoroff
kuznetsov kuznetzov kouznetsov
morozov morozow
volkov wolkov wolkow
tsvetkov tzvetkoff
smirnov smirnow smirnoff
kuznetsov kuznezov

# Additional Western orthography and unambiguous diminutives.
weiss weis
fischer fisher
john johnny jon
john jack
benjamin ben benny
henry harry
alexander alex
elizabeth betty
susan sue
matthew matt
daniel dan danny
richard dick rick
michael mikey mick
robert bobby
barbara barb
patricia pat
jose pepe
peter pedro
thomas tom tommy
theodore teddy
rebecca becky
elizabeth lizzy
margaret peggy
katherine kat
william liam

# Remaining regular long-vowel and final-vowel renderings.
ahmadi ahmady
abbas abaas
awad aouade
aziz azeze
hamdan hamdane
karim karem kareeme
khalid khalled
rami ramy
taha tahaa
timur timour
viktoria viktorya
aleksei alexeiy
elizaveta elisaveta yelizaweta
zaitsev saisev
mahmoud mahmud
mansour mansur
victoria viktoria viktoriya wiktorya viktorya

# Turkish conventions for Arabic-origin names.
omar omer
aisha ayse
fatima fatma
maryam meryem
zaynab zeynep
amina emine
amir emir
anwar enver
bashar bessar
hamid hamit
hisham hisam
kamal kemal
khadija hatice
khalid halit halid
mahmoud mahmut
majed mecit macit
marwan mervan
nabil nebil
rashid resit rasit
saeed sait
abdulkarim abdulkerim
salma selma
walid velid
hakim hekim
salman selman
darwish dervis
najjar neccar
khatib hatip
sayid seyyid seyit
shamsi semsi
zahrani zehrani
amin emin

# Malay/Indonesian forms, including the pre-1972 oe/dj/sj orthography.
muhammad mochamad mochammad muchammad
hussein hoesin hoesein hoessein husin
omar oemar
rahman rachman
shaheen sjahin
shamsi sjamsi syamsi
yassin jasin
mustafa mustofa
khalid chalid
shaheen sahin
shaheen syahin
karim kerim
salim selim
aisha aisyah aisjah
rashid rasyid
sharif syarif
yusuf jusuf
muhammad moehammad
abdullah abdoellah
abdulaziz abdoelaziz
abdulkarim abdoelkarim
abdulrahman abdoelrachman

# Further unaccented scholarly (scientific) Cyrillic transliterations.
aleksei aleksej
andrei andrej
yevgeny evgenij
vasily vasilij
vyacheslav vjaceslav
gennady gennadij
grigory grigorij
arkady arkadij
tatiana tatjana
valery valerij
anastasia anastasija
natalia natalja
kseniya ksenija
nikolai nikolaj
yulia julija
maria marija
nadezhda nadezda
zhanna zanna
zaitsev zajcev
yakovlev jakovlev
zakharov zacharov

# Other common French/German/Polish forms covered by the policy.
jamal djamel
hisham hichem
hussein hocine houcine
rashid rachid
kamal kamel
sharif cherif
masoud messaoud massud
dmitri dimitri
yuri youri iouri juri
fedor feodor
vasily wassili wasilij
vyacheslav wjatscheslaw wiaczeslaw
sergei siergiej
yevgeny jewgienij
gennady giennadij
zhukov zukow
shevchenko szewczenko
chaikovsky tschaikowski
shcherbakov szczerbakow
chernov czernow
tsvetkov cwietkow
kuznetsov kuzniecow
ivanov iwanow
petrov pietrow
zaitsev zajcew
yakovlev jakowlew
tkachenko tkaczenko
bykov bykoff
shirazi cherazi chirazi
hashemi hachimmi hashimie
javad javade
kamran kamrene
maria marja
nikolai nikolaij
shevchenko schevtschenko
tsoy tzoi
yassin yassen
"""

CANON: dict[str, str] = {}
for _line in TOKEN_GROUPS.splitlines():
    if _line.lstrip().startswith('#'):
        continue
    _words = _line.split()
    if _words:
        for _word in _words:
            CANON[_word] = _words[0]


# Original-script vocabulary gives reliable word-level transliteration even
# where a list record has no Latin spelling at all.
SCRIPT_WORDS_TEXT = r"""
Борис=boris Денис=denis Иванов=ivanov Андреева=andreev Людмила=lyudmila Егоров=egorov Николаева=nikolaev Иванова=ivanov Елизавета=elizaveta Фёдорова=fedorov Зайцева=zaitsev Новикова=novikov Елена=elena Егорова=egorov Цветков=tsvetkov Волкова=volkov Макарова=makarov Павлова=pavlov Лебедева=lebedev Яковлева=yakovlev Виктор=viktor
كنعان=kanaan حميد=hamid فراهانی=farahani مهسا=mahsa ابراهیمی=ebrahimi محسن=mohsen النجار=najjar امید=omid احسان=ehsan نسرین=nasrin بابک=babak
Александр=aleksandr Александрович=aleksandrovich Алексеевич=alekseevich Алексей=aleksei Анастасия=anastasia Анатолий=anatoly Андреев=andreev Андрей=andrei Анна=anna Аркадий=arkady Артём=artyom
Белоусов=belousov Белоусова=belousova Бондаренко=bondarenko Быков=bykov Быкова=bykova Валентина=valentina Валерий=valery Василий=vasily Виктория=viktoria Владимир=vladimir Владимирович=vladimirovich Владимировна=vladimirovna Волков=volkov Вячеслав=vyacheslav
Галина=galina Геннадий=gennady Григорий=grigory Гришин=grishin Гришина=grishina Дарья=darya Дмитрий=dmitri Евгений=yevgeny Екатерина=ekaterina Жанна=zhanna Жуков=zhukov Жукова=zhukova Зайцев=zaitsev Захаров=zakharov Иван=ivan Иванович=ivanovich Ивановна=ivanovna Игорь=igor Ирина=irina
Киселёв=kiselyov Киселёва=kiselyova Коваленко=kovalenko Козлов=kozlov Козлова=kozlova Константин=konstantin Кравченко=kravchenko Ксения=kseniya Кузнецов=kuznetsov Кузнецова=kuznetsova Лебедев=lebedev Леонид=leonid Макаров=makarov Максим=maksim Марина=marina Мария=maria Михаил=mikhail Михайлович=mikhailovich Михайловна=mikhailovna
Морозов=morozov Морозова=morozova Надежда=nadezhda Наталья=natalia Николаев=nikolaev Николаевич=nikolaevich Николаевна=nikolaevna Николай=nikolai Новиков=novikov Оксана=oksana Олег=oleg Ольга=olga Орлов=orlov Орлова=orlov Павел=pavel Павлов=pavlov Петров=petrov Петрова=petrov Петрович=petrovich Петровна=petrovna Попов=popov Попова=popov
Роман=roman Руслан=ruslan Светлана=svetlana Семён=semyon Семёнов=semyonov Семёнова=semyonov Сергеевич=sergeyevich Сергеевна=sergeyevna Сергей=sergei Смирнов=smirnov Смирнова=smirnov Соколов=sokolov Соколова=sokolov Станислав=stanislav Степанов=stepanov Степанова=stepanov Татьяна=tatiana Тимур=timur Ткаченко=tkachenko
Фёдор=fedor Фёдоров=fedorov Цветкова=tsvetkov Цой=tsoy Чайковская=chaikovsky Чайковский=chaikovsky Чернов=chernov Чернова=chernov Шевченко=shevchenko Шишкин=shishkin Шишкина=shishkin Щербаков=shcherbakov Щербакова=shcherbakov Юлия=yulia Юрий=yuri Яковлев=yakovlev Яшин=yashin Яшина=yashin
آرش=arash أحمد=ahmad أمينة=amina أنور=anwar إبراهيم=ibrahim إسماعيل=ismail احمدی=ahmadi اصفهانی=esfahani الأمين=amin التكريتي=tikriti الجبوري=jabouri الخطيب=khatib الدوري=douri الرحمن=rahman الرشيد=rashid الزهراني=zahrani السيد=sayid الشمسي=shamsi الصباح=sabah العزيز=aziz العطار=attar الفارسي=farsi الكريم=karim الله=allah المصري=masri الهاشمي=hashemi
امیر=amir اکبری=akbari باقری=bagheri بركات=barakat بشار=bashar بكر=bakr بلال=bilal بن=bin بهروز=behrouz بیژن=bijan تبریزی=tabrizi تهرانی=tehrani جعفری=jafari جمال=jamal جواد=javad حداد=haddad حسن=hassan حسين=hussein حسین=hussein حسینی=hosseini حكيم=hakim حمدان=hamdan حمزة=hamza حمید=hamid حنان=hanan خالد=khalid خديجة=khadija خوري=khoury
داریوش=dariush درويش=darwish دلال=dalal راشد=rashid رامي=rami رامین=ramin رانيا=rania رحمانی=rahmani رحیمی=rahimi رستمی=rostami رضا=reza رضایی=rezaei زمانی=zamani زهرا=zahra زياد=ziad زيدي=zaydi زينب=zaynab سامي=sami سعيد=saeed سعید=saeed سلطان=sultan سلمان=salman سلمى=salma سليم=salim سمير=samir سميرة=samira سیاوش=siavash شاهين=shaheen شهرام=shahram شیرازی=shirazi شیرین=shirin
صادقی=sadeghi صالح=saleh صالحی=salehi طارق=tariq طلال=talal طه=taha عائشة=aisha عباس=abbas عبد=abd عدنان=adnan عزيز=aziz علي=ali عمر=omar عوض=awad غانم=ghanem فارس=fares فاطمة=fatima فاطمه=fatima فرهاد=farhad فهد=fahd فيصل=faisal قاسم=qasim قاسمی=ghasemi كريم=karim كمال=kamal ليلى=layla لیلا=layla ماجد=majed مجید=majed محمد=muhammad محمدی=mohammadi محمود=mahmoud محمودی=mahmoudi
مرادی=moradi مرتضی=morteza مروان=marwan مريم=maryam مریم=maryam مسعود=masoud مصطفى=mustafa منصور=mansour مهدي=mahdi مهدی=mehdi موسوی=mousavi ناصر=nasser نبيل=nabil نزار=nizar نصر=nasr نظری=nazari نور=nour نیلوفر=niloufar هاشمی=hashemi هدى=huda هشام=hisham وليد=walid ياسر=yasser ياسين=yassin يوسف=yusuf پرویز=parviz پریسا=parisa کامران=kamran کاوه=kaveh کرمانی=kermani کریمی=karimi گلناز=golnaz یزدانی=yazdani
"""
SCRIPT_WORDS = dict(item.split("=", 1) for item in SCRIPT_WORDS_TEXT.split())

CYRILLIC_MAP = {
    'а':'a','б':'b','в':'v','г':'g','д':'d','е':'e','ё':'yo','ж':'zh',
    'з':'z','и':'i','й':'y','к':'k','л':'l','м':'m','н':'n','о':'o',
    'п':'p','р':'r','с':'s','т':'t','у':'u','ф':'f','х':'kh','ц':'ts',
    'ч':'ch','ш':'sh','щ':'shch','ъ':'','ы':'y','ь':'','э':'e','ю':'yu','я':'ya',
}
ARABIC_MAP = {
    'ا':'a','آ':'a','أ':'a','إ':'i','ٱ':'a','ب':'b','ت':'t','ث':'th','ج':'j',
    'ح':'h','خ':'kh','د':'d','ذ':'dh','ر':'r','ز':'z','س':'s','ش':'sh',
    'ص':'s','ض':'d','ط':'t','ظ':'z','ع':'','غ':'gh','ف':'f','ق':'q','ك':'k',
    'ک':'k','گ':'g','ل':'l','م':'m','ن':'n','ه':'h','ة':'a','و':'w','ؤ':'w',
    'ي':'y','ى':'a','ی':'y','ئ':'y','ء':'','پ':'p','چ':'ch','ژ':'zh','ۀ':'h',
}


def ascii_fold(text: str) -> str:
    text = text.translate(str.maketrans({'ß':'ss','ẞ':'ss','ø':'o','Ø':'o',
                                         'ł':'l','Ł':'l','đ':'d','Đ':'d',
                                         'ı':'i','İ':'I'}))
    return ''.join(c for c in unicodedata.normalize('NFKD', text)
                   if not unicodedata.combining(c))


def transliterate_word(word: str) -> str:
    if word in SCRIPT_WORDS:
        return SCRIPT_WORDS[word]
    out = []
    for char in word.lower():
        if char in CYRILLIC_MAP:
            out.append(CYRILLIC_MAP[char])
        elif char in ARABIC_MAP:
            out.append(ARABIC_MAP[char])
        elif char.isascii():
            out.append(char)
        elif char.isalpha():
            # Latin letters with diacritics are folded after script handling.
            out.append(ascii_fold(char))
    return ''.join(out)


def raw_words(name: str) -> list[str]:
    # Tokenize before accent folding. NFKD on the whole string would erase the
    # breve in Cyrillic й and the hamza in Arabic أ/إ before transliteration.
    name = re.sub(r'[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]', '', name)
    words = re.findall(r"[^\W\d_]+", name, flags=re.UNICODE)
    answer = []
    for word in words:
        transliterated = transliterate_word(word)
        if transliterated:
            answer.append(transliterated)
    return answer


PATRONYMIC_RE = re.compile(
    r'(?:ovich|evich|yevich|yich|ovna|evna|yevna|ovitch|evitch|ovitsch|'
    r'evitsch|owitsch|ewitsch|ovich|evich|owich|ewich|ovicz|evicz|owicz|'
    r'ewicz|ovic|evic|owna|ewna)$')
RUS_FAMILIES = set("""
andreev belousov bondarenko bykov chaikovsky chernov egorov fedorov grishin
ivanov kiselyov kovalenko kozlov kravchenko kuznetsov lebedev makarov morozov
nikolaev novikov orlov pavlov petrov popov shcherbakov shevchenko shishkin
smirnov sokolov stepanov tkachenko tsoy tsvetkov volkov yakovlev yashin
zaitsev zakharov zhukov semyonov
""".split())


def token_canon(token: str) -> str:
    token = CANON.get(ascii_fold(token).lower(), ascii_fold(token).lower())
    for ending in ('skaya', 'skaja', 'skaia'):
        if token.endswith(ending):
            masculine = token[:-len(ending)] + 'sky'
            masculine = CANON.get(masculine, masculine)
            if masculine in RUS_FAMILIES:
                token = masculine
                break
    if token.endswith('a') and CANON.get(token[:-1], token[:-1]) in RUS_FAMILIES:
        token = CANON.get(token[:-1], token[:-1])
    return CANON.get(token, token)


# Chinese readings. Values are pinyin; ambiguous dialect readings are expanded
# rather than forced to one surname.
CHINESE_READINGS: dict[str, tuple[str, ...]] = {
    'chang':('zhang',), 'cheung':('zhang',), 'teo':('zhang','zhao'),
    'teoh':('zhang','zhao'), 'tiong':('zhang',),
    'chan':('chen',), 'tan':('chen',), 'chin':('chen',),
    'wong':('wang','huang'), 'ong':('wang',),
    'lee':('li',), 'lei':('lei','li'), 'lam':('lin',), 'lim':('lin',),
    'chou':('zhou',), 'chow':('zhou',), 'chew':('zhou',),
    'ng':('wu',), 'goh':('wu',), 'go':('wu',),
    'chao':('zhao',), 'chiu':('zhao',), 'tio':('zhao',),
    'hsieh':('xie',), 'tse':('xie',), 'hsu':('xu',),
    'tsai':('cai',), 'choi':('cai',), 'tsao':('cao',),
    'chien':('qian',), 'chiang':('jiang',), 'kuo':('guo',), 'kwok':('guo',),
    'kao':('gao',), 'ko':('gao',), 'chu':('zhu',), 'tsuei':('cui',),
    'teng':('deng',), 'yeh':('ye',), 'juei':('rui',), 'chieh':('jie',),
    'ching':('jing',), 'tien':('tian',), 'chih':('zhi',), 'hsia':('xia',),
    'hsiao':('xiao',), 'hsiang':('xiang',), 'hsueh':('xue',),
    'hsin':('xin',), 'tseng':('zeng',), 'ho':('he',), 'leung':('liang',),
    'lo':('luo','lu'), 'tong':('tang',), 'fung':('feng',), 'poon':('pan',),
    'yuen':('yuan',), 'yeung':('yang',), 'lau':('liu',), 'low':('liu',),
    'soon':('sun',), 'to':('du',), 'tu':('du',), 'tai':('dai',),
    'pao':('bao',), 'poming':('boming',), 'kang':('gang',),
    'najung':('narong',),
    'kuei':('gui',), 'faan':('fan',), 'mah':('ma',), 'hoo':('hu',),
    'hwang':('huang',), 'chun':('chun','jun'), 'jung':('rong',),
    'tung':('dong',), 'chung':('zhong',), 'tsui':('cui',), 'chui':('cui',),
    'yip':('ye',), 'suen':('sun',), 'sung':('song',), 'keung':('qiang',),
    'po':('bo',), 'te':('de',), 'dang':('deng',),
    # Further Hokkien/Teochew surname conventions.
    'chua':('cai',), 'seah':('xie',), 'kwek':('guo',), 'que':('guo',),
    'quek':('guo',), 'yeo':('yang',), 'wee':('huang',), 'oei':('huang',),
    'phua':('pan',), 'pua':('pan',), 'tay':('zeng',), 'teh':('zeng',),
}
CHINESE_SURNAMES = set("""
cai cao chen cui dai deng du fan feng gao guo he hu huang jiang li liang lin
liu lu luo ma pan qi qian shen song sun tang wang wu xie xu yang ye yuan zeng
zhang zhao zhou zhu
""".split())


def combine_name_parts(words: list[str]) -> list[str]:
    words = [w.lower() for w in words]
    article_families = {
        'amin','attar','douri','farsi','hashemi','jabouri','khatib','masri',
        'najjar','rashid','sabah','sayid','shamsi','tikriti','zahrani','noor','bahr',
    }
    expanded = []
    for position, word in enumerate(words):
        split = False
        # The Arabic definite article assimilates before sun letters in common
        # romanization: ad-Douri, ar-Rashid, as-Shamsi, at-Tikriti, az-Zahrani,
        # and an-Najjar are all forms of al-.
        for article in ('al','el','ad','ar','as','at','az','an','ash',
                        'ed','er','es','et','ez','en','esh','asy'):
            remainder = token_canon(word[len(article):]) if word.startswith(article) else ''
            if word.startswith(article) and remainder in article_families:
                expanded.append(remainder)
                split = True
                break
        if split:
            continue
        if word in ('al', 'el'):
            continue
        if (word in ('ad','ar','as','at','az','an','ash',
                     'ed','er','es','et','ez','en','esh','asy') and
                position + 1 < len(words) and
                token_canon(words[position + 1]) in article_families):
            continue
        if not split:
            expanded.append(word)
    words = expanded

    out = []
    i = 0
    while i < len(words):
        if (words[i] in {'bin', 'ibn', 'ben', 'b'} and len(words) >= 4 and
                i > 0 and i + 1 < len(words)):
            # A father's compound Abd al-/Abdul ... belongs to the optional
            # nasab as a unit.
            if i + 2 < len(words) and words[i + 1] in {
                    'abd','abdel','abdol','abdul','abdoel','abdool'}:
                if (i + 3 < len(words) and words[i + 2] in
                        {'al','el','ar','er','ur','ul'}):
                    i += 4
                else:
                    i += 3
            else:
                i += 2
        else:
            out.append(words[i])
            i += 1
    words = [word for word in out if len(word) != 1]  # middle initials

    out = []
    i = 0
    while i < len(words):
        if (i + 2 < len(words) and words[i] in
                {'abd','abdel','abdol','abdul','abdoel','abdool'} and
                words[i + 1] in {'al','el','ar','er','ur','ul'}):
            second = token_canon(words[i + 2])
            joined = {'rahman':'abdulrahman', 'rahmen':'abdulrahman',
                      'allah':'abdullah', 'aziz':'abdulaziz',
                      'karim':'abdulkarim', 'karem':'abdulkarim'}.get(second)
            if joined:
                out.append(joined)
                i += 3
                continue
        if i + 1 < len(words) and words[i] in {
                'abd','abdel','abdol','abdul','abdoel','abdool'}:
            second = token_canon(words[i + 1])
            joined = {'rahman':'abdulrahman', 'rahmen':'abdulrahman',
                      'allah':'abdullah', 'aziz':'abdulaziz',
                      'karim':'abdulkarim', 'karem':'abdulkarim'}.get(second)
            if joined:
                out.append(joined)
                i += 2
                continue
        out.append(words[i])
        i += 1
    words = out

    # Nasr Allah is a single family name, written either joined or spaced.
    out = []
    i = 0
    while i < len(words):
        if i + 1 < len(words) and words[i] == 'nasr' and words[i+1] == 'allah':
            out.append('nasrallah'); i += 2
        else:
            out.append(words[i]); i += 1
    words = out

    joined = []
    i = 0
    while i < len(words):
        triples = tuple(words[i:i+3])
        pairs = tuple(words[i:i+2])
        if triples == ('van','der','berg'):
            joined.append('vanderberg'); i += 3
        elif triples == ('de','la','cruz'):
            joined.append('delacruz'); i += 3
        elif pairs == ('da','silva'):
            joined.append('dasilva'); i += 2
        elif pairs == ('du','bois'):
            joined.append('dubois'); i += 2
        elif pairs == ('le','fevre'):
            joined.append('lefevre'); i += 2
        elif pairs == ('mac','donald'):
            joined.append('macdonald'); i += 2
        elif pairs == ('o','brien'):
            joined.append('obrien'); i += 2
        elif pairs == ('smith','jones'):
            joined.append('smithjones'); i += 2
        else:
            joined.append(words[i]); i += 1
    # The particles can move with a family-first rendering ("Cruz, ... De la")
    # and Dutch den/der are conventional alternatives.
    def collapse_unordered(parts: list[str], required: tuple[str, ...], result: str) -> bool:
        copy = parts[:]
        for item in required:
            if item not in copy:
                return False
            copy.remove(item)
        parts[:] = copy + [result]
        return True
    collapse_unordered(joined, ('de','la','cruz'), 'delacruz')
    if not collapse_unordered(joined, ('van','der','berg'), 'vanderberg'):
        collapse_unordered(joined, ('van','den','berg'), 'vanderberg')
    return [token_canon(word) for word in joined]


def is_patronymic(word: str) -> bool:
    return bool(PATRONYMIC_RE.search(word)) and word not in RUS_FAMILIES


def individual_signatures(name: str) -> set[tuple[str, ...]]:
    raw = raw_words(name)
    raw_latin = {ascii_fold(word).lower() for word in raw}
    words = [word for word in combine_name_parts(raw)
             if not is_patronymic(word)]
    if not words:
        return set()
    signatures: set[tuple[str, ...]] = {('p', *sorted(words))}
    # "Sammy" is independently a conventional form of Arabic Sami and
    # Western Samuel. Preserve both readings and let surname/DOB disambiguate.
    if 'sammy' in raw_latin and 'sami' in words:
        alternate = ['samuel' if word == 'sami' else word for word in words]
        signatures.add(('p', *sorted(alternate)))
    # Ted is a conventional short form of both Theodore and Edward. Full
    # Theodore is not thereby made equivalent to full Edward.
    if 'ted' in raw_latin and 'theodore' in words:
        alternate = ['edward' if word == 'theodore' else word for word in words]
        signatures.add(('p', *sorted(alternate)))
    # A few cross-language spellings are genuinely ambiguous. Preserve both
    # readings without merging their unambiguous standard forms.
    ambiguous = {
        'darouishe': ('darwish', 'dariush'),
        'hosaine': ('hosseini', 'hussein'),
        'jasin': ('yassin', 'yashin'),
    }
    for spelling, (current, alternate_word) in ambiguous.items():
        if spelling in raw_latin and current in words:
            alternate = [alternate_word if word == current else word for word in words]
            signatures.add(('p', *sorted(alternate)))

    def chinese_readings(word: str) -> tuple[str, ...]:
        if word in CHINESE_READINGS:
            return CHINESE_READINGS[word]
        # Wade-Giles digraphs also occur inside an unspaced given name.
        forms = {word}
        for old, new in (('hsueh','xue'), ('hsiang','xiang'),
                         ('hsiao','xiao'), ('hsia','xia'), ('hsin','xin'),
                         ('hsi','xi'), ('chih','zhi'), ('chieh','jie'),
                         ('chien','qian'), ('ching','jing'), ('tien','tian'),
                         ('kuei','gui'), ('kuo','guo'), ('tsuei','cui'),
                         ('tsui','cui'), ('tung','dong'), ('chung','zhong'),
                         ('jung','rong'), ('pao','bao'), ('poy','boy')):
            forms = {item.replace(old, new) for item in forms}
        # P/B in Wade-Giles-generated compounds (Feng-po/Fengbo,
        # Mei-pin/Meibin) is position-sensitive; retain both readings.
        more = set(forms)
        for item in forms:
            if item.endswith('po'):
                more.add(item[:-2] + 'bo')
            if item.endswith('pin'):
                more.add(item[:-3] + 'bin')
            if 'chun' in item:
                more.add(item.replace('chun', 'jun'))
        return tuple(sorted(more))

    expanded_lists = [chinese_readings(word) for word in words]
    combos: list[list[str]] = [[]]
    for alternatives in expanded_lists:
        combos = [base + [alternative] for base in combos for alternative in alternatives]
        if len(combos) > 16:
            combos = combos[:16]
    for combo in combos:
        for i, word in enumerate(combo):
            if word in CHINESE_SURNAMES and len(combo) >= 2:
                given = ''.join(combo[:i] + combo[i+1:])
                if given:
                    signatures.add(('c', word, given))
    # With a split two-syllable Chinese given name, arbitrary token sorting
    # would also accept the syllables in reverse order. The Chinese signature
    # permits family/given order changes while preserving given-name order.
    if len(words) > 2 and any(signature[0] == 'c' for signature in signatures):
        signatures = {signature for signature in signatures if signature[0] == 'c'}
    return signatures


LEGAL_SUFFIXES = [
    ('free','zone','limited','liability','company'),
    ('free','zone','limited','liability','co'),
    ('free','zone','llc'),
    ('open','joint','stock','company'), ('closed','joint','stock','company'),
    ('public','joint','stock','company'), ('limited','liability','company'),
    ('limited','liability','co'),
    ('joint','stock','company'), ('free','zone','establishment'),
    ('sociedad','anonima'), ('societe','anonyme'), ('private','limited'),
    ('proprietary','limited'), ('sendirian','berhad'), ('sdn','bhd'),
    ('aktiengesellschaft',), ('incorporated',), ('corporation',), ('company',),
    ('limited',), ('gmbh',), ('llc',), ('ltd',), ('inc',), ('corp',),
    ('plc',), ('pjsc',), ('ojsc',), ('cjsc',), ('jsc',), ('oao',), ('zao',), ('ao',), ('sa',),
    ('fze',), ('fzllc',), ('fz',), ('ag',), ('bv',), ('nv',), ('oy',), ('as',),
    ('pt',), ('pte',), ('pty',), ('bhd',), ('berhad',), ('spa',), ('srl',),
    ('sarl',), ('sas',), ('snc',), ('ltda',), ('llp',), ('lp',), ('ooo',), ('kk',),
    ('ab',), ('asa',), ('co',),
]


def business_words(name: str) -> list[str]:
    text = ascii_fold(name).lower()
    text = re.sub(r'(?<=[a-z])\.(?=[a-z])', '', text)
    text = text.replace('&', ' and ')
    words = re.findall(r'[a-z0-9]+', text)
    if words and words[0] == 'the':
        words.pop(0)
    words = [word for word in words if word != 'and']
    changed = True
    while changed:
        changed = False
        for suffix in LEGAL_SUFFIXES:
            if len(words) >= len(suffix) and tuple(words[-len(suffix):]) == suffix:
                del words[-len(suffix):]
                changed = True
                break
    return words


def entity_signature(name: str) -> tuple[str, ...]:
    return tuple(business_words(name))


def vessel_signature(name: str) -> tuple[str, ...]:
    text = ascii_fold(name).lower().strip()
    text = re.sub(
        r'^\s*(?:(?:m|s)\s*/?\s*[vts]|mv|mt|ms|ss|vessel|motor\s+vessel|'
        r'motor\s+tanker)\b[\s.:/-]*', '', text)
    return tuple(re.findall(r'[a-z0-9]+', text))


def normalized_literal(name: str) -> tuple[str, ...]:
    # Weak aliases require equality, not synonym expansion. Normalize only
    # script/diacritics, case and punctuation here.
    return tuple(ascii_fold(word).lower() for word in raw_words(name))


def dob_compatible(customer_dob: str, entry_dob: str) -> bool:
    return not customer_dob or not entry_dob or entry_dob.startswith(customer_dob)


def dob_supported(customer_dob: str, entry_dob: str) -> bool:
    return bool(customer_dob and entry_dob and entry_dob.startswith(customer_dob))


class Screener:
    def __init__(self, entries: list[dict]):
        self.by_uid = {entry['uid']: entry for entry in entries}
        self.ids: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self.names: dict[str, dict[tuple[str, ...], set[str]]] = {
            'individual': defaultdict(set), 'entity': defaultdict(set),
            'vessel': defaultdict(set)}
        self.weak: dict[tuple[str, ...], set[str]] = defaultdict(set)

        for entry in entries:
            for ident in entry.get('ids', []):
                self.ids[(ident.get('type',''), ident.get('number',''))].append(entry)
            typ = entry['type']
            names = [entry.get('primary_name') or '', entry.get('script_name') or '']
            names += [alias['name'] for alias in entry.get('aliases', [])
                      if alias.get('strength') == 'strong']
            for name in names:
                if not name:
                    continue
                if typ == 'individual':
                    for signature in individual_signatures(name):
                        self.names[typ][signature].add(entry['uid'])
                elif typ == 'entity':
                    self.names[typ][entity_signature(name)].add(entry['uid'])
                else:
                    self.names[typ][vessel_signature(name)].add(entry['uid'])
            if typ == 'individual':
                for alias in entry.get('aliases', []):
                    if alias.get('strength') == 'weak':
                        self.weak[normalized_literal(alias['name'])].add(entry['uid'])

    def choose(self, uids: set[str], dob: str) -> dict | None:
        candidates = [self.by_uid[uid] for uid in uids
                      if dob_compatible(dob, self.by_uid[uid].get('dob') or '')]
        if not candidates:
            return None
        candidates.sort(key=lambda entry: (
            0 if dob_supported(dob, entry.get('dob') or '') else 1, entry['uid']))
        return candidates[0]

    def screen(self, customer: dict) -> str | None:
        id_type = customer.get('id_type') or ''
        id_number = customer.get('id_number') or ''
        if id_type and id_number:
            hits = self.ids.get((id_type, id_number), [])
            if hits:
                # Identifier support is first. Among duplicate identifiers the
                # policy's remaining DOB/UID tie-breakers still apply, but a
                # conflicting DOB cannot veto the identifier match.
                return min(hits, key=lambda entry: (
                    0 if dob_supported(customer.get('dob') or '',
                                       entry.get('dob') or '') else 1,
                    entry['uid']))['uid']

        typ = customer.get('type') or 'individual'
        name = customer.get('full_name') or ''
        dob = customer.get('dob') or ''
        uids: set[str] = set()
        if typ == 'individual':
            for signature in individual_signatures(name):
                uids.update(self.names['individual'].get(signature, ()))
            # Weak aliases become candidates only with an identical full DOB.
            if len(dob) == 10:
                for uid in self.weak.get(normalized_literal(name), ()):
                    if self.by_uid[uid].get('dob') == dob:
                        uids.add(uid)
        elif typ == 'entity':
            uids.update(self.names['entity'].get(entity_signature(name), ()))
        elif typ == 'vessel':
            uids.update(self.names['vessel'].get(vessel_signature(name), ()))
        result = self.choose(uids, dob)
        if result:
            return result['uid']
        return None


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Screen customers against a sanctions watchlist')
    parser.add_argument('--watchlist', required=True)
    parser.add_argument('--customers', required=True)
    parser.add_argument('--out', required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    with open(args.watchlist, encoding='utf-8') as handle:
        entries = json.load(handle)
    screener = Screener(entries)
    with open(args.customers, newline='', encoding='utf-8-sig') as src, \
         open(args.out, 'w', newline='', encoding='utf-8') as dst:
        reader = csv.DictReader(src)
        required = {'customer_id','full_name','dob','nationality','id_type',
                    'id_number','type'}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError('customers CSV is missing required columns')
        writer = csv.DictWriter(dst, fieldnames=['customer_id','decision','matched_uid'])
        writer.writeheader()
        for customer in reader:
            uid = screener.screen(customer)
            writer.writerow({'customer_id': customer['customer_id'],
                             'decision': 'MATCH' if uid else 'NO_MATCH',
                             'matched_uid': uid or ''})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
