# Archive Record Linkage Policy

This policy defines when a record from a newly digitised batch refers to an entry already in the archive register. The
verifier grades outcomes only: for every record in `/app/records.csv`,
`decision` must be `MATCH` with the correct `matched_uid`, or `NO_MATCH`.

## Inputs

`/app/register.json` is a list of entries with `uid`, `type`
(`individual`, `entity`, `vessel`), `primary_name`, `script_name` (the name in
its original script when the person is from an Arabic-, Persian- or
Cyrillic-script culture, else null), `aliases` (each with `name` and
`strength` `strong` or `weak`), `dob` (`YYYY-MM-DD`, `YYYY`, or empty),
`nationalities`, `ids` (each with `type` and `number`) and `collections` (the holdings the entry was compiled from). For some
individuals `primary_name` is the original-script name itself; those entries
may have no Latin spelling anywhere.

`/app/records.csv` has `record_id, full_name, dob, nationality, id_type,
id_number, type`. `dob` may be a full date, a year, a year-month, or empty.

## Rule 1: identifiers

If the record's `id_type` and `id_number` equal an entry's identifier
(`document`, `registration`, or `imo`), the record matches that entry
regardless of the name or date of birth. An identifier that matches no entry
neither confirms nor rules out anything; the record is then judged on name
and date of birth like any other.

## Rule 2: name equivalence

Two names refer to the same person when, after normalization, the given name
and the family name correspond. Names correspond across all of the following
variations. The development sample illustrates them; it does not exhaust them.
The batch uses romanization conventions (for example French, German, Polish
and Gulf spellings of Arabic and Russian names, Cantonese surnames, sun-letter
assimilation of the Arabic article) that do not appear in the development
sample, and it stacks several conventions on one name. The engine is also run
on a second batch, not provided, that further uses Turkish spellings of Arabic
names (Cemal, Hüseyin, Ahmet, Kasım), Indonesian and Malay spellings (Achmad,
Joesoef, Sjarif), scientific transliteration of Russian names with the
diacritics stripped (Cajkovskij, Zukov, Sevcenko), and Hokkien and Teochew
Chinese surnames (Tan, Lim, Ong, Goh, Teo).

- Transliteration into Latin script from Arabic, Persian and Cyrillic under any
  common romanization (for example Muhammad/Mohammed/Mohamed/Mohamad,
  Abdul Rahman/Abdurrahman/Abd al-Rahman, Hussein/Husain/Hussain/Husayn,
  Sergei/Sergey/Serguei/Sergej, Fedorov/Fyodorov/Fedoroff, Yevgeny/Evgeny/Eugene),
  including matching a Latin record name against an entry that only has an
  original-script name.
- Chinese names under pinyin and Wade-Giles/Cantonese romanizations
  (Zhang/Chang, Wang/Wong, Li/Lee, Zhou/Chou/Chow, Xiao Ming/Xiaoming/Hsiao-Ming),
  in either family-name-first or given-name-first order.
- Western nicknames and diacritic variants (William/Bill, Katherine/Kate,
  Jose/José, Mueller/Müller/Muller, Nguyen/Nguyễn), middle initials, and
  hyphenated versus spaced compound surnames.
- Name order (family name first, with or without a comma), presence or absence
  of Russian patronymics, presence or absence of Arabic nasab elements
  (`bin`/`ibn`/`ben` + father's name), and presence or absence of the Arabic
  article (`al-`, `el-`, `Al `, attached `Al`).
- Feminine Russian surname forms (Ivanova/Ivanov).

Names do not correspond when the given name or the family name is a different
name (Hassan is not Hussein, Ahmadi is not Ahmadi-with-a-different-given-name,
Al-Noor Trading is not Al-Noor Shipping). A single shared given name or a
single shared family name is not a name match.

## Rule 3: aliases

A `strong` alias is an alternative name of the entry and participates in
Rule 2 exactly like `primary_name`. A `weak` alias (a nickname or nom de
guerre) matches a record only when the record's name equals the alias and
Rule 4 corroborates with an identical full date of birth, or Rule 1 applies.
A weak alias alone never produces a match.

## Rule 4: date of birth

Dates of birth are compared only when both sides have one. A full record
date must equal the entry's full date. A record year or year-month must be
a prefix of the entry's date. Any disagreement rules the candidate out (the
record is a different person with a similar name). A missing date on either
side neither confirms nor rules out.

## Rule 5: entities and vessels

Entity names correspond when all name words correspond after removing legal
form designators (LLC, L.L.C., Limited Liability Company, Ltd, Limited, S.A.,
GmbH, JSC, Joint Stock Company, AO, OAO, PJSC, Co., Company, FZE, FZ-LLC and
similar), leading `The`, punctuation, and the words `and`/`&`; case is
ignored. Vessel names correspond after removing prefixes such as `M/V`, `MV`,
`M/T`, `MT`, `Vessel`. Identifiers (`registration`, `imo`) match under Rule 1.

## Rule 6: nationality

Nationality is informational and does not confirm or rule out a match.

## Output

`/app/decisions.csv` with a header row `record_id,decision,matched_uid`,
exactly one row per record in the batch, `decision` in `{MATCH, NO_MATCH}`,
and `matched_uid` set to the entry `uid` for every `MATCH`. When more than one
entry could match, choose the one supported by an identifier, then by a date
of birth, then the lowest `uid` (string order). Closeness of spelling is not a
tie-breaker: two entries with the same name and different dates of birth are
two people, and a record without a date of birth resolves to the lower `uid`.

## Scoring

The batch is scored against hidden labels produced by the same process as
`/app/dev/labels_dev.csv`, and the engine `/app/link.py` is run on a second,
unseen batch from the same process and scored the same way. The task passes
only if all of the following hold on each batch: overall recall of true matches at least 0.97 and overall precision
at least 0.97; recall at least 0.90 within every true-match variation class;
false-positive rate at most 0.05 within every look-alike look-alike class and at
most 0.01 among unrelated records; and at least 0.97 of correct matches
carry the correct `matched_uid`. The development sample reports the same
classes so you can measure yourself before the batch is scored.
