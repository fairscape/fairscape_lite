import { FormEvent, useEffect, useState } from "react";
import styled from "styled-components";
import { Link, useSearchParams } from "react-router-dom";
import {
  CtaButton,
  SectionHeader,
  TypeTag,
  Mono,
} from "../components/shared/DirectionA";
import LoadingSpinner from "../components/common/LoadingSpinner";
import { PageBody } from "../components/Layout";
import { search, EntitySummary } from "../api";

const SearchForm = styled.form`
  display: flex;
  gap: 12px;
  margin-bottom: 18px;
`;

const SearchInput = styled.input`
  flex: 1;
  font-family: ${({ theme }) => theme.fonts.main};
  font-size: 15px;
  padding: 11px 14px;
  color: ${({ theme }) => theme.colors.ink};
  background: ${({ theme }) => theme.colors.surface};
  border: 1px solid ${({ theme }) => theme.colors.borderStrong};
  border-radius: ${({ theme }) => theme.borderRadius.sm};
  outline: none;

  &:focus {
    border-color: ${({ theme }) => theme.colors.primary};
  }
`;

const Summary = styled.p`
  font-size: 14px;
  color: ${({ theme }) => theme.colors.ink2};
  margin-bottom: 18px;
`;

const ResultCard = styled.div`
  background: ${({ theme }) => theme.colors.surface};
  border: 1px solid ${({ theme }) => theme.colors.border};
  border-radius: ${({ theme }) => theme.borderRadius.md};
  padding: 16px 20px;
  margin-bottom: 12px;
`;

const ResultTitle = styled(Link)`
  font-size: 15.5px;
  font-weight: 650;
  color: ${({ theme }) => theme.colors.primary};
  text-decoration: none;
  margin-right: 10px;

  &:hover {
    text-decoration: underline;
  }
`;

const ResultDescription = styled.p`
  margin: 6px 0;
  font-size: 13.5px;
  line-height: 1.6;
  color: ${({ theme }) => theme.colors.ink2};
`;

const ErrorNote = styled.p`
  color: ${({ theme }) => theme.colors.danger};
  font-size: 14px;
`;

const truncate = (text: string | null, n = 240) =>
  text && text.length > n ? `${text.slice(0, n).trimEnd()}…` : text;

const SearchPage = () => {
  const [params, setParams] = useSearchParams();
  const query = params.get("q") ?? "";
  const [input, setInput] = useState(query);
  const [results, setResults] = useState<EntitySummary[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setInput(query);
    if (!query.trim()) {
      setResults(null);
      return;
    }
    setLoading(true);
    setError(null);
    search(query)
      .then(setResults)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [query]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (input.trim()) setParams({ q: input.trim() });
  };

  return (
    <PageBody style={{ maxWidth: 900 }}>
      <SectionHeader title="Search" />
      <SearchForm onSubmit={submit}>
        <SearchInput
          autoFocus
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Search names, descriptions and keywords…"
        />
        <CtaButton type="submit">Search</CtaButton>
      </SearchForm>
      {error && <ErrorNote>Search failed: {error}</ErrorNote>}
      {loading && <LoadingSpinner />}
      {!loading && results !== null && (
        <>
          <Summary>
            {results.length} result{results.length === 1 ? "" : "s"} for “
            {query}”
          </Summary>
          {results.map((r) => (
            <ResultCard key={r.id}>
              <ResultTitle to={`/view/${r.id}`}>{r.name ?? r.id}</ResultTitle>
              <TypeTag>{r.type}</TypeTag>
              {r.description && (
                <ResultDescription>{truncate(r.description)}</ResultDescription>
              )}
              <Mono>{r.id}</Mono>
            </ResultCard>
          ))}
        </>
      )}
    </PageBody>
  );
};

export default SearchPage;
