import React, { useState, useMemo, ReactNode } from "react";
import styled from "styled-components";
import { Link } from "react-router-dom";
import { GraphDataService } from "./hooks/GraphDataService";
import { RawGraphEntity } from "../../types/graph";
import { findRootEntity } from "./utils/findRootEntity";

const Container = styled.div`
  margin-top: ${({ theme }) => theme.spacing.lg};
  width: 100%;
`;

const SectionTitle = styled.h3`
  font-size: 18px;
  color: ${({ theme }) => theme.colors.ink};
  font-weight: 650;
  letter-spacing: -0.015em;
  margin-top: 0;
  margin-bottom: ${({ theme }) => theme.spacing.sm};
`;

const SearchInputContainer = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.md};
`;

const SearchInput = styled.input`
  width: 100%;
  padding: ${({ theme }) => theme.spacing.sm};
  border: 1px solid ${({ theme }) => theme.colors.border};
  border-radius: ${({ theme }) => theme.borderRadius.md};
  font-size: 0.9rem;
  box-sizing: border-box;

  &:focus {
    outline: none;
    border-color: ${({ theme }) => theme.colors.primary};
  }
`;

const CollapsibleSection = styled.div`
  margin-bottom: ${({ theme }) => theme.spacing.sm};
  border: 1px solid ${({ theme }) => theme.colors.border};
  border-radius: ${({ theme }) => theme.borderRadius.md};
  overflow: hidden;
`;

const SectionHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: ${({ theme }) => theme.spacing.sm} ${({ theme }) => theme.spacing.md};
  background-color: ${({ theme }) => theme.colors.background};
  border-top: 2px solid ${({ theme }) => theme.colors.ink};
  border-bottom: 1px solid ${({ theme }) => theme.colors.border};
  color: ${({ theme }) => theme.colors.ink};
  font-weight: 600;
  cursor: pointer;
  font-size: 0.9rem;
`;

const SectionContent = styled.div<{ isOpen: boolean }>`
  max-height: ${({ isOpen }) => (isOpen ? "2000px" : "0")};
  overflow: hidden;
  transition: max-height 0.3s ease-in-out;
  background-color: ${({ theme }) => theme.colors.surface};
`;

const Table = styled.table`
  width: 100%;
  border-collapse: collapse;
  min-width: 700px;
`;

const TableHead = styled.thead`
  background-color: ${({ theme }) => theme.colors.background};
  border-top: 2px solid ${({ theme }) => theme.colors.ink};
  border-bottom: 1px solid ${({ theme }) => theme.colors.border};
`;

const TableHeaderCell = styled.th`
  padding: 9px ${({ theme }) => theme.spacing.sm};
  text-align: left;
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 10.5px;
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: ${({ theme }) => theme.colors.ink3};
`;

const TableRow = styled.tr`
  border-bottom: 1px solid ${({ theme }) => theme.colors.border};
  &:hover {
    background-color: ${({ theme }) => theme.colors.backgroundHover};
  }
`;

const TableCell = styled.td`
  padding: ${({ theme }) => theme.spacing.sm};
  border-bottom: 1px solid ${({ theme }) => theme.colors.border};
  vertical-align: middle;
  font-size: 0.9rem;
`;

const DescriptionCell = styled(TableCell)`
  max-width: 400px;
  line-height: 1.4;
  vertical-align: top;
`;

const StyledLink = styled(Link)`
  color: ${({ theme }) => theme.colors.primary};
  text-decoration: none;
  &:hover {
    text-decoration: underline;
  }
`;

const NoDataMessage = styled.p`
  color: ${({ theme }) => theme.colors.textSecondary};
  font-style: italic;
  text-align: center;
  padding: ${({ theme }) => theme.spacing.md};
`;

const RelationshipButton = styled.button`
  background-color: ${({ theme }) => theme.colors.surface};
  color: ${({ theme }) => theme.colors.primary};
  border: 1px solid ${({ theme }) => theme.colors.borderStrong};
  padding: 4px 8px;
  border-radius: 2px;
  cursor: pointer;
  font-size: 0.8rem;
  margin-left: 8px;

  &:hover {
    background-color: ${({ theme }) => theme.colors.primaryDark};
  }
  &:disabled {
    background-color: ${({ theme }) => theme.colors.textSecondary};
    cursor: not-allowed;
  }
`;

const HighlightSpan = styled.span`
  background-color: yellow;
  font-weight: bold;
  color: black;
`;

interface SupportingElementsComponentProps {
  dataService: GraphDataService | null;
  onShowRelationshipPath: (pathNodeIds: string[] | null) => void;
}

const escapeRegExp = (s: string): string =>
  s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const getHighlightedText = (text: string, highlight: string): ReactNode[] => {
  if (!text) return [text];
  if (!highlight.trim()) return [text];
  const escaped = escapeRegExp(highlight);
  const parts = text.split(new RegExp(`(${escaped})`, "gi"));
  return parts.map((part, i) =>
    part.toLowerCase() === highlight.toLowerCase() ? (
      <HighlightSpan key={`${part}-${i}`}>{part}</HighlightSpan>
    ) : (
      part
    ),
  );
};

const extractArkIdentifier = (url: string) => {
  const match = url.match(/(ark:.+)/);
  return match ? match[1] : url;
};

const getEntityType = (typeUri: string | string[] | undefined): string => {
  if (!typeUri) return "Unknown";
  const typeString = Array.isArray(typeUri)
    ? typeUri[typeUri.length - 1]
    : typeUri;
  return typeString.split(/[#\/]/).pop() || "Unknown";
};

interface TraverseParams {
  node: RawGraphEntity;
  results: SupportData;
  seenIds: Set<string>;
}

const traverseAndCollect = ({
  node,
  results,
  seenIds,
}: TraverseParams): void => {
  if (
    !node ||
    typeof node !== "object" ||
    !node["@id"] ||
    seenIds.has(node["@id"])
  ) {
    return;
  }
  seenIds.add(node["@id"]);
  let nodeTypes: string[] =
    typeof node["@type"] === "string"
      ? [node["@type"]]
      : Array.isArray(node["@type"])
        ? node["@type"]
        : ["Unknown"];
  const outputElement: SupportingElement = {
    "@id": node["@id"],
    name: node.name || "N/A",
    description: node.description || "",
    "@type": node["@type"] || "Unknown",
  };

  if (
    nodeTypes.some((t) => t.includes("Dataset")) &&
    !results.datasets.some((el) => el["@id"] === node["@id"])
  )
    results.datasets.push(outputElement);
  else if (
    nodeTypes.some((t) => t.includes("Software")) &&
    !results.software.some((el) => el["@id"] === node["@id"])
  )
    results.software.push(outputElement);
  else if (
    nodeTypes.some((t) => t.includes("Computation")) &&
    !results.computations.some((el) => el["@id"] === node["@id"])
  )
    results.computations.push(outputElement);
  else if (
    nodeTypes.some((t) => t.includes("Sample")) &&
    !results.samples.some((el) => el["@id"] === node["@id"])
  )
    results.samples.push(outputElement);
  else if (
    nodeTypes.some((t) => t.includes("Experiment")) &&
    !results.experiments.some((el) => el["@id"] === node["@id"])
  )
    results.experiments.push(outputElement);
  else if (
    nodeTypes.some((t) => t.includes("Instrument")) &&
    !results.instruments.some((el) => el["@id"] === node["@id"])
  )
    results.instruments.push(outputElement);

  const relationshipKeys = [
    "generatedBy",
    "usedDataset",
    "usedSoftware",
    "usedSample",
    "usedInstrument",
    "hasPart",
  ];
  for (const key of relationshipKeys) {
    const relatedItems = node[key];
    if (!relatedItems) continue;
    const itemsToProcess: any[] = Array.isArray(relatedItems)
      ? relatedItems
      : [relatedItems];
    for (const item of itemsToProcess) {
      if (item && typeof item === "object" && item["@id"]) {
        traverseAndCollect({ node: item as RawGraphEntity, results, seenIds });
      }
    }
  }
};

export const extractSupportData = (
  graphData: RawGraphData | null,
): SupportData | null => {
  if (!graphData || !graphData["@graph"]) {
    return null;
  }
  const results: SupportData = {
    datasets: [],
    software: [],
    computations: [],
    samples: [],
    experiments: [],
    instruments: [],
  };
  const seenIds = new Set<string>();
  const graphEntities = graphData["@graph"];

  if (Array.isArray(graphEntities)) {
    const rootEntity = findRootEntity(graphEntities);
    if (rootEntity) {
      traverseAndCollect({ node: rootEntity, results, seenIds });
    } else {
      graphEntities.forEach((entity) =>
        traverseAndCollect({ node: entity, results, seenIds }),
      );
    }
  } else if (typeof graphEntities === "object" && graphEntities !== null) {
    traverseAndCollect({
      node: graphEntities as RawGraphEntity,
      results,
      seenIds,
    });
  } else {
    return null;
  }
  const hasData = Object.values(results).some((arr) => arr.length > 0);
  return hasData ? results : null;
};

const SupportingElementsComponent: React.FC<
  SupportingElementsComponentProps
> = ({ dataService, onShowRelationshipPath }) => {
  if (!dataService) {
    return (
      <Container>
        <SectionTitle>Supporting Elements</SectionTitle>
        <NoDataMessage>Graph data not loaded yet.</NoDataMessage>
      </Container>
    );
  }

  const [expandedSections, setExpandedSections] = useState<{
    [key: string]: boolean;
  }>({
    datasets: false,
    software: false,
    computations: false,
    samples: false,
    experiments: false,
    instruments: false,
  });

  const [searchTerm, setSearchTerm] = useState("");

  const supportData = useMemo(() => {
    const allNodes = dataService.getAllNodes();

    const categorizedNodes: {
      datasets: RawGraphEntity[];
      software: RawGraphEntity[];
      computations: RawGraphEntity[];
      samples: RawGraphEntity[];
      experiments: RawGraphEntity[];
      instruments: RawGraphEntity[];
    } = {
      datasets: [],
      software: [],
      computations: [],
      samples: [],
      experiments: [],
      instruments: [],
    };

    allNodes.forEach((node) => {
      const type = getEntityType(node["@type"]);
      switch (type) {
        case "Dataset":
          categorizedNodes.datasets.push(node);
          break;
        case "Software":
          categorizedNodes.software.push(node);
          break;
        case "Computation":
          categorizedNodes.computations.push(node);
          break;
        case "Sample":
          categorizedNodes.samples.push(node);
          break;
        case "Experiment":
          categorizedNodes.experiments.push(node);
          break;
        case "Instrument":
          categorizedNodes.instruments.push(node);
          break;
      }
    });

    return categorizedNodes;
  }, [dataService]);

  const filteredSupportData = useMemo(() => {
    if (!searchTerm.trim()) return supportData;

    const q = searchTerm.toLowerCase();
    const result = {
      datasets: [] as RawGraphEntity[],
      software: [] as RawGraphEntity[],
      computations: [] as RawGraphEntity[],
      samples: [] as RawGraphEntity[],
      experiments: [] as RawGraphEntity[],
      instruments: [] as RawGraphEntity[],
    };

    (Object.keys(supportData) as Array<keyof typeof supportData>).forEach(
      (key) => {
        result[key] = supportData[key].filter(
          (el) =>
            (el.name && el.name.toLowerCase().includes(q)) ||
            (el.description && el.description.toLowerCase().includes(q)),
        );
      },
    );

    return result;
  }, [supportData, searchTerm]);

  const toggleSection = (section: string) => {
    setExpandedSections((prev) => ({ ...prev, [section]: !prev[section] }));
  };

  const showRelationship = (elementId: string) => {
    const path = dataService.findPathFromAnyOutput(elementId);
    if (path && path.length > 0) onShowRelationshipPath(path);
    else {
      console.warn(`No path found from outputs to ${elementId}`);
      onShowRelationshipPath(null);
    }
  };

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) =>
    setSearchTerm(e.target.value);

  const hasAnyElements = Object.values(supportData).some(
    (arr) => arr.length > 0,
  );
  if (!hasAnyElements) {
    return (
      <Container>
        <SectionTitle>Supporting Elements</SectionTitle>
        <NoDataMessage>
          No supporting elements found for this graph.
        </NoDataMessage>
      </Container>
    );
  }

  const hasFilteredElements = Object.values(filteredSupportData).some(
    (arr) => arr.length > 0,
  );
  const outputIds = dataService.getOutputNodes().map((n) => n["@id"]);

  return (
    <Container>
      <SectionTitle>Supporting Elements</SectionTitle>

      <SearchInputContainer>
        <SearchInput
          type="text"
          placeholder="Search elements by name or description..."
          value={searchTerm}
          onChange={handleSearchChange}
        />
      </SearchInputContainer>

      {!hasFilteredElements && searchTerm.trim() ? (
        <NoDataMessage>
          No supporting elements match your search criteria.
        </NoDataMessage>
      ) : (
        Object.entries(filteredSupportData).map(([sectionKey, elements]) => {
          if (elements.length === 0) return null;

          return (
            <CollapsibleSection key={sectionKey}>
              <SectionHeader onClick={() => toggleSection(sectionKey)}>
                <span>
                  {sectionKey.charAt(0).toUpperCase() + sectionKey.slice(1)} (
                  {elements.length})
                </span>
                <span>{expandedSections[sectionKey] ? "▲" : "▼"}</span>
              </SectionHeader>
              <SectionContent isOpen={!!expandedSections[sectionKey]}>
                <div style={{ overflowX: "auto" }}>
                  <Table>
                    <TableHead>
                      <tr>
                        <TableHeaderCell>Name</TableHeaderCell>
                        <TableHeaderCell>Description</TableHeaderCell>
                        <TableHeaderCell>Actions</TableHeaderCell>
                      </tr>
                    </TableHead>
                    <tbody>
                      {elements.map((el) => {
                        const isOutput = outputIds.includes(el["@id"]);
                        return (
                          <TableRow key={el["@id"]}>
                            <TableCell>
                              <StyledLink
                                to={`/view/${extractArkIdentifier(el["@id"])}`}
                              >
                                {getHighlightedText(
                                  el.name || el["@id"],
                                  searchTerm,
                                )}
                              </StyledLink>
                              {isOutput && " (Output)"}
                            </TableCell>
                            <DescriptionCell>
                              {getHighlightedText(
                                el.description || "No description provided.",
                                searchTerm,
                              )}
                            </DescriptionCell>
                            <TableCell>
                              <RelationshipButton
                                onClick={() => showRelationship(el["@id"])}
                                disabled={isOutput}
                                title={
                                  isOutput
                                    ? "This node is already an output"
                                    : "Show path from an output to this node"
                                }
                              >
                                {isOutput ? "Is Output" : "Show Relationship"}
                              </RelationshipButton>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </tbody>
                  </Table>
                </div>
              </SectionContent>
            </CollapsibleSection>
          );
        })
      )}
    </Container>
  );
};

export default SupportingElementsComponent;
