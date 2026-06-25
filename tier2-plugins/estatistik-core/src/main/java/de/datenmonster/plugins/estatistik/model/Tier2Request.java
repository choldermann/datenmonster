package de.datenmonster.plugins.estatistik.model;

import java.util.List;
import java.util.Map;

/** Eingehende Anfrage im Datenmonster Tier-2 Protokoll. */
public class Tier2Request {
    private Map<String, Object> config;
    private List<Map<String, Object>> rows;

    public Map<String, Object> getConfig() { return config; }
    public void setConfig(Map<String, Object> config) { this.config = config; }

    public List<Map<String, Object>> getRows() { return rows; }
    public void setRows(List<Map<String, Object>> rows) { this.rows = rows; }
}
