package de.datenmonster.plugins.estatistik.service;

import de.datenmonster.plugins.estatistik.model.IntrastatConfig;
import de.datenmonster.plugins.estatistik.model.SendResult;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class SenderService {

    private static final Logger log = LoggerFactory.getLogger(SenderService.class);

    /**
     * Sendet eine Meldung via CORE.connect.
     *
     * v0.1:
     *   - Testmodus: simuliert Versand, gibt Test-EntryStamp zurück
     *   - Produktionsmodus: DEAKTIVIERT (CORE.connect noch nicht integriert)
     *
     * v0.2: CORE.connect Integration für Produktivversand.
     */
    public SendResult send(IntrastatConfig config, String content, String format) {
        if (!config.isTestMode()) {
            log.warn("Produktivversand angefordert aber nicht implementiert (v0.1)");
            return SendResult.disabled(
                "Produktivversand via CORE.connect ist in v0.1 deaktiviert. " +
                "Bitte Betriebsmodus auf 'test' setzen."
            );
        }

        // Testmodus: simulierter Versand
        String entryStamp = "TEST-" + config.getSenderId() + "-"
            + config.getPeriod() + "-" + System.currentTimeMillis();

        log.info("Testmodus: Meldung simuliert (nicht gesendet). entryStamp={}", entryStamp);

        // TODO v0.2: CORE.connect aufrufen:
        // CoreConnect core = new CoreConnect(config.getCoreUser(), config.getCorePassword());
        // SubmitResult result = core.submit(content, format);
        // return SendResult.success(result.getEntryStamp(), result.getMessage());

        return SendResult.testSuccess(
            entryStamp,
            "Testmodus: Meldung erfolgreich simuliert. Kein Versand an eSTATISTIK erfolgt."
        );
    }
}
