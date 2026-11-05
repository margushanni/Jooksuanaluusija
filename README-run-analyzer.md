# Garmini jooksuanalüüs

See Windowsi töölauaprogramm impordib jooksude `.FIT` failid ühendatud Garmini kellast või Garmin Connect Personal API kaudu. Analüüsis kasutatakse FIT-faili enesehinnangu välju RPE ja enesetunne; pulssi ei kasutata pingutuse liigitamiseks. Kell tuvastatakse nii draivitähise kui ka Windowsi MTP/WPD-liidese kaudu, mis katab seadmed, mis kuvatakse ainult „This PC” all.

FIT-failide dekodeerimiseks kasutatakse Garmini FIT Python SDK-d (`garmin-fit-sdk`) ja Personal API päringuteks Garmini ametlikku Python klienti (`garmin-connect-personal-api-python`).

## Käivitamine

Käivita projekti kaustas PowerShellis:

```powershell
.\setup_run_analyzer.ps1
```

Esimesel käivitamisel paigaldatakse vajalik SDK lokaalsesse `.venv` keskkonda ning MTP-seadmete lugemiseks vajalik allikakood `.vendor` kausta.

## 2025. aasta jooksude import API-st

1. Käivita programm.
2. Vajuta **Impordi 2025 API-st** ja sisesta Garmin Personal API võti avanevasse peidetud sisestusaknasse. Võtit ei salvestata.
3. Programm otsib Garmin Connectist 2025. aasta jooksud, laeb iga tegevuse FIT-faili alla ja lisab jooksud lokaalsesse analüüsi.
4. Analüüsiaasta valik lülitub 2025 peale. Vali **Kõik aastad**, kui soovid näha kõiki lokaalseid jookse.

Import võib sõltuvalt jooksude arvust aega võtta. Sama FIT-faili kordusimport jäetakse vahele. Lühiajaline API bearer-token jääb lokaalselt faili `.garmin-private\bearer-token-cache.json`; treeningute FIT-failid asuvad kaustas `data\fit`.

## Kellast importimine

1. Ühenda kell USB-andmekaabliga ja oota, kuni Windows selle kättesaadavaks teeb.
2. Vajuta **Otsi ühendatud Garmini kella**. Otsing vaatab nii draivitähiseid kui ka MTP-seadmeid Windowsi WPD API kaudu.
3. Kui automaatotsing ei leia kella, vajuta **Vali FIT-kaust…** ja vali kella `GARMIN\ACTIVITY` kaust. Võid valida ka eraldi `.FIT` faile.
4. Programm loeb iga jooksu enesehinnangu FIT-failist.

Uute importide korral jäetakse juba lisatud failid vahele. Kellal olevaid originaalfaile programm ei muuda. FIT-failide koopiad salvestatakse lokaalselt kausta `data`; see kaust on Gitist välja jäetud.

MTP lugemiseks peab kell olema Windowsiga ühendatud andmekaabliga. Sulge enne importi Garmin Express või BaseCamp, kui need on avatud, sest Garmin märgib, et MTP-seadet saab korraga kasutada üks rakendus.

## Andmed ja kokkuvõtted

Tabel näitab treeningu kuupäeva, FIT-enesehinnangut (RPE skaalal 0–10 ja enesetunne skaalal 0–100), distantsi, kestust ning kuni 5:30/km aktiivsete töölõikude arvu, tööaega, töödistantse ja töötempot. Lõiguanalüüs kasutab ainult FIT-is `active`-märgisega ringe; soojendus, taastelõigud ja lõdvestus jäetakse välja. Töötempo arvutatakse aktiivlõikude koguaja ja kogudistantsi suhtena, et pikemad lõigud saaksid tempole rohkem kaalu. RPE kokkuvõte arvutab nende töötempode keskmise RPE ja töökoormuse järgi; tempo vahemikud on 15 sekundit. Kui aktiivseid lõike FIT-failis ei eristata, kuvatakse **FIT-is märkimata**; kui aktiivsed lõigud on olemas, kuid kõik on aeglasemad kui 5:30/km, kuvatakse **Pole ≤5:30**. Kui enesehinnangu väljad puuduvad, kuvatakse **Hinnang - märkimata**. Aastavalikuga saab analüüsi piiritleda näiteks ainult 2025. aasta jooksudega.
