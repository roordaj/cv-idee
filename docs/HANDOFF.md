# Handoff: CV-idee

Bijgewerkt op 19 oktober 2026. GitHub is leidend voor actuele issue-aantallen en statussen. De opdrachtgever heeft zelfstandig en parallel werken geautoriseerd; onafhankelijke tickets draaien in geïsoleerde Git-worktrees. De detectieregels zijn toegevoegd in PR #109 (implementatie `004ffeb`).

## Actuele voortgang

- #20 en #21 afgerond en gemergd via [PR #105](https://github.com/roordaj/cv-idee/pull/105): profiel, perioden, versiebeheer, herberekening en runner-integratie. Reviewfixes: onbekend aantal groepen blijft toegestaan; numerieke pompstand bereikt de regels.
- #18 en #25 afgerond en gemergd via [PR #106](https://github.com/roordaj/cv-idee/pull/106): 18 catalogusrollen, HA-validatie, versiebeheer van koppelingen, circuit-scopes, werkelijke dekking/resolutie en beschikbaarheidsroutes. Ontkoppelen beëindigt de geldigheid in de pipeline.
- #22 afgerond en gemergd via [PR #107](https://github.com/roordaj/cv-idee/pull/107): instellingen met versiegeschiedenis en conflictcontrole, schemas uit geregistreerde regels, toepassing in runner en onveranderlijke configuratie-/advies-snapshots. Migratie 0005 bewaart onboarding-voltooiing.
- PR #109 rondt #31, #32 en #33 af: zes nieuwe regels voor stops tijdens vraag, uitgelijnd temperatuurverloop, verbindingsverlies, expliciet onbeschikbare waarden, veroudering, tapwater en ontbrekende lokale hydraulische metingen. Drempels en regeldocumentatie zijn bijgewerkt.
- PR's #105–#108 hadden groene backend-, frontend- en OpenAPI-checks. De volledige lokale controle voor de detectieregels: 561 backendtests en 94 frontendtests geslaagd, daarna 45 gerichte regressietests na twee reviewaanvullingen; 8 bestaande skips en 32 bestaande xfails. Lint, typechecks en productiebuild groen.
- #35 is uitgewerkt via [PR #110](https://github.com/roordaj/cv-idee/pull/110): declaratieve bundels met oorspronkelijke bron, versie, parameters, bewijs en meetadvies; opvolging en notities blijven beschermd. Scenario 2 heeft één cv-onderzoekspunt, naast zelfstandige tapwaterinformatie. Documentatie: [bevindingen bundelen](bevindingen-bundelen.md).
- Statuslabels: bij oppakken `status:ready` → `status:in-progress`. Bij sluiten blijft `status:in-progress` staan als laatste werkstatus; geen `status:ready` op gesloten issues. Dit is expliciet zo door de opdrachtgever bepaald. De gesloten issues zijn gecontroleerd en hersteld, inclusief #23.
- #36 is gemergd via [PR #111](https://github.com/roordaj/cv-idee/pull/111): echte status- en notitieroutes, persistente uitsteldatum en heropening op datum of bij nieuwe, voldoende gedekte verslechtering. Bestaande profielgebonden adviezen en de UI-link van uitgevoerd naar wijzigingen blijven in gebruik. Documentatie: [aanbevelingen en opvolging](aanbevelingen-opvolging.md). Volledige controle: 588 backendtests en 95 frontendtests geslaagd, 8 bestaande skips en 32 bestaande xfails; lint, typechecks, productiebuild en OpenAPI-generatie groen. Na de laatste verfijning van de instelbare dekkingsgrens zijn de gerichte tests en typecheck opnieuw uitgevoerd.
- #37 is gemergd via [PR #112](https://github.com/roordaj/cv-idee/pull/112): echte gepagineerde advieshistorie, snapshots bij handmatige en automatische statusovergangen, behoud van oorspronkelijke parameters/profiel/specs en vergelijking met actuele regels. Ook zonder opgeslagen instellingenrevisie wordt het eerste advies bewaard. Regelwijzigingsteksten worden uit de docs als package-resource meegeleverd. Documentatie: [advieshistorie](advieshistorie.md). Volledige lokale lint/typechecks/tests/build groen; aanvullend zijn regressies voor standaardinstellingen en profielwijzigingen gecontroleerd.
- #38 is gemergd via [PR #113](https://github.com/roordaj/cv-idee/pull/113): echt wijzigingslogboek, atomaire koppeling met uitgevoerd advies en snapshots, plus echte tijdlijn met wijzigingsmarkers, meetreeksen, cycli en expliciete onbekende tijd. Documentatie: [wijzigingslogboek](wijzigingslogboek.md). Volledige lint/typechecks/tests/build/OpenAPI groen (597 backendtests, 95 frontendtests); aanvullend 5 gerichte tests inclusief numerieke waarden en kwaliteitsgaten.
- #19 is gemergd via [PR #114](https://github.com/roordaj/cv-idee/pull/114): echte HA-recorderimport in blokken van 24 uur, idempotente opslag, persistente checkpoints, hervatten en annuleren, en heranalyse via dezelfde runner als live. Test met fake HA bewijst gelijke cycli bij live-replay en import. Documentatie: [historische import](historische-import.md). Volledige lint/typechecks/tests/build/OpenAPI groen; na heartbeat-review 25 gerichte import-/ingesttests en mypy groen.
- #115 is gemergd via [PR #116](https://github.com/roordaj/cv-idee/pull/116) en herstelt ontbrekende kamersetpoints in de synthetische generator; scenario 7 had wel een comfortoordeel maar geen gewenste kamertemperaturen. De targets zijn expliciet en configureerbaar; bestaande acceptatieverwachtingen en brandercycli blijven behouden. Volledige controle: 599 backendtests en 95 frontendtests geslaagd, bestaande skips/xfails ongewijzigd. De testafhankelijkheid van #39 is hiermee opgelost.
- #39 is gemergd via [PR #119](https://github.com/roordaj/cv-idee/pull/119): pure berekening, echte SQL/runner/API-integratie, cycli en comfort per ruimte, expliciete vergelijkbaarheid en terugdraaicriteria. Historie bewaart ook de oorspronkelijke evaluatie en parameters bij status-/uitkomstwijzigingen. Scenario 7 en 8 zijn via echte opslag/runner getest. Volledige controle: 609 backendtests en 95 frontendtests geslaagd; bestaande 8 skips en 32 xfails blijven tot #52. Documentatie: [voor/na-evaluatie](voor-na-evaluatie.md).
- #118 legt de ontbrekende onderbouwing voor de vlamresolutie in de scenario-opnamen vast. De fixture levert nu echte configureerbare vlambevestigingen; werkelijke resolutie blijft verplicht. Ook dubbele verwerking van dezelfde datagaten bij de resolutiecontrole is verwijderd. Dit is samen met #39 gemergd in PR #119; alle CI-controles waren groen.
- #127 is gemergd via [PR #133](https://github.com/roordaj/cv-idee/pull/133): eerste beoordelingsmoment uit geldige installatiegeschiedenis halen zonder latere signalen of interne gaten te maskeren.
- #130 is gemergd via [PR #134](https://github.com/roordaj/cv-idee/pull/134): hydraulische beschikbaarheid per mengverdeler en informatieve waarschuwing bij ontbrekende lokale metingen.
- #117 is in uitvoering op `feat/117-live-read-models`: echte `/status`, `/overview`, `/quality` en `/cycles`-leesroutes lezen de database. Ontbrekende/ongeldige waarden blijven expliciet onbekend; cycliekengetallen blijven null tot een geslaagde analyse. OpenAPI en frontendtypes zijn bijgewerkt. Lokale lint, typechecks, backendtests (657 geslaagd, 10 bestaande skips en 32 xfails) en frontendtests (115) zijn groen; PR/CI volgen.
- #40 is gemergd via [PR #120](https://github.com/roordaj/cv-idee/pull/120): MQTT discovery, retained state/attributen, Last Will, actuele uitvalcontrole, Supervisor-brokerlookup, REST-terugval en echte exportstatus. De 16 gerichte tests, inclusief Mosquitto-containerproef met abrupt beëindigd testproces, fake-HA en Supervisor slagen. Volledige lint/typechecks/tests/build/OpenAPI zijn groen: 623 backendtests en 95 frontendtests, 8 bestaande skips plus 2 optionele brokertests, 32 bestaande xfails voor #52. De optionele brokertests zijn afzonderlijk daadwerkelijk uitgevoerd en draaien ook in CI. Documentatie: [HA-export](home-assistant-export.md).
- #41 is geïmplementeerd op `feat/41-notification-policy`: echte beleids-/logroutes, duurzame cursor en outbox, dag-/weekbundels om 08:00 Amsterdam, hogere ernst en alleen aangetoond herstel. Migratie 0006. Volledige lint/typechecks/tests/build/OpenAPI groen: 641 backendtests, 95 frontendtests; daarna 19 gerichte tests incl behoud van analyse-instellingen/onboarding. Documentatie: [meldingen](meldingen.md).
- #99 is na review gemergd via [PR #121](https://github.com/roordaj/cv-idee/pull/121): datum/tijd in Amsterdam, reden, uitvoerder en zomer-/wintertijdvalidatie; 104 frontendtests groen.
- #51 is gemergd via [PR #124](https://github.com/roordaj/cv-idee/pull/124): echte instellingen-/onboardingflows en app-shell. #52 werkt aan echte runneracceptatie zonder fixtureverwachtingen te versoepelen. #123 heeft onvoltooide implementatie en tests op een eigen werkbranch; #129, #131, #128 en #132 blijven open voor de gevonden acceptatieproblemen.
- #5-documentatie/opname zijn gemergd via [PR #125](https://github.com/roordaj/cv-idee/pull/125); #5 blijft open omdat een echt vlamsignaal ontbreekt. CAN-entiteiten zijn nu via HA MCP leesbaar. #122 vraagt decoderbewijs/GM003; #123 levert installatiegebonden modusmapping. AM012 3=CV en 4=tapwater passen niet bij de vroegere voorlopige 1/2-mapping.
- De opdrachtgever heeft zelfstandig afwerken van issues en PR's geautoriseerd. Volg de actuele AGENTS.md-instructies uit de sessie. De historische werkafspraken hieronder beschrijven de oorspronkelijke overdracht.

Documentatie bij het nieuwe backendgedrag: [signaalkoppelingen](signaalkoppelingen.md) en [instellingen-API](instellingen-api.md).

## Oorspronkelijke overdracht

De volgende secties bewaren het oorspronkelijke overzicht van 9 oktober 2026. Wip-statussen van #20/#21 en #18/#25 zijn achterhaald; gebruik de actuele voortgang hierboven.

## Project in het kort

- CV-idee leest gegevens van een Remeha Calenta Ace met eTwist via Home Assistant en geeft verklaarbaar advies. Nooit schrijven naar ketel of thermostaat.
- Repository: `roordaj/cv-idee` (privé). De GitHub-token staat lokaal in `.env` als `GITHUB_ACCESS_TOKEN`. Toon of commit de token nooit. Voor GitHub CLI:

  ```sh
  set -a
  . ./.env
  set +a
  export GH_TOKEN=$GITHUB_ACCESS_TOKEN
  ```

- Stack: Python 3.12, FastAPI, SQLite en Alembic; React, TypeScript en Vite. Uitrol als HA add-on met ingress of standalone via Docker. Terugkoppeling naar HA via MQTT discovery (Mosquitto), uitsluitend binnen de toegestane eigen topics uit `AGENTS.md`.
- Leidende documentatie: [AGENTS.md](../AGENTS.md), [functionele requirements](cv-idee-functionele-requirements.md), [technisch plan](technisch-plan.md), ADR 001–004 in [adr/](adr/) (datamodel, pipeline, veroudering, regels), [ontwerp v3](design/CV-analyse-v3.dc.html) en [aanvullingen](design/aanvullingen.md).
- Roadmap: [issue #63](https://github.com/roordaj/cv-idee/issues/63).
- `make dev`: backend op 8099 met voorbeelddata en frontend op 5173; ontbrekende packages worden geïnstalleerd. `make dev-up`: HA, Mosquitto en app in Docker. Lokale API-documentatie: <http://localhost:8099/docs>.

## Wat af is

- Basis: repo-opzet, CI, automatische blocked/ready-labels, container en add-on, migraties bij opstarten.
- Data: opslag van waarnemingen en HA-client.
- Analyse: stap 1–5 (tijdlijnen en kwaliteit, bedrijfsmodi, cycli, kengetallen), analyse-runner, bevindingen-engine, regel kort-branden en de 10 testscenario's (deels nog als verwachte fout gemarkeerd).
- API en UI: volledig API-contract met voorbeelddata en alle 9 schermen.

## Eerst hervatten: #20 en #21

Profiel en perioden in de backend zijn in uitvoering op `feat/20-21-profile-periods`, nog zonder PR. Beide issues staan op `status:in-progress`.

Af volgens de overdracht: migratie 0004; packages `installation/` en `periods/` met repository, standaardprofiel, predicaten en `excluded_intervals`; echte routes inclusief `PUT /api/periods/{id}`; runner die het echte profiel en de echte perioden doorgeeft aan de regels.

De tests zijn geschreven maar nog niet gedraaid. Hervat op de wip-branch:

1. Draai de gerichte tests en herstel fouten.
2. Draai `make lint typecheck test` en `make openapi`. De verplaatste routes kunnen een contractdiff veroorzaken; controleer en commit noodzakelijke wijzigingen.
3. Rebase op `main`.
4. Open een PR met `Closes #20` en `Closes #21`, review en controleer CI.

## Daarna: #18 en #25

Signaalcatalogus, koppeling en beschikbaarheid zijn nog niet begonnen. #18 staat op ready; #25 is blocked omdat het wacht op #18. Lever beide in één PR. Een eerdere agentopdracht bestaat volgens de overdracht, maar is hier niet opgenomen.

## Vervolgens, op volgorde van belang

Volgens de overdracht zijn onderstaande direct oppakbare issues prio M en ready; controleer de actuele labels en afhankelijkheden.

1. #22 Instellingen-API. Hierop bouwt #51: analyse-instellingen en eerste start op `/welkom`.
2. #31 en #32 Detectieregels. #33 (hydraulisch) wacht op #20 en #25.
3. #35 Bundelen van bevindingen; #36 Aanbevelingen en opvolging (wacht op #20); #37 Advieshistorie.
4. #38 Wijzigingslogboek in de backend, daarna #39 voor/na-evaluatie, daarna #52 MVP-acceptatie.
5. #40 MQTT-export en #41 meldingen.
6. #99 Tijdstip, reden en ‘uitgevoerd door’ invoeren in het formulier Wijzigingen.
7. #71 Image publiceren naar GHCR.
8. #53 End-to-end tests met Playwright.

## Werkafspraken uit de overdracht

- Maximaal 3 agents tegelijk. De eerdere Claude-werkwijze gebruikte Sonnet voor bouwtickets en Opus alleen voor complexe ontwerptickets; pas dit alleen toe waar die modellen beschikbaar zijn.
- Agentopdrachten noemen uitsluitend benodigde documenten en secties. Lees het ontwerpbestand van 123 KB gericht met `sed` per scherm. Rapporten maximaal 10 regels. Draai de volledige testsuite één keer aan het eind.
- Na een pauze: start een nieuwe agent op de wip-branch, hervat de oude agent niet wegens opgebouwde context.
- De eerdere afspraak geeft Claude toestemming om na review en groene CI te mergen. Branch protection kan volgens de overdracht niet aan voor deze private repo op een gratis account. Nooit mergen met rode checks.
- Volg daarnaast de issue-, branch-, scope- en Definition of Done-afspraken in `AGENTS.md`.

## Bekende valkuilen en opruimwerk

- UI-PR's botsen vaak in de `screenElement`-switch van `frontend/src/app/App.tsx`. Rebase vlak voor pushen; behoud bij conflicten beide bedoelde wijzigingen.
- Als CI niet start, heeft de PR meestal een merge-conflict.
- `gh issue list` toont standaard maximaal 30 resultaten. Gebruik `--limit 300`.
- Bij een 403 op `gh pr checks` mist de token de permissie Checks. Gebruik `gh run list` en `gh run watch`.
- `backend/data/` (lokale dev-database en runtimebestanden) is inmiddels toegevoegd aan `.gitignore`.
- Ongeveer 30 gemergde remote-branches staan nog op origin en kunnen worden opgeruimd.

## Wacht op de eigenaar

- #5: inventarisatie van CAN-signalen met toegang tot de eigen HA en de checklist uit het issue. Deze bepaalt de modus-codes (voorlopig 1 = CV, 2 = tapwater), `heartbeat_expected` en `max_age`.
- Ontwerpvragen 1–9 uit een eerder bericht (onder andere standaarddrempels): zonder antwoord geldt het voorstel. De vragen en voorstellen zijn niet opgenomen in deze overdracht; zoek de bron voordat ze nodig zijn voor implementatie.
