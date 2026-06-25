package de.datenmonster.plugins.estatistik.model;

import java.time.Instant;
import java.util.List;

/** Ein Eintrag im Versandprotokoll (in-memory, v0.1). */
public class ProtocolEntry {
    private String entryStamp;
    private Instant timestamp;
    private String mode;
    private String senderId;
    private String direction;
    private String period;
    private int positionCount;
    private String format;
    private boolean sent;
    private String sendMessage;
    private List<String> validationWarnings;

    public ProtocolEntry() {}

    // ── Getter/Setter ─────────────────────────────────────────────────────────

    public String getEntryStamp() { return entryStamp; }
    public void setEntryStamp(String v) { this.entryStamp = v; }

    public Instant getTimestamp() { return timestamp; }
    public void setTimestamp(Instant v) { this.timestamp = v; }

    public String getMode() { return mode; }
    public void setMode(String v) { this.mode = v; }

    public String getSenderId() { return senderId; }
    public void setSenderId(String v) { this.senderId = v; }

    public String getDirection() { return direction; }
    public void setDirection(String v) { this.direction = v; }

    public String getPeriod() { return period; }
    public void setPeriod(String v) { this.period = v; }

    public int getPositionCount() { return positionCount; }
    public void setPositionCount(int v) { this.positionCount = v; }

    public String getFormat() { return format; }
    public void setFormat(String v) { this.format = v; }

    public boolean isSent() { return sent; }
    public void setSent(boolean v) { this.sent = v; }

    public String getSendMessage() { return sendMessage; }
    public void setSendMessage(String v) { this.sendMessage = v; }

    public List<String> getValidationWarnings() { return validationWarnings; }
    public void setValidationWarnings(List<String> v) { this.validationWarnings = v; }
}
