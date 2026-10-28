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
  ImportPreview,
} from "./types";

const BASE = "/api";

async function json<T>(url: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url, { credentials: "include", ...init });
  } catch {
    throw new Error("Could not connect to this installation. Check that it is running, then try again.");
  }
  if (!res.ok) {
    const expired = res.status === 401 && !url.startsWith(`${BASE}/auth/`) && url !== `${BASE}/health`;
    if (expired) window.dispatchEvent(new Event("kinwhere:unauthorized"));
    let detail = expired ? "Your sign-in has expired. Sign in again to continue." :
      res.statusText || "The request could not be completed. Please try again.";
    try {
      const body = await res.json();
      if (!expired && typeof body.detail === "string") detail = body.detail;
      else if (!expired && Array.isArray(body.detail)) {
        const messages = body.detail.flatMap((issue: { loc?: unknown[]; msg?: unknown }) => {
          if (!issue || typeof issue.msg !== "string") return [];
          const field = Array.isArray(issue.loc) ? issue.loc.filter((part) =>
            typeof part === "string" && part !== "body").join(" · ") : "";
          return [field ? `${field}: ${issue.msg}` : issue.msg];
        });
        if (messages.length) detail = messages.join(". ");
      }
    } catch {
      /* non-JSON error body */
    }
    // Message is the human-readable detail only (no "NNN:" prefix); the numeric
    // status is carried on `err.status` for callers that branch on it (e.g. 401).
    const err = new Error(detail) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  try {
    return (await res.json()) as T;
  } catch {
    throw new Error("Could not read the response from this installation. Please try again.");
  }
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
  preview: (files: File[]) => {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    return json<ImportPreview>(`${BASE}/trees/preview`, { method: "POST", body: fd });
  },
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
