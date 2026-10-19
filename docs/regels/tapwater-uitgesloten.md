# `tapwater-uitgesloten` — Tapwater blijft zichtbaar, uitgesloten van cv-conclusies

- **Id:** `tapwater-uitgesloten` · **Huidige versie:** 1.1.0
- **Code:** `backend/src/cvidee/rules/dhw.py` · **Issue:** #32

## Doel

Een info-bevinding wanneer in het beoordelingsvenster ten minste 10 branderperioden als tapwater zijn geclassificeerd, of wanneer minstens 4 korte cv-cycli de tapwatercontext relevant maken voor de interpretatie. Gewone individuele tapwaterperioden blijven zichtbaar in de tijdlijn zonder extra bevinding. Ook een onvolledige tapwaterperiode blijft zichtbaar; er wordt geen bekende duur verzonnen.

## Toepasbaarheid

boiler:dhw; geen bundelondersteuning. Cv-patroonregels sluiten onvolledige cycli, tapwater en bijzondere perioden uit; kwaliteits- en tapwaterinformatie blijft zichtbaar.

## Signalen

Vlam en bedrijfsmodus verplicht. Tapwater blijft uitgesloten van korte-cycli- en cv-temperatuurregels.

## Parameters

window_days: 7 (3–28). Standaardwaarden zijn configureerbare voorstellen, geen universele normen. De instellingen-API valideert de geregistreerde schema's.

## Zekerheid

Hoog bij minstens 90% kerndekking; anders matig. Geen hoog (gemeten) voor een interpretatie van de bedrijfsmodus.

## Hypotheses

Uitleg van uitsluiting, geen cv-overtemperatuurdiagnose.

## Advies

Geen advies nodig. Ter informatie zichtbaar gehouden. Bij onvoldoende bewijs is het advies uitsluitend een aanvullende meting. Voorwaarden: bruikbare gegevens buiten bijzondere perioden. Evaluatie na aanvullende gegevens; succes is dat de ontbrekende gegevens bruikbaar zijn. Er is geen terugdraaicriterium voor een instellingswijziging omdat geen instelling wordt gewijzigd.

## Herstel

Afwezigheid van het patroon is pas herstel bij voldoende gegevens en het herstelcriterium van de bevindingen-engine. Een datagat telt nooit als herstel. Kwaliteitsmeldingen blijven zolang hun gebeurtenissen in het beoordelingsvenster staan.

## Wijzigingen

### 1.0.0 — 2026-10-09

- Eerste versie, met scenario- en uitsluitingstests.

### 1.1.0 — 2026-10-19

- Toon de tapwatercontext-bevinding alleen bij herhaalde draws of bij een kortecycli-patroon dat DHW-uitsluiting voor de interpretatie relevant maakt.
