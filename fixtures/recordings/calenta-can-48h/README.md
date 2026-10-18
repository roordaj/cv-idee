# CAN-recorderopname, 48 uur

Echte HA-recorderhistorie, volledig gepagineerd (20 entiteiten, 12.690 records). Zie [inventarisatie](../../../docs/signalen-calenta.md) voor de betekenis en beperkingen. Dit is geen synthetische fixture en geen CAN-framecapture.

`manifest.json` beschrijft bron, query, aantallen, eenheden en kwaliteitsgrenzen. `observations.jsonl` bevat één record per door HA teruggegeven state, gesorteerd op relatieve tijd en alias. `t_us` en `updated_us` zijn microseconden vanaf de vensterstart; de oorspronkelijke submilliseconderesolutie is behouden. Het venster eindigt exclusief bij 172.800.000.000 µs. `state` blijft de oorspronkelijke string, inclusief unknown/unavailable. `boundary_state=true` markeert de eerste door recorder ingevoegde/beschikbare toestand per entiteit; dit is geen nieuwe waarneming op t=0.

Aliassen vervangen alleen de oorspronkelijke entityprefix en bronroute: `gateway_mqtt_` of `gateway_native_`. Geen absolute tijdstippen, ruimte-/locatienamen, MAC-adressen, tokens, context-id's of hostnamen. Geen interpolatie, downsampling, verplaatste events of aangevulde bevestigingen. Cloud-/kamer-/aanwezigheidsgegevens zijn niet opgenomen.

Drie AM012=3-perioden duren ongeveer 22, 116 en 61 seconden (start respectievelijk 12.588.983.687, 82.643.236.632 en 102.548.081.692 µs). AM012=4 komt eveneens voor: volgens gatewayomschrijving en officiële handleiding warmwaterbedrijf. Deze aanwijzingen bewijzen **geen korte branderperiodes**, omdat GM003/vlamdetectie ontbreekt. Er zijn bewust geen verwachte vlamstarts of gegenereerde flame-records toegevoegd. #5 blijft daarom open; #122 vraagt het ontbrekende bewijs.

Voor replay: lees de bronaliassen als afzonderlijke tijdlijnen, behoud grensrecords als carry-in en unknown als onbekend; kies expliciet een gevalideerde statusmapping. Gebruik nooit de app-default 1=CH/2=DHW voor deze AM012-opname (#123). Voor rapportcadans/actualiteit is aanvullend bewijs nodig; alleen recorderwijzigingen tonen geen heartbeat.

Controle: `python3 fixtures/recordings/calenta-can-48h/verify.py`. Dit controleert integriteit en aanwezige statusevents, zonder daar brandercycli van te maken. De gewone backendtests voeren dezelfde verifier uit via `backend/tests/test_recording_integrity.py`, zodat CI de checksum en paginatellingen bewaakt.
