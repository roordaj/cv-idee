# Voor/na-evaluatie

`GET /api/changes/{id}/evaluation` berekent de vergelijking op echte gegevens en
bewaart het resultaat in `change_evaluations`. De analyserunner doet hetzelfde en
levert de feiten aan de versiebeheerde regel [voor-na](regels/voor-na.md).

De berekening in `cvidee.analysis.change_evaluation` is puur. De IO-laag haalt
waarnemingen en afgeleide cycli op, past bestaande gegevenskwaliteitscontrole toe en
bewaart de vergelijking. Per periode worden gerapporteerd:

- CV-starts per daadwerkelijk waargenomen uur met warmtevraag;
- mediaan brandduur en aandeel korte stops tijdens vraag;
- gemiddelde ketelaanvoer tijdens stabiel CV-bedrijf;
- comfortverlies per gekoppelde ruimte, meer dan de ingestelde grens onder het
  geldige kamersetpoint, omgerekend naar een waargenomen week;
- dekking, vlamresolutie en uitgesloten tijd.

Vergelijkbaarheid toont weer, kamerinstellingen, andere wijzigingen, bijzondere
perioden, gegevensdekking en comfortdekking per ruimte. Veranderingen in een
kamerprogramma worden ook bij gelijkblijvend gemiddelde herkend via lokale
weekdag-/kwartierprofielen. Datagaten blijven onbekend. Warmtevraagtijd wordt niet
met lange standby vermengd. Lagere aanvoer is op zichzelf geen bewijs van verbetering.

Vóór het einde van de observatieperiode blijft het oordeel lopend. Bekende andere
wijzigingen kunnen al eerder aantonen dat individueel toeschrijven onmogelijk is.
Daarna zijn de oordelen verbeterd, verslechterd, afweging, niet toe te schrijven of
onvoldoende bewijs. Richtingen worden op dezelfde precisie als de weergave beoordeeld.

Bij een gekoppelde uitgevoerde aanbeveling wordt de uitkomst bijgewerkt. Een
overschreden terugdraaicriterium activeert de opvolgstatus `rollback_triggered` en
legt een adviessnapshot vast. Een wijziging van alleen de uitkomst krijgt ook een
snapshot, met de oorspronkelijke adviesonderbouwing én de bewaarde evaluatie,
parameters en configuratiehash. Herhaald berekenen zonder status-/uitkomstwijziging
maakt geen dubbele historie. Onvoldoende bewijs wist een eerdere activatie niet.

De API ondersteunt expliciete criteria met `metric: room_cold_hours_per_week`,
`scope_key: room:<ruimte>`, `op: '>'` en een niet-negatieve `threshold`. Zonder
adviesoverride geldt de ingestelde standaardgrens per ruimte.

Voor de synthetische acceptatiescenario's zijn gewenste kamertemperaturen expliciet
vastgelegd (#115) en vlambevestigingen aantoonbaar aanwezig (#118). De verwachte
scenario-oordelen zijn daarbij niet aangepast. Uitsluitend synthetische data heeft
zulke defaults; echte ontbrekende signalen blijven onbekend.
