# Aanbevelingen en opvolging

De bestaande routes `POST /api/findings/{id}/status` en
`POST /api/findings/{id}/notes` gebruiken nu ook zonder voorbeelddata de database.
Status, uitsteldatum en notities blijven bij een herstart behouden. Bevindingen
zonder aanbeveling geven bij deze acties een 422; een onbekend nummer geeft 404.
Notities worden ontdaan van omringende witruimte; lege notities zijn ongeldig.

Een aanbeveling kan open, geaccepteerd, uitgesteld, uitgevoerd of afgewezen zijn.
Bij uitstellen geldt de ingestelde standaardtermijn, tenzij een toekomstige
uitsteldatum is opgegeven. Een uitsteldatum bij een andere status is ongeldig.
Bij uitgevoerd blijft de uitkomst eerst onbeslist; de
[voor/na-evaluatie](voor-na-evaluatie.md) beoordeelt het effect.
De bestaande UI verwijst dan naar het vastleggen van een wijziging. De beschreven
succes- en terugdraaicriteria blijven zichtbaar; effectmeting kan het ingestelde
terugdraaicriterium activeren, met behoud van de oorspronkelijke adviessnapshot.

Uitstel eindigt op de ingestelde datum, ook als er geen nieuwe meetgegevens zijn:
zowel de bevindingenroutes als de runner controleren dit. Het probleem zelf wordt
hierdoor niet als hersteld beschouwd. Eerder terugkomen kan alleen bij nieuwe
meetgegevens binnen dezelfde regelversie en parameters:

- hogere ernst bij ten minste de ingestelde minimale beoordelingsdekking
  (standaard 80%) en minimaal de oorspronkelijke dekking;
- een groter aandeel patrooncycli bij diezelfde dekking en minimaal het
  oorspronkelijke aantal relevante cycli.

De vergelijking gebruikt de onderbouwing op het moment van uitstellen. Meer
waarnemingen bij een gelijkblijvend aandeel, onvoldoende dekking, heranalyse van
hetzelfde tijdvak en een regelwijziging zijn geen bewijs van verslechtering.
Notities blijven behouden. Geaccepteerde, uitgevoerde en afgewezen adviezen worden
niet automatisch herschreven. De detectieregels blijven verantwoordelijk voor
profielgebonden advies en aanvullende metingen bij ontbrekende gegevens.

Advieshistorie en snapshots bij statusovergangen staan beschreven in
[advieshistorie](advieshistorie.md).
