import { useState, useEffect, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import SmartMappingModal from "../components/mapping/SmartMappingModal";
import { useNavigate, useParams } from "react-router-dom";
import { useProject } from "../context/ProjectContext";
import { useAIAssistant } from "../contexts/AIAssistantContext";
import { ArrowLeft, Bug, Calculator, Check, ChevronDown, ChevronRight, Code2, Database, Download, Eye, FileText, Filter, FunctionSquare, GitBranch, Globe, GripVertical, Layers, Loader2, Pencil, Play, Plus, Save, Search, ShieldCheck, Sparkles, Terminal, Trash2, Type, Wand2, X } from "lucide-react";
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
import PythonNode, { PYTHON_NODE_COLOR } from "../components/mapping/PythonNode";
import AiTransformNode, { AI_NODE_COLOR } from "../components/mapping/AiTransformNode";
import ExprNode, { EXPR_NODE_COLOR } from "../components/mapping/ExprNode";
import DataQualityNode, { DQ_NODE_COLOR } from "../components/mapping/DataQualityNode";
import ParamsNode, { PARAMS_NODE_COLOR } from "../components/mapping/ParamsNode";
import PreviewPanel from "../components/mapping/PreviewPanel";
import DebugPanel from "../components/mapping/DebugPanel";
import CanvasMinimap from "../components/mapping/CanvasMinimap";
import NodePaletteModal from "../components/mapping/NodePaletteModal";
import { ExportModal, ContextMenu, TargetConfig, TargetAddField } from "../components/mapping/ExportModal";
import { FieldPickerModal, TargetConfigModal } from "../components/mapping/Modals";

export default function MappingEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { activeProject } = useProject();
  const projectId = activeProject?.id ?? null;
  const canEdit = !activeProject || activeProject.role !== "viewer";
  const { setPageContext, setGenerateNodesCallback, setSuggestTablesCallback, triggerExplainError } = useAIAssistant();

  const [name, setName] = useState("Neues Mapping");
  const [saving, setSaving] = useState(false);
  const [showJoinList, setShowJoinList] = useState(false);
  const [allDatasets, setAllDatasets] = useState([]);
  const [targetColumnTypes, setTargetColumnTypes] = useState({});
  const [dbConnections, setDbConnections] = useState([]);
  const [pluginTargetTypes, setPluginTargetTypes] = useState([]);
  const [previewDataset, setPreviewDataset] = useState(null);
  const [canvasNodes, setCanvasNodes] = useState([]);
  const [tableRelationships, setTableRelationships] = useState<{from_table: string; from_col: string; to_table: string; to_col: string}[]>([]);
  const [targets, setTargets] = useState([]); // multi-target array
  const [activeTargetId, setActiveTargetId] = useState(null); // which target is selected
  const [showNewTarget, setShowNewTarget] = useState(false); // new target wizard
  const [editingTargetId, setEditingTargetId] = useState(null); // target config editor
  const [joins, setJoins] = useState([]);
  const [autoJoinNotice, setAutoJoinNotice] = useState(null); // { joins: [...], timeout }
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
  const [pythonNodes, setPythonNodes] = useState([]);
  const pythonOutputRefs = useRef({});
  const [aiNodes, setAiNodes] = useState([]);
  const aiOutputRefs = useRef({});
  const [exprNodes, setExprNodes] = useState([]);
  const exprOutputRefs = useRef({});
  const [qualityNodes, setQualityNodes] = useState([]);
  const [paramNodes, setParamNodes] = useState([]);
  const paramOutputRefs = useRef({});
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
  const [editingDefault, setEditingDefault] = useState(null); // { idx, value }
  const [debugTrace, setDebugTrace] = useState(null);  // null = hidden, object = showing
  const [debugLoading, setDebugLoading] = useState(false);
  const [debugActiveStageId, setDebugActiveStageId] = useState(null);
  const [debugSelectedRowIdx, setDebugSelectedRowIdx] = useState(null);
  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiSuggestOpen, setAiSuggestOpen] = useState(false);
  const [activeNodeId, setActiveNodeId] = useState<string | null>(null);
  const [activeNodeInfo, setActiveNodeInfo] = useState<any>(null);

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
  const insertSuggestedTablesRef = useRef<((result: any) => Promise<void>) | null>(null);
  const insertSuggestedTables = useCallback(async ({ tables, joins: suggestedJoins }: any) => {
    const newNodes: any[] = [];
    const allNodes = [...canvasNodes];
    for (const t of tables) {
      if (t.already_exists && t.dataset_id) {
        const ds = allDatasets.find((d: any) => d.id === t.dataset_id);
        if (ds && !allNodes.find((n: any) => n.dataset_id === ds.id) && !newNodes.find((n: any) => n.dataset_id === ds.id)) {
          newNodes.push({ dataset_id: ds.id, dataset_name: ds.name, dataset_columns: ds.columns || [], dataset_column_types: ds.column_types || {}, dataset_file_type: ds.file_type, dataset_row_count: ds.row_count || 0, x: 80 + newNodes.length * 280, y: 100 });
        }
      } else {
        const conn = dbConnections.find((c: any) => c.id === t.connection_id) || dbConnections[0];
        if (conn) {
          try {
            const sql = t.schema && t.schema.toLowerCase() !== "dbo"
              ? `SELECT * FROM [${t.schema}].[${t.name}]`
              : `SELECT * FROM [${t.name}]`;
            const { data } = await api.post(`/api/connections/${conn.id}/import`, { sql, dataset_name: t.full_name || t.name, project_id: projectId });
            newNodes.push({ dataset_id: data.id, dataset_name: data.name, dataset_columns: data.columns || [], dataset_column_types: {}, dataset_file_type: conn.db_type ? `db_${conn.db_type}` : "db_mssql", dataset_row_count: 0, x: 80 + newNodes.length * 280, y: 100 });
          } catch (e) { console.error("Import fehlgeschlagen:", t.name, e); }
        }
      }
    }
    if (newNodes.length > 0) setCanvasNodes(prev => [...prev, ...newNodes]);
    const allAfter = [...allNodes, ...newNodes];
    if (suggestedJoins?.length > 0) {
      const newJoins = suggestedJoins.map((j: any) => {
        const findNode = (fullName: string) => allAfter.find((n: any) => n.dataset_name === fullName || n.dataset_name === fullName.split(".").pop());
        const left = findNode(j.from_table);
        const right = findNode(j.to_table);
        if (!left || !right) return null;
        return { left_dataset_id: left.dataset_id, left_field: j.from_col, right_dataset_id: right.dataset_id, right_field: j.to_col, join_type: "INNER JOIN" };
      }).filter(Boolean);
      if (newJoins.length > 0) setJoins(prev => [...prev, ...newJoins]);
    }
    setTimeout(triggerLineDraw, 300);
  // triggerLineDraw bewusst nicht im Dep-Array (stabile leere Deps, sonst TDZ weil später deklariert)
  }, [canvasNodes, allDatasets, dbConnections, projectId]); // eslint-disable-line react-hooks/exhaustive-deps

  insertSuggestedTablesRef.current = insertSuggestedTables;

  useEffect(() => {
    setSuggestTablesCallback((result: any) => insertSuggestedTablesRef.current?.(result));
    return () => setSuggestTablesCallback(null);
  }, [setSuggestTablesCallback]);

  const [filterEditor, setFilterEditor] = useState(null);
  const [openGroups, setOpenGroups] = useState({ transform: true, query: true, calc: true, logic: true });
  const toggleGroup = (id) => setOpenGroups(prev => ({ ...prev, [id]: !prev[id] }));
  const [paletteInfo, setPaletteInfo] = useState(null);

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

  const [lineTick, setLineTick] = useState(0);
  const allSourceFieldsFlat = canvasNodes.flatMap((n) => n.dataset_columns || []);
  const triggerLineDraw = useCallback(() => setLineTick((t) => t + 1), []);

  const insertGeneratedNodes = useCallback((result: { nodes: any[]; explanation: string }) => {
    const rawNodes = result?.nodes;
    if (!Array.isArray(rawNodes) || rawNodes.length === 0) return;

    const allYs = [
      ...canvasNodes.map(n => (n.y || 0) + 250),
      ...transformNodes.map(n => n.y || 0),
      ...constantNodes.map(n => n.y || 0),
      ...aggNodes.map(n => n.y || 0),
      ...calcNodes.map(n => n.y || 0),
      ...lookupNodes.map(n => n.y || 0),
      ...pythonNodes.map(n => n.y || 0),
      ...aiNodes.map(n => n.y || 0),
      ...exprNodes.map(n => n.y || 0),
      ...qualityNodes.map(n => n.y || 0),
    ];
    const startY = allYs.length > 0 ? Math.max(...allYs) + 80 : 400;
    const newId = () => Math.random().toString(36).slice(2, 9);
    const pos = (idx: number) => ({
      x: 80 + (idx % 4) * 240,
      y: startY + Math.floor(idx / 4) * 190,
    });

    const newTransforms: any[] = [];
    const newConstants: any[] = [];
    const newAggs: any[] = [];
    const newCalcs: any[] = [];
    const newLookups: any[] = [];
    const newPython: any[] = [];
    const newExprs: any[] = [];
    const newQuality: any[] = [];

    rawNodes.forEach((n: any, idx: number) => {
      const { x, y } = pos(idx);
      switch (n.node_type) {
        case "transform":
          newTransforms.push({
            id: newId(), x, y,
            type: n.transform_type || "text_trim",
            config: defaultConfig(n.transform_type || "text_trim"),
            inputs: n.input_field ? [{ source_field: n.input_field }] : [],
            output_field: n.output_field || `transform_${Date.now()}`,
          });
          break;
        case "constant":
          newConstants.push({
            id: newId(), x, y,
            const_type: n.const_type || "static_text",
            const_value: n.const_value || "",
            output_field: n.output_field || `konstante_${Date.now()}`,
          });
          break;
        case "agg":
          newAggs.push({ id: newId(), x, y, fields: n.fields || [] });
          break;
        case "calc":
          newCalcs.push({
            id: newId(), x, y,
            calc_type: n.calc_type || "cumsum",
            input_field: n.input_field || "",
            output_field: n.output_field || `calc_${Date.now()}`,
            order_field: n.order_field || "",
            order_dir: n.order_dir || "asc",
            group_field: n.group_field || "",
            window_size: n.window_size || 3,
          });
          break;
        case "lookup": {
          const dsMatch = allDatasets.find((d: any) => d.name === n.lookup_dataset_name);
          newLookups.push({
            id: newId(), x, y,
            input_field: n.input_field || "",
            lookup_dataset_id: dsMatch?.id ?? null,
            lookup_key_col: n.lookup_key_col || "",
            on_missing: "null",
            output_mappings: n.output_mappings || [],
          });
          break;
        }
        case "python":
          newPython.push({ id: newId(), x, y, script: n.script || "", output_fields: n.output_fields || [] });
          break;
        case "expr":
          newExprs.push({ id: newId(), x, y, label: n.label || "Expression", output_fields: n.output_fields || [] });
          break;
        case "data_quality":
          newQuality.push({ id: newId(), x, y, label: n.label || "Datenqualität", rules: n.rules || [] });
          break;
      }
    });

    if (newTransforms.length) setTransformNodes(prev => [...prev, ...newTransforms]);
    if (newConstants.length) setConstantNodes(prev => [...prev, ...newConstants]);
    if (newAggs.length) setAggNodes(prev => [...prev, ...newAggs]);
    if (newCalcs.length) setCalcNodes(prev => [...prev, ...newCalcs]);
    if (newLookups.length) setLookupNodes(prev => [...prev, ...newLookups]);
    if (newPython.length) setPythonNodes(prev => [...prev, ...newPython]);
    if (newExprs.length) setExprNodes(prev => [...prev, ...newExprs]);
    if (newQuality.length) setQualityNodes(prev => [...prev, ...newQuality]);
    setTimeout(triggerLineDraw, 100);
  }, [canvasNodes, transformNodes, constantNodes, aggNodes, calcNodes, lookupNodes, pythonNodes, exprNodes, qualityNodes, allDatasets, triggerLineDraw]);

  const insertGeneratedNodesRef = useRef<any>(null);
  useEffect(() => {
    insertGeneratedNodesRef.current = insertGeneratedNodes;
  }, [insertGeneratedNodes]);

  useEffect(() => {
    setGenerateNodesCallback((result: any) => insertGeneratedNodesRef.current?.(result));
    return () => setGenerateNodesCallback(null);
  }, [setGenerateNodesCallback]);

  useEffect(() => {
    const dbDatasetIds = canvasNodes
      .filter((n: any) => n.dataset_id && n.dataset_file_type && n.dataset_file_type.startsWith("db_"))
      .map((n: any) => n.dataset_id);
    if (dbDatasetIds.length < 2) {
      setTableRelationships([]);
      return;
    }
    api.post("/api/ai/mapping-context", { dataset_ids: dbDatasetIds })
      .then(({ data }) => setTableRelationships(data.relationships || []))
      .catch(() => setTableRelationships([]));
  }, [canvasNodes]);

  useEffect(() => {
    setPageContext({
      page: "mapping_editor",
      title: name || "Mapping Editor",
      description: "Visueller ETL-Mapping-Editor: Datasets verbinden, transformieren, filtern, sortieren und in Zieldatenbanken schreiben.",
      currentData: {
        mappingId: id ?? null,
        mappingName: name,
        canvasDatasets: canvasNodes.map(n => ({
          id: n.dataset_id,
          name: n.dataset_name,
          columns: (n.dataset_columns || []).slice(0, 20).map((c: any) => (typeof c === "string" ? c : c.name || "")),
        })),
        connectionIds: [...new Set(
          canvasNodes
            .map((n: any) => allDatasets.find((d: any) => d.id === n.dataset_id)?.source_connection_id)
            .filter(Boolean)
        )],
        ...(tableRelationships.length > 0 ? { tableRelationships } : {}),
        ...(activeNodeInfo ? { activeNode: activeNodeInfo } : {}),
      },
    });
    return () => setPageContext(null);
  }, [setPageContext, name, id, activeNodeInfo, canvasNodes, tableRelationships]);
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

  useEffect(() => {
    const p = projectId != null ? `?project_id=${projectId}` : "";
    const excludeParam = id && id !== "new" ? `${p ? "&" : "?"}exclude_mapping_id=${id}` : "";
    api.get(`/api/datasets/${p}${excludeParam}`).then(({ data }) => setAllDatasets(Array.isArray(data) ? data : []));
    api.get(`/api/connections/${p}`).then(({ data }) => setDbConnections(Array.isArray(data) ? data : []));
    api.get("/api/plugins/target-types").then(({ data }) => setPluginTargetTypes(Array.isArray(data) ? data : [])).catch(() => {});
    api.get("/api/ai/status").then(({ data }) => setAiEnabled(!!data?.enabled)).catch(() => {});
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
        setPythonNodes(data.python_nodes || []);
        setAiNodes(data.ai_nodes || []);
        setExprNodes(data.expr_nodes || []);
        setQualityNodes(data.quality_nodes || []);
        setParamNodes(data.param_nodes || []);
        const loadedTargets = data.targets || [];
        setTargets(loadedTargets);
        if (loadedTargets.length > 0) setActiveTargetId(loadedTargets[0].id);
      });
    }
  }, [id]);

  useEffect(() => { const t = setTimeout(triggerLineDraw, 100); return () => clearTimeout(t); }, [canvasNodes, targets, activeTargetId, joins, transformNodes, constantNodes, sqlNodes, aggNodes, restNodes, lookupNodes, calcNodes, switchNodes, pythonNodes, aiNodes, exprNodes, qualityNodes, paramNodes]);

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
    const rect = canvasRef.current.getBoundingClientRect();
    const dropX = Math.max(0, e.clientX - rect.left + canvasRef.current.scrollLeft - 80);
    const dropY = Math.max(0, e.clientY - rect.top + canvasRef.current.scrollTop - 20);

    const nodeType = e.dataTransfer.getData("node_type");
    if (nodeType) {
      const id = Math.random().toString(36).slice(2, 9);
      if (nodeType === "transform") setTransformNodes((prev) => [...prev, { id, x: dropX, y: dropY, type: "number_format", config: defaultConfig("number_format"), inputs: [], output_field: `transform_${prev.length + 1}` }]);
      else if (nodeType === "constant") setConstantNodes((prev) => [...prev, { id, x: dropX, y: dropY, const_type: "static_text", const_value: "", output_field: `konstante_${prev.length + 1}` }]);
      else if (nodeType === "sql") setSqlNodes((prev) => [...prev, { id, x: dropX, y: dropY, connection_id: null, sql: "", mode: "scalar", output_field: `sql_${prev.length + 1}` }]);
      else if (nodeType === "agg") setAggNodes((prev) => [...prev, { id, x: dropX, y: dropY, fields: [] }]);
      else if (nodeType === "rest") setRestNodes((prev) => [...prev, { id, x: dropX, y: dropY, url: "", method: "GET", input_field: "", auth: { type: "none" }, data_path: "", response_mappings: [] }]);
      else if (nodeType === "lookup") setLookupNodes((prev) => [...prev, { id, x: dropX, y: dropY, input_field: "", lookup_dataset_id: null, lookup_key_col: "", on_missing: "null", output_mappings: [] }]);
      else if (nodeType === "calc") setCalcNodes((prev) => [...prev, { id, x: dropX, y: dropY, calc_type: "cumsum", input_field: "", output_field: "", order_field: "", order_dir: "asc", group_field: "", window_size: 3 }]);
      else if (nodeType === "switch") setSwitchNodes((prev) => [...prev, { id, x: dropX, y: dropY, output_field: "", branches: [
        { id: "b1", condition: "has_rows", dataset_id: null, source_dataset_id: null, threshold: 0, label: "Wenn Daten vorhanden" },
        { id: "b2", condition: "always", dataset_id: null, source_dataset_id: null, threshold: 0, label: "Sonst (Fallback)" },
      ]}]);
      else if (nodeType === "python") setPythonNodes((prev) => [...prev, { id, x: dropX, y: dropY, script: "", output_fields: [] }]);
      else if (nodeType === "ai") setAiNodes((prev) => [...prev, { id, x: dropX, y: dropY, prompt_template: "", output_fields: [], model: null, batch_size: 10 }]);
      else if (nodeType === "expr") setExprNodes((prev) => [...prev, { id, x: dropX, y: dropY, label: "Expression", output_fields: [] }]);
      else if (nodeType === "quality") setQualityNodes((prev) => [...prev, { id, x: dropX, y: dropY, label: "Datenqualität", rules: [] }]);
      else if (nodeType === "params") setParamNodes((prev) => [...prev, { id, x: dropX, y: dropY, label: "Formular-Parameter", fields: [] }]);
      setTimeout(triggerLineDraw, 50);
      return;
    }

    const dsId = parseInt(e.dataTransfer.getData("dataset_id"));
    if (!dsId) return;
    if (canvasNodes.find((n) => n.dataset_id === dsId)) return;
    const ds = allDatasets.find((d) => d.id === dsId);
    if (!ds) return;
    const newNode = { dataset_id: ds.id, dataset_name: ds.name, dataset_columns: ds.columns || [], dataset_column_types: ds.column_types || {}, dataset_file_type: ds.file_type, dataset_row_count: ds.row_count || 0, x: Math.max(0, e.clientX - rect.left - 115), y: Math.max(0, e.clientY - rect.top - 20) };
    setCanvasNodes((prev) => [...prev, newNode]);
    _applyAutoJoins(newNode, canvasNodes);
    if (ds.file_type?.startsWith("db_")) {
      const hasSchema = Object.values(ds.column_types || {}).some(t => t?.is_primary != null);
      if (!hasSchema) {
        api.post(`/api/datasets/${ds.id}/detect-schema`).then(({ data }) => {
          if (data?.column_types) setCanvasNodes(prev => prev.map(n => n.dataset_id === ds.id ? { ...n, dataset_column_types: { ...n.dataset_column_types, ...data.column_types } } : n));
        }).catch(() => {});
      }
    }
  }, [allDatasets, canvasNodes]);

  const _applyAutoJoins = (newNode, existingNodes) => {
    const newTypes = newNode.dataset_column_types || {};
    const newPks = Object.keys(newTypes).filter(f => newTypes[f]?.is_primary);
    const newFks = Object.keys(newTypes).filter(f => newTypes[f]?.is_fk);
    const detected = [];
    for (const existing of existingNodes) {
      const et = existing.dataset_column_types || {};
      const existingPks = Object.keys(et).filter(f => et[f]?.is_primary);
      const existingFks = Object.keys(et).filter(f => et[f]?.is_fk);
      // New node FK → existing PK
      for (const fk of newFks) {
        if (existingPks.includes(fk)) detected.push({ left_dataset_id: newNode.dataset_id, left_field: fk, right_dataset_id: existing.dataset_id, right_field: fk, join_type: "INNER JOIN" });
      }
      // Existing FK → new PK
      for (const pk of newPks) {
        if (existingFks.includes(pk)) detected.push({ left_dataset_id: existing.dataset_id, left_field: pk, right_dataset_id: newNode.dataset_id, right_field: pk, join_type: "INNER JOIN" });
      }
    }
    if (detected.length === 0) return;
    setJoins(prev => {
      const fresh = detected.filter(dj => !prev.some(j => j.left_dataset_id === dj.left_dataset_id && j.right_dataset_id === dj.right_dataset_id && j.left_field === dj.left_field));
      if (fresh.length === 0) return prev;
      const notice = { count: fresh.length, names: fresh.map(j => j.left_field) };
      setAutoJoinNotice(notice);
      setTimeout(() => setAutoJoinNotice(null), 5000);
      return [...prev, ...fresh];
    });
  };

  const handlePositionChange = useCallback((dsId, x, y, toggleMinimize = false) => {
    setCanvasNodes((prev) => prev.map((n) => {
      if (n.dataset_id !== dsId) return n;
      if (toggleMinimize) return { ...n, minimized: !n.minimized };
      return { ...n, x, y };
    }));
    triggerLineDraw();
  }, [triggerLineDraw]);

  const handleNodeResize = useCallback((dsId, width, height) => {
    setCanvasNodes((prev) => prev.map((n) => n.dataset_id !== dsId ? n : { ...n, width, height }));
    triggerLineDraw();
  }, [triggerLineDraw]);

  const removeNode = useCallback((dsId) => {
    setCanvasNodes((prev) => prev.filter((n) => n.dataset_id !== dsId));
    setTargets((prev) => prev.map((t) => ({ ...t, fields: (t.fields || []).filter((c) => c.source_dataset_id !== dsId) })));
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

  const applyDefaultValue = (idx, value) => {
    setEditingDefault(null);
    setConnections((prev) => prev.map((c, i) => i === idx ? { ...c, default_value: value === "" ? undefined : value } : c));
  };

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
      const payload = { name, canvas_nodes: canvasNodes, joins, transform_nodes: transformNodes, constant_nodes: constantNodes, sql_nodes: sqlNodes, agg_nodes: aggNodes, rest_nodes: restNodes, lookup_nodes: lookupNodes, calc_nodes: calcNodes, switch_nodes: switchNodes, python_nodes: pythonNodes, ai_nodes: aiNodes, expr_nodes: exprNodes, quality_nodes: qualityNodes, param_nodes: paramNodes, targets, project_id: projectId };
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
  const [runErrorBanner, setRunErrorBanner] = useState<{ errors: string[]; detail?: string } | null>(null);
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
      python_nodes:    pythonNodes,
      ai_nodes:        aiNodes,
      expr_nodes:      exprNodes,
      quality_nodes:   qualityNodes,
      param_nodes:     paramNodes,
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
        if (!abortRef.current) {
          const detail = e.response?.data?.detail || e.message || "Unbekannter Fehler";
          errors.push({ label: `"${target.name}"`, detail });
        }
      } finally {
        done++;
        setExecuteStatus({ done, total, errors: errors.map(e => `${e.label}: ${e.detail}`) });
      }
    }));

    setIsExecuting(false);
    if (errors.length) {
      setRunErrorBanner({ errors: errors.map(e => e.label), detail: errors.map(e => `${e.label}:\n${e.detail}`).join("\n\n") });
    }
    setTimeout(() => setExecuteStatus(null), 2000);
  };

  const cancelAll = () => { setPendingSource(null); setPendingJoin(null); setDragJoin(null); setEditingConnection(null); setContextMenu(null); setActiveNodeId(null); setActiveNodeInfo(null); };

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
          python_nodes: pythonNodes, ai_nodes: aiNodes, expr_nodes: exprNodes, quality_nodes: qualityNodes,
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

  const handleDebugRun = async () => {
    setDebugLoading(true);
    setDebugTrace(null);
    setDebugActiveStageId(null);
    setDebugSelectedRowIdx(null);
    try {
      const payload = {
        canvas_nodes: canvasNodes, joins,
        transform_nodes: transformNodes, constant_nodes: constantNodes,
        sql_nodes: sqlNodes, agg_nodes: aggNodes, rest_nodes: restNodes,
        lookup_nodes: lookupNodes, calc_nodes: calcNodes, switch_nodes: switchNodes,
        python_nodes: pythonNodes, ai_nodes: aiNodes, expr_nodes: exprNodes, quality_nodes: qualityNodes,
        targets: targets.length ? targets : undefined,
        fields: !targets.length ? connections : undefined,
      };
      const { data } = await api.post("/api/mappings/debug-run", payload);
      setDebugTrace(data);
      // Fehler aus Debug-Trace in Banner zeigen
      const traceErrors = (data?.result?.errors || []);
      if (traceErrors.length) {
        setRunErrorBanner({ errors: ["Debug-Run"], detail: traceErrors.join("\n") });
      }
    } catch (e) {
      const detail = e.response?.data?.detail || e.message;
      setRunErrorBanner({ errors: ["Debug-Run"], detail });
    } finally {
      setDebugLoading(false);
    }
  };

  // Sample-Daten + Stats pro Stage für Feld-Tooltips und Node Statistics
  const debugSamplesMap = {};
  const debugStatsMap = {};
  if (debugTrace?.trace) {
    for (const stage of debugTrace.trace) {
      debugStatsMap[stage.id] = { rows_in: stage.rows_in, rows_out: stage.rows_out, errors: stage.errors, duration_ms: stage.duration_ms };
      if (stage.type === "dataset" && stage.id?.startsWith("dataset_")) {
        const dsId = parseInt(stage.id.split("_")[1]);
        if (!isNaN(dsId)) debugSamplesMap[dsId] = stage.sample || [];
      }
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh", backgroundColor: S.bgMain }}>

      {/* Fehler-Banner mit KI-Erklären Button */}
      {runErrorBanner && (
        <div style={{
          position: "fixed", bottom: 24, right: 24, zIndex: 9999,
          backgroundColor: S.bgCard, border: "1px solid rgba(248,113,113,0.4)",
          borderRadius: 10, padding: "14px 18px", boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
          display: "flex", alignItems: "flex-start", gap: 12, maxWidth: 460,
        }}>
          <span style={{ fontSize: 18, flexShrink: 0 }}>✗</span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <p style={{ fontSize: 13, fontWeight: 600, color: "#f87171", margin: 0 }}>
              Fehler beim Ausführen
            </p>
            <p style={{ fontSize: 11, color: S.textDim, margin: "2px 0 8px", wordBreak: "break-word" }}>
              {runErrorBanner.errors.join(", ")}
            </p>
            <button
              onClick={() => { triggerExplainError(runErrorBanner.detail || runErrorBanner.errors.join("\n")); setRunErrorBanner(null); }}
              style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, padding: "5px 10px",
                borderRadius: 5, cursor: "pointer", backgroundColor: "rgba(167,139,250,0.15)",
                border: "1px solid rgba(167,139,250,0.4)", color: "#a78bfa" }}>
              <Sparkles size={11} /> KI: Fehler erklären
            </button>
          </div>
          <button onClick={() => setRunErrorBanner(null)}
            style={{ background: "none", border: "none", cursor: "pointer", color: S.textDim, fontSize: 16, flexShrink: 0 }}>
            ×
          </button>
        </div>
      )}

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

          {/* Debug-Run Button */}
          <button onClick={handleDebugRun} disabled={debugLoading} title="Debug-Run: Pipeline-Trace mit Zeilenzahlen pro Stufe"
            style={{ display: "flex", alignItems: "center", gap: 5, padding: "6px 11px", borderRadius: 4, border: `1px solid ${debugTrace ? "#818cf866" : S.border}`, background: debugTrace ? "rgba(129,140,248,0.1)" : "none", color: debugTrace ? "#818cf8" : S.textDim, fontSize: 11, cursor: debugLoading ? "not-allowed" : "pointer", opacity: debugLoading ? 0.6 : 1 }}
            onMouseEnter={e => { if (!debugLoading) { e.currentTarget.style.color = "#818cf8"; e.currentTarget.style.borderColor = "#818cf866"; } }}
            onMouseLeave={e => { if (!debugTrace) { e.currentTarget.style.color = S.textDim; e.currentTarget.style.borderColor = S.border; } }}>
            {debugLoading ? <Loader2 size={13} className="animate-spin" /> : <Bug size={13} />} Debug
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
          {/* Node Palette Accordion */}
          <div style={{ borderTop: `1px solid ${S.border}`, flexShrink: 0, overflowY: "auto", scrollbarWidth: "thin" }}>
            {[
              {
                id: "transform", label: "Transformation",
                items: [
                  canEdit && { type: "transform", Icon: Wand2,      color: "#818cf8", title: "Transform Node",  onAdd: () => { const id = Math.random().toString(36).slice(2,9); setTransformNodes(prev => [...prev, { id, x: 300, y: 120, type: "number_format", config: defaultConfig("number_format"), inputs: [], output_field: `transform_${prev.length+1}` }]); } },
                  {            type: "constant",  Icon: Type,       color: "#a78bfa", title: "Konstante",       onAdd: () => { const id = Math.random().toString(36).slice(2,9); setConstantNodes(prev => [...prev, { id, x: 340, y: 80+prev.length*40, const_type: "static_text", const_value: "", output_field: `konstante_${prev.length+1}` }]); } },
                ].filter(Boolean),
              },
              {
                id: "query", label: "Abfrage & Daten",
                items: [
                  { type: "sql",    Icon: Code2,      color: "#38bdf8",      title: "SQL Node",    onAdd: () => { const id = Math.random().toString(36).slice(2,9); setSqlNodes(prev => [...prev, { id, x: 360, y: 80+prev.length*50, connection_id: null, sql: "", mode: "scalar", output_field: `sql_${prev.length+1}` }]); } },
                  { type: "rest",   Icon: Globe,      color: REST_NODE_COLOR, title: "REST Node",   onAdd: () => { const id = Math.random().toString(36).slice(2,9); setRestNodes(prev => [...prev, { id, x: 420, y: 80+prev.length*60, url: "", method: "GET", input_field: "", auth: { type: "none" }, data_path: "", response_mappings: [] }]); } },
                  { type: "lookup", Icon: Search,     color: LOOKUP_COLOR,   title: "Lookup Node", onAdd: () => { const id = Math.random().toString(36).slice(2,9); setLookupNodes(prev => [...prev, { id, x: 480, y: 80+prev.length*60, input_field: "", lookup_dataset_id: null, lookup_key_col: "", on_missing: "null", output_mappings: [] }]); } },
                ],
              },
              {
                id: "calc", label: "Berechnung",
                items: [
                  { type: "agg",  Icon: Layers,     color: "#f59e0b",  title: "Aggregation", onAdd: () => { const id = Math.random().toString(36).slice(2,9); setAggNodes(prev => [...prev, { id, x: 400, y: 80+prev.length*60, fields: [] }]); } },
                  { type: "calc", Icon: Calculator,  color: CALC_COLOR, title: "Berechnung",  onAdd: () => { const id = Math.random().toString(36).slice(2,9); setCalcNodes(prev => [...prev, { id, x: 540, y: 80+prev.length*60, calc_type: "cumsum", input_field: "", output_field: "", order_field: "", order_dir: "asc", group_field: "", window_size: 3 }]); } },
                ],
              },
              {
                id: "logic", label: "Logik & Skript",
                items: [
                  { type: "switch",  Icon: GitBranch,      color: SWITCH_COLOR,      title: "Switch Node",    onAdd: () => { const id = Math.random().toString(36).slice(2,9); setSwitchNodes(prev => [...prev, { id, x: 600, y: 80+prev.length*60, output_field: "", branches: [{ id: "b1", condition: "has_rows", dataset_id: null, source_dataset_id: null, threshold: 0, label: "Wenn Daten vorhanden" }, { id: "b2", condition: "always", dataset_id: null, source_dataset_id: null, threshold: 0, label: "Sonst (Fallback)" }] }]); } },
                  { type: "python",  Icon: Terminal,        color: PYTHON_NODE_COLOR,  title: "Python Script", onAdd: () => { const id = Math.random().toString(36).slice(2,9); setPythonNodes(prev => [...prev, { id, x: 640, y: 80+prev.length*60, script: "", output_fields: [] }]); } },
                  { type: "ai",      Icon: Sparkles,        color: AI_NODE_COLOR,      title: "KI-Transform",  onAdd: () => { const id = Math.random().toString(36).slice(2,9); setAiNodes(prev => [...prev, { id, x: 640, y: 80+prev.length*60, prompt_template: "", output_fields: [], model: null, batch_size: 10 }]); } },
                  { type: "expr",    Icon: FunctionSquare,  color: EXPR_NODE_COLOR,    title: "Expression",    onAdd: () => { const id = Math.random().toString(36).slice(2,9); setExprNodes(prev => [...prev, { id, x: 680, y: 80+prev.length*60, label: "Expression", output_fields: [] }]); } },
                  { type: "quality", Icon: ShieldCheck,     color: DQ_NODE_COLOR,      title: "Datenqualität", onAdd: () => { const id = Math.random().toString(36).slice(2,9); setQualityNodes(prev => [...prev, { id, x: 720, y: 80+prev.length*60, label: "Datenqualität", rules: [] }]); } },
                  { type: "params",  Icon: Database,         color: PARAMS_NODE_COLOR,  title: "Params Node",   onAdd: () => { const id = Math.random().toString(36).slice(2,9); setParamNodes(prev => [...prev, { id, x: 760, y: 80+prev.length*60, label: "Formular-Parameter", fields: [] }]); } },
                ],
              },
            ].map(group => (
              <div key={group.id}>
                <button onClick={() => toggleGroup(group.id)}
                  style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%", padding: "6px 12px", background: "none", border: "none", borderBottom: `1px solid ${S.border}`, cursor: "pointer", color: S.textDim, fontSize: 10, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" }}
                  onMouseEnter={e => e.currentTarget.style.backgroundColor = "rgba(255,255,255,0.03)"}
                  onMouseLeave={e => e.currentTarget.style.backgroundColor = "transparent"}>
                  <span>{group.label}</span>
                  {openGroups[group.id] ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
                </button>
                {openGroups[group.id] && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 5, padding: "8px 10px", borderBottom: `1px solid ${S.border}` }}>
                    {group.items.map(item => (
                      <button key={item.type} draggable
                        onDragStart={e => e.dataTransfer.setData("node_type", item.type)}
                        onClick={() => setPaletteInfo(item)}
                        title={item.title + " – klicken für Info, ziehen zum Platzieren"}
                        style={{ width: 34, height: 34, display: "flex", alignItems: "center", justifyContent: "center", borderRadius: 6, cursor: "grab", backgroundColor: item.color + "18", border: `1px solid ${item.color}45`, color: item.color, flexShrink: 0, transition: "background-color 0.15s, border-color 0.15s" }}
                        onMouseEnter={e => { e.currentTarget.style.backgroundColor = item.color + "35"; e.currentTarget.style.borderColor = item.color + "90"; }}
                        onMouseLeave={e => { e.currentTarget.style.backgroundColor = item.color + "18"; e.currentTarget.style.borderColor = item.color + "45"; }}>
                        <item.Icon size={15} />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", overflow: "hidden", position: "relative" }}>

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
            {autoJoinNotice && (
              <div style={{ position: "absolute", top: 12, left: "50%", transform: "translateX(-50%)", zIndex: 30, padding: "6px 16px", borderRadius: 20, fontSize: 11, pointerEvents: "none", backgroundColor: "rgba(110,231,183,0.12)", border: "1px solid #6ee7b3", color: "#6ee7b3", whiteSpace: "nowrap" }}>
                🔗 {autoJoinNotice.count} Join{autoJoinNotice.count > 1 ? "s" : ""} automatisch erkannt: {autoJoinNotice.names.join(", ")}
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

              <SvgOverlay connections={connections} joins={joins} fieldRefs={fieldRefs} targetRefs={targetRefs} nodeFieldListRefs={nodeFieldListRefs} targetListRef={targetListRef} transformOutputRefs={transformOutputRefs} transformInputRefs={transformInputRefs} transformNodes={transformNodes} constantOutputRefs={constantOutputRefs} sqlOutputRefs={sqlOutputRefs} sqlNodes={sqlNodes} aggOutputRefs={aggOutputRefs} aggInputRefs={aggInputRefs} aggNodeRefs={aggNodeRefs} aggNodes={aggNodes} restOutputRefs={restOutputRefs} restInputRefs={restInputRefs} restNodes={restNodes} lookupOutputRefs={lookupOutputRefs} lookupInputRefs={lookupInputRefs} lookupNodes={lookupNodes} calcOutputRefs={calcOutputRefs} calcInputPortRefs={calcInputPortRefs} calcNodes={calcNodes} switchOutputRefs={switchOutputRefs} switchNodes={switchNodes} pythonOutputRefs={pythonOutputRefs} pythonNodes={pythonNodes} aiOutputRefs={aiOutputRefs} aiNodes={aiNodes} exprOutputRefs={exprOutputRefs} exprNodes={exprNodes} paramOutputRefs={paramOutputRefs} paramNodes={paramNodes} canvasRef={canvasRef} tick={lineTick} onJoinClick={(i) => setEditingJoin(i)} onConnectionClick={(conn, i) => setConfirmDeleteConn({ conn, index: i })} dragJoin={dragJoin} canvasNodes={canvasNodes} nodeBodyRefs={nodeBodyRefs} miniPortRefs={miniPortRefs} targetColumnTypes={targetColumnTypes} />

              {canvasNodes.map((node) => (
                <DatasetNode key={node.dataset_id} node={node} connections={connections} joins={joins}
                  onFieldClick={handleFieldClick} onFieldRightClick={handleFieldRightClick}
                  onJoinDrop={handleJoinDrop}
                  onFieldDoubleClick={handleFieldDoubleClick}
                  onFilterClick={handleFilterClick}
                  isActive={activeNodeId === String(node.dataset_id)}
                  onActivate={(info) => { setActiveNodeId(String(node.dataset_id)); setActiveNodeInfo(info); }}
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
                  onRemove={removeNode} onPositionChange={handlePositionChange} onResize={handleNodeResize} fieldRefs={fieldRefs}
                  onSortChange={(dsId, sorts) => setCanvasNodes(prev => prev.map(n => n.dataset_id === dsId ? { ...n, sorts } : n))}
                  onSchemaRefresh={(dsId, colTypes) => setCanvasNodes(prev => prev.map(n => n.dataset_id === dsId ? { ...n, dataset_column_types: { ...n.dataset_column_types, ...colTypes } } : n))}
                  debugHighlight={debugActiveStageId === `dataset_${node.dataset_id}`}
                  debugSampleRows={debugSamplesMap[node.dataset_id] || []}
                  debugSelectedRowIdx={debugSelectedRowIdx}
                  debugStats={debugStatsMap[`dataset_${node.dataset_id}`]}
                />
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
                    debugHighlight={debugActiveStageId === "transform"}
                    debugStats={debugStatsMap["transform"]}
                    isActive={activeNodeId === tn.id}
                    onActivate={(info) => { setActiveNodeId(tn.id); setActiveNodeInfo(info); }}
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
                    isActive={activeNodeId === cn.id}
                    onActivate={(info) => { setActiveNodeId(cn.id); setActiveNodeInfo(info); }}
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
                    aiEnabled={aiEnabled}
                    mappingId={id && id !== "new" ? parseInt(id) : null}
                    isActive={activeNodeId === sn.id}
                    onActivate={(info) => { setActiveNodeId(sn.id); setActiveNodeInfo(info); }}
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
                    debugHighlight={debugActiveStageId === "agg"}
                    debugStats={debugStatsMap["agg"]}
                    isActive={activeNodeId === an.id}
                    onActivate={(info) => { setActiveNodeId(an.id); setActiveNodeInfo(info); }}
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
                    isActive={activeNodeId === sn.id}
                    onActivate={(info) => { setActiveNodeId(sn.id); setActiveNodeInfo(info); }}
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
                    debugHighlight={debugActiveStageId === "calc"}
                    debugStats={debugStatsMap["calc"]}
                    isActive={activeNodeId === cn.id}
                    onActivate={(info) => { setActiveNodeId(cn.id); setActiveNodeInfo(info); }}
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
                    isActive={activeNodeId === ln.id}
                    onActivate={(info) => { setActiveNodeId(ln.id); setActiveNodeInfo(info); }}
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
                    isActive={activeNodeId === rn.id}
                    onActivate={(info) => { setActiveNodeId(rn.id); setActiveNodeInfo(info); }}
                  />
                );
              })}

              {pythonNodes.map((pn) => (
                <PythonNode key={pn.id} node={pn}
                  outputRefs={pythonOutputRefs}
                  onPositionChange={(id, x, y) => { setPythonNodes(prev => prev.map(n => n.id === id ? { ...n, x, y } : n)); triggerLineDraw(); }}
                  onUpdate={(updated) => { setPythonNodes(prev => prev.map(n => n.id === updated.id ? updated : n)); setTimeout(triggerLineDraw, 30); }}
                  onRemove={(id) => { setPythonNodes(prev => prev.filter(n => n.id !== id)); setConnections(prev => prev.filter(c => c.source_dataset_id !== "__python__" + id)); }}
                  debugHighlight={debugActiveStageId === "python"}
                  debugStats={debugStatsMap["python"]}
                  aiEnabled={aiEnabled}
                  mappingId={id && id !== "new" ? parseInt(id) : null}
                  isActive={activeNodeId === pn.id}
                  onActivate={(info) => { setActiveNodeId(pn.id); setActiveNodeInfo(info); }}
                />
              ))}

              {exprNodes.map((en) => (
                <ExprNode key={en.id} node={en}
                  outputRefs={exprOutputRefs}
                  onPositionChange={(id, x, y) => { setExprNodes(prev => prev.map(n => n.id === id ? { ...n, x, y } : n)); triggerLineDraw(); }}
                  onUpdate={(updated) => { setExprNodes(prev => prev.map(n => n.id === updated.id ? updated : n)); setTimeout(triggerLineDraw, 30); }}
                  onRemove={(id) => { setExprNodes(prev => prev.filter(n => n.id !== id)); setConnections(prev => prev.filter(c => c.source_dataset_id !== "__expr__" + id)); }}
                  debugHighlight={debugActiveStageId === "expr"}
                  debugStats={debugStatsMap["expr"]}
                  aiEnabled={aiEnabled}
                  mappingId={id && id !== "new" ? parseInt(id) : null}
                  isActive={activeNodeId === en.id}
                  onActivate={(info) => { setActiveNodeId(en.id); setActiveNodeInfo(info); }}
                />
              ))}

              {qualityNodes.map((qn) => (
                <DataQualityNode key={qn.id} node={qn}
                  onPositionChange={(id, x, y) => { setQualityNodes(prev => prev.map(n => n.id === id ? { ...n, x, y } : n)); triggerLineDraw(); }}
                  onUpdate={(updated) => { setQualityNodes(prev => prev.map(n => n.id === updated.id ? updated : n)); }}
                  onRemove={(id) => { setQualityNodes(prev => prev.filter(n => n.id !== id)); }}
                  debugHighlight={debugActiveStageId === "quality"}
                  debugStats={debugStatsMap["quality"]}
                  isActive={activeNodeId === qn.id}
                  onActivate={(info) => { setActiveNodeId(qn.id); setActiveNodeInfo(info); }}
                />
              ))}

              {paramNodes.map((pn) => (
                <ParamsNode key={pn.id} node={pn}
                  outputRefs={paramOutputRefs}
                  onPositionChange={(id, x, y) => { setParamNodes(prev => prev.map(n => n.id === id ? { ...n, x, y } : n)); triggerLineDraw(); }}
                  onUpdate={(updated) => { setParamNodes(prev => prev.map(n => n.id === updated.id ? updated : n)); setTimeout(triggerLineDraw, 30); }}
                  onRemove={(id) => { setParamNodes(prev => prev.filter(n => n.id !== id)); setConnections(prev => prev.filter(c => c.source_dataset_id !== "__params__" + id)); }}
                  isActive={activeNodeId === pn.id}
                  onActivate={(info) => { setActiveNodeId(pn.id); setActiveNodeInfo(info); }}
                />
              ))}

              {aiNodes.map((an) => (
                <AiTransformNode key={an.id} node={an}
                  outputRefs={aiOutputRefs}
                  availableFields={canvasNodes.flatMap(n =>
                    (n.dataset_columns || []).map(col => ({
                      name: col,
                      type: n.dataset_column_types?.[col]?.type || "string",
                      dataset: n.dataset_name,
                    }))
                  )}
                  onPositionChange={(id, x, y) => { setAiNodes(prev => prev.map(n => n.id === id ? { ...n, x, y } : n)); triggerLineDraw(); }}
                  onUpdate={(updated) => { setAiNodes(prev => prev.map(n => n.id === updated.id ? updated : n)); setTimeout(triggerLineDraw, 30); }}
                  onRemove={() => { setAiNodes(prev => prev.filter(n => n.id !== an.id)); setConnections(prev => prev.filter(c => c.source_dataset_id !== "__ai__" + an.id)); }}
                  debugHighlight={debugActiveStageId === "ai"}
                  isActive={activeNodeId === an.id}
                  onActivate={() => { setActiveNodeId(an.id); setActiveNodeInfo(null); }}
                />
              ))}

            </div>

            <CanvasMinimap
              canvasRef={canvasRef}
              canvasNodes={canvasNodes}
              transformNodes={transformNodes}
              constantNodes={constantNodes}
              sqlNodes={sqlNodes}
              aggNodes={aggNodes}
              restNodes={restNodes}
              lookupNodes={lookupNodes}
              calcNodes={calcNodes}
              switchNodes={switchNodes}
              pythonNodes={pythonNodes}
              aiNodes={aiNodes}
              exprNodes={exprNodes}
              qualityNodes={qualityNodes}
              paramNodes={paramNodes}
              tick={lineTick}
            />
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
            pythonNodes={pythonNodes}
            aiNodes={aiNodes}
            exprNodes={exprNodes}
            qualityNodes={qualityNodes}
            paramNodes={paramNodes}
            targets={targets}
          />

          {/* Debug Panel */}
          {debugTrace && (
            <DebugPanel
              trace={debugTrace.trace || []}
              totalDurationMs={debugTrace.total_duration_ms || 0}
              errors={debugTrace.result?.errors || []}
              activeStageId={debugActiveStageId}
              onStageSelect={setDebugActiveStageId}
              selectedRowIdx={debugSelectedRowIdx}
              onRowSelect={setDebugSelectedRowIdx}
              onClose={() => { setDebugTrace(null); setDebugActiveStageId(null); setDebugSelectedRowIdx(null); }}
            />
          )}
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
                  const dsId = srcDsId.startsWith("__transform__") || srcDsId.startsWith("__const__") || srcDsId.startsWith("__sql__") || srcDsId.startsWith("__agg__") || srcDsId.startsWith("__params__") ? srcDsId : parseInt(srcDsId);
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
                          const srcDsId = srcDsIdRaw.startsWith("__transform__") || srcDsIdRaw.startsWith("__const__") || srcDsIdRaw.startsWith("__sql__") || srcDsIdRaw.startsWith("__agg__") || srcDsIdRaw.startsWith("__rest__") || srcDsIdRaw.startsWith("__lookup__") || srcDsIdRaw.startsWith("__calc__") || srcDsIdRaw.startsWith("__switch__") || srcDsIdRaw.startsWith("__params__") ? srcDsIdRaw : parseInt(srcDsIdRaw);
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
                      <div style={{ marginLeft: 22, marginTop: 2 }}>
                        {srcField ? (
                          conn.transformer?.type === "formula" ? (
                            <span style={{ fontSize: 9, fontFamily: "monospace", color: S.textDim, fontStyle: "italic" }}>ƒ {conn.transformer.formula?.slice(0, 28)}{(conn.transformer.formula?.length || 0) > 28 ? "…" : ""}</span>
                          ) : conn.transformer?.type === "constant" ? (
                            <span style={{ fontSize: 9, fontFamily: "monospace", color: S.textDim }}>= „{conn.transformer.constant_value}"</span>
                          ) : (
                            <span style={{ fontSize: 9, fontFamily: "monospace", color: S.textDim, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", display: "block" }}>← {srcField}</span>
                          )
                        ) : editingDefault?.idx === idx ? (
                          <div style={{ display: "flex", alignItems: "center", gap: 4 }} onClick={(e) => e.stopPropagation()}>
                            <span style={{ fontSize: 9, color: S.textDim, fontFamily: "monospace", flexShrink: 0 }}>=</span>
                            <input
                              autoFocus
                              value={editingDefault.value}
                              onChange={(e) => setEditingDefault((d) => ({ ...d, value: e.target.value }))}
                              onBlur={() => applyDefaultValue(idx, editingDefault.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter") applyDefaultValue(idx, editingDefault.value);
                                if (e.key === "Escape") setEditingDefault(null);
                                e.stopPropagation();
                              }}
                              placeholder="Standardwert…"
                              style={{ flex: 1, background: "rgba(255,255,255,0.08)", border: "1px solid #6ee7b755", borderRadius: 3, color: "#6ee7b7", fontFamily: "monospace", fontSize: 9, padding: "1px 4px", outline: "none" }}
                            />
                          </div>
                        ) : conn.default_value != null && conn.default_value !== "" ? (
                          <span
                            style={{ fontSize: 9, fontFamily: "monospace", color: "#6ee7b7", cursor: "pointer" }}
                            onClick={(e) => { e.stopPropagation(); setEditingDefault({ idx, value: conn.default_value }); }}
                            title="Standardwert bearbeiten">
                            = „{conn.default_value}"
                          </span>
                        ) : (
                          <button
                            onClick={(e) => { e.stopPropagation(); setEditingDefault({ idx, value: "" }); }}
                            style={{ fontSize: 9, color: S.textDim, background: "none", border: "none", cursor: "pointer", padding: 0, fontFamily: "monospace" }}
                            onMouseEnter={(e) => { e.currentTarget.style.color = "#6ee7b7"; }}
                            onMouseLeave={(e) => { e.currentTarget.style.color = S.textDim; }}
                            title="Standardwert setzen (wird verwendet wenn kein Quellfeld verbunden)">
                            + Standard
                          </button>
                        )}
                      </div>
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
                    const srcDsId = srcDsIdRaw.startsWith("__transform__") || srcDsIdRaw.startsWith("__const__") || srcDsIdRaw.startsWith("__sql__") || srcDsIdRaw.startsWith("__agg__") || srcDsIdRaw.startsWith("__rest__") || srcDsIdRaw.startsWith("__lookup__") || srcDsIdRaw.startsWith("__calc__") || srcDsIdRaw.startsWith("__switch__") || srcDsIdRaw.startsWith("__params__") ? srcDsIdRaw : parseInt(srcDsIdRaw);
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

      {/* Node Palette Info Modal */}
      <NodePaletteModal info={paletteInfo} onClose={() => setPaletteInfo(null)} />
    </div>
  );
}
