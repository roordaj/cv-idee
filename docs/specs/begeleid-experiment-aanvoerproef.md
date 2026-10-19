# Begeleid experiment en proef met lagere aanvoer (FR-33, FR-34)

## Doel en grenzen

Een begeleid experiment legt één door de gebruiker uitgevoerde wijziging vast en
vergelijkt de situatie ervoor en erna. De app helpt de gebruiker een proef met een
lagere maximale CV-aanvoer te beoordelen wanneer comfortgegevens voor de relevante
ruimten en de bedrijfsomstandigheden dat toelaten.

De app blijft read-only ten opzichte van ketel en thermostaat. De gebruiker voert
instellingen zelf buiten de app uit en registreert daarna de wijziging. Er is geen
automatische instelling, bediening, setpoint-voorstel uit onbevestigde data,
besparingsclaim of garantie dat comfort behouden blijft. Een lagere aanvoer is geen
verbetering op zichzelf.

Deze uitbreiding bouwt voort op de wijzigingsregistratie en voor/na-evaluatie
(FR-29/30/32, #29 en #39), comfortdoelen en comfortmetingen per ruimte (FR-05/17,
#55) en aanbevelingsopvolging (#36). De berekening van de bestaande evaluatie blijft
leidend; een experiment introduceert geen tweede evaluatiemodel.

## Begrippen en gegevens

- **Experiment:** een gebruiker-gestuurde evaluatie met precies één bedoelde
  installatieparameterwijziging, één referentieperiode en één observatieperiode.
- **Referentieperiode:** het vergelijkbare tijdvak direct vóór de geregistreerde
  wijziging.
- **Observatieperiode:** het even lange tijdvak vanaf de wijziging. De ingestelde
  vergelijkingsduur en uitsluiting van bijzondere perioden uit de voor/na-evaluatie
  zijn leidend.
- **Proef lagere aanvoer:** een experiment waarvan de parameter de maximale
  CV-aanvoer is en de nieuwe waarde lager is dan de oude waarde.

Een experiment verwijst naar de bestaande wijzigingsregistratie. Het bewaart de
betrokken parameter, oude en nieuwe waarde, tijdstip, reden, optioneel gekoppeld
advies, periodegrenzen, aanmaak-/bijwerktijd en de laatst bekende evaluatie. Het
kopieert geen ruwe meetreeks en bewaart geen alternatieve waarden voor ketel of
thermostaat. De evaluatie verwijst naar de al berekende kengetallen,
vergelijkbaarheid, gegevensdekking, bewijsbeperkingen en het oordeel.

De bedoelde wijziging moet één parameter betreffen. Een tweede geregistreerde
wijziging die de perioden overlapt maakt individuele toeschrijving onmogelijk volgens
FR-32; het systeem toont het bestaande oordeel “Niet toe te schrijven” en beweert
niet dat het eerste experiment geïsoleerd is gebleven. De gebruiker kan een gepland
experiment beëindigen; beëindigen verwijdert de wijziging of historie niet.

## Levenscyclus en evaluatie

1. **Voorbereiden:** de gebruiker kiest één parameter, vult de oude en voorgenomen
   nieuwe waarde in en kiest het tijdstip waarop de wijziging buiten de app is
   uitgevoerd. De app controleert dat er geen tweede bedoelde parameterwijziging in
   hetzelfde experiment zit. Voor een aanvoerproef moet de nieuwe waarde lager zijn.
2. **Lopend:** vanaf het geregistreerde wijzigingstijdstip vergelijkt de app de
   observatieperiode met de direct voorafgaande referentieperiode. Tot de ingestelde
   observatieduur is bereikt, blijft de evaluatie lopend; reeds bekende
   vergelijkbaarheidsproblemen en ontbrekende gegevens zijn zichtbaar.
3. **Evalueren:** bij voldoende observatiegegevens gebruikt de app de bestaande
   voor/na-evaluatie en haar criteria voor dekking, weer, setpoints, andere
   wijzigingen, bijzondere perioden, cycli en comfort per ruimte. Een nog
   onvolledige of onvergelijkbare periode levert het bestaande oordeel
   “Onvoldoende bewijs” of “Niet toe te schrijven” op, niet een voorlopige
   verbetering.
4. **Afronden:** toon het bestaande oordeel en de indicatoren met hun meetbasis. Een
   combinatie van minder korte cycli en slechter comfort blijft een afweging en kan
   het reeds ingestelde terugdraaicriterium activeren. Een verandering van
   aanbevelingsstatus of uitkomst volgt de bestaande historie- en snapshotregels.

Bij opnieuw berekenen wordt de actuele evaluatie ververst zonder dubbele historie
wanneer oordeel en status niet veranderen. Het vastgelegde wijzigingstijdstip en de
oorspronkelijke waarden blijven behouden.

## Voorwaarden voor voorstel van een lagere-aanvoerproef

Een voorstel is alleen beschikbaar wanneer de app voldoende gegevens heeft om zowel
het verwarmingsgedrag als het comfortrisico te volgen:

- de maximale CV-aanvoer is als wijzigbare, bekende installatieparameter
  geregistreerd; de huidige waarde is bekend;
- voor iedere relevante ruimte op de betrokken circuits zijn ruimte, sensor,
  kamersetpoint/comfortdoel en comfortgrens bekend en aan geldige signalen gekoppeld;
  een meting in alleen de woonkamer voldoet niet wanneer andere relevante ruimten
  worden verwarmd;
- temperatuur- en setpointmetingen zijn bruikbaar en de dekking per ruimte is
  zichtbaar; ontbrekende kamers worden nooit als comfortabel verondersteld;
- de buitentemperatuur en CV-kengetallen hebben de dekking die de bestaande
  voor/na-evaluatie vereist, en de perioden zijn niet door een andere wijziging,
  afwijkende setpoints of uitgesloten bijzondere perioden onvergelijkbaar;
- er loopt geen ander experiment op dezelfde wijziging/parameter.

De bestaande configureerbare instellingen voor comfortmarge, toegestane
comfortverliesgrens, vergelijkingsduur, weervergelijkbaarheid en minimale dekking
zijn leidend. Geen parallelle of verborgen drempels toevoegen. Bij onvoldoende
voorwaarden toont de app welke gegevens ontbreken en biedt zij geen lager-aanvoer-
voorstel aan.

Het voorstel benoemt de bekende huidige waarde en vraagt de gebruiker één lagere
waarde zelf te kiezen en na uitvoering te registreren. De app verzint geen stapgrootte,
temperatuur, besparing in kWh/euro of gegarandeerd effect. Het voorstel bevat per
relevante ruimte de gemeten comfortreferentie en het bestaande, configureerbare
terugdraaicriterium. De gebruiker krijgt de waarschuwing dat de proef comfort kan
verslechteren en dat de app de instelling niet zelf uitvoert.

## Presentatie- en ontwerpbehoefte

Design v3 bevat al een voor/na-evaluatie, wijzigingshistorie, comfort per ruimte en
een verwijzing naar een proef met lagere aanvoer, maar geen scherm voor het
begeleiden of volgen van een experiment. Er is daarom een UI-ontwerp nodig vóór de
frontendimplementatie. Dat ontwerp specificeert:

- de ingang vanuit een wijziging, advies en voor/na-evaluatie;
- de invoer en bevestiging van precies één handmatig uitgevoerde wijziging;
- referentie- en observatieperiode, voortgang en status;
- indicatoren en vergelijkbaarheid, met ontbrekende/ontoereikende gegevens per
  ruimte zichtbaar;
- de gate voor een lagere-aanvoerproef en de expliciete reden wanneer die niet
  beschikbaar is;
- het afwegingsresultaat en een geactiveerd terugdraaicriterium;
- een permanente aanduiding dat de app alleen adviseert en de ketel/thermostaat niet
  aanstuurt.

Het scherm hergebruikt de termen en statussen uit ontwerp v3 en de bestaande
voor/na-pagina. Nieuwe Nederlandse microcopy en interacties worden in een aanvulling
op het ontwerp vastgelegd; deze specificatie schrijft geen nieuw visueel patroon
voor.

## Acceptatie- en scenariotests

1. Een experiment met één geregistreerde wijziging gebruikt de bestaande
   referentie-/observatieperioden en toont “Lopend” voordat de observatieduur is
   verstreken.
2. Na een volledige vergelijkbare periode toont het experiment dezelfde bestaande
   uitkomst en indicatoren als `GET /api/changes/{id}/evaluation`.
3. Een wijziging van pomp en aanvoer in overlappende perioden wordt “Niet toe te
   schrijven”; geen effect wordt aan één parameter toegeschreven.
4. Minder starts of korte cycli gecombineerd met overschreden comfortgrens in een
   ruimte wordt als afweging/ongunstig getoond, niet als verbetering; het bestaande
   terugdraaicriterium wordt gevolgd.
5. Ontbrekende kamersetpoint-, comfortdoel- of temperatuurdata voor een relevante
   ruimte blokkeert een voorstel voor lagere aanvoer en benoemt de ontbrekende
   gegevens. Geldige woonkamerdata compenseert geen ontbrekende data boven.
6. Alleen wanneer alle relevante ruimten en de overige bestaande
   vergelijkbaarheids-/dekkingsvoorwaarden voldoen, is een lager-aanvoerproef
   beschikbaar; haar criteria per ruimte komen uit de bestaande instellingen.
7. De app vraagt de gebruiker de lagere waarde zelf uit te voeren en te registreren;
   een experiment- of aanbevelingsroute roept geen HA-bedieningsservice aan.
8. Een extra wijziging, ongeldig tijdstip, speciale periode of onvoldoende dekking
   blijft zichtbaar als vergelijkbaarheids-/bewijsbeperking en levert geen verzonnen
   effect of waarde op.

## Implementatievolgorde

1. Maak scherm-/interactieontwerp voor de begeleide levenscyclus en de
   lagere-aanvoer-gate.
2. Voeg API/datarepresentatie voor experimenten toe boven op wijzigingen en de
   bestaande evaluatie; test de lifecycle, autorisatie en read-only grens.
3. Voeg de lagere-aanvoer-eligibility en uitlegbare ontbrekende voorwaarden toe,
   afhankelijk van de ruimtecomfortdoelen en bestaande voor/na-evaluatie.
4. Implementeer scherm en interacties tegen de vastgelegde API en het goedgekeurde
   ontwerp; valideer alle scenariotests en toetsenbordtoegankelijkheid.

Vervolgissues: #154 (ontwerp), #155 (experiment-API en lifecycle), #156
(lagere-aanvoer-gate), #157 (frontend). #156 hangt af van #55 en #155; #157 hangt
af van #154 en #155.
