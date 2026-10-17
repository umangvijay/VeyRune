/**
 * Veyrune — Typed API Client (PRODUCTION)
 *
 * No hardcoded tokens. Uses real JWT from auth state.
 * Auto-refreshes expired tokens. All endpoints typed.
 */

import { fetchEventSource } from "@microsoft/fetch-event-source";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

// ── Token management ─────────────────────────────────────────────

function getAuthData(): { accessToken: string | null; refreshToken: string | null } {
  if (typeof window === "undefined") return { accessToken: null, refreshToken: null };
  try {
    const stored = localStorage.getItem("agentos_auth");
    if (!stored) return { accessToken: null, refreshToken: null };
    const parsed = JSON.parse(stored);
    return {
      accessToken: parsed.accessToken || null,
      refreshToken: parsed.refreshToken || null,
    };
  } catch {
    return { accessToken: null, refreshToken: null };
  }
}

function getToken(): string | null {
  return getAuthData().accessToken;
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const CSRF_STORAGE_KEY = "agentos_csrf_token";

function readStoredCsrf(): string {
  if (typeof window === "undefined") return "";
  try {
    return sessionStorage.getItem(CSRF_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

function writeStoredCsrf(token: string) {
  try {
    sessionStorage.setItem(CSRF_STORAGE_KEY, token);
  } catch {
    /* private mode / disabled storage */
  }
}

function csrfHeaders(): Record<string, string> {
  const token = readStoredCsrf();
  return token ? { "X-CSRF-Token": token } : {};
}

async function ensureCsrf(): Promise<void> {
  if (typeof window === "undefined") return;
  if (readStoredCsrf()) return;
  const res = await fetch(`${API_BASE.replace("/api/v1", "")}/api/v1/csrf-token`, {
    credentials: "include",
  });
  if (!res.ok) return;
  const data = (await res.json().catch(() => ({}))) as { csrf_token?: unknown };
  const token = typeof data.csrf_token === "string" ? data.csrf_token : "";
  if (token) writeStoredCsrf(token);
}

// ── Generic fetcher with auth ────────────────────────────────────

function formatApiError(errData: unknown, status: number): string {
  const detail = (errData as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && "msg" in item) return String((item as { msg: unknown }).msg);
        return JSON.stringify(item);
      })
      .join("; ");
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return `API error: ${status}`;
}

function rewriteFetchError(err: unknown): Error {
  if (err instanceof TypeError) {
    return new Error(
      "Could not reach the API (network or CORS). If Cloud Run is waking up, wait a few seconds and retry."
    );
  }
  return err instanceof Error ? err : new Error(String(err));
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  await ensureCsrf();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...authHeaders(),
    ...csrfHeaders(),
    ...(options.headers as Record<string, string> || {}),
  };

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      ...options,
      headers,
      credentials: "include",
    });
  } catch (err) {
    throw rewriteFetchError(err);
  }

  if (res.status === 401) {
    // Try refresh
    const { refreshToken } = getAuthData();
    if (refreshToken) {
      const refreshRes = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
      if (refreshRes.ok) {
        const data = await refreshRes.json();
        const stored = JSON.parse(localStorage.getItem("agentos_auth") || "{}");
        stored.accessToken = data.access_token;
        stored.refreshToken = data.refresh_token;
        stored.user = data.user;
        localStorage.setItem("agentos_auth", JSON.stringify(stored));

        // Retry original request
        headers.Authorization = `Bearer ${data.access_token}`;
        let retry: Response;
        try {
          retry = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: "include" });
        } catch (err) {
          throw rewriteFetchError(err);
        }
        if (!retry.ok) {
          const errData = await retry.json().catch(() => ({}));
          throw new Error(formatApiError(errData, retry.status));
        }
        return retry.json();
      } else {
        localStorage.removeItem("agentos_auth");
        window.location.href = "/login";
        return new Promise(() => {}) as Promise<T>;
      }
    }
    localStorage.removeItem("agentos_auth");
    window.location.href = "/login";
    return new Promise(() => {}) as Promise<T>;
  }

  if (res.status === 403) {
    const errData = await res.clone().json().catch(() => ({}));
    const detail = formatApiError(errData, 403);
    if (/csrf/i.test(detail)) {
      writeStoredCsrf("");
      await ensureCsrf();
      const retryHeaders: Record<string, string> = {
        ...headers,
        ...csrfHeaders(),
      };
      try {
        res = await fetch(`${API_BASE}${path}`, {
          ...options,
          headers: retryHeaders,
          credentials: "include",
        });
      } catch (err) {
        throw rewriteFetchError(err);
      }
    }
  }

  if (res.status === 204) return {} as T;

  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error(formatApiError(errData, res.status));
  }

  return res.json();
}

// ── Interfaces ───────────────────────────────────────────────────

export interface Task {
  task_id: string;
  workflow_id: string;
  run_id: string;
  agent: string;
  tool?: string;
  title?: string;
  status: string;
  input_data: Record<string, unknown>;
  output_data?: Record<string, unknown>;
  dependencies: string[];
  started_at?: string;
  completed_at?: string;
  error?: string;
  error_type?: string;
  attempt: number;
}

export interface WorkflowRun {
  run_id: string;
  workflow_id: string;
  user_id: string;
  goal: string;
  status: string;
  tasks: Task[];
  created_at: string;
  parent_run_id?: string | null;
  thread_id?: string | null;
}

export interface WorkflowEvent {
  event_id: string;
  timestamp: string;
  type: string;
  workflow_id: string;
  run_id: string;
  task_id?: string;
  status?: string;
  summary: string;
  sanitized_metadata: Record<string, unknown>;
}

export interface Integration {
  mcp_id: string;
  name: string;
  description?: string;
  trust_tier: string;
  is_enabled: boolean;
  health?: string;
  tool_count: number;
  circuit_breaker: {
    state: string;
    failure_count: number;
    total_successes: number;
    total_failures: number;
    retry_in_seconds?: number;
  };
  created_at?: string;
}

export interface IntegrationTool {
  tool_name?: string;
  name?: string;
  description?: string;
  inputSchema?: Record<string, unknown>;
}

export interface Notification {
  id: string;
  type: string;
  title: string;
  body: string;
  is_read: boolean;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Schedule {
  schedule_id: string;
  name: string;
  goal: string;
  cron_expression: string;
  timezone: string;
  /** Backend source of truth: "ACTIVE" | "PAUSED" */
  status?: string;
  /** Derived flag (backend also sends it); undefined falls back to status */
  is_enabled?: boolean;
  next_run_at?: string;
  created_at: string;
}

export function scheduleIsEnabled(schedule: Schedule): boolean {
  if (typeof schedule.is_enabled === "boolean") return schedule.is_enabled;
  return (schedule.status || "ACTIVE").toUpperCase() === "ACTIVE";
}

export interface ApprovalRequest {
  approval_id: string;
  workflow_id: string;
  run_id: string;
  task_id: string;
  user_id: string;
  status: string;
  requested_at: string;
  expires_at: string;
  risk_level: string;
  reason: string;
  tool_name: string;
  tool_arguments: Record<string, unknown>;
}

export interface UserSettings {
  theme: string;
  autonomy_level: number;
  default_model: string;
  notifications_enabled: boolean;
  daily_token_limit: number;
  auto_approve_low_risk: boolean;
}

export interface GoalAttachment {
  name: string;
  mime: string;
  text?: string;
  image_base64?: string;
}

// ── Workflows ────────────────────────────────────────────────────

export async function submitGoal(
  goal: string,
  attachments: GoalAttachment[] = [],
  opts: { parent_run_id?: string; thread_id?: string; model?: string } = {},
) {
  return apiFetch<{ run_id: string; workflow_id: string; status: string; task_count: number; thread_id?: string }>(
    "/workflows",
    {
      method: "POST",
      body: JSON.stringify({
        goal,
        attachments,
        model: opts.model || undefined,
        parent_run_id: opts.parent_run_id || undefined,
        thread_id: opts.thread_id || undefined,
      }),
    }
  );
}

export async function getWorkflowThread(runId: string) {
  return apiFetch<{ thread_id: string; workflows: WorkflowRun[] }>(`/workflows/${runId}/thread`);
}

export async function listWorkflows(limit = 50, offset = 0) {
  return apiFetch<{ workflows: WorkflowRun[]; count: number }>(
    `/workflows?limit=${limit}&offset=${offset}`
  );
}

export async function getWorkflow(runId: string) {
  return apiFetch<WorkflowRun>(`/workflows/${runId}`);
}

export async function cancelWorkflow(runId: string) {
  return apiFetch<{ run_id: string; status: string }>(
    `/workflows/${runId}/cancel`,
    { method: "POST" }
  );
}

export async function retryWorkflow(runId: string) {
  return apiFetch<{ run_id: string; status: string; retried_tasks: number }>(
    `/workflows/${runId}/retry`,
    { method: "POST" }
  );
}

export async function resumeWorkflow(runId: string) {
  return apiFetch<{ run_id: string; status: string; resumed_tasks: number }>(
    `/workflows/${runId}/resume`,
    { method: "POST" }
  );
}

export function subscribeWorkflowEvents(
  runId: string,
  onMessage: (event: WorkflowEvent) => void,
  onOpen?: () => void,
  onError?: (err: unknown) => void
) {
  const controller = new AbortController();
  const seen = new Set<string>();

  void ensureCsrf();
  fetchEventSource(`${API_BASE}/workflows/${runId}/events`, {
    headers: { ...authHeaders(), ...csrfHeaders() },
    credentials: "include",
    signal: controller.signal,
    onopen: async (res) => {
      if (res.ok && res.status === 200) {
        if (onOpen) onOpen();
      } else if (res.status >= 400 && res.status < 500 && res.status !== 429) {
        throw new Error(`SSE failed: ${res.status}`);
      }
    },
    onmessage: (msg) => {
      if (msg.event === "error") {
        let text = msg.data || "Event stream failed";
        try {
          const parsed = JSON.parse(msg.data) as { error?: string };
          if (parsed.error) text = parsed.error;
        } catch { /* keep raw */ }
        if (onError) onError(new Error(text));
        return;
      }
      if (msg.data) {
        try {
          const data = JSON.parse(msg.data) as WorkflowEvent;
          if (data.event_id) {
            if (seen.has(data.event_id)) return;
            seen.add(data.event_id);
          }
          onMessage(data);
        } catch (e) {
          console.error("Failed to parse SSE event", e);
        }
      }
    },
    onerror: (err) => {
      if (onError) onError(err);
    },
  });

  return () => controller.abort();
}

// ── Integrations ─────────────────────────────────────────────────

export interface AgentTool {
  agent_tool_name: string;
  name: string;
  mcp_name?: string;
  description?: string;
  input_schema?: Record<string, unknown>;
}

export interface AgentPlugin {
  id: string;
  state: string;
  installed_by: string;
  manifest: {
    plugin_id: string;
    name: string;
    description: string;
    required_tools: string[];
    agents: { agent_id: string; display_name: string; instructions: string; allowed_tools: string[] }[];
  };
}

export async function listAgentPlugins() {
  return apiFetch<{ plugins: AgentPlugin[] }>("/agents/plugins");
}

export async function listAgentTools() {
  return apiFetch<{ tools: AgentTool[] }>("/agents/tools");
}

export async function installAgentPlugin(manifest: Record<string, unknown>) {
  return apiFetch<{ plugin: AgentPlugin }>("/agents/plugins", {
    method: "POST", body: JSON.stringify({ manifest }),
  });
}

export async function setAgentPluginEnabled(pluginId: string, enabled: boolean, requiredTools: string[] = []) {
  return apiFetch<{ status: string; plugin_id: string }>(`/agents/plugins/${encodeURIComponent(pluginId)}/${enabled ? "enable" : "disable"}`, {
    method: "POST", ...(enabled ? { body: JSON.stringify({ required_tools: requiredTools }) } : {}),
  });
}

export async function listIntegrations() {
  return apiFetch<{ integrations: Integration[]; count: number }>("/integrations");
}

export async function getIntegration(mcpId: string) {
  return apiFetch<Integration & { tools: IntegrationTool[] }>(`/integrations/${mcpId}`);
}

export async function buildIntegrationFromURL(url: string, name?: string, method?: "url" | "website") {
  return apiFetch<{ status: string; message: string; build_id?: string; mcp_id?: string }>(
    "/integrations/build-from-url",
    { method: "POST", body: JSON.stringify({ url, name, method }) }
  );
}

export async function buildIntegrationFromWebsite(url: string, name?: string, notes?: string) {
  return apiFetch<{ status: string; message: string; build_id?: string; mcp_id?: string }>(
    "/integrations/build-from-website",
    { method: "POST", body: JSON.stringify({ url, name, notes }) }
  );
}

export async function buildIntegrationFromSpec(spec: string, name?: string) {
  return apiFetch<{ status: string; message: string; build_id?: string; mcp_id?: string }>(
    "/integrations/build",
    { method: "POST", body: JSON.stringify({ spec, name }) }
  );
}

export async function buildIntegrationFromPrompt(prompt: string, name?: string) {
  return apiFetch<{ status: string; message: string; build_id?: string; mcp_id?: string }>(
    "/integrations/build-from-prompt",
    { method: "POST", body: JSON.stringify({ prompt, name }) }
  );
}

export async function getIntegrationBuild(buildId: string) {
  return apiFetch<{
    build_id: string;
    status: string;
    stage: string;
    logs: string[];
    mcp_id?: string;
    tools?: unknown[];
    error?: string;
    message?: string;
  }>(`/integrations/builds/${buildId}`);
}

export async function testIntegration(mcpId: string) {
  return apiFetch<{ status: string }>(`/integrations/${mcpId}/test`, { method: "POST" });
}

export async function enableIntegration(mcpId: string) {
  return apiFetch(`/integrations/${mcpId}/enable`, { method: "POST" });
}

export async function disableIntegration(mcpId: string) {
  return apiFetch(`/integrations/${mcpId}/disable`, { method: "POST" });
}

export async function deleteIntegration(mcpId: string) {
  return apiFetch(`/integrations/${mcpId}`, { method: "DELETE" });
}

// ── Notifications ────────────────────────────────────────────────

export async function listNotifications(unreadOnly = false, limit = 50) {
  return apiFetch<{ notifications: Notification[]; unread_count: number }>(
    `/notifications?unread_only=${unreadOnly}&limit=${limit}`
  );
}

export async function getUnreadCount() {
  return apiFetch<{ unread_count: number }>("/notifications/unread");
}

export async function markNotificationRead(id: string) {
  return apiFetch(`/notifications/${id}/read`, { method: "POST" });
}

export async function markAllNotificationsRead() {
  return apiFetch("/notifications/read-all", { method: "POST" });
}

// ── Schedules ────────────────────────────────────────────────────

export async function listSchedules() {
  return apiFetch<{ schedules: Schedule[]; count: number }>("/schedules");
}

export async function createSchedule(data: {
  name: string;
  goal: string;
  cron_expression: string;
  timezone?: string;
  is_enabled?: boolean;
}) {
  return apiFetch<Schedule>("/schedules", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function deleteSchedule(id: string) {
  return apiFetch(`/schedules/${id}`, { method: "DELETE" });
}

export async function runScheduleNow(id: string) {
  return apiFetch(`/schedules/${id}/run`, { method: "POST" });
}

export async function toggleSchedulePause(id: string) {
  return apiFetch(`/schedules/${id}/pause`, { method: "POST" });
}

// ── Settings ─────────────────────────────────────────────────────

export async function getSettings() {
  return apiFetch<{ settings: UserSettings; available_models?: string[] }>("/settings");
}

export async function updateSettings(data: Partial<UserSettings>) {
  return apiFetch<{ settings: UserSettings }>("/settings", {
    method: "PUT",
    body: JSON.stringify(data),
  });
}

// ── Memory ───────────────────────────────────────────────────────

export async function addMemory(content: string, memory_type = "semantic") {
  return apiFetch<{ memory_id: string }>("/memory", {
    method: "POST",
    body: JSON.stringify({ content, memory_type }),
  });
}

export async function searchMemory(query: string, limit = 10) {
  return apiFetch<{ results: unknown[] }>("/memory/search", {
    method: "POST",
    body: JSON.stringify({ query, limit }),
  });
}

// ── Approvals ────────────────────────────────────────────────────

export async function listApprovals() {
  return apiFetch<{ approvals: ApprovalRequest[]; count: number }>("/approvals");
}

export async function resolveApproval(approvalId: string, action: "approve" | "reject") {
  return apiFetch(`/approvals/${approvalId}/${action}`, { method: "POST" });
}

// ── Health ───────────────────────────────────────────────────────

export async function healthCheck() {
  const res = await fetch(`${API_BASE.replace("/api/v1", "")}/health`);
  return res.json();
}

// ── Credentials ──────────────────────────────────────────────────

export async function listCredentials() {
  return apiFetch<{ credentials: string[]; count: number }>("/credentials");
}

export async function storeCredential(name: string, values: Record<string, string>) {
  return apiFetch<{ name: string; fields: string[]; stored: boolean }>("/credentials", {
    method: "POST",
    body: JSON.stringify({ name, values }),
  });
}

export async function deleteCredential(name: string) {
  return apiFetch(`/credentials/${encodeURIComponent(name)}`, { method: "DELETE" });
}

// ── Capabilities ─────────────────────────────────────────────────

export async function checkSiteHealth(url: string) {
  return apiFetch<Record<string, unknown>>("/capabilities/site-health", {
    method: "POST",
    body: JSON.stringify({ url }),
  });
}

export async function debugSource(source: string, language = "python", error_message = "", goal = "") {
  return apiFetch<Record<string, unknown>>("/capabilities/debug", {
    method: "POST",
    body: JSON.stringify({ source, language, error_message, goal }),
  });
}

export async function pingGemini(candidateKey?: string) {
  return apiFetch<{ ok: boolean; reply: string; using_user_key: boolean }>("/capabilities/ping", {
    method: "POST",
    body: JSON.stringify(candidateKey ? { candidate_key: candidateKey } : {}),
  });
}

export async function validateCredential(name: string, values: Record<string, string>) {
  return apiFetch<{ valid: boolean; error?: string }>("/credentials/validate", {
    method: "POST",
    body: JSON.stringify({ name, values }),
  });
}

export interface GenerateProgress { job_id: string; status: string; stage?: string; completed_files?: number; total_files?: number }

export async function generateProject(brief: string, kind = "website", name = "", scale = "standard", onProgress?: (progress: GenerateProgress) => void) {
  const started = await apiFetch<{ job_id: string; status: string }>("/capabilities/generate", {
    method: "POST",
    body: JSON.stringify({ brief, kind, name, scale }),
  });
  const jobId = started.job_id;
  onProgress?.(started);
  const controller = new AbortController();
  void fetchEventSource(`${API_BASE}/capabilities/generate/${jobId}/events`, {
    headers: authHeaders(), credentials: "include", signal: controller.signal,
    onmessage(event) {
      if (event.event === "progress") {
        try { onProgress?.(JSON.parse(event.data)); } catch { /* polling recovers */ }
      }
    },
    onerror() { controller.abort(); },
  }).catch(() => {});
  try {
  const deadline = Date.now() + 30 * 60 * 1000;
  while (Date.now() < deadline) {
    const job = await apiFetch<{
      job_id: string;
      status: string;
      error?: string | null;
      result?: {
        artifact_id: string;
        name: string;
        summary: string;
        files: string[];
        entrypoint: string;
        kind: string;
        scale?: string;
      } | null;
    }>(`/capabilities/generate/${jobId}`);
    onProgress?.(job);
    if (job.status === "completed" && job.result) {
      return job.result;
    }
    if (job.status === "failed") {
      throw new Error(job.error || "Generation failed");
    }
    await new Promise((r) => setTimeout(r, 2500));
  }
  throw new Error(`Generation is still running (job ${jobId}). Check its saved status before starting another job.`);
  } finally { controller.abort(); }
}

export async function listArtifacts() {
  return apiFetch<{ artifacts: unknown[]; count: number }>("/artifacts");
}

export function artifactFileUrl(artifactId: string, filePath: string) {
  return `${API_BASE}/artifacts/${artifactId}/files/${filePath}`;
}

export async function fetchArtifactText(artifactId: string, filePath: string) {
  const res = await fetch(`${API_BASE}/artifacts/${artifactId}/files/${encodeURIComponent(filePath).replace(/%2F/g, "/")}`, {
    headers: { ...authHeaders() },
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error("Could not load generated file");
  }
  return res.text();
}

// ── Resume ───────────────────────────────────────────────────────

export async function createResumeFromText(profile_text: string, job_description = "", tailor = false) {
  return apiFetch<Record<string, unknown>>("/resume/create", {
    method: "POST",
    body: JSON.stringify({ profile_text, job_description, tailor }),
  });
}

export async function tailorResume(master_resume: Record<string, unknown>, job_description: string) {
  return apiFetch<{ status: string; tailored_resume: Record<string, unknown> }>("/resume/tailor", {
    method: "POST",
    body: JSON.stringify({ master_resume, job_description, target_job_id: "jd" }),
  });
}

export async function renderResumeHtml(resume: Record<string, unknown>) {
  return apiFetch<{ html: string; pdf_error?: string }>("/resume/render", {
    method: "POST",
    body: JSON.stringify({ resume, format: "html" }),
  });
}

export async function scanResumeFile(file: File, jobDescription: string) {
  await ensureCsrf();
  const form = new FormData();
  form.append("file", file);
  form.append("jobDescription", jobDescription);
  const headers: Record<string, string> = { ...authHeaders(), ...csrfHeaders() };
  delete (headers as { "Content-Type"?: string })["Content-Type"];
  const res = await fetch(`${API_BASE}/resume/scan`, {
    method: "POST",
    headers,
    body: form,
    credentials: "include",
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => ({}));
    throw new Error((errData as { detail?: string }).detail || `API error: ${res.status}`);
  }
  return res.json();
}

// ── Context usage ────────────────────────────────────────────────

export interface ContextCategory {
  id: string;
  label: string;
  tokens: number;
}

export interface ContextUsage {
  window_tokens: number;
  context_estimate: number;
  used_tokens: number;
  remaining_tokens?: number;
  percent: number;
  daily_limit: number;
  daily_used?: number;
  daily_remaining?: number;
  model: string;
  tool_count: number;
  categories: ContextCategory[];
}

export async function getContextUsage() {
  return apiFetch<ContextUsage>("/usage/context");
}


export async function listAdminUsers() {
  return apiFetch<{ users: Array<{ user_id: string; email?: string; name?: string; role: string; is_active: boolean; runs_total?: number; runs_5h?: number; last_run_at?: string }>; count: number; window_hours: number }>(
    "/admin/users"
  );
}

export async function setUserActive(userId: string, active: boolean) {
  return apiFetch<{ user_id: string; is_active: boolean }>(`/admin/users/${userId}/${active ? "enable" : "disable"}`, { method: "POST" });
}

export async function adminStats() {
  return apiFetch<{ users_total: number; users_active_5h: number; runs_total: number; integrations: number; window_hours: number }>("/admin/stats");
}

export async function setUserRole(userId: string, role: string) {
  return apiFetch<{ user_id: string; role: string }>(`/admin/users/${userId}/role`, { method: "POST", body: JSON.stringify({ role }) });
}


export async function deleteAnyUser(userId: string) {
  return apiFetch<{ deleted: boolean }>(`/admin/users/${userId}`, { method: "DELETE" });
}

export async function setUserLimits(userId: string, dailyTokenLimit?: number, windowHours?: number) {
  return apiFetch<{ user_id: string }>(`/admin/users/${userId}/limits`, {
    method: "PUT",
    body: JSON.stringify({ daily_token_limit: dailyTokenLimit ?? null, window_hours: windowHours ?? null }),
  });
}


export async function attachIntegrationKey(mcpId: string, apiKey: string) {
  return apiFetch(`/integrations/${mcpId}/credentials`, {
    method: "POST", body: JSON.stringify({api_key: apiKey}),
  });
}


export function subscribeBuildEvents(buildId: string, onUpdate: (build: Awaited<ReturnType<typeof getIntegrationBuild>>) => void) {
  const controller = new AbortController();
  void fetchEventSource(`${API_BASE}/integrations/builds/${buildId}/events`, {
    headers: authHeaders(), credentials: "include", signal: controller.signal,
    onmessage(message) {
      if (message.event !== "build") return;
      try { onUpdate(JSON.parse(message.data)); } catch { /* polling remains available */ }
    },
    onerror() { controller.abort(); },
  }).catch(() => { /* polling remains available */ });
  return () => controller.abort();
}


export async function downloadIntegrationServer(mcpId: string) {
  const response = await fetch(`${API_BASE}/integrations/${mcpId}/export`, {headers: authHeaders(), credentials: "include"});
  if (!response.ok) throw new Error("Server export is available for HTTP API integrations only.");
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement("a"); link.href = url; link.download = "generated-mcp.zip";
  link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export interface ConnectorRevision {
  revision_id: string;
  created_at: string;
  tool_count: number;
  version?: string;
}
export async function listConnectorRevisions(mcpId: string): Promise<{ revisions: ConnectorRevision[] }> {
  return apiFetch(`/integrations/${encodeURIComponent(mcpId)}/revisions`);
}
export async function checkpointConnector(mcpId: string) {
  return apiFetch(`/integrations/${encodeURIComponent(mcpId)}/revisions`, { method: "POST" });
}
export async function restoreConnectorRevision(mcpId: string, revisionId: string): Promise<{ mcp_id: string }> {
  return apiFetch(`/integrations/${encodeURIComponent(mcpId)}/revisions/${encodeURIComponent(revisionId)}/restore`, { method: "POST" });
}

export interface OperationsSummary {
  sample_size: number;
  sample_limit: number;
  completion_rate: number | null;
  median_completion_seconds: number | null;
  status_counts: Record<string, number>;
  failed_tasks_by_agent: Record<string, number>;
  attention: { run_id: string; status: string; reason: string; age_seconds: number | null }[];
  generated_at: string;
  cost_tracking: string;
}
export async function getOperationsSummary(): Promise<OperationsSummary> {
  return apiFetch("/usage/operations");
}
