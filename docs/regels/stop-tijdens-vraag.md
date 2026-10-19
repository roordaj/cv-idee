# `stop-tijdens-vraag` — Herhaald stoppen tijdens aanhoudende warmtevraag

- **Id:** `stop-tijdens-vraag` · **Huidige versie:** 1.1.0
- **Code:** `backend/src/cvidee/rules/stop_during_demand.py` · **Issue:** #31

## Doel

De regel ondersteunt `kort-branden`: alleen herhaalde `stop_during_demand`-cycli korter dan de standaard kortecyclusgrens van 3 minuten kunnen een bevinding onderbouwen. Langere onderbrekingen tijdens warmtevraag blijven als waarnemingen in de tijdlijn staan; herhaling alleen is geen optimalisatieadvies. Normaal einde van warmtevraag, tapwater, datagaten en gemarkeerde perioden tellen niet mee.

## Toepasbaarheid

boiler:ch; ondersteunt kort-branden. Cv-patroonregels sluiten onvolledige cycli, tapwater en bijzondere perioden uit; kwaliteits- en tapwaterinformatie blijft zichtbaar.

## Signalen

Vlam, bedrijfsmodus en warmtevraag verplicht. Aanvoer, gewenste aanvoer en modulatie optioneel. Temperatuur vlak vóór stop komt alleen uit OVERSHOOT_AT_STOP met uitgelijnde tijdsbasis. Gemelde blokkeringen komen uitsluitend uit directe fault_blocking-modussegmenten rond de stop.

## Parameters

min_stop_cycles: 4 (2–30); demand_after_stop_s: 60 (0–600); min_observation_h: 6 (1–72); structural_days: 2 (1–14); window_days: 7 (3–28). Herhalingsdagen mogen het venster niet overschrijden. Standaardwaarden zijn configureerbare voorstellen, geen universele normen. De instellingen-API valideert de geregistreerde schema's.

## Zekerheid

Plafond redelijk. Onder 80% kerndekking of de minimale observatieduur: onvoldoende bewijs. Herhaling op minder dan structural_days: voorlopig. Redelijk vereist 90% dekking, 12 volledige cv-cycli en herhaling op 3 dagen. Ontbrekende optionele signalen verlagen de categorie.

## Hypotheses

Temperatuur, modulatie en blokkeringen zijn correlaties, geen bewezen oorzaak. Het minimum van waargenomen modulatie binnen de cycli is geen gevalideerd ketelminimum. Geen omzetting naar kW.

## Advies

Meetadvies: controleer temperatuur, modulatie en blokkeringen rond de stoptijden. Geen instellingswijziging. Bij onvoldoende bewijs is het advies uitsluitend een aanvullende meting. Voorwaarden: bruikbare gegevens buiten bijzondere perioden. Evaluatie na aanvullende gegevens; succes is dat de ontbrekende gegevens bruikbaar zijn. Er is geen terugdraaicriterium voor een instellingswijziging omdat geen instelling wordt gewijzigd.

## Herstel

Afwezigheid van het patroon is pas herstel bij voldoende gegevens en het herstelcriterium van de bevindingen-engine. Een datagat telt nooit als herstel. Kwaliteitsmeldingen blijven zolang hun gebeurtenissen in het beoordelingsvenster staan.

## Wijzigingen

### 1.0.0 — 2026-10-09

- Eerste versie, met scenario- en uitsluitingstests.

### 1.1.0 — 2026-10-19

- Beperk de ondersteunende bevinding tot herhaalde korte stops; lange stops tijdens warmtevraag blijven alleen waarnemingen.
