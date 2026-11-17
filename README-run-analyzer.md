# Garmini jooksuanalüüs

See Windowsi töölauaprogramm impordib jooksude `.FIT` failid ühendatud Garmini kellast või Garmin Connect Personal API kaudu. Analüüsis kasutatakse FIT-faili enesehinnangu välju RPE ja enesetunne; pulssi ei kasutata pingutuse liigitamiseks. Kell tuvastatakse nii draivitähise kui ka Windowsi MTP/WPD-liidese kaudu, mis katab seadmed, mis kuvatakse ainult „This PC” all.

FIT-failide dekodeerimiseks kasutatakse Garmini FIT Python SDK-d (`garmin-fit-sdk`) ja Personal API päringuteks Garmini ametlikku Python klienti (`garmin-connect-personal-api-python`).

## Käivitamine

Käivita projekti kaustas PowerShellis:

```powershell
.\setup_run_analyzer.ps1
```

Esimesel käivitamisel paigaldatakse vajalik SDK lokaalsesse `.venv` keskkonda ning MTP-seadmete lugemiseks vajalik allikakood `.vendor` kausta.

## Jooksude import API-st

1. Käivita programm.
2. Vajuta **Impordi API-st…** ja vali impordi algus- ning lõppkuupäev kalendrist või sisesta need kujul `AAAA-KK-PP`.
3. Vajuta **Jätka API võtmega…** ja sisesta Garmin Personal API võti avanevasse peidetud sisestusaknasse. Võtit ei salvestata.
4. Programm otsib valitud ajavahemiku jooksud, laeb nende FIT-failid alla ja lisab jooksud lokaalsesse analüüsi. Pärast importi seatakse analüüsi kuupäevavahemik imporditud perioodile.

Import võib sõltuvalt jooksude arvust aega võtta. Sama FIT-faili kordusimport jäetakse vahele. Lühiajaline API bearer-token jääb lokaalselt faili `.garmin-private\bearer-token-cache.json`; treeningute FIT-failid asuvad kaustas `data\fit`.

## Kellast importimine

1. Ühenda kell USB-andmekaabliga ja oota, kuni Windows selle kättesaadavaks teeb.
2. Vajuta **Otsi ühendatud Garmini kella**. Otsing vaatab nii draivitähiseid kui ka MTP-seadmeid Windowsi WPD API kaudu.
3. Kui automaatotsing ei leia kella, vajuta **Vali FIT-kaust…** ja vali kella `GARMIN\ACTIVITY` kaust. Võid valida ka eraldi `.FIT` faile.
4. Programm loeb iga jooksu enesehinnangu FIT-failist.

Uute importide korral jäetakse juba lisatud failid vahele. Kellal olevaid originaalfaile programm ei muuda. FIT-failide koopiad salvestatakse lokaalselt kausta `data`; see kaust on Gitist välja jäetud.

MTP lugemiseks peab kell olema Windowsiga ühendatud andmekaabliga. Sulge enne importi Garmin Express või BaseCamp, kui need on avatud, sest Garmin märgib, et MTP-seadet saab korraga kasutada üks rakendus.

## Andmed ja kokkuvõtted

Tabel näitab treeningu kuupäeva, FIT-enesehinnangut (RPE skaalal 0–10 ja enesetunne skaalal 0–100), distantsi ja kestust. **Analüüsi jooksud** valikuga saab kuvada kõik jooksud või ainult need, mille FIT-failis on aktiivlõigud märgitud. Kui valitud on **Kõik jooksud**, võrreldakse tempovahemikuga kogu jooksu keskmist tempot. Kui valitud on **Ainult aktiivlõikudega**, võrreldakse tempovahemikuga aktiivlõikude tempoid ning tabel näitab valitud lõikude arvu, tööaega, töödistantse ja töötempot. Filtrile mittevastavad jooksud jäetakse tabelist ja kokkuvõttest välja.

Analüüsi saab piirata algus- ja lõppkuupäevaga; kuupäeva valimiseks ava vastava välja kõrval kalendrivaade. Kalendri päises saab kuu ja aasta otse rippmenüüst valida, nii ei pea nooltega kuude kaupa liikuma. Kuupäeva võib ka otse sisestada kujul `AAAA-KK-PP`. **Kuva kõik kuupäevad** eemaldab kuupäevapiirangu. Valitud filtrid rakenduvad tabelile ja kokkuvõttele ning tühja tulemuse korral antakse sellest teada.

Lõiguanalüüs kasutab ainult FIT-is `active`-märgisega ringe; soojendus, taastelõigud ja lõdvestus jäetakse välja. Väljad **Alates (kiireim)** ja **kuni (aeglaseim)** määravad analüüsitava tempovahemiku kujul `M:SS` min/km. Kiireima tempo piiri võib tühjaks jätta; vaikimisi aeglaseima tempo piir on 5:30/km. Nupp **Kõik aktiivlõigud** eemaldab mõlemad piirid. Aktiivlõikude režiimis arvutatakse töötempo valitud lõikude koguaja ja kogudistantsi suhtena, et pikemad lõigud saaksid tempole rohkem kaalu. RPE kokkuvõte arvutab tempo järgi aktiivlõikude RPE ja töökoormuse; tempo vahemikud on 15 sekundit. Aktiivlõikude režiimis jäetakse jooks välja, kui selles pole valitud tempovahemikku jäävaid lõike. Kui enesehinnangu väljad puuduvad, kuvatakse **Hinnang - märkimata**.
