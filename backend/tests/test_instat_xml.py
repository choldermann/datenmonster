"""INSTAT/XML für den Datei-Upload in eSTATISTIK.core (Destatis „INSTAT/XML Integration“, 10/2025)."""
import xml.etree.ElementTree as ET

import pandas as pd
import pytest

from app.services.export_service import export_destatis_instat_xml

CFG = {"psi_id": "0512345678900001", "firma": "Muster & Söhne GmbH", "strasse": "Teststraße 1",
       "plz": "40210", "ort": "Düsseldorf", "ansprechpartner": "Erika Muster", "bundesland": "05"}


def _zeile(**w):
    z = {"richtung": "V", "commodity_code": "48181010", "country_of_origin": "HU", "partner_country": "AT",
         "transaction_nature": "11", "mode_of_transport": "5", "net_mass": 252.6, "invoiced_amount": 1011.4,
         "statistical_value": 1011.4, "vat_id_recipient": "ATU83164219", "bundesland": "99",
         "monat": "10", "bzr": "2026"}
    z.update(w)
    return z


def _baum(rows, cfg=CFG):
    return ET.fromstring(export_destatis_instat_xml(pd.DataFrame(rows), cfg))


def test_je_richtung_eine_meldung_und_partnerid_nur_bei_versendung():
    root = _baum([_zeile(),
                  _zeile(richtung="E", partner_country="PL", country_of_origin="PL",
                         vat_id_recipient="", bundesland="05", transaction_nature="11")])
    decls = root.findall("./Envelope/Declaration")
    assert [d.findtext("flowCode") for d in decls] == ["A", "D"]
    assert all(d.findtext("referencePeriod") == "2026-10" for d in decls)
    assert all(d.findtext("currencyCode") == "EUR" for d in decls)
    eingang, versendung = decls
    assert eingang.find("./Item/partnerId") is None
    item = versendung.find("./Item")
    assert item.findtext("partnerId") == "ATU83164219"
    assert item.findtext("netMass") == "253"            # volle kg, gerundet
    assert item.findtext("regionCode") == "99"           # ausländischer Ursprung
    assert item.findtext("NatureOfTransaction/natureOfTransactionACode") == "1"
    assert item.findtext("NatureOfTransaction/natureOfTransactionBCode") == "1"
    assert root.findtext("./Envelope/numberOfDeclarations") == "2"
    assert root.find("./Envelope/Party[@partyType='PSI']/partyName").text == "Muster & Söhne GmbH"


def test_privatkunde_art_des_geschaefts_12():
    item = _baum([_zeile(transaction_nature="12", vat_id_recipient="QN999999999999")]).find(".//Item")
    assert item.findtext("NatureOfTransaction/natureOfTransactionBCode") == "2"
    assert item.findtext("partnerId") == "QN999999999999"


def test_reihenfolge_der_item_elemente_wie_spezifikation():
    item = _baum([_zeile()]).find(".//Item")
    assert [e.tag for e in item] == ["itemNumber", "CN8", "MSConsDestCode", "countryOfOriginCode", "netMass",
                                     "invoicedAmount", "statisticalValue", "partnerId", "NatureOfTransaction",
                                     "modeOfTransportCode", "regionCode"]


def test_summen_der_meldung():
    decl = _baum([_zeile(net_mass=10, invoiced_amount=100, statistical_value=100),
                  _zeile(commodity_code="34013000", net_mass=5, invoiced_amount=50, statistical_value=50)]
                 ).find(".//Declaration")
    assert (decl.findtext("totalNetMass"), decl.findtext("totalInvoicedAmount")) == ("15", "150")


def test_fehlende_warennummer_bricht_mit_klarer_meldung_ab():
    with pytest.raises(ValueError, match="Warennummer"):
        export_destatis_instat_xml(pd.DataFrame([_zeile(commodity_code="")]), CFG)


def test_versendung_ohne_ustid_bricht_ab():
    with pytest.raises(ValueError, match="USt-IdNr"):
        export_destatis_instat_xml(pd.DataFrame([_zeile(vat_id_recipient="")]), CFG)


def test_nicht_ausgefuellte_vorlagen_einstellung_gilt_als_leer():
    with pytest.raises(ValueError, match="Melder-ID"):
        export_destatis_instat_xml(pd.DataFrame([_zeile()]), dict(CFG, psi_id="{{core_melder_id}}"))
    with pytest.raises(ValueError, match="firma"):
        export_destatis_instat_xml(pd.DataFrame([_zeile()]), dict(CFG, firma="{{core_firma}}"))
