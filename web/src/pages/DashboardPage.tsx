import { useCallback, useEffect, useRef, useState } from "react";
import styled from "styled-components";
import { Link } from "react-router-dom";
import {
  Eyebrow,
  SecondaryButton,
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
import {
  listCrates,
  listEntities,
  uploadCrate,
  CrateSummary,
  SubcrateRef,
  UploadError,
  UploadResult,
} from "../api";
import { viewPath } from "../links";

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

const UploadBox = styled.div`
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 14px;
  padding: 16px 18px;
  margin-bottom: 28px;
  border: 1px dashed ${({ theme }) => theme.colors.borderStrong};
  border-radius: ${({ theme }) => theme.borderRadius.sm};
  background: ${({ theme }) => theme.colors.surface};
  font-size: 13.5px;
  color: ${({ theme }) => theme.colors.ink2};
`;

const UploadNote = styled.span<{ $error?: boolean }>`
  color: ${({ theme, $error }) =>
    $error ? theme.colors.danger : theme.colors.ink2};
`;

const MissingList = styled.ul`
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: 13px;
  color: ${({ theme }) => theme.colors.ink2};
`;

const names = (refs: SubcrateRef[]) => refs.map((m) => m.name ?? m["@id"]);

/** Pick a crate zip (or a bare ro-crate-metadata.json) and POST it.
 *
 * A release that lists sub-crates is held back until they are uploaded
 * (the server answers 409 with the missing ones); "Upload anyway" sends
 * it regardless.
 */
const UploadPanel = ({ onUploaded }: { onUploaded: () => void }) => {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [held, setHeld] = useState<{ file: File; missing: SubcrateRef[] } | null>(null);

  const send = (file: File, requireSubcrates = true) => {
    setBusy(true);
    setResult(null);
    setError(null);
    setHeld(null);
    uploadCrate(file, requireSubcrates)
      .then((r) => {
        setResult(r);
        onUploaded();
      })
      .catch((e) => {
        if (e instanceof UploadError && e.missing.length)
          setHeld({ file, missing: e.missing });
        else setError(e.message);
      })
      .finally(() => {
        setBusy(false);
        if (input.current) input.current.value = "";
      });
  };

  return (
    <UploadBox>
      <input
        ref={input}
        type="file"
        accept=".zip,.json,application/zip,application/json"
        style={{ display: "none" }}
        onChange={(e) => e.target.files?.[0] && send(e.target.files[0])}
      />
      <SecondaryButton disabled={busy} onClick={() => input.current?.click()}>
        {busy ? "Uploading…" : "Upload crate"}
      </SecondaryButton>
      {!result && !error && !held && (
        <UploadNote>
          A .zip of the crate folder (ro-crate-metadata.json plus the files it
          points to), or a bare ro-crate-metadata.json.
        </UploadNote>
      )}
      {error && <UploadNote $error>Upload failed: {error}</UploadNote>}
      {held && (
        <div style={{ flexBasis: "100%" }}>
          <UploadNote $error>
            {held.file.name} lists {held.missing.length} sub-crate
            {held.missing.length === 1 ? "" : "s"} that are not uploaded yet.
            Upload them first so they keep their own contents, then upload this
            one last.
          </UploadNote>
          <MissingList>
            {names(held.missing).map((n) => (
              <li key={n}>{n}</li>
            ))}
          </MissingList>
          <SecondaryButton
            style={{ marginTop: 10, padding: "7px 14px", fontSize: 13 }}
            disabled={busy}
            onClick={() => send(held.file, false)}
          >
            Upload anyway
          </SecondaryButton>
        </div>
      )}
      {result && (
        <UploadNote>
          Registered <NameLink to={viewPath(result.crate)}>{result.crate}</NameLink>
          {result.files.local > 0 &&
            ` · ${result.files.found} of ${result.files.local} local files found`}
          {result.subcrates.declared > 0 &&
            ` · ${result.subcrates.declared - result.subcrates.missing.length} of ${result.subcrates.declared} sub-crates present`}
          {result.files.missing.length > 0 &&
            ` (missing: ${result.files.missing
              .slice(0, 3)
              .map((m) => m.contentUrl)
              .join(", ")}${result.files.missing.length > 3 ? ", …" : ""})`}
        </UploadNote>
      )}
    </UploadBox>
  );
};

const truncate = (text: string | null, n = 160) =>
  text && text.length > n ? `${text.slice(0, n).trimEnd()}…` : text;

interface Row extends CrateSummary {
  name: string | null;
  description: string | null;
}

const DashboardPage = () => {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
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

  useEffect(load, [load]);

  return (
    <>
      <HeroSection>
        <HeroInner>
          <Eyebrow style={{ color: "#5FB3BF" }}>LOCAL METADATA STORE</Eyebrow>
          <HeroTitle>Registered RO-Crates</HeroTitle>
          <HeroSub>
            Crates indexed on or uploaded to this server. Open one to browse its metadata
            and evidence graph, or search across everything.
          </HeroSub>
        </HeroInner>
      </HeroSection>
      <PageBody>
        <SectionHeader
          index={rows ? String(rows.length).padStart(2, "0") : ""}
          title="Crates"
        />
        <UploadPanel onUploaded={load} />
        {error && <ErrorNote>Could not load crates: {error}</ErrorNote>}
        {!error && rows === null && <LoadingSpinner />}
        {rows !== null && rows.length === 0 && (
          <Empty>
            Nothing registered yet. Upload a crate above, or index one with{" "}
            <code>POST /rocrate {"{"}"path": "…"{"}"}</code>, and it will
            appear here.
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
                    <NameLink to={viewPath(row.id)}>
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
