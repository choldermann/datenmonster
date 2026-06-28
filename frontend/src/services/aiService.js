const BASE = "/api/ai";

function getToken() {
  return localStorage.getItem("dm_token") || "";
}

function classifyFetchError(err) {
  const msg = (err?.message || "").toLowerCase();
  if (msg.includes("networkerror") || msg.includes("failed to fetch") || msg.includes("network request failed")) {
    return "Backend nicht erreichbar – läuft der Datenmonster-Server?";
  }
  if (msg.includes("timeout") || msg.includes("aborted")) {
    return "Anfrage abgebrochen – Modell antwortet nicht rechtzeitig";
  }
  return `Netzwerkfehler: ${err?.message || "Unbekannter Fehler"}`;
}

export async function streamRequest(endpoint, body, onToken, onMeta = null) {
  let resp;
  try {
    resp = await fetch(`${BASE}${endpoint}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${getToken()}`,
      },
      body: JSON.stringify(body),
    });
  } catch (err) {
    throw new Error(classifyFetchError(err));
  }

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    if (resp.status === 502 || resp.status === 503) throw new Error("Ollama nicht erreichbar – läuft der Ollama-Dienst?");
    if (resp.status === 504) throw new Error("Anfrage ist abgelaufen (Gateway Timeout)");
    if (resp.status === 401) throw new Error("Nicht authentifiziert – bitte neu anmelden");
    throw new Error(err.detail || `Backend-Fehler (HTTP ${resp.status})`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let full = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        const raw = line.slice(5).trim();
        if (raw === "[DONE]") return full;
        try {
          const msg = JSON.parse(raw);
          if (msg.error) throw new Error(`Modell-Fehler: ${msg.error}`);
          if (msg.meta && onMeta) { onMeta(msg.meta); continue; }
          if (msg.token) {
            full += msg.token;
            onToken(msg.token, full);
          }
        } catch (e) {
          if (e.message?.startsWith("Modell-Fehler")) throw e;
          // ignore malformed chunk
        }
      }
    }
  } catch (err) {
    if (err.message?.startsWith("Modell-Fehler")) throw err;
    if (full.length > 0) return full; // partial response is OK
    throw new Error(classifyFetchError(err));
  }
  return full;
}

export async function listModels() {
  const resp = await fetch(`${BASE}/models`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function pullModel(model, onProgress) {
  const resp = await fetch(`${BASE}/pull-model`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ model }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) {
      if (!line.startsWith("data:")) continue;
      const raw = line.slice(5).trim();
      if (raw === "[DONE]") return;
      try { onProgress(JSON.parse(raw)); } catch { /* ignore */ }
    }
  }
}

export async function getStatus() {
  const resp = await fetch(`${BASE}/status`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

export async function testConnection(baseUrl, model) {
  const resp = await fetch(`${BASE}/test-connection`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ base_url: baseUrl, model }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

// Context Builder API — backend assembles all context automatically

export const explainSql = (sql, connectionId, mappingId, onToken) =>
  streamRequest("/explain-sql", { sql, connection_id: connectionId, mapping_id: mappingId }, onToken);

export const generateSql = (description, connectionId, mappingId, onToken) =>
  streamRequest("/generate-sql", { description, connection_id: connectionId, mapping_id: mappingId }, onToken);

export const generatePython = (description, mappingId, nodeId, currentScript, onToken) =>
  streamRequest("/generate-python", {
    description,
    mapping_id: mappingId,
    node_id: nodeId,
    current_script: currentScript || "",
  }, onToken);

export const generateExpression = (description, mappingId, nodeId, fieldName, onToken) =>
  streamRequest("/generate-expression", {
    description,
    mapping_id: mappingId,
    node_id: nodeId,
    field_name: fieldName || "",
  }, onToken);

export const explainError = (error, nodeType, code, mappingId, nodeId, onToken) =>
  streamRequest("/explain-error", {
    error,
    node_type: nodeType || "",
    code: code || "",
    mapping_id: mappingId,
    node_id: nodeId,
  }, onToken);

export async function getTableContext(connectionId, description) {
  const resp = await fetch(`${BASE}/table-context`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ connection_id: connectionId, description }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export async function suggestDatasets(connectionId, description, selectedTables, onToken) {
  const resp = await fetch(`${BASE}/suggest-datasets`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ connection_id: connectionId, description, selected_tables: selectedTables ?? null }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) {
      if (!line.startsWith("data:")) continue;
      const raw = line.slice(5).trim();
      if (raw === "[DONE]") return;
      try {
        const msg = JSON.parse(raw);
        if (msg.error) throw new Error(msg.error);
        if (Array.isArray(msg.result)) return { suggestions: msg.result };
        if (msg.token && onToken) onToken(msg.token);
      } catch (e) {
        if (e.message && !e.message.startsWith("JSON")) throw e;
      }
    }
  }
  return { suggestions: [] };
}

export const suggestMapping = (mappingId, onToken) =>
  streamRequest("/suggest-mapping", { mapping_id: mappingId }, onToken);

export async function generateNodes(description, availableDatasets, onToken) {
  const resp = await fetch(`${BASE}/generate-nodes`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ description, available_datasets: availableDatasets ?? [] }),
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) {
      if (!line.startsWith("data:")) continue;
      const raw = line.slice(5).trim();
      if (raw === "[DONE]") return null;
      try {
        const msg = JSON.parse(raw);
        if (msg.error) throw new Error(msg.error);
        if (msg.result) return msg.result; // { nodes, explanation }
        if (msg.token && onToken) onToken(msg.token);
      } catch (e) {
        if (e.message && !e.message.startsWith("JSON")) throw e;
      }
    }
  }
  return null;
}

export const chatStream = (message, history, pageContext, onToken) =>
  streamRequest("/chat", { message, history: history ?? [], page_context: pageContext ?? {} }, onToken);

export async function deleteModel(model) {
  const resp = await fetch(`${BASE}/models/delete`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ model }),
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}
