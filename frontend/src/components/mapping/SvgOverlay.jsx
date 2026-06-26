import { Filter } from "lucide-react";
import { S, TRANSFORMER_TYPES, JOIN_TYPES, JOIN_COLOR, SQL_NODE_COLOR, AGG_COLOR } from "./constants";
import { REST_NODE_COLOR } from "./RestNode";
import { LOOKUP_COLOR } from "./LookupNode";
import { CALC_COLOR } from "./CalcNode";
import { SWITCH_COLOR } from "./SwitchNode";
import { PYTHON_NODE_COLOR } from "./PythonNode";

function SvgOverlay({ connections, joins, fieldRefs, targetRefs, nodeFieldListRefs, targetListRef, transformOutputRefs, transformInputRefs, transformNodes, constantOutputRefs, sqlOutputRefs, sqlNodes, aggOutputRefs, aggInputRefs, aggNodeRefs, aggNodes, restOutputRefs, restInputRefs, restNodes, lookupOutputRefs, lookupInputRefs, lookupNodes, calcOutputRefs, calcInputPortRefs, calcNodes, switchOutputRefs, switchNodes, pythonOutputRefs, pythonNodes, canvasRef, tick, onJoinClick, dragJoin, canvasNodes, nodeBodyRefs, miniPortRefs, onConnectionClick, targetColumnTypes }) {
  const canvasEl = canvasRef.current;
  if (!canvasEl) return null;

  // Prüft ob ein DOM-Element noch im Dokument ist (nicht detached durch Minimierung)
  const isInDOM = (el) => el && el.isConnected;

  // Gibt den Port-Dot einer minimierten Special-Node zurück
  // prefix: "transform", "calc", "agg", "sql", "switch", "lookup", "rest", "const"
  const getMiniPort = (prefix, nodeId, side) => {
    const key = `${prefix}_${nodeId}`;
    const ports = miniPortRefs?.current?.[key];
    if (!ports) return null;
    const el = side === 'right' ? ports.right : ports.left;
    return isInDOM(el) ? el : null;
  };


  // All coordinates are computed relative to the canvas element's top-left corner,
  // then offset by scrollTop/scrollLeft so they sit in SVG "content space"
  // (the SVG is position:absolute inside the scrollable canvas div).
  const canvasRect = canvasEl.getBoundingClientRect();
  const toSvg = (rect) => ({
    top:    rect.top    - canvasRect.top  + canvasEl.scrollTop,
    left:   rect.left   - canvasRect.left + canvasEl.scrollLeft,
    bottom: rect.bottom - canvasRect.top  + canvasEl.scrollTop,
    right:  rect.right  - canvasRect.left + canvasEl.scrollLeft,
    width:  rect.width,
    height: rect.height,
  });

  // Get source point, clamped to the visible field-list area of its node.
  // Also handles transform node outputs (source_dataset_id starts with __transform__)
  const getSourcePoint = (srcEl, datasetId, sourceField) => {
    // Transform node output dot → use directly, no clamping needed
    if (String(datasetId).startsWith("__transform__")) {
      const nodeId = String(datasetId).replace("__transform__", "");
      const outEl = transformOutputRefs?.current?.[nodeId]?.current;
      if (!outEl) return null;
      if (!outEl.isConnected) {
        // Detached: kurz nach Minimierung → null zurückgeben, beim nächsten tick korrekt
        return null;
      }
      const r = toSvg(outEl.getBoundingClientRect());


      return { x: r.right, y: r.top + r.height / 2, clamped: false };
    }

    // Constant node output dot
    if (String(datasetId).startsWith("__const__")) {
      const nodeId = String(datasetId).replace("__const__", "");
      const miniEl = getMiniPort("const", nodeId, "right");
      if (miniEl) {
        const r = toSvg(miniEl.getBoundingClientRect());
        return { x: r.left + r.width / 2, y: r.top + r.height / 2, clamped: false };
      }
      const outEl = constantOutputRefs?.current?.[nodeId]?.current;
      if (!isInDOM(outEl)) return null;
      const r = toSvg(outEl.getBoundingClientRect());
      return { x: r.right, y: r.top + r.height / 2, clamped: false };
    }

    // SQL node output dot
    if (String(datasetId).startsWith("__sql__")) {
      const nodeId = String(datasetId).replace("__sql__", "");
      const miniEl = getMiniPort("sql", nodeId, "right");
      if (miniEl) {
        const r = toSvg(miniEl.getBoundingClientRect());
        return { x: r.left + r.width / 2, y: r.top + r.height / 2, clamped: false };
      }
      const outEl = sqlOutputRefs?.current?.[nodeId]?.current || sqlOutputRefs?.current?.[nodeId];
      const outElR = outEl?.current || outEl;
      if (!isInDOM(outElR)) return null;
      const r = toSvg(outElR.getBoundingClientRect());
      return { x: r.right, y: r.top + r.height / 2, clamped: false };
    }

    // Switch node output dot
    if (String(datasetId).startsWith("__switch__")) {
      const nodeId = String(datasetId).replace("__switch__", "");
      const miniEl = getMiniPort("switch", nodeId, "right");
      if (miniEl) {
        const r = toSvg(miniEl.getBoundingClientRect());
        return { x: r.left + r.width / 2, y: r.top + r.height / 2, clamped: false };
      }
      const outEl = switchOutputRefs?.current?.[nodeId]?.current;
      if (!isInDOM(outEl)) return null;
      const r = toSvg(outEl.getBoundingClientRect());
      return { x: r.right, y: r.top + r.height / 2, clamped: false };
    }

    // Calc node output dot
    if (String(datasetId).startsWith("__calc__")) {
      const nodeId = String(datasetId).replace("__calc__", "");
      const miniEl = getMiniPort("calc", nodeId, "right");
      if (miniEl) {
        const r = toSvg(miniEl.getBoundingClientRect());
        return { x: r.left + r.width / 2, y: r.top + r.height / 2, clamped: false };
      }
      const outEl = calcOutputRefs?.current?.[nodeId]?.current;
      if (!isInDOM(outEl)) return null;
      const r = toSvg(outEl.getBoundingClientRect());
      return { x: r.right, y: r.top + r.height / 2, clamped: false };
    }

    // Lookup node output dot
    if (String(datasetId).startsWith("__lookup__")) {
      const nodeId = String(datasetId).replace("__lookup__", "");
      if (!lookupOutputRefs?.current) return null;
      const lookupNode = lookupNodes?.find(n => n.id === nodeId);
      if (!lookupNode) return null;
      const fieldIdx = (lookupNode.output_mappings || []).findIndex(m => m.output_field === sourceField);
      const dotKey = nodeId + "_" + (fieldIdx >= 0 ? fieldIdx : 0);
      const outEl = lookupOutputRefs.current[dotKey]?.current || lookupOutputRefs.current[dotKey];
      if (!isInDOM(outEl)) return null;
      const r = toSvg(outEl.getBoundingClientRect());
      return { x: r.right, y: r.top + r.height / 2, clamped: false };
    }

    // REST node output dot
    if (String(datasetId).startsWith("__rest__")) {
      const nodeId = String(datasetId).replace("__rest__", "");
      if (!restOutputRefs?.current) return null;
      const restNode = restNodes?.find(n => n.id === nodeId);
      if (!restNode) return null;
      const fieldIdx = (restNode.response_mappings || []).findIndex(m => m.output_field === sourceField);
      const dotKey = `${nodeId}_${fieldIdx >= 0 ? fieldIdx : 0}`;
      const outEl = restOutputRefs.current[dotKey]?.current || restOutputRefs.current[dotKey];
      if (!isInDOM(outEl)) return null;
      const r = toSvg(outEl.getBoundingClientRect());
      return { x: r.right, y: r.top + r.height / 2, clamped: false };
    }

    // Python node output dot
    if (String(datasetId).startsWith("__python__")) {
      const nodeId = String(datasetId).replace("__python__", "");
      if (!pythonOutputRefs?.current) return null;
      const pythonNode = pythonNodes?.find(n => n.id === nodeId);
      if (!pythonNode) return null;
      const fieldIdx = (pythonNode.output_fields || []).findIndex(f => f === sourceField);
      const dotKey = nodeId + "_" + (fieldIdx >= 0 ? fieldIdx : 0);
      const outEl = pythonOutputRefs.current[dotKey]?.current || pythonOutputRefs.current[dotKey];
      if (!isInDOM(outEl)) return null;
      const r = toSvg(outEl.getBoundingClientRect());
      return { x: r.right, y: r.top + r.height / 2, clamped: false };
    }

    // Aggregation node output dot – finde den Dot per source_field (output_field des Agg-Node)
    if (String(datasetId).startsWith("__agg__")) {
      const nodeIdAgg = String(datasetId).replace("__agg__", "");
      const miniElAgg = getMiniPort("agg", nodeIdAgg, "right");
      if (miniElAgg) {
        const r = toSvg(miniElAgg.getBoundingClientRect());
        return { x: r.left + r.width / 2, y: r.top + r.height / 2, clamped: false };
      }
      const nodeId = String(datasetId).replace("__agg__", "");
      if (!aggOutputRefs?.current) return null;
      // sourceField nutzen um den richtigen Output-Dot zu finden
      if (sourceField) {
        const aggNode = aggNodes?.find(n => n.id === nodeId);
        if (aggNode) {
          const fieldIdx = (aggNode.fields || []).findIndex(f => f.output_field === sourceField);
          if (fieldIdx >= 0) {
            const dotKey = `${nodeId}_${fieldIdx}`;
            const outEl = aggOutputRefs.current[dotKey]?.current || aggOutputRefs.current[dotKey];
            if (isInDOM(outEl)) {
              const r = toSvg(outEl.getBoundingClientRect());
              return { x: r.right, y: r.top + r.height / 2, clamped: false };
            }
          }
        }
      }
      // Fallback: erster Dot wenn source_field nicht bekannt
      const keys = Object.keys(aggOutputRefs.current).filter(k => k.startsWith(nodeId + "_"));
      if (!keys.length) return null;
      const outEl = aggOutputRefs.current[keys[0]]?.current || aggOutputRefs.current[keys[0]];
      if (!isInDOM(outEl)) return null;
      const r = toSvg(outEl.getBoundingClientRect());
      return { x: r.right, y: r.top + r.height / 2, clamped: false };
    }

    // Wenn der Node minimiert ist: kein Clamping, direkt die ref-Position nehmen
    if (!isInDOM(srcEl)) return null;
    const isMinimized = (canvasNodes || []).find(n => n.dataset_id == datasetId)?.minimized;
    const s = toSvg(srcEl.getBoundingClientRect());
    const midY = s.top + s.height / 2;
    const x    = s.right;

    if (isMinimized) {
      // srcEl ist Output-Port-Dot → s.right ist der korrekte Ausgangspunkt
      return { x, y: midY, clamped: false };
    }

    const listEl = nodeFieldListRefs?.current?.[datasetId]?.current;
    if (!listEl) return { x, y: midY, clamped: false };

    const l = toSvg(listEl.getBoundingClientRect());
    if (midY < l.top) {
      return { x, y: l.top + 1, clamped: true };
    } else if (midY > l.bottom) {
      return { x, y: l.bottom - 1, clamped: true };
    }
    return { x, y: midY, clamped: false };
  };

  // Same clamping for target fields (right panel scroll container)
  const getTargetPoint = (tgtEl) => {
    const t = toSvg(tgtEl.getBoundingClientRect());
    const midY = t.top + t.height / 2;
    const x    = t.left;

    const listEl = targetListRef?.current;
    if (!listEl) return { x, y: midY, clamped: false };

    const l = toSvg(listEl.getBoundingClientRect());
    if (midY < l.top) {
      return { x, y: l.top + 1, clamped: true };
    } else if (midY > l.bottom) {
      return { x, y: l.bottom - 1, clamped: true };
    }
    return { x, y: midY, clamped: false };
  };

  return (
    <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", zIndex: 5, overflow: "visible", pointerEvents: "none" }}>
      <defs>
        {TRANSFORMER_TYPES.map((tt) => (
          <marker key={tt.value} id={`arr-${tt.value}`} markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M0,0 L0,6 L6,3 z" fill={tt.color} fillOpacity="0.7" />
          </marker>
        ))}
        <marker id="arr-join" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto">
          <circle cx="3" cy="3" r="2.5" fill={JOIN_COLOR} fillOpacity="0.8" />
        </marker>
      </defs>

      {/* ── Transform input lines: source → transform node input dot ── */}
      {(transformNodes || []).flatMap((tn) =>
        (tn.inputs || []).map((inp, ii) => {
          const srcDsIdRaw = inp.source_dataset_id;
          const srcDsId = String(srcDsIdRaw);
          const isNaN_val = srcDsId === "NaN" || srcDsId === "null" || srcDsId === "undefined";
          const isSpecial = srcDsId.startsWith("__transform__") || srcDsId.startsWith("__const__") || srcDsId.startsWith("__sql__") || srcDsId.startsWith("__agg__");

          const dotElRaw = transformInputRefs?.current?.[`${tn.id}__${inp.port_id}`];
          const dotEl = isInDOM(dotElRaw) ? dotElRaw : getMiniPort("transform", tn.id, "left");
          if (!isInDOM(dotEl)) return null;

          let sp = null;

          if (isSpecial) {
            if (srcDsId.startsWith("__agg__")) {
              // Finde den richtigen Output-Dot per source_field
              const nodeId = srcDsId.replace("__agg__", "");
              const aggNode = aggNodes?.find(n => n.id === nodeId);
              if (aggNode && aggOutputRefs?.current) {
                const fieldIdx = (aggNode.fields || []).findIndex(f => f.output_field === inp.source_field);
                const dotKey = `${nodeId}_${fieldIdx >= 0 ? fieldIdx : 0}`;
                const outEl = aggOutputRefs.current[dotKey]?.current || aggOutputRefs.current[dotKey];
                if (outEl) {
                  const r = toSvg(outEl.getBoundingClientRect());
                  sp = { x: r.right, y: r.top + r.height / 2, clamped: false };
                }
              }
            } else {
              sp = getSourcePoint(null, srcDsId);
            }
          } else if (isNaN_val) {
            // Fallback: Suche Transform-Node dessen output_field = source_field
            const srcField = inp.source_field;
            const srcTn = (transformNodes || []).find(t => t.id !== tn.id && t.output_field === srcField);
            if (srcTn) {
              sp = getSourcePoint(null, `__transform__${srcTn.id}`);
            } else {
              // Suche in fieldRefs
              // Bei Feldnamen-Kollision: bevorzuge Dataset das im Canvas ist
              const matchKeys = Object.keys(fieldRefs.current).filter(k => k.endsWith(`__${srcField}`));
              const srcKey = matchKeys.length === 1
                ? matchKeys[0]
                : (matchKeys.find(k => canvasNodes?.some(n => n.dataset_id == k.split("__")[0])) || matchKeys[0]);
              if (srcKey) {
                const srcEl = fieldRefs.current[srcKey];
                const actualDsId = srcKey.split("__")[0];
                sp = getSourcePoint(srcEl, actualDsId);
              }
            }
          } else {
            const srcKey = `${srcDsIdRaw}__${inp.source_field}`;
            const srcEl = fieldRefs.current[srcKey];
            if (srcEl) sp = getSourcePoint(srcEl, srcDsIdRaw);
          }

          if (!sp) return null;
          const d = toSvg(dotEl.getBoundingClientRect());
          const x1 = sp.x, y1 = sp.y;
          const x2 = d.left, y2 = d.top + d.height / 2;
          const cx = Math.min(100, Math.abs(x2 - x1) * 0.5);
          return <path key={`ti-${tn.id}-${ii}`}
            d={`M${x1} ${y1} C${x1+cx} ${y1} ${x2-cx} ${y2} ${x2} ${y2}`}
            fill="none" stroke="#818cf8" strokeWidth="1.5" strokeOpacity="0.6"
            strokeDasharray="5 3" />;
        })
      )}

      {/* ── REST input lines: source field → rest node input dot ── */}
      {(restNodes || []).flatMap((rn) => {
        const inputFields = rn.input_fields || (rn.input_field ? [{ field: rn.input_field }] : []);
        return inputFields.flatMap((inp, i) => {
          if (!inp.field) return [];
          const dotEl = restInputRefs?.current?.[`${rn.id}_${i}`]?.current || restInputRefs?.current?.[`${rn.id}_${i}`];
          if (!isInDOM(dotEl)) return [];
          // Suche Quellfeld in fieldRefs (Dataset-Felder) oder Transform/Agg Outputs
          const srcDsId = inp.source_dataset_id;
          let sp = null;
          if (srcDsId && String(srcDsId).startsWith("__")) {
            sp = getSourcePoint(null, srcDsId, inp.field);
          } else {
            const srcKey = srcDsId
              ? `${srcDsId}__${inp.field}`
              : (Object.keys(fieldRefs.current).filter(k => k.endsWith(`__${inp.field}`)).find(k => canvasNodes?.some(n => n.dataset_id == k.split("__")[0])) || Object.keys(fieldRefs.current).find(k => k.endsWith(`__${inp.field}`)));
            if (!srcKey) return [];
            const srcEl = fieldRefs.current[srcKey];
            if (!srcEl) return [];
            sp = getSourcePoint(srcEl, srcKey.split("__")[0]);
          }
          if (!sp) return [];
          const dr = toSvg(dotEl.getBoundingClientRect());
          const x1 = sp.x, y1 = sp.y, x2 = dr.left + dr.width / 2, y2 = dr.top + dr.height / 2;
          const cx = Math.min(100, Math.abs(x2 - x1) * 0.5);
          return [<path key={`ri-${rn.id}-${i}`}
            d={`M${x1} ${y1} C${x1+cx} ${y1} ${x2-cx} ${y2} ${x2} ${y2}`}
            fill="none" stroke={REST_NODE_COLOR} strokeWidth="1.5" strokeOpacity="0.5" strokeDasharray="5 3" />];
        });
      })}

      {/* ── Lookup input lines: source field → lookup node input dot ── */}
      {(lookupNodes || []).flatMap((ln) => {
        if (!ln.input_field) return [];
        const dotEl = lookupInputRefs?.current?.[ln.id]?.current || lookupInputRefs?.current?.[ln.id];
        if (!isInDOM(dotEl)) return [];
        const srcDsId = ln.input_source_dataset_id;
        let sp = null;
        if (srcDsId && String(srcDsId).startsWith("__")) {
          sp = getSourcePoint(null, srcDsId, ln.input_field);
        } else {
          const srcKey = srcDsId ? srcDsId + "__" + ln.input_field : (Object.keys(fieldRefs.current).filter(k => k.endsWith("__" + ln.input_field)).find(k => canvasNodes?.some(n => n.dataset_id == k.split("__")[0])) || Object.keys(fieldRefs.current).find(k => k.endsWith("__" + ln.input_field)));
          if (!srcKey) return [];
          const srcEl = fieldRefs.current[srcKey];
          if (!srcEl) return [];
          sp = getSourcePoint(srcEl, srcKey.split("__")[0]);
        }
        if (!sp) return [];
        const dr = toSvg(dotEl.getBoundingClientRect());
        const x1 = sp.x, y1 = sp.y, x2 = dr.left, y2 = dr.top + dr.height / 2;
        const cx = Math.min(100, Math.abs(x2 - x1) * 0.5);
        return [<path key={"li-" + ln.id}
          d={"M" + x1 + " " + y1 + " C" + (x1+cx) + " " + y1 + " " + (x2-cx) + " " + y2 + " " + x2 + " " + y2}
          fill="none" stroke={LOOKUP_COLOR} strokeWidth="1.5" strokeOpacity="0.5" strokeDasharray="5 3" />];
      })}

      {/* ── Calc Formel input lines: source field → formula input dots ── */}
      {(calcNodes || []).filter(cn => cn.calc_type === "formula" || !cn.calc_type).flatMap((cn) => {
        const parts = cn.formula_parts || [];
        return parts.map((part, i) => {
          if (part.op !== undefined || !part.value) return null;
          const refKey = `${cn.id}_formula_${i}`;
          const dotElRaw = calcInputPortRefs?.current?.[refKey]?.current;
          const dotEl = isInDOM(dotElRaw) ? dotElRaw : getMiniPort("calc", cn.id, "left");
          if (!isInDOM(dotEl)) return null;
          // Bevorzuge source_dataset_id wenn vorhanden (eindeutig)
          const srcKey = part.source_dataset_id
            ? `${part.source_dataset_id}__${part.value}`
            : Object.keys(fieldRefs.current).find(k => k.endsWith(`__${part.value}`));
          if (!srcKey) return null;
          const srcEl = fieldRefs.current[srcKey];
          if (!srcEl) return null;
          const srcDsIdForCalc = srcKey.split("__")[0];
          const sp = getSourcePoint(srcEl, srcDsIdForCalc);
          if (!sp) return null;
          const dr = toSvg(dotEl.getBoundingClientRect());
          const x1 = sp.x, y1 = sp.y, x2 = dr.left + dr.width / 2, y2 = dr.top + dr.height / 2;
          const cx = Math.min(100, Math.abs(x2 - x1) * 0.5);
          return <path key={`cf-${cn.id}-${i}`}
            d={`M${x1} ${y1} C${x1+cx} ${y1} ${x2-cx} ${y2} ${x2} ${y2}`}
            fill="none" stroke={CALC_COLOR} strokeWidth="1.5" strokeOpacity="0.5" strokeDasharray="5 3" />;
        }).filter(Boolean);
      })}

      {/* ── Agg input lines: dataset field → agg node input dot ── */}
      {(aggNodes || []).flatMap((an) =>
        (an.fields || []).filter(f => f.input_field).map((f, fi) => {
          // Suche das Quellfeld - bevorzuge eindeutige Keys (keine Kollision)
          const matchingKeys = Object.keys(fieldRefs.current).filter(k => k.endsWith(`__${f.input_field}`));
          if (!matchingKeys.length) return null;
          // Bei mehreren Treffern: bevorzuge den Key dessen Dataset im Mapping aktiv ist
          const srcKey = matchingKeys.length === 1
            ? matchingKeys[0]
            : (matchingKeys.find(k => canvasNodes?.some(n => n.dataset_id == k.split("__")[0])) || matchingKeys[0]);
          if (!srcKey) return null;
          const srcEl = fieldRefs.current[srcKey];
          if (!srcEl) return null;
          const dotEl = aggInputRefs?.current?.[`${an.id}_${fi}`]?.current || aggInputRefs?.current?.[`${an.id}_${fi}`];
          if (!isInDOM(dotEl)) return null;
          const sp = getSourcePoint(srcEl, srcKey.split("__")[0]);
          if (!sp) return null;
          const dr = toSvg(dotEl.getBoundingClientRect());
          const x1 = sp.x, y1 = sp.y;
          const x2 = dr.left, y2 = dr.top + dr.height / 2;
          const cx = Math.min(100, Math.abs(x2 - x1) * 0.5);
          return <path key={`ai-${an.id}-${fi}`}
            d={`M${x1} ${y1} C${x1+cx} ${y1} ${x2-cx} ${y2} ${x2} ${y2}`}
            fill="none" stroke={AGG_COLOR} strokeWidth="1.5" strokeOpacity="0.5"
            strokeDasharray="5 3" />;
        })
      )}

      {/* ── Mapping lines: canvas source → right panel target ── */}
      {connections.map((conn, i) => {
        const isTransform = String(conn.source_dataset_id).startsWith("__transform__");
        const isConst = String(conn.source_dataset_id).startsWith("__const__");
        const isSql = String(conn.source_dataset_id).startsWith("__sql__");
        const isAgg = String(conn.source_dataset_id).startsWith("__agg__");
        const isRest = String(conn.source_dataset_id).startsWith("__rest__");
        const isLookup = String(conn.source_dataset_id).startsWith("__lookup__");
        const isCalc = String(conn.source_dataset_id).startsWith("__calc__");
        const isSwitch = String(conn.source_dataset_id).startsWith("__switch__");
        const isPython = String(conn.source_dataset_id).startsWith("__python__");
        const isSpecialNode = isTransform || isConst || isSql || isAgg || isRest || isLookup || isCalc || isSwitch || isPython;
        const srcKey = `${conn.source_dataset_id}__${conn.source_field}`;
        const srcEl = isSpecialNode ? null : fieldRefs.current[srcKey];
        const tgtEl = targetRefs.current[conn.target_field];

        // Minimierter Node: srcEl zeigt auf Port-Dot direkt
        const miniNode = !isSpecialNode
          ? ((canvasNodes || []).find(n => n.dataset_id == conn.source_dataset_id && n.minimized) || null)
          : null;

        if ((!srcEl && !miniNode && !isSpecialNode) || !tgtEl) return null;

        let sp;
        if (isSwitch) {
          const nodeId = String(conn.source_dataset_id).replace("__switch__", "");
          const outEl = switchOutputRefs?.current?.[nodeId]?.current;
          if (!isInDOM(outEl)) return null;
          const r = toSvg(outEl.getBoundingClientRect());
          sp = { x: r.right, y: r.top + r.height / 2, clamped: false };
        } else if (isCalc) {
          const nodeId = String(conn.source_dataset_id).replace("__calc__", "");
          const outEl = calcOutputRefs?.current?.[nodeId]?.current;
          if (!isInDOM(outEl)) return null;
          const r = toSvg(outEl.getBoundingClientRect());
          console.log(`CALC sp: r={l:${Math.round(r.left)},r:${Math.round(r.right)},t:${Math.round(r.top)}} outEl.offsetLeft=${outEl.offsetLeft} offsetWidth=${outEl.offsetWidth}`);
          sp = { x: r.right, y: r.top + r.height / 2, clamped: false };
        } else if (isSql) {
          const nodeId = String(conn.source_dataset_id).replace("__sql__", "");
          if (!sqlOutputRefs?.current) return null;
          const sqlNode = sqlNodes?.find(n => n.id === nodeId);
          if (sqlNode?.mode === "transform" && (sqlNode.output_fields || []).length > 0) {
            const fieldIdx = (sqlNode.output_fields || []).indexOf(conn.source_field);
            const dotKey = `${nodeId}_${fieldIdx >= 0 ? fieldIdx : 0}`;
            const outEl = sqlOutputRefs.current[dotKey]?.current || sqlOutputRefs.current[dotKey];
            if (!isInDOM(outEl)) return null;
            const r = toSvg(outEl.getBoundingClientRect());
            const midY = r.top + r.height / 2;
            // Clamping: prüfe ob Dot im sichtbaren Bereich des scrollbaren Containers liegt
            const listEl = nodeFieldListRefs?.current?.[`__sql__${nodeId}`]?.current;
            let clamped = false;
            let clampedY = midY;
            if (listEl) {
              const l = toSvg(listEl.getBoundingClientRect());
              if (midY < l.top) { clampedY = l.top + 1; clamped = true; }
              else if (midY > l.bottom) { clampedY = l.bottom - 1; clamped = true; }
            }
            sp = { x: r.right, y: clampedY, clamped };
          } else {
            const outEl = sqlOutputRefs.current[nodeId]?.current || sqlOutputRefs.current[nodeId];
            const outElR = outEl?.current || outEl;
            if (!isInDOM(outElR)) return null;
            const r = toSvg(outElR.getBoundingClientRect());
            sp = { x: r.right, y: r.top + r.height / 2, clamped: false };
          }
        } else if (isLookup) {
          const nodeId = String(conn.source_dataset_id).replace("__lookup__", "");
          if (!lookupOutputRefs?.current) return null;
          const lookupNode = lookupNodes?.find(n => n.id === nodeId);
          if (!lookupNode) return null;
          const fieldIdx = (lookupNode.output_mappings || []).findIndex(f => f.output_field === conn.source_field);
          const dotKey = nodeId + "_" + (fieldIdx >= 0 ? fieldIdx : 0);
          const outEl = lookupOutputRefs.current[dotKey]?.current || lookupOutputRefs.current[dotKey];
          if (!isInDOM(outEl)) return null;
          const r = toSvg(outEl.getBoundingClientRect());
          sp = { x: r.right, y: r.top + r.height / 2, clamped: false };
        } else if (isRest) {
          const nodeId = String(conn.source_dataset_id).replace("__rest__", "");
          if (!restOutputRefs?.current) return null;
          const restNode = restNodes?.find(n => n.id === nodeId);
          if (!restNode) return null;
          const fieldIdx = (restNode.response_mappings || []).findIndex(f => f.output_field === conn.source_field);
          const dotKey = `${nodeId}_${fieldIdx >= 0 ? fieldIdx : 0}`;
          const outEl = restOutputRefs.current[dotKey]?.current || restOutputRefs.current[dotKey];
          if (!isInDOM(outEl)) return null;
          const r = toSvg(outEl.getBoundingClientRect());
          sp = { x: r.right, y: r.top + r.height / 2, clamped: false };
        } else if (isAgg) {
          // Finde Output-Dot per output_field = source_field
          const nodeId = String(conn.source_dataset_id).replace("__agg__", "");
          if (!aggOutputRefs?.current) return null;
          // Finde Agg-Node und den Field-Index mit passendem output_field
          const aggNode = aggNodes?.find(n => n.id === nodeId);
          if (!aggNode) return null;
          const fieldIdx = (aggNode.fields || []).findIndex(f => f.output_field === conn.source_field);
          const dotKey = `${nodeId}_${fieldIdx >= 0 ? fieldIdx : 0}`;
          const outEl = aggOutputRefs.current[dotKey]?.current || aggOutputRefs.current[dotKey];
          if (!isInDOM(outEl)) return null;
          const r = toSvg(outEl.getBoundingClientRect());
          sp = { x: r.right, y: r.top + r.height / 2, clamped: false };
        } else if (isPython) {
          const nodeId = String(conn.source_dataset_id).replace("__python__", "");
          if (!pythonOutputRefs?.current) return null;
          const pythonNode = pythonNodes?.find(n => n.id === nodeId);
          if (!pythonNode) return null;
          const fieldIdx = (pythonNode.output_fields || []).findIndex(f => f === conn.source_field);
          const dotKey = nodeId + "_" + (fieldIdx >= 0 ? fieldIdx : 0);
          const outEl = pythonOutputRefs.current[dotKey]?.current || pythonOutputRefs.current[dotKey];
          if (!isInDOM(outEl)) return null;
          const r = toSvg(outEl.getBoundingClientRect());
          sp = { x: r.right, y: r.top + r.height / 2, clamped: false };
        } else if (miniNode) {
          // srcEl ist Output-Port-Dot → toSvg gibt korrekte scroll-bereinigte Koordinate
          if (srcEl) {
            const r = toSvg(srcEl.getBoundingClientRect());
            sp = { x: r.right, y: r.top + r.height / 2, clamped: false };
          } else {
            sp = null;
          }
        } else {
          sp = getSourcePoint(srcEl, conn.source_dataset_id);
        }
        if (!sp) return null;
        const tp = getTargetPoint(tgtEl);

        const x1 = sp.x, y1 = sp.y;
        const x2 = tp.x, y2 = tp.y;
        const cx = Math.min(120, Math.abs(x2 - x1) * 0.5);
        const ti = TRANSFORMER_TYPES.find((t) => t.value === (conn.transformer?.type || "direct"));
        const color = isPython ? PYTHON_NODE_COLOR : isSwitch ? SWITCH_COLOR : isCalc ? CALC_COLOR : isLookup ? LOOKUP_COLOR : isRest ? REST_NODE_COLOR : isAgg ? AGG_COLOR : isSql ? SQL_NODE_COLOR : isConst ? "#a78bfa" : isTransform ? "#818cf8" : (ti?.color || "#6ee7b7");
        const isClamped = sp.clamped || tp.clamped;

        // target_type Badge
        const ttype = conn.target_type;
        const TYPE_COLORS = { integer:"#60a5fa", decimal:"#34d399", date:"#f59e0b", datetime:"#f59e0b", boolean:"#a78bfa", string:"#94a3b8" };
        const TYPE_LABELS = { integer:"INT", decimal:"DEC", date:"DAT", datetime:"DT", boolean:"BOOL", string:"STR" };
        const midX = (x1 + x2) / 2;
        const midY = (y1 + y2) / 2;
        const badgeColor = ttype ? (TYPE_COLORS[ttype] || "#94a3b8") : null;
        const badgeLabel = ttype ? (TYPE_LABELS[ttype] || ttype.toUpperCase().slice(0,3)) : null;

        // Typ-Kompatibilitätswarnung: nur für reguläre Dataset-Connections ohne expliziten Cast
        let typeWarn = false;
        if (!isSwitch && !isCalc && !isLookup && !isRest && !isAgg && !isSql && !isConst && !isTransform && !isPython && !ttype && conn.source_field && conn.target_field) {
          const srcNode = canvasNodes?.find(n => n.dataset_id == conn.source_dataset_id);
          const srcType = srcNode?.dataset_column_types?.[conn.source_field]?.type;
          const tgtType = targetColumnTypes?.[conn.target_field]?.type;
          if (srcType && tgtType && srcType !== tgtType) {
            // integer → decimal ist OK (Erweiterung), alles andere ist inkompatibel
            const compatible = srcType === "integer" && tgtType === "decimal";
            if (!compatible) typeWarn = true;
          }
        }

        const pathD = `M${x1} ${y1} C${x1+cx} ${y1} ${x2-cx} ${y2} ${x2} ${y2}`;
        const connColor = typeWarn ? "#f97316" : color;
        return (
          <g key={`m${i}`} style={{ cursor: onConnectionClick ? "pointer" : "default", pointerEvents: onConnectionClick ? "all" : "none" }}>
            {/* Unsichtbarer dicker Pfad zum einfachen Treffen */}
            {onConnectionClick && (
              <path d={pathD} fill="none" stroke="transparent" strokeWidth="12"
                onClick={(e) => { e.stopPropagation(); onConnectionClick(conn, i); }} />
            )}
            <path
              d={pathD}
              fill="none" stroke={connColor} strokeWidth="1.5"
              strokeOpacity={isClamped ? 0.3 : 0.7}
              strokeDasharray={typeWarn ? "5 3" : isClamped ? "4 3" : undefined}
              markerEnd={isClamped ? undefined : `url(#arr-${isSpecialNode ? "direct" : (ti?.value || "direct")})`}
              onClick={onConnectionClick ? (e) => { e.stopPropagation(); onConnectionClick(conn, i); } : undefined}
              onMouseEnter={onConnectionClick ? (e) => { e.currentTarget.style.strokeWidth = "3"; e.currentTarget.style.strokeOpacity = "1"; } : undefined}
              onMouseLeave={onConnectionClick ? (e) => { e.currentTarget.style.strokeWidth = "1.5"; e.currentTarget.style.strokeOpacity = isClamped ? "0.3" : "0.7"; } : undefined} />
            {typeWarn && !isClamped && (
              <g>
                <rect x={midX-20} y={midY-8} width={40} height={16} rx={4}
                  fill={S.bgCard} stroke="#f97316" strokeWidth="1.5" />
                <text x={midX} y={midY+4} textAnchor="middle" fontSize="8"
                  fontWeight="700" fill="#f97316" fontFamily="monospace">
                  ⚠ CAST?
                </text>
              </g>
            )}
            {badgeLabel && !typeWarn && !isClamped && (
              <g>
                <rect x={midX-14} y={midY-8} width={28} height={16} rx={4}
                  fill={S.bgCard} stroke={badgeColor} strokeWidth="1.2" />
                <text x={midX} y={midY+4} textAnchor="middle" fontSize="8"
                  fontWeight="700" fill={badgeColor} fontFamily="monospace">
                  {badgeLabel}
                </text>
              </g>
            )}
          </g>
        );
      })}

      {/* ── Join lines: both endpoints inside canvas ── */}
      {joins.map((join, i) => {
        const lKey = `${join.left_dataset_id}__${join.left_field}`;
        const rKey = `${join.right_dataset_id}__${join.right_field}`;
        const lEl = fieldRefs.current[lKey];
        const rEl = fieldRefs.current[rKey];

        // Minimierte Nodes: Position direkt aus canvas-Koordinaten
        // Beide Nodes aus canvasNodes holen (egal ob minimiert oder nicht)
        const lCanvasNode = (canvasNodes || []).find(n => n.dataset_id == join.left_dataset_id);
        const rCanvasNode = (canvasNodes || []).find(n => n.dataset_id == join.right_dataset_id);

        if ((!lEl && !lCanvasNode) || (!rEl && !rCanvasNode)) return null;

        // Koordinaten IMMER aus canvasNodes berechnen - kein DOM für x-Koordinaten
        // y-Koordinate: aus DOM wenn verfügbar (für Scroll-Clamp), sonst aus node.y
        // Koordinaten immer aus DOM messen - node.x ist nicht scrollkorrigiert
        // lEl/rEl zeigen auf Output-Port-Dot (right:-6 der Node)
        // toSvg() rechnet scroll korrekt ein
        const getJoinCoord = (el, canvasNode, isOutput) => {
          if (el) {
            const r = toSvg(el.getBoundingClientRect());
            return {
              x: isOutput ? r.right : r.left - (canvasNode?.minimized ? 0 : 230),
              y: r.top + r.height / 2,
            };
          }
          return { x: 0, y: 0 };
        };

        // Für Output (linke Node): rechter Rand des Output-Port-Dots
        // Für Join-Linien: nodeBodyRefs nutzen für präzise Node-Ränder
        // Join-Linie: von Feld-Output der linken Node zu Feld-Input der rechten Node
        // x1: rechter Rand der linken Node (Output-Port) via nodeBodyRef
        // y1: y-Position des Join-Feldes via fieldRef
        // x2: linker Rand der rechten Node via nodeBodyRef
        // y2: y-Position des Join-Feldes der rechten Node via fieldRef

        const getBodyX = (dsId, isOutput) => {
          const bodyRef = nodeBodyRefs?.current?.[dsId];
          const bodyEl = bodyRef?.current || bodyRef;
          if (!isInDOM(bodyEl)) return null;
          const br = toSvg(bodyEl.getBoundingClientRect());
          return isOutput ? br.right : br.left;
        };

        // y-Koordinate mit Clamping: wenn Feld aus sichtbarem Bereich gescrollt,
        // auf Rand der FieldList-ScrollBox clampen (wie bei Mapping-Linien)
        const getFieldYClamped = (el, dsId) => {
          if (!isInDOM(el)) return null;
          const r = toSvg(el.getBoundingClientRect());
          const midY = r.top + r.height / 2;
          const listEl = nodeFieldListRefs?.current?.[dsId]?.current;
          if (!listEl) return midY;
          const l = toSvg(listEl.getBoundingClientRect());
          if (midY < l.top)    return l.top + 1;
          if (midY > l.bottom) return l.bottom - 1;
          return midY;
        };

        const x1r = getBodyX(join.left_dataset_id, true);
        const x2r = getBodyX(join.right_dataset_id, false);
        if (x1r === null || x2r === null) return null;

        const y1RawL = getFieldYClamped(lEl, join.left_dataset_id);
        const y2RawR = getFieldYClamped(rEl, join.right_dataset_id);

        // Wenn rechte Node visuell links von linker Node → Koordinaten tauschen
        const swapped = x1r > x2r;
        const x1 = swapped ? getBodyX(join.right_dataset_id, true) : x1r;
        const x2 = swapped ? getBodyX(join.left_dataset_id, false) : x2r;
        const y1Raw = swapped ? y2RawR : y1RawL;
        const y2Raw = swapped ? y1RawL : y2RawR;
        // Fallback auf Node-Mitte wenn kein fieldRef
        const getBodyMidY = (dsId) => {
          const bodyRef = nodeBodyRefs?.current?.[dsId];
          const bodyEl = bodyRef?.current || bodyRef;
          if (!isInDOM(bodyEl)) return 0;
          const br = toSvg(bodyEl.getBoundingClientRect());
          return br.top + br.height / 2;
        };
        const y1 = y1Raw ?? getBodyMidY(join.left_dataset_id);
        const y2 = y2Raw ?? getBodyMidY(join.right_dataset_id);

        const cx = Math.min(100, Math.abs(x2 - x1) * 0.45);
        const mx = (x1 + x2) / 2;
        const my = (y1 + y2) / 2;
        const jt = JOIN_TYPES.find((j) => j.value === join.join_type) || JOIN_TYPES[0];
        const isClamped = false;

        return (
          <g key={`j${i}`} style={{ pointerEvents: "all", cursor: "pointer" }} onClick={(e) => { e.stopPropagation(); onJoinClick(i); }}>
            <path d={`M${x1} ${y1} C${x1+cx} ${y1} ${x2-cx} ${y2} ${x2} ${y2}`} fill="none" stroke="transparent" strokeWidth="12" />
            <path d={`M${x1} ${y1} C${x1+cx} ${y1} ${x2-cx} ${y2} ${x2} ${y2}`}
              fill="none" stroke={JOIN_COLOR} strokeWidth="2"
              strokeOpacity={isClamped ? 0.35 : 0.8}
              strokeDasharray="6 4"
              markerStart={isClamped ? undefined : "url(#arr-join)"}
              markerEnd={isClamped ? undefined : "url(#arr-join)"} />
            <rect x={mx-22} y={my-10} width={44} height={20} rx={4} fill={S.bgCard} stroke={JOIN_COLOR} strokeOpacity="0.6" strokeWidth="1" />
            <text x={mx} y={my+4} textAnchor="middle" fontSize="9" fontWeight="700" fill={JOIN_COLOR} fontFamily="monospace">{jt.label}</text>
          </g>
        );
      })}

      {/* ── Drag preview line ── */}
      {dragJoin && (
        <line x1={dragJoin.x1} y1={dragJoin.y1} x2={dragJoin.x2} y2={dragJoin.y2}
          stroke={JOIN_COLOR} strokeWidth="2" strokeDasharray="5 3" strokeOpacity="0.6" />
      )}
    </svg>
  );
}


// ─── Filter Editor ─────────────────────────────────────────────────────────────


export default SvgOverlay;
