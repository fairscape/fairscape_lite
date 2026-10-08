// The Properties tab: every JSON-LD field, grouped the way the FAIRSCAPE
// RO-Crate model groups them (fairscape_models.rocrate.ROCrateMetadataElem,
// Dataset, Computation), with evi:* roll-up counts as stat tiles up top.
// @id references show the referenced entity's name when the index has it.
import { useState } from "react";
import styled from "styled-components";
import { Link } from "react-router-dom";
import {
  DefList,
  DefRow,
  DefTerm,
  DefValue,
} from "../components/shared/DirectionA";
import { viewPath } from "../links";
import { Labels } from "../api";

// contentUrl -> download href, for local files this server can serve.
type FileLinks = Record<string, string>;

interface Ctx {
  labels: Labels;
  fileLinks?: FileLinks;
}

// ---- styles ----------------------------------------------------------------

const RefLink = styled(Link)`
  color: ${({ theme }) => theme.colors.primary};
  text-decoration: none;

  &:hover {
    text-decoration: underline;
  }
`;

const RawRef = styled(RefLink)`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 12.5px;
  word-break: break-all;
`;

const ExternalLink = styled.a`
  color: ${({ theme }) => theme.colors.primary};
  text-decoration: none;
  word-break: break-word;

  &:hover {
    text-decoration: underline;
  }
`;

const UrlLink = styled(ExternalLink)`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 12.5px;
  word-break: break-all;
`;

const Muted = styled.span`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 11px;
  color: ${({ theme }) => theme.colors.ink3};
  margin-left: 6px;
`;

const JsonBlock = styled.pre`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 12px;
  line-height: 1.55;
  background: ${({ theme }) => theme.colors.background};
  border: 1px solid ${({ theme }) => theme.colors.border};
  border-radius: ${({ theme }) => theme.borderRadius.sm};
  padding: 10px 12px;
  overflow-x: auto;
  max-width: 100%;
  margin: 0;
`;

const ValueStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
`;

const Inline = styled.div`
  line-height: 1.75;
`;

const Chips = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
`;

const Chip = styled.span`
  font-size: 12.5px;
  padding: 2px 9px;
  border: 1px solid ${({ theme }) => theme.colors.border};
  border-radius: 999px;
  background: ${({ theme }) => theme.colors.surface};
  color: ${({ theme }) => theme.colors.ink2};
  white-space: nowrap;
`;

const ShowAll = styled.button`
  align-self: flex-start;
  font-size: 12.5px;
  font-weight: 600;
  color: ${({ theme }) => theme.colors.primary};
  background: none;
  border: none;
  padding: 0;
  margin-left: 4px;
  cursor: pointer;

  &:hover {
    text-decoration: underline;
  }
`;

const GroupTitle = styled.h3`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 11.5px;
  font-weight: 500;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: ${({ theme }) => theme.colors.primary};
  margin: 0 0 4px;
  padding-bottom: 8px;
  border-bottom: 1px solid ${({ theme }) => theme.colors.borderStrong};
`;

const Group = styled.section`
  & + & {
    margin-top: 32px;
  }
`;

const StatGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
  margin: 14px 0 16px;
`;

const Stat = styled.div`
  background: ${({ theme }) => theme.colors.surface};
  border: 1px solid ${({ theme }) => theme.colors.border};
  border-radius: ${({ theme }) => theme.borderRadius.sm};
  padding: 14px 16px;
`;

const StatValue = styled.div`
  font-size: 24px;
  font-weight: 650;
  letter-spacing: -0.01em;
  color: ${({ theme }) => theme.colors.ink};
  font-variant-numeric: tabular-nums;
`;

const StatLabel = styled.div`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: ${({ theme }) => theme.colors.ink3};
  margin-top: 4px;
`;

const StatNote = styled.span`
  font-size: 12px;
  font-weight: 500;
  color: ${({ theme }) => theme.colors.ink3};
  margin-left: 6px;
`;

// ---- grouping ---------------------------------------------------------------

// Header fields the page already renders, plus JSON-LD plumbing.
const SKIP = new Set(["@id", "@type", "@context", "name", "description"]);

const set = (...keys: string[]) => new Set(keys.map((k) => k.toLowerCase()));

const GROUPS: { title: string; keys?: Set<string>; test?: (k: string) => boolean }[] = [
  {
    title: "Overview",
    keys: set(
      "version", "datePublished", "dateCreated", "dateModified", "identifier",
      "url", "license", "keywords", "language", "inLanguage",
      "creativeWorkStatus", "about", "additionalType", "conformsTo",
      "correction",
    ),
  },
  {
    title: "People & funding",
    keys: set(
      "author", "creator", "principalInvestigator", "contactEmail",
      "publisher", "funder", "maintainer", "contributor",
      "dataGovernanceCommittee", "wasAttributedTo", "prov:wasAttributedTo",
      "affiliation", "email", "runBy",
    ),
  },
  {
    title: "Data & files",
    keys: set(
      "contentUrl", "contentSize", "format", "fileFormat", "encodingFormat",
      "md5", "sha256", "hash", "schema", "dataSchema", "evi:Schema",
      "hasSummaryStatistics", "rowCount", "columnCount", "sampleSize",
      "splits", "distribution", "additionalProperty", "properties",
      "required", "separator", "header",
    ),
  },
  {
    title: "Provenance",
    keys: set(
      "generatedBy", "derivedFrom", "generated", "usedBy", "inputs",
      "outputs", "command", "parameter", "startTime", "endTime",
      "dateExecuted", "additionalDocumentation", "datasetUsedBy",
      "softwareUsedBy", "derivedTo", "annotatedBy",
    ),
    test: (k) => /^(prov:|used)/i.test(k) || /(generated|derived)/i.test(k),
  },
  {
    title: "Citation & access",
    keys: set(
      "citation", "associatedPublication", "conditionsOfAccess",
      "copyrightNotice", "usageInfo", "prohibitedUses",
      "confidentialityLevel",
    ),
  },
  {
    title: "Responsible AI",
    keys: set("completeness"),
    test: (k) => k.startsWith("rai:"),
  },
  {
    title: "Ethics & human subjects",
    keys: set(
      "ethicalReview", "irb", "irbProtocolId", "humanSubjectExemption",
      "humanSubjectResearch", "fdaRegulated", "deidentified",
    ),
    test: (k) => k.startsWith("d4d:"),
  },
  { title: "Structure", keys: set("hasPart", "isPartOf") },
];

const groupOf = (key: string) => {
  const lower = key.toLowerCase();
  const i = GROUPS.findIndex((g) => g.keys?.has(lower) || g.test?.(key));
  return i === -1 ? GROUPS.length : i; // GROUPS.length = "Other"
};

const PEOPLE_GROUP = 1;

/** "rai:dataCollectionMissingData" -> "Data collection missing data". */
const humanize = (key: string) => {
  const bare = key.replace(/^[A-Za-z0-9]+:/, "");
  const words = bare
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")
    .replace(/_/g, " ")
    .toLowerCase();
  return words.charAt(0).toUpperCase() + words.slice(1);
};

// ---- values -----------------------------------------------------------------

const isRef = (v: unknown): v is { "@id": string } =>
  typeof v === "object" &&
  v !== null &&
  typeof (v as any)["@id"] === "string" &&
  Object.keys(v as object).length === 1;

const isUrl = (s: string) => /^https?:\/\//.test(s);
const isEmail = (s: string) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(s);

const Ref = ({ id, ctx }: { id: string; ctx: Ctx }) => {
  const label = ctx.labels[id];
  if (!label?.name) return <RawRef to={viewPath(id)}>{id}</RawRef>;
  // People and organisations with a URL id (ORCID, ROR): the name links out.
  if ((label.type === "Person" || label.type === "Organization") && isUrl(id))
    return (
      <ExternalLink href={id} target="_blank" rel="noreferrer" title={id}>
        {label.name}
      </ExternalLink>
    );
  return (
    <RefLink to={viewPath(id)} title={id}>
      {label.name}
    </RefLink>
  );
};

const Value = ({ value, field, ctx }: { value: any; field: string; ctx: Ctx }) => {
  if (value === null || value === undefined || value === "") return <>—</>;
  if (isRef(value)) return <Ref id={value["@id"]} ctx={ctx} />;
  if (typeof value === "string") {
    const href = field === "contentUrl" ? ctx.fileLinks?.[value] : undefined;
    if (href)
      return (
        <UrlLink href={href} download>
          {value} ↓
        </UrlLink>
      );
    if (isUrl(value))
      return (
        <UrlLink href={value} target="_blank" rel="noreferrer">
          {value}
        </UrlLink>
      );
    if (isEmail(value))
      return <ExternalLink href={`mailto:${value}`}>{value}</ExternalLink>;
    return <>{value}</>;
  }
  if (typeof value === "number") return <>{value.toLocaleString()}</>;
  if (typeof value === "boolean") return <>{value ? "Yes" : "No"}</>;
  if (typeof value === "object" && !Array.isArray(value)) {
    // PropertyValue {name, value}, or an inline Person / Organization.
    if (typeof value.name === "string" && "value" in value)
      return (
        <>
          {value.name}: <Value value={value.value} field="" ctx={ctx} />
        </>
      );
    if (typeof value.name === "string") {
      const type = Array.isArray(value["@type"]) ? value["@type"][0] : value["@type"];
      const id = value["@id"] ?? value.identifier;
      return (
        <>
          {typeof id === "string" && isUrl(id) ? (
            <ExternalLink href={id} target="_blank" rel="noreferrer">
              {value.name}
            </ExternalLink>
          ) : (
            value.name
          )}
          {type && <Muted>{String(type)}</Muted>}
        </>
      );
    }
  }
  return <JsonBlock>{JSON.stringify(value, null, 2)}</JsonBlock>;
};

const isShortScalar = (v: any) =>
  typeof v === "number" ||
  (typeof v === "string" && v.length <= 48 && !isUrl(v));

/** People: one wrapped line, semicolon-separated, collapsed past 30. */
const InlineList = ({ items, field, ctx }: { items: any[]; field: string; ctx: Ctx }) => {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? items : items.slice(0, 30);
  return (
    <Inline>
      {shown.map((item, i) => (
        <span key={i}>
          {i > 0 && "; "}
          <Value value={item} field={field} ctx={ctx} />
        </span>
      ))}
      {items.length > shown.length && (
        <ShowAll onClick={() => setExpanded(true)}>
          + {items.length - shown.length} more
        </ShowAll>
      )}
    </Inline>
  );
};

const StackList = ({ items, field, ctx }: { items: any[]; field: string; ctx: Ctx }) => {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? items : items.slice(0, 12);
  return (
    <ValueStack>
      {shown.map((item, i) => (
        <span key={i} style={{ minWidth: 0 }}>
          <Value value={item} field={field} ctx={ctx} />
        </span>
      ))}
      {items.length > shown.length && (
        <ShowAll onClick={() => setExpanded(true)} style={{ marginLeft: 0 }}>
          Show all {items.length.toLocaleString()}
        </ShowAll>
      )}
    </ValueStack>
  );
};

const FieldValue = ({ field, value, ctx }: { field: string; value: any; ctx: Ctx }) => {
  if (!Array.isArray(value)) return <Value value={value} field={field} ctx={ctx} />;
  if (value.length === 0) return <>—</>;
  if (value.length <= 80 && value.every(isShortScalar))
    return (
      <Chips>
        {value.map((v, i) => (
          <Chip key={i}>{typeof v === "number" ? v.toLocaleString() : v}</Chip>
        ))}
      </Chips>
    );
  if (groupOf(field) === PEOPLE_GROUP)
    return <InlineList items={value} field={field} ctx={ctx} />;
  return <StackList items={value} field={field} ctx={ctx} />;
};

// ---- evi:* roll-up counts ----------------------------------------------------

const formatBytes = (n: number) => {
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  let i = 0;
  while (n >= 1000 && i < units.length - 1) {
    n /= 1000;
    i++;
  }
  return `${n.toLocaleString(undefined, { maximumFractionDigits: n < 10 ? 1 : 0 })} ${units[i]}`;
};

const STAT_ORDER: [string, string][] = [
  ["evi:totalContentSizeBytes", "Total size"],
  ["evi:datasetCount", "Datasets"],
  ["evi:computationCount", "Computations"],
  ["evi:softwareCount", "Software"],
  ["evi:schemaCount", "Schemas"],
  ["evi:totalEntities", "Datasets + software"],
  ["evi:entitiesWithChecksums", "With checksums"],
  ["evi:entitiesWithSummaryStats", "With summary stats"],
];

/** ".tsv", "TSV" and "tsv" are one format; keep the first spelling seen. */
const distinctFormats = (formats: string[]) => {
  const seen = new Map<string, string>();
  formats.forEach((f) => {
    const key = f.replace(/^\./, "").toLowerCase();
    if (!seen.has(key)) seen.set(key, f.replace(/^\./, ""));
  });
  return [...seen.values()];
};

const Summary = ({ meta }: { meta: Record<string, any> }) => {
  const known = new Map(STAT_ORDER);
  const keys = [
    ...STAT_ORDER.map(([k]) => k).filter((k) => typeof meta[k] === "number"),
    ...Object.keys(meta).filter(
      (k) => k.startsWith("evi:") && !known.has(k) && typeof meta[k] === "number",
    ),
  ];
  const formats: string[] = Array.isArray(meta["evi:formats"])
    ? distinctFormats(meta["evi:formats"].map(String))
    : [];
  const total = meta["evi:totalEntities"];
  return (
    <Group>
      <GroupTitle>Summary</GroupTitle>
      <StatGrid>
        {keys.map((k) => {
          const v = meta[k] as number;
          const pct =
            k === "evi:entitiesWithChecksums" && typeof total === "number" && total > 0
              ? Math.round((100 * v) / total)
              : null;
          return (
            <Stat key={k} title={k}>
              <StatValue>
                {k === "evi:totalContentSizeBytes" ? formatBytes(v) : v.toLocaleString()}
                {pct !== null && <StatNote>{pct}%</StatNote>}
              </StatValue>
              <StatLabel>{known.get(k) ?? humanize(k)}</StatLabel>
            </Stat>
          );
        })}
      </StatGrid>
      {formats.length > 0 && (
        <DefList>
          <DefRow>
            <DefTerm>Formats</DefTerm>
            <DefValue>
              <Chips>
                {formats.map((f) => (
                  <Chip key={f}>{f}</Chip>
                ))}
              </Chips>
            </DefValue>
          </DefRow>
        </DefList>
      )}
    </Group>
  );
};

// ---- the view ---------------------------------------------------------------

const MetadataView = ({
  metadata,
  fileLinks,
  labels = {},
}: {
  metadata: Record<string, any>;
  fileLinks?: FileLinks;
  labels?: Labels;
}) => {
  const ctx: Ctx = { labels, fileLinks };
  const entries = Object.entries(metadata).filter(
    ([k]) => !SKIP.has(k) && !k.startsWith("evi:"),
  );
  const hasSummary = Object.keys(metadata).some((k) => k.startsWith("evi:"));
  if (!entries.length && !hasSummary)
    return <p style={{ color: "#51626B" }}>No further metadata fields.</p>;

  const grouped = new Map<number, [string, any][]>();
  entries.forEach(([k, v]) => {
    const g = groupOf(k);
    grouped.set(g, [...(grouped.get(g) ?? []), [k, v]]);
  });
  const order = [...grouped.keys()].sort((a, b) => a - b);

  return (
    <div>
      {hasSummary && <Summary meta={metadata} />}
      {order.map((g) => (
        <Group key={g}>
          <GroupTitle>{g < GROUPS.length ? GROUPS[g].title : "Other"}</GroupTitle>
          <DefList>
            {grouped.get(g)!.map(([key, value]) => (
              <DefRow key={key}>
                <DefTerm title={key}>{humanize(key)}</DefTerm>
                <DefValue>
                  <FieldValue field={key} value={value} ctx={ctx} />
                </DefValue>
              </DefRow>
            ))}
          </DefList>
        </Group>
      ))}
    </div>
  );
};

export default MetadataView;
