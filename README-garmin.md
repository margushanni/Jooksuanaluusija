# Garmin jooksuandmete päring

See lokaalne töövoog kasutab Garmini ametlikku `garmin-connect-personal-api-python` klienti, et tuua viimase 365 päeva jooksutegevuste kokkuvõtted faili `data/running_activities.json`.

## Esmakordne käivitus

Vaja on Python 3.12 või uuemat ning Garmini Personal API võtit. Ava PowerShell projekti kaustas ja käivita:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install garmin-connect-personal-api-python
.venv\Scripts\python.exe .\fetch_garmin_runs.py
```

Skript küsib API võtit peidetud sisestusena. Ära lisa võtit käsureale, faili ega vestlusesse. API võtme asemel Garmini klient hoiab vahemälus lühiajalist bearer-tokenit failis `.garmin-private\bearer-token-cache.json`; see fail ja allalaaditud treeninguandmed on Gitist välja jäetud.

## Järgmised käivitused

```powershell
.venv\Scripts\python.exe .\fetch_garmin_runs.py
```

Vaikimisi küsitakse viimase 365 päeva jookse. Perioodi saab muuta, näiteks viimase 90 päeva jaoks:

```powershell
.venv\Scripts\python.exe .\fetch_garmin_runs.py --days 90
```

Iga käivitus kirjutab `data\running_activities.json` faili uuesti. Fail sisaldab sinu isiklikke treeninguandmeid; hoia seda privaatsena.
