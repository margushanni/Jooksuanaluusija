# Garmini jooksuanalüüs

## Projekti plaan

### 1. Projekti nimi

**Garmini jooksuanalüüs** – Windowsi töölauaprogramm Garmini jooksude importimiseks ja enda treeningukoormuse mõistmiseks.

### 2. Eesmärk

Projekt aitab vastata küsimusele: millise enesehinnangu ehk RPE juures ja millise tempoga ma jooksen? Terve jooksu keskmine tempo ei kirjelda alati treeningu sisu, sest treeningus võib olla kiireid töölõike ja aeglaseid taastumispause. Seetõttu analüüsib programm aktiivseid lõike ning arvestab ka nende kestuse ja distantsiga. Pulssi ei kasutata pingutuse hindamiseks, sest randmelt mõõdetud pulss ei ole minu jaoks piisavalt usaldusväärne.

### 3. Sihtrühm

Programm on mõeldud jooksjatele, kes kasutavad Garmini kella või Garmin Connecti, hindavad treeningu pingutust RPE-ga ning soovivad võrrelda enesetunnet jooksutempo ja aktiivse töö mahuga. Esmane kasutaja olen mina ise.

### 4. Funktsionaalsus

1. Otsib arvutiga ühendatud Garmini kella automaatselt, nii draivina kui ka Windowsi MTP/WPD-seadmena.
2. Võimaldab valida FIT-faile või nende kausta käsitsi importimiseks.
3. Impordib 2025. aasta jooksude FIT-failid Garmin Connect Personal API kaudu ning jätab korduvad failid vahele.
4. Loeb FIT-failist treeningu RPE ja enesetunde; puuduva hinnangu märgib „Hinnang - märkimata”.
5. Kuvab jooksude kuupäeva, distantsi, kestuse ja enesehinnangu ning võimaldab valida analüüsitava aasta.
6. Eristab FIT-failis aktiivseks märgitud töölõigud soojendusest ja taastumisest ning võtab tempoanalüüsi arvesse kuni 5:30/km lõigud.
7. Arvutab aktiivlõikude kaalutud keskmise töötempo ning võrdleb seda RPE ja aktiivse töö kestuse või distantsiga.

### 5. Tehnoloogiad

- **Python 3** programmi ja andmeanalüüsi jaoks.
- **Tkinter** Windowsi töölaualiidese jaoks.
- **Garmin FIT SDK** FIT-failide lugemiseks.
- **Garmin Connect Personal API Python klient** jooksude pärimiseks ja FIT-failide allalaadimiseks.
- **comtypes ja Windowsi WPD/MTP-liides** kella automaatseks leidmiseks ja failide lugemiseks.
- **PowerShell** käivitamise ja vajalike sõltuvuste seadistamise skriptina.
- **GitHub** lähtekoodi ja projekti dokumentatsiooni hoidmiseks.

### 6. Teostusplaan

1. Määratleda, milliseid andmeid analüüsida ja kuidas RPE, töötempo ning lõigud omavahel siduda.
2. Luua Windowsi töölaualiides ja seadistusskript, mis paigaldab sõltuvused.
3. Teha FIT-failide import käsitsi valitud kaustast või failidest ning ühendada automaatne kellatuvastus.
4. Lisada Personal API kaudu jooksude otsimine ja FIT-failide allalaadimine.
5. Lugeda FIT-failidest treeningu enesehinnang ja ringide aktiivsus, distants ning kestus.
6. Arvutada aktiivlõikude kaalutud töötempo ja koostada RPE ning töömahu kokkuvõtted.
7. Kontrollida tulemust päris treeningufailidega, parandada vigade käsitlemist ja täiendada kasutusjuhendit.

### 7. Valmisoleku kriteeriumid

- Programm käivitub juhendi järgi Windowsi arvutis ning kuvab arusaadava veateate, kui sõltuvus või sisendfail puudub.
- Kasutaja saab jooksud importida ühendatud kellast, valitud FIT-failidest või 2025. aasta Personal API päringuga.
- Korduv import ei lisa sama treeningut teist korda ning isiklikud FIT-failid ja tokenivahemälu ei lähe GitHubi.
- Tabelis kuvatakse treeningu põhiandmed ja FIT-is olevad RPE/enesetunde hinnangud; puuduva hinnangu puhul kuvatakse „Hinnang - märkimata”.
- RPE-tempo kokkuvõte kasutab ainult aktiivseid töölõike, jätab taastelõigud välja ja arvestab tempoga kuni 5:30/km.
- Töötempo arvutus arvestab aktiivlõikude koguaega ja kogudistantsi ning kokkuvõttes saab võrrelda tulemusi ka töö kestuse ja distantsi järgi.
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

RPE ja enesetunne loetakse otse FIT-faili enesehinnangu väljadest. Lõiguanalüüs võtab arvesse FIT-is `active` märgisega töölõike kuni tempoga 5:30/km; soojendus ja taastelõigud jäetakse välja. Töötempo on aktiivlõikude koguaja ja kogudistantsi suhe, nii et pikemad lõigud mõjutavad tulemust rohkem.

Kui FIT-failis enesehinnang puudub, kuvatakse **Hinnang - märkimata**.

Lisajuhised: [Garmin Connect API](README-garmin.md) ja [jooksuanalüsaatori kasutamine](README-run-analyzer.md).

See repo sisaldab programmi lähtekoodi. Isiklikud FIT-andmed ja API tokenivahemälu repo osaks ei ole.
