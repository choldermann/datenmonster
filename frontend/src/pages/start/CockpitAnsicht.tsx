import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import api, { fehlerText } from "../../api/client";
import { useAuth } from "../../context/AuthContext";
import FormRunner from "../FormRunner";
import PortalRunner from "../PortalRunner";
import { S } from "./StartLayout";

/** Ein Cockpit innerhalb der Händler-Ansicht. Editoren laufen über den FormRunner,
 *  Portal-Benutzer über den PortalRunner (der braucht den Slug statt der ID). */
export default function CockpitAnsicht() {
  const { id } = useParams();
  const { user } = useAuth();
  const portal = !!user?.is_portal_only;
  const [slug, setSlug] = useState(null);
  const [fehler, setFehler] = useState(null);

  useEffect(() => {
    if (!portal) return;
    api.get("/api/start/cockpits")
      .then(({ data }) => {
        const c = (data || []).find((x) => String(x.id) === String(id));
        if (c?.slug) setSlug(c.slug);
        else setFehler("Dieses Cockpit ist für Sie nicht freigegeben.");
      })
      .catch((e) => setFehler(fehlerText(e)));
  }, [id, portal]);

  if (fehler) return <p style={{ color: "var(--err)" }}>{fehler}</p>;
  if (!portal) return <FormRunner key={id} formId={id} eingebettet="seite" />;
  if (!slug) return <span style={{ color: S.textDim }}>Lädt…</span>;
  return <PortalRunner key={slug} slug={slug} eingebettet="seite" />;
}
