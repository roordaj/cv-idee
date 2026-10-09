# `temperatuurverloop` — Afwijkend temperatuurverloop tijdens cv-bedrijf

- **Id:** `temperatuurverloop` · **Huidige versie:** 1.0.0
- **Code:** `backend/src/cvidee/rules/temperature.py` · **Issue:** #31

## Doel

Detecteert herhaald doorschieten en een uitgelijnde retour hoger dan aanvoer tijdens stabiel cv-bedrijf. Geen oordeel over schadelijkheid, gewenste lus-ΔT of oorzaak.

## Toepasbaarheid

boiler:ch; ondersteunt kort-branden en stop-tijdens-vraag. Cv-patroonregels sluiten onvolledige cycli, tapwater en bijzondere perioden uit; kwaliteits- en tapwaterinformatie blijft zichtbaar.

## Signalen

Vlam, modus, aanvoer en gewenste aanvoer verplicht; retour optioneel. Alleen CYCLE-kengetallen OVERSHOOT en BOILER_DELTA_T_STABLE met positieve tijdsbasis worden gebruikt. Geen verschil van losse cyclusmaxima of ongepaarde gemiddelden.

## Parameters

min_temperature_cycles: 4 (2–30); overshoot_margin_c: 0 (0–20 °C); overige venster-/observatieparameters als stop-tijdens-vraag. De nulmarge detecteert boven-gewenst, niet een universele schadelijkheidsnorm. Standaardwaarden zijn configureerbare voorstellen, geen universele normen. De instellingen-API valideert de geregistreerde schema's.

## Zekerheid

Zelfde criteria als stop-tijdens-vraag; dekking wordt ook begrensd door dekking van de gebruikte uitgelijnde kengetallen. Plafond redelijk.

## Hypotheses

Controle van sensorplaatsing en samenhang met brandergedrag. Een hydraulische oorzaak is niet vastgesteld.

## Advies

Meetadvies: sensorplaatsing controleren en uitgelijnde gegevens verzamelen. Geen ketelretour- of lusinstelling. Bij onvoldoende bewijs is het advies uitsluitend een aanvullende meting. Voorwaarden: bruikbare gegevens buiten bijzondere perioden. Evaluatie na aanvullende gegevens; succes is dat de ontbrekende gegevens bruikbaar zijn. Er is geen terugdraaicriterium voor een instellingswijziging omdat geen instelling wordt gewijzigd.

## Herstel

Afwezigheid van het patroon is pas herstel bij voldoende gegevens en het herstelcriterium van de bevindingen-engine. Een datagat telt nooit als herstel. Kwaliteitsmeldingen blijven zolang hun gebeurtenissen in het beoordelingsvenster staan.

## Wijzigingen

### 1.0.0 — 2026-10-09

- Eerste versie, met scenario- en uitsluitingstests.
