"""Formel-Injektion in CSV-Dateien für Menschen verhindern.

Excel/LibreOffice führen eine Zelle, die mit = + - @ beginnt, als Formel aus –
mit DDE (=cmd|'/c …'!A1) sogar Programme. Inhalte stammen hier oft aus fremder
Hand (Artikelnamen, Kundenadressen, Mails). Ein vorangestelltes ' macht die Zelle
zu Text.

Bewusst eng: viele dieser Dateien werden bearbeitet und wieder in die Wawi
importiert. "-5", "+49 711 …" oder "- Sonderposten" bleiben deshalb unverändert;
+/- wird nur entschärft, wenn danach Formelzeichen folgen.
Gegenstück im Frontend: frontend/src/utils/csvSicher.ts. Maschinenformate
(DATEV, Ameise-Ziele der Mappings) laufen NICHT hier durch.
"""
_IMMER = ("=", "@", "\t", "\r")
_FORMELZEICHEN = ("(", "!", "|", "=")


def zelle(wert):
    if not isinstance(wert, str) or not wert:
        return wert
    erstes = wert[0]
    if erstes in _IMMER or (erstes in "+-" and any(z in wert for z in _FORMELZEICHEN)):
        return "'" + wert
    return wert
