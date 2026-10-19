# Dag- en weekrapporten (FR-40)

## Doel en afbakening

Een rapport geeft een controleerbaar overzicht van de cv-analyse over een gekozen kalenderdag of -week. Het brengt metingen, interpretaties en adviezen bij elkaar, zodat de gebruiker veranderingen en ontbrekende gegevens kan beoordelen. Het rapport adviseert alleen; het wijzigt geen ketel- of thermostaatinstellingen.

Rapportage is een presentatie van bestaande analyse- en logboekgegevens. Een rapportberekening introduceert geen nieuwe detectieregels, diagnoses, besparingsschattingen of betrouwbaarheidspercentages. De bestaande meldingendigest `dagbundel`/`weekrapport` blijft een bundeling van meldingen en is niet hetzelfde als het FR-40-rapport.

## Periode en reproduceerbaarheid

- De gebruiker kiest een dag of week. Standaard is de laatst volledig afgesloten lokale periode: gisteren of de vorige maandag–zondag.
- Kalendergrenzen volgen `Europe/Amsterdam`; week begint op maandag. Datums en tijden worden in nl-NL-notatie getoond. API-tijdstippen blijven UTC.
- Een rapport bevat de gekozen periode, generatie-tijdstip en gegevensdekking. Randen zijn halfopen: `[start, end)`.
- Een rapport is een momentopname van de gegevens die bij generatie beschikbaar waren. Na een nieuwe import of heranalyse kan een opnieuw gegenereerd rapport afwijken; de generatie-tijdstippen maken dat zichtbaar.
- Een gebruiker kan geen periode na nu of een lege/ongeldige periode opvragen. Maximaal bereik is 31 dagen per rapportaanvraag; een weekrapport gebruikt exact één kalenderweek.

## Inhoud en regels

1. **Kernsamenvatting.** Benoem de belangrijkste bevindingen, wijzigingen en gegevensbeperkingen. Geef geen totaaloordeel “goed” als dekking ontoereikend is.
2. **Gegevenskwaliteit.** Toon dekking van relevante signalen over de periode, datagaten en verouderde/onbeschikbare signalen. Maak onderscheid tussen nul gebeurtenissen en onbekend door onvoldoende gegevens.
3. **Bevindingen en adviezen.** Toon bevindingen die in de periode zijn aangemaakt, bijgewerkt of hersteld, met ernst, status en korte onderbouwing. Toon daarnaast adviezen die aan het periode-einde nog open of uitgesteld zijn, met hun herstelcriterium en ontbrekende gegevens indien van toepassing. Adviezen die op het periode-einde geaccepteerd, uitgevoerd of afgewezen zijn, blijven zichtbaar als statuswijziging wanneer die binnen de periode viel.
4. **Wijzigingen en effect.** Toon wijzigingen uit het wijzigingslogboek in de periode. Koppel beschikbare voor/na-evaluaties en toon het bestaande oordeel (`improved`, `worsened`, `trade_off`, `not_attributable`, `insufficient_evidence`) met de vergelijkbaarheid en bewijsbeperkingen. Zonder afgeronde evaluatie staat er “Nog geen conclusie”; schrijf geen effect toe op basis van alleen temporele samenloop.
5. **Analyse.** Neem beschikbare kernkengetallen en cycli op, inclusief meetbasis en eenheid zoals door de bestaande API geleverd. Onbekende of niet-gemapte signalen blijven “Onbekend”/“Niet gekoppeld”; vul geen waarden in.
6. **Bron en tijd.** Elke conclusie linkt waar mogelijk naar de relevante bevinding, cyclus, gegevenskwaliteit of wijziging in de app. Toon lokale tijd met datum; vermeld bij klok-/tijdonzekerheid de kwaliteitsmelding.

Een item valt binnen de periode wanneer zijn gebeurtenistijd in `[start, end)` ligt. Status “open aan het einde” wordt bepaald op basis van de laatste status die op of vóór `end` bekend is, niet op de huidige status. Een wijziging of evaluatie zonder valide tijd/periode wordt niet stilzwijgend in het rapport opgenomen; de ontbrekende koppeling wordt als beperking vermeld.

## Formaten en levering

- **HTML (primair):** leesbaar en toegankelijk rapport in de app, met links naar detailpagina’s. Dit is de referentieweergave.
- **PDF:** download van dezelfde rapportmomentopname en inhoudsvolgorde als HTML; paginering mag alleen presentatie wijzigen. Pagina’s tonen titel, periode en paginanummer.
- **CSV:** één rij per gerapporteerd item (bevinding, statuswijziging, wijziging/evaluatie, kwaliteitsgebeurtenis of cyclus) met kolommen `type`, `id`, `tijdstip`, `status`, `titel`, `waarde`, `eenheid`, `toelichting`, `dekking`. Niet-toepasselijke velden zijn leeg. UTF-8, header aanwezig, `;` als scheidingsteken en nl-NL decimale komma. Escape CSV-cellen conform RFC 4180 en neutraliseer spreadsheetformules in tekstvelden.
- **App-download:** gebruiker kan HTML, PDF en CSV downloaden vanuit het rapport; bestandsnamen bevatten soort en lokale periode.
- **Home Assistant-notificatie:** opt-in digest via het bestaande geconfigureerde `notify`-doel met periode, korte samenvatting en een link naar het rapport wanneer de app-URL bruikbaar is. Geen bijlage, volledige meetreeks of persoonlijke notitie in de notificatie. Ontbreekt een notify-doel, dan blijft rapportgeneratie en downloaden beschikbaar.
- Automatische bezorging is apart instelbaar voor dag- en weekrapport. De huidige meldingfrequentie per ernst (`direct`, `dagbundel`, `weekrapport`, `geen`) bepaalt deze rapportplanning niet.

## API- en schermimpact

- Nieuw scherm **Rapporten**, bereikbaar vanuit de hoofdnav en de overzichtspagina.
- Kies dag/week en een beschikbare periode; toon eerst de HTML-preview en de dekking voordat de gebruiker exporteert of verzending inschakelt.
- API biedt een rapportmomentopname in een gestructureerd schema en export-URLs voor HTML/PDF/CSV. HTML, PDF en CSV worden uit dezelfde gevalideerde momentopname opgebouwd.
- Download-endpoints gebruiken expliciete content types en veilige bestandsnamen. API-authenticatie en Home Assistant-ingress gelden gelijk aan andere API-routes.
- De rapportstatus toont export- of afleverfouten zonder de onderliggende rapportgegevens te verliezen; opnieuw proberen maakt geen dubbele rapportnotificatie voor dezelfde periode.
- Er komt een instelling voor dag-/weekbezorging en het bestaande notify-doel. Geen nieuwe ontvanger of kanaal wordt verondersteld.

## Acceptatietests

1. Een dag rond een zomer-/wintertijdgrens bevat alle gebeurtenissen tussen de lokale middernachtgrenzen precies eenmaal; API-UTC-grenzen zijn eenduidig.
2. Een weekrapport gebruikt maandag 00:00 tot de volgende maandag 00:00 in `Europe/Amsterdam` en bevat geen gebeurtenis op de eindgrens.
3. Bevindingen die tijdens de periode wijzigen worden chronologisch getoond; adviezen tonen de status op periode-einde, ook als hun huidige status later veranderde.
4. Een wijziging met evaluatie toont oordeel, vergelijkbaarheid en bewijs; een wijziging zonder evaluatie claimt geen effect.
5. Een rapport met ontbrekende signalen toont de feitelijke dekking en datagaten. Geen data levert geen nulwaarden of groene conclusie op.
6. HTML, PDF en CSV van één momentopname bevatten dezelfde items en status; PDF bevat periode/paginering; CSV rondt waarden niet extra af en ontsnapt separatoren, quotes, regeleinden en formule-prefixen.
7. Dag-/weeknotificaties verschijnen alleen wanneer apart ingeschakeld en het notify-doel is ingesteld; zonder doel blijft downloaden werken. Herhalen van dezelfde verzending levert geen duplicaat op.
8. Rapporten en downloads gebruiken uitsluitend read-only gegevensroutes; er worden geen HA-services voor apparaatbediening aangeroepen en er wordt niet gepubliceerd buiten de eigen `cv_analyse`-topics.

## Implementatievolgorde

1. Rapportquery en momentopname: periodegrenzen, tijdgebonden status, inhoudsselectie en gestructureerd API-schema.
2. HTML/PDF/CSV-renderers en downloadendpoints met content types, escaping en uitvoerige formatteringstests.
3. Rapportenscherm, preview, periodekeuze en downloads.
4. Opt-in geplande HA-notificaties met idempotentie en afleverstatus.

De bijbehorende implementatietickets zijn #131, #132 en #133. Elke stap kan los worden gereviewd; stappen 2–4 zijn afhankelijk van de rapportquery uit stap 1.
