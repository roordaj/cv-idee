# Bundelen van bevindingen

`cvidee.findings.bundling` bepaalt declaratief welke kandidaten één onderzoekspunt
vormen. `kort-branden` kan `stop-tijdens-vraag`, `temperatuurverloop` en een gerelateerde
hydraulische beperking bevatten. Zonder kort-branden kan temperatuurverloop onder
stop-tijdens-vraag vallen. Een kind moet de ouderregel expliciet ondersteunen.

## Relatie en tijdvak

Perioden moeten overlappen; elkaar rakende halfopen perioden zijn niet voldoende.
Als beide kandidaten cyclussen noemen, moet minstens één cyclus gedeeld zijn.
Scopes moeten gelijk zijn. Alleen het beleid voor kort-branden staat een bekende
cv-circuitscope onder de ketelscope toe. Elk kind krijgt hoogstens één ouder, in een
vaste beleidsvolgorde. Gegevenskwaliteit en tapwaterinformatie blijven zelfstandig.

Een kandidaat met `insufficient_evidence` en een `supports`-relatie die niet kan worden
gebundeld, blijft niet als losse bevinding staan. Zo worden losse meetadviezen zonder
voldoende patrooncontext niet als afwijking gepresenteerd.

Bundeling verandert de zekerheid, ernst, prioriteit of aanbeveling van de hoofdbevinding
niet. Het aantal oorspronkelijke kandidaten is geen extra statistisch bewijs.
Ondersteunende meetadviezen blijven afzonderlijk zichtbaar binnen de bundel.

## Opslag en levenscyclus

Oorspronkelijke regel-ID, versie, parameters, scope, periode, waarneming, interpretatie,
hypotheses, signalen, onderbouwing, verwijzingen en advies blijven in de bundel opgeslagen.
`FindingEvidence` gebruikt daarvoor het bestaande type `bundled_candidate`; originele
verwijzingen blijven met hun bronregel bewaard. Een databasemigratie is niet nodig.

Een bestaande losse melding die nu wordt gebundeld krijgt `superseded`, niet `recovered`.
De oorspronkelijke melding en haar advies verdwijnen niet uit de database. Het detail
verwijst via `superseded_by` naar de hoofdbevinding. Als de ouder niet meer wordt uitgegeven
maar het kind nog wel, kan het kind opnieuw een zelfstandige actieve bevinding worden.

Adviezen met een opvolgstatus buiten `open`, of met gebruikersnotities, worden niet
stilzwijgend verborgen door bundeling. Verdwijnende bronnen blijven niet hangen in een
bijgewerkte bundel. Bij onvoldoende gegevens gelden de bestaande conservatieve
herstelcriteria: bundeling bewijst geen herstel.

## API en schermen

`GET /api/findings/{id}` levert onder `bundle` de oorspronkelijke tekst, bron/regelversie,
parameters, onderbouwing en meetadvies. De tijdlijn omvat ook de perioden van de bronnen;
verwijzingen naar dezelfde meting worden in de weergave ontdubbeld. De bestaande kaart
“Samengevoegd tot één punt” toont ook aanvullende metingen.

De database-lijst behoudt de bestaande deterministische prioriteitsformule en tie-breaks.
Overzicht en Bevindingen gebruiken in de voorbeeldmodus dezelfde prioriteitsvolgorde.
De overige onderdelen van de echte Overzicht-API zijn nog niet geïmplementeerd.

Advies-snapshots registreren de introductie of verandering van een bundelbron, regelversie,
parameters of profiel. Een wijziging van alleen een live-telling maakt geen extra snapshot.
Eerdere snapshots blijven onveranderlijk.

## Verificatie

Scenario 2 levert één cv-onderzoekspunt met de oorspronkelijke stop-, temperatuur- en
hydraulische onderbouwing. De aparte tapwater-informatie uit die fixture blijft zichtbaar.
Regressietests dekken volgorde-onafhankelijkheid, niet-overlappende perioden, verschillende
cyclussen/scopes, opvolging, superseded-verwijzingen, terugkerende zelfstandige meldingen,
prioriteit en onveranderlijke snapshots.
