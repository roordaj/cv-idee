# `sensor-verouderd` — Sensor verouderd

- **Id:** `sensor-verouderd` · **Huidige versie:** 1.0.0
- **Code:** `backend/src/cvidee/rules/data_quality.py` · **Issue:** #32

## Doel

Meldt STALE-kwaliteitsgebeurtenissen per signaal. De pipeline bepaalt de maximale leeftijd en past die alleen toe bij verwachte regelmatige rapportage.

## Toepasbaarheid

Signaal-id, bijvoorbeeld room_temperature@room:slaapkamer. Cv-patroonregels sluiten onvolledige cycli, tapwater en bijzondere perioden uit; kwaliteits- en tapwaterinformatie blijft zichtbaar.

## Signalen

Geen verplichte rol. Een STALE-gebeurtenis is nodig; ouderdom van een alleen-bij-wijziging-signaal is onvoldoende.

## Parameters

window_days: 7 (3–28). Maximale leeftijd en heartbeat-keuze staan op de signaalkoppeling. Standaardwaarden zijn configureerbare voorstellen, geen universele normen. De instellingen-API valideert de geregistreerde schema's.

## Zekerheid

Hoog (gemeten): overschrijding van de ingestelde leeftijd is geregistreerd. Geen bewezen fysieke sensorstoring.

## Hypotheses

Verouderde waarden tellen onbekend en worden niet met nieuwere waarden tot een temperatuurconclusie gecombineerd.

## Advies

Geen optimalisatieadvies. Controleer sensor en verwachte rapportagefrequentie. Bij onvoldoende bewijs is het advies uitsluitend een aanvullende meting. Voorwaarden: bruikbare gegevens buiten bijzondere perioden. Evaluatie na aanvullende gegevens; succes is dat de ontbrekende gegevens bruikbaar zijn. Er is geen terugdraaicriterium voor een instellingswijziging omdat geen instelling wordt gewijzigd.

## Herstel

Afwezigheid van het patroon is pas herstel bij voldoende gegevens en het herstelcriterium van de bevindingen-engine. Een datagat telt nooit als herstel. Kwaliteitsmeldingen blijven zolang hun gebeurtenissen in het beoordelingsvenster staan.

## Wijzigingen

### 1.0.0 — 2026-10-09

- Eerste versie, met scenario- en uitsluitingstests.
