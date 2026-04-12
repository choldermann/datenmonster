import { useState, useEffect, useRef, useCallback } from "react";
import { createPortal } from "react-dom";
import { useNavigate, useParams } from "react-router-dom";
import { useProject } from "../context/ProjectContext";
import api from "../api/client";

import { S } from "../components/pipeline/constants";
import PipelineHeader from "../components/pipeline/PipelineHeader";
import PipelineToolbar from "../components/pipeline/PipelineToolbar";
import PipelineSvgOverlay from "../components/pipeline/SvgOverlay";
import TriggerNode from "../components/pipeline/nodes/TriggerNode";
import FtpNode from "../components/pipeline/nodes/FtpNode";
import DispatcherNode from "../components/pipeline/nodes/DispatcherNode";
import MappingNode from "../components/pipeline/nodes/MappingNode";
import { FtpUploadNode, EmailNode } from "../components/pipeline/nodes/OutputNodes";
import RestFetchNode from "../components/pipeline/nodes/RestFetchNode";

function genId() { return Math.random().toString(36).slice(2, 9); }

const DEFAULT_NODE_CONFIGS = {
  trigger:    { mode: "daily", time: "06:00", intervalMin: 0, cron: "0 6 * * *" },
  ftp:        { after_import: "nothing" },
  rest_fetch: { on_error: "stop" },
  dispatcher: { condition_mode: "AND", conditions: [] },
  mapping:    { on_error: "stop" },
  ftp_upload: { remote_dir: "/" },
  email:      { send_on: "always" },
};

export default function PipelineEditor() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { activeProject } = useProject();
  const projectId = activeProject?.id ?? null;

  // ── State ──────────────────────────────────────────────────────────────────
  const [name, setName] = useState("Neue Pipeline");
  const [nodes, setNodes] = useState([]);
  const [connections, setConnections] = useState([]);
  const [saving, setSaving] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [lineTick, setLineTick] = useState(0);
  const [confirmDeleteConn, setConfirmDeleteConn] = useState(null);

  // Externe Daten
  const [ftpSources, setFtpSources] = useState([]);
  const [mappings, setMappings] = useState([]);
  const [xmlDatasets, setXmlDatasets] = useState([]);
  const [restSources, setRestSources] = useState([]);

  // Refs
  const canvasRef = useRef(null);
  const nodeRefs = useRef({}); // nodeId_portId_side → DOM element ref
  const pendingConn = useRef(null); // { from_node, from_port }

  const triggerLineDraw = useCallback(() => setLineTick(t => t + 1), []);

  // ── Laden ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    const p = projectId ? `?project_id=${projectId}` : "";
    Promise.all([
      api.get(`/api/ftp-sources/${p}`),
      api.get(`/api/mappings/${p}`),
      api.get(`/api/datasets/${p}`),
      api.get(`/api/rest-sources/${p}`),
    ]).then(([ftpRes, mapRes, dsRes, restRes]) => {
      setFtpSources(ftpRes.data || []);
      setMappings(Array.isArray(mapRes.data) ? mapRes.data : []);
      setXmlDatasets((Array.isArray(dsRes.data) ? dsRes.data : []).filter(d => d.file_type === "xml" && d.xml_configured === 1));
      setRestSources(Array.isArray(restRes.data) ? restRes.data : []);
    });

    if (id && id !== "new") {
      api.get(`/api/pipelines/${id}`).then(({ data }) => {
        setName(data.name || "Pipeline");
        setNodes(data.nodes || []);
        setConnections(data.connections || []);
      });
    }
  }, [id, projectId]);

  useEffect(() => { setTimeout(triggerLineDraw, 100); }, [nodes, connections]);

  // ── Node Helpers ───────────────────────────────────────────────────────────
  const addNode = (type, x, y) => {
    const node = {
      id: genId(), type,
      x: x ?? 200 + nodes.length * 30,
      y: y ?? 150 + (nodes.length % 4) * 60,
      config: { ...DEFAULT_NODE_CONFIGS[type] },
    };
    setNodes(prev => [...prev, node]);
  };

  const updateNode = useCallback((updated) => {
    setNodes(prev => prev.map(n => n.id === updated.id ? updated : n));
    setTimeout(triggerLineDraw, 30);
  }, [triggerLineDraw]);

  const removeNode = useCallback((nodeId) => {
    setNodes(prev => prev.filter(n => n.id !== nodeId));
    setConnections(prev => prev.filter(c => c.from_node !== nodeId && c.to_node !== nodeId));
  }, []);

  const positionChange = useCallback((nodeId, x, y) => {
    setNodes(prev => prev.map(n => n.id === nodeId ? { ...n, x, y } : n));
    triggerLineDraw();
  }, [triggerLineDraw]);

  // ── Verbindungs-Drop ───────────────────────────────────────────────────────
  const handleCanvasDrop = (e) => {
    e.preventDefault();

    // Neuer Node von der Toolbar
    const newType = e.dataTransfer.getData("new_node_type");
    if (newType) {
      const canvasRect = canvasRef.current.getBoundingClientRect();
      const x = e.clientX - canvasRect.left + canvasRef.current.scrollLeft - 120;
      const y = e.clientY - canvasRect.top  + canvasRef.current.scrollTop  - 40;
      addNode(newType, Math.max(10, x), Math.max(10, y));
      return;
    }

    // Verbindung von Output-Port
    const fromNode = e.dataTransfer.getData("from_node");
    const fromPort = e.dataTransfer.getData("from_port");
    if (fromNode && fromPort) {
      pendingConn.current = { from_node: fromNode, from_port: fromPort };
    }
  };

  const handlePortDrop = (e, toNode, toPort) => {
    e.preventDefault(); e.stopPropagation();
    const fromNode = e.dataTransfer.getData("from_node");
    const fromPort = e.dataTransfer.getData("from_port");
    if (!fromNode || fromNode === toNode) return;
    // Doppelte Verbindung verhindern
    const exists = connections.find(c => c.from_node === fromNode && c.to_node === toNode && c.to_port === toPort);
    if (!exists) {
      setConnections(prev => [...prev, { from_node: fromNode, from_port: fromPort, to_node: toNode, to_port: toPort }]);
      setTimeout(triggerLineDraw, 50);
    }
  };

  const portRef = (nodeId, portId, side) => {
    const key = `${nodeId}_${portId}_${side}`;
    if (!nodeRefs.current[key]) nodeRefs.current[key] = { current: null };
    return nodeRefs.current[key];
  };

  // Shorthand – side wird aus portId abgeleitet
  const inRef  = (nodeId, portId = "in")  => portRef(nodeId, portId, "in");
  const outRef = (nodeId, portId = "out") => portRef(nodeId, portId, "out");

  // ── Speichern ──────────────────────────────────────────────────────────────
  const handleSave = async () => {
    setSaving(true);
    try {
      const payload = { name, nodes, connections, project_id: projectId };
      if (id && id !== "new") {
        await api.put(`/api/pipelines/${id}`, payload);
      } else {
        const { data } = await api.post("/api/pipelines/", payload);
        navigate(`/pipelines/${data.id}`, { replace: true });
      }
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    } finally { setSaving(false); }
  };

  // ── Ausführen ──────────────────────────────────────────────────────────────
  const [runResults, setRunResults] = useState(null); // { nodeId: { status, message, rows } }

  const handleExecute = async () => {
    if (!id || id === "new") { alert("Erst speichern!"); return; }
    setExecuting(true);
    setRunResults(null);
    try {
      const { data } = await api.post(`/api/pipelines/${id}/run`);
      // data.results: { nodeId: { status, rows, message, ... } }
      setRunResults(data.results || {});
      const errors = data.errors || [];
      if (errors.length > 0) {
        alert("Pipeline fertig – Fehler:\n" + errors.join("\n"));
      }
    } catch (e) {
      alert(e.response?.data?.detail || e.message);
    } finally { setExecuting(false); }
  };

  // ── Node rendern ───────────────────────────────────────────────────────────
  const renderNode = (node) => {
    const nodeResult = runResults?.[node.id];
    const common = { key: node.id, node, onRemove: removeNode, onPositionChange: positionChange, onUpdate: updateNode, runResult: nodeResult };
    const nInRef  = (portId = "in")  => inRef(node.id, portId);
    const nOutRef = (portId = "out") => outRef(node.id, portId);
    const onDrop  = (portId = "in")  => (e) => handlePortDrop(e, node.id, portId);

    switch (node.type) {
      case "trigger":
        return <TriggerNode {...common}
          outputPortRef={nOutRef()} />;

      case "ftp":
        return <FtpNode {...common}
          ftpSources={ftpSources}
          inputPortRef={nInRef()}
          inputPortDrop={onDrop()}
          outputPortRef={nOutRef()} />;

      case "dispatcher":
        return <DispatcherNode {...common}
          xmlDatasets={xmlDatasets}
          allNodes={nodes}
          connections={connections}
          inputPortRef={nInRef()}
          inputPortDrop={onDrop()}
          outputPortRefs={[nOutRef("match"), nOutRef("no_match")]} />;

      case "mapping":
        return <MappingNode {...common}
          mappings={mappings}
          inputPortRef={nInRef()}
          inputPortDrop={onDrop()}
          outputPortRef={nOutRef()} />;

      case "rest_fetch":
        return <RestFetchNode {...common}
          restSources={restSources}
          inputPortRef={nInRef()}
          inputPortDrop={onDrop()}
          outputPortRef={nOutRef()} />;

      case "ftp_upload":
        return <FtpUploadNode {...common}
          ftpSources={ftpSources}
          inputPortRef={nInRef()}
          inputPortDrop={onDrop()} />;

      case "email":
        return <EmailNode {...common}
          inputPortRef={nInRef()}
          inputPortDrop={onDrop()} />;

      default:
        return null;
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div style={{ height: "100vh", display: "flex", flexDirection: "column", backgroundColor: S.bgMain, color: S.textMain }}>

      <PipelineHeader
        name={name} onNameChange={setName}
        onBack={() => navigate("/dashboard", { state: { tab: "pipelines" } })}
        onSave={handleSave} onExecute={handleExecute}
        saving={saving} executing={executing}
        nodeCount={nodes.length} connCount={connections.length}
      />

      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

        <PipelineToolbar onAddNode={addNode} />

        {/* Canvas */}
        <div
          ref={canvasRef}
          onDragOver={e => e.preventDefault()}
          onDrop={handleCanvasDrop}
          style={{ flex: 1, position: "relative", overflow: "auto", backgroundImage: "radial-gradient(circle, rgba(255,255,255,0.04) 1px, transparent 1px)", backgroundSize: "24px 24px" }}
        >
          {/* Nodes */}
          {nodes.map(renderNode)}

          {/* Verbindungslinien */}
          <PipelineSvgOverlay
            connections={connections}
            nodes={nodes}
            nodeRefs={nodeRefs}
            canvasRef={canvasRef}
            tick={lineTick}
            onConnectionClick={(conn, i) => setConfirmDeleteConn({ conn, index: i })}
          />

          {/* Leerer Canvas Hinweis */}
          {nodes.length === 0 && (
            <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 12, pointerEvents: "none" }}>
              <p style={{ fontSize: 16, color: S.textDim, fontWeight: 600 }}>Pipeline Canvas</p>
              <p style={{ fontSize: 12, color: S.textDim }}>Nodes aus der linken Leiste hinzufügen</p>
            </div>
          )}
        </div>
      </div>
      {confirmDeleteConn && createPortal(
        <div onClick={() => setConfirmDeleteConn(null)} style={{
          position: "fixed", inset: 0, zIndex: 9999,
          backgroundColor: "rgba(0,0,0,0.6)",
          display: "flex", alignItems: "center", justifyContent: "center",
        }}>
          <div onClick={e => e.stopPropagation()} style={{
            background: S.bgCard, border: `1px solid ${S.border}`,
            borderRadius: 10, padding: "20px 24px", width: 360,
            boxShadow: "0 24px 60px rgba(0,0,0,0.7)",
          }}>
            <p style={{ fontSize: 14, fontWeight: 700, color: S.textBright, margin: "0 0 10px" }}>
              Verbindung entfernen
            </p>
            <p style={{ fontSize: 12, color: S.textMain, margin: "0 0 6px", fontFamily: "monospace" }}>
              {confirmDeleteConn.conn.from_node} → {confirmDeleteConn.conn.to_node}
            </p>
            <p style={{ fontSize: 11, color: S.textDim, margin: "0 0 20px" }}>
              Diese Verbindung wird aus der Pipeline entfernt.
            </p>
            <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
              <button onClick={() => setConfirmDeleteConn(null)} style={{
                fontSize: 12, padding: "7px 14px", borderRadius: 6, cursor: "pointer",
                background: "transparent", border: `1px solid ${S.border}`, color: S.textDim,
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
    </div>
  );
}
