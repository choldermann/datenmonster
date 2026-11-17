-- Views für die büro+-Exporttabellen (Datenmonster-Cockpits).
-- WICHTIG: büro+ vergibt Vorgangs-IDs (VogID) neu – dieselbe VogID kann im Archiv und in der
-- Übersicht zu zwei verschiedenen Belegen gehören. Eindeutig ist nur (Quelle, VogID).
-- Positionen deshalb immer mit dem Kopf aus DERSELBEN Tabelle verbinden.
GO
CREATE OR ALTER VIEW dbo.vVorgang AS
SELECT 'Archiv' AS Quelle, a.* FROM dbo.VorgangArchiv a
UNION ALL
SELECT 'Übersicht' AS Quelle, v.* FROM dbo.Vorgang v
WHERE NOT EXISTS (SELECT 1 FROM dbo.VorgangArchiv a WHERE a.VogBelegNr = v.VogBelegNr AND a.VogArt = v.VogArt)
GO
CREATE OR ALTER VIEW dbo.vVorgangPosition AS
SELECT k.Quelle, p.*,
       CAST(p.EPrNt * p.BuchMge * p.EPreisFak AS decimal(18,2)) AS NettoPos,
       CAST(p.EEkRoh * p.BuchMge * p.EPreisFak AS decimal(18,2)) AS EkPos,
       CAST(p.EPrNt * p.BuchMge * p.EPreisFak - p.EEkRoh * p.BuchMge * p.EPreisFak AS decimal(18,2)) AS RohertragPos
FROM (SELECT 'Archiv' AS PQuelle, * FROM dbo.VorgangPositionArchiv
      UNION ALL
      SELECT 'Übersicht' AS PQuelle, * FROM dbo.VorgangPosition) p
JOIN dbo.vVorgang k ON k.VogID = p.VogID AND k.Quelle = p.PQuelle
GO
