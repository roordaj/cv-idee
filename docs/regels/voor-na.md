# `voor-na` — effect van een vastgelegde wijziging

- **Id:** `voor-na` · **Huidige versie:** 1.0.0 · **Categorie:** `effect_measurement`
- **Code:** `backend/src/cvidee/rules/before_after.py` · **Issue:** #39
- **Requirements:** FR-25, FR-30, FR-32, FR-41

## Doel

Maakt afwegingen, ongunstige uitkomsten, overschreden terugdraaicriteria en
onvoldoende vergelijkbare gegevens zichtbaar. Minder starts met slechter comfort
wordt nooit als onvoorwaardelijke verbetering beoordeeld. Een waargenomen verschil
bewijst geen oorzaak of energiebesparing.

De gebruikersgerichte analyse `before_after` is beschikbaar als er een wijzigingsevaluatie
kan worden uitgevoerd. Overlappende wijzigingen, niet-vergelijkbaar weer of gewijzigde
kamerdoelen maken de analyse beperkt. Zonder wijziging of met uitsluitend onvoldoende
bewijs is de analyse niet beschikbaar; een `voor-na`-bevinding kan de ontbrekende gegevens
wel uitleggen zonder de analyse als beschikbaar te presenteren. Deze status komt uit de
productie-evaluatiefeiten, niet uit de conclusie van de bevinding.

## Toepasbaarheid

De evaluatie geldt voor een vastgelegde wijziging, met even lange referentie- en
observatieperioden (standaard zeven dagen). Alleen CV-cycli tellen mee in de
cycluskengetallen. Gemarkeerde perioden met uitsluiting van vergelijkingen tellen
niet mee. Aanvoer wordt alleen tijdens stabiel CV-bedrijf gemiddeld.

`history_ms` is nul: de IO-laag levert afzonderlijk berekende evaluatiefeiten met
hun eigen perioden. Daardoor verandert de contextperiode van andere regels niet.
De scope is `change:W-nn`. Overlappende wijzigingen vormen één onderzoekspunt;
de afzonderlijke evaluaties blijven via het wijzigingslogboek beschikbaar.

## Signalen

De eigen evaluatie controleert vlamstatus, bedrijfsmodus, warmtevraag,
buitentemperatuur en gekoppelde werkelijke en gewenste kamertemperaturen.
Ontbrekende gegevens leveren onvoldoende bewijs op. De regel heeft geen globale
signaalpoort, omdat een bevinding over ontbrekend bewijs anders niet zichtbaar kan
worden. Gewenste temperatuur is een doeltoestand die geldig blijft tot een wijziging;
een onbekende of verouderde doeltoestand wordt niet aangenomen.

De daadwerkelijke mediaan tussen vlamrapportages bepaalt de resolutie. Boven de
halve kortecyclusgrens is een effectoordeel niet onderbouwd; tussen een kwart en de
helft blijft de zekerheid voorlopig. Verwachte resolutie vervangt geen waarnemingen.

## Parameters

| Parameter | Standaard | Gebruik |
|---|---|---|
| `comparison_days` | 7 dagen | Even lange perioden vóór/na |
| `min_period_coverage_pct` | 90% | Minimale dekking per periode |
| `comparable_weather_c` | 2,0 °C | Maximaal verschil voor vergelijkbaar weer |
| `limited_weather_c` | 4,0 °C | Daarboven geen toeschrijving |
| `comfort_margin_c` | 0,5 °C | Onderschrijding die als te koud telt |
| `allowed_comfort_loss_h_per_week` | 4,0 u/week | Standaard terugdraaigrens per ruimte |
| `short_cycle_min` | 3,0 min | Korte stops tijdens vraag |
| `min_observation_hours` | 6,0 uur | Benodigde waargenomen warmtevraagtijd per periode |

De grens voor beperkt vergelijkbaar weer mag niet lager zijn dan de grens voor
vergelijkbaar weer. Een machineleesbaar terugdraaicriterium bij het gekoppelde advies
kan de ruimte en grens overschrijven. Een niet ondersteund criterium wordt als niet
automatisch beoordeelbaar vermeld; de app verzint geen vervangend criterium.

## Zekerheid

- **Redelijk:** de observatieperiode is compleet, kernsignalen en comfortparen hebben
  voldoende dekking, beide perioden bevatten voldoende warmtevraagtijd en volledige
  CV-cycli, de vlamresolutie is voldoende en weer en kamerdoelen zijn vergelijkbaar.
- **Voorlopig:** bekende verschillen of andere wijzigingen beperken de vergelijking,
  of de vlamresolutie is slechts beperkt. Bij onvergelijkbare omstandigheden wordt geen
  individueel effect toegeschreven.
- **Onvoldoende bewijs:** ontoereikende dekking, resolutie, comfortgegevens of
  waarnemingen. Datagaten zijn geen verbetering.

Het plafond is redelijk: de vergelijking is observationeel en bewijst geen oorzaak.
Kamerdoelen worden per lokaal weekdag-/kwartierprofiel vergeleken; een gelijk gemiddelde
kan een veranderd programma niet maskeren. Constante gelijke doelen zijn ook bij kortere
perioden vergelijkbaar. Ontbrekende profieldekking beperkt de vergelijking.

## Hypotheses

De regel stelt geen nieuwe technische diagnose. Zij verwijst naar de gemeten effecten
en bekende beperkingen, waaronder gelijktijdige wijzigingen, afwijkend weer,
gewijzigde kamerdoelen, uitgesloten perioden en ontbrekende gegevens.

## Advies

Bij een overschreden comfortcriterium: beoordeel terugzetten naar de oude vastgelegde
waarde. Bij onvoldoende bewijs of onvergelijkbaarheid: verzamel vergelijkbare gegevens
met één wijziging tegelijk en gekoppelde kamerdoelen. Er wordt geen verandering aan
ketel, thermostaat of verdeler uitgevoerd en geen besparing in euro's of kW bedacht.

## Herstel

De oorspronkelijke bevindingen-engine bewaakt herstel. Ontbrekende gegevens worden
niet als herstel gebruikt; een eerder geactiveerde opvolgstatus blijft bij onvoldoende
bewijs behouden. Uitvoering of terugzetten wordt door de gebruiker vastgelegd. De
historische evaluatie blijft beschikbaar en wordt bij herberekening opnieuw onderbouwd.

## Wijzigingen

### 1.0.0 — 2026-10-15

- Eerste versie: vergelijkbaarheid, cycli en comfort, terugdraaicriteria en adviessnapshots.
