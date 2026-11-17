# Tegevuslogi

Projektitööde lühike kronoloogiline arvestus. Iga uue arenduskorraga lisatakse siia uus kuupäevastatud sissekanne. Isiklikke treeninguandmeid, API võtmeid ega tokeneid siia ei kirjutata.

## 2026-11-17 — Tegevuslogi kasutusele võtmine

- **Seotud Issue:** töölogi korra käivitamine; seotud GitHubi Issue lisatakse, kui see on loodud.
- **Eesmärk:** hakata koguma projekti arendustegevusi hilisemaks päeviku või blogipostituse koostamiseks.
- **Muudatused:** lisatud `logi.md` ning projekti `AGENTS.md`, mis suunab edaspidiseid arenduskordi logi täiendama.
- **Kontroll:** `git diff --check` läbis; rakenduse teste ei käivitatud, sest muudatus puudutab juhiseid ja dokumentatsiooni.
- **Tulemus:** töölogi vorming ja edaspidine logimise juhis on loodud. Järgmised sisulised arendustööd lisatakse samasse faili.

## 2026-11-17 — FIT-failide taustal laadimine

- **Seotud Issue:** [#5 — Paranda programmi aeglane käivitus suure FIT-kaustaga](https://github.com/margushanni/Jooksuanaluusija/issues/5).
- **Eesmärk:** lahendada olukord, kus programm paistis suure kohaliku FIT-failide hulga korral käivitamisel hangunud.
- **Muudatused:** kohalike FIT-failide dekodeerimine liigub taustalõime; aken kuvatakse enne laadimise lõppu ning edenemisriba ja olekuteade näitavad laadimise käiku ja tulemust.
- **Kontroll:** `git diff --check` läbis. Rakendust ega teste ei käivitatud.
- **Tulemus:** käivitus ei pea enam ootama kõigi kohalike FIT-failide järjestikust dekodeerimist enne kasutajaliidese kuvamist. Vajab kasutaja arvutis käivitamise kinnitust.

## 2026-11-17 — Kalendriga kuupäevavahemik

- **Seotud Issue:** [#1 — Lisa kuupäevavahemik ja perioodide kiirvalikud](https://github.com/margushanni/Jooksuanaluusija/issues/1).
- **Eesmärk:** asendada analüüsiaasta valik vabalt valitava algus- ja lõppkuupäevaga.
- **Muudatused:** lisatud kalendrivaatega kuupäevavalikud, kuupäevade käsitsi sisestus ning kõigi kuupäevade kuvamise nupp. Valitud vahemik filtreerib jooksude tabelit ja kokkuvõtet; 2025 API import seab vahemikuks 2025. aasta. Tühja vahemiku korral kuvatakse teade. Uuendatud käivitusjuhendit ja README projekti kirjeldust.
- **Kontroll:** `git diff --check` läbis. Rakendust ega teste ei käivitatud.
- **Tulemus:** kasutaja saab valida analüüsi kuupäevavahemiku kalendrist. Rakenduses visuaalne kontroll tegemata.

## 2026-11-17 — API impordi kuupäevavahemiku valik

- **Seotud Issue:** [#1 — Lisa kuupäevavahemik ja perioodide kiirvalikud](https://github.com/margushanni/Jooksuanaluusija/issues/1).
- **Eesmärk:** lubada Garmin Connect Personal API-st jooksude importimisel valida ise päringu algus- ja lõppkuupäev.
- **Muudatused:** API impordi nupp avab kuupäevavahemiku akna kahe kalendrivaatega; kuupäevi saab ka käsitsi sisestada. Päring kasutab valitud kuupäevi ja pärast importi seatakse analüüsivahemik samale perioodile. Vaikimisi kasutatakse analüüsivahemikku või 2025. aastat, kui see puudub. Uuendatud kasutusjuhendid.
- **Kontroll:** `git diff --check` läbis. Rakendust ega teste ei käivitatud.
- **Tulemus:** API import ei ole enam piiratud 2025. aastaga; kasutaja saab valida imporditava ajavahemiku. Visuaalne kontroll tegemata.
