"""Value tables for items and patrons: Alephino value -> Koha code. Standard library only, so the check tools can use
them without pymarc. A value that is not in a table becomes a Klärfall „Wert ohne Zuordnung“ (umwandeln.py).
"""
from __future__ import annotations

ZWEIG = "BIB"                                                      # one branch in the sample
TYPEN = {"BK": "BK", "ZS": "ZS"}                                   # medientyp -> item type
TYPNAMEN = {"BK": "Buch", "ZS": "Zeitschriftenband"}
STANDORTE = {"Magazin": "MAG", "Lesesaal": "LS", "Freihand": "FH"}  # standort -> shelving location (LOC)
STATUS = {"ausleihbar": None, "praesenz": "1"}                     # status -> notforloan (952 $7)
GRUPPEN = {"MA": "MA", "EX": "EX"}                                 # gruppe -> patron category
GRUPPENNAMEN = {"MA": "Mitarbeitende", "EX": "Externe"}
