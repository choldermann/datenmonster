const BASE = "/api/ai";

function getToken() {
  return localStorage.getItem("dm_token") || "";
}

export async function streamRequest(endpoint, body, onToken) {
  const resp = await fetch(`${BASE}${endpoint}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${getToken()}`,
    },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let full = "";

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
        const { token } = JSON.parse(raw);
        if (token) {
          full += token;
          onToken(token, full);
        }
      } catch {
        // ignore malformed chunk
      }
    }
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

export async function suggestDatasets(connectionId, description, onToken) {
  const resp = await fetch(`${BASE}/suggest-datasets`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${getToken()}` },
    body: JSON.stringify({ connection_id: connectionId, description }),
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
