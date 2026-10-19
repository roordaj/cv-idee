# Brongebonden statuscode-mapping

Issue #123 · FR-01, FR-09, FR-41

## Waarom expliciet

De oude ontwerpvoorbeelden `1=CV, 2=tapwater` zijn geen universele Calenta Ace-codes.
De echte AM012-bron uit [de inventarisatie](signalen-calenta.md) gebruikt 3 voor
CV-bedrijf en 4 voor warmwaterbedrijf. De gatewayomschrijvingen en officiële
handleiding ondersteunen die betekenissen; de lokale decoder is nog niet
onafhankelijk gevalideerd. Er wordt geen vlamstatus uit deze codes afgeleid.

## Configureren

Kies onder Signalen of tijdens de eerste start het signaal CV-/tapwatermodus en de
juiste Home Assistant-entiteit. Vul de tabel **Statuscodes voor deze bron** in,
één code per regel, met een van deze betekenissen:

```
0 = stand-by
1 = onbekend
2 = onbekend
3 = cv
4 = tapwater
5 = onbekend
6 = naloop
8 = onbekend
```

Dit is een voorbeeld voor de geïnventariseerde AM012-bron, geen automatisch
toegepast profiel. Leg bij **Herkomst en betekenis van statuscodes** vast op welke
bron, documentversie en waarnemingen de tabel steunt, inclusief onzekerheden.
Lege/niet gekoppelde codes blijven onbekend. Code 8 betekent gecontroleerde stop;
geen storing aannemen. Codes 9/10 worden alleen als storing/blokkering ingevoerd
wanneer de betekenis voor de gekozen bron expliciet is bevestigd. De recorder
bevat die codes niet. Voor andere bronnen geldt een eigen tabel.

De API gebruikt het bestaande `PUT /api/signals/{signal_id}` met `value_map`
(bijvoorbeeld `{"3":"ch","4":"dhw"}`) en verplichte `meaning` bij een ingevulde
modustabel. Canonieke waarden zijn `ch`, `dhw`, `standby`, `afterrun`,
`fault_blocking`, `unknown`. Een tabel zonder bronbeschrijving of met andere
betekenissen wordt geweigerd. `mapping_version` identificeert de opgeslagen versie.

Bij een andere entiteit worden de oude tabel en betekenis niet overgenomen.
Koppelen bewaart een nieuwe datatijdversie; de eerdere tabel blijft bij haar oude
entiteit en geldigheidsperiode. Ingang vanaf historische datum kan expliciet via
`valid_from`; de ingangsdatum mag niet vóór de huidige koppeling liggen of in de
toekomst. Historische data buiten een geldige mapping wordt niet achteraf ingevuld.

## Verwerking en historie

Live en import slaan ruwe waarden ongewijzigd op. De leesadapter past de tabel van
de geldige bronversie toe en geeft een getypeerde bedrijfsmodus door aan dezelfde
pure pipeline. Een gekoppelde, onbekende/ongevalideerde/ontbrekende modus valt niet
terug op vlam- of vraaginferentie. Alleen wanneer geen modustijdlijn gekoppeld is,
blijft de bestaande beperkte inferentie beschikbaar. Een apparaatmodus is geen
bewijs van vlamstarts; zonder vlamsignaal ontstaan geen branderperiodes.

`PipelineConfig.mode_mapping` is standaard leeg. Synthetische scenario's behouden
hun expliciet opgegeven eigen tabel. Configuratiehashes, runstatistieken en nieuwe
adviessnapshots bewaren de bronversies, tabellen, geldigheid en herkomst. Een
expliciete pipelinecodetabel wordt eveneens vastgelegd. Bestaande snapshots blijven
ongewijzigd; ontbrekende oude broninformatie wordt niet verzonnen.

De regressies replayen de geanonimiseerde 48-uursopname en controleren identieke
modi bij historie/live-herberekening, nul verzonnen branderperiodes, onbekende
transities, bronwissel, versiegrenzen en herkomstvalidatie.
