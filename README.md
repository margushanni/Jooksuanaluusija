# Garmini jooksuanalüüs

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
