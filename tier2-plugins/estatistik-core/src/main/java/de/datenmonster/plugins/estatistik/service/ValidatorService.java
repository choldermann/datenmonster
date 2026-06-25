package de.datenmonster.plugins.estatistik.service;

import de.datenmonster.plugins.estatistik.model.ValidationResult;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

@Service
public class ValidatorService {

    /**
     * Validiert eine erzeugte Meldung.
     * v0.1: Nur Basis-Checks (nicht leer, XML-Header vorhanden).
     * v0.2: Vollständige Validierung via CORE.inspector.
     */
    public ValidationResult validate(String content, String format) {
        List<String> errors = new ArrayList<>();
        List<String> warnings = new ArrayList<>();

        warnings.add("STUB v0.1: Vollständige Validierung via CORE.inspector ausstehend");

        if (content == null || content.isBlank()) {
            errors.add("Kein Inhalt zur Validierung vorhanden");
            return new ValidationResult(false, errors, warnings);
        }

        if (!content.contains("<?xml")) {
            errors.add("Kein gültiger XML-Header gefunden");
        }

        if (!content.contains("<INSTAT")) {
            errors.add("Kein INSTAT-Wurzelelement gefunden");
        }

        if (!content.contains("<Item>")) {
            warnings.add("Keine Positionen (<Item>) im Dokument");
        }

        // TODO v0.2: CORE.inspector aufrufen:
        // CoreInspector inspector = new CoreInspector(config);
        // InspectionResult result = inspector.validate(content);

        return new ValidationResult(errors.isEmpty(), errors, warnings);
    }
}
