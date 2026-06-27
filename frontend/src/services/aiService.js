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

export async function getStatus() {
  const resp = await fetch(`${BASE}/status`, {
    headers: { Authorization: `Bearer ${getToken()}` },
  });
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
  return resp.json();
}

// Context Builder API — backend assembles all context automatically

export const explainSql = (sql, connectionId, onToken) =>
  streamRequest("/explain-sql", { sql, connection_id: connectionId }, onToken);

export const generateSql = (description, connectionId, onToken) =>
  streamRequest("/generate-sql", { description, connection_id: connectionId }, onToken);

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

export const suggestMapping = (mappingId, onToken) =>
  streamRequest("/suggest-mapping", { mapping_id: mappingId }, onToken);
