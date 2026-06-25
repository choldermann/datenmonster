package de.datenmonster.plugins.estatistik.service;

import de.datenmonster.plugins.estatistik.model.IntrastatConfig;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

@Service
public class ConnectionService {

    /**
     * Prüft die Konfiguration auf Vollständigkeit.
     * v0.1: nur lokale Validierung, noch kein CORE.connect-Aufruf.
     */
    public Map<String, Object> test(IntrastatConfig config) {
        List<String> missing = new ArrayList<>();

        if (blank(config.getCoreUser()))  missing.add("core_user");
        if (blank(config.getSenderId()))  missing.add("sender_id");
        if (blank(config.getReporterId())) missing.add("reporter_id");
        if (blank(config.getPeriod()))    missing.add("period");
        if (blank(config.getDirection())) missing.add("direction");

        if (!missing.isEmpty()) {
            return Map.of(
                "ok", false,
                "message", "Fehlende Pflichtfelder: " + String.join(", ", missing)
            );
        }

        if (!"E".equals(config.getDirection()) && !"V".equals(config.getDirection())) {
            return Map.of("ok", false, "message", "direction muss 'E' oder 'V' sein");
        }

        if (!config.getPeriod().matches("\\d{6}")) {
            return Map.of("ok", false, "message", "period muss Format JJJJMM haben (z.B. 202601)");
        }

        String modeInfo = config.isTestMode()
            ? "Testmodus aktiv – kein Produktivversand"
            : "Produktionsmodus – CORE.connect Integration ausstehend (v0.1)";

        // TODO v0.2: CORE.connect Verbindungstest via Java-Bibliothek
        return Map.of(
            "ok", true,
            "message", "Konfiguration vollständig. " + modeInfo,
            "mode", config.getMode(),
            "sender_id", config.getSenderId(),
            "period", config.getPeriod(),
            "direction", config.getDirection()
        );
    }

    private boolean blank(String s) {
        return s == null || s.isBlank();
    }
}
