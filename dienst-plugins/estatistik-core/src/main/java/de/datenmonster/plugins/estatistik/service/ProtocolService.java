package de.datenmonster.plugins.estatistik.service;

import de.datenmonster.plugins.estatistik.model.*;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

/**
 * In-memory Versandprotokoll.
 * v0.1: ConcurrentHashMap – reicht für Entwicklung und Tests.
 * v0.2: Persistierung in DB oder Datei ergänzen.
 */
@Service
public class ProtocolService {

    private final Map<String, ProtocolEntry> entries = new ConcurrentHashMap<>();

    public void log(String entryStamp, IntrastatConfig config,
                    GenerateResponse generated, ValidationResult validation, SendResult send) {
        ProtocolEntry entry = new ProtocolEntry();
        entry.setEntryStamp(entryStamp);
        entry.setTimestamp(Instant.now());
        entry.setMode(config.getMode());
        entry.setSenderId(config.getSenderId());
        entry.setDirection(config.getDirection());
        entry.setPeriod(config.getPeriod());
        entry.setFormat(generated != null ? generated.getFormat() : null);
        entry.setSent(send.isOk());
        entry.setSendMessage(send.getMessage());
        entry.setValidationWarnings(validation != null ? validation.getWarnings() : List.of());
        entries.put(entryStamp, entry);
    }

    public Optional<ProtocolEntry> findByEntryStamp(String entryStamp) {
        return Optional.ofNullable(entries.get(entryStamp));
    }

    public Collection<ProtocolEntry> findAll() {
        return entries.values();
    }
}
