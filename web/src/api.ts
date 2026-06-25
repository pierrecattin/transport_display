import type { Config, Meta } from "./types";

const API = "/api";

async function getJson<T>(path: string): Promise<T> {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(`GET ${path} failed: ${r.status}`);
  return (await r.json()) as T;
}

async function errorDetail(r: Response): Promise<string> {
  try {
    const body = (await r.json()) as { detail?: string };
    return body.detail ?? `HTTP ${r.status}`;
  } catch {
    return `HTTP ${r.status}`;
  }
}

export const getConfig = (): Promise<Config> => getJson<Config>("/config");
export const getMeta = (): Promise<Meta> => getJson<Meta>("/meta");
export const getFonts = (): Promise<string[]> => getJson<string[]>("/fonts");

export interface SaveResult {
  ok: boolean;
  restart: { ok: boolean; detail: string };
}

export async function putConfig(cfg: Config): Promise<SaveResult> {
  const r = await fetch(API + "/config", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg),
  });
  if (!r.ok) throw new Error(await errorDetail(r));
  return (await r.json()) as SaveResult;
}

// Returns an object URL for the rendered PNG; caller revokes it.
export async function fetchPreview(cfg: Config, scale = 4): Promise<string> {
  const r = await fetch(`${API}/preview?scale=${scale}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cfg),
  });
  if (!r.ok) throw new Error(await errorDetail(r));
  return URL.createObjectURL(await r.blob());
}
