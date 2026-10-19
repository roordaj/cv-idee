# Zoneanalyse: ketelgedrag en beschikbare warmteafgifte (FR-18)

## Doel en afbakening

Zoneanalyse vergelijkt waargenomen CV-branderstarts en korte cycli met het aantal
zones dat op dat moment warmte vraagt of waarvan de klepstatus een open toestand
meldt. Het resultaat beschrijft samenhang en meetkwaliteit. Het stelt niet vast dat
een zone fysiek warmte afgeeft, dat een klep werkelijk open is, of dat een laag
zoneaantal de oorzaak van een ketelgedrag is.

De app leest alleen Home Assistant-signalen. Een `zone_demand` is een gemapte
warmtevraagstatus. Een `valve_state` is de gemelde klepstatus en kan in de bron een
commando zijn. Die rollen blijven afzonderlijke metingen; twee signalen worden niet
samengevoegd alsof ze hetzelfde betekenen. Geen codepad stuurt kleppen, ketel of
thermostaat aan.

De uitbreiding gebruikt bestaande zone-scoped signalen, de versiebeheerde
installatieprofielstructuur, kwaliteitsintervallen, CV-cycli en korte-cycli-
classificatie. Zoneanalyse voegt geen nieuwe branderclassificatie of diagnose toe.

## Zoneconfiguratie en signaalbetekenis

Elke zone heeft een stabiele sleutel, een zichtbare naam en een koppeling aan een
bestaand circuit. De installatie-API moet deze zones kunnen lezen en opslaan in de
profielversie, waarna `zone_demand` en `valve_state` per zone kunnen worden
gekoppeld. Een onbekende of niet-gemapte zone blijft expliciet zichtbaar.

`GET /api/installation` geeft de zone-inventaris terug als `key`, `name` en
`circuit_key`; `PUT /api/installation` valideert unieke sleutels en bestaande
circuitkoppelingen. De inventaris is onderdeel van de onveranderlijke
profielversie. Een profielwijziging maakt geen nieuwe signaalkoppelingen aan en
verandert de identiteit van bestaande koppelingen niet. Een zonekoppeling is alleen
beschikbaar zolang de zonesleutel in het actuele profiel staat.

De bestaande catalogus behandelt beide waarden als gerapporteerd en verwacht een
boolean. De invoerlaag normaliseert alleen herkende waarden naar actief/inactief;
onbekende of niet-parseerbare waarden blijven `unknown`. Er wordt geen waarheid
afgeleid uit een numeriek percentage of vrije tekst die niet eenduidig is.
Zonder expliciete bronwaardetabel worden alleen `on`/`off`, `true`/`false` en
`1`/`0` als binaire statussen genormaliseerd.

Voor elke zone-mapping wordt de door de gebruiker gekozen rol getoond:

- **Zone vraagt warmte:** bron meldt dat de zone warmtevraag heeft. Dit is geen
  bewijs dat de warmtebron of afgifte fysiek actief is.
- **Klep meldt open/gesloten:** bron meldt een klepstatus of commando. Toon de
  bronsoort zoals gemapt; “open” bewijst niet dat de klep fysiek beweegt of dat er
  debiet is.

Wanneer beide rollen voor een zone bestaan, blijven zij afzonderlijk gerapporteerd.
Een verschil tussen vraag en klepstatus wordt als signaalverschil getoond, zonder
automatisch defect of oorzaak af te leiden. Geen enkele klepstatus wordt naar
debiet, doorstroming, fysieke opening of vermogen omgerekend.

Zone- en signaalconfiguratie volgt profielversies. Analyse en historie verwijzen
naar het profiel dat geldig was in het onderzochte tijdvak. Een profielwijziging
overschrijft geen oude zone-identiteit of eerdere evaluatie.

## Koppeling aan ketelgedrag

Een analyse-eenheid is een volledige CV-brandercyclus die al door de bestaande
pipeline is gereconstrueerd. Tapwatercycli, onbekende bedrijfsmodus en cycli zonder
de benodigde warmtevraagcontext worden niet stilzwijgend als CV-zonevergelijking
gebruikt. De analyse gebruikt de actuele cyclusclassificatie (waaronder bestaand
`short`) en maakt haar versie/meetperiode zichtbaar.

Voor een cyclus wordt het aantal actief gemelde zones bepaald op het startmoment van
de cyclus, tijdens CV-warmtevraag. Een signaal telt alleen wanneer het profiel en de
zone-mapping geldig zijn, de toestand op dat moment bekend is en het signaal binnen
de bestaande versheids-/kwaliteitsgrens valt. Vertraagde, stale, ontbrekende of
tegenstrijdige waarden tellen niet als actief of inactief; zij maken de zonecount
onvolledig.

Counts op basis van `zone_demand` en `valve_state` worden apart berekend en benoemd.
Per zone-aantal toont de analyse ten minste het aantal beoordeelbare cycli, het
aantal cycli dat als kort is geclassificeerd, de gemeten tijdsdekking en de
meetbasis. Een onvolledige zonecount wordt apart weergegeven en niet gebruikt om
een volledige count te veinzen. De gebruiker kan van een count naar de bijbehorende
cycli en zone-signalen doorklikken.

Een configureerbare, zichtbare grens kan aangeven tot welk aantal actieve zones de
app de context “weinig actieve zones” noemt. Er is geen universele grens en dus geen
verborgen standaardwaarde. Zonder ingestelde grens toont de app de verdeling per
concreet zone-aantal, maar trekt zij geen conclusie dat het aantal laag of hoog is.
De bestaande korte-cyclusgrens blijft de enige bron voor de classificatie “kort”.

De analyse mag beschrijven dat korte cycli vaker voorkomen bij bepaalde gemeten
zonecounts, mits beide aantallen en de dekking zichtbaar zijn. Zij mag dit niet
verwoorden als verklaring, oorzaak of aanbeveling om zones/kleppen anders aan te
sturen. Is het aantal beoordeelbare cycli of de gelijktijdige signaaldekking
onvoldoende volgens de expliciete analysecriteria, dan is het oordeel
“Onvoldoende bewijs” of de beschikbaarheid “Beperkt”, met reden.

## Beschikbaarheid en gegevenskwaliteit

- Geen geconfigureerde zones of zone-scoped mappings: zoneanalyse is niet
  beschikbaar; toon welke profiel-/signaalgegevens ontbreken.
- Wel vlam-/cyclusgegevens maar geen zonevraag of klepstatus: toon de zoneanalyse als
  niet beschikbaar, niet als nul actieve zones.
- Alleen `zone_demand` beschikbaar: vergelijk op gemelde zonevraag en vermeld dat
  klepstatus ontbreekt.
- Alleen `valve_state` beschikbaar: vergelijk op gemelde klepstatus/commando en
  vermeld dat dit geen fysieke opening of warmteafgifte bewijst.
- Een deel van de zones heeft geen bruikbare status: toon bekende en ontbrekende
  zones, dekking en onvolledige counts; trek geen “weinig zones”-conclusie uit een
  partieel profiel.
- Alle signalen onbekend/stale of geen CV-warmtevraag: er is geen betrouwbare
  vergelijking; dit is onbekend/onvoldoende bewijs, niet nul activiteit.
- Gelijktijdige vraag- en klepstatus die verschillen blijven twee bronnen; er wordt
  geen prioriteit of fysieke werkelijkheid verondersteld.

Beschikbaarheid volgt de bestaande statussen `available`, `limited` en
`not_available`, met ontbrekende/perkende signalen en zonekeys. Zekerheid is een
gedocumenteerde categorie, nooit een percentage.

## UI- en API-impact

- Breid het installatieprofiel-endpoint uit zodat de gebruiker zones met stabiele
  sleutel, naam en circuit kan bekijken en vastleggen; valideer unieke sleutels,
  geldige circuitkoppelingen en hergebruik van zonescopes in signaalmapping.
- Voeg een zoneanalysekaart/detail toe aan de bestaande analyse-/bevindingenflow:
  zonecountverdeling, korte cycli per count, bronsoort, dekking, ontbrekende zones,
  profielperiode en links naar relevante cycli.
- Toon vraagstatus en gemelde klepstatus apart wanneer beide bestaan.
- Leg een eventuele grens voor “weinig zones” als zichtbare configureerbare
  parameter vast; laat deze leeg/onbekend totdat de gebruiker een waarde kiest.
- Toon de disclaimer dat samenhang geen oorzaak bewijst en dat gemelde klepstatus geen
  fysieke opening of debiet bewijst.
- Voeg Nederlandse teksten en beschikbaarheids-/lege-/onvoldoende-data-states toe
  aan design v3 voordat de frontend deze implementeert. API-contractwijzigingen
  werken door in OpenAPI en frontend-types.

## Acceptatie- en scenariotests

1. Met vers gemapte warmtevraagstatus voor alle geconfigureerde zones worden CV-
   cycli gegroepeerd naar het aantal zones dat bij cyclusstart warmte vroeg.
2. Met alleen klepstatus worden resultaten benoemd als “klep meldt open”; zij
   verklaren geen fysieke opening, debiet of warmteafgifte.
3. Wanneer beide rollen bestaan, blijven vraag- en klepcount gescheiden; een
   verschil levert context/kwaliteit op en geen defectdiagnose.
4. Tapwatercycli en cycli zonder bekende CV-warmtevraag tellen niet mee in de
   zonevergelijking.
5. Een ontbrekende/stale zone maakt de count onvolledig; het ontbrekende signaal
   wordt getoond en niet als inactief geteld.
6. Zonder ingestelde grens voor “weinig zones” toont de UI counts en aantallen,
   maar geen laag-/hooglabel of diagnose.
7. Met een ingestelde grens wordt alleen een beschrijvende vergelijking met
   voldoende bewijs getoond; zij beweert geen oorzakelijk verband.
8. Een bestaande `short`-classificatie wordt hergebruikt; andere cycli krijgen geen
   nieuwe of gewijzigde classificatie door zonegegevens.
9. Oude tijdvakken blijven gekoppeld aan de bijbehorende profiel-/zoneversie.
10. Tests bevestigen dat er geen HA-bedieningsservice wordt aangeroepen en dat
    MQTT alleen eigen analyse-topics gebruikt.

## Implementatievolgorde

1. Ontwerp zoneconfiguratie, signaalherkomst, analyseverdeling, drilldown en
   kwaliteitstoestanden in design v3.
2. Maak zones configureerbaar via het installatieprofiel en valideer zone-scoped
   signaalkoppelingen per profielversie.
3. Implementeer zuivere zonecontext-/countberekening en een analyse-/regelresultaat
   dat de bestaande cycli en classificaties hergebruikt.
4. Integreer runner/API en daarna UI/drilldown; test volledige dekking,
   gedeeltelijke/stale data, verschillen tussen signalen en uitgesloten cycli.

Vervolgissues: #164 (ontwerp), #165 (zoneprofiel en mappings), #166
(zonecontext-analyse), #167 (frontend). #165 hangt af van #56 en #164; #166 hangt
af van #56 en #165; #167 hangt af van #164, #165 en #166.

## Implementatie van #166

`GET /api/zones/analysis` groepeert volledige CV-cycli met bekende CV-warmtevraag
naar het aantal zonevraagstatussen en, afzonderlijk, het aantal gemelde open
klepstatussen op het cyclusstartmoment. De response bevat per bron dekking als het
aandeel beoordeelbare cyclusstarts, korte-cycli-aantallen volgens de bestaande
classificatie, links via cyclusstarttijd en per onvolledige telling de bekende en
ontbrekende zones. De analyse gebruikt het profiel dat aan het einde van het
tijdvak geldig is en knipt de start af op de profielversiegrens.

De zichtbare instelling `few_active_zones_max` is optioneel en standaard leeg.
Zonder ingestelde grens bevat de response geen laag-/hooglabel. Wanneer de grens is
ingesteld, markeert zij uitsluitend de beschrijvende count-bins die aan die grens
voldoen. De vergelijking geeft geen oorzaak of regeladvies.
