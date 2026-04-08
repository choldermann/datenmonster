# Datenmonster Part6 – Dokumentation: Mapping-Editor Linien & Node-Minimierung Bugfixes

## Überblick

Diese Session war ausschließlich Frontend-fokussiert und hat das Linien-System im Mapping-Editor grundlegend repariert und stabilisiert. Der Schwerpunkt lag auf dem korrekten Verhalten von Verbindungslinien zwischen minimierten und nicht-minimierten Nodes.

---

## Probleme die behoben wurden

### 1. Join-Linien starteten am falschen Punkt

**Problem:** Join-Linien (gestrichelte orangene Linien zwischen Dataset-Nodes) starteten am Input-Port (links) statt am Output-Port (rechts) der linken Node.

**Ursache:** `node.x` in `canvasNodes` ist canvas-relativ (ohne Scroll-Offset), während `toSvg()` den `scrollLeft` des Canvas-Containers einrechnet. Die frühere Berechnung `node.x + 230` war zufällig korrekt für normale Nodes, aber für minimierte Nodes (`node.x + 60`) fehlte der Scroll-Offset komplett.

**Fix:** `nodeBodyRef` eingeführt – ein Ref auf den äußersten `<div>` jeder `DatasetNode`. `getBoundingClientRect()` auf diesem Element gibt die korrekte Viewport-Position zurück, `toSvg()` rechnet `scrollLeft` korrekt ein. `x1 = nodeBodyRef.right`, `x2 = nodeBodyRef.left`.

**Betroffene Dateien:**
- `frontend/src/components/mapping/DatasetNode.jsx` – `nodeBodyRef` registriert via `onRegisterNodeRef`
- `frontend/src/pages/MappingEditor.jsx` – `nodeBodyRefs = useRef({})` + Übergabe an SvgOverlay
- `frontend/src/components/mapping/SvgOverlay.jsx` – Join-Koordinaten aus `nodeBodyRefs`

### 2. Join-Linien gingen Feld-zu-Feld (wie früher) statt Node-Mitte zu Node-Mitte

**Problem:** Join-Linien sollen von dem spezifischen Join-Feld (z.B. `kRechnung`) zum entsprechenden Feld der rechten Node gehen – nicht zur Node-Mitte.

**Fix:** `x1/x2` aus `nodeBodyRef` (Node-Rand), `y1/y2` aus `fieldRef` (Feld-Position) mit Scroll-Clamping – genau wie die grünen Mapping-Linien. Wenn das Join-Feld aus dem sichtbaren Bereich der Node gescrollt ist, wird `y` auf den Rand der FieldList-ScrollBox geclampt.

### 3. Linien für minimierte Special-Nodes (Transform, Calc, etc.) starteten am falschen Punkt

**Problem:** Output-Linien von minimierten Nodes (TransformNode, CalcNode, etc.) starteten weit rechts außerhalb der Node, weil `outputRef.current` auf einen unsichtbaren Proxy-Div bei `left: nodeWidth` (z.B. `left: 270`) zeigte.

**Ursache:** Der Proxy-Div war ursprünglich nötig weil `node.x` falsch war. Nach dem Umstieg auf DOM-Messungen ist er obsolet und störend.

**Fix:** Proxy-Divs vollständig entfernt. Stattdessen: `miniRightRef` (rechter Port-Dot der minimierten Node) als Ankerpunkt genutzt. `outputRef.current = miniRightRef.current` wird im `useEffect` gesetzt wenn `node.minimized = true`.

### 4. React Ref-Cleanup-Reihenfolge (Linien verschwanden beim Minimieren)

**Problem:** Beim Wechsel normal → minimiert wurde `outputRef.current` auf `null` gesetzt, weil der Cleanup-Callback des alten Output-Dots nach dem Mount des neuen Proxy/Port-Dots aufgerufen wurde.

**Fix:** Ref-Callbacks im normalen Zustand setzen nur bei `el != null` (kein Cleanup). Der Proxy/Port-Dot setzt `outputRef.current` ebenfalls nur bei `el != null`.

```jsx
// Vorher (falsches Cleanup):
ref={el => { if (outputRef) outputRef.current = el; }}

// Nachher (kein Cleanup):
ref={el => { if (outputRef && el) outputRef.current = el; }}
```

### 5. Port-Dots in MinimizedNode falsch positioniert

**Problem:** Die Port-Dots (links/rechts) in `MinimizedNode.jsx` waren `position: absolute` im äußeren `inline-flex` Wrapper ohne `position: relative`. Dadurch positionierten sie sich relativ zum nächsten positionierten Vorfahren (der äußere Node-Container), nicht relativ zur sichtbaren Form.

**Fix:** Port-Dots in den Form-Container verschoben:

```jsx
// Vorher: Dots außerhalb des Form-Containers
<div style={{ display: "inline-flex", ... }}>
  <div ref={portLeftRef} style={{ position: "absolute", left: -6, ... }} />
  <div ref={portRightRef} style={{ position: "absolute", right: -6, ... }} />
  <div style={{ position: "relative", width: w, height: h }}> {/* Form */}

// Nachher: Dots innerhalb des Form-Containers (position: relative)
<div style={{ display: "inline-flex", ... }}>
  <div style={{ position: "relative", width: w, height: h }}>
    <div ref={portLeftRef} style={{ position: "absolute", left: -6, top: "50%", ... }} />
    <div ref={portRightRef} style={{ position: "absolute", right: -6, top: "50%", ... }} />
    {/* Form */}
```

`top: "50%"` bezieht sich jetzt exakt auf die Formhöhe `h` – nicht mehr auf den übergeordneten Container. Außerdem `pointerEvents: "none"` entfernt damit Drag & Drop korrekt funktioniert.

### 6. Dritter Dot bei minimierten Nodes

**Problem:** Minimierte Nodes zeigten 3 Dots statt 2 – der dritte kam von einem übrig gebliebenen `{/* Output-Port Dot - visuell */}` div in `TransformNode.jsx`.

**Fix:** Alle extra Port-Dot-Divs aus den minimierten Blöcken entfernt.

### 7. SvgOverlay Logik-Bugs (Cursor-Analyse)

**Problem 1:** `__agg__` Output-Dot ignorierte `source_field` und nahm immer `keys[0]` – falsche Linie bei mehreren Aggregations-Outputs.

**Fix:** `fieldIdx = aggNode.fields.findIndex(f => f.output_field === sourceField)` → korrekter Dot per Index.

**Problem 2:** `endsWith(__field)` Suche in `fieldRefs` nicht eindeutig bei Feldnamen-Kollisionen (gleicher Name in zwei Datasets).

**Fix:** Bei mehreren Treffern wird der Key bevorzugt dessen Dataset-ID in `canvasNodes` vorkommt. Für Calc-Nodes: `part.source_dataset_id` direkt nutzen wenn vorhanden.

---

## Neues Port-System für minimierte Special-Nodes

### Architektur

```
MappingEditor
  ├── miniPortRefs = useRef({})   // { "transform_42": { left: domEl, right: domEl }, ... }
  │
  ├── TransformNode (minimiert)
  │   ├── miniLeftRef  → portLeftRef  in MinimizedNode  ← linker Port-Dot DOM-Element
  │   ├── miniRightRef → portRightRef in MinimizedNode  ← rechter Port-Dot DOM-Element
  │   └── useEffect: outputRef.current = miniRightRef.current
  │                  onMiniPortsReady(id, left, right) → miniPortRefs befüllen
  │                  setTimeout(triggerLineDraw, 0)
  │
  └── SvgOverlay
      └── getMiniPort(prefix, nodeId, side)
          → miniPortRefs.current["transform_42"].right
          → toSvg(el).left + width/2  (Dot-Mittelpunkt)
```

### Unterstützte Node-Typen und Keys

| Node | Prefix | outputRef-Typ |
|------|--------|--------------|
| TransformNode | `transform_` | `outputRef.current` (singular) |
| CalcNode | `calc_` | `outputRef.current` (singular) |
| AggNode | `agg_` | `outputRefs.current[id].current` (plural) |
| SqlNode | `sql_` | `outputRef.current` (singular) |
| SwitchNode | `switch_` | `outputRefs.current[id].current` (plural) |
| LookupNode | `lookup_` | `outputRefs.current[id].current` (plural) |
| RestNode | `rest_` | `outputRefs.current[id].current` (plural) |
| ConstantNode | `const_` | `outputRef.current` (singular) |

---

## Geänderte Dateien

### Frontend

| Datei | Änderungen |
|-------|-----------|
| `frontend/src/components/mapping/MinimizedNode.jsx` | Port-Dots in Form-Container verschoben, `pointerEvents: none` entfernt |
| `frontend/src/components/mapping/DatasetNode.jsx` | `nodeBodyRef` registriert via `onRegisterNodeRef(id, fieldListRef, nodeBodyRef)` |
| `frontend/src/components/mapping/SvgOverlay.jsx` | `nodeBodyRefs` + `miniPortRefs` als Props, `getMiniPort()`, Join-Koordinaten DOM-basiert, Clamping für Join-y, AGG/endsWith Bugfixes |
| `frontend/src/pages/MappingEditor.jsx` | `nodeBodyRefs`, `miniPortRefs`, `onMiniPortsReady`-Callbacks mit `triggerLineDraw` |
| `frontend/src/components/TransformNode.jsx` | `miniLeftRef`/`miniRightRef`, `useEffect` für `outputRef`+`onMiniPortsReady`, Proxy-Div entfernt |
| `frontend/src/components/mapping/CalcNode.jsx` | dto. |
| `frontend/src/components/mapping/AggNode.jsx` | dto. (outputRefs plural) |
| `frontend/src/components/mapping/SqlNode.jsx` | dto. |
| `frontend/src/components/mapping/SwitchNode.jsx` | dto. (outputRefs plural) |
| `frontend/src/components/mapping/LookupNode.jsx` | dto. (outputRefs plural) |
| `frontend/src/components/mapping/RestNode.jsx` | dto. (outputRefs plural) |
| `frontend/src/components/mapping/ConstantNode.jsx` | dto. |

---

## Aktueller Stand

- ✅ Join-Linien: Feld-zu-Feld, korrekte x-Koordinaten (scroll-bereinigt), Clamping beim Scrollen
- ✅ Mapping-Linien: DatasetNode → Ziel, korrekt ausgeklappt und minimiert
- ✅ Special-Node Output-Linien: starten vom rechten Port-Dot der minimierten Form
- ✅ Special-Node Input-Linien: enden am linken Port-Dot der minimierten Form
- ✅ Port-Dots: sauber positioniert relativ zur sichtbaren Form
- ✅ Genau 2 Dots pro minimierter Node (links + rechts)
- ✅ Linien verschwinden nicht beim Minimieren/Aufklappen
