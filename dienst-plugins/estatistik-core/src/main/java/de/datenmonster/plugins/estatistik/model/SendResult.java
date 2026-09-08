package de.datenmonster.plugins.estatistik.model;

public class SendResult {
    private boolean ok;
    private String entryStamp;
    private String message;
    private boolean disabled;

    private SendResult() {}

    public static SendResult testSuccess(String entryStamp, String message) {
        SendResult r = new SendResult();
        r.ok = true; r.entryStamp = entryStamp; r.message = message;
        return r;
    }

    public static SendResult disabled(String message) {
        SendResult r = new SendResult();
        r.ok = false; r.disabled = true; r.message = message;
        r.entryStamp = "DISABLED-" + System.currentTimeMillis();
        return r;
    }

    public static SendResult failure(String message) {
        SendResult r = new SendResult();
        r.ok = false; r.message = message;
        r.entryStamp = "ERROR-" + System.currentTimeMillis();
        return r;
    }

    public boolean isOk() { return ok; }
    public String getEntryStamp() { return entryStamp; }
    public String getMessage() { return message; }
    public boolean isDisabled() { return disabled; }
}
