package de.datenmonster.plugins.estatistik.controller;

import de.datenmonster.plugins.estatistik.model.*;
import de.datenmonster.plugins.estatistik.service.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Map;

/**
 * Eigene REST-API des Plugins – direkt aufrufbar oder via Plugin Manager Generic Proxy.
 */
@RestController
@RequestMapping("/api/v1")
public class ApiV1Controller {

    @Autowired private ConnectionService connectionService;
    @Autowired private GeneratorService generatorService;
    @Autowired private ValidatorService validatorService;
    @Autowired private SenderService senderService;
    @Autowired private ProtocolService protocolService;

    @GetMapping("/health")
    public Map<String, Object> health() {
        return Map.of(
            "status", "ok",
            "plugin", "estatistik-core",
            "version", "0.1.0",
            "core_connect", "not_integrated",
            "core_inspector", "not_integrated"
        );
    }

    @PostMapping("/connection-test")
    public Map<String, Object> connectionTest(@RequestBody IntrastatConfig config) {
        return connectionService.test(config);
    }

    @PostMapping("/generate")
    public ResponseEntity<Map<String, Object>> generate(@RequestBody GenerateRequest req) {
        GenerateResponse result = generatorService.generate(req.getConfig(), req.getPositions());
        if (!result.isOk()) {
            return ResponseEntity.badRequest().body(Map.of(
                "ok", false,
                "message", result.getMessage()
            ));
        }
        return ResponseEntity.ok(Map.of(
            "ok", true,
            "format", result.getFormat(),
            "content", result.getContent(),
            "message", result.getMessage(),
            "warnings", result.getWarnings()
        ));
    }

    @PostMapping("/validate")
    public Map<String, Object> validate(@RequestBody Map<String, String> req) {
        String content = req.getOrDefault("content", "");
        String format  = req.getOrDefault("format", "DatML");
        ValidationResult result = validatorService.validate(content, format);
        return Map.of(
            "valid",    result.isValid(),
            "errors",   result.getErrors(),
            "warnings", result.getWarnings()
        );
    }

    /**
     * Versand-Endpunkt.
     * v0.1: Testmodus simuliert Versand. Produktionsmodus deaktiviert.
     */
    @PostMapping("/send")
    public ResponseEntity<Map<String, Object>> send(@RequestBody Map<String, Object> req) {
        @SuppressWarnings("unchecked")
        Map<String, Object> configMap = (Map<String, Object>) req.getOrDefault("config", Map.of());
        String content = (String) req.getOrDefault("content", "");
        String format  = (String) req.getOrDefault("format", "DatML");

        IntrastatConfig config = new IntrastatConfig();
        config.setMode((String) configMap.getOrDefault("mode", "test"));
        config.setSenderId((String) configMap.get("sender_id"));
        config.setCoreUser((String) configMap.get("core_user"));
        config.setCorePassword((String) configMap.get("core_password"));

        if (content.isBlank()) {
            return ResponseEntity.badRequest().body(Map.of(
                "ok", false, "message", "Kein Inhalt zum Senden übergeben"
            ));
        }

        SendResult result = senderService.send(config, content, format);
        return ResponseEntity.ok(Map.of(
            "ok",          result.isOk(),
            "entry_stamp", result.getEntryStamp(),
            "message",     result.getMessage(),
            "disabled",    result.isDisabled()
        ));
    }

    @GetMapping("/protocol/{entryStamp}")
    public ResponseEntity<Object> protocol(@PathVariable String entryStamp) {
        return protocolService.findByEntryStamp(entryStamp)
            .<ResponseEntity<Object>>map(ResponseEntity::ok)
            .orElse(ResponseEntity.notFound().build());
    }

    @GetMapping("/protocol")
    public List<ProtocolEntry> allProtocol() {
        return List.copyOf(protocolService.findAll());
    }
}
