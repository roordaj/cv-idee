# Gasverbruik, vergelijkbare perioden en weerscontext (FR-31)

## Doel en grenzen

De verbruiksanalyse laat de gebruiker het ruwe gemeten gasverbruik en de
vergelijking met passende perioden beoordelen. Zij maakt zichtbaar wat de meter
precies meet, hoe tellerresets en datagaten zijn behandeld en welke verschillen in
weer, setpoint, verwarmingsduur of gebruik de vergelijking beperken.

Een cumulatieve gasmeter kan ook koken en tapwater omvatten. Zonder een aparte
meter of expliciete, gevalideerde gebruikssplitsing mag het totale gasverbruik niet
als ketelgas, ruimteverwarming, rendement of besparing worden gepresenteerd. Een
weersvergelijking is geen bewijs van oorzaak. De app stuurt geen ketel of
thermostaat aan.

De analyse toont ruwe meterwaarden naast een weers-/gebruiksvergelijking met alle
aannames. De eerste vergelijkingsvorm selecteert alleen waargenomen perioden die
binnen bestaande vergelijkbaarheidsgrenzen vallen; er wordt geen onbewezen
correctiefactor toegepast. Als zulke perioden ontbreken, is de gecorrigeerde/
vergelijkbare uitkomst niet beschikbaar en worden de ruwe waarden met de reden
getoond.

## Meter, eenheden en tellerresets

Elke verbruikswaarde noemt de bron, scope en eenheid:

- **Meter-scope:** `boiler_only`, `whole_house` of `unknown`, handmatig expliciet
  vastgelegd. Een HA-entiteitsnaam of een patroon in de waarden bepaalt de scope
  niet automatisch.
- **Gasvolume:** m³, direct uit een gekoppelde cumulatieve meter. Toon begin- en
  eindstand, verbruikt verschil, meetperiode, dekking en bronstatus.
- **Brandstofenergie:** alleen als een gevalideerde omzetting van meter-eenheid
  naar energie expliciet beschikbaar is. Een m³-waarde wordt niet met een
  aangenomen calorische waarde naar kWh omgerekend.
- **Kosten:** alleen als de gebruiker een gasprijs heeft ingesteld die aantoonbaar
  voor de betreffende verbruiksperiode geldt. Toon prijs, eenheid, toepasselijke
  instellingenversie en berekeningsbasis. Zonder passende prijs geen euro's.

Een dalende tellerstand start een nieuw tellersegment. Bereken nooit negatief
verbruik en tel geen onbekende overgang over een reset alsof die nul of volledig
gemeten was. Verbruik binnen elk betrouwbaar segment blijft zichtbaar; de reset en
het onbekende tusseninterval verlagen de dekking en beperken periodevergelijking.
Dubbele waarnemingen en reconnects leveren geen kunstmatige consumptie op.

## Ruwe en vergelijkbare uitkomst

1. **Ruw verbruik:** toon het gemeten totaal per gekozen dag/week/vergelijkings-
   periode, begin-/eindtellerstand en m³. Vermeld expliciet wanneer de meter ook
   koken/tapwater of onbekende toepassingen omvat. Ontbrekende tellerintervallen
   blijven onbekend.
2. **Periodekeuze:** bied een ruwe trend en een vergelijking met eerder
   waargenomen perioden. Selecteer referentieperioden met dezelfde duur en een
   meetbasis die binnen de bestaande buitentemperatuur- en setpointmarges valt.
   Gebruik beschikbare CV-bedrijfsduur, warmtevraag en zonegebruik als context;
   ontbrekende context maakt de overeenkomst beperkt, niet gelijk.
3. **Geen extrapolatie buiten waarnemingen:** rapporteer alleen waarden in de
   gemeten periode of in een expliciet geselecteerde, vergelijkbare periode.
   Corrigeer geen verbruik naar hypothetisch weer buiten het waargenomen bereik en
   vul een ontbrekende dag niet met een gemiddelde.
4. **Contextverschillen:** toon referentie en observatie naast elkaar met weer,
   binnen-setpoint, CV-bedrijfsduur, zone-/gebruikcontext, meter-scope, teller-
   dekking, resets, profiel-/mappingversie en bijzondere perioden. Een gewijzigd
   gebruik zoals koken of tapwater is alleen vergelijkbaar als het expliciet
   bekend en voldoende gelijk is; anders vermeldt de UI dat dit onbekend blijft.
5. **Weerscorrectie:** zolang geen gevalideerde correctiemethode en expliciete
   configuratie beschikbaar zijn, betekent de vergelijkbare uitkomst een selectie
   van werkelijk waargenomen, vergelijkbare perioden; noem dit geen voorspeld of
   genormaliseerd gasvolume. Een vervolgspike bepaalt of een aanvullende
   correctie verantwoord is. Die correctie moet ruwe waarden behouden, de
   referentie-/buitentemperatuur en aannames tonen, binnen de gemeten context
   blijven en bij onvoldoende bewijs `unknown` opleveren.
6. **Geen toeschrijving:** een verbruiksverschil wordt niet aan een specifieke
   parameter, ketelinstelling, gebruiker of weersverandering toegeschreven zonder
   vergelijkbare meetbasis en een afzonderlijk onderbouwde methode.

Ruwe en vergelijkbare waarden gebruiken dezelfde periodegrenzen waar dat kan.
Als door selectie minder dagen of dekking overblijft, toont de API beide
meetbasissen expliciet; het scherm suggereert niet dat ongelijke perioden direct
vergelijkbaar zijn.

## Rendement en euro's

- Een verschil in m³ of een gasprijs levert op zichzelf geen ketelrendement op.
- Een rendementsoordeel vereist voldoende betrouwbare brandstofenergie én
  geleverde warmte over dezelfde geldige perioden. Verbrandingswarmte,
  calorische omzetting, meterkwaliteit en meetonzekerheid moeten gevalideerd en
  gedocumenteerd zijn. Als één voorwaarde ontbreekt, toon `niet beschikbaar` of
  een expliciet benoemde verbruiksindicator/geschatte verhouding; noem die geen
  gemeten rendement.
- Modulatiepercentage wordt niet naar vermogen omgezet.
- Een eurobedrag is `gasvolume × ingestelde toepasselijke prijs` en krijgt die
  basis direct erbij. Zonder prijs of zonder bekende toepasselijke prijsperiode
  blijft de euro-uitkomst onbekend.

## Bijzondere perioden en beschikbaarheid

Bijzondere perioden worden volgens hun bestaande instellingen behandeld. Perioden
met `exclude_from_comparisons` blijven zichtbaar maar worden niet in een
vergelijkbare referentie gebruikt. Een uitsluiting van vergelijkingen verandert
de ruwe meterstand of ruwe consumptie niet. Opstookprotocol, onderhoud, vakantie
en bijzonder gebruik worden als context getoond.

De verbruiksanalyse is:

- **Niet beschikbaar** zonder gekoppelde, bruikbare cumulatieve gasmeter.
- **Beperkt** bij resetovergang, stale/ongeldige waarnemingen, onvoldoende
  dekking, onbekende meter-scope, niet-vergelijkbaar weer/setpoint/gebruikscontext
  of uitgesloten perioden.
- **Beschikbaar** voor een ruwe meteruitkomst zodra de bestaande
  kwaliteitscriteria dit toelaten. Een compleet ruwe resultaat kan beschikbaar
  zijn terwijl weers-/gebruiksvergelijking of rendement niet beschikbaar blijft.

Beschikbaarheid van ruwe consumptie is geen bewijs dat het verbruik van de ketel
komt. De UI houdt de statussen voor gasverbruik, vergelijking, rendement en kosten
afzonderlijk.

## API-, opslag- en schermimpact

- Leg meter-scope expliciet vast bij de signaalkoppeling/installatie: alleen
  `boiler_only`, `whole_house` of `unknown`; bestaande mappings blijven `unknown`
  totdat de gebruiker ze bevestigt.
- Lever ruwe countersegmenten/consumptie met begin/eind, periode, eenheid, dekking,
  reset-/datagat-events en meter-scope. Voorkom dat een resetsegment over de
  onmeetbare grens als volledig gemeten wordt weergegeven.
- Lever een vergelijkingsobject met referentie- en observatieperiode, gekozen
  meetbasis, ruwe waarden, contextverschillen, vergelijkbaarheid, uitsluitingen
  en ontbrekende aannames. Geavanceerde gecorrigeerde output blijft optioneel en
  vereist het besluit uit de normalisatiespike.
- Rendement, euro's en weersvergelijkbaarheid krijgen afzonderlijke expliciete
  beschikbaarheidsvelden en reden-codes. Geen `0` als onbekend.
- Gebruik de bestaande prijsinstelling, maar leg effectieve prijs-/configuratie-
  versies per rapport-/evaluatieperiode vast om prijswijzigingen niet met terugwerkende
  kracht toe te passen.
- Werk OpenAPI en gegenereerde frontend-types bij. Alle API-mutaties zijn
  geauthenticeerd; geen HA-bedieningsservice of extern MQTT-command topic.

Het scherm **Verbruik** toont bron en meter-scope, ruwe meterstand en gebruik,
reset-/datakwaliteitsmeldingen, ruwe trend en geselecteerde vergelijkbare perioden.
Toon daarnaast afzonderlijk of rendement en kosten beschikbaar zijn. Een grafiek
maakt resetten en ontbrekende intervallen zichtbaar en verbindt een gekalibreerde
of geselecteerde vergelijking met haar aannames. Geen besparingsbadge, groen
rendementsoordeel of eurobedrag verschijnt zonder geldige basis.

## Acceptatie- en scenariotests

1. Zonder gasmeter blijven cyclusanalyses beschikbaar en is de verbruiksanalyse
   niet beschikbaar met ontbrekende bron genoemd (FR-04).
2. Een geldige stijgende cumulatieve meter toont exact het ruwe m³-verschil en
   tijdvak.
3. Een meterreset levert geen negatief verbruik; de onbekende resetovergang verlaagt
   dekking en wordt zichtbaar (FR-08).
4. Een reconnect of dubbele melding levert geen extra verbruik of kunstmatige
   tellerstart.
5. Een huishoudmeter kan gas voor koken/tapwater omvatten; UI en API noemen de
   meter-scope en schrijven het totaal niet toe aan ruimteverwarming.
6. Ontbrekende/weinig betrouwbare buitentemperatuur, setpoint, bedrijfsduur of
   gebruikscontext geeft geen vergelijkbare/gecorrigeerde uitkomst zonder expliciete
   reden.
7. Perioden met vergelijkbaar weer maar ander setpoint of zonegebruik worden niet
   stilzwijgend als gelijke gebruiksperioden vergeleken.
8. Uitgesloten bijzondere perioden beïnvloeden de vergelijking niet, maar blijven
   zichtbaar; ruwe consumptie blijft intact.
9. Geen calorische omzetting of betrouwbare warmtemeter geeft geen gemeten
   rendement; modulatie wordt niet als kW gebruikt.
10. Geen toepasselijke gasprijs geeft geen euro-uitkomst. Een prijswijziging tijdens
    een periode gebruikt de juiste versies of maakt de kosten onbekend.
11. Een geselecteerde vergelijking gebruikt alleen waargenomen dagen en benoemt
    eventueel ongelijke meetbasis; er wordt niet buiten het gemeten weerbereik
    geëxtrapoleerd.
12. Alle gegevensroutes zijn geauthenticeerd en er worden geen HA-bedienings-
    services aangeroepen.

## Implementatievolgorde

1. Voer een spike uit naar een verdedigbare weersnormalisatie versus selectie van
   gematchte perioden, met speciale aandacht voor huishoudgas inclusief koken en
   tapwater. Leg keuze en beperkingen vast voordat een gecorrigeerde waarde wordt
   geïmplementeerd.
2. Ontwerp verbruiksscherm, meter-scope en reset-/onbekende toestanden in design v3.
3. Voeg meter-scope, ruwe segmentuitkomsten, prijs-/configuratieherkomst en
   vergelijkings-API toe.
4. Implementeer de gekozen selectie/correctiemethode met scenario's, dekking,
   rendement-/eurogrenzen en OpenAPI.
5. Implementeer UI tegen het goedgekeurde ontwerp en contract; valideer dat alle
   labels en conclusies overeenkomen met API-waarden.

Vervolgissues: #189 (normalisatiemethode-spike), #190 (design), #191 (meter-scope
en ruwe API), #192 (selectie/correctie en vergelijking), #193 (frontend). #190
hangt af van #189; #192 van #189 en #191; #193 van #190 en #192.
