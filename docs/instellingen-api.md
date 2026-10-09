# Instellingen-API en configuratiesnapshots

`GET /api/settings` levert de effectieve instellingen, een revisietoken en het
formulier-schema. Zonder opgeslagen revisie gelden de schemadefaults en is
`updated_at` onbekend (`null`). `PUT /api/settings` valideert algemene instellingen
en parameters tegen de schemas van de geregistreerde regels.

Het formulier-schema behoudt de Nederlandse teksten en `x-unit`, `x-step`, `x-group`
en `x-rule` uit het ontwerp. `x-rule-schemas` bevat daarnaast de volledige schemas
van geregistreerde regels. Expliciete adapters verbinden bijvoorbeeld
`min_observation_hours` met de regelparameter `min_observation_h`.

## Versies en herberekening

Een save draagt de gelezen revisietoken mee. Alleen de actuele token wordt geaccepteerd;
verouderde of gelijktijdige saves geven 409. De token bevat een revisienummer en
configuratiehash: terugzetten naar eerdere waarden maakt een oudere token niet opnieuw
geldig. Een save zonder inhoudelijke wijziging maakt geen nieuwe revisie.

`GET /api/settings/history` levert de revisies met waarden, tijdstip en de eventueel
meegegeven `changed_by` en `note`. Deze auteur is door de gebruiker opgegeven,
niet afgeleid van een HA-account. Nieuwe revisies bevatten ook de opgeloste defaults,
zodat een latere wijziging van codedefaults hun betekenis niet verandert. Bestaande
revisies met alleen overrides blijven leesbaar. De legacy-retentiesleutel
`retention.raw_days` wordt gelezen als `retention_days`.

Bij gewijzigde waarden en opgeslagen signaaldata wordt herberekening vanaf de oudste
relevante waarneming aangevraagd. Zonder zulke data wordt geen herberekening gestart.
Onboarding-voltooiing wordt met de revisie opgeslagen, maar triggert op zichzelf geen
analyse. Maximale sensorleeftijd en de heartbeat-keuze blijven op de signaalkoppeling;
ze worden via `/api/signals/{signal_id}` gewijzigd.

## Runner en advies

De runner leest één instellingen-snapshot per reeks runs. De configuratiehash hangt
van die instellingen af; runs bewaren de revisie-ID en volledige gebruikte waarden.
Warmtevraag-na-stop beïnvloedt de pipeline en vergroot zo nodig de wachtmarge.
Kortecyclusgrens, aantallen en herhalingscriteria gaan naar de geregistreerde regel;
de beschikbaarheids- en herstelinstellingen worden eveneens toegepast.

Open adviezen krijgen bij een nieuwe of gewijzigde configuratie een onveranderlijke
snapshot met meetperiode, profiel, regelversie, parameters, instellingen en de getoonde
bevinding/aanbeveling. Opvolging en de volledige advieshistorie-API volgen in #36/#37.
Adviezen die al in opvolging zijn worden door deze configuratiesnapshot niet herschreven.
