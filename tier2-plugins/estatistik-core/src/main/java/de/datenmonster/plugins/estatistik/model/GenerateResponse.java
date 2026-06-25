package de.datenmonster.plugins.estatistik.model;

import java.util.List;

public class GenerateResponse {
    private boolean ok;
    private String format;   // "DatML" oder "XML"
    private String content;  // erzeugter Inhalt
    private String message;
    private List<String> warnings;

    public GenerateResponse() {}

    public GenerateResponse(boolean ok, String format, String content, String message, List<String> warnings) {
        this.ok = ok;
        this.format = format;
        this.content = content;
        this.message = message;
        this.warnings = warnings;
    }

    public boolean isOk() { return ok; }
    public void setOk(boolean ok) { this.ok = ok; }

    public String getFormat() { return format; }
    public void setFormat(String format) { this.format = format; }

    public String getContent() { return content; }
    public void setContent(String content) { this.content = content; }

    public String getMessage() { return message; }
    public void setMessage(String message) { this.message = message; }

    public List<String> getWarnings() { return warnings; }
    public void setWarnings(List<String> warnings) { this.warnings = warnings; }
}
