export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    credentials: "same-origin",
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return undefined as T;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    let message = data?.detail ?? res.statusText;
    if (Array.isArray(message)) {
      message = message.map((d: { loc?: string[]; msg: string }) => `${d.loc?.slice(1).join(".")}: ${d.msg}`).join("; ");
    }
    throw new ApiError(res.status, message);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  del: (path: string) => request<void>("DELETE", path),
};

export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

// ---------------------------------------------------------------- types

/** User emails must be at the company domain (the backend's ALLOWED_EMAIL_DOMAIN enforces it). */
export const EMAIL_DOMAIN = "pahtama.com";
export const EMAIL_PATTERN = `[^@\\s]+@${EMAIL_DOMAIN.replace(/\./g, "\\.")}`;

export interface User {
  id: number;
  username: string;
  full_name: string; // "" for older accounts: show the username instead

  email: string;
  is_active: boolean;
  is_admin: boolean;
  must_change_password: boolean; // admin-set password: must be replaced before using the portal or any system
  created_at: string;
  last_login_at: string | null;
}

export interface UserDetail extends User {
  role_ids: number[];
  emailed?: boolean; // after creating: whether their sign-in details are being emailed (a mail server is set)
}

export interface SystemAccess {
  application_id: number;
  application_name: string;
  roles: string[];
}

export interface UserListItem extends User {
  access: SystemAccess[];
}

export interface Overview {
  users_total: number;
  users_active: number;
  admins: number;
  systems_total: number;
  sign_ins_24h: number;
  failed_sign_ins_24h: number;
  sso_grants_24h: number;
  denied_24h: number;
  systems: { id: number; name: string; is_active: boolean; role_count: number; member_count: number }[];
}

export interface Role {
  id: number;
  application_id: number;
  name: string;
  description: string;
  permission_ids: number[];
}

export interface Permission {
  id: number;
  application_id: number;
  name: string;
  description: string;
}

export interface Application {
  id: number;
  name: string;
  description: string;
  client_id: string;
  redirect_uris: string[];
  web_origins: string[];
  home_url: string;
  is_active: boolean;
  is_confidential: boolean;
  allow_access_requests: boolean; // listed on the public Request access page
  created_at: string;
  roles: Role[];
  permissions: Permission[];
  member_count: number;
}

export interface ApplicationWithSecret extends Application {
  client_secret: string | null;
}

export interface Member {
  user_id: number;
  username: string;
  full_name: string;
  email: string;
  is_active: boolean;
  roles: string[];
}

export interface MyApplication {
  id: number;
  name: string;
  description: string;
  home_url: string;
  roles: string[];
  permissions: string[];
}

export interface AuditEntry {
  id: number;
  created_at: string;
  actor_username: string | null;
  action: string;
  target: string;
  detail: string;
  ip: string;
}

export interface RequestableSystem {
  id: number;
  name: string;
  client_id: string;
}

export interface AccessRequest {
  id: number;
  email: string;
  application_id: number;
  application_name: string;
  status: "open" | "approved" | "declined";
  created_at: string;
  handled_at: string | null;
  handled_by: string | null;
  reason: string; // why it was declined (emailed to them)
  user_id: number | null; // the account with this email, if there is one
  username: string | null;
  user_active: boolean | null;
  current_roles: string[]; // the account's roles in this system already
  roles: { id: number; name: string }[]; // the system's roles, to choose from when approving
  emailed?: boolean; // after approve/decline: whether the requester is being emailed (a mail server is set)
}

export function parseDate(value: string): Date {
  // API timestamps are UTC without a zone suffix.
  return new Date(value.endsWith("Z") ? value : value + "Z");
}

export function formatDate(value: string | null): string {
  return value ? parseDate(value).toLocaleString() : "—";
}

const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

export function timeAgo(value: string | null): string {
  if (!value) return "Never";
  const seconds = (parseDate(value).getTime() - Date.now()) / 1000;
  const abs = Math.abs(seconds);
  if (abs < 45) return "Just now";
  if (abs < 3600) return rtf.format(Math.round(seconds / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(seconds / 3600), "hour");
  if (abs < 86400 * 30) return rtf.format(Math.round(seconds / 86400), "day");
  return parseDate(value).toLocaleDateString();
}

export function generatePassword(length = 14): string {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$%&*";
  const bytes = crypto.getRandomValues(new Uint32Array(length));
  return Array.from(bytes, (b) => chars[b % chars.length]).join("");
}
