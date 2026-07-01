import api from "./client.js";

export interface Knowledge {
  id: number;
  scope: "global" | "datasource" | "project";
  scope_id: string | null;
  category: string;
  title: string;
  content: string;
  enabled: boolean;
  use_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface Solution {
  id: number;
  project_id: number | null;
  category: string;
  title: string;
  prompt: string | null;
  response: string;
  use_count: number;
  rating: number;
  created_at: string | null;
  last_used_at: string | null;
}

export interface Correction {
  id: number;
  project_id: number | null;
  original_prompt: string | null;
  ai_response: string;
  user_correction: string;
  category: string;
  applied_count: number;
  created_at: string | null;
}

export interface CacheStats {
  total_entries: number;
  entries_with_hits: number;
  total_hit_count: number;
  hit_rate: number;
}

// ── Knowledge ─────────────────────────────────────────────────────────────────

export const listKnowledge = (scope?: string, scope_id?: string) =>
  api.get("/api/ai-memory/knowledge", { params: { scope, scope_id } }).then(r => r.data as Knowledge[]);

export const createKnowledge = (data: Partial<Knowledge>) =>
  api.post("/api/ai-memory/knowledge", data).then(r => r.data as Knowledge);

export const updateKnowledge = (id: number, data: Partial<Knowledge>) =>
  api.put(`/api/ai-memory/knowledge/${id}`, data).then(r => r.data as Knowledge);

export const deleteKnowledge = (id: number) =>
  api.delete(`/api/ai-memory/knowledge/${id}`).then(r => r.data);

// ── Solutions ─────────────────────────────────────────────────────────────────

export const listSolutions = (project_id?: number, category?: string) =>
  api.get("/api/ai-memory/solutions", { params: { project_id, category } }).then(r => r.data as Solution[]);

export const createSolution = (data: Partial<Solution>) =>
  api.post("/api/ai-memory/solutions", data).then(r => r.data as Solution);

export const updateSolution = (id: number, data: Partial<Solution>) =>
  api.put(`/api/ai-memory/solutions/${id}`, data).then(r => r.data as Solution);

export const useSolution = (id: number) =>
  api.post(`/api/ai-memory/solutions/${id}/use`).then(r => r.data);

export const deleteSolution = (id: number) =>
  api.delete(`/api/ai-memory/solutions/${id}`).then(r => r.data);

// ── Corrections ───────────────────────────────────────────────────────────────

export const listCorrections = (project_id?: number) =>
  api.get("/api/ai-memory/corrections", { params: { project_id } }).then(r => r.data as Correction[]);

export const createCorrection = (data: Partial<Correction>) =>
  api.post("/api/ai-memory/corrections", data).then(r => r.data as Correction);

export const deleteCorrection = (id: number) =>
  api.delete(`/api/ai-memory/corrections/${id}`).then(r => r.data);

// ── Cache ─────────────────────────────────────────────────────────────────────

export const getCacheStats = () =>
  api.get("/api/ai-memory/cache/stats").then(r => r.data as CacheStats);

export const clearCache = () =>
  api.delete("/api/ai-memory/cache").then(r => r.data);

// ── Suggestions ───────────────────────────────────────────────────────────────

export interface Suggestion {
  type: string;
  solution_id: number;
  title: string;
  category: string;
  use_count: number;
  response_preview: string;
  message: string;
}

export const getSuggestions = (project_id?: number) =>
  api.get("/api/ai-memory/suggestions", { params: { project_id } }).then(r => r.data as Suggestion[]);

export const promoteSolution = (data: { solution_id: number; scope: string; scope_id?: string; category: string }) =>
  api.post("/api/ai-memory/suggestions/promote", data).then(r => r.data as Knowledge);

// ── Schema Import ─────────────────────────────────────────────────────────────

export const importSchema = (text: string, scope = "global", scope_id?: string) =>
  api.post("/api/ai-memory/knowledge/import-schema", { text, scope, scope_id }).then(r => r.data);
