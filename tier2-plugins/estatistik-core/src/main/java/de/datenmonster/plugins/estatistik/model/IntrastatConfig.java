package de.datenmonster.plugins.estatistik.model;

import com.fasterxml.jackson.annotation.JsonProperty;

/**
 * Konfiguration für eine Intrastat-Meldung.
 * Wird aus dem Datenmonster query_config / target_config befüllt.
 * Secrets (core_password) niemals ins Manifest/Log schreiben.
 */
public class IntrastatConfig {

    /** "test" oder "production" */
    private String mode = "test";

    @JsonProperty("core_user")
    private String coreUser;

    @JsonProperty("core_password")
    private String corePassword;

    @JsonProperty("sender_id")
    private String senderId;

    @JsonProperty("reporter_id")
    private String reporterId;

    /** "E" = Eingang, "V" = Versendung */
    private String direction = "V";

    /** Format: JJJJMM, z.B. "202601" */
    private String period;

    @JsonProperty("customs_number")
    private String customsNumber;

    @JsonProperty("company_id")
    private String companyId;

    // ── Getter/Setter ─────────────────────────────────────────────────────────

    public String getMode() { return mode; }
    public void setMode(String mode) { this.mode = mode; }

    public String getCoreUser() { return coreUser; }
    public void setCoreUser(String coreUser) { this.coreUser = coreUser; }

    public String getCorePassword() { return corePassword; }
    public void setCorePassword(String corePassword) { this.corePassword = corePassword; }

    public String getSenderId() { return senderId; }
    public void setSenderId(String senderId) { this.senderId = senderId; }

    public String getReporterId() { return reporterId; }
    public void setReporterId(String reporterId) { this.reporterId = reporterId; }

    public String getDirection() { return direction; }
    public void setDirection(String direction) { this.direction = direction; }

    public String getPeriod() { return period; }
    public void setPeriod(String period) { this.period = period; }

    public String getCustomsNumber() { return customsNumber; }
    public void setCustomsNumber(String customsNumber) { this.customsNumber = customsNumber; }

    public String getCompanyId() { return companyId; }
    public void setCompanyId(String companyId) { this.companyId = companyId; }

    public boolean isTestMode() { return "test".equalsIgnoreCase(mode); }
}
