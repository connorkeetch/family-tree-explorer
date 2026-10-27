import type {
  TreeCreated,
  TreeMeta,
  TreeSummary,
  OriginsSummary,
  MapPayload,
  FanPayload,
  DeadendsPayload,
  DuplicatesPayload,
  UserOut,
} from "./types";

const BASE = "/api";

async function json<T>(url: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(url, { credentials: "include", ...init });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    // Message is the human-readable detail only (no "NNN:" prefix); the numeric
    // status is carried on `err.status` for callers that branch on it (e.g. 401).
    const err = new Error(detail) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return (await res.json()) as T;
}

function postJson<T>(url: string, body: unknown): Promise<T> {
  return json<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export const api = {
  health: () => json<{ status: string }>(`${BASE}/health`),

  // auth
  register: (email: string, password: string, invite?: string) =>
    postJson<UserOut>(`${BASE}/auth/register`, { email, password, invite }),
  login: (email: string, password: string) =>
    postJson<UserOut>(`${BASE}/auth/login`, { email, password }),
  logout: () => postJson<{ ok: boolean }>(`${BASE}/auth/logout`, {}),
  me: () => json<UserOut>(`${BASE}/auth/me`),

  // trees
  listTrees: () => json<TreeSummary[]>(`${BASE}/trees`),
  deleteTree: (id: string) => json<{ ok: boolean }>(`${BASE}/trees/${id}`, { method: "DELETE" }),
  upload: (files: File[], root?: string) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    if (root) fd.append("root", root);
    return json<TreeCreated>(`${BASE}/trees`, { method: "POST", body: fd });
  },

  meta: (id: string) => json<TreeMeta>(`${BASE}/trees/${id}/meta`),
  origins: (id: string) => json<OriginsSummary>(`${BASE}/trees/${id}/origins`),
  map: (id: string) => json<MapPayload>(`${BASE}/trees/${id}/map`),
  fan: (id: string) => json<FanPayload>(`${BASE}/trees/${id}/fan`),
  deadends: (id: string) => json<DeadendsPayload>(`${BASE}/trees/${id}/deadends`),
  duplicates: (id: string) => json<DuplicatesPayload>(`${BASE}/trees/${id}/duplicates`),
};
