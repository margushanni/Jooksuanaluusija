# Garmini jooksuanalüüs

## Projekti plaan

### 1. Projekti nimi

**Garmini jooksuanalüüs** – Windowsi töölauaprogramm Garmini jooksude importimiseks ja enda jooksuarengu jälgimiseks.

### 2. Eesmärk

Projekt aitab jälgida, kuidas muutub jooksja keskmine tempo valitud ajavahemiku jooksul ning millise pingutuse juures ta seda hoiab. Pingutust saab hinnata RPE ehk enesehinnangu või pulsisageduse järgi. Kasutaja saab valida sobiva mõõdiku, sest pulsinäit ei pruugi kõigis olukordades olla usaldusväärne. Treeningute sisu kirjeldamiseks arvestab programm võimalusel aktiivseid töölõike, nende kestust ja distantsi, mitte ainult kogu jooksu keskmist tempot.

### 3. Sihtrühm

Programm on mõeldud jooksjatele, kes kasutavad Garmini kella või Garmin Connecti ning soovivad jälgida enda arengut tempo ja pingutuse (RPE või pulsisageduse) kaudu. Esmane kasutaja olen mina ise.

### 4. Funktsionaalsus

**Praeguses versioonis:**

1. Otsib arvutiga ühendatud Garmini kella automaatselt, nii draivina kui ka Windowsi MTP/WPD-seadmena.
2. Võimaldab valida FIT-faile või nende kausta käsitsi importimiseks.
3. Impordib 2025. aasta jooksude FIT-failid Garmin Connect Personal API kaudu ning jätab korduvad failid vahele.
4. Loeb FIT-failist treeningu RPE ja enesetunde; puuduva hinnangu märgib „Hinnang - märkimata”.
5. Kuvab jooksude kuupäeva, distantsi, kestuse ja enesehinnangu ning võimaldab valida analüüsitava aasta.
6. Eristab FIT-failis aktiivseks märgitud töölõigud soojendusest ja taastumisest ning võtab tempoanalüüsi arvesse kuni 5:30/km lõigud.
7. Arvutab aktiivlõikude kaalutud keskmise töötempo ning võrdleb seda RPE ja aktiivse töö kestuse või distantsiga.

**Edasi plaanitav:**

8. Kuupäevavahemiku käsitsi valimine ning kiirvalikud: viimane kuu, viimased kuus kuud ja viimane aasta.
9. Jooksude filtreerimine: kõik jooksud, ainult lõigutrennid või kasutaja valitud tempovahemik.
10. Mõõdiku valimine analüüsiks: RPE või pulsisagedus.
11. Valitud ajavahemiku arenguvaade, mis näitab keskmise tempo muutust RPE või pulsisageduse lõikes. Filtri järgi kasutatakse kas kogu jooksu keskmist tempot või ainult aktiivlõikude kaalutud töötempot.

### 5. Tehnoloogiad

- **Python 3** programmi ja andmeanalüüsi jaoks.
- **Tkinter** Windowsi töölaualiidese jaoks.
- **Garmin FIT SDK** FIT-failide lugemiseks.
- **Garmin Connect Personal API Python klient** jooksude pärimiseks ja FIT-failide allalaadimiseks.
- **comtypes ja Windowsi WPD/MTP-liides** kella automaatseks leidmiseks ja failide lugemiseks.
- **PowerShell** käivitamise ja vajalike sõltuvuste seadistamise skriptina.
- **GitHub** lähtekoodi ja projekti dokumentatsiooni hoidmiseks.

### 6. Teostusplaan

1. Importida ja lugeda Garmini jooksuandmeid kellast, FIT-failidest või Personal API kaudu. *(Olemas)*
2. Kuvada treeningud koos RPE ja aktiivsete töölõikude tempoga. *(Olemas)*
3. Lisada kuupäevavahemiku valik ja perioodide kiirvalikud.
4. Lisada jooksude tüübi ning tempovahemiku filtrid.
5. Lisada analüüsitava mõõdiku valik RPE ja pulsisageduse vahel.
6. Koostada valitud perioodi arenguvaade, kus keskmist tempot võrreldakse valitud pingutusmõõdikuga.
7. Kontrollida arvutusi eri treeningutega, käsitleda puuduvaid andmeid ning täiendada kasutusjuhendit.

### 7. Valmisoleku kriteeriumid

- Programm käivitub juhendi järgi Windowsi arvutis ning kuvab arusaadava veateate, kui sõltuvus või sisendfail puudub.
- Kasutaja saab jooksud importida ühendatud kellast, valitud FIT-failidest või 2025. aasta Personal API päringuga.
- Korduv import ei lisa sama treeningut teist korda ning isiklikud FIT-failid ja tokenivahemälu ei lähe GitHubi.
- Tabelis kuvatakse treeningu põhiandmed ja FIT-is olevad RPE/enesetunde hinnangud; puuduva hinnangu puhul kuvatakse „Hinnang - märkimata”.
- RPE-tempo kokkuvõte kasutab ainult aktiivseid töölõike, jätab taastelõigud välja ja arvestab tempoga kuni 5:30/km.
- Töötempo arvutus arvestab aktiivlõikude koguaega ja kogudistantsi ning kokkuvõttes saab võrrelda tulemusi ka töö kestuse ja distantsi järgi.
- Kasutaja saab valida algus- ja lõppkuupäeva või perioodi kiirvaliku (viimane kuu, kuus kuud või aasta) ning tulemused uuenevad vastavalt valikule.
- Kasutaja saab kombineerida jooksu tüübi ja tempovahemiku filtreid ning valida, kas pingutust võrreldakse RPE või pulsisagedusega.
- Valitud ajavahemiku tulemus näitab keskmise tempo arengut valitud pingutusmõõdiku järgi; puuduva mõõdiku korral kuvatakse see arusaadavalt.
- Kasutusjuhend selgitab käivitamist, importi, analüüsi ja isikuandmete kohalikku säilitamist.

---

Windowsi töölauaprogramm Garmini jooksude importimiseks ja enesehinnangu (RPE ning enesetunde) analüüsimiseks. Kasutab FIT-faili ringe, et võrrelda aktiivsete lõikude tempot treeningu RPE-ga. Pulssi pingutuse hindamisel ei kasutata.

## Käivitamine

Ava PowerShell projekti kaustas ja käivita:

```powershell
.\setup_run_analyzer.ps1
```

Esimesel käivitamisel paigaldatakse vajalikud sõltuvused lokaalsesse `.venv` keskkonda.

## Treeningute importimine

- **Ühendatud kellast:** vajuta programmis **Otsi ühendatud Garmini kella**. Kui automaatotsing ei leia kella, saad valida FIT-kausta või üksikud failid.
- **Garmin Connect Personal API-st:** vajuta **Impordi 2025 API-st** ja sisesta API võti programmi peidetud sisestusaknasse. Võtit ei salvestata.

Lühiajaline bearer-token salvestatakse lokaalselt faili `.garmin-private\bearer-token-cache.json`. FIT-treeningud ja analüüsitulemused salvestatakse `data` kausta. Need failid on `.gitignore`-iga GitHubist välja jäetud.

## Analüüs

Praegune versioon loeb RPE ja enesetunde otse FIT-faili enesehinnangu väljadest. Lõiguanalüüs võtab arvesse FIT-is `active` märgisega töölõike kuni tempoga 5:30/km; soojendus ja taastelõigud jäetakse välja. Töötempo on aktiivlõikude koguaja ja kogudistantsi suhe, nii et pikemad lõigud mõjutavad tulemust rohkem. Kuupäevavahemiku, täiendavate filtrite ning RPE/pulsi valikuga arenguvaade on projekti järgmine arendusetapp.

Kui FIT-failis enesehinnang puudub, kuvatakse **Hinnang - märkimata**.

Lisajuhised: [Garmin Connect API](README-garmin.md) ja [jooksuanalüsaatori kasutamine](README-run-analyzer.md).

See repo sisaldab programmi lähtekoodi. Isiklikud FIT-andmed ja API tokenivahemälu repo osaks ei ole.
