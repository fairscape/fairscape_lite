import React, { useEffect, useState, useCallback, useRef } from "react";
import styled from "styled-components";
import ReactFlow, {
  Controls,
  Background,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  ReactFlowProvider,
  useReactFlow,
  Node,
  Edge,
  OnNodesChange,
  OnEdgesChange,
  NodeChange,
  EdgeChange,
} from "reactflow";
import "reactflow/dist/style.css";

import { RawGraphData, EvidenceNode, EvidenceEdge } from "../../types/graph";
import { GraphDataService } from "./hooks/GraphDataService";
import { GraphBuilder } from "./utils/graphUtils";
import { getLayoutedElements } from "./utils/layoutUtils";
import Legend from "./Legend";
import EvidenceNodeComponent from "./EvidenceNode";
import LoadingSpinner from "../common/LoadingSpinner";
import SupportingElementsComponent from "./SupportingElementsComponent";

const Container = styled.div`
  width: 100%;
`;
const ViewerWrapper = styled.div`
  width: 100%;
  height: 550px;
  position: relative;
  border: 1px solid ${({ theme }) => theme.colors.border};
  border-radius: ${({ theme }) => theme.borderRadius.md};
  background-color: ${({ theme }) => theme.colors.surface};
  margin-bottom: ${({ theme }) => theme.spacing.lg};
  .react-flow__edge {
    path {
      transition:
        stroke 0.2s ease,
        stroke-width 0.2s ease;
    }
    &.path-highlight {
      z-index: 1;
      path {
        stroke: #ff0072;
        stroke-width: 2.5;
      }
    }
  }
`;
const LoadingOverlay = styled.div`
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
`;
const LegendWrapper = styled.div`
  position: absolute;
  top: 8px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 10px;
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid ${({ theme }) => theme.colors.border};
  border-radius: 2px;
  pointer-events: none;
  user-select: none;

  .hint-label {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    color: #888;
  }
  svg {
    display: block;
  }
`;
const SelectionIndicator = styled.div`
  position: absolute;
  top: 10px;
  left: 10px;
  background: rgba(0, 114, 255, 0.1);
  color: #0056b3;
  padding: 5px 10px;
  border-radius: 2px;
  font-size: 12px;
  z-index: 5;
  border: 1px solid rgba(0, 114, 255, 0.3);
`;

const nodeTypes = { evidenceNode: EvidenceNodeComponent };
type RFNode = Node<EvidenceNode["data"]>;
type RFEdge = Edge<EvidenceEdge>;

interface GraphRendererProps {
  dataService: GraphDataService | null;
  targetPath: string[] | null;
}

const GraphRenderer: React.FC<GraphRendererProps> = ({
  dataService,
  targetPath,
}) => {
  const [nodes, setNodes, onNodesChangeInternal] = useNodesState<
    RFNode["data"]
  >([]);
  const [edges, setEdges, onEdgesChangeInternal] = useEdgesState<RFEdge>([]);
  const [isLoading, setIsLoading] = useState(false);
  const { fitView } = useReactFlow();
  const graphBuilderRef = useRef<GraphBuilder | null>(null);
  const [pathSelectionStart, setPathSelectionStart] = useState<string | null>(
    null,
  );
  const [highlightedPath, setHighlightedPath] = useState<{
    nodes: string[];
    edges: string[];
  }>({ nodes: [], edges: [] });

  const clearHighlighting = useCallback(() => {
    setHighlightedPath({ nodes: [], edges: [] });
    setPathSelectionStart(null);
  }, []);

  const applyLayout = useCallback(
    (
      elements: { nodes: EvidenceNode[]; edges: EvidenceEdge[] },
      fit = false,
    ) => {
      setIsLoading(true);
      setTimeout(() => {
        try {
          const { nodes: layoutedNodes, edges: layoutedEdges } =
            getLayoutedElements(
              elements.nodes as Node[],
              elements.edges as Edge[],
              "LR",
            );
          setNodes(layoutedNodes as RFNode[]);
          setEdges(layoutedEdges as RFEdge[]);
          if (fit)
            setTimeout(() => {
              fitView({ padding: 0.15, duration: 300 });
            }, 100);
        } catch (e) {
          console.error("Layout failed:", e);
          setNodes(elements.nodes as RFNode[]);
          setEdges(elements.edges as RFEdge[]);
        } finally {
          setIsLoading(false);
        }
      }, 10);
    },
    [setNodes, setEdges, fitView],
  );

  useEffect(() => {
    if (!dataService) {
      setNodes([]);
      setEdges([]);
      return;
    }
    graphBuilderRef.current = new GraphBuilder(dataService);

    if (targetPath && targetPath.length) {
      const elements = graphBuilderRef.current.buildPathGraph(targetPath);
      setHighlightedPath({
        nodes: targetPath,
        edges: elements.edges
          .filter(
            (e) =>
              targetPath.includes(e.source) && targetPath.includes(e.target),
          )
          .map((e) => e.id),
      });
      applyLayout(elements, true);
    } else {
      const elements = graphBuilderRef.current.buildInitialGraph(2);
      clearHighlighting();
      applyLayout(elements, true);
    }
  }, [dataService, targetPath, applyLayout, clearHighlighting]);

  const onNodeClick = useCallback(
    (event: React.MouseEvent, node: RFNode) => {
      if (!dataService || !graphBuilderRef.current) return;

      if (event.shiftKey) {
        event.preventDefault();
        event.stopPropagation();
        if (!pathSelectionStart) {
          setPathSelectionStart(node.id);
          setHighlightedPath({ nodes: [node.id], edges: [] });
        } else if (pathSelectionStart === node.id) {
          clearHighlighting();
        } else {
          const path = dataService.findPath(pathSelectionStart, node.id);
          if (path) {
            const pathElements = graphBuilderRef.current.buildPathGraph(path);
            setHighlightedPath({
              nodes: path,
              edges: pathElements.edges
                .filter(
                  (e) => path.includes(e.source) && path.includes(e.target),
                )
                .map((e) => e.id),
            });
            applyLayout(pathElements, false);
          } else {
            console.warn(
              `No path found between ${pathSelectionStart} and ${node.id}`,
            );
            clearHighlighting();
          }
          setPathSelectionStart(null);
        }
        return;
      }

      if (pathSelectionStart) {
        clearHighlighting();
        event.stopPropagation();
        return;
      }
      if (!node.data.expandable) {
        event.stopPropagation();
        return;
      }

      setIsLoading(true);
      setTimeout(() => {
        if (graphBuilderRef.current) {
          const elements = graphBuilderRef.current.expandNode(node.id);
          applyLayout(elements, false);
        }
        event.stopPropagation();
      }, 10);
    },
    [dataService, applyLayout, clearHighlighting, pathSelectionStart],
  );

  const handleNodesChange: OnNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const relevant = changes.filter(
        (c) => !isLoading || (c.type === "position" && c.dragging === true),
      );
      if (relevant.length) onNodesChangeInternal(relevant);
    },
    [isLoading, onNodesChangeInternal],
  );

  const handleEdgesChange: OnEdgesChange = useCallback(
    (changes: EdgeChange[]) => onEdgesChangeInternal(changes),
    [onEdgesChangeInternal],
  );

  const styledNodes = nodes.map((node) => {
    const isPathNode = highlightedPath.nodes.includes(node.id);
    const isStartNode = isPathNode && node.id === highlightedPath.nodes[0];
    const isEndNode =
      isPathNode &&
      node.id === highlightedPath.nodes[highlightedPath.nodes.length - 1] &&
      highlightedPath.nodes.length > 1;
    let cls = "";
    if (isPathNode) cls += "path-highlight ";
    if (isStartNode) cls += "path-start ";
    if (isEndNode) cls += "path-end ";
    if (node.id === pathSelectionStart) cls += "path-selection-start ";
    return { ...node, className: cls.trim() };
  });

  const styledEdges = edges.map((edge) => {
    const isPathEdge = highlightedPath.edges.includes(edge.id);
    const typeClass = `edge-${edge.label?.replace(/\s+/g, "-")}`;
    const classes = [typeClass];
    if (isPathEdge) classes.push("path-highlight");
    return { ...edge, className: classes.join(" ") };
  });

  return (
    <ViewerWrapper>
      {isLoading && (
        <LoadingOverlay>
          <LoadingSpinner />
        </LoadingOverlay>
      )}
      {pathSelectionStart && (
        <SelectionIndicator>
          Selecting path from: {pathSelectionStart}. Shift+click another node to
          complete.
        </SelectionIndicator>
      )}
      <ReactFlow
        nodes={styledNodes}
        edges={styledEdges}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        onPaneClick={() => {
          if (pathSelectionStart || highlightedPath.nodes.length)
            clearHighlighting();
        }}
        nodesDraggable={!isLoading}
        nodesConnectable={false}
        minZoom={0.1}
        maxZoom={4}
        fitView={false}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={15}
          size={0.5}
          color="#ccc"
        />
        <Controls />
        <LegendWrapper>
          <Legend />
        </LegendWrapper>
      </ReactFlow>
    </ViewerWrapper>
  );
};

interface EvidenceGraphViewerProps {
  evidenceGraphData: RawGraphData | null;
  supportData?: any;
}

const EvidenceGraphViewer: React.FC<EvidenceGraphViewerProps> = ({
  evidenceGraphData,
  supportData,
}) => {
  const [dataService, setDataService] = useState<GraphDataService | null>(null);
  const [pathToVisualize, setPathToVisualize] = useState<string[] | null>(null);

  useEffect(() => {
    if (evidenceGraphData) {
      setDataService(new GraphDataService(evidenceGraphData));
    } else {
      setDataService(null);
      setPathToVisualize(null);
    }
  }, [evidenceGraphData]);

  if (!evidenceGraphData) {
    return (
      <div
        style={{
          height: 320,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          border: "1px solid var(--border, #ddd)",
          borderRadius: 6,
          background: "white",
        }}
      >
        <LoadingSpinner />
        <p style={{ marginTop: 10, color: "#666" }}>
          Building evidence graph...
        </p>
      </div>
    );
  }

  return (
    <Container>
      <ReactFlowProvider>
        <GraphRenderer dataService={dataService} targetPath={pathToVisualize} />
      </ReactFlowProvider>
      <SupportingElementsComponent
        dataService={dataService}
        supportData={supportData}
        onShowRelationshipPath={setPathToVisualize}
      />
    </Container>
  );
};

export default EvidenceGraphViewer;
