# Wijzigingslogboek

`GET /api/changes` en `POST /api/changes` gebruiken de database. Een wijziging
bevat het uitgevoerde tijdstip, uitvoerder, parameter, oude en nieuwe waarde,
reden en eventueel de bevinding met de opgevolgde aanbeveling. De lijst staat
op uitgevoerd tijdstip, nieuwste eerst; `W-nn`-nummers blijven uniek, ook als
wijzigingen later met een eerder tijdstip worden ingevoerd.

De bekende parameters zijn maximale CV-aanvoer, pompstand, stooklijn eTwist,
thermostaatprogramma en lusdebiet van de verdeler. Andere labels worden als
vrije parameter bewaard. Waarden blijven weergavetekst: er wordt geen eenheid
of betekenis geraden. Lege parameters of nieuwe waarden en toekomstige
uitvoeringstijdstippen worden afgewezen.

Bij koppeling aan een aanbeveling wordt die in dezelfde transactie als
uitgevoerd gemarkeerd, inclusief adviessnapshot. Een onbekende bevinding of
een bevinding zonder aanbeveling maakt de hele aanvraag ongeldig. De app
voert de wijziging nooit uit en werkt het installatieprofiel niet automatisch bij.

`GET /api/timeline?from=…&to=…` gebruikt nu ook echte gegevens. Wijzigingsmarkers
vallen in het halfopen tijdvak `[from, to)`; de laatste eerdere wijziging staat
in `last_change_before`. Tijdstippen worden als UTC teruggegeven, met behoud
van het door de gebruiker opgegeven werkelijke moment.

De tijdlijn gebruikt dezelfde signaalkoppelingen, geldigheidsintervallen en
kwaliteitscontrole als de analyse. Meetreeksen worden op maximaal 1.200
punten bemonsterd. Onbekende waarden blijven `null`, vlamgaten blijven zichtbaar
en ontbrekende modus of warmtevraag wordt onbekend. Opgeslagen cycli en
bijzondere perioden blijven zichtbaar. Zonder tijdvak geldt de laatste 24 uur;
het maximale tijdvak is 31 dagen.

De evaluatieroute berekent de referentie- en observatieperiode op echte gegevens.
Zie [voor/na-evaluatie](voor-na-evaluatie.md) voor de kengetallen,
vergelijkbaarheidscontroles, oordelen en terugdraaicriteria.
