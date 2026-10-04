export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "X-ChannelOS-Client": "web",
      ...(options.body && !(options.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...options.headers,
    },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      detail = data.detail ?? detail;
    } catch {
      // response body wasn't JSON — fall back to statusText
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body !== undefined ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PATCH", body: body !== undefined ? JSON.stringify(body) : undefined }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, form: FormData) => request<T>(path, { method: "POST", body: form }),
};

// ---- Domain types ----

export type User = { id: string; email: string; full_name: string };
export type Workspace = { id: string; name: string; slug: string; role: string };

export type TelegramAccount = {
  id: string;
  phone_masked: string;
  status: string;
  first_name: string;
  last_name: string;
  username: string | null;
  last_error: string | null;
};

export type TelegramChannel = {
  id: string;
  title: string;
  username: string | null;
  can_post: boolean;
  health: string;
  subscriber_count: number | null;
  autopilot_enabled: boolean;
  default_cta_key: string | null;
};

export type ChannelSet = {
  id: string;
  name: string;
  description: string;
  mode: string;
  autopilot_enabled: boolean;
  member_count: number;
};

export type ContentItem = {
  id: string;
  status: string;
  topic: string;
  category: string;
  title: string;
  plain_text: string;
  telegram_html: string;
  cta_key: string | null;
  tags: string[];
  duplicate_score: number | null;
  requires_review: boolean;
  scheduled_at: string | null;
  published_at: string | null;
};

export type CostDashboard = {
  today_rub: string;
  month_rub: string;
  month_budget_rub: string;
  forecast_month_end_rub: string;
};

export type AIStatus = {
  text_provider: string;
  text_provider_is_fake: boolean;
  image_provider: string;
  image_provider_status: string;
  image_provider_is_fake: boolean;
  telegram_provider_is_fake: boolean;
};

export type AuthFlow = {
  flow_id: string;
  state: string;
  phone_masked: string;
  expires_at: string;
  error: string | null;
  account_id: string | null;
  attempts_left: number;
  refresh_job_id: string | null;
};

export type JobRow = {
  id: string;
  job_type: string;
  status: string;
  attempt: number;
  max_attempts: number;
  error: string | null;
};

export type MediaAsset = {
  id: string;
  mime_type: string;
  width: number | null;
  height: number | null;
  size_bytes: number;
  status: string;
  url: string;
};

export type AutopilotConfig = {
  mode: string;
  channel_set_id: string | null;
  schedule_id: string | null;
  posts_per_day: number;
  daily_budget_rub: string;
  monthly_budget_rub: string;
  max_cost_per_post_rub: string;
  generate_image: boolean;
};

export type DistributionBatch = {
  id: string;
  content_item_id: string;
  status: string;
  publications: {
    id: string;
    channel_id: string;
    status: string;
    attempt: number;
    error_code: string | null;
    error_message: string | null;
    telegram_message_id: number | null;
  }[];
};

// ---- Endpoints ----

export const endpoints = {
  me: () => api.get<User>("/api/v1/auth/me"),
  login: (email: string, password: string) => api.post<User>("/api/v1/auth/login", { email, password }),
  register: (email: string, password: string, full_name: string, workspace_name: string) =>
    api.post<User>("/api/v1/auth/register", { email, password, full_name, workspace_name }),
  logout: () => api.post<void>("/api/v1/auth/logout"),

  workspaces: () => api.get<Workspace[]>("/api/v1/workspaces"),

  telegramAccounts: (ws: string) => api.get<TelegramAccount[]>(`/api/v1/workspaces/${ws}/telegram/accounts`),
  startTelegramAuth: (ws: string, phone: string, accountId?: string) =>
    api.post<AuthFlow>(`/api/v1/workspaces/${ws}/telegram/auth/start`, { phone, account_id: accountId ?? null }),
  submitTelegramCode: (ws: string, flowId: string, code: string) =>
    api.post<AuthFlow>(`/api/v1/workspaces/${ws}/telegram/auth/${flowId}/code`, { code }),
  submitTelegramPassword: (ws: string, flowId: string, password: string) =>
    api.post<AuthFlow>(`/api/v1/workspaces/${ws}/telegram/auth/${flowId}/password`, { password }),
  refreshTelegramChannels: (ws: string, accountId: string) =>
    api.post<JobRow>(`/api/v1/workspaces/${ws}/telegram/accounts/${accountId}/refresh-channels`),
  disconnectTelegramAccount: (ws: string, accountId: string) =>
    api.post<TelegramAccount>(`/api/v1/workspaces/${ws}/telegram/accounts/${accountId}/disconnect`),
  deleteTelegramAccount: (ws: string, accountId: string) =>
    api.delete<void>(`/api/v1/workspaces/${ws}/telegram/accounts/${accountId}`),

  channels: (ws: string) => api.get<TelegramChannel[]>(`/api/v1/workspaces/${ws}/channels`),
  updateChannel: (ws: string, channelId: string, payload: Partial<TelegramChannel>) =>
    api.patch<TelegramChannel>(`/api/v1/workspaces/${ws}/channels/${channelId}`, payload),

  channelSets: (ws: string) => api.get<ChannelSet[]>(`/api/v1/workspaces/${ws}/channel-sets`),
  createChannelSet: (ws: string, payload: { name: string; description: string; mode: string; channel_ids: string[] }) =>
    api.post<ChannelSet>(`/api/v1/workspaces/${ws}/channel-sets`, payload),

  content: (ws: string, statusFilter?: string) =>
    api
      .get<{ items: (ContentItem & { excerpt: string })[]; next_cursor: string | null }>(
        `/api/v1/workspaces/${ws}/content${statusFilter ? `?status=${statusFilter}` : ""}`,
      )
      .then((page) => page.items.map((i) => ({ ...i, plain_text: i.plain_text ?? i.excerpt }))),
  contentDetail: (ws: string, id: string) => api.get<ContentItem>(`/api/v1/workspaces/${ws}/content/${id}`),
  generateContent: (ws: string, payload: { instruction: string; channel_set_id?: string | null }) =>
    api.post<{ content: ContentItem; job: JobRow }>(`/api/v1/workspaces/${ws}/content/generate`, payload),
  editContent: (ws: string, id: string, payload: { title: string; telegram_html: string; plain_text: string }) =>
    api.patch<ContentItem>(`/api/v1/workspaces/${ws}/content/${id}`, payload),
  submitContent: (ws: string, id: string) => api.post<ContentItem>(`/api/v1/workspaces/${ws}/content/${id}/submit`),
  approveContent: (ws: string, id: string) => api.post<ContentItem>(`/api/v1/workspaces/${ws}/content/${id}/approve`),
  rejectContent: (ws: string, id: string) => api.post<ContentItem>(`/api/v1/workspaces/${ws}/content/${id}/reject`),
  scheduleContent: (ws: string, id: string, scheduled_at: string) =>
    api.post<ContentItem>(`/api/v1/workspaces/${ws}/content/${id}/schedule`, { scheduled_at }),

  costDashboard: (ws: string) => api.get<CostDashboard>(`/api/v1/workspaces/${ws}/analytics/costs`),
  aiStatus: (ws: string) => api.get<AIStatus>(`/api/v1/workspaces/${ws}/settings/ai-status`),

  jobs: (ws: string) => api.get<{ items: JobRow[]; next_cursor: string | null; counts: Record<string, number> }>(`/api/v1/workspaces/${ws}/jobs`),

  media: (ws: string) => api.get<MediaAsset[]>(`/api/v1/workspaces/${ws}/media`),
  uploadMedia: (ws: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.upload<MediaAsset>(`/api/v1/workspaces/${ws}/media/upload`, form);
  },

  autopilot: (ws: string) => api.get<AutopilotConfig>(`/api/v1/workspaces/${ws}/autopilot`),
  updateAutopilot: (ws: string, payload: Partial<AutopilotConfig>) =>
    api.patch<AutopilotConfig>(`/api/v1/workspaces/${ws}/autopilot`, payload),

  retryBatch: (ws: string, batchId: string) =>
    api.post<DistributionBatch>(`/api/v1/workspaces/${ws}/distributions/${batchId}/retry-failed`),
  batch: (ws: string, batchId: string) => api.get<DistributionBatch>(`/api/v1/workspaces/${ws}/distributions/${batchId}`),
  batchesForContent: (ws: string, contentId: string) =>
    api.get<DistributionBatch[]>(`/api/v1/workspaces/${ws}/distributions?content_id=${contentId}`),
};
