package de.datenmonster.plugins.estatistik.service;

import de.datenmonster.plugins.estatistik.model.GenerateResponse;
import de.datenmonster.plugins.estatistik.model.IntrastatConfig;
import de.datenmonster.plugins.estatistik.model.IntrastatPosition;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.util.List;

@Service
public class GeneratorService {

    /**
     * Erzeugt eine Intrastat-Meldung als DatML/XML-Stub.
     * v0.1: Template-basierte Erzeugung ohne CORE-Bibliotheken.
     * v0.2: Ersatz durch CORE.connect DatML-Builder.
     */
    public GenerateResponse generate(IntrastatConfig config, List<IntrastatPosition> positions) {
        if (positions == null || positions.isEmpty()) {
            return new GenerateResponse(false, null, null,
                "Keine Positionen übergeben", List.of());
        }

        String content = buildDatML(config, positions);
        return new GenerateResponse(
            true,
            "DatML",
            content,
            "Dummy-DatML erzeugt (v0.1 – CORE.connect ausstehend)",
            List.of("STUB: Erzeugung noch nicht via CORE.connect validiert")
        );
    }

    private String buildDatML(IntrastatConfig config, List<IntrastatPosition> positions) {
        String today = LocalDate.now().toString();
        StringBuilder sb = new StringBuilder();
        sb.append("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n");
        sb.append("<!-- STUB v0.1 – CORE.connect Integration ausstehend -->\n");
        sb.append("<INSTAT xmlns=\"http://www.destatis.de/schema/intrastat/head/1\">\n");
        sb.append("  <Envelope>\n");
        sb.append("    <envelopeId>").append(safe(config.getSenderId())).append("-")
          .append(config.getPeriod()).append("</envelopeId>\n");
        sb.append("    <DateTime><date>").append(today).append("</date></DateTime>\n");
        sb.append("    <Party partyType=\"PSI\" partyRole=\"sender\">\n");
        sb.append("      <partyId>").append(safe(config.getSenderId())).append("</partyId>\n");
        sb.append("    </Party>\n");
        sb.append("    <Party partyType=\"CC\" partyRole=\"receiver\">\n");
        sb.append("      <partyId>DE-DESTATIS</partyId>\n");
        sb.append("    </Party>\n");
        sb.append("    <Declaration>\n");
        sb.append("      <declarationId>").append(safe(config.getSenderId())).append("-")
          .append(config.getPeriod()).append("-").append(config.getDirection()).append("</declarationId>\n");
        sb.append("      <referencePeriod>").append(safe(config.getPeriod())).append("</referencePeriod>\n");
        sb.append("      <PSIId>").append(safe(config.getReporterId())).append("</PSIId>\n");
        sb.append("      <Function><functionCode>O</functionCode></Function>\n");
        sb.append("      <declarationTypeCode>").append(safe(config.getDirection()))
          .append("</declarationTypeCode>\n");

        for (int i = 0; i < positions.size(); i++) {
            IntrastatPosition p = positions.get(i);
            sb.append("      <Item>\n");
            sb.append("        <itemNumber>").append(i + 1).append("</itemNumber>\n");
            sb.append("        <CN8><CN8Code>").append(safe(p.getCommodityCode()))
              .append("</CN8Code></CN8>\n");
            if ("E".equals(config.getDirection()) && p.getCountryOfOrigin() != null) {
                sb.append("        <countryOfOriginCode>").append(safe(p.getCountryOfOrigin()))
                  .append("</countryOfOriginCode>\n");
            }
            sb.append("        <MSConsDestCode>").append(safe(p.getPartnerCountry()))
              .append("</MSConsDestCode>\n");
            sb.append("        <natureOfTransactionACode>")
              .append(safe(p.getTransactionNature())).append("</natureOfTransactionACode>\n");
            sb.append("        <modeOfTransportCode>")
              .append(safe(p.getModeOfTransport())).append("</modeOfTransportCode>\n");
            sb.append("        <netMass>").append(safe(p.getNetMass())).append("</netMass>\n");
            sb.append("        <invoicedAmount>").append(safe(p.getInvoicedAmount()))
              .append("</invoicedAmount>\n");
            sb.append("        <statisticalValue>").append(safe(p.getStatisticalValue()))
              .append("</statisticalValue>\n");
            if (p.getQuantityUnit() != null && !p.getQuantityUnit().isBlank()) {
                sb.append("        <quantityInSU>").append(safe(p.getQuantityUnit()))
                  .append("</quantityInSU>\n");
            }
            sb.append("      </Item>\n");
        }

        sb.append("    </Declaration>\n");
        sb.append("  </Envelope>\n");
        sb.append("</INSTAT>\n");
        return sb.toString();
    }

    private String safe(String s) {
        return s != null ? s : "";
    }
}
