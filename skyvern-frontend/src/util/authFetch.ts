import { apiBaseUrl } from "@/util/env";

/**
 * Fetch wrapper that automatically adds the enterprise auth token.
 * Reads the token from localStorage (same key as AuthStore).
 */
const LS_TOKEN = "procurerpa_auth_token";
const API_PREFIX = "/api/v1";

function resolveApiInput(input: RequestInfo | URL): RequestInfo | URL {
  if (typeof input === "string" && input.startsWith(API_PREFIX) && apiBaseUrl) {
    return `${apiBaseUrl.replace(/\/$/, "")}${input.slice(API_PREFIX.length)}`;
  }
  return input;
}

export async function authFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
): Promise<Response> {
  const token = localStorage.getItem(LS_TOKEN);
  const headers = new Headers(init?.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return fetch(resolveApiInput(input), { ...init, headers });
}
