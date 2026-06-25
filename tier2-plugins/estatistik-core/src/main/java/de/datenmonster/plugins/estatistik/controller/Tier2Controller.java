package de.datenmonster.plugins.estatistik.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import de.datenmonster.plugins.estatistik.model.*;
import de.datenmonster.plugins.estatistik.service.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * Implementiert das Datenmonster Tier-2 Plugin-Protokoll.
 * Wird durch den Plugin Manager via Proxy aufgerufen.
 */
@RestController
public class Tier2Controller {

    @Autowired private ConnectionService connectionService;
    @Autowired private GeneratorService generatorService;
    @Autowired private ValidatorService validatorService;
    @Autowired private SenderService senderService;
    @Autowired private ProtocolService protocolService;
    @Autowired private ObjectMapper objectMapper;

    private static final List<String> INTRASTAT_FIELDS = List.of(
        "position_number", "commodity_code", "country_of_origin",
        "partner_country", "transaction_nature", "mode_of_transport",
        "net_mass", "statistical_value", "invoiced_amount", "quantity_unit"
    );

    @GetMapping("/health")
    public Map<String, Object> health() {
        return Map.of("status", "ok", "plugin", "estatistik-core", "version", "0.1.0");
    }

    @GetMapping("/manifest")
    public Map<String, Object> manifest() {
        return Map.of(
            "id", "estatistik-core",
            "name", "eSTATISTIK.core / Intrastat",
            "version", "0.1.0",
            "capabilities", List.of("target"),
            "target_type_id", "estatistik_intrastat",
            "target_type_label", "eSTATISTIK Intrastat"
        );
    }

    @PostMapping("/test")
    public Map<String, Object> test(@RequestBody Tier2Request req) {
        IntrastatConfig config = toConfig(req.getConfig());
        return connectionService.test(config);
    }

    @PostMapping("/schema")
    public Map<String, Object> schema(@RequestBody Tier2Request req) {
        return Map.of("columns", INTRASTAT_FIELDS);
    }

    @PostMapping("/fetch")
    public Map<String, Object> fetch(@RequestBody Tier2Request req) {
        return Map.of(
            "rows", List.of(),
            "message", "eSTATISTIK.core ist ein Ziel-Plugin – kein Datenabruf möglich"
        );
    }

    @PostMapping("/write")
    public Map<String, Object> write(@RequestBody Tier2Request req) {
        IntrastatConfig config = toConfig(req.getConfig());
        List<IntrastatPosition> positions = toPositions(req.getRows());

        GenerateResponse generated = generatorService.generate(config, positions);
        if (!generated.isOk()) {
            return Map.of("written", 0, "errors", List.of(generated.getMessage()));
        }

        ValidationResult validation = validatorService.validate(generated.getContent(), generated.getFormat());
        if (!validation.isValid()) {
            return Map.of("written", 0, "errors", validation.getErrors(),
                "warnings", validation.getWarnings());
        }

        SendResult send = senderService.send(config, generated.getContent(), generated.getFormat());
        protocolService.log(send.getEntryStamp(), config, generated, validation, send);

        return Map.of(
            "written", send.isOk() ? positions.size() : 0,
            "errors", send.isOk() ? List.of() : List.of(send.getMessage()),
            "warnings", validation.getWarnings(),
            "entry_stamp", send.getEntryStamp(),
            "mode", config.getMode()
        );
    }

    // ── Hilfsmethoden ─────────────────────────────────────────────────────────

    private IntrastatConfig toConfig(Map<String, Object> map) {
        return objectMapper.convertValue(map != null ? map : Map.of(), IntrastatConfig.class);
    }

    private List<IntrastatPosition> toPositions(List<Map<String, Object>> rows) {
        if (rows == null) return List.of();
        return rows.stream()
            .map(r -> objectMapper.convertValue(r, IntrastatPosition.class))
            .toList();
    }
}
