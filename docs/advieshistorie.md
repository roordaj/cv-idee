# Advieshistorie

`GET /api/history?limit=50&offset=0` leest onveranderlijke adviessnapshots uit de
database, nieuwste eerst. Bij gelijke tijdstippen bepaalt het snapshotnummer de
volgorde. De bestaande frontend toont deze gegevens onder **Advieshistorie**.

De runner bewaart bij het eerste advies de meetperiode, oorspronkelijke
waarneming, interpretatie en aanbeveling, regel-id en versie, effectieve
parameters, configuratiehash, instellingenrevisie en installatieprofielversie.
Specificaties worden inclusief onbekende waarden meegekopieerd. Een wijziging
van configuratie, regelversie, parameters of bundelonderbouwing levert bij een
open advies een nieuwe snapshot op; bestaande snapshots worden niet bijgewerkt.

Elke daadwerkelijke opvolgstatuswijziging krijgt een nieuwe snapshot in dezelfde
transactie, inclusief de laatste gebruikersnotitie. Dit geldt ook voor automatisch
heropenen na uitstel of onderbouwde verslechtering. Het opnieuw aanbieden van
dezelfde status zonder wijziging van uitsteldatum voegt geen duplicaat toe.
Bij de eerste opvolging van een open advies wordt de op dat moment zichtbare
onderbouwing vastgelegd. Bij verdere opvolging blijft die adviesonderbouwing
behouden; latere meetgegevens vervangen haar niet stilzwijgend.
Notities die na een statusovergang worden toegevoegd staan bij een volgende
statusovergang in de historie; het oude snapshot blijft intact.

Voor oude bevindingen zonder snapshot wordt bij de eerste statusovergang alleen
beschikbare, vastgelegde analyseherkomst gebruikt. Ontbrekende instellingen worden
niet aangevuld met huidige defaults. Eerdere statusovergangen worden niet
achteraf gereconstrueerd.

De API levert naast de weergaveteksten ook `parameters`, `profile_version` en
`config_hash`. **Sindsdien** vergelijkt de opgeslagen regelversie en parameters
met het actuele regelregister en de huidige instellingen. De oude parameters
blijven zichtbaar, met Nederlandse decimale komma. Een verwijderde regel wordt
expliciet als niet meer beschikbaar vermeld.

Wijzigingsteksten komen uit de sectie **Wijzigingen** in `docs/regels/*.md`.
De samenvattingen worden als package-resource meegeleverd, zodat de container
geen toegang tot de documentatiemap nodig heeft. Genereer na wijzigingen:

```sh
cd backend
uv run python -m cvidee.rules.changelog ../docs/regels src/cvidee/rules/changelog.json
```

Een test bewaakt dat de meegeleverde samenvattingen overeenkomen met de docs.
