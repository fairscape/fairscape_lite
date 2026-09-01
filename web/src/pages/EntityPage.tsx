import { useEffect, useMemo, useState } from "react";
import styled from "styled-components";
import { Link, useParams, useSearchParams } from "react-router-dom";
import {
  ArkId,
  Mono,
  SectionHeader,
  Table,
  Th,
  Tr,
  Td,
  TdMono,
  TypeTag,
} from "../components/shared/DirectionA";
import LoadingSpinner from "../components/common/LoadingSpinner";
import EvidenceGraphViewer from "../components/EvidenceGraph/EvidenceGraphViewer";
import { PageBody } from "../components/Layout";
import MetadataView from "./MetadataView";
import {
  resolve,
  evidenceGraph,
  listEntities,
  Envelope,
  EntitySummary,
} from "../api";
import { RawGraphData } from "../types/graph";

const TitleRow = styled.div`
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;

  h1 {
    margin: 0;
    font-size: 27px;
    font-weight: 700;
    letter-spacing: -0.015em;
    color: ${({ theme }) => theme.colors.ink};
  }
`;

const IdRow = styled.div`
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 18px;
`;

const CrateLink = styled(Link)`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 12.5px;
  color: ${({ theme }) => theme.colors.primary};
  text-decoration: none;
  word-break: break-all;

  &:hover {
    text-decoration: underline;
  }
`;

const Description = styled.p`
  max-width: 900px;
  font-size: 15px;
  line-height: 1.7;
  color: ${({ theme }) => theme.colors.ink2};
  margin-bottom: 32px;
`;

const TabBar = styled.div`
  display: flex;
  gap: 26px;
  border-bottom: 1px solid ${({ theme }) => theme.colors.border};
  margin-bottom: 24px;
`;

const Tab = styled.button<{ $active: boolean }>`
  font-family: ${({ theme }) => theme.fonts.main};
  font-size: 14.5px;
  font-weight: ${({ $active }) => ($active ? 650 : 500)};
  color: ${({ theme, $active }) =>
    $active ? theme.colors.primary : theme.colors.ink2};
  background: none;
  border: none;
  border-bottom: 2px solid
    ${({ theme, $active }) => ($active ? theme.colors.primary : "transparent")};
  margin-bottom: -1px;
  padding: 8px 2px 10px;
  cursor: pointer;

  &:hover {
    color: ${({ theme }) => theme.colors.primary};
  }
`;

const Chips = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 16px;
`;

const Chip = styled.button<{ $active: boolean }>`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 11.5px;
  letter-spacing: 0.05em;
  padding: 4px 10px;
  cursor: pointer;
  border-radius: ${({ theme }) => theme.borderRadius.sm};
  border: 1px solid
    ${({ theme, $active }) =>
      $active ? theme.colors.primary : theme.colors.borderStrong};
  color: ${({ theme, $active }) =>
    $active ? "#fff" : theme.colors.ink2};
  background: ${({ theme, $active }) =>
    $active ? theme.colors.primary : theme.colors.surface};
`;

const NameLink = styled(Link)`
  font-weight: 600;
  font-size: 13.5px;
  color: ${({ theme }) => theme.colors.primary};
  text-decoration: none;

  &:hover {
    text-decoration: underline;
  }
`;

const JsonBlock = styled.pre`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 12px;
  line-height: 1.55;
  background: ${({ theme }) => theme.colors.background};
  border: 1px solid ${({ theme }) => theme.colors.border};
  border-radius: ${({ theme }) => theme.borderRadius.sm};
  padding: 14px 16px;
  overflow-x: auto;
`;

const ErrorNote = styled.p`
  color: ${({ theme }) => theme.colors.danger};
  font-size: 14px;
  padding: 24px 0;
`;

const TABS = ["metadata", "graph", "raw"] as const;
type TabKey = (typeof TABS)[number];
const TAB_LABELS: Record<TabKey, string> = {
  metadata: "Metadata",
  graph: "Evidence Graph",
  raw: "Raw JSON",
};

/** "https://w3id.org/EVI#ROCrate" -> "ROCrate"; dedupe, keep order. */
const typeTags = (type: string | string[] | undefined): string[] => {
  const list = Array.isArray(type) ? type : type ? [type] : [];
  const seen = new Set<string>();
  return list
    .map((t) => String(t).split(/[#/]/).pop() ?? "")
    .filter((t) => t && !seen.has(t.toLowerCase()) && seen.add(t.toLowerCase()));
};

const ContentsSection = ({ crateId }: { crateId: string }) => {
  const [entities, setEntities] = useState<EntitySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string | null>(null);

  useEffect(() => {
    listEntities({ crate: crateId })
      .then(setEntities)
      .catch((e) => setError(e.message));
  }, [crateId]);

  const types = useMemo(() => {
    const counts = new Map<string, number>();
    (entities ?? []).forEach((e) =>
      counts.set(e.type, (counts.get(e.type) ?? 0) + 1),
    );
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [entities]);

  if (error) return <ErrorNote>Could not load contents: {error}</ErrorNote>;
  if (entities === null) return <LoadingSpinner />;
  if (!entities.length) return null;

  const shown = filter ? entities.filter((e) => e.type === filter) : entities;

  return (
    <div style={{ marginTop: 40 }}>
      <SectionHeader title="Contents" />
      <Chips>
        <Chip $active={filter === null} onClick={() => setFilter(null)}>
          ALL ({entities.length})
        </Chip>
        {types.map(([type, count]) => (
          <Chip
            key={type}
            $active={filter === type}
            onClick={() => setFilter(filter === type ? null : type)}
          >
            {type.toUpperCase()} ({count})
          </Chip>
        ))}
      </Chips>
      <Table>
        <thead>
          <tr>
            <Th style={{ width: "40%" }}>Name</Th>
            <Th>Type</Th>
            <Th style={{ width: "40%" }}>Identifier</Th>
          </tr>
        </thead>
        <tbody>
          {shown.map((e) => (
            <Tr key={e.id}>
              <Td>
                <NameLink to={`/view/${e.id}`}>{e.name ?? e.id}</NameLink>
              </Td>
              <Td>
                <TdMono>{e.type}</TdMono>
              </Td>
              <Td>
                <TdMono>{e.id}</TdMono>
              </Td>
            </Tr>
          ))}
        </tbody>
      </Table>
    </div>
  );
};

const EntityPage = () => {
  const id = decodeURI(useParams()["*"] ?? "");
  const [params, setParams] = useSearchParams();
  const tab: TabKey = (TABS as readonly string[]).includes(
    params.get("tab") ?? "",
  )
    ? (params.get("tab") as TabKey)
    : "metadata";

  const [envelope, setEnvelope] = useState<Envelope | null>(null);
  const [graphData, setGraphData] = useState<RawGraphData | null>(null);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setEnvelope(null);
    setGraphData(null);
    setGraphError(null);
    setError(null);
    if (!id) return;
    resolve(id)
      .then(setEnvelope)
      .catch((e) => setError(e.message));
  }, [id]);

  useEffect(() => {
    if (tab !== "graph" || graphData || graphError || !id) return;
    evidenceGraph(id)
      .then((env) => setGraphData(env.metadata as RawGraphData))
      .catch((e) => setGraphError(e.message));
  }, [tab, id, graphData, graphError]);

  if (error)
    return (
      <PageBody>
        <ErrorNote>
          Could not resolve <Mono>{id}</Mono>: {error}
        </ErrorNote>
      </PageBody>
    );
  if (!envelope)
    return (
      <PageBody>
        <LoadingSpinner />
      </PageBody>
    );

  const meta = envelope.metadata;
  const tags = typeTags(envelope["@type"]);
  const isCrate = tags.some((t) => t.toLowerCase() === "rocrate");
  const fromCrate =
    envelope.sourceCrate && envelope.sourceCrate !== envelope["@id"]
      ? envelope.sourceCrate
      : null;

  return (
    <PageBody>
      <TitleRow>
        <h1>{meta.name ?? envelope["@id"]}</h1>
        {tags.map((t) => (
          <TypeTag key={t}>{t}</TypeTag>
        ))}
      </TitleRow>
      <IdRow>
        <ArkId>{envelope["@id"]}</ArkId>
        {fromCrate && (
          <span>
            <Mono>from crate </Mono>
            <CrateLink to={`/view/${fromCrate}`}>{fromCrate}</CrateLink>
          </span>
        )}
      </IdRow>
      {meta.description && <Description>{meta.description}</Description>}

      <TabBar>
        {TABS.map((key) => (
          <Tab
            key={key}
            $active={tab === key}
            onClick={() =>
              setParams(key === "metadata" ? {} : { tab: key }, {
                replace: true,
              })
            }
          >
            {TAB_LABELS[key]}
          </Tab>
        ))}
      </TabBar>

      {tab === "metadata" && (
        <>
          <SectionHeader title="Properties" />
          <MetadataView metadata={meta} />
          {isCrate && <ContentsSection crateId={envelope["@id"]} />}
        </>
      )}
      {tab === "graph" &&
        (graphError ? (
          <ErrorNote>Could not build evidence graph: {graphError}</ErrorNote>
        ) : (
          <EvidenceGraphViewer evidenceGraphData={graphData} />
        ))}
      {tab === "raw" && (
        <JsonBlock>{JSON.stringify(meta, null, 2)}</JsonBlock>
      )}
    </PageBody>
  );
};

export default EntityPage;
