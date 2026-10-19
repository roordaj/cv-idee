# Vergelijking van ketel-, mengverdeler- en vloerverwarmingscircuit (FR-19)

## Doel en grenzen

Deze uitbreiding maakt zichtbaar wat op elk afzonderlijk verwarmingscircuit is
gemeten. De ketelmetingen blijven bij het ketelcircuit; mengverdelerwaarden horen
bij de betreffende mengverdeler; luswaarden horen bij één expliciet geïdentificeerde
vloerverwarmingslus. De gebruiker kan zo zien waar een temperatuurverschil is
waargenomen zonder te doen alsof de ketelmeting de vloerverwarming beschrijft.

De analyse beschrijft metingen en gegevenskwaliteit. Een lage of hoge ΔT is op
zichzelf geen diagnose, fout, rendementsmaat of aanbeveling. Er is geen universele
doel-ΔT voor alle ketels, verdelers, groepen en bedrijfsomstandigheden. De app
adviseert daarom niet algemeen om de ketelretour te verhogen of alle lussen op één
vaste ΔT in te stellen. De app stuurt geen ketel, pomp, mengklep, thermostaat of
lusdebiet aan.

Deze specificatie werkt FR-19 uit boven op het installatieprofiel, de signaalcatalogus,
de bestaande hydraulische beschikbaarheidsanalyse en bijzondere perioden. Zij
vervangt de beperkte-gegevensmelding uit #33 niet.

## Begrippen en meetwaarden

- **Ketelpaar:** gelijktijdig bruikbare ketelaanvoer en -retour (`flow_temperature`
  en `return_temperature` op de ketel-scope).
- **Verdelerpaar:** gelijktijdig bruikbare aanvoer en retour van dezelfde mengverdeler
  (`manifold_flow_temperature` en `manifold_return_temperature` op dezelfde
  verdeler-scope).
- **Luspaar:** gelijktijdig bruikbare aanvoer en retour van dezelfde, stabiel
  geïdentificeerde lus. Een sensorpaar op de mengverdeler is geen luspaar.
- **ΔT:** aanvoertemperatuur min retourtemperatuur binnen één paar en tijdvak. Toon
  het verschil in K (numeriek gelijk aan °C temperatuurverschil); toon nooit een
  verschil tussen losse of niet-uitgelijnde metingen.

Per paar en periode kan de analyse de waargenomen mediane ΔT en het bereik van de
bruikbare waarden tonen, samen met aantal meetpunten, tijdvak, dekking, datagaten,
veroudering en uitgesloten perioden. De meetbasis is dezelfde voor aanvoer en retour.
Onbekende intervallen blijven onbekend en worden niet als nul of als constante
ingevuld. Alleen een expliciet gevalideerde paarmeting levert ΔT op.

## Circuit- en lusidentiteit

De installatieprofielversie is leidend voor de relatie tussen circuit, mengverdeler,
ruimte en lus. Een circuit behoudt zijn stabiele sleutel. Een mengverdeler kan een
optionele inventaris van lussen bevatten met per lus een stabiele sleutel en
gebruikerslabel. De bestaande telling van lussen blijft voor oude profielen
behouden; een aantal zonder lusidentiteiten is geen toestemming om sensoren over
groepen te verdelen.

Lus-sensorsignalen krijgen een expliciete loop-scope met de stabiele lussleutel.
De mapping vermeldt dus de gemeten fysieke lus, niet alleen een vrije volgorde of
een afgeleide index. Een profielwijziging maakt een nieuwe profielversie; historische
analyse houdt de circuit- en lusidentiteiten aan die toen golden. Verwijderde of
hernoemde lussen overschrijven geen historische koppelingen.

De bestaande circuitdebietrol is geen temperatuurpaar. Een debietmeting mag als
afzonderlijke context worden getoond, maar vult ontbrekende aanvoer- of retourdata
niet aan en levert zelf geen lus-ΔT op. Keteldebiet, verdelerdebiet, kamertemperatuur
en waarden van een andere lus vullen een ontbrekende luspaarmeting evenmin aan.

## Analyse en bewijsgrenzen

1. Beoordeel alleen verwarmingsbedrijf in de bestaande relevante CV-context.
   Tapwater, onbekende modus, opstart-/naloopintervallen, niet-uitgelijnde samples,
   onbruikbare/verouderde sensoren en voor analyse uitgesloten bijzondere perioden
   leveren geen vergelijkbare ΔT-sample.
2. Bereken ieder paar afzonderlijk. Het ketelpaar wordt niet hernoemd als
   verdelerpaar. Een direct circuit mag naar het ketelpaar verwijzen, maar wordt niet
   als onafhankelijke tweede meting dubbel geteld.
3. Bereken een luspaar alleen als profielidentiteit, beide lus-sensorrollen,
   tijdsuitlijning en kwaliteitsvoorwaarden voor diezelfde lus bekend zijn. Deel een
   verdelerwaarde nooit toe aan alle lussen.
4. Als aanvoer lager is dan retour, toon de waarneming en een kwaliteits-/richting-
   beperking volgens de bestaande kwaliteitsregels; keer de aftrekking niet om en
   presenteer de absolute waarde niet als normale ΔT.
5. Vergelijk ketel, verdeler en lussen naast elkaar in hun eigen meetcontext. Geen
   conclusie over oorzaak, hydraulische balans, pompinstelling, mengtemperatuur,
   energieverbruik of comfort volgt enkel uit een verschil tussen die paren.
6. De bestaande hydraulische beschikbaarheid, dekkingsinstellingen en kwaliteits-
   classificaties bepalen of het resultaat beschikbaar, beperkt of niet beschikbaar
   is. Een ontbrekend paar blijft zichtbaar als ontbrekend; deze specificatie
   introduceert geen nieuwe numerieke kwaliteitsdrempel of streefwaarde.
7. Een concrete afwijkingsdetectie of insteladvies vereist een afzonderlijke
   refinement met gevalideerde installatiecontext, onderbouwing en expliciete
   configureerbare criteria. Tot die tijd is de UI uitsluitend beschrijvend.

## API- en opslagimpact

- Voeg stabiele loopinventaris toe aan de profielrepresentatie zonder de bestaande
  `loops`-telling voor oude clients/profielen stilzwijgend te herinterpreteren.
- Voeg expliciete aanvoer- en retourrollen met `loop`-scope toe aan signaalreferenties,
  catalogus, mappings en OpenAPI. Valideer dat een loop-scope naar een lus in de
  actieve profielversie verwijst.
- Lever een begrensd hydraulisch vergelijkingsresultaat per ketel-, verdeler- en
  luspaar met periode, statistiek, eenheid, sampleaantal, dekking, kwaliteitsstatus,
  uitsluitingen en ontbrekende signalen. Behoud onbekend als `null`/status, nooit 0.
- De bestaande meldingen en analyses blijven de bron voor beschikbaarheid en
  bewijsbeperkingen. De nieuwe response bevat geen aanbeveling of tweede parallelle
  diagnostische status.
- Werk `api/openapi.json` en gegenereerde frontend-types bij zodra de API wordt
  geïmplementeerd.

## Scherm- en ontwerpimpact

Breid de hydraulische analyse uit met een circuitvergelijking die de ketel, iedere
gekoppelde mengverdeler en iedere expliciet gemeten lus als afzonderlijke rijen of
kaarten toont. Toon per paar de aanvoer, retour, ΔT, tijdvak, meetdekking en
beperkingen. Gebruik Nederlandse teksten en een expliciete lege staat wanneer
verdeler- of lusmetingen ontbreken. Een ontbrekende lusidentiteit of één ontbrekende
temperatuursensor mag nooit een berekende lus-ΔT tonen.

Het ontwerp volgt de bestaande hydraulische bevinding en installatieprofielkaart in
design v3. Voeg geen groene/rode doelkleuren, ranglijst van lussen, totaalscore of
call-to-action voor een instellingenwijziging toe. Een uitleg maakt expliciet dat
metingen van verschillende circuits niet onderling uitwisselbaar zijn en dat de
weergave geen universele streefwaarde veronderstelt.

## Acceptatie- en scenariotests

1. Een gemeten ketelpaar en gemeten verdelerpaar verschijnen afzonderlijk; hun
   aanvoer, retour en ΔT zijn nooit aan het verkeerde circuit gekoppeld.
2. Bij een mengverdeler zonder lokaal paar blijft verdeler-ΔT onbekend, ook als het
   ketelpaar compleet is.
3. Een verdelerpaar zonder lus-sensors geeft geen lus-ΔT, ook niet wanneer het
   profiel alleen het aantal lussen kent.
4. Met twee expliciet geïdentificeerde lussen toont een bruikbaar paar per lus alleen
   de eigen samples; ontbrekende data van de ene lus worden niet van de andere
   overgenomen.
5. Een circuitdebietmeting zonder lokaal temperatuurpaar vult ΔT niet in.
6. Een ontbrekende, verouderde, niet-uitgelijnde of door een bijzondere periode
   uitgesloten meting verlaagt de dekking/beperkt de uitkomst volgens bestaande
   kwaliteitsregels; onbekende tijd wordt niet als nul meegerekend.
7. Tapwater, opstart en naloop verschijnen niet als stabiele CV-ΔT-samples.
8. Een aanvoer-retourvolgorde die niet fysiek aannemelijk is, wordt zichtbaar als
   kwaliteitsbeperking; de software neemt geen absolute waarde.
9. Een vergelijking genereert geen algemene retour-, pomp-, mengklep- of
   lusdebietaanbeveling en doet geen energiebesparingsclaim.
10. API-authenticatie blijft gelden en er worden geen HA-bedieningsservices
    aangeroepen.

## Implementatievolgorde

1. Ontwerp de circuitvergelijking en lege/beperkte toestanden in design v3.
2. Voeg profielidentiteit per lus, loop-scoped temperatuurrollen en mappingvalidatie
   toe met migratie-/compatibiliteitstests.
3. Implementeer de kwaliteitsbewuste paired-ΔT-analyse en API-contract boven op de
   bestaande hydraulische beschikbaarheid.
4. Implementeer het circuitvergelijkingsscherm tegen het goedgekeurde ontwerp en de
   API; valideer scenario's en toegankelijkheid.

Vervolgissues: #179 (design), #180 (profiel en lus-signaalkoppelingen), #181
(paired-ΔT-analyse en API), #182 (frontend). #180 hangt af van #179; #181 van
#180; #182 van #179 en #181.
