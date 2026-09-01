// The whole client for fairscape_lite's HTTP surface (read endpoints only).
// Served from the same origin as the API, so every path is relative; in dev
// the vite proxy forwards these prefixes to uvicorn on :8000.

export interface CrateSummary {
  id: string;
  path: string;
  node_count: number;
  ingested_at: string;
  entities: number;
}

export interface EntitySummary {
  id: string;
  type: string;
  name: string | null;
  description: string | null;
  source_crate: string;
}

/** The resolver envelope: what /ark:..., /identifier and /evidencegraph return. */
export interface Envelope {
  "@id": string;
  "@type": string | string[];
  metadata: Record<string, any>;
  sourceCrate: string | null;
}

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return res.json();
}

export const listCrates = () =>
  get<{ crates: CrateSummary[] }>("/rocrate").then((r) => r.crates);

export const listEntities = (params: {
  crate?: string;
  type?: string;
  limit?: number;
  offset?: number;
}) => {
  const q = new URLSearchParams();
  if (params.crate) q.set("crate", params.crate);
  if (params.type) q.set("type", params.type);
  q.set("limit", String(params.limit ?? 500));
  if (params.offset) q.set("offset", String(params.offset));
  return get<{ entities: EntitySummary[] }>(`/entity?${q}`).then(
    (r) => r.entities,
  );
};

// ARK ids are legal path segments and get the pretty route; a quarter of the
// corpus has URL-form @ids, which only the query-param endpoints can spell.
export const resolve = (id: string) =>
  id.startsWith("ark:")
    ? get<Envelope>(`/${id}`)
    : get<Envelope>(`/identifier?id=${encodeURIComponent(id)}`);

export const evidenceGraph = (id: string) =>
  id.startsWith("ark:")
    ? get<Envelope>(`/evidencegraph/${id}`)
    : get<Envelope>(`/evidencegraph?id=${encodeURIComponent(id)}`);

export const search = (q: string, limit = 100) =>
  get<{ query: string; results: EntitySummary[] }>(
    `/search?q=${encodeURIComponent(q)}&limit=${limit}`,
  ).then((r) => r.results);
