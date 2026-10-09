# `dataverlies` — Verbindingsverlies blijft onbekende tijd

- **Id:** `dataverlies` · **Huidige versie:** 1.0.0
- **Code:** `backend/src/cvidee/rules/data_quality.py` · **Issue:** #32

## Doel

Bundelt overlappende/aansluitende CONNECTION_LOST-gebeurtenissen per bron. Rapporteert verlies en betrokken onvolledige cycli; geen optimalisatieconclusie.

## Toepasbaarheid

source:ws of source:can_gateway; geen bundelondersteuning. Cv-patroonregels sluiten onvolledige cycli, tapwater en bijzondere perioden uit; kwaliteits- en tapwaterinformatie blijft zichtbaar.

## Signalen

Expliciete `UNAVAILABLE`-gebeurtenissen krijgen daarnaast een melding per signaal als ze
niet al door een bronmelding gedekt worden. Hierbij wordt geen verbindingsverlies als
oorzaak verzonnen: HA kan verbonden blijven terwijl een apparaat geen waarde levert.

Geen verplichte signaalrol: de regel moet ook bij verdwenen data werken. WS omvat de gekoppelde signalen. Bij CAN worden alleen expliciet geconfigureerde gateway-signalen genoemd; anders is de getroffen entiteitenlijst onbekend.

## Parameters

window_days: 7 (3–28). Gegevensverlies blijft ook in bijzondere perioden relevant. Standaardwaarden zijn configureerbare voorstellen, geen universele normen. De instellingen-API valideert de geregistreerde schema's.

## Zekerheid

Hoog (gemeten) bij direct geregistreerd verbindingsverlies. Matig bij afgeleid gatewayverlies (detail derived). De dekking in het verloren tijdvak is 0; dat is geen zekerheidspercentage.

## Hypotheses

Geen diagnose van de oorzaak van de uitval. Onbekend is niet brander uit; reconnect-peilingen zijn geen waargenomen starts.

## Advies

Geen optimalisatieadvies. Bij herhaling: gateway en HA-verbinding controleren. Bij onvoldoende bewijs is het advies uitsluitend een aanvullende meting. Voorwaarden: bruikbare gegevens buiten bijzondere perioden. Evaluatie na aanvullende gegevens; succes is dat de ontbrekende gegevens bruikbaar zijn. Er is geen terugdraaicriterium voor een instellingswijziging omdat geen instelling wordt gewijzigd.

## Herstel

Afwezigheid van het patroon is pas herstel bij voldoende gegevens en het herstelcriterium van de bevindingen-engine. Een datagat telt nooit als herstel. Kwaliteitsmeldingen blijven zolang hun gebeurtenissen in het beoordelingsvenster staan.

## Wijzigingen

### 1.0.0 — 2026-10-09

- Eerste versie, met scenario- en uitsluitingstests.
