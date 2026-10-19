# `hydraulisch` — Mengverdeler zonder bruikbare lokale gegevens

- **Id:** `hydraulisch` · **Huidige versie:** 1.0.1
- **Code:** `backend/src/cvidee/rules/hydraulic.py` · **Issue:** #33

## Doel

Alleen mengverdeler-circuits. Geen waarschuwing voor directe radiatoren. Bij alleen tapwater of uitsluitend gemarkeerd cv-bedrijf geen hydraulische conclusie. Zonder cycli betreft de melding alleen de bekende installatietopologie.

## Toepasbaarheid

circuit:<key>:ch; ondersteunt kort-branden (circuitrelatie bij bundelen in #35). Cv-patroonregels sluiten onvolledige cycli, tapwater en bijzondere perioden uit; kwaliteits- en tapwaterinformatie blijft zichtbaar.

## Signalen

Geen verplichte rol: ontbreken is de diagnosegrens. Bruikbare verdeleraanvoer én -retour, zonder gemelde misuitlijning, of lokaal circuitdebiet nemen deze ontbrekende-data-melding weg. Keteldebiet bewijst geen debiet achter de mengverdeler. Deze regel geeft ook bij voldoende gegevens geen lusadvies.

De informatiewaarschuwing kan worden uitgevoerd terwijl de hydraulische analyse beperkt is. Met ketelaanvoer en -retour maar zonder bruikbare lokale metingen is de analyse `limited`, met expliciete ontbrekende of verouderde signalen. Zonder een van beide keteltemperaturen is de analyse `unavailable`. Volledige lokale dekking vereist per mengverdeler een bruikbaar temperatuurpaar of debiet op dat eigen circuit; een keteldebietmeter of metingen van een ander circuit vullen dit niet aan. Beschikbaarheid is geen toestemming om een lokale diagnose te doen: de bewijsgrenzen van de regel blijven gelden.

## Parameters

min_assessment_coverage_pct: 80 (50–100); window_days: 7 (3–28). Verouderde en onvoldoende gedekte lokale signalen zijn niet bruikbaar. Standaardwaarden zijn configureerbare voorstellen, geen universele normen. De instellingen-API valideert de geregistreerde schema's.

## Zekerheid

Altijd onvoldoende bewijs voor een hydraulische conclusie; ernst `info`, uitsluitend een aanvullende meting.

## Hypotheses

Ketel-ΔT is niet ΔT per vloerverwarmingslus. Geen algemene aanbeveling om ketelretour te verhogen of lussen op vaste ΔT in te stellen.

## Advies

Aanvullende meting: sensoren op verdeleraanvoer en -retour van het betreffende circuit. Geen directe energieclaim, omvang of instellingswijziging. Bij onvoldoende bewijs is het advies uitsluitend een aanvullende meting. Voorwaarden: bruikbare gegevens buiten bijzondere perioden. Evaluatie na aanvullende gegevens; succes is dat de ontbrekende gegevens bruikbaar zijn. Er is geen terugdraaicriterium voor een instellingswijziging omdat geen instelling wordt gewijzigd.

## Herstel

Afwezigheid van het patroon is pas herstel bij voldoende gegevens en het herstelcriterium van de bevindingen-engine. Een datagat telt nooit als herstel. Kwaliteitsmeldingen blijven zolang hun gebeurtenissen in het beoordelingsvenster staan.

## Wijzigingen

### 1.0.1 — 2026-10-18

- De melding over ontbrekende lokale gegevens heeft ernst info.
- Keteldata met ontbrekende lokale verdelerdata maakt de hydraulische analyse beperkt; de waarschuwing zelf blijft uitvoerbaar.
- Lokale beschikbaarheid wordt per mengverdeler beoordeeld, zonder keteldebiet of een ander circuit als vervanging te gebruiken.

### 1.0.0 — 2026-10-09

- Eerste versie, met scenario- en uitsluitingstests.
