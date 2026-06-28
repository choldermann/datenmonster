import { useState, useEffect, useCallback, useRef } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useProject } from "../context/ProjectContext";
import api from "../api/client";
import { WIDGET_TYPES, S } from "../components/report/constants";
import ReportHeader from "../components/report/ReportHeader";
import ReportToolbar from "../components/report/ReportToolbar";
import ReportCanvas from "../components/report/ReportCanvas";
import ReportFilterBar from "../components/report/ReportFilterBar";
import WidgetConfigPanel from "../components/report/WidgetConfigPanel";

function genId() { return Math.random().toString(36).slice(2, 9); }

export default function ReportEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { activeProject } = useProject();
  const projectId = activeProject?.id ?? null;

  const [name, setName] = useState("Neuer Report");
  const [widgets, setWidgets] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [preview, setPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [datasets, setDatasets] = useState([]);
  const [widgetData, setWidgetData] = useState({});
  const [filters, setFilters] = useState({});
  const loadingRef = useRef({});

  // ── Laden ────────────────────────────────────────────────────────────────────
  useEffect(() => {
    const p = projectId ? `?project_id=${projectId}` : "";
    api.get(`/api/datasets/${p}`).then(({ data }) => setDatasets(data || []));

    if (id && id !== "new") {
      api.get(`/api/reports/${id}`).then(({ data }) => {
        setName(data.name || "Report");
        setWidgets(data.widgets || []);
      });
    }
  }, [id, projectId]);

  // ── Daten laden wenn Widget-Config oder Filter sich ändern ───────────────────
  const loadWidgetData = useCallback(async (widget, activeFilters) => {
    if (!widget.config?.dataset_id && !widget.config?.sql) return;
    const key = widget.id;
    if (loadingRef.current[key]) return;
    loadingRef.current[key] = true;

    try {
      const params = {
        widget_id: widget.id,
        dataset_id: widget.config.dataset_id,
        sql: widget.config.sql,
        connection_id: widget.config.connection_id,
        filters: JSON.stringify(activeFilters || {}),
        filter_fields: JSON.stringify(widget.config.filter_fields || []),
      };
      const { data } = await api.post("/api/reports/widget-data", params);
      setWidgetData(prev => ({ ...prev, [key]: { data: data.rows || [] } }));

      // Vergleichszeitraum
      if (widget.config.show_compare && activeFilters?.date_from) {
        const compareFilters = buildCompareFilters(activeFilters);
        if (compareFilters) {
          const { data: cdata } = await api.post("/api/reports/widget-data", { ...params, filters: JSON.stringify(compareFilters) });
          setWidgetData(prev => ({ ...prev, [key]: { ...prev[key], compareData: cdata.rows || [] } }));
        }
      }
    } catch (e) {
      console.error("Widget data error:", e);
    } finally {
      loadingRef.current[key] = false;
    }
  }, []);

  const buildCompareFilters = (f) => {
    if (!f?.date_from || !f?.date_to) return null;
    const from = new Date(f.date_from);
    const to = new Date(f.date_to);
    const diff = to - from;
    return {
      ...f,
      date_from: new Date(from - diff).toISOString().slice(0, 10),
      date_to: new Date(to - diff).toISOString().slice(0, 10),
    };
  };

  const refreshAllWidgets = useCallback(() => {
    widgets.forEach(w => loadWidgetData(w, filters));
  }, [widgets, filters, loadWidgetData]);

  useEffect(() => { refreshAllWidgets(); }, [widgets.length, filters]);

  // ── Widget Helpers ────────────────────────────────────────────────────────────
  const addWidget = (type, x = 0, y = 0) => {
    const wt = WIDGET_TYPES.find(w => w.type === type);
    const widget = {
      id: genId(), type, title: wt?.label || type,
      x, y, w: wt?.defaultW || 4, h: wt?.defaultH || 3,
      config: {},
    };
    setWidgets(prev => [...prev, widget]);
    setSelectedId(widget.id);
  };

  const updateWidget = useCallback((updated) => {
    setWidgets(prev => prev.map(w => w.id === updated.id ? updated : w));
    // Daten neu laden wenn Datenquelle geändert
    setTimeout(() => loadWidgetData(updated, filters), 100);
  }, [filters, loadWidgetData]);

  const removeWidget = useCallback((wid) => {
    setWidgets(prev => prev.filter(w => w.id !== wid));
    setSelectedId(null);
  }, []);

  const updatePosition = useCallback((wid, changes) => {
    setWidgets(prev => prev.map(w => w.id === wid ? { ...w, ...changes } : w));
  }, []);

  // ── Speichern ─────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = { name, widgets, project_id: projectId };
      if (id && id !== "new") {
        await api.put(`/api/reports/${id}`, payload);
      } else {
        const { data } = await api.post("/api/reports/", payload);
        navigate(`/reports/${data.id}`, { replace: true });
      }
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  const selectedWidget = widgets.find(w => w.id === selectedId);

  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", backgroundColor: S.bgMain, color: S.textMain }}>
      <ReportHeader
        name={name} onNameChange={setName}
        onBack={() => navigate("/dashboard", { state: { tab: "reports" } })}
        onSave={handleSave} saving={saving}
        preview={preview} onTogglePreview={() => setPreview(v => !v)}
        widgetCount={widgets.length}
        reportId={id && id !== "new" ? parseInt(id) : null}
      />

      {/* Filter Bar – nur wenn Filter definiert */}
      <ReportFilterBar
        widgets={widgets}
        filters={filters}
        onChange={setFilters}
        onRefresh={refreshAllWidgets}
      />

      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {!preview && <ReportToolbar onAddWidget={addWidget} />}

        <ReportCanvas
          widgets={widgets}
          widgetData={widgetData}
          preview={preview}
          selectedId={selectedId}
          onSelect={setSelectedId}
          onPositionChange={updatePosition}
          onDrop={addWidget}
        />

        {!preview && selectedWidget && (
          <WidgetConfigPanel
            widget={selectedWidget}
            datasets={datasets}
            onUpdate={updateWidget}
            onRemove={removeWidget}
            onClose={() => setSelectedId(null)}
          />
        )}
      </div>
    </div>
  );
}
