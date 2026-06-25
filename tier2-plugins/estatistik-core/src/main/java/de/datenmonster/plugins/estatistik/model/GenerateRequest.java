package de.datenmonster.plugins.estatistik.model;

import java.util.List;

/** Anfrage an POST /api/v1/generate */
public class GenerateRequest {
    private IntrastatConfig config;
    private List<IntrastatPosition> positions;

    public IntrastatConfig getConfig() { return config; }
    public void setConfig(IntrastatConfig config) { this.config = config; }

    public List<IntrastatPosition> getPositions() { return positions; }
    public void setPositions(List<IntrastatPosition> positions) { this.positions = positions; }
}
