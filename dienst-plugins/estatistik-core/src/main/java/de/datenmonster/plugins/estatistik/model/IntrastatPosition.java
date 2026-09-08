package de.datenmonster.plugins.estatistik.model;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Eine Intrastat-Meldungsposition.
 * Feldnamen entsprechen dem Datenmonster-Mapping (snake_case).
 */
public class IntrastatPosition {

    @JsonProperty("position_number")
    private String positionNumber;

    /** CN8-Warennummer (8-stellig) */
    @JsonProperty("commodity_code")
    private String commodityCode;

    /** Ursprungsland (ISO 3166-1 Alpha-2) – nur bei Eingang relevant */
    @JsonProperty("country_of_origin")
    private String countryOfOrigin;

    /** Partnerland (ISO 3166-1 Alpha-2) */
    @JsonProperty("partner_country")
    private String partnerCountry;

    /** Geschäftsart (1-stellig oder 2-stellig) */
    @JsonProperty("transaction_nature")
    private String transactionNature;

    /** Beförderungsweg (1-stellig) */
    @JsonProperty("mode_of_transport")
    private String modeOfTransport;

    /** Eigengewicht in kg (ganzzahlig) */
    @JsonProperty("net_mass")
    private String netMass;

    /** Statistischer Wert in EUR (ganzzahlig) */
    @JsonProperty("statistical_value")
    private String statisticalValue;

    /** Rechnungsbetrag in EUR */
    @JsonProperty("invoiced_amount")
    private String invoicedAmount;

    /** Besondere Maßeinheit (optional, z.B. Stück) */
    @JsonProperty("quantity_unit")
    private String quantityUnit;

    // ── Getter/Setter ─────────────────────────────────────────────────────────

    public String getPositionNumber() { return positionNumber; }
    public void setPositionNumber(String v) { this.positionNumber = v; }

    public String getCommodityCode() { return commodityCode; }
    public void setCommodityCode(String v) { this.commodityCode = v; }

    public String getCountryOfOrigin() { return countryOfOrigin; }
    public void setCountryOfOrigin(String v) { this.countryOfOrigin = v; }

    public String getPartnerCountry() { return partnerCountry; }
    public void setPartnerCountry(String v) { this.partnerCountry = v; }

    public String getTransactionNature() { return transactionNature; }
    public void setTransactionNature(String v) { this.transactionNature = v; }

    public String getModeOfTransport() { return modeOfTransport; }
    public void setModeOfTransport(String v) { this.modeOfTransport = v; }

    public String getNetMass() { return netMass; }
    public void setNetMass(String v) { this.netMass = v; }

    public String getStatisticalValue() { return statisticalValue; }
    public void setStatisticalValue(String v) { this.statisticalValue = v; }

    public String getInvoicedAmount() { return invoicedAmount; }
    public void setInvoicedAmount(String v) { this.invoicedAmount = v; }

    public String getQuantityUnit() { return quantityUnit; }
    public void setQuantityUnit(String v) { this.quantityUnit = v; }
}
