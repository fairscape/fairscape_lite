// One generic property grid instead of the web client's typed MetadataDisplay
// tree: every JSON-LD field gets a row, @id references become links, long
// arrays collapse, nested objects fall back to a JSON block.
import { useState } from "react";
import styled from "styled-components";
import { Link } from "react-router-dom";
import {
  DefList,
  DefRow,
  DefTerm,
  DefValue,
} from "../components/shared/DirectionA";

const RefLink = styled(Link)`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 12.5px;
  color: ${({ theme }) => theme.colors.primary};
  text-decoration: none;
  word-break: break-all;

  &:hover {
    text-decoration: underline;
  }
`;

const ExternalLink = styled.a`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 12.5px;
  color: ${({ theme }) => theme.colors.ink3};
  word-break: break-all;
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
`;

const ValueStack = styled.div`
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
`;

const ShowAll = styled.button`
  align-self: flex-start;
  font-size: 12.5px;
  font-weight: 600;
  color: ${({ theme }) => theme.colors.primary};
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;

  &:hover {
    text-decoration: underline;
  }
`;

// Header fields the page already renders, plus JSON-LD plumbing.
const SKIP = new Set(["@id", "@type", "@context", "name", "description"]);
const COLLAPSE_AT = 12;

const isRef = (v: unknown): v is { "@id": string } =>
  typeof v === "object" &&
  v !== null &&
  typeof (v as any)["@id"] === "string" &&
  Object.keys(v as object).length === 1;

const Value = ({ value }: { value: any }) => {
  if (value === null || value === undefined) return <>—</>;
  if (isRef(value)) {
    const id = value["@id"];
    return <RefLink to={`/view/${id}`}>{id}</RefLink>;
  }
  if (typeof value === "string") {
    if (/^https?:\/\//.test(value))
      return (
        <ExternalLink href={value} target="_blank" rel="noreferrer">
          {value}
        </ExternalLink>
      );
    return <>{value}</>;
  }
  if (typeof value === "number" || typeof value === "boolean")
    return <>{String(value)}</>;
  return <JsonBlock>{JSON.stringify(value, null, 2)}</JsonBlock>;
};

const ArrayValue = ({ items }: { items: any[] }) => {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? items : items.slice(0, COLLAPSE_AT);
  return (
    <ValueStack>
      {shown.map((item, i) => (
        <span key={i} style={{ minWidth: 0 }}>
          <Value value={item} />
        </span>
      ))}
      {items.length > COLLAPSE_AT && !expanded && (
        <ShowAll onClick={() => setExpanded(true)}>
          Show all {items.length}
        </ShowAll>
      )}
    </ValueStack>
  );
};

const MetadataView = ({ metadata }: { metadata: Record<string, any> }) => {
  const entries = Object.entries(metadata).filter(([k]) => !SKIP.has(k));
  if (!entries.length)
    return <p style={{ color: "#51626B" }}>No further metadata fields.</p>;
  return (
    <DefList>
      {entries.map(([key, value]) => (
        <DefRow key={key}>
          <DefTerm>{key}</DefTerm>
          <DefValue>
            {Array.isArray(value) ? (
              <ArrayValue items={value} />
            ) : (
              <Value value={value} />
            )}
          </DefValue>
        </DefRow>
      ))}
    </DefList>
  );
};

export default MetadataView;
