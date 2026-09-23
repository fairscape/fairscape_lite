import { useEffect, useState } from "react";
import styled from "styled-components";
import { Link } from "react-router-dom";
import {
  Eyebrow,
  GhostButton,
  SectionHeader,
  Table,
  Th,
  Tr,
  Td,
  TdMono,
} from "../components/shared/DirectionA";
import { HeroSection } from "../components/shared/DirectionA";
import LoadingSpinner from "../components/common/LoadingSpinner";
import { PageBody } from "../components/Layout";
import { listCrates, listEntities, CrateSummary } from "../api";

const HeroInner = styled.div`
  max-width: 1280px;
  margin: 0 auto;
  padding: 44px 32px 48px;
`;

const HeroTitle = styled.h1`
  margin: 0 0 14px;
  font-size: 34px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: #fff;
`;

const HeroSub = styled.p`
  margin: 0;
  max-width: 620px;
  font-size: 15px;
  line-height: 1.7;
  color: ${({ theme }) => theme.colors.heroSub};
`;

const NameLink = styled(Link)`
  font-size: 14.5px;
  font-weight: 600;
  color: ${({ theme }) => theme.colors.primary};
  text-decoration: none;

  &:hover {
    text-decoration: underline;
  }
`;

const Blurb = styled.p`
  margin: 4px 0 0;
  font-size: 13px;
  line-height: 1.55;
  color: ${({ theme }) => theme.colors.ink2};
`;

const NumTd = styled(Td)`
  text-align: right;
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 12.5px;
`;

const Empty = styled.p`
  padding: 24px 0;
  color: ${({ theme }) => theme.colors.ink2};
  font-size: 14px;

  code {
    font-family: ${({ theme }) => theme.fonts.mono};
    background: ${({ theme }) => theme.colors.background};
    border: 1px solid ${({ theme }) => theme.colors.border};
    padding: 2px 6px;
  }
`;

const ErrorNote = styled.p`
  padding: 24px 0;
  color: ${({ theme }) => theme.colors.danger};
  font-size: 14px;
`;

const truncate = (text: string | null, n = 160) =>
  text && text.length > n ? `${text.slice(0, n).trimEnd()}…` : text;

interface Row extends CrateSummary {
  name: string | null;
  description: string | null;
}

const DashboardPage = () => {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listCrates(), listEntities({ type: "ROCrate" })])
      .then(([crates, roots]) => {
        const byId = new Map(roots.map((e) => [e.id, e]));
        setRows(
          crates.map((c) => ({
            ...c,
            name: byId.get(c.id)?.name ?? null,
            description: byId.get(c.id)?.description ?? null,
          })),
        );
      })
      .catch((e) => setError(e.message));
  }, []);

  return (
    <>
      <HeroSection>
        <HeroInner>
          <Eyebrow style={{ color: "#5FB3BF" }}>LOCAL METADATA STORE</Eyebrow>
          <HeroTitle>Registered RO-Crates</HeroTitle>
          <HeroSub>
            Crates indexed from this machine. Open one to browse its metadata
            and evidence graph, or search across everything.
          </HeroSub>
        </HeroInner>
      </HeroSection>
      <PageBody>
        <SectionHeader
          index={rows ? String(rows.length).padStart(2, "0") : ""}
          title="Crates"
        />
        {error && <ErrorNote>Could not load crates: {error}</ErrorNote>}
        {!error && rows === null && <LoadingSpinner />}
        {rows !== null && rows.length === 0 && (
          <Empty>
            Nothing registered yet. Index a crate with{" "}
            <code>POST /rocrate {"{"}"path": "…"{"}"}</code>, or upload a zip
            with <code>POST /rocrate/upload</code>, and it will appear here.
          </Empty>
        )}
        {rows !== null && rows.length > 0 && (
          <Table>
            <thead>
              <tr>
                <Th style={{ width: "34%" }}>Name</Th>
                <Th style={{ width: "24%" }}>Identifier</Th>
                <Th style={{ textAlign: "right" }}>Nodes</Th>
                <Th>Registered</Th>
                <Th style={{ width: "24%" }}>Path</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <Tr key={row.id}>
                  <Td>
                    <NameLink to={`/view/${row.id}`}>
                      {row.name ?? row.id}
                    </NameLink>
                    {row.description && (
                      <Blurb>{truncate(row.description)}</Blurb>
                    )}
                  </Td>
                  <Td>
                    <TdMono style={{ fontSize: "12.5px" }}>{row.id}</TdMono>
                  </Td>
                  <NumTd>{row.node_count.toLocaleString()}</NumTd>
                  <Td>
                    <TdMono>{row.ingested_at.slice(0, 10)}</TdMono>
                  </Td>
                  <Td>
                    <TdMono>{row.path}</TdMono>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </PageBody>
    </>
  );
};

export default DashboardPage;
