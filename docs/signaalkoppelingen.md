# Signaalkoppelingen en beschikbaarheid

De catalogus in `cvidee.signals.catalog` bevat alle 18 rollen uit het analysecontract.
Ketelaanvoer, ketelretour en verdeleraanvoer zijn afzonderlijke rollen. Ruimte-, zone-
en verdelerrollen gebruiken sleutels uit het installatieprofiel. Debiet en pompstatus
kunnen ook per circuit worden gekoppeld. De catalogus wordt bij opstarten met de
database gesynchroniseerd; bestaande koppelingen en waarnemingen blijven behouden.

## Koppelen

`GET /api/signals` toont gekoppelde en ongekoppelde rollen. Met
`PUT /api/signals/{signal_id}` wordt een HA-entiteit gekoppeld; `entity_id: null`
ontkoppelt. De app leest HA-toestanden om de entiteit en eenheid te controleren.
Onbereikbare HA geeft 502, niet-ingestelde HA geeft 503. Ontkoppelen kan zonder HA.

Eenheden moeten overeenkomen met de catalogus. Alleen schrijfwijzen zoals `m3`/`m³`
en `C`/`°C` zijn uitwisselbaar; de app voert geen eenheidsconversie uit. Locatie,
betekenis, herkomst, maximale leeftijd, verwachte resolutie en de keuze voor regelmatige
updates worden met de koppeling opgeslagen. `value_map` kan expliciete broncodes
naar canonieke waarden vertalen; modus-codes worden niet door deze catalogus ingevuld.

Elke wijziging sluit de oude versie en maakt een nieuwe versie. `valid_from` is
optioneel en gebruikt standaard het moment van opslaan; een ingangsdatum in de toekomst
of vóór de huidige versie wordt geweigerd. Een eerste koppeling kan een eerdere datum
krijgen om al opgeslagen historie te analyseren. Het actuele HA-peilmoment wordt
opgeslagen als peiling, zodat koppelen geen kunstmatige branderstart maakt.
Ingest vernieuwt de gekoppelde entiteiten en de runner krijgt een herberekening vanaf
de ingangsdatum. Ontkoppelen beëindigt de geldigheid van het signaal in de pipeline.

## Dekking, veroudering en resolutie

`GET /api/analyses` beoordeelt de afgelopen 24 uur met de pure beschikbaarheidsfunctie
uit ADR-004. De ingestelde minimale dekking en gewenste vlamresolutie komen uit de
instellingen; zonder opgeslagen instellingen gelden de bestaande schemadefaults.

De werkelijke resolutie is de mediaan van positieve intervallen tussen unieke
rapportagetijden binnen het venster en de huidige koppeling. Intervallen over een
datagat tellen niet mee. Een opgegeven verwachte resolutie vervangt geen waarnemingen:
zonder voldoende rapportages blijft de werkelijke resolutie onbekend. Dezelfde
kwaliteitsfunctie wordt door de bevindingen-runner gebruikt, zodat regels ook hun
eigen resolutiegrenzen kunnen toepassen.

Leeftijd maakt een signaal alleen verouderd als het regelmatige updates hoort te geven.
Een verbindingsgat of expliciet onbekende waarde blijft onbekend. Zonder gasmeter
kunnen cycli beschikbaar zijn; verbruik meldt dan ontbrekende gasgegevens. Rendement
vereist gas én een warmtemeter.

## Voorlopige defaults

De maximale leeftijden en heartbeat-keuzes zijn voorlopige configuratiedefaults.
Voor de CAN-rollen staat regelmatige rapportage standaard uit. De inventarisatie in
issue #5 moet de werkelijke rapportage en modus-codes vaststellen. Deze defaults
zijn geen waarnemingen en worden niet als bewijs voor beschikbaarheid gebruikt.
