export const API_BASE: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  retryAfter: number | null;
  kind: string | null;
  constructor(
    status: number,
    message: string,
    retryAfter: number | null = null,
    kind: string | null = null,
  ) {
    super(message);
    this.status = status;
    this.retryAfter = retryAfter;
    this.kind = kind;
  }
}

function describe(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors -> readable sentence
    return detail
      .map((d: { msg?: string; loc?: unknown[] }) => {
        const field = Array.isArray(d.loc)
          ? d.loc.filter((p) => p !== "body").join(".")
          : "";
        return `${field ? field + ": " : ""}${(d.msg ?? "").replace(/^Value error, /, "")}`;
      })
      .join("; ");
  }
  return fallback;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
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
  } catch {
    throw new ApiError(
      0,
      "Can't reach the ChannelOS API. Check your connection or that the backend is running.",
    );
  }
  if (!response.ok) {
    let message = response.statusText || `Request failed (${response.status})`;
    let kind: string | null = null;
    try {
      const data = await response.json();
      message = describe(data.detail, message);
      kind = data.kind ?? null;
    } catch {
      // non-JSON error body
    }
    const retry = response.headers.get("Retry-After");
    throw new ApiError(
      response.status,
      message,
      retry ? Number(retry) : null,
      kind,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const json =
  (method: string) =>
  <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: json("POST"),
  put: json("PUT"),
  patch: json("PATCH"),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, form: FormData) =>
    request<T>(path, { method: "POST", body: form }),
};

export function qs(
  params: Record<
    string,
    string | number | boolean | string[] | null | undefined
  >,
): string {
  const out = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => out.append(k, x));
    else out.set(k, String(v));
  }
  const s = out.toString();
  return s ? `?${s}` : "";
}

// ---------------------------------------------------------------- types

export type User = { id: string; email: string; full_name: string };
export type Role = "OWNER" | "ADMIN" | "EDITOR" | "APPROVER" | "VIEWER";
export type Workspace = { id: string; name: string; slug: string; role: Role };
export type Session = {
  id: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  ip_address: string;
  user_agent: string;
  current: boolean;
};
export type Member = {
  user_id: string;
  email: string;
  full_name: string;
  role: Role;
};

export type TelegramAccount = {
  id: string;
  phone_masked: string;
  status: string;
  first_name: string;
  last_name: string;
  username: string | null;
  last_error: string | null;
  flood_wait_until: string | null;
  last_heartbeat_at: string | null;
  channel_count: number;
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
export type Channel = {
  id: string;
  title: string;
  username: string | null;
  can_post: boolean;
  health: string;
  subscriber_count: number | null;
  autopilot_enabled: boolean;
  default_cta_key: string | null;
  timezone: string;
  tone_profile_id: string | null;
  cta_overrides: Record<string, string>;
  account_id: string;
  account_label: string;
  account_status: string;
  last_published_at: string | null;
  next_scheduled_at: string | null;
  posts_30d: number;
};
export type ChannelSet = {
  id: string;
  name: string;
  description: string;
  mode: string;
  autopilot_enabled: boolean;
  member_count: number;
  healthy_count: number;
  subscribers: number;
};
export type ChannelSetDetail = ChannelSet & {
  channels: Channel[];
  recent_posts: {
    content_id: string;
    title: string;
    status: string;
    published_at: string | null;
    scheduled_at: string | null;
    targets: number;
    published: number;
    failed: number;
    views: number;
  }[];
  totals: {
    publications: number;
    views: number;
    forwards: number;
    reactions: number;
  };
  schedules: {
    id: string;
    name: string;
    enabled: boolean;
    posts_per_day: number;
  }[];
};

export type Content = {
  id: string;
  status: string;
  topic: string;
  category: string;
  angle: string;
  title: string;
  plain_text: string;
  telegram_html: string;
  cta_key: string | null;
  tags: string[];
  sources: string[];
  risk_flags: string[];
  duplicate_score: number | null;
  requires_review: boolean;
  image_prompt: string;
  media_asset_id: string | null;
  channel_set_id: string | null;
  series_id: string | null;
  schedule_id: string | null;
  tone_profile_id: string | null;
  source_item_id: string | null;
  scheduled_at: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
  created_by_user_id: string | null;
  latest_revision_id: string | null;
  ai_cost_rub: string;
};
export type ContentListItem = {
  id: string;
  status: string;
  title: string;
  topic: string;
  category: string;
  excerpt: string;
  channel_set_id: string | null;
  channel_set_name: string | null;
  series_id: string | null;
  targets: number;
  published_count: number;
  failed_count: number;
  views: number;
  ai_cost_rub: string;
  scheduled_at: string | null;
  published_at: string | null;
  created_at: string;
  author_id: string | null;
  author_name: string | null;
  media_asset_id: string | null;
  duplicate_score: number | null;
  requires_review: boolean;
};
export type Page<T> = { items: T[]; next_cursor: string | null };
export type Revision = {
  id: string;
  version: number;
  action: string;
  is_ai: boolean;
  author_id: string | null;
  author_name: string | null;
  created_at: string;
  title: string;
  telegram_html: string;
  cost_rub: string | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  diff: { op: "equal" | "insert" | "delete"; text: string }[];
};
export type CostBreakdown = {
  lines: {
    operation: string;
    count: number;
    failed: number;
    prompt_tokens: number;
    completion_tokens: number;
    cost_rub: string;
  }[];
  text_cost_rub: string;
  image_cost_rub: string;
  total_rub: string;
};
export type CalendarEntry = {
  id: string;
  title: string;
  status: string;
  category: string;
  at: string;
  kind: "scheduled" | "published";
  channel_set_id: string | null;
  channel_set_name: string | null;
  media_asset_id: string | null;
  targets: number;
  published_count: number;
  failed_count: number;
};
export type FreeSlot = {
  schedule_id: string;
  schedule_name: string;
  channel_set_id: string | null;
  at: string;
};
export type ActiveContext = {
  tone: { id: string; name: string; source: string } | null;
  series: { id: string; title: string; next_label: string } | null;
};

export type Job = {
  id: string;
  job_type: string;
  status: string;
  progress: number;
  entity_type: string | null;
  entity_id: string | null;
  payload_summary: string;
  attempt: number;
  max_attempts: number;
  queued_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  next_retry_at: string | null;
  worker: string | null;
  error_code: string | null;
  error_message: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
  duration_ms: number | null;
};
export type JobDetail = Job & {
  attempts: {
    attempt_number: number;
    status: string;
    error: string | null;
    started_at: string | null;
    finished_at: string | null;
    duration_ms: number | null;
  }[];
};
export type JobPage = Page<Job> & { counts: Record<string, number> };

export type Publication = {
  id: string;
  channel_id: string;
  channel_title: string | null;
  channel_username: string | null;
  status: string;
  attempt: number;
  error_code: string | null;
  error_message: string | null;
  flood_wait_seconds: number | null;
  telegram_message_id: number | null;
  published_at: string | null;
  delivery_unknown: boolean;
};
export type Batch = {
  id: string;
  content_item_id: string;
  status: string;
  created_at: string;
  publications: Publication[];
};

export type MediaAsset = {
  id: string;
  mime_type: string;
  width: number | null;
  height: number | null;
  size_bytes: number;
  status: string;
  source: "generated" | "uploaded";
  used: boolean;
  original_filename: string;
  url: string;
  created_at: string;
};
export type MediaDetail = MediaAsset & {
  provider: string | null;
  model: string | null;
  prompt: string | null;
  cost_rub: string | null;
  checksum_sha256: string;
  linked_posts: { id: string; title: string; status: string }[];
};
export type ImageProviderInfo = {
  provider: string;
  status: string;
  available: boolean;
  message: string | null;
  sizes: string[];
};

export type Schedule = {
  id: string;
  name: string;
  channel_set_id: string | null;
  channel_set_name: string | null;
  timezone: string;
  days_of_week: number[];
  posts_per_day: number;
  windows: { start: string; end: string }[];
  randomize: boolean;
  min_interval_minutes: number;
  max_posts_per_day: number;
  categories: string[];
  exclude_dates: string[];
  enabled: boolean;
  misfire_policy: string | null;
  scheduled_count: number;
  next_slots: string[];
};
export type ScheduleInput = Omit<
  Schedule,
  "id" | "channel_set_name" | "scheduled_count" | "next_slots"
>;

export type KnowledgeBase = {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  documents: number;
  entries: number;
  created_at: string;
};
export type KnowledgeDoc = {
  id: string;
  knowledge_base_id: string | null;
  title: string;
  kind: string;
  format: string;
  enabled: boolean;
  valid_until: string | null;
  source_filename: string;
  entries: number;
  warnings: string[];
  updated_at: string;
};
export type KnowledgeDocDetail = KnowledgeDoc & {
  preview: {
    id: string;
    index: number;
    kind: string;
    content: string;
    effective_at: string | null;
    metadata: Record<string, unknown>;
  }[];
};
export type KnowledgeHit = {
  document_id: string;
  document_title: string;
  kind: string;
  snippet: string;
  effective_at: string | null;
};

export type ToneProfile = {
  id: string;
  name: string;
  description: string;
  language: string;
  addressing: string;
  formality: string;
  emoji_policy: string;
  headline_style: string;
  paragraph_style: string;
  average_length: string;
  cta_style: string;
  allowed_vocabulary: string[];
  forbidden_vocabulary: string[];
  cliches_blacklist: string[];
  good_examples: string[];
  bad_examples: string[];
  is_workspace_default: boolean;
  channel_count: number;
  series_count: number;
  updated_at: string;
};
export type ToneInput = Omit<
  ToneProfile,
  | "id"
  | "is_workspace_default"
  | "channel_count"
  | "series_count"
  | "updated_at"
>;

export type SeriesPart = {
  label: string;
  number: number;
  title: string;
  status: string;
  content_id: string;
};
export type Series = {
  id: string;
  title: string;
  description: string;
  channel_set_id: string | null;
  tone_profile_id: string | null;
  schedule_id: string | null;
  category: string;
  status: string;
  numbering_format: string;
  planned_topics: string[];
  channel_set_name: string | null;
  tone_profile_name: string | null;
  published_count: number;
  planned_count: number;
  next_topic: string | null;
  next_label: string;
  remaining_topics: string[];
  items: SeriesPart[];
  in_progress: SeriesPart[];
  updated_at: string;
};
export type SeriesInput = Pick<
  Series,
  | "title"
  | "description"
  | "channel_set_id"
  | "tone_profile_id"
  | "schedule_id"
  | "category"
  | "status"
  | "numbering_format"
  | "planned_topics"
>;

export type Source = {
  id: string;
  kind: string;
  name: string;
  enabled: boolean;
  config: Record<string, unknown>;
  last_fetched_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  items_total: number;
  items_new: number;
};
export type Idea = {
  id: string;
  source_id: string;
  source_name: string;
  title: string;
  summary: string;
  url: string;
  url_verified: boolean;
  published_at: string | null;
  freshness: number;
  relevance: number;
  status: string;
  category: string;
  created_at: string;
};

export type AuditEntry = {
  id: string;
  actor_id: string | null;
  actor_name: string;
  action: string;
  entity_type: string;
  entity_id: string;
  metadata: Record<string, unknown>;
  created_at: string;
};
export type Notification = {
  id: string;
  kind: string;
  message: string;
  metadata: Record<string, unknown>;
  read: boolean;
  created_at: string;
};
export type SearchResult = {
  kind: "post" | "channel" | "channel_set";
  id: string;
  title: string;
  subtitle: string;
};

export type Named = {
  key: string;
  label: string;
  cost_rub: string;
  requests: number;
};
export type CostDashboard = {
  today_rub: string;
  week_rub: string;
  month_rub: string;
  daily_budget_rub: string;
  month_budget_rub: string;
  warning_pct: number;
  forecast_month_end_rub: string;
  input_tokens_month: number;
  output_tokens_month: number;
  breakdown: Named[];
  by_channel_set: Named[];
  by_category: Named[];
  by_provider: Named[];
  daily: { day: string; cost_rub: string }[];
  top_content: {
    content_id: string;
    title: string;
    status: string;
    cost_rub: string;
    requests: number;
  }[];
};
export type PostBrief = {
  content_id: string;
  title: string;
  status: string;
  at: string | null;
  channel_set_name: string | null;
  targets: number;
  published: number;
  failed: number;
  views: number;
};
export type HealthCheck = {
  ok: boolean;
  error?: string;
  last_seen_seconds_ago?: number;
};
export type Dashboard = {
  channels: number;
  channels_healthy: number;
  accounts: number;
  accounts_connected: number;
  posts_today: number;
  scheduled: number;
  pending_approval: number;
  failed_publications_7d: number;
  failed_jobs_7d: number;
  next_scheduled: PostBrief[];
  recent_published: PostBrief[];
  recent_failed: {
    content_id: string;
    title: string;
    channel_title: string;
    error: string | null;
    at: string;
  }[];
  telegram_accounts: {
    id: string;
    phone: string;
    status: string;
    flood_wait_until: string | null;
    last_heartbeat_at: string | null;
  }[];
  ai_provider: {
    text: string;
    text_fake: boolean;
    image: string;
    image_status: string;
  };
  system: Record<
    "postgres" | "redis" | "s3" | "worker" | "scheduler",
    HealthCheck
  >;
  views_7d: { day: string; views: number }[];
  top_posts: PostBrief[];
  has_metrics: boolean;
};
export type Settings = {
  general: {
    workspace_name: string;
    timezone: string;
    misfire_policy: string;
    misfire_grace_minutes: number;
    cta_defaults: Record<string, string>;
    cta_keys: string[];
  };
  ai: {
    text_provider: string;
    text_provider_is_fake: boolean;
    agent_base_url: string;
    agent_api_key: string | null;
    model: string;
    pricing: Record<string, string>;
    image_provider: string;
    image_provider_status: string;
    image_provider_is_fake: boolean;
    gateway_api_key: string | null;
    gateway_image_model: string | null;
  };
  budget: {
    daily_budget_rub: string;
    monthly_budget_rub: string;
    max_cost_per_post_rub: string;
    budget_warning_pct: number;
  };
  telegram: {
    api_id_configured: boolean;
    api_hash_configured: boolean;
    session_encryption_configured: boolean;
    provider_is_fake: boolean;
  };
  storage: { endpoint_host: string; bucket: string; access_key: string | null };
  security: {
    session_max_age_hours: number;
    idle_timeout_hours: number;
    secure_cookies: boolean;
    environment: string;
  };
  notifications: { muted_kinds?: string[] };
};
export type AIStatus = {
  text_provider: string;
  text_provider_is_fake: boolean;
  image_provider: string;
  image_provider_status: string;
  image_provider_is_fake: boolean;
  telegram_provider_is_fake: boolean;
};
export type Autopilot = {
  mode: string;
  channel_set_id: string | null;
  schedule_id: string | null;
  posts_per_day: number;
  daily_budget_rub: string;
  monthly_budget_rub: string;
  max_cost_per_post_rub: string;
  generate_image: boolean;
};

// ---------------------------------------------------------------- endpoints

const W = (ws: string) => `/api/v1/workspaces/${ws}`;

export const endpoints = {
  me: () => api.get<User>("/api/v1/auth/me"),
  login: (email: string, password: string) =>
    api.post<User>("/api/v1/auth/login", { email, password }),
  register: (body: {
    email: string;
    password: string;
    full_name: string;
    workspace_name: string;
  }) => api.post<User>("/api/v1/auth/register", body),
  logout: () => api.post<void>("/api/v1/auth/logout"),
  sessions: () => api.get<Session[]>("/api/v1/auth/sessions"),
  revokeOtherSessions: () =>
    api.post<void>("/api/v1/auth/sessions/revoke-others"),

  workspaces: () => api.get<Workspace[]>("/api/v1/workspaces"),
  members: (ws: string) =>
    api.get<Member[]>(`/api/v1/workspaces/${ws}/members`),
  addMember: (ws: string, email: string, role: Role) =>
    api.post<Member[]>(`/api/v1/workspaces/${ws}/members`, { email, role }),
  changeRole: (ws: string, userId: string, role: Role) =>
    api.patch<Member[]>(`/api/v1/workspaces/${ws}/members/${userId}`, { role }),

  telegramAccounts: (ws: string) =>
    api.get<TelegramAccount[]>(`${W(ws)}/telegram/accounts`),
  startTelegramAuth: (ws: string, phone: string, accountId?: string) =>
    api.post<AuthFlow>(`${W(ws)}/telegram/auth/start`, {
      phone,
      account_id: accountId ?? null,
    }),
  submitTelegramCode: (ws: string, flowId: string, code: string) =>
    api.post<AuthFlow>(`${W(ws)}/telegram/auth/${flowId}/code`, { code }),
  submitTelegramPassword: (ws: string, flowId: string, password: string) =>
    api.post<AuthFlow>(`${W(ws)}/telegram/auth/${flowId}/password`, {
      password,
    }),
  refreshTelegramChannels: (ws: string, accountId: string) =>
    api.post<Job>(`${W(ws)}/telegram/accounts/${accountId}/refresh-channels`),
  disconnectTelegramAccount: (ws: string, accountId: string) =>
    api.post<TelegramAccount>(
      `${W(ws)}/telegram/accounts/${accountId}/disconnect`,
    ),
  deleteTelegramAccount: (ws: string, accountId: string) =>
    api.delete<void>(`${W(ws)}/telegram/accounts/${accountId}`),

  channels: (ws: string) => api.get<Channel[]>(`${W(ws)}/channels`),
  updateChannel: (ws: string, id: string, body: Record<string, unknown>) =>
    api.patch<Channel>(`${W(ws)}/channels/${id}`, body),
  channelSets: (ws: string) => api.get<ChannelSet[]>(`${W(ws)}/channel-sets`),
  channelSet: (ws: string, id: string) =>
    api.get<ChannelSetDetail>(`${W(ws)}/channel-sets/${id}`),
  createChannelSet: (
    ws: string,
    body: {
      name: string;
      description: string;
      mode: string;
      channel_ids: string[];
    },
  ) => api.post<ChannelSet>(`${W(ws)}/channel-sets`, body),
  updateChannelSet: (
    ws: string,
    id: string,
    body: {
      name: string;
      description: string;
      mode: string;
      channel_ids: string[];
    },
  ) => api.put<ChannelSet>(`${W(ws)}/channel-sets/${id}`, body),
  deleteChannelSet: (ws: string, id: string) =>
    api.delete<void>(`${W(ws)}/channel-sets/${id}`),

  content: (
    ws: string,
    p: {
      status?: string[];
      q?: string;
      category?: string;
      channel_set_id?: string;
      series_id?: string;
      cursor?: string;
      limit?: number;
    } = {},
  ) => api.get<Page<ContentListItem>>(`${W(ws)}/content${qs(p)}`),
  contentDetail: (ws: string, id: string) =>
    api.get<Content>(`${W(ws)}/content/${id}`),
  contentContext: (ws: string, id: string) =>
    api.get<ActiveContext>(`${W(ws)}/content/${id}/context`),
  createContent: (
    ws: string,
    body: {
      title: string;
      telegram_html: string;
      channel_set_id?: string | null;
      category?: string;
    },
  ) => api.post<Content>(`${W(ws)}/content`, body),
  generateContent: (
    ws: string,
    body: {
      instruction?: string;
      channel_set_id?: string | null;
      tone_profile_id?: string | null;
      series_id?: string | null;
      source_item_id?: string | null;
      topic?: string;
    },
  ) =>
    api.post<{ content: Content; job: Job }>(`${W(ws)}/content/generate`, body),
  editContent: (ws: string, id: string, body: Record<string, unknown>) =>
    api.patch<Content>(`${W(ws)}/content/${id}`, body),
  transform: (
    ws: string,
    id: string,
    body: {
      operation: string;
      selection?: string;
      instructions?: string;
      tone_profile_id?: string | null;
      base_revision_id?: string | null;
    },
  ) => api.post<Job>(`${W(ws)}/content/${id}/transform`, body),
  revisions: (ws: string, id: string) =>
    api.get<Revision[]>(`${W(ws)}/content/${id}/revisions`),
  restoreRevision: (ws: string, id: string, revId: string) =>
    api.post<Content>(`${W(ws)}/content/${id}/revisions/${revId}/restore`),
  contentCosts: (ws: string, id: string) =>
    api.get<CostBreakdown>(`${W(ws)}/content/${id}/costs`),
  submitContent: (ws: string, id: string) =>
    api.post<Content>(`${W(ws)}/content/${id}/submit`),
  approveContent: (ws: string, id: string) =>
    api.post<Content>(`${W(ws)}/content/${id}/approve`),
  rejectContent: (ws: string, id: string) =>
    api.post<Content>(`${W(ws)}/content/${id}/reject`),
  scheduleContent: (
    ws: string,
    id: string,
    body: { scheduled_at?: string; schedule_id?: string },
  ) => api.post<Content>(`${W(ws)}/content/${id}/schedule`, body),
  rescheduleContent: (ws: string, id: string, scheduled_at: string) =>
    api.patch<Content>(`${W(ws)}/content/${id}/schedule`, { scheduled_at }),
  unscheduleContent: (ws: string, id: string) =>
    api.delete<Content>(`${W(ws)}/content/${id}/schedule`),
  publishNow: (ws: string, id: string) =>
    api.post<Content>(`${W(ws)}/content/${id}/publish-now`),
  archiveContent: (ws: string, id: string) =>
    api.post<Content>(`${W(ws)}/content/${id}/archive`),
  deleteContent: (ws: string, id: string) =>
    api.delete<void>(`${W(ws)}/content/${id}`),
  calendar: (ws: string, start: string, end: string, channelSetId?: string) =>
    api.get<{ entries: CalendarEntry[]; free_slots: FreeSlot[] }>(
      `${W(ws)}/content/calendar${qs({ start, end, channel_set_id: channelSetId })}`,
    ),

  batches: (ws: string, contentId: string) =>
    api.get<Batch[]>(`${W(ws)}/distributions${qs({ content_id: contentId })}`),
  retryBatch: (ws: string, batchId: string) =>
    api.post<Batch>(`${W(ws)}/distributions/${batchId}/retry-failed`),
  resolvePublication: (
    ws: string,
    pubId: string,
    outcome: "published" | "failed",
  ) =>
    api.post<Batch>(`${W(ws)}/distributions/publications/${pubId}/resolve`, {
      outcome,
    }),

  jobs: (
    ws: string,
    p: {
      status?: string[];
      type?: string[];
      q?: string;
      entity_id?: string;
      cursor?: string;
      limit?: number;
    } = {},
  ) => api.get<JobPage>(`${W(ws)}/jobs${qs(p)}`),
  job: (ws: string, id: string) => api.get<JobDetail>(`${W(ws)}/jobs/${id}`),
  retryJob: (ws: string, id: string) =>
    api.post<Job>(`${W(ws)}/jobs/${id}/retry`),
  cancelJob: (ws: string, id: string) =>
    api.post<Job>(`${W(ws)}/jobs/${id}/cancel`),

  media: (
    ws: string,
    p: { tab?: string; cursor?: string; limit?: number } = {},
  ) => api.get<Page<MediaAsset>>(`${W(ws)}/media${qs(p)}`),
  mediaDetail: (ws: string, id: string) =>
    api.get<MediaDetail>(`${W(ws)}/media/${id}`),
  uploadMedia: (ws: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return api.upload<MediaAsset>(`${W(ws)}/media/upload`, form);
  },
  archiveMedia: (ws: string, id: string, archived: boolean) =>
    api.post<MediaAsset>(`${W(ws)}/media/${id}/archive${qs({ archived })}`),
  imageProvider: (ws: string) =>
    api.get<ImageProviderInfo>(`${W(ws)}/media/image-provider`),
  generateImage: (ws: string, prompt: string, contentId?: string) =>
    api.post<Job>(`${W(ws)}/media/generate`, {
      prompt,
      content_id: contentId ?? null,
    }),

  schedules: (ws: string) => api.get<Schedule[]>(`${W(ws)}/schedules`),
  createSchedule: (ws: string, body: ScheduleInput) =>
    api.post<Schedule>(`${W(ws)}/schedules`, body),
  updateSchedule: (ws: string, id: string, body: ScheduleInput) =>
    api.put<Schedule>(`${W(ws)}/schedules/${id}`, body),
  pauseSchedule: (ws: string, id: string, paused: boolean) =>
    api.post<Schedule>(`${W(ws)}/schedules/${id}/pause${qs({ paused })}`),
  deleteSchedule: (ws: string, id: string) =>
    api.delete<void>(`${W(ws)}/schedules/${id}`),
  previewSchedule: (ws: string, body: ScheduleInput) =>
    api.post<string[]>(`${W(ws)}/schedules/preview`, body),

  knowledgeBases: (ws: string) =>
    api.get<KnowledgeBase[]>(`${W(ws)}/knowledge/bases`),
  createKnowledgeBase: (
    ws: string,
    body: { name: string; description: string; enabled: boolean },
  ) => api.post<KnowledgeBase>(`${W(ws)}/knowledge/bases`, body),
  updateKnowledgeBase: (
    ws: string,
    id: string,
    body: { name: string; description: string; enabled: boolean },
  ) => api.patch<KnowledgeBase>(`${W(ws)}/knowledge/bases/${id}`, body),
  deleteKnowledgeBase: (ws: string, id: string) =>
    api.delete<void>(`${W(ws)}/knowledge/bases/${id}`),
  knowledgeDocs: (ws: string, p: { base_id?: string; kind?: string } = {}) =>
    api.get<KnowledgeDoc[]>(`${W(ws)}/knowledge/documents${qs(p)}`),
  knowledgeDoc: (ws: string, id: string) =>
    api.get<KnowledgeDocDetail>(`${W(ws)}/knowledge/documents/${id}`),
  uploadKnowledge: (
    ws: string,
    file: File,
    kind: string,
    baseId?: string | null,
    title?: string,
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    if (baseId) form.append("knowledge_base_id", baseId);
    if (title) form.append("title", title);
    return api.upload<KnowledgeDocDetail>(
      `${W(ws)}/knowledge/documents/upload`,
      form,
    );
  },
  createKnowledgeEntry: (
    ws: string,
    body: {
      title: string;
      kind: string;
      text: string;
      knowledge_base_id?: string | null;
      valid_until?: string | null;
    },
  ) => api.post<KnowledgeDocDetail>(`${W(ws)}/knowledge/documents`, body),
  updateKnowledgeDoc: (ws: string, id: string, body: Record<string, unknown>) =>
    api.patch<KnowledgeDoc>(`${W(ws)}/knowledge/documents/${id}`, body),
  deleteKnowledgeDoc: (ws: string, id: string) =>
    api.delete<void>(`${W(ws)}/knowledge/documents/${id}`),
  searchKnowledge: (ws: string, q: string) =>
    api.get<KnowledgeHit[]>(`${W(ws)}/knowledge/search${qs({ q })}`),

  toneProfiles: (ws: string) =>
    api.get<ToneProfile[]>(`${W(ws)}/tone-profiles`),
  createTone: (ws: string, body: ToneInput) =>
    api.post<ToneProfile>(`${W(ws)}/tone-profiles`, body),
  updateTone: (ws: string, id: string, body: ToneInput) =>
    api.put<ToneProfile>(`${W(ws)}/tone-profiles/${id}`, body),
  deleteTone: (ws: string, id: string) =>
    api.delete<void>(`${W(ws)}/tone-profiles/${id}`),
  makeToneDefault: (ws: string, id: string) =>
    api.post<ToneProfile>(`${W(ws)}/tone-profiles/${id}/make-default`),

  series: (ws: string) => api.get<Series[]>(`${W(ws)}/series`),
  seriesDetail: (ws: string, id: string) =>
    api.get<Series>(`${W(ws)}/series/${id}`),
  createSeries: (ws: string, body: SeriesInput) =>
    api.post<Series>(`${W(ws)}/series`, body),
  updateSeries: (ws: string, id: string, body: SeriesInput) =>
    api.put<Series>(`${W(ws)}/series/${id}`, body),
  deleteSeries: (ws: string, id: string) =>
    api.delete<void>(`${W(ws)}/series/${id}`),

  sources: (ws: string) => api.get<Source[]>(`${W(ws)}/sources`),
  createSource: (
    ws: string,
    body: {
      kind: string;
      name: string;
      config: Record<string, unknown>;
      enabled: boolean;
    },
  ) => api.post<Source>(`${W(ws)}/sources`, body),
  updateSource: (ws: string, id: string, body: Record<string, unknown>) =>
    api.patch<Source>(`${W(ws)}/sources/${id}`, body),
  deleteSource: (ws: string, id: string) =>
    api.delete<void>(`${W(ws)}/sources/${id}`),
  fetchSource: (ws: string, id: string) =>
    api.post<Job>(`${W(ws)}/sources/${id}/fetch`),
  ideas: (
    ws: string,
    p: { status?: string[]; source_id?: string; q?: string } = {},
  ) =>
    api.get<{ items: Idea[]; counts: Record<string, number> }>(
      `${W(ws)}/ideas${qs(p)}`,
    ),
  updateIdea: (ws: string, id: string, status: string) =>
    api.patch<Idea>(`${W(ws)}/ideas/${id}`, { status }),

  audit: (
    ws: string,
    p: {
      action?: string;
      actor_id?: string;
      entity_type?: string;
      since?: string;
      until?: string;
      q?: string;
      cursor?: string;
    } = {},
  ) =>
    api.get<Page<AuditEntry> & { actions: string[] }>(`${W(ws)}/audit${qs(p)}`),
  notifications: (ws: string, unreadOnly = false) =>
    api.get<{ items: Notification[]; unread: number }>(
      `${W(ws)}/notifications${qs({ unread_only: unreadOnly })}`,
    ),
  readNotification: (ws: string, id: string) =>
    api.post<void>(`${W(ws)}/notifications/${id}/read`),
  readAllNotifications: (ws: string) =>
    api.post<void>(`${W(ws)}/notifications/read-all`),
  search: (ws: string, q: string) =>
    api.get<SearchResult[]>(`${W(ws)}/search${qs({ q })}`),

  costDashboard: (ws: string) =>
    api.get<CostDashboard>(`${W(ws)}/analytics/costs`),
  dashboard: (ws: string) => api.get<Dashboard>(`${W(ws)}/analytics/dashboard`),
  contentAnalytics: (ws: string, id: string) =>
    api.get<{
      total_views: number;
      total_forwards: number;
      total_reactions: number;
      per_channel: {
        channel_id: string;
        channel_title: string;
        views: number;
        forwards: number;
        reactions: number;
        published_at: string | null;
      }[];
    }>(`${W(ws)}/analytics/content/${id}`),
  performance: (ws: string, days = 30) =>
    api.get<
      {
        channel_id: string;
        channel_title: string;
        posts: number;
        views: number;
        forwards: number;
        reactions: number;
      }[]
    >(`${W(ws)}/analytics/performance${qs({ days })}`),

  settings: (ws: string) => api.get<Settings>(`${W(ws)}/settings`),
  updateGeneralSettings: (
    ws: string,
    body: Omit<Settings["general"], "cta_keys">,
  ) => api.put<Settings>(`${W(ws)}/settings/general`, body),
  updateBudget: (ws: string, body: Settings["budget"]) =>
    api.put<Settings>(`${W(ws)}/settings/budget`, body),
  updateNotificationPrefs: (ws: string, body: { muted_kinds: string[] }) =>
    api.put<Settings>(`${W(ws)}/settings/notifications`, body),
  aiStatus: (ws: string) => api.get<AIStatus>(`${W(ws)}/settings/ai-status`),
  autopilot: (ws: string) => api.get<Autopilot>(`${W(ws)}/autopilot`),
  updateAutopilot: (ws: string, body: Partial<Autopilot>) =>
    api.patch<Autopilot>(`${W(ws)}/autopilot`, body),
};

export function mediaUrl(path: string) {
  return `${API_BASE}${path}`;
}
