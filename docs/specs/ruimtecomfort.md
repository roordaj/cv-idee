# Ruimtecomfort, gebruikstijden en comfortanalyse (FR-05, FR-17)

## Doel en afbakening

Deze uitbreiding laat de gebruiker per ruimte vastleggen wanneer warmtecomfort is
gewenst en welk kamertemperatuurdoel dan geldt. De analyse vergelijkt gemeten
kamertemperatuur met de toepasselijke doel- en setpointgegevens en houdt comfort
afzonderlijk per ruimte bij. Een warme woonkamer maskeert geen koude slaapkamer.

De app registreert gebruikersdoelen en analyseert meetgegevens; zij stuurt de ketel,
thermostaat of verwarmingszones niet aan. Een comfortdoel is de gewenste
kamertemperatuur van de gebruiker, niet automatisch het actuele kamersetpoint uit
Home Assistant. Beide blijven apart zichtbaar. Ontbrekende doelen, setpoints of
metingen blijven onbekend en worden niet uit andere ruimten afgeleid.

De uitbreiding bouwt voort op het versiebeheerde installatieprofiel (#10),
signaalkoppelingen en kwaliteitsintervallen (#7/#11), en de bestaande bijzondere
perioden (#21). Voor/na-evaluatie gebruikt dezelfde per-ruimte comfortmeting en
bestaande configureerbare comfortgrens (#39); deze uitbreiding wijzigt de bestaande
evaluatie niet stilzwijgend.

## Configuratie per ruimte

Een kamerconfiguratie is gekoppeld aan de stabiele ruimtesleutel in een
installatieprofiel en bevat:

- een expliciete gebruiksstatus: comfort gewenst volgens schema, of geen
  comfortverwachting buiten de ingestelde gebruikstijden;
- één of meer weekdag-/tijdvakken met een door de gebruiker ingestelde
  comfortdoeltemperatuur;
- optionele nachtverlaging als afzonderlijk tijdvak en doeltemperatuur (deze wordt
  niet verondersteld wanneer niet ingevuld);
- de aan de ruimte gekoppelde kamertemperatuursensor en, indien beschikbaar, het
  feitelijke kamersetpoint via de bestaande signaalkoppeling;
- zichtbare geldigheid en herkomst van elk doel: handmatig ingesteld, overgenomen
  uit een toepasselijke bijzondere periode, of niet ingesteld.

Een gebruiker kan doelen per ruimte opslaan zonder een sensor te hebben. In dat geval
is de voorkeur opgeslagen, maar blijft de analyse van comfortbeschikbaarheid
“Niet beschikbaar” totdat bruikbare metingen en een bruikbaar referentiesetpoint of
doel aanwezig zijn. Kamers zonder verwarmingscircuit of comfortverwachting worden
niet stilzwijgend als verwarmde kamers geanalyseerd.

Weekdag en tijd volgen `Europe/Amsterdam`; opslag en analysegrenzen blijven UTC.
Tijdvakken zijn halfopen `[start, einde)`, mogen middernacht overschrijden en mogen
elkaar niet overlappen binnen dezelfde ruimte en weekdag. In een overgang naar/van
zomertijd wordt een lokaal tijdvak maar eenmaal toegepast; ontbrekende lokale tijden
worden overgeslagen en dubbel voorkomende tijden volgen de werkelijke UTC-volgorde.
De UI toont opgeslagen lokale tijden en valideert overlappende of lege tijdvakken.

De bestaande bijzondere perioden blijven de bron voor vakantie, onderhoud,
opstookprotocol en ander tijdelijk gebruik. Hun bestaande uitsluitvlaggen gelden
ook voor ruimtecomfort. Een periode die voor comfortanalyse is uitgesloten, telt niet
als comfortverlies, opwarmtijd of herstel. Een periode die niet uitgesloten is kan
een tijdelijk ruimtecomfortdoel bevatten; zonder zo'n override blijft het normale
weekschema gelden. De UI maakt zichtbaar welke periode/doel actief is.

Doelen en weekschema's horen bij de profielversie. Een wijziging maakt een nieuwe
profielversie; analyses en adviessnapshots behouden zo de doelen en tijden die
golden toen de metingen werden beoordeeld. Een wijziging met terugwerkende kracht
overschrijft geen eerdere profielversie of historisch oordeel.

## Analyse per ruimte

Alle waarden zijn gebaseerd op geldige, tijdsuitgelijnde intervallen voor de
betreffende ruimte. De analyse respecteert sensorstatus, resolutie, datagaten,
speciale perioden en dekking. Elke metric vermeldt periode, meetbasis, dekking en
ontbrekende signalen. Er worden geen nulwaarden ingevuld voor onbekende intervallen.

- **Opwarmtijd:** tijd vanaf het begin van een comfortdoel-tijdvak totdat de gemeten
  temperatuur de bestaande comfortgrens ten opzichte van het doel bereikt. De
  comfortgrens is de expliciet getoonde/configureerbare grens uit de huidige
  analyse-instellingen. Als temperatuur aan het begin ontbreekt, het doel gedurende
  de opwarming verandert, of de meetreeks wordt onderbroken, is de opwarmtijd
  onbekend/onvolledig, geen nul.
- **Afwijking van setpoint/doel:** actuele kamertemperatuur minus het geldige
  kamersetpoint en, apart, minus het ingestelde comfortdoel. Toon beschikbare
  afwijking en duur per richting. Vergelijk een gebruikersdoel niet alsof het een
  door de thermostaat gevraagde setpoint is.
- **Comfortverlies:** waargenomen tijd tijdens comforturen waarin de temperatuur
  verder onder het actuele doel/setpoint ligt dan de ingestelde comfortgrens. Toon
  dit per ruimte en per periode, plus dekking en de gebruikte doelbron.
- **Overshoot:** waargenomen temperatuur boven het actuele doel/setpoint tijdens
  comforturen, als duur en gemeten maximale afwijking per ruimte. Zonder expliciet
  ingestelde bovengrens is dit een metric/observatie, geen foutmelding of oordeel
  “te warm”.

Een wijziging naar een nieuw setpoint/doel start een nieuwe meetfase voor
opwarmtijd; zij mengt geen twee doelen in één metric. Vlamstatus, CV-/tapwatermodus,
warmtevraag en actuele setpoint blijven waar nodig als context zichtbaar. Tapwater,
onbekende modus, uitgeschakelde comforturen en uitgesloten perioden worden niet
gepresenteerd als ruimtecomfortverlies.

Een bevinding is altijd ruimtegebonden met eigen periode, metingen, datadekking en
onderbouwing. Een positieve afwijking in de ene ruimte wist of compenseert een
negatieve afwijking in een andere ruimte niet. Correlatie tussen aanvoer, zones,
weersomstandigheden of kamertemperatuur beschrijft samenloop en bewijst geen
oorzaak. Ernst en zekerheid volgen alleen bestaande, zichtbare, configureerbare
criteria; deze specificatie verzint geen universele ideale temperatuur of
opwarmduur.

## Beschikbaarheid en ontbrekende gegevens

- Geen ingestelde comforturen/doelen: toon dat de comfortverwachting niet is
  geconfigureerd; leid deze niet af uit een sensor of de woonkamer.
- Geen gemapte/bruikbare kamertemperatuur: toon de ruimte als niet beschikbaar en
  benoem de vereiste mapping/sensor.
- Geen bruikbaar kamersetpoint: metrics ten opzichte van het feitelijke setpoint
  zijn onbekend. Metrics ten opzichte van een ingesteld doel zijn alleen mogelijk
  wanneer dat doel voor het hele tijdvak expliciet en geldig is.
- Onvolledige dekking of een datagat: toon de waargenomen fractie en tijd; niet
  gemeten duur telt niet mee als comfort of comfortverlies.
- Bijzondere periode met uitsluiting: toon het uitgesloten interval en de reden.
  Bij een toepasselijk tijdelijk doel blijft dat doel zichtbaar, ook wanneer de
  periode voor bepaalde analyses is uitgesloten.
- Een wijziging van schema, doel, setpoint of sensor wordt als contextwijziging
  getoond en niet met de oude instelling samengevoegd.

De beschikbaarheidskaart vermeldt per ruimte of de analyse beschikbaar, beperkt of
niet beschikbaar is en waarom. Een totaalscore over kamers wordt niet berekend.

## API, opslag en UI-impact

- Breid het versiebeheerde installatieprofiel uit met configureerbare comfortdoelen
  en weekdag-/tijdvakken per stabiele ruimtesleutel. De datavorm moet doel en
  gebruiksstatus expliciet onderscheiden; een ontbrekend doel blijft onbekend.
- Hergebruik de bestaande signaalmapping per ruimte voor kamertemperatuur en
  kamersetpoint, en de bestaande bijzondere-perioden-API voor datumgebonden
  uitzonderingen. Voorkom dubbele opslag van sensor-ID's of tweede
  periode-implementaties.
- Lever ruimtegebonden metrics, dekking, doelbron en beperkingen via het analyse-/API
  contract. OpenAPI en frontend-types veranderen mee.
- Werk de kaart “Comfort per ruimte” uit in design v3: doel en schema, werkelijk
  setpoint, actuele/waargenomen temperatuur, comfortverlies, overshoot, dekking,
  ontbrekende mapping en speciale perioden. Bied instellen/bewerken per ruimte en
  een duidelijke lege/niet-beschikbare state.
- De frontend maakt geen comfortconclusies; zij presenteert de gevalideerde
  API-uitkomst en de doelbron.

## Acceptatie- en scenariotests

1. Twee ruimtes op hetzelfde circuit kunnen verschillende comforturen en doelen
   hebben; wijzigingen aan de ene ruimte veranderen de andere niet.
2. Een kamer boven setpoint en een andere onder setpoint leveren twee afzonderlijke
   metrics/bevindingen met eigen ruimte-ID, periode en onderbouwing.
3. Buiten ingestelde comforturen wordt temperatuurafwijking niet als
   comfortverlies aangemerkt. Een nachtverlaging is alleen actief wanneer expliciet
   ingesteld.
4. Een geldige doelverhoging binnen een gemeten tijdvak start een nieuwe
   opwarmmeting; datagaten of doelwijzigingen tijdens de meting geven onbekend of
   onvolledig, niet een verzonnen opwarmtijd.
5. Temperatuur boven doel toont overshootduur en maximum per ruimte. Zonder
   ingestelde bovengrens ontstaat geen “te warm”-bevinding.
6. Geen kamertemperatuursensor of geen geldig doel/setpoint levert beperkte of geen
   beschikbaarheid op, met de ontbrekende gegevens benoemd; nul comfortverlies
   wordt niet afgeleid.
7. Een uitgesloten vakantie-/bijzondere periode telt niet mee in comfortverlies of
   opwarmtijd. Een niet-uitgesloten periode gebruikt haar expliciete ruimteoverride
   of anders het normale weekschema.
8. Hetzelfde historische tijdvak met een latere profielwijziging behoudt het toen
   geldige schema en doel in de evaluatie-/adviessnapshot.
9. Een wijziging in het schema rond de DST-vooruit-/achteruitgang wordt op lokale
   weekdag en tijd toegepast zonder dubbele meetminuten; API-tijd blijft UTC.
10. Analyse en gebruikersinterface voeren geen HA-service uit en publiceren niet op
    apparaat- of MQTT-commandotopics.

## Implementatievolgorde

1. Ontwerp de comfortkaart, ruimteconfiguratie, lege/kwaliteitstoestanden en
   weergave van tijdelijke perioden in design v3.
2. Voeg versiebeheerde ruimtecomfortdoelen en wekelijkse tijdvakken toe aan profiel,
   validatie en API; hergebruik bestaande signaal- en periodemodellen.
3. Voeg zuivere, testbare analyse voor comforturen, opwarmtijd, afwijking,
   comfortverlies en overshoot toe, plus datakwaliteit en snapshots.
4. Integreer roommetrics en beschikbaarheid met runner, bevindingen, voor/na,
   rapportage en frontend; valideer alle scenariotests.

Vervolgissues: #159 (ontwerp), #160 (ruimtecomfortconfiguratie/API), #161 (analyse,
metrics en evaluatie), #162 (frontend). #160 hangt af van #159; #161 hangt af van
#160; #162 hangt af van #159, #160 en #161.
