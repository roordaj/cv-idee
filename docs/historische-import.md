# Historische import

De import gebruikt uitsluitend de leesroute van de
[Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest/).
Per gekoppelde bronentiteit worden blokken van maximaal 24 uur opgehaald.
`minimal_response` en `no_attributes` beperken de overdracht; bij signalen met
verwachte heartbeats wordt het volledige antwoord gevraagd om beschikbare
bevestigingstijdstippen te behouden.

`POST /api/import` accepteert `from`, `to` en optioneel de canonieke signaal-id's
in `signal_ids`. Er kan één import tegelijk actief zijn. Een tweede aanvraag
geeft 409; zonder HA-configuratie geeft starten 503. Ongeldige tijdvakken,
toekomstige eindtijden en onbekende of lege signaalselecties geven 422.

Elke afgeronde bloktransactie bewaart waarnemingen, aantallen en het volgende
ophaaltijdstip samen. Ontdubbelen gebruikt de bestaande opslaglogica; opnieuw
importeren voegt identieke waarnemingen niet toe. Polling via
`GET /api/import/{id}` verandert de voortgang niet. `GET /api/import` toont
opgeslagen taken, ook na een herstart.

Een identieke aanvraag hervat een onderbroken of mislukte import bij het laatste
volledig opgeslagen blok. Bij een applicatieherstart wordt een achtergebleven
actieve import automatisch hervat als HA ingesteld is. Annuleren bewaart reeds
vastgelegde gegevens, maar commit geen gedeeltelijk opgehaald blok. Zonder
nieuwe gegevens na annuleren kan de status niet alsnog naar klaar springen.

De eerste recorderwaarde van een blok kan de toestand van vóór dat blok zijn.
Die wordt als peiling opgeslagen, zodat een al brandende ketel geen nieuwe start
krijgt. Ontbrekende bevestigingen worden niet bijgemaakt. Een later beschikbaar
rapportagetijdstip wordt als aparte bevestiging vastgelegd en vult eerdere
onbekende tijd niet achteraf op. De recorder bewaart
niet altijd dezelfde heartbeats als liveverwerking; daarom toont de import een
waarschuwing en blijven de bestaande verouderingsregels van toepassing.
Een onbekende bewaartermijn, dekking of resterende duur blijft `null`.

Bronselecties worden bij het starten vastgelegd; signaalkoppelingen worden niet
stilzwijgend teruggedateerd. Waar koppelingen pas later geldig zijn, waarschuwt
de API dat eerdere waarnemingen buiten die analyse blijven. Hun geldigheid kan
via de bestaande signaalkoppel-API expliciet worden opgegeven.

Na het ophalen verwerkt `AnalysisRunner.run_range` hetzelfde gegevensbereik via
hetzelfde analysepad als livegegevens. De taak wordt alleen klaar als de
analyseruns slagen. Fouten bewaren een bruikbare melding zonder tokens of
upstream-URL's op te slaan.
