// The whole client for fairscape_lite's HTTP surface (reads, plus crate upload).
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

/** {@id: {name, type}} for indexed entities a node references. */
export type Labels = Record<string, { name: string | null; type: string }>;

/** The resolver envelope: what /ark:..., /identifier and /evidencegraph return. */
export interface Envelope {
  "@id": string;
  "@type": string | string[];
  metadata: Record<string, any>;
  sourceCrate: string | null;
  labels?: Labels;
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

// ---- Crate files: upload a zip, fetch what it unpacked ---------------------

export interface LocalFile {
  "@id": string;
  n: number;
  name: string | null;
  contentUrl: string;
  path: string;
  exists: boolean;
}

export interface SubcrateRef {
  "@id": string;
  name: string | null;
}

export interface Subcrate extends SubcrateRef {
  description: string | null;
  registered: boolean;
  entities: number;
}

export const subcrates = (crateId: string) =>
  get<{ subcrates: Subcrate[] }>(
    `/rocrate/subcrates?id=${encodeURIComponent(crateId)}`,
  ).then((r) => r.subcrates);

export interface UploadResult {
  crate: string;
  kind: "zip" | "metadata";
  subcrates: { declared: number; missing: SubcrateRef[] };
  files: {
    local: number;
    found: number;
    missing: { "@id": string; contentUrl: string }[];
    missing_truncated: boolean;
  };
}

/** Where the browser downloads one entity's n-th local contentUrl. */
export const fileUrl = (id: string, n = 0) =>
  `/rocrate/file?id=${encodeURIComponent(id)}${n ? `&n=${n}` : ""}`;

export const crateFiles = (crateId: string) =>
  get<{ files: LocalFile[] }>(
    `/rocrate/files?id=${encodeURIComponent(crateId)}`,
  ).then((r) => r.files);

/** A refused upload; `missing` is set when sub-crates must go first (409). */
export class UploadError extends Error {
  missing: SubcrateRef[];
  constructor(message: string, missing: SubcrateRef[] = []) {
    super(message);
    this.missing = missing;
  }
}

export async function uploadCrate(
  file: File,
  requireSubcrates = true,
): Promise<UploadResult> {
  const body = new FormData();
  body.append("file", file);
  const res = await fetch(
    `/rocrate/upload?require_subcrates=${requireSubcrates}`,
    { method: "POST", body },
  );
  if (!res.ok) {
    let detail: any = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    if (typeof detail === "object" && detail?.missing)
      throw new UploadError(detail.message, detail.missing);
    throw new UploadError(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}
