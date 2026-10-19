# Normaalgedrag en vergelijkbare referentieperioden (FR-20, FR-35)

## Doel en grenzen

De analyse vergelijkt huidig installatiegedrag met een uitlegbare referentie van
eerder waargenomen, voldoende vergelijkbaar gedrag. Zij benoemt de referentieperiode
en relevante contextverschillen, zodat weer, kamersetpoints, zonegebruik, een
installatiewijziging of een gegevensgat niet als een onverklaarde storing verschijnt.

Het model beschrijft metingen; het stelt geen oorzaak vast. Het model is geen
black-box thermostaat, maakt geen automatische instellingen en stuurt geen ketel,
pomp, thermostaat of zoneklep aan. Bestaande detectieregels en hun configureerbare
criteria blijven leidend voor bevindingen. Een modelafwijking zonder gevalideerde
regelgrens is een beschrijvende vergelijking en geen alarm.

## Begrippen en modelidentiteit

- **Referentieperiode:** de verzameling eerdere, geldige meetvensters die als
  representatief zijn toegelaten voor een specifiek kengetal en een expliciete
  bedrijfscontext.
- **Observatievenster:** het recente venster dat met de passende referentie wordt
  vergeleken. De analyse toont begin/einde, tijdsbasis en gegevensdekking van beide.
- **Context:** alleen reeds bekende meet- en profielgegevens die voor het
  kengetal relevant zijn, waaronder buitentemperatuur, kamersetpoint, actieve
  zones/warmtevraag, bedrijfsmodus, circuit, profielversie, signaalmapping en
  bijzondere perioden.
- **Modelversie:** een onveranderlijke geschiedenis van modelinstellingen,
  referentiegrenzen en toegelaten observaties. Een nieuwe profiel- of
  signaalmappingversie wordt als context getoond en niet onzichtbaar met een
  incompatibele referentie samengevoegd.

Een model bestaat per installatie en ondersteund kengetal. De referentie bewaart
geen kopie van ruwe signalen: zij verwijst naar afgeleide kengetallen, hun periode,
meetbasis, dekking, gebruikte context en modelversie. De onderliggende historische
waarnemingen en analyse-uitkomsten blijven de bron. Het model gebruikt alleen
bestaande kengetallen en expliciete waarden; onbekend wordt niet als nul of als een
afgeleid gebruikersdoel ingevuld.

## Referentie opbouwen en vergelijken

1. **Geschikte waarnemingen.** Alleen geslaagde analysevensters die voldoen aan de
   bestaande kwaliteits-, dekking- en minimumwaarnemingscriteria voor het betrokken
   kengetal kunnen de referentie voeden. De meetbasis en eenheid blijven gelijk.
2. **Context matchen.** Per kengetal worden vensters alleen samengenomen als hun
   relevante context binnen de bestaande, expliciete vergelijkbaarheidsinstellingen
   valt. Gebruik bestaande grenzen voor weer en setpoints. Neem actieve-zone- en
   warmtevraagcontext mee wanneer die bron beschikbaar is. Ontbrekende context is
   onbekend en wordt niet als gelijk verondersteld.
3. **Niet vergelijkbaar blijft apart.** Als een observatievenster geen bruikbare
   vergelijkingsgroep heeft, toon welke context ontbreekt of verschilt. Vergelijk
   geen verschillende circuits, modi, meetresoluties of kengetaldefinities alsof
   die één populatie vormen.
4. **Referentiewaarde.** Toon per vergelijkingsgroep de bestaande metric over de
   referentie en het observatievenster met dekking en waarnemingsduur. Gebruik de
   bestaande metricdefinitie en rapportage-eenheid. Een gemiddelde, mediaan of
   bereik wordt alleen gebruikt wanneer de metric-/analysecontracten die aggregatie
   definiëren; leid geen nieuwe engineeringnorm af uit de verdeling.
5. **Afwijking.** Een verschil wordt als gemeten verschil met richting, omvang,
   tijdvak en relevante contextverschillen beschreven. Een bevinding ontstaat
   alleen wanneer een bestaande of afzonderlijk gevalideerde detectieregel haar
   eigen bewijs- en herhalingscriteria haalt. Modeltraining introduceert geen
   verborgen drempel.
6. **Geen oorzaak- of besparingsclaim.** Samenloop met weer, setpoint, zones,
   wijziging of profielversie bewijst geen oorzaak, verbetering, verslechtering,
   energieverbruik of euro-effect.

## Leren, pauzeren en nieuwe referentie

Het model heeft voor iedere metric een zichtbare status: `insufficient_data`,
`learning`, `active` of `paused`. Wanneer bestaande minimumcriteria nog niet gehaald
zijn, meldt de UI hoeveel geldige observatie/context nog ontbreekt volgens die
criteria; er verschijnt geen voorspelde waarde of afwijkingsbevinding.

Bij `paused` worden nieuwe vensters niet aan de referentie toegevoegd. De laatst
opgebouwde referentie blijft beschikbaar met de expliciete melding dat zij niet
actueel wordt bijgewerkt. Als haar context niet vergelijkbaar is met de observatie,
wordt geen individuele conclusie getrokken. Pauzeren vereist een expliciete
gebruikersactie met reden en tijdstip; het systeem pauzeert niet stilzwijgend omdat
een metric tijdelijk afwijkt.

De gebruiker kan na een grote wijziging (bijvoorbeeld renovatie, nieuwe ketel,
nieuwe regeling of wezenlijk andere circuitindeling) een nieuwe referentie starten
met een gekozen ingangsdatum. De oude referentie blijft historisch beschikbaar. De
nieuwe versie begint leeg en doorloopt opnieuw `learning`; de UI maakt duidelijk
dat de app in deze fase nog geen afwijkingen aan de oude installatie toeschrijft.
Een profielwijziging of wijzigingslog-item is context, maar start op zichzelf geen
nieuwe baseline zolang de gebruiker dit niet bevestigt. Er wordt geen
settle-in-periode of aantal dagen verzonnen; eventuele ingestelde perioden en
minimumcriteria komen uit bestaande beleidsinstellingen of een afzonderlijk
gevalideerd besluit.

## Bijzondere perioden en datakwaliteit

Een bijzondere periode met `exclude_from_baseline` blijft in grafieken, historie en
rapporten zichtbaar, maar draagt niet bij aan modelopbouw. De overige uitsluitvlaggen
blijven onafhankelijk gelden voor hun huidige doeleinden. Een datagat, verouderde
meting, onbekende modus, misuitlijning of onvoldoende dekking wordt niet als herstel,
normaal gedrag of afwijking geïnterpreteerd.

Als een uitsluitperiode een venster slechts gedeeltelijk overlapt, volgen de
gebruikte samples de bestaande interval- en uitsluitlogica. De UI toont welke periode
is uitgesloten en hoeveel geldige meetbasis resteert. Vergelijkingsvensters zonder
dezelfde kengetaldefinitie, meeteenheid of geldige meetbasis vallen uiteen in
afzonderlijke referenties.

## API-, opslag- en schermimpact

- Voeg versiegebonden modelmetadata en status toe zonder afgeleide waarden of ruwe
  geschiedenis te dupliceren. Bewaar aanmaak-/bijwerktijd, actieve modelversie,
  status, gebruikersreden/tijdstip voor pauze of reset, periodegrenzen en context-/
  configuratieversie waarmee het model is opgebouwd.
- Sla herleidbare metricreferenties per contextgroep op, met observatievenster,
  eenheid, dekking, relevante contextvelden en modelversie. Herbouw moet idempotent
  zijn; dezelfde analyse mag geen dubbele referentieobservatie maken.
- Respecteer `exclude_from_baseline` uit bijzondere perioden en de bestaande
  profiel-/signaalmappingversies.
- De API levert een begrensde lijst metricmodellen en vergelijkingen met status,
  referentie- en observatieperiode, feitelijke metricwaarden, dekking, meetbasis,
  contextverschillen en reden-codes. Onbekende velden zijn `null`/expliciet onbekend.
- Pauzeren, hervatten en een nieuwe referentie starten wijzigen alleen eigen
  analysemetadata; routes roepen geen HA-bedieningsservice aan.
- Genereer OpenAPI en frontend-types bij contractwijziging. Het model mag niet
  afhankelijk zijn van een externe LLM of niet-herleidbare classificatie.

Het scherm **Normaalgedrag** toont per metric de status, de referentie en observatie
naast elkaar, relevante overeenkomsten/verschillen, dekking en uitgesloten perioden.
Het toont een zichtbare tijdlijn van pauzes en referentiewissels. De gebruiker kan
pauzeren, hervatten of een nieuwe referentie vanaf een datum starten met een reden.
Lege, lerende, gepauzeerde, beperkte en verouderde toestanden leggen concreet uit
wat nog ontbreekt. De UI gebruikt de bestaande Nederlandstalige oordeel- en
zekerheidscategorieën; zij toont geen zekerheid als percentage en geen generieke
groen/rood-balk of adviestekst voor een ketelinstelling.

## Acceptatie- en scenariotests

1. Een vergelijking toont altijd de referentie- en observatieperiode, tijdsbasis,
   metricdefinitie, eenheid en dekking (FR-20).
2. Een buitentemperatuurverschil buiten de bestaande vergelijkbaarheidsgrens wordt
   benoemd en maakt de vensters niet stilzwijgend één referentiegroep.
3. Een gewijzigd kamersetpoint of actief-zonegebruik wordt getoond als
   contextverschil; ontbrekende context wordt niet als gelijk aangenomen.
4. Onvoldoende bruikbare historische vensters geeft status `insufficient_data` of
   `learning`, zonder voorspelde metric of afwijkingsbevinding.
5. Vensters binnen uitgesloten opstookprotocol/onderhoud dragen niet aan de
   referentie bij, maar blijven zichtbaar in historie en tijdlijn (FR-10).
6. Pauzeren stopt modelupdates, bewaart de laatst geldige referentie en toont
   pauzereden en -tijdstip; hervatten voegt daarna alleen nieuwe geschikte vensters
   toe.
7. Een nieuwe referentie na renovatie/nieuwe regeling start een lege modelversie;
   oude geschiedenis blijft opvraagbaar en wordt niet overschreven (FR-35).
8. Een herhaalde verwerking van dezelfde analysevensters maakt geen dubbele
   modelobservaties of snapshots.
9. Een grote metricverandering zonder een gevalideerde detectieregel toont een
   beschrijvend verschil, geen alarm, oorzaak of aanbeveling.
10. Een verandering die een bestaande regel activeert gebruikt diens bestaande
    herhalings-, dekking- en bewijscriteria en noemt de passende referentie/context.
11. Installatieprofiel-, circuit- of mappingwijzigingen worden herkenbaar als
    context/modelversie getoond; onverenigbare vensters worden niet samengevoegd.
12. Alle API-mutaties zijn geauthenticeerd en beperken zich tot normaalgedragmodel-
    metadata; geen HA-bedieningsservice of apparaat-topic wordt gebruikt.

## Implementatievolgorde

1. Ontwerp het scherm voor referentie, status, contextverschillen, leren/pauzeren en
   een nieuwe modelversie.
2. Voeg versiegebonden modelmetadata, idempotente metricobservaties en expliciete
   pauze-/resetacties toe.
3. Implementeer vergelijkbare referentie-selectie, afwijkingspresentatie en
   geauthenticeerde API-contracten die bestaande regelcriteria hergebruiken.
4. Implementeer UI, scenario's en toegankelijkheidsvalidatie tegen het goedgekeurde
   ontwerp en API.

Vervolgissues: #184 (design), #185 (model-lifecycle en opslag), #186
(vergelijkbare referenties en API), #187 (frontend). #185 hangt af van #184;
#186 van #185; #187 van #184 en #186.
