import type { Provider, ProviderPreset, SmtpConfig, TestRun, TestRunListItem } from "./types";

export const API_BASE = (window as any).QA_AGENT_API_BASE || "http://127.0.0.1:8756";
const WS_BASE = API_BASE.replace(/^http/, "ws");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`Falha na requisição ${path}: ${res.status}`);
  }
  return res.json();
}

export interface StartTestPayload {
  url: string;
  goal: string;
  username?: string;
  password?: string;
  max_steps: number;
  headless: boolean;
}

export interface ProviderCreatePayload {
  name: string;
  base_url: string;
  api_key?: string;
  vision_model: string;
  text_model: string;
  enabled: boolean;
}

export interface ProviderPatchPayload {
  name?: string;
  base_url?: string;
  api_key?: string;
  vision_model?: string;
  text_model?: string;
  enabled?: boolean;
}

export interface SmtpPatchPayload {
  host?: string;
  port?: number;
  encryption?: "starttls" | "ssl" | "none";
  username?: string;
  password?: string;
  from_email?: string;
  from_name?: string;
}

export const api = {
  health: () => request<{ ok: boolean; configured: boolean }>("/api/health"),

  getSmtpConfig: () => request<SmtpConfig>("/api/smtp"),

  patchSmtpConfig: (payload: SmtpPatchPayload) =>
    request<SmtpConfig>("/api/smtp", { method: "PATCH", body: JSON.stringify(payload) }),

  sendReportEmail: (runId: string, recipients: string[], message?: string) =>
    request<{ ok: boolean; error?: string }>(`/api/tests/${runId}/send-email`, {
      method: "POST",
      body: JSON.stringify({ recipients, message }),
    }),

  listProviders: () => request<Provider[]>("/api/providers"),

  providerPresets: () => request<Record<string, ProviderPreset>>("/api/providers/presets"),

  addProvider: (payload: ProviderCreatePayload) =>
    request<Provider[]>("/api/providers", { method: "POST", body: JSON.stringify(payload) }),

  patchProvider: (id: string, payload: ProviderPatchPayload) =>
    request<Provider[]>(`/api/providers/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),

  deleteProvider: (id: string) => request<Provider[]>(`/api/providers/${id}`, { method: "DELETE" }),

  reorderProviders: (order: string[]) =>
    request<Provider[]>("/api/providers/reorder", { method: "POST", body: JSON.stringify({ order }) }),

  startTest: (payload: StartTestPayload) =>
    request<{ run_id: string }>("/api/tests", { method: "POST", body: JSON.stringify(payload) }),

  listTests: () => request<TestRunListItem[]>("/api/tests"),

  getTest: (id: string) => request<TestRun>(`/api/tests/${id}`),

  screenshotUrl: (filename: string) => `${API_BASE}/files/screenshots/${filename}`,

  reportUrl: (filename: string) => `${API_BASE}/files/reports/${filename}`,

  streamTest: (id: string, onEvent: (event: any) => void): WebSocket => {
    const ws = new WebSocket(`${WS_BASE}/api/tests/${id}/stream`);
    ws.onmessage = (msg) => {
      try {
        onEvent(JSON.parse(msg.data));
      } catch {
        // ignore malformed frame
      }
    };
    return ws;
  },
};
