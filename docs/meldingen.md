# Meldingen en ruisonderdrukking

Issue #41, FR-39. Het meldingsbeleid en logboek werken op de echte database.
De app bestuurt geen ketel, thermostaat of andere apparaten.

## Kanaal en ontvanger

Standaard: hoog **Direct**, middel **Dagbundel**, laag **Weekrapport**, info **Geen**.
`GET|PUT /api/notifications/policy` bewaart de kanaalkeuze per ernst. De schakelaars
voor bundelen en opnieuw melden worden met de instellingenrevisie bewaard;
wijzigen daarvan behoudt analyse-instellingen en onboardingstatus.

Stel `CVIDEE_NOTIFY_TARGET` in op bijvoorbeeld `notify.mobile_app_telefoon` of
`mobile_app_telefoon`. Alleen een `notify`-servicenaam is toegestaan. Zonder doel
wordt uitsluitend het eigen HA-event verstuurd. Dit verzendt geen pushbericht.

Elke verzonden melding bevat ook het event `cv_analyse_finding` met
`notification_id`, soort, bevinding-ID's, kanaal en de waargenomen periode.
**Geen** onderdrukt `notify`, maar laat één event voor eigen automations toe.
Bij dag-/weekbundels wordt één event voor de bundel verstuurd. De keuze voor
Geen is dus geen opdracht om de leesbare eigen HA-sensoren of events uit te zetten.

## Eén melding per probleem

De bevindingen-engine bundelt verwante analyses en houdt een blijvend bevinding-ID.
Een aparte persistente meldingscursor bewaart de laatst waargenomen ernst en
levenscyclus. Een volgende cyclus of een appherstart creëert daardoor geen nieuwe
melding voor hetzelfde probleem. Een stijging in ernst geeft een nieuwe melding,
als **Opnieuw melden als het erger wordt** aan staat. Alleen een gewijzigd aantal
cycli geeft geen nieuwe melding.

De verstuurde tekst bevat het waarnemingstijdstip in Europe/Amsterdam. De
onderbouwing en zekerheid blijven categorieën uit de analyse. De melding noemt
geen berekende besparingen of vermogens zonder de daarvoor benodigde gegevens.

## Bundels en tijdzone

Dagbundels worden vanaf **08:00 Europe/Amsterdam** aangeboden; weekrapporten vanaf
**maandag 08:00**. Alleen gebeurtenissen tot die grens gaan mee. Een gebeurtenis
later op de dag wacht op de volgende grens. Uitval rond de grens wordt na herstel
ingehaald. Berekeningen gebruiken lokale kalenderdagen, inclusief zomer-/wintertijd.

Met bundelen aan toont een bundel per bevinding de laatste overgang, bijvoorbeeld
hersteld. Alle oorspronkelijke gebeurtenis-ID's blijven bewaard. Met bundelen uit
blijven de afzonderlijke overgangen in de bundeltekst zichtbaar. Er wordt geen
leeg dag-/weekrapport verstuurd en hetzelfde onveranderde probleem wordt niet
iedere dag of week opnieuw gemeld.

## Herstel

Een melding sluit uitsluitend na `resolution_reason = recovered` uit de bestaande
bevindingen-engine. Onbekende/verloren data, aangepaste drempels, een gewijzigde
regel of samenvoegen van bevindingen zijn geen herstelbewijs. Het scherm toont de
werkelijke herstelinstellingen (aantal dagen, vergelijkbaar weer en minimale
dekking); die zijn instelbaar via Analyse-instellingen.

## Wachtrij en fouten

Gebeurtenis, cursor en eventuele bundel worden in één databasetransactie vastgelegd.
Verzending gebeurt daarna, los van analyse en import. Een onbereikbare HA laat de
wachtrij staan. Een bevestigde `notify`-verzending wordt apart opgeslagen, zodat een
mislukt volgend event niet steeds opnieuw een pushbericht veroorzaakt. Een later
gewijzigde kanaalkeuze geldt ook voor nog niet verzonden individuele gebeurtenissen;
Geen stopt ook de push van een reeds klaargezette bundel.

Volledig precies één verzending kan een netwerk-API niet garanderen: als de app
stopt nadat HA een bericht heeft aangenomen maar vóór de bevestiging lokaal is
bewaard, kan een poging herhaald worden. Het stabiele `notification_id` in het event
maakt ontdubbelen in eigen automations mogelijk. Achterstallige meldingen vermelden
hun oorspronkelijke waarnemingstijd; zij zijn geen nieuwe actuele meting.

`GET /api/notifications?limit=50&offset=0` toont de bevestigde verzendingen,
nieuwste eerst. Pending, mislukte en in bundels opgenomen gebeurtenissen blijven
voor controle in de database; zij worden niet als verstuurd gepresenteerd.

## Verificatie

De tests gebruiken echte SQL-opslag, migraties en bevindingen-engine, met een fake
HA-transport. Ze controleren herstartbestendige deduplicatie, hogere ernst,
schakelaars, dag-/weekgrenzen en wintertijd, aantoonbaar herstel, uitval en
hervatten na gedeeltelijke verzending, kanaalwijzigingen en de echte API-routes.
Geen test stuurt een werkelijk apparaat of verstuurt een echte gebruikersmelding.
