import { useState, useEffect, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import SmartMappingModal from "../components/mapping/SmartMappingModal";
import { useNavigate, useParams } from "react-router-dom";
import { useProject } from "../context/ProjectContext";
import { ArrowLeft, Calculator, Check, Database, Download, Eye, FileText, Filter, GitBranch, Globe, GripVertical, Layers, Loader2, Pencil, Play, Plus, Save, Search, Sparkles, Trash2, X } from "lucide-react";
import api from "../api/client";
import XmlTemplateEditor from "../components/XmlTemplateEditor";
import TransformNode, { TRANSFORM_TYPES, defaultConfig } from "../components/TransformNode";

import { S, TRANSFORMER_TYPES, JOIN_TYPES, JOIN_COLOR, AGG_COLOR, SQL_NODE_COLOR, typeColor, TARGET_TYPES, TARGET_TYPE_COLORS } from "../components/mapping/constants";
import SvgOverlay from "../components/mapping/SvgOverlay";
import { TransformerEditor, JoinEditor } from "../components/mapping/TransformerEditor";
import { FilterEditor, SortEditor, TypeConvertEditor, CAST_COLOR } from "../components/mapping/FilterSortEditor";
import { DatasetNode, DatasetPreviewTable } from "../components/mapping/DatasetNode";
import ConstantNode from "../components/mapping/ConstantNode";
import SqlNode from "../components/mapping/SqlNode";
import AggNode from "../components/mapping/AggNode";
import RestNode, { REST_NODE_COLOR } from "../components/mapping/RestNode";
import LookupNode, { LOOKUP_COLOR } from "../components/mapping/LookupNode";
import CalcNode, { CALC_COLOR } from "../components/mapping/CalcNode";
import SwitchNode, { SWITCH_COLOR } from "../components/mapping/SwitchNode";
import PreviewPanel from "../components/mapping/PreviewPanel";
import { ExportModal, ContextMenu, TargetConfig, TargetAddField } from "../components/mapping/ExportModal";
import { FieldPickerModal, TargetConfigModal } from "../components/mapping/Modals";

export default function MappingEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { activeProject } = useProject();
  const projectId = activeProject?.id ?? null;
  const canEdit = !activeProject || activeProject.role !== "viewer";

  const [name, setName] = useState("Neues Mapping");
  const [saving, setSaving] = useState(false);
  const [showJoinList, setShowJoinList] = useState(false);
  const [allDatasets, setAllDatasets] = useState([]);
  const [targetColumnTypes, setTargetColumnTypes] = useState({});
  const [dbConnections, setDbConnections] = useState([]);
  const [pluginTargetTypes, setPluginTargetTypes] = useState([]);
  const [previewDataset, setPreviewDataset] = useState(null);
  const [canvasNodes, setCanvasNodes] = useState([]);
  const [targets, setTargets] = useState([]); // multi-target array
  const [activeTargetId, setActiveTargetId] = useState(null); // which target is selected
  const [showNewTarget, setShowNewTarget] = useState(false); // new target wizard
  const [editingTargetId, setEditingTargetId] = useState(null); // target config editor
  const [joins, setJoins] = useState([]);
  const [transformNodes, setTransformNodes] = useState([]);
  const [constantNodes, setConstantNodes] = useState([]);
  const [sqlNodes, setSqlNodes] = useState([]);
  const [aggNodes, setAggNodes] = useState([]);
  const aggOutputRefs = useRef({});
  const aggNodeRefs = useRef({});
  const aggInputRefs = useRef({});
  const [restNodes, setRestNodes] = useState([]);
  const restOutputRefs = useRef({});
  const restInputRefs = useRef({});
  const [lookupNodes, setLookupNodes] = useState([]);
  const lookupOutputRefs = useRef({});
  const lookupInputRefs = useRef({});
  const [calcNodes, setCalcNodes] = useState([]);
  const calcOutputRefs = useRef({});
  const calcInputPortRefs = useRef({});
  const [switchNodes, setSwitchNodes] = useState([]);
  const switchOutputRefs = useRef({});
  const [pendingSource, setPendingSource] = useState(null);
  const [editingConnection, setEditingConnection] = useState(null);
  const [editingTargetTypeIdx, setEditingTargetTypeIdx] = useState(null); // idx der Connection deren target_type editiert wird
  const [showSchema, setShowSchema] = useState(false);
  const [schemaData, setSchemaData] = useState(null);
  const [schemaLoading, setSchemaLoading] = useState(false);
  const [editingJoin, setEditingJoin] = useState(null);
  const [confirmDeleteConn, setConfirmDeleteConn] = useState(null); // { conn, index }
  const [showSmartMapping, setShowSmartMapping] = useState(false);
  const [renamingTargetField, setRenamingTargetField] = useState(null); // { oldName, value }

  const handleSmartMappingApply = async ({ tables, joins: suggestedJoins }) => {
    // 1. Fehlende Datasets importieren
    const newNodes = [];
    for (const t of tables) {
      if (t.already_exists && t.dataset_id) {
        // Dataset bereits vorhanden → als Node hinzufügen
        const ds = allDatasets.find(d => d.id === t.dataset_id);
        if (ds && !canvasNodes.find(n => n.dataset_id === ds.id)) {
          newNodes.push({
            dataset_id: ds.id, dataset_name: ds.name,
            dataset_columns: ds.columns || [], dataset_column_types: ds.column_types || {},
            dataset_file_type: ds.file_type, dataset_row_count: ds.row_count || 0,
            x: 80 + newNodes.length * 280, y: 100,
          });
        }
      } else {
        // Neu importieren
        const conn = dbConnections.find(c => c.id === parseInt(t.schema !== "dbo" ? t.key.split(".")[0] : "0")) || dbConnections[0];
        if (conn) {
          try {
            const sql = t.schema && t.schema !== "dbo"
              ? `SELECT * FROM [${t.schema}].[${t.name}]`
              : `SELECT * FROM [${t.name}]`;
            const { data } = await api.post(`/api/connections/${conn.id}/import`, {
              sql, dataset_name: t.name, project_id: projectId,
            });
            newNodes.push({
              dataset_id: data.id, dataset_name: data.name,
              dataset_columns: t.columns.map(c => c.name) || [],
              dataset_column_types: {}, dataset_file_type: "db_mssql",
              dataset_row_count: 0, x: 80 + newNodes.length * 280, y: 100,
            });
          } catch (e) {
            console.error("Import fehlgeschlagen:", t.name, e);
          }
        }
      }
    }
    if (newNodes.length > 0) {
      setCanvasNodes(prev => [...prev, ...newNodes]);
    }

    // 2. JOINs hinzufügen
    if (suggestedJoins.length > 0 && newNodes.length >= 2) {
      const newJoins = suggestedJoins.map(j => {
        const leftNode = newNodes.find(n => n.dataset_name === j.from_table.split(".").pop());
        const rightNode = newNodes.find(n => n.dataset_name === j.to_table.split(".").pop());
        if (!leftNode || !rightNode) return null;
        return {
          left_dataset_id: leftNode.dataset_id,
          left_field: j.from_col,
          right_dataset_id: rightNode.dataset_id,
          right_field: j.to_col,
          join_type: "INNER JOIN",
        };
      }).filter(Boolean);
      if (newJoins.length > 0) {
        setJoins(prev => [...prev, ...newJoins]);
      }
    }

    setTimeout(triggerLineDraw, 300);
  };
  const [filterEditor, setFilterEditor] = useState(null);

  // Join drag state
  const [pendingJoin, setPendingJoin] = useState(null);
  const [dragJoin, setDragJoin] = useState(null);
  const [contextMenu, setContextMenu] = useState(null);

  // Active target's connections (shortcut)
  const activeTarget = targets.find((t) => t.id === activeTargetId) || targets[0] || null;
  const connections = activeTarget?.fields || [];
  // targetColumnTypes aus aktivem Target lesen (DB-Schema oder Dataset column_types)
  useEffect(() => {
    setTargetColumnTypes(activeTarget?.target_column_types || {});
  }, [activeTargetId, targets]);
  const setConnections = (updater) => {
    setTargets((prev) => prev.map((t) => t.id === (activeTarget?.id) ? {
      ...t, fields: typeof updater === "function" ? updater(t.fields || []) : updater
    } : t));
  };

  const fieldRefs = useRef({});
  const targetRefs = useRef({});
  const nodeFieldListRefs = useRef({}); // dataset_id → fieldList scroll container ref
  const nodeBodyRefs = useRef({}); // dataset_id → outer node div ref
  const miniPortRefs = useRef({}); // nodeKey → { left: domEl, right: domEl }
  const targetListRef = useRef(null);   // right panel field list scroll container
  const transformOutputRefs = useRef({}); // nodeId → output dot el
  const transformInputRefs  = useRef({}); // nodeId__portId → input dot el
  const constantOutputRefs  = useRef({}); // constId → output dot el
  const sqlOutputRefs       = useRef({}); // sqlId → output dot el
  const canvasRef = useRef(null);
  const [lineTick, setLineTick] = useState(0);
  const allSourceFieldsFlat = canvasNodes.flatMap((n) => n.dataset_columns || []);
  const triggerLineDraw = useCallback(() => setLineTick((t) => t + 1), []);

  useEffect(() => {
    const p = projectId != null ? `?project_id=${projectId}` : "";
    const excludeParam = id && id !== "new" ? `${p ? "&" : "?"}exclude_mapping_id=${id}` : "";
    api.get(`/api/datasets/${p}${excludeParam}`).then(({ data }) => setAllDatasets(Array.isArray(data) ? data : []));
    api.get(`/api/connections/${p}`).then(({ data }) => setDbConnections(Array.isArray(data) ? data : []));
    api.get("/api/plugins/target-types").then(({ data }) => setPluginTargetTypes(Array.isArray(data) ? data : [])).catch(() => {});
    if (id && id !== "new") {
      api.get(`/api/mappings/${id}`).then(({ data }) => {
        setName(data.name);
        setCanvasNodes(data.canvas_nodes || []);
        setJoins(data.joins || []);
        setTransformNodes(data.transform_nodes || []);
        setConstantNodes(data.constant_nodes || []);
        setSqlNodes(data.sql_nodes || []);
        setAggNodes(data.agg_nodes || []);
        setRestNodes(data.rest_nodes || []);
        setLookupNodes(data.lookup_nodes || []);
        setCalcNodes(data.calc_nodes || []);
        setSwitchNodes(data.switch_nodes || []);
        const loadedTargets = data.targets || [];
        setTargets(loadedTargets);
        if (loadedTargets.length > 0) setActiveTargetId(loadedTargets[0].id);
      });
    }
  }, [id]);

  useEffect(() => { const t = setTimeout(triggerLineDraw, 100); return () => clearTimeout(t); }, [canvasNodes, targets, activeTargetId, joins, transformNodes, constantNodes, sqlNodes, aggNodes, restNodes, lookupNodes, calcNodes, switchNodes]);

  // Mouse move for join drag preview
  useEffect(() => {
    if (!pendingJoin) return;
    const onMove = (e) => {
      const srcKey = `${pendingJoin.dataset_id}__${pendingJoin.field}`;
      const srcEl = fieldRefs.current[srcKey];
      if (!srcEl || !canvasRef.current) return;
      const cRect = canvasRef.current.getBoundingClientRect();
      const sRect = srcEl.getBoundingClientRect();
      setDragJoin({
        x1: sRect.right - cRect.left,
        y1: sRect.top + sRect.height / 2 - cRect.top,
        x2: e.clientX - cRect.left,
        y2: e.clientY - cRect.top,
      });
    };
    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, [pendingJoin]);

  const handleCanvasDrop = useCallback((e) => {
    e.preventDefault();
    const dsId = parseInt(e.dataTransfer.getData("dataset_id"));
    if (!dsId) return;
    if (canvasNodes.find((n) => n.dataset_id === dsId)) return;
    const ds = allDatasets.find((d) => d.id === dsId);
    if (!ds) return;
    const rect = canvasRef.current.getBoundingClientRect();
    setCanvasNodes((prev) => [...prev, { dataset_id: ds.id, dataset_name: ds.name, dataset_columns: ds.columns || [], dataset_column_types: ds.column_types || {}, dataset_file_type: ds.file_type, dataset_row_count: ds.row_count || 0, x: Math.max(0, e.clientX - rect.left - 115), y: Math.max(0, e.clientY - rect.top - 20) }]);
  }, [allDatasets, canvasNodes]);

  const handlePositionChange = useCallback((dsId, x, y, toggleMinimize = false) => {
    setCanvasNodes((prev) => prev.map((n) => {
      if (n.dataset_id !== dsId) return n;
      if (toggleMinimize) return { ...n, minimized: !n.minimized };
      return { ...n, x, y };
    }));
    triggerLineDraw();
  }, [triggerLineDraw]);

  const removeNode = useCallback((dsId) => {
    setCanvasNodes((prev) => prev.filter((n) => n.dataset_id !== dsId));
    setConnections((prev) => prev.filter((c) => c.source_dataset_id !== dsId));
    setJoins((prev) => prev.filter((j) => j.left_dataset_id !== dsId && j.right_dataset_id !== dsId));
  }, []);

  // ── Mapping field click ──
  const handleFieldClick = useCallback((datasetId, field) => {
    if (pendingJoin) {
      if (pendingJoin.dataset_id !== datasetId) {
        setJoins((prev) => [...prev, {
          left_dataset_id: pendingJoin.dataset_id, left_field: pendingJoin.field,
          right_dataset_id: datasetId, right_field: field,
          join_type: "INNER JOIN",
        }]);
        setPendingJoin(null); setDragJoin(null);
        setTimeout(triggerLineDraw, 50);
      } else {
        setPendingJoin(null); setDragJoin(null);
      }
      return;
    }

    // If another source is already pending → auto-create target field from this field name
    if (pendingSource && !(pendingSource.dataset_id === datasetId && pendingSource.field === field)) {
      const targetField = field; // use source field name as target field name
      setConnections((prev) => {
        const existing = prev.find((c) => c.target_field === targetField);
        const newConn = {
          source_dataset_id: pendingSource.dataset_id,
          source_field: pendingSource.field,
          target_field: targetField,
          transformer: { type: "direct", source_field: pendingSource.field },
        };
        if (existing) {
          // overwrite existing mapping for that target field
          return [...prev.filter((c) => c.target_field !== targetField), newConn];
        } else {
          return [...prev, newConn];
        }
      });
      setPendingSource(null);
      setTimeout(triggerLineDraw, 50);
      return;
    }

    // Normal: select this field as pending source
    setPendingSource((prev) =>
      prev?.dataset_id === datasetId && prev?.field === field ? null : { dataset_id: datasetId, field }
    );
  }, [pendingJoin, pendingSource, triggerLineDraw]);

  // ── Right-click → context menu ──
  const handleFieldRightClick = useCallback((datasetId, field, e) => {
    setContextMenu({ x: e.clientX, y: e.clientY, dataset_id: datasetId, field });
  }, []);

  const startJoinFromContext = useCallback(() => {
    if (!contextMenu) return;
    setPendingJoin({ dataset_id: contextMenu.dataset_id, field: contextMenu.field });
    setPendingSource(null);
    setContextMenu(null);
  }, [contextMenu]);

  const handleJoinDrop = useCallback((leftDsId, leftField, rightDsId, rightField) => {
    const newJoin = {
      left_dataset_id: leftDsId, left_field: leftField,
      right_dataset_id: rightDsId, right_field: rightField,
      join_type: "INNER JOIN",
    };
    setJoins((prev) => {
      // Avoid duplicate
      const exists = prev.some((j) =>
        j.left_dataset_id === leftDsId && j.left_field === leftField &&
        j.right_dataset_id === rightDsId && j.right_field === rightField
      );
      if (exists) return prev;
      return [...prev, newJoin];
    });
    // Open join editor immediately
    setJoins((prev) => {
      const idx = prev.findIndex((j) =>
        j.left_dataset_id === leftDsId && j.left_field === leftField &&
        j.right_dataset_id === rightDsId && j.right_field === rightField
      );
      if (idx >= 0) return prev; // already exists, do nothing
      return prev;
    });
    setTimeout(() => {
      triggerLineDraw();
    }, 50);
  }, [triggerLineDraw]);

  const handleFieldDoubleClick = useCallback((datasetId, field) => {
    // Feld direkt als neue Connection ins aktive Ziel übernehmen
    const targetConn = connections.find(c => c.target_field === field && !c.source_field);
    if (targetConn) {
      // Freies Zielfeld mit gleichem Namen belegen
      setConnections(prev => prev.map(c =>
        c.target_field === field && !c.source_field
          ? { ...c, source_dataset_id: datasetId, source_field: field, transformer: { type: "direct", source_field: field } }
          : c
      ));
    } else {
      // Neue Connection anlegen wenn Zielfeld existiert
      setConnections(prev => {
        const exists = prev.find(c => c.source_dataset_id === datasetId && c.source_field === field);
        if (exists) return prev;
        return [...prev, { source_dataset_id: datasetId, source_field: field, target_field: field, transformer: { type: "direct", source_field: field } }];
      });
    }
    setTimeout(triggerLineDraw, 50);
  }, [connections, triggerLineDraw]);

  const handleFilterClick = useCallback((datasetId, field, currentFilter) => {
    setFilterEditor({ datasetId, field, currentFilter });
  }, []);

  const handleFilterSave = useCallback((datasetId, field, expr) => {
    setCanvasNodes((prev) => prev.map((n) => {
      if (n.dataset_id !== datasetId) return n;
      const filters = { ...(n.filters || {}) };
      if (expr) filters[field] = expr;
      else delete filters[field];
      return { ...n, filters };
    }));
  }, []);

  const handleTargetFieldClick = (targetField) => {
    if (!pendingSource) return;
    setConnections((prev) => [...prev.filter((c) => c.target_field !== targetField), {
      source_dataset_id: pendingSource.dataset_id, source_field: pendingSource.field,
      target_field: targetField, transformer: { type: "direct", source_field: pendingSource.field },
    }]);
    setPendingSource(null);
    setTimeout(triggerLineDraw, 50);
  };

  const addTargetField = (fieldName) => {
    if (!fieldName.trim()) return;
    setConnections((prev) => {
      if (prev.find((c) => c.target_field === fieldName)) return prev;
      return [...prev, { source_dataset_id: null, source_field: null, target_field: fieldName, transformer: { type: "direct" } }];
    });
  };

  const removeConnection = (idx) => setConnections((prev) => prev.filter((_, i) => i !== idx));
  const updateTransformer = (idx, transformer) => setConnections((prev) => prev.map((c, i) => i === idx ? { ...c, transformer } : c));

  const applyTargetFieldRename = (oldName, newName) => {
    const trimmed = newName.trim();
    setRenamingTargetField(null);
    if (!trimmed || trimmed === oldName) return;
    if (connections.find((c) => c.target_field === trimmed)) return;
    setConnections((prev) => prev.map((c) => c.target_field === oldName ? { ...c, target_field: trimmed } : c));
    setTimeout(triggerLineDraw, 50);
  };

  const [savedToast, setSavedToast] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = { name, canvas_nodes: canvasNodes, joins, transform_nodes: transformNodes, constant_nodes: constantNodes, sql_nodes: sqlNodes, agg_nodes: aggNodes, rest_nodes: restNodes, lookup_nodes: lookupNodes, calc_nodes: calcNodes, switch_nodes: switchNodes, targets, project_id: projectId };
      if (id && id !== "new") {
        await api.put(`/api/mappings/${id}`, payload);
      } else {
        const { data } = await api.post("/api/mappings/", payload);
        navigate(`/mappings/${data.id}`, { replace: true });
      }
      setSavedToast(true);
      setTimeout(() => setSavedToast(false), 2500);
    } finally { setSaving(false); }
  };

  const [isExecuting, setIsExecuting] = useState(false);
  const [exportSuccess, setExportSuccess] = useState(null);
  const [executeStatus, setExecuteStatus] = useState(null); // { done, total, errors }
  const abortRef = useRef(false);

  // Global spinning cursor + ESC to abort while executing
  useEffect(() => {
    if (!isExecuting) { document.body.style.cursor = ""; return; }
    document.body.style.cursor = "wait";
    const onKey = (e) => { if (e.key === "Escape") { abortRef.current = true; } };
    window.addEventListener("keydown", onKey);
    return () => { window.removeEventListener("keydown", onKey); document.body.style.cursor = ""; };
  }, [isExecuting]);

  const handleExecuteAll = async () => {
    if (isExecuting) { abortRef.current = true; return; }
    abortRef.current = false;
    setIsExecuting(true);
    const total = targets.length;
    let done = 0;
    const errors = [];
    setExecuteStatus({ done: 0, total, errors: [] });

    // Gemeinsamer Node-Kontext – einmal für alle Targets
    const nodeCtx = {
      canvas_nodes:    canvasNodes,
      joins,
      transform_nodes: transformNodes,
      constant_nodes:  constantNodes,
      sql_nodes:       sqlNodes,
      agg_nodes:       aggNodes,
      rest_nodes:      restNodes,
      lookup_nodes:    lookupNodes,
      calc_nodes:      calcNodes,
      switch_nodes:    switchNodes,
      mapping_id:      id && id !== "new" ? parseInt(id) : null,
      project_id:      projectId || null,
    };

    await Promise.all(targets.map(async (target) => {
      if (abortRef.current) return;
      try {
        const isFileExport = !target.save_as_dataset && target.target_type !== "db";

        if (isFileExport) {
          // Export unter Exporte speichern (kein direkter Browser-Download mehr)
          const resp = await api.post("/api/mappings/execute-download", {
            ...nodeCtx,
            targets: [target],
          });
          if (abortRef.current) return;
          const exportId = resp.data?.export_id;
          if (exportId) {
            setExportSuccess({ id: exportId, name: target.name || target.target_type });
          }
        } else {
          // DB-Schreiben oder Dataset speichern via execute
          const execResp = await api.post("/api/mappings/execute", {
            ...nodeCtx,
            targets: [target],
            save_as_dataset: !!target.save_as_dataset,
            target_name: target.name || target.target_type,
          });
          // Fehler in der Response prüfen
          const execErrors = execResp.data?.errors || [];
          const failedTargets = (execResp.data?.targets_results || []).filter(t => t.status === "error");
          if (failedTargets.length > 0) {
            throw new Error(failedTargets.map(t => t.error || t.name).join(", "));
          } else if (execErrors.length > 0) {
            throw new Error(execErrors.join(", "));
          }
        }
      } catch (e) {
        if (!abortRef.current) errors.push(`"${target.name}": ${e.response?.data?.detail || e.message}`);
      } finally {
        done++;
        setExecuteStatus({ done, total, errors: [...errors] });
      }
    }));

    setIsExecuting(false);
    if (errors.length) alert("Fehler:\n" + errors.join("\n"));
    setTimeout(() => setExecuteStatus(null), 2000);
  };

  const cancelAll = () => { setPendingSource(null); setPendingJoin(null); setDragJoin(null); setEditingConnection(null); setContextMenu(null); };

  const handleShowSchema = async () => {
    setShowSchema(true);
    setSchemaLoading(true);
    setSchemaData(null);
    try {
      if (id && id !== "new") {
        // Gespeichertes Mapping: Endpunkt nutzen
        const { data } = await api.get(`/api/mappings/${id}/schema`);
        setSchemaData(data);
      } else {
        // Noch nicht gespeichert: Preview-Endpunkt mit aktuellem State
        const activeTarget = targets[0];
        const { data } = await api.post("/api/mappings/preview", {
          canvas_nodes: canvasNodes, joins,
          transform_nodes: transformNodes, constant_nodes: constantNodes,
          sql_nodes: sqlNodes, agg_nodes: aggNodes, rest_nodes: restNodes,
          lookup_nodes: lookupNodes, calc_nodes: calcNodes, switch_nodes: switchNodes,
          targets: targets.length ? targets : undefined,
          fields: activeTarget?.fields || connections,
          preview_rows: 50,
        });
        setSchemaData({ columns: data.columns, column_types: data.column_types,
                        total: data.total, errors: data.errors });
      }
    } catch (e) {
      setSchemaData({ columns: [], column_types: {}, errors: [e.message] });
    } finally {
      setSchemaLoading(false); }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", backgroundColor: S.bgMain }}>

      {/* Export-Erfolg Banner */}
      {exportSuccess && (
        <div style={{
          position: "fixed", bottom: 24, right: 24, zIndex: 9999,
          backgroundColor: S.bgCard, border: "1px solid rgba(110,231,183,0.4)",
          borderRadius: 10, padding: "14px 18px", boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
          display: "flex", alignItems: "center", gap: 12, minWidth: 320,
        }}>
          <span style={{ fontSize: 18 }}>✓</span>
          <div style={{ flex: 1 }}>
            <p style={{ fontSize: 13, fontWeight: 600, color: "#6ee7b7", margin: 0 }}>
              Export gespeichert
            </p>
            <p style={{ fontSize: 11, color: S.textDim, margin: "2px 0 0" }}>
              "{exportSuccess.name}" ist jetzt unter Exporte verfügbar
            </p>
          </div>
          <button onClick={() => navigate("/exports")}
            style={{ fontSize: 11, padding: "5px 10px", borderRadius: 5, cursor: "pointer",
              backgroundColor: "rgba(110,231,183,0.12)", border: "1px solid rgba(110,231,183,0.3)",
              color: "#6ee7b7" }}>
            Exporte →
          </button>
          <button onClick={() => setExportSuccess(null)}
            style={{ background: "none", border: "none", cursor: "pointer", color: S.textDim, fontSize: 16 }}>
            ×
          </button>
        </div>
      )}

      {/* Top Bar */}
      <header style={{ display: "flex", alignItems: "center", gap: 16, padding: "10px 16px", backgroundColor: S.bgCard, borderBottom: `1px solid ${S.border}`, flexShrink: 0 }}>
        <button onClick={() => navigate("/dashboard", { state: { tab: "mappings" } })} className="btn-ghost text-xs"><ArrowLeft size={13} /> Dashboard</button>
        <div style={{ width: 1, height: 20, backgroundColor: S.border }} />
        <input value={name} onChange={(e) => setName(e.target.value)} style={{ background: "transparent", border: "none", outline: "none", fontSize: 13, fontWeight: 600, color: S.textBright, flex: 1 }} />
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginLeft: "auto" }}>
          <span style={{ fontSize: 11, color: S.textDim }}>{connections.length} Felder · {joins.length} Joins · {targets.length} Ziel{targets.length !== 1 ? "e" : ""}</span>
          {!canEdit && (
            <span style={{ fontSize: 11, color: "#93c5fd", padding: "3px 8px", borderRadius: 4, border: "1px solid rgba(147,197,253,0.25)", backgroundColor: "rgba(147,197,253,0.06)" }}>
              Nur Lesen
            </span>
          )}
          {canEdit && (
            <button onClick={() => setShowSmartMapping(true)}
              style={{ display: "flex", alignItems: "center", gap: 5, padding: "6px 11px", borderRadius: 4, border: "1px solid rgba(252,228,153,0.3)", background: "rgba(252,228,153,0.08)", color: S.accent, fontSize: 11, cursor: "pointer", fontWeight: 600 }}
              title="Smart Mapping – Tabellen automatisch erkennen">
              <Sparkles size={13} /> Smart
            </button>
          )}
          {canEdit && (
            <button onClick={handleSave} disabled={saving} className="btn-primary text-xs">
              {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />} Speichern
            </button>
          )}
          {/* Schema-Preview Button */}
          <button onClick={handleShowSchema} title="Schema-Vorschau: Welche Spalten/Typen kommen raus?"
            style={{ display: "flex", alignItems: "center", gap: 5, padding: "6px 11px", borderRadius: 4, border: `1px solid ${S.border}`, background: "none", color: showSchema ? S.accent : S.textDim, fontSize: 11, cursor: "pointer" }}
            onMouseEnter={e => e.currentTarget.style.color = S.accent}
            onMouseLeave={e => { if (!showSchema) e.currentTarget.style.color = S.textDim; }}>
            <Layers size={13} /> Schema
          </button>

          <button onClick={handleExecuteAll} disabled={targets.length === 0 && !isExecuting}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: 4, cursor: targets.length === 0 && !isExecuting ? "not-allowed" : "pointer", backgroundColor: isExecuting ? "rgba(239,68,68,0.15)" : "#22c55e22", border: `1px solid ${isExecuting ? "rgba(239,68,68,0.5)" : "#22c55e55"}`, color: isExecuting ? "#f87171" : "#22c55e", fontSize: 12, fontWeight: 700, opacity: targets.length === 0 && !isExecuting ? 0.4 : 1, transition: "all 0.2s" }}
            onMouseEnter={(e) => { if (!isExecuting && targets.length > 0) e.currentTarget.style.backgroundColor = "#22c55e33"; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = isExecuting ? "rgba(239,68,68,0.15)" : "#22c55e22"; }}>
            {isExecuting
              ? <><Loader2 size={13} className="animate-spin" /> {executeStatus ? `${executeStatus.done}/${executeStatus.total} · ESC` : "Abbrechen"}</>
              : <><Play size={13} /> Ausführen</>}
          </button>
          {savedToast && (
            <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "#6ee7b7", animation: "fadeIn 0.2s ease" }}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="20 6 9 17 4 12"/></svg>
              Gespeichert
            </span>
          )}
          {isExecuting && executeStatus && executeStatus.done < executeStatus.total && (
            <span style={{ fontSize: 11, color: "#f87171" }}>
              {executeStatus.done}/{executeStatus.total} fertig
            </span>
          )}
        </div>
      </header>

      {/* Main */}
      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>

        {/* LEFT: Dataset Explorer */}
        <div style={{ width: 220, flexShrink: 0, display: "flex", flexDirection: "column", backgroundColor: S.bgCard, borderRight: `1px solid ${S.border}` }}>
          <div style={{ padding: "12px 16px", borderBottom: `1px solid ${S.border}`, flexShrink: 0 }}>
            <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: S.accent }}>Datasets</p>
            <p style={{ fontSize: 11, color: S.textDim, marginTop: 2 }}>Auf Canvas ziehen</p>
          </div>
          <div style={{ flex: 1, overflowY: "auto", padding: "6px 0", scrollbarWidth: "thin" }}>
            {allDatasets.filter((ds) => ds.xml_configured !== 0).map((ds) => {
              const onCanvas = canvasNodes.some((n) => n.dataset_id === ds.id);
              return (
                <div key={ds.id} draggable={!onCanvas}
                  onDragStart={(e) => e.dataTransfer.setData("dataset_id", ds.id)}
                  onDoubleClick={() => !onCanvas && setPreviewDataset(ds)}
                  style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 14px", cursor: onCanvas ? "default" : "grab", opacity: onCanvas ? 0.4 : 1, borderRadius: 4, margin: "0 6px" }}
                  onMouseEnter={(e) => { if (!onCanvas) e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.04)"; }}
                  onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}>
                  <FileText size={12} style={{ color: typeColor[ds.file_type] || S.textDim, flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <p style={{ fontSize: 12, fontWeight: 500, color: onCanvas ? S.textDim : S.textBright, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{ds.name}</p>
                    <p style={{ fontSize: 10, color: S.textDim }}>{ds.columns?.length || 0} Felder</p>
                  </div>
                  {onCanvas && <span style={{ fontSize: 10, color: S.accent }}>✓</span>}
                </div>
              );
            })}
          </div>
          {/* Add nodes buttons */}
          <div style={{ padding: "8px 10px", borderTop: `1px solid ${S.border}`, flexShrink: 0, display: "flex", flexDirection: "column", gap: 6 }}>
            {canEdit && (
              <button
                onClick={() => {
                  const id = Math.random().toString(36).slice(2, 9);
                  setTransformNodes((prev) => [...prev, { id, x: 300, y: 120, type: "number_format", config: defaultConfig("number_format"), inputs: [], output_field: `transform_${prev.length + 1}` }]);
                }}
                style={{ display: "flex", alignItems: "center", gap: 6, width: "100%", padding: "7px 10px", borderRadius: 5, cursor: "pointer", backgroundColor: "rgba(129,140,248,0.08)", border: "1px dashed rgba(129,140,248,0.35)", color: "#818cf8", fontSize: 11, fontWeight: 600, justifyContent: "center" }}
                onMouseEnter={(e) => e.currentTarget.style.backgroundColor = "rgba(129,140,248,0.16)"}
                onMouseLeave={(e) => e.currentTarget.style.backgroundColor = "rgba(129,140,248,0.08)"}>
                <Plus size={12} /> Transform hinzufügen
              </button>
            )}
            <button
              onClick={() => {
                const id = Math.random().toString(36).slice(2, 9);
                setConstantNodes((prev) => [...prev, { id, x: 340, y: 80 + prev.length * 40, const_type: "static_text", const_value: "", output_field: `konstante_${prev.length + 1}` }]);
              }}
              style={{ display: "flex", alignItems: "center", gap: 6, width: "100%", padding: "7px 10px", borderRadius: 5, cursor: "pointer", backgroundColor: "rgba(167,139,250,0.08)", border: "1px dashed rgba(167,139,250,0.35)", color: "#a78bfa", fontSize: 11, fontWeight: 600, justifyContent: "center" }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = "rgba(167,139,250,0.16)"}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = "rgba(167,139,250,0.08)"}>
              <Plus size={12} /> Konstante hinzufügen
            </button>
            <button
              onClick={() => {
                const id = Math.random().toString(36).slice(2, 9);
                setSqlNodes((prev) => [...prev, { id, x: 360, y: 80 + prev.length * 50, connection_id: null, sql: "", mode: "scalar", output_field: `sql_${prev.length + 1}` }]);
              }}
              style={{ display: "flex", alignItems: "center", gap: 6, width: "100%", padding: "7px 10px", borderRadius: 5, cursor: "pointer", backgroundColor: "rgba(56,189,248,0.08)", border: "1px dashed rgba(56,189,248,0.35)", color: "#38bdf8", fontSize: 11, fontWeight: 600, justifyContent: "center" }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = "rgba(56,189,248,0.16)"}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = "rgba(56,189,248,0.08)"}>
              <Plus size={12} /> SQL Node hinzufügen
            </button>
            <button
              onClick={() => {
                const id = Math.random().toString(36).slice(2, 9);
                setAggNodes((prev) => [...prev, { id, x: 400, y: 80 + prev.length * 60, fields: [] }]);
              }}
              style={{ display: "flex", alignItems: "center", gap: 6, width: "100%", padding: "7px 10px", borderRadius: 5, cursor: "pointer", backgroundColor: "rgba(245,158,11,0.08)", border: "1px dashed rgba(245,158,11,0.35)", color: "#f59e0b", fontSize: 11, fontWeight: 600, justifyContent: "center" }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = "rgba(245,158,11,0.16)"}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = "rgba(245,158,11,0.08)"}>
              <Layers size={12} /> Aggregation hinzufügen
            </button>
            <button
              onClick={() => {
                const id = Math.random().toString(36).slice(2, 9);
                setRestNodes((prev) => [...prev, { id, x: 420, y: 80 + prev.length * 60, url: "", method: "GET", input_field: "", auth: { type: "none" }, data_path: "", response_mappings: [] }]);
              }}
              style={{ display: "flex", alignItems: "center", gap: 6, width: "100%", padding: "7px 10px", borderRadius: 5, cursor: "pointer", backgroundColor: `${REST_NODE_COLOR}10`, border: `1px dashed ${REST_NODE_COLOR}44`, color: REST_NODE_COLOR, fontSize: 11, fontWeight: 600, justifyContent: "center" }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = `${REST_NODE_COLOR}20`}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = `${REST_NODE_COLOR}10`}>
              <Globe size={12} /> REST Node hinzufügen
            </button>
            <button
              onClick={() => {
                const id = Math.random().toString(36).slice(2, 9);
                setLookupNodes(prev => [...prev, { id, x: 480, y: 80 + prev.length * 60, input_field: "", lookup_dataset_id: null, lookup_key_col: "", on_missing: "null", output_mappings: [] }]);
              }}
              style={{ display: "flex", alignItems: "center", gap: 6, width: "100%", padding: "7px 10px", borderRadius: 5, cursor: "pointer", backgroundColor: LOOKUP_COLOR + "10", border: "1px dashed " + LOOKUP_COLOR + "44", color: LOOKUP_COLOR, fontSize: 11, fontWeight: 600, justifyContent: "center" }}
              onMouseEnter={e => e.currentTarget.style.backgroundColor = LOOKUP_COLOR + "20"}
              onMouseLeave={e => e.currentTarget.style.backgroundColor = LOOKUP_COLOR + "10"}>
              <Search size={12} /> Lookup Node hinzufügen
            </button>
            <button
              onClick={() => {
                const id = Math.random().toString(36).slice(2, 9);
                setCalcNodes(prev => [...prev, { id, x: 540, y: 80 + prev.length * 60, calc_type: "cumsum", input_field: "", output_field: "", order_field: "", order_dir: "asc", group_field: "", window_size: 3 }]);
              }}
              style={{ display: "flex", alignItems: "center", gap: 6, width: "100%", padding: "7px 10px", borderRadius: 5, cursor: "pointer", backgroundColor: CALC_COLOR + "10", border: "1px dashed " + CALC_COLOR + "44", color: CALC_COLOR, fontSize: 11, fontWeight: 600, justifyContent: "center" }}
              onMouseEnter={e => e.currentTarget.style.backgroundColor = CALC_COLOR + "20"}
              onMouseLeave={e => e.currentTarget.style.backgroundColor = CALC_COLOR + "10"}>
              <Calculator size={12} /> Berechnung hinzufügen
            </button>
            <button
              onClick={() => {
                const id = Math.random().toString(36).slice(2, 9);
                setSwitchNodes(prev => [...prev, { id, x: 600, y: 80 + prev.length * 60, output_field: "", branches: [
                  { id: "b1", condition: "has_rows", dataset_id: null, source_dataset_id: null, threshold: 0, label: "Wenn Daten vorhanden" },
                  { id: "b2", condition: "always", dataset_id: null, source_dataset_id: null, threshold: 0, label: "Sonst (Fallback)" }
                ]}]);
              }}
              style={{ display: "flex", alignItems: "center", gap: 6, width: "100%", padding: "7px 10px", borderRadius: 5, cursor: "pointer", backgroundColor: SWITCH_COLOR + "10", border: "1px dashed " + SWITCH_COLOR + "44", color: SWITCH_COLOR, fontSize: 11, fontWeight: 600, justifyContent: "center" }}
              onMouseEnter={e => e.currentTarget.style.backgroundColor = SWITCH_COLOR + "20"}
              onMouseLeave={e => e.currentTarget.style.backgroundColor = SWITCH_COLOR + "10"}>
              <GitBranch size={12} /> Switch Node hinzufügen
            </button>
          </div>
        </div>

        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", overflow: "hidden" }}>

          {/* Canvas area */}
          <div style={{ flex: 1, minHeight: 0, position: "relative" }}>
            {/* Hints */}
            {pendingSource && !pendingJoin && (
              <div style={{ position: "absolute", top: 12, left: "50%", transform: "translateX(-50%)", zIndex: 30, padding: "6px 16px", borderRadius: 20, fontSize: 11, pointerEvents: "none", backgroundColor: "rgba(252,228,153,0.12)", border: `1px solid ${S.accent}`, color: S.accent }}>
                „{pendingSource.field}" ausgewählt → Zielfeld anklicken oder Quellfeld für Auto-Mapping
              </div>
            )}
            {pendingJoin && (
              <div style={{ position: "absolute", top: 12, left: "50%", transform: "translateX(-50%)", zIndex: 30, padding: "6px 16px", borderRadius: 20, fontSize: 11, pointerEvents: "none", backgroundColor: `${JOIN_COLOR}18`, border: `1px solid ${JOIN_COLOR}`, color: JOIN_COLOR }}>
                Join: „{pendingJoin.field}" → Feld im anderen Dataset klicken · ESC abbr.
              </div>
            )}

            <div ref={canvasRef} data-canvas
              style={{ position: "relative", width: "100%", height: "100%", overflow: "auto" }}
              onDragOver={(e) => e.preventDefault()} onDrop={handleCanvasDrop}
              onClick={cancelAll}
              onKeyDown={(e) => { if (e.key === "Escape") cancelAll(); }}
              onScroll={triggerLineDraw}
              tabIndex={0}>

              <div style={{ position: "absolute", inset: 0, pointerEvents: "none", backgroundImage: `radial-gradient(circle, ${S.border} 1px, transparent 1px)`, backgroundSize: "28px 28px", opacity: 0.5 }} />

              {canvasNodes.length === 0 && (
                <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", pointerEvents: "none" }}>
                  <GripVertical size={32} style={{ color: S.textDim, marginBottom: 12 }} />
                  <p style={{ fontSize: 13, color: S.textDim }}>Datasets hierher ziehen</p>
                  <p style={{ fontSize: 11, color: S.textDim, opacity: 0.5, marginTop: 4 }}>aus der linken Spalte</p>
                </div>
              )}

              <SvgOverlay connections={connections} joins={joins} fieldRefs={fieldRefs} targetRefs={targetRefs} nodeFieldListRefs={nodeFieldListRefs} targetListRef={targetListRef} transformOutputRefs={transformOutputRefs} transformInputRefs={transformInputRefs} transformNodes={transformNodes} constantOutputRefs={constantOutputRefs} sqlOutputRefs={sqlOutputRefs} sqlNodes={sqlNodes} aggOutputRefs={aggOutputRefs} aggInputRefs={aggInputRefs} aggNodeRefs={aggNodeRefs} aggNodes={aggNodes} restOutputRefs={restOutputRefs} restInputRefs={restInputRefs} restNodes={restNodes} lookupOutputRefs={lookupOutputRefs} lookupInputRefs={lookupInputRefs} lookupNodes={lookupNodes} calcOutputRefs={calcOutputRefs} calcInputPortRefs={calcInputPortRefs} calcNodes={calcNodes} switchOutputRefs={switchOutputRefs} switchNodes={switchNodes} canvasRef={canvasRef} tick={lineTick} onJoinClick={(i) => setEditingJoin(i)} onConnectionClick={(conn, i) => setConfirmDeleteConn({ conn, index: i })} dragJoin={dragJoin} canvasNodes={canvasNodes} nodeBodyRefs={nodeBodyRefs} miniPortRefs={miniPortRefs} targetColumnTypes={targetColumnTypes} />

              {canvasNodes.map((node) => (
                <DatasetNode key={node.dataset_id} node={node} connections={connections} joins={joins}
                  onFieldClick={handleFieldClick} onFieldRightClick={handleFieldRightClick}
                  onJoinDrop={handleJoinDrop}
                  onFieldDoubleClick={handleFieldDoubleClick}
                  onFilterClick={handleFilterClick}
                  onCastChange={(dsId, newRules) => {
                    // 1. cast_rules im DatasetNode speichern
                    setCanvasNodes(prev => prev.map(n => n.dataset_id === dsId ? { ...n, cast_rules: newRules } : n));
                    // 2. Automatisch target_type in verbundenen Connections vorschlagen
                    //    (nur wenn Connection noch keinen target_type hat)
                    setConnections(prev => prev.map(c => {
                      if (c.source_dataset_id !== dsId) return c;
                      const rule = newRules[c.source_field];
                      if (!rule) return c;
                      if (c.target_type) return c; // nicht überschreiben wenn bereits gesetzt
                      return {
                        ...c,
                        target_type: rule.type,
                        date_format: rule.date_format,
                        decimal_sep: rule.decimal_sep,
                        on_error:    rule.on_error,
                      };
                    }));
                  }}
                  onRegisterNodeRef={(id, ref, bodyRef) => { nodeFieldListRefs.current[id] = ref; if (bodyRef) nodeBodyRefs.current[id] = bodyRef; }}
                  onFieldListScroll={triggerLineDraw}
                  pendingSource={pendingSource} pendingJoin={pendingJoin}
                  onRemove={removeNode} onPositionChange={handlePositionChange} fieldRefs={fieldRefs}
                  onSortChange={(dsId, sorts) => setCanvasNodes(prev => prev.map(n => n.dataset_id === dsId ? { ...n, sorts } : n))} />
              ))}

              {transformNodes.map((tn) => {
                if (!transformOutputRefs.current[tn.id]) transformOutputRefs.current[tn.id] = { current: null };
                return (
                  <TransformNode key={tn.id} node={tn}
                    onPositionChange={(id, x, y) => setTransformNodes((prev) => prev.map((n) => n.id === id ? { ...n, x, y } : n))}
                    onUpdate={(updated) => { setTransformNodes((prev) => prev.map((n) => n.id === updated.id ? updated : n)); setTimeout(triggerLineDraw, 30); }}
                    onRemove={(id) => { setTransformNodes((prev) => prev.filter((n) => n.id !== id)); setConnections((prev) => prev.filter((c) => c.source_dataset_id !== `__transform__${id}`)); }}
                    outputRef={transformOutputRefs.current[tn.id]}
                    inputRefs={transformInputRefs}
                    onMiniPortsReady={(id, l, r) => { miniPortRefs.current[`transform_${id}`] = { left: l, right: r }; if (l || r) setTimeout(triggerLineDraw, 0); }}
                  />
                );
              })}

              {constantNodes.map((cn) => {
                if (!constantOutputRefs.current[cn.id]) constantOutputRefs.current[cn.id] = { current: null };
                return (
                  <ConstantNode key={cn.id} node={cn}
                    onPositionChange={(id, x, y) => { setConstantNodes((prev) => prev.map((n) => n.id === id ? { ...n, x, y } : n)); triggerLineDraw(); }}
                    onUpdate={(updated) => { setConstantNodes((prev) => prev.map((n) => n.id === updated.id ? updated : n)); setTimeout(triggerLineDraw, 30); }}
                    onRemove={(id) => { setConstantNodes((prev) => prev.filter((n) => n.id !== id)); setConnections((prev) => prev.filter((c) => c.source_dataset_id !== `__const__${id}`)); }}
                    outputRef={constantOutputRefs.current[cn.id]}
                    onMiniPortsReady={(id, l, r) => { miniPortRefs.current[`const_${id}`] = { left: l, right: r }; if (l || r) setTimeout(triggerLineDraw, 0); }}
                  />
                );
              })}
              {sqlNodes.map((sn) => {
                if (!sqlOutputRefs.current[sn.id]) sqlOutputRefs.current[sn.id] = { current: null };
                return (
                  <SqlNode key={sn.id} node={sn}
                    dbConnections={dbConnections}
                    canvasNodes={canvasNodes}
                    outputRefs={sqlOutputRefs}
                    onPositionChange={(id, x, y) => { setSqlNodes((prev) => prev.map((n) => n.id === id ? { ...n, x, y } : n)); triggerLineDraw(); }}
                    onUpdate={(updated) => { setSqlNodes((prev) => prev.map((n) => n.id === updated.id ? updated : n)); setTimeout(triggerLineDraw, 30); }}
                    onRemove={(id) => { setSqlNodes((prev) => prev.filter((n) => n.id !== id)); setConnections((prev) => prev.filter((c) => c.source_dataset_id !== `__sql__${id}`)); }}
                    outputRef={sqlOutputRefs.current[sn.id]}
                    onRegisterFieldListRef={(key, ref) => { nodeFieldListRefs.current[key] = ref; }}
                    onMiniPortsReady={(id, l, r) => { miniPortRefs.current[`sql_${sn.id}`] = { left: l, right: r }; if (l || r) setTimeout(triggerLineDraw, 0); }}
                  />
                );
              })}

              {aggNodes.map((an) => {
                if (!aggNodeRefs.current[an.id]) aggNodeRefs.current[an.id] = { current: null };
                return (
                  <AggNode key={an.id} node={an}
                    allSourceFields={allSourceFieldsFlat.map(f => f.name || f)}
                    outputRefs={aggOutputRefs}
                    onMiniPortsReady={(id, l, r) => { miniPortRefs.current[`agg_${id}`] = { left: l, right: r }; if (l || r) setTimeout(triggerLineDraw, 0); }}
                    inputRefs={aggInputRefs}
                    nodeRef={aggNodeRefs.current[an.id]}
                    onPositionChange={(id, x, y) => { setAggNodes((prev) => prev.map((n) => n.id === id ? { ...n, x, y } : n)); triggerLineDraw(); }}
                    onUpdate={(updated) => { setAggNodes((prev) => prev.map((n) => n.id === updated.id ? updated : n)); setTimeout(triggerLineDraw, 30); }}
                    onRemove={(id) => { setAggNodes((prev) => prev.filter((n) => n.id !== id)); setConnections((prev) => prev.filter((c) => c.source_dataset_id !== `__agg__${id}`)); }}
                  />
                );
              })}

{switchNodes.map((sn) => {
                if (!switchOutputRefs.current[sn.id]) switchOutputRefs.current[sn.id] = { current: null };
                return (
                  <SwitchNode key={sn.id} node={sn}
                    allDatasets={allDatasets}
                    outputRefs={switchOutputRefs}
                    onMiniPortsReady={(id, l, r) => { miniPortRefs.current[`switch_${id}`] = { left: l, right: r }; if (l || r) setTimeout(triggerLineDraw, 0); }}
                    onPositionChange={(id, x, y) => { setSwitchNodes(prev => prev.map(n => n.id === id ? { ...n, x, y } : n)); triggerLineDraw(); }}
                    onUpdate={updated => { setSwitchNodes(prev => prev.map(n => n.id === updated.id ? updated : n)); setTimeout(triggerLineDraw, 30); }}
                    onRemove={id => { setSwitchNodes(prev => prev.filter(n => n.id !== id)); setConnections(prev => prev.filter(c => c.source_dataset_id !== "__switch__" + id)); }}
                  />
                );
              })}

              {calcNodes.map((cn) => {
                if (!calcOutputRefs.current[cn.id]) calcOutputRefs.current[cn.id] = { current: null };
                return (
                  <CalcNode key={cn.id} node={cn}
                    allSourceFields={allSourceFieldsFlat.map(f => f.name || f)}
                    outputRef={calcOutputRefs.current[cn.id]}
                    onMiniPortsReady={(id, l, r) => { miniPortRefs.current[`calc_${id}`] = { left: l, right: r }; if (l || r) setTimeout(triggerLineDraw, 0); }}
                    inputPortRefs={calcInputPortRefs}
                    onPositionChange={(id, x, y) => { setCalcNodes(prev => prev.map(n => n.id === id ? { ...n, x, y } : n)); triggerLineDraw(); }}
                    onUpdate={updated => { setCalcNodes(prev => prev.map(n => n.id === updated.id ? updated : n)); setTimeout(triggerLineDraw, 30); }}
                    onRemove={id => { setCalcNodes(prev => prev.filter(n => n.id !== id)); setConnections(prev => prev.filter(c => c.source_dataset_id !== "__calc__" + id)); }}
                  />
                );
              })}

              {lookupNodes.map((ln) => {
                if (!lookupInputRefs.current[ln.id]) lookupInputRefs.current[ln.id] = { current: null };
                return (
                  <LookupNode key={ln.id} node={ln}
                    allDatasets={allDatasets}
                    allSourceFields={allSourceFieldsFlat.map(f => f.name || f)}
                    outputRefs={lookupOutputRefs}
                    onMiniPortsReady={(id, l, r) => { miniPortRefs.current[`lookup_${id}`] = { left: l, right: r }; if (l || r) setTimeout(triggerLineDraw, 0); }}
                    inputRef={lookupInputRefs.current[ln.id]}
                    onPositionChange={(id, x, y) => { setLookupNodes(prev => prev.map(n => n.id === id ? { ...n, x, y } : n)); triggerLineDraw(); }}
                    onUpdate={updated => { setLookupNodes(prev => prev.map(n => n.id === updated.id ? updated : n)); setTimeout(triggerLineDraw, 30); }}
                    onRemove={id => { setLookupNodes(prev => prev.filter(n => n.id !== id)); setConnections(prev => prev.filter(c => c.source_dataset_id !== "__lookup__" + id)); }}
                  />
                );
              })}

              {restNodes.map((rn) => {
                if (!restInputRefs.current[rn.id]) restInputRefs.current[rn.id] = { current: null };
                return (
                  <RestNode key={rn.id} node={rn}
                    allSourceFields={allSourceFieldsFlat.map(f => f.name || f)}
                    outputRefs={restOutputRefs}
                    onMiniPortsReady={(id, l, r) => { miniPortRefs.current[`rest_${id}`] = { left: l, right: r }; if (l || r) setTimeout(triggerLineDraw, 0); }}
                    inputRefs={restInputRefs}
                    onPositionChange={(id, x, y) => { setRestNodes((prev) => prev.map((n) => n.id === id ? { ...n, x, y } : n)); triggerLineDraw(); }}
                    onUpdate={(updated) => { setRestNodes((prev) => prev.map((n) => n.id === updated.id ? updated : n)); setTimeout(triggerLineDraw, 30); }}
                    onRemove={(id) => { setRestNodes((prev) => prev.filter((n) => n.id !== id)); setConnections((prev) => prev.filter((c) => c.source_dataset_id !== `__rest__${id}`)); }}
                  />
                );
              })}

            </div>
          </div>

          {/* Preview Panel */}
          <PreviewPanel
            canvasNodes={canvasNodes}
            connections={connections}
            joins={joins}
            transformNodes={transformNodes}
            constantNodes={constantNodes}
            sqlNodes={sqlNodes}
            aggNodes={aggNodes}
            restNodes={restNodes}
            lookupNodes={lookupNodes}
            calcNodes={calcNodes}
            switchNodes={switchNodes}
            targets={targets}
          />
        </div>

        {/* RIGHT: Multi-Target Panel */}
        <div style={{ width: 300, flexShrink: 0, display: "flex", flexDirection: "column", backgroundColor: S.bgCard, borderLeft: `1px solid ${S.border}` }}>

          {/* Target Tabs Header */}
          <div style={{ flexShrink: 0, borderBottom: `1px solid ${S.border}` }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 12px 0" }}>
              <p style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: S.accent }}>Ziele</p>
              {canEdit && (
                <button onClick={() => setShowNewTarget(true)}
                  style={{ display: "flex", alignItems: "center", gap: 4, fontSize: 10, color: S.accent, background: "none", border: "none", cursor: "pointer", padding: "2px 4px", borderRadius: 4 }}
                  onMouseEnter={(e) => e.currentTarget.style.backgroundColor = "rgba(252,228,153,0.1)"}
                  onMouseLeave={(e) => e.currentTarget.style.backgroundColor = "transparent"}>
                  <Plus size={11} /> Neues Ziel
                </button>
              )}
            </div>
            {/* Tab bar */}
            <div style={{ display: "flex", overflowX: "auto", padding: "6px 8px 0", gap: 4, scrollbarWidth: "none" }}>
              {targets.map((t) => {
                const isActive = t.id === activeTarget?.id;
                const tColor = TARGET_TYPE_COLORS[t.target_type] || S.textDim;
                return (
                  <button key={t.id} onClick={() => setActiveTargetId(t.id)}
                    style={{ flexShrink: 0, display: "flex", alignItems: "center", gap: 5, padding: "5px 10px", borderRadius: "6px 6px 0 0", fontSize: 11, fontWeight: isActive ? 600 : 400, cursor: "pointer", border: `1px solid ${isActive ? S.border : "transparent"}`, borderBottom: isActive ? `1px solid ${S.bgCard}` : `1px solid ${S.border}`, backgroundColor: isActive ? S.bgCard : "transparent", color: isActive ? S.textBright : S.textDim, marginBottom: isActive ? -1 : 0, transition: "all 0.1s" }}>
                    <span style={{ width: 7, height: 7, borderRadius: "50%", backgroundColor: tColor, flexShrink: 0 }} />
                    <span style={{ maxWidth: 80, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t.name || t.target_type}</span>
                    <span style={{ fontSize: 9, color: S.textDim }}>({(t.fields || []).length})</span>
                    {t.save_as_dataset && <span title="Als Dataset speichern" style={{ fontSize: 9, color: S.accent }}>⊙</span>}
                  </button>
                );
              })}
              {targets.length === 0 && (
                <p style={{ fontSize: 11, color: S.textDim, padding: "6px 4px 8px" }}>Noch kein Ziel</p>
              )}
            </div>
          </div>

          {/* Active Target Content */}
          {activeTarget ? (
            <>
              {/* Target header: name + type + actions */}
              <div style={{ flexShrink: 0, padding: "8px 12px", borderBottom: `1px solid ${S.border}`, display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", color: TARGET_TYPE_COLORS[activeTarget.target_type] || S.textDim, letterSpacing: "0.06em" }}>{activeTarget.target_type?.toUpperCase()}</span>
                    {activeTarget.target_table && <span style={{ fontSize: 10, color: S.textDim, fontFamily: "monospace", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{activeTarget.target_table}</span>}
                  </div>
                  <p style={{ fontSize: 11, color: S.textMain, marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{activeTarget.name}</p>
                </div>
                {canEdit && (
                  <div style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                    <button onClick={() => setEditingTargetId(activeTarget.id)} title="Ziel bearbeiten"
                      style={{ padding: "3px 6px", borderRadius: 4, background: "none", border: `1px solid ${S.border}`, color: S.textDim, cursor: "pointer", fontSize: 11 }}
                      onMouseEnter={(e) => e.currentTarget.style.color = S.accent}
                      onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
                      <Pencil size={11} />
                    </button>
                    <button onClick={() => {
                      if (!window.confirm(`Ziel "${activeTarget.name}" wirklich löschen?`)) return;
                      setTargets((prev) => { const next = prev.filter((t) => t.id !== activeTarget.id); setActiveTargetId(next[0]?.id || null); return next; });
                    }} title="Ziel löschen"
                      style={{ padding: "3px 6px", borderRadius: 4, background: "none", border: `1px solid ${S.border}`, color: S.textDim, cursor: "pointer" }}
                      onMouseEnter={(e) => e.currentTarget.style.color = "#e07070"}
                      onMouseLeave={(e) => e.currentTarget.style.color = S.textDim}>
                      <Trash2 size={11} />
                    </button>
                  </div>
                )}
              </div>

              {/* Fields list */}
              <div ref={targetListRef} style={{ flex: 1, minHeight: 0, overflowY: "auto", scrollbarWidth: "thin" }}
                onScroll={triggerLineDraw}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  const srcDsId = e.dataTransfer.getData("source_dataset_id");
                  const srcField = e.dataTransfer.getData("source_field");
                  if (!srcField || !srcDsId) return;
                  const dsId = srcDsId.startsWith("__transform__") || srcDsId.startsWith("__const__") || srcDsId.startsWith("__sql__") || srcDsId.startsWith("__agg__") ? srcDsId : parseInt(srcDsId);
                  e.preventDefault(); e.stopPropagation();
                  setConnections((prev) => {
                    if (prev.find((c) => c.target_field === srcField)) return prev;
                    return [...prev, { source_dataset_id: dsId, source_field: srcField, target_field: srcField, transformer: { type: "direct", source_field: srcField } }];
                  });
                  setTimeout(triggerLineDraw, 50);
                }}>
                {connections.map((conn, idx) => {
                  const ti = TRANSFORMER_TYPES.find((t) => t.value === (conn.transformer?.type || "direct"));
                  const isEditing = editingConnection === idx;
                  const srcField = conn.transformer?.source_field || conn.source_field;
                  // Typ-Kompatibilitätsprüfung
                  const _isSpecialSrc = typeof conn.source_dataset_id === "string";
                  const _srcNode = !_isSpecialSrc ? canvasNodes.find(n => n.dataset_id == conn.source_dataset_id) : null;
                  const _srcType = _srcNode?.dataset_column_types?.[conn.source_field]?.type;
                  const _tgtType = targetColumnTypes[conn.target_field]?.type;
                  const _typeIncompat = !conn.target_type && _srcType && _tgtType && _srcType !== _tgtType && !(_srcType === "integer" && _tgtType === "decimal");
                  const isSchemaField = !!targetColumnTypes[conn.target_field];
                  const isPluginField = pluginTargetTypes.some(p => p.id === activeTarget?.target_type);
                  const isRenameable = !isSchemaField && !isPluginField;
                  const isRenamingThis = renamingTargetField?.oldName === conn.target_field;
                  return (
                    <div key={`${conn.target_field}-${idx}`}
                      ref={(el) => { if (el) targetRefs.current[conn.target_field] = el; }}
                      draggable
                      onDragStart={(e) => { if (isRenamingThis) { e.preventDefault(); return; } e.dataTransfer.setData("conn_idx", idx); e.currentTarget.style.opacity = "0.4"; }}
                      onDragEnd={(e) => { e.currentTarget.style.opacity = "1"; }}
                      onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); e.currentTarget.style.borderTop = `2px solid ${S.accent}`; }}
                      onDragLeave={(e) => { e.currentTarget.style.borderTop = "2px solid transparent"; }}
                      onDrop={(e) => {
                        e.stopPropagation();
                        e.currentTarget.style.borderTop = "2px solid transparent";
                        const srcDsIdRaw = e.dataTransfer.getData("source_dataset_id");
                        const draggedField = e.dataTransfer.getData("source_field");
                        if (draggedField && srcDsIdRaw) {
                          const srcDsId = srcDsIdRaw.startsWith("__transform__") || srcDsIdRaw.startsWith("__const__") || srcDsIdRaw.startsWith("__sql__") || srcDsIdRaw.startsWith("__agg__") || srcDsIdRaw.startsWith("__rest__") || srcDsIdRaw.startsWith("__lookup__") || srcDsIdRaw.startsWith("__calc__") || srcDsIdRaw.startsWith("__switch__") ? srcDsIdRaw : parseInt(srcDsIdRaw);
                          setConnections((prev) => prev.map((c, i) => i === idx ? { ...c, source_dataset_id: srcDsId, source_field: draggedField, transformer: { type: "direct", source_field: draggedField } } : c));
                          setTimeout(triggerLineDraw, 50); return;
                        }
                        const fromIdx = parseInt(e.dataTransfer.getData("conn_idx"));
                        if (isNaN(fromIdx) || fromIdx === idx) return;
                        setConnections((prev) => { const next = [...prev]; const [moved] = next.splice(fromIdx, 1); next.splice(idx, 0, moved); return next; });
                        setTimeout(triggerLineDraw, 50);
                      }}
                      onClick={(e) => { e.stopPropagation(); if (pendingSource) { handleTargetFieldClick(conn.target_field); } }}
                      style={{ display: "flex", flexDirection: "column", padding: "6px 10px 6px 8px", margin: "1px 6px", borderRadius: 4, cursor: "grab", borderTop: "2px solid transparent", backgroundColor: "transparent", border: `1px solid ${conn.source_field ? (ti?.color || "#6ee7b7") + "33" : "transparent"}`, transition: "background-color 0.1s" }}
                      onMouseEnter={(e) => { e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)"; }}
                      onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = "transparent"; }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <GripVertical size={10} style={{ color: S.textDim, flexShrink: 0 }} />
                        <div style={{ width: 7, height: 7, borderRadius: "50%", flexShrink: 0, backgroundColor: conn.source_field ? (ti?.color || "#6ee7b7") : "transparent", border: `2px solid ${conn.source_field ? (ti?.color || "#6ee7b7") : S.textDim}` }} />
                        <span style={{ fontSize: 11, fontFamily: "monospace", fontWeight: 600, color: conn.source_field ? S.textBright : S.textDim, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "flex", alignItems: "center", gap: 0 }}>
                          {/* 🔑 Slot – feste Breite */}
                          <span style={{ width: 16, flexShrink: 0, display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 9 }}>
                            {targetColumnTypes[conn.target_field]?.is_primary ? "🔑" : ""}
                          </span>
                          {/* Typ-Badge Slot – feste Breite */}
                          {(() => {
                            const ct = targetColumnTypes[conn.target_field];
                            const TC = { integer:"#93c5fd", decimal:"#6ee7b7", date:"#fcd34d", boolean:"#c4b5fd", string:"#6a6a6a" };
                            const TL = { integer:"INT", decimal:"DEC", date:"DAT", boolean:"BOL", string:"STR" };
                            if (!ct) return <span style={{ width: 28, flexShrink: 0 }} />;
                            const c = TC[ct.type] || "#6a6a6a";
                            return <span style={{ width: 28, flexShrink: 0, fontSize: 8, fontWeight: 700, color: c, backgroundColor: c + "18", borderRadius: 2, padding: "1px 3px", marginRight: 4, textAlign: "center" }}>{TL[ct.type] || ct.type?.slice(0,3).toUpperCase()}</span>;
                          })()}
                          {isRenamingThis ? (
                            <input
                              autoFocus
                              value={renamingTargetField.value}
                              onChange={(e) => setRenamingTargetField((r) => ({ ...r, value: e.target.value }))}
                              onBlur={() => applyTargetFieldRename(conn.target_field, renamingTargetField.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") applyTargetFieldRename(conn.target_field, renamingTargetField.value);
                                if (e.key === "Escape") setRenamingTargetField(null);
                                e.stopPropagation();
                              }}
                              onClick={(e) => e.stopPropagation()}
                              style={{ background: "rgba(255,255,255,0.08)", border: "1px solid var(--accent)", borderRadius: 3, color: "inherit", fontFamily: "monospace", fontSize: "inherit", fontWeight: "inherit", padding: "0 4px", width: "100%", outline: "none" }}
                            />
                          ) : (
                            <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{conn.target_field}</span>
                          )}
                        </span>
                        {conn.source_field && <span style={{ fontSize: 9, color: ti?.color || "#6ee7b7", flexShrink: 0, textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 700 }}>{ti?.label}</span>}
                        {/* target_type Badge */}
                        {conn.target_type && (() => {
                          const TYPE_COLORS = { integer:"#60a5fa", decimal:"#34d399", date:"#f59e0b", datetime:"#f59e0b", boolean:"#a78bfa", string:"#94a3b8" };
                          const TYPE_LABELS = { integer:"INT", decimal:"DEC", date:"DAT", datetime:"DT", boolean:"BOOL", string:"STR" };
                          const c = TYPE_COLORS[conn.target_type] || "#94a3b8";
                          return <span style={{ fontSize: 8, fontWeight: 700, fontFamily: "monospace", color: c, border: `1px solid ${c}`, borderRadius: 3, padding: "1px 4px", flexShrink: 0 }}>{TYPE_LABELS[conn.target_type] || conn.target_type}</span>;
                        })()}
                        {/* Typ-Inkompatibilitäts-Warnung */}
                        {_typeIncompat && (
                          <span title={`Typ-Konflikt: ${_srcType} → ${_tgtType}. Bitte einen Cast konfigurieren.`}
                            style={{ fontSize: 8, fontWeight: 700, fontFamily: "monospace", color: "#f97316", border: "1px solid #f97316", borderRadius: 3, padding: "1px 4px", flexShrink: 0, cursor: "help" }}>
                            ⚠ {_srcType?.slice(0,3).toUpperCase()}→{_tgtType?.slice(0,3).toUpperCase()}
                          </span>
                        )}
                        {isRenameable && !isRenamingThis && (
                          <button onClick={(e) => { e.stopPropagation(); setRenamingTargetField({ oldName: conn.target_field, value: conn.target_field }); }} title="Feldname umbenennen" style={{ color: S.textDim, flexShrink: 0, lineHeight: 1, background: "none", border: "none", cursor: "pointer" }}
                            onMouseEnter={(e) => { e.currentTarget.style.color = S.accent || "#a78bfa"; }}
                            onMouseLeave={(e) => { e.currentTarget.style.color = S.textDim; }}>
                            <Pencil size={9} />
                          </button>
                        )}
                        <button onClick={(e) => { e.stopPropagation(); removeConnection(idx); }} style={{ color: S.textDim, flexShrink: 0, lineHeight: 1, background: "none", border: "none", cursor: "pointer" }}
                          onMouseEnter={(e) => { e.currentTarget.style.color = "#e07070"; }}
                          onMouseLeave={(e) => { e.currentTarget.style.color = S.textDim; }}>
                          <X size={10} />
                        </button>
                      </div>
                      {srcField && (
                        <div style={{ marginLeft: 22, marginTop: 2 }}>
                          {conn.transformer?.type === "formula" ? (
                            <span style={{ fontSize: 9, fontFamily: "monospace", color: S.textDim, fontStyle: "italic" }}>ƒ {conn.transformer.formula?.slice(0, 28)}{(conn.transformer.formula?.length || 0) > 28 ? "…" : ""}</span>
                          ) : conn.transformer?.type === "constant" ? (
                            <span style={{ fontSize: 9, fontFamily: "monospace", color: S.textDim }}>= „{conn.transformer.constant_value}"</span>
                          ) : (
                            <span style={{ fontSize: 9, fontFamily: "monospace", color: S.textDim, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block" }}>← {srcField}</span>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}

                {/* Drop zone */}
                <div style={{ margin: "4px 6px 6px", padding: "10px", borderRadius: 4, border: `1px dashed ${S.border}`, textAlign: "center", fontSize: 10, color: S.textDim }}
                  onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); e.currentTarget.style.borderColor = S.accent; e.currentTarget.style.color = S.accent; e.currentTarget.style.backgroundColor = "rgba(252,228,153,0.05)"; }}
                  onDragLeave={(e) => { e.currentTarget.style.borderColor = S.border; e.currentTarget.style.color = S.textDim; e.currentTarget.style.backgroundColor = "transparent"; }}
                  onDrop={(e) => {
                    e.currentTarget.style.borderColor = S.border; e.currentTarget.style.color = S.textDim; e.currentTarget.style.backgroundColor = "transparent";
                    const srcDsIdRaw = e.dataTransfer.getData("source_dataset_id");
                    const draggedField = e.dataTransfer.getData("source_field");
                    if (!draggedField || !srcDsIdRaw) return;
                    const srcDsId = srcDsIdRaw.startsWith("__transform__") || srcDsIdRaw.startsWith("__const__") || srcDsIdRaw.startsWith("__sql__") || srcDsIdRaw.startsWith("__agg__") || srcDsIdRaw.startsWith("__rest__") || srcDsIdRaw.startsWith("__lookup__") || srcDsIdRaw.startsWith("__calc__") || srcDsIdRaw.startsWith("__switch__") ? srcDsIdRaw : parseInt(srcDsIdRaw);
                    if (!srcDsId) return;
                    e.preventDefault(); e.stopPropagation();
                    setConnections((prev) => {
                      if (prev.find((c) => c.target_field === draggedField)) return prev;
                      return [...prev, { source_dataset_id: srcDsId, source_field: draggedField, target_field: draggedField, transformer: { type: "direct", source_field: draggedField } }];
                    });
                    setTimeout(triggerLineDraw, 50);
                  }}>
                  Feld hier ablegen
                </div>
              </div>

              {/* Add field manually */}
              {canEdit && (
                <TargetAddField onAdd={(fieldName) => { addTargetField(fieldName); }} />
              )}
            </>
          ) : (
            <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 12, padding: 24 }}>
              <Database size={32} style={{ color: S.textDim, opacity: 0.3 }} />
              <p style={{ fontSize: 12, color: S.textDim, textAlign: "center" }}>Noch kein Ziel definiert.<br/>Klicke auf „Neues Ziel".</p>
              {canEdit && (
                <button onClick={() => setShowNewTarget(true)} className="btn-primary text-xs"><Plus size={12} /> Neues Ziel</button>
              )}
            </div>
          )}

          {/* Joins summary */}
          {(joins.length > 0 || canvasNodes.some((n) => Object.values(n.filters || {}).filter(Boolean).length > 0)) && (
            <div style={{ flexShrink: 0, borderTop: `1px solid ${S.border}`, padding: "8px 12px" }}>
              {(() => {
                const totalFilters = canvasNodes.reduce((s, n) => s + Object.values(n.filters || {}).filter(Boolean).length, 0);
                return (
                  <button onClick={() => setShowJoinList(true)}
                    style={{ width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between", padding: "6px 10px", borderRadius: 4, cursor: "pointer", backgroundColor: `${JOIN_COLOR}10`, border: `1px solid ${JOIN_COLOR}40`, color: JOIN_COLOR }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = `${JOIN_COLOR}20`)}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = `${JOIN_COLOR}10`)}>
                    <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
                      {joins.length > 0 && <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em" }}>Joins ({joins.length})</span>}
                      {totalFilters > 0 && <span style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em", color: "#a78bfa" }}>⊤ Filter ({totalFilters})</span>}
                    </div>
                    <span style={{ fontSize: 10, opacity: 0.6 }}>▸</span>
                  </button>
                );
              })()}
            </div>
          )}
        </div>
      </div>

      {/* Schema-Preview Modal */}
    {showSchema && (
      <div style={{ position: "fixed", inset: 0, zIndex: 60, display: "flex", alignItems: "center",
          justifyContent: "center", backgroundColor: "rgba(0,0,0,0.75)" }}
        onClick={() => setShowSchema(false)}>
        <div style={{ backgroundColor: S.bgCard, border: `1px solid ${S.border}`, borderRadius: 10,
            width: 640, maxHeight: "80vh", display: "flex", flexDirection: "column",
            boxShadow: "0 24px 60px rgba(0,0,0,0.6)" }}
          onClick={e => e.stopPropagation()}>

          {/* Header */}
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 18px",
              borderBottom: `1px solid ${S.border}`, backgroundColor: S.bgEl, borderRadius: "10px 10px 0 0" }}>
            <Layers size={14} style={{ color: S.accent }} />
            <span style={{ fontSize: 13, fontWeight: 700, color: S.textBright }}>Schema-Vorschau</span>
            <span style={{ fontSize: 10, color: S.textDim }}>— Ausgabe-Spalten & Typen</span>
            <button onClick={() => setShowSchema(false)}
              style={{ marginLeft: "auto", color: S.textDim, background: "none", border: "none", cursor: "pointer" }}>
              <X size={14} />
            </button>
          </div>

          {/* Body */}
          <div style={{ flex: 1, overflow: "auto", padding: 18 }}>
            {schemaLoading ? (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center",
                  height: 120, color: S.textDim, gap: 8 }}>
                <Loader2 size={16} className="animate-spin" /> Schema wird berechnet…
              </div>
            ) : schemaData ? (
              <>
                {schemaData.errors?.length > 0 && (
                  <div style={{ marginBottom: 12, padding: "8px 12px", backgroundColor: "rgba(224,112,112,0.08)",
                      border: "1px solid rgba(224,112,112,0.25)", borderRadius: 6 }}>
                    {schemaData.errors.map((e, i) => (
                      <p key={i} style={{ fontSize: 10, color: "#e07070", margin: 0 }}>⚠ {e}</p>
                    ))}
                  </div>
                )}
                <div style={{ fontSize: 10, color: S.textDim, marginBottom: 10 }}>
                  {schemaData.columns?.length || 0} Spalten · {schemaData.total || 0} Zeilen (Vorschau)
                </div>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                  <thead>
                    <tr style={{ backgroundColor: S.bgEl }}>
                      {[["Spalte", "60%"], ["Typ", "20%"], ["Raw-Typ", "20%"]].map(([h, w]) => (
                        <th key={h} style={{ textAlign: "left", padding: "6px 12px", fontFamily: "monospace",
                            fontWeight: 700, color: S.accent, borderBottom: `1px solid ${S.border}`,
                            width: w, whiteSpace: "nowrap" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(schemaData.columns || []).map((col, i) => {
                      const ti = schemaData.column_types?.[col];
                      const TYPE_COLORS = { integer:"#60a5fa", decimal:"#34d399", date:"#f59e0b",
                                            datetime:"#f59e0b", boolean:"#a78bfa", bool:"#a78bfa", string:"#94a3b8" };
                      const TYPE_LABELS = { integer:"INT", decimal:"DEC", date:"DAT", datetime:"DT",
                                            boolean:"BOOL", bool:"BOOL", string:"STR" };
                      const tc = ti ? (TYPE_COLORS[ti.type] || "#94a3b8") : "#94a3b8";
                      const tl = ti ? (TYPE_LABELS[ti.type] || ti.type?.toUpperCase() || "?") : "?";
                      return (
                        <tr key={col} style={{ borderBottom: `1px solid ${S.border}`,
                            backgroundColor: i % 2 === 0 ? "transparent" : "rgba(255,255,255,0.01)" }}>
                          <td style={{ padding: "5px 12px", fontFamily: "monospace", color: S.textBright }}>{col}</td>
                          <td style={{ padding: "5px 12px" }}>
                            <span style={{ fontSize: 9, fontWeight: 700, color: tc,
                                backgroundColor: tc + "18", borderRadius: 3, padding: "2px 6px" }}>{tl}</span>
                          </td>
                          <td style={{ padding: "5px 12px", fontFamily: "monospace",
                              fontSize: 10, color: S.textDim }}>{ti?.raw || "—"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </>
            ) : null}
          </div>

          <div style={{ padding: "10px 18px", borderTop: `1px solid ${S.border}`,
              display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: 10, color: S.textDim }}>
              Spaltentypen basieren auf 50 Preview-Zeilen + manuellen target_type Einstellungen
            </span>
            <button onClick={() => setShowSchema(false)}
              style={{ padding: "5px 14px", borderRadius: 4, border: `1px solid ${S.border}`,
                  background: "none", color: S.textMain, fontSize: 11, cursor: "pointer" }}>
              Schließen
            </button>
          </div>
        </div>
      </div>
    )}

    {/* target_type Editor Modal */}
      {editingTargetTypeIdx !== null && (() => {
        const conn = connections[editingTargetTypeIdx];
        if (!conn) return null;
        return (
          <TypeConvertEditor
            mode="target"
            field={conn.target_field}
            currentCast={conn.target_type ? {
              type: conn.target_type,
              date_format: conn.date_format,
              decimal_sep: conn.decimal_sep,
              on_error:    conn.on_error,
            } : null}
            onSave={(rule) => {
              setConnections(prev => prev.map((c, i) => i === editingTargetTypeIdx ? {
                ...c,
                target_type:  rule?.type        || undefined,
                date_format:  rule?.date_format  || undefined,
                decimal_sep:  rule?.decimal_sep  || undefined,
                on_error:     rule?.on_error     || undefined,
              } : c));
            }}
            onClose={() => setEditingTargetTypeIdx(null)}
          />
        );
      })()}

      {/* Transformer Popup */}
      {editingConnection !== null && connections[editingConnection] && (
        <div style={{ position: "fixed", inset: 0, zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "rgba(0,0,0,0.6)" }} onClick={() => setEditingConnection(null)}>
          <div onClick={(e) => e.stopPropagation()}>
            <TransformerEditor connection={connections[editingConnection]} allSourceFields={allSourceFieldsFlat} onClose={() => setEditingConnection(null)} onChange={(t) => updateTransformer(editingConnection, t)} />
          </div>
        </div>
      )}

      {/* Join + Filter List Modal */}
      {showJoinList && (
        <div style={{ position: "fixed", inset: 0, zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center", backgroundColor: "rgba(0,0,0,0.7)" }} onClick={() => setShowJoinList(false)}>
          <div style={{ width: 480, maxHeight: "70vh", display: "flex", flexDirection: "column", backgroundColor: S.bgCard, borderRadius: 8, border: `1px solid ${S.border}`, boxShadow: "0 24px 60px rgba(0,0,0,0.7)" }} onClick={(e) => e.stopPropagation()}>
            {/* Header */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 18px", borderBottom: `1px solid ${S.border}`, flexShrink: 0 }}>
              <span style={{ fontSize: 12, fontWeight: 700, color: S.textBright, textTransform: "uppercase", letterSpacing: "0.1em" }}>Joins & Filter</span>
              <button onClick={() => setShowJoinList(false)} style={{ color: S.textDim, background: "none", border: "none", cursor: "pointer", fontSize: 16 }}>✕</button>
            </div>
            {/* Scrollable list */}
            <div style={{ overflowY: "auto", scrollbarWidth: "thin", flex: 1, padding: "10px 10px" }}>
              {/* Joins */}
              {joins.length > 0 && (
                <>
                  <p style={{ fontSize: 9, fontWeight: 700, color: JOIN_COLOR, textTransform: "uppercase", letterSpacing: "0.1em", padding: "2px 6px 6px" }}>Joins ({joins.length})</p>
                  {joins.map((j, i) => {
                    const jt = JOIN_TYPES.find((x) => x.value === j.join_type) || JOIN_TYPES[0];
                    const ln = canvasNodes.find((n) => n.dataset_id === j.left_dataset_id)?.dataset_name || "?";
                    const rn = canvasNodes.find((n) => n.dataset_id === j.right_dataset_id)?.dataset_name || "?";
                    return (
                      <div key={i}
                        onClick={() => { setShowJoinList(false); setEditingJoin(i); }}
                        style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 10px", borderRadius: 5, cursor: "pointer", marginBottom: 3, border: `1px solid ${S.border}` }}
                        onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = `${JOIN_COLOR}10`)}
                        onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}>
                        <span style={{ fontSize: 9, fontWeight: 700, color: JOIN_COLOR, textTransform: "uppercase", letterSpacing: "0.08em", width: 40, flexShrink: 0 }}>{jt.label}</span>
                        <span style={{ fontSize: 11, color: S.textMain, fontFamily: "monospace", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          <span style={{ color: S.accent }}>{ln}</span>.{j.left_field}
                          <span style={{ color: S.textDim, margin: "0 6px" }}>=</span>
                          <span style={{ color: S.accent }}>{rn}</span>.{j.right_field}
                        </span>
                        <span style={{ fontSize: 10, color: S.textDim, flexShrink: 0 }}>✎</span>
                      </div>
                    );
                  })}
                </>
              )}

              {/* Filters */}
              {(() => {
                const filterEntries = canvasNodes.flatMap((n) =>
                  Object.entries(n.filters || {})
                    .filter(([, expr]) => expr)
                    .map(([field, expr]) => ({ datasetId: n.dataset_id, datasetName: n.dataset_name, field, expr }))
                );
                if (!filterEntries.length) return null;
                return (
                  <>
                    <p style={{ fontSize: 9, fontWeight: 700, color: "#a78bfa", textTransform: "uppercase", letterSpacing: "0.1em", padding: "10px 6px 6px", marginTop: joins.length > 0 ? 6 : 0, borderTop: joins.length > 0 ? `1px solid ${S.border}` : "none" }}>
                      ⊤ Filter ({filterEntries.length})
                    </p>
                    {filterEntries.map((f, i) => (
                      <div key={i}
                        onClick={() => { setShowJoinList(false); setFilterEditor({ datasetId: f.datasetId, field: f.field, currentFilter: f.expr }); }}
                        style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 10px", borderRadius: 5, cursor: "pointer", marginBottom: 3, border: `1px solid ${S.border}` }}
                        onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "rgba(167,139,250,0.08)")}
                        onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}>
                        <span style={{ fontSize: 10, color: S.accent, fontFamily: "monospace", flexShrink: 0, maxWidth: 110, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.datasetName}</span>
                        <span style={{ fontSize: 10, color: "#a78bfa", fontFamily: "monospace", flexShrink: 0 }}>.{f.field}</span>
                        <span style={{ fontSize: 10, color: S.textDim, margin: "0 2px" }}>→</span>
                        <span style={{ fontSize: 11, color: S.textMain, fontFamily: "monospace", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.expr}</span>
                        <span style={{ fontSize: 10, color: S.textDim, flexShrink: 0 }}>✎</span>
                      </div>
                    ))}
                  </>
                );
              })()}
            </div>
          </div>
        </div>
      )}

      {/* Join Editor Popup */}
      {editingJoin !== null && joins[editingJoin] && (
        <JoinEditor
          join={joins[editingJoin]}
          onClose={() => setEditingJoin(null)}
          onChange={(updated) => setJoins((prev) => prev.map((j, i) => i === editingJoin ? updated : j))}
          onDelete={() => { setJoins((prev) => prev.filter((_, i) => i !== editingJoin)); setEditingJoin(null); }}
        />
      )}

      {/* Verbindung löschen Modal */}
      {showSmartMapping && (
        <SmartMappingModal
          projectId={projectId}
          connections={dbConnections}
          onClose={() => setShowSmartMapping(false)}
          onApply={handleSmartMappingApply}
        />
      )}

      {confirmDeleteConn && createPortal(
        <div onClick={() => setConfirmDeleteConn(null)} style={{
          position: "fixed", inset: 0, zIndex: 9999,
          backgroundColor: "rgba(0,0,0,0.6)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            background: "var(--bg-card)", border: "1px solid var(--border)",
            borderRadius: 10, padding: "20px 24px", width: 360,
            boxShadow: "0 24px 60px rgba(0,0,0,0.7)",
          }}>
            <p style={{ fontSize: 14, fontWeight: 700, color: "var(--text-bright)", margin: "0 0 10px" }}>
              Verbindung entfernen
            </p>
            <p style={{ fontSize: 12, color: "var(--text-main)", margin: "0 0 6px" }}>
              <span style={{ color: "#6ee7b7", fontFamily: "monospace" }}>{confirmDeleteConn.conn.source_field}</span>
              {" → "}
              <span style={{ color: "var(--accent)", fontFamily: "monospace" }}>{confirmDeleteConn.conn.target_field}</span>
            </p>
            <p style={{ fontSize: 11, color: "var(--text-dim)", margin: "0 0 20px" }}>
              Diese Verbindung wird aus dem Mapping entfernt.
            </p>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button onClick={() => setConfirmDeleteConn(null)} style={{
                fontSize: 12, padding: "7px 14px", borderRadius: 6, cursor: "pointer",
                background: "transparent", border: "1px solid var(--border)", color: "var(--text-dim)",
              }}>Abbrechen</button>
              <button onClick={() => {
                setConnections(prev => prev.filter((_, i) => i !== confirmDeleteConn.index));
                setConfirmDeleteConn(null);
                triggerLineDraw();
              }} style={{
                fontSize: 12, fontWeight: 600, padding: "7px 14px", borderRadius: 6, cursor: "pointer",
                background: "rgba(224,112,112,0.15)", border: "1px solid rgba(224,112,112,0.4)", color: "#e07070",
              }}>Verbindung löschen</button>
            </div>
          </div>
        </div>
      , document.body)}

      {filterEditor && (
        <FilterEditor
          datasetId={filterEditor.datasetId}
          field={filterEditor.field}
          currentFilter={filterEditor.currentFilter}
          onSave={handleFilterSave}
          onClose={() => setFilterEditor(null)}
        />
      )}

      {showNewTarget && (
        <TargetConfigModal
          target={null}
          dbConnections={dbConnections}
          pluginTargetTypes={pluginTargetTypes}
          onSave={(newTarget) => {
            if (newTarget.target_type === "db" && newTarget.target_table) {
              const dup = targets.find((t) => t.target_type === "db" && t.target_table === newTarget.target_table);
              if (dup) { alert(`Tabelle "${newTarget.target_table}" ist bereits als Ziel "${dup.name}" eingetragen.`); return; }
            }
            setTargets((prev) => [...prev, newTarget]);
            setActiveTargetId(newTarget.id);
            setShowNewTarget(false);
          }}
          onClose={() => setShowNewTarget(false)}
        />
      )}

      {editingTargetId && (
        <TargetConfigModal
          target={targets.find((t) => t.id === editingTargetId)}
          dbConnections={dbConnections}
          pluginTargetTypes={pluginTargetTypes}
          onSave={(updated) => {
            if (updated.target_type === "db" && updated.target_table) {
              const dup = targets.find((t) => t.id !== editingTargetId && t.target_type === "db" && t.target_table === updated.target_table);
              if (dup) { alert(`Tabelle "${updated.target_table}" ist bereits als Ziel "${dup.name}" eingetragen.`); return; }
            }
            setTargets((prev) => prev.map((t) => {
              if (t.id !== editingTargetId) return t;
              // Wenn der FieldPicker neue Felder mitgegeben hat (DB-Ziel), diese übernehmen.
              // Sonst bestehende Felder behalten (CSV/JSON/etc. – da ändert sich nur Config).
              const keepOldFields = !updated.fields || updated.fields.length === 0;
              return { ...updated, fields: keepOldFields ? (t.fields || []) : updated.fields };
            }));
            setEditingTargetId(null);
          }}
          onClose={() => setEditingTargetId(null)}
        />
      )}

      {/* Dataset Preview Modal */}
      {previewDataset && (
        <div style={{ position: "fixed", inset: 0, zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center", padding: 16, backgroundColor: "rgba(0,0,0,0.8)" }} onClick={() => setPreviewDataset(null)}>
          <div style={{ width: "100%", maxWidth: 960, height: "70vh", display: "flex", flexDirection: "column", borderRadius: 8, overflow: "hidden", backgroundColor: S.bgCard, border: `1px solid ${S.border}` }} onClick={(e) => e.stopPropagation()}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 20px", borderBottom: `1px solid ${S.border}`, flexShrink: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <FileText size={15} style={{ color: S.accent }} />
                <span style={{ fontSize: 13, fontWeight: 600, color: S.textBright }}>{previewDataset.name}</span>
                <span style={{ fontSize: 11, fontFamily: "monospace", color: S.textDim }}>{previewDataset.row_count} Zeilen · {previewDataset.columns?.length} Spalten</span>
              </div>
              <button onClick={() => setPreviewDataset(null)} className="btn-ghost text-xs">Schließen</button>
            </div>
            <DatasetPreviewTable dataset={previewDataset} />
          </div>
        </div>
      )}

      {/* Context Menu */}
      {contextMenu && (
        <ContextMenu x={contextMenu.x} y={contextMenu.y} onJoin={startJoinFromContext} onClose={() => setContextMenu(null)} />
      )}
    </div>
  );
}
