import React, { useCallback } from "react";
import { Handle, Position, NodeProps } from "reactflow";
import Tippy from "@tippyjs/react";
import "tippy.js/dist/tippy.css";
import "tippy.js/themes/light.css";
import { EvidenceNodeData } from "../../types/graph";
import {
  formatPropertyValue,
  getDisplayableProperties,
} from "./utils/graphUtils";
import styled from "styled-components"; // Ensure styled-components is imported
import { getNodeColor } from "../shared/nodeColors";

const TooltipWrapper = styled.div`
  max-width: 480px;
  text-align: left;
  font-size: 13px;
  padding: 8px;
  font-family: sans-serif;
  color: #333;

  h4 {
    margin-top: 0;
    margin-bottom: 8px;
    font-size: 1.1em;
    color: #000;
    border-bottom: 1px solid #eee;
    padding-bottom: 4px;
  }

  .tooltip-section {
    margin-bottom: 8px;
    padding-bottom: 8px;
    &:not(:last-child) {
      border-bottom: 1px dotted #eee;
    }
  }

  .prop-item {
    display: flex;
    margin: 4px 0;
    line-height: 1.4;
  }

  .prop-key {
    font-weight: bold;
    min-width: 100px;
    flex-shrink: 0;
    margin-right: 8px;
    color: #555;
    vertical-align: top;
  }

  .prop-value {
    word-break: break-word;
    a {
      color: #007bff;
      text-decoration: none;
      &:hover {
        text-decoration: underline;
      }
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-all;
      background-color: #f8f8f8;
      padding: 4px 6px;
      border-radius: 3px;
      font-size: 0.95em;
      max-height: 150px;
      overflow-y: auto;
    }
  }

  .node-meta {
    font-size: 0.9em;
    color: #666;
  }

  em.expand-hint {
    display: block;
    margin-top: 10px;
    color: #007bff;
    font-style: italic;
    font-size: 0.9em;
  }
`;

// Styled component for the node wrapper
const NodeWrapper = styled.div<{
  expandable: boolean;
  color: string;
}>`
  background: #fff;
  padding: 0;
  border-radius: 2px;
  border: 1px solid #ddd; /* Base border */
  text-align: center;
  width: 180px;
  height: 90px;
  font-size: 13px;
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition:
    border 0.2s ease,
    box-shadow 0.2s ease;
  cursor: default;

  /* Add dashed border for expandable nodes */
  ${({ expandable }) =>
    expandable &&
    `
    border: 2px dashed #555;
    cursor: pointer;
  `}

  /* Highlight styles applied via class names */
  &.path-highlight {
    border: 2px solid rgba(255, 0, 114, 0.9) !important; /* Override dashed border if highlighted */
    z-index: 2; /* Ensure highlighted nodes are above non-highlighted */
  }
  &.path-start-end {
    border: 2px solid rgba(0, 114, 255, 0.9) !important; /* Override dashed/highlight border */
    z-index: 3; /* Ensure start/end nodes are highest */
  }
`;

const NodeHeader = styled.div<{ bgColor: string }>`
  background: ${(e) => e.bgColor};
  padding: 8px 6px;
  font-size: 14px;
  font-weight: bold;
  text-align: center;
  width: 100%;
  border-top-left-radius: 3px;
  border-top-right-radius: 3px;
  flex-shrink: 0;
`;

const NodeContent = styled.div`
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px 10px;
  width: 100%;
  text-align: center;
  word-break: break-word;
  white-space: normal;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  line-height: 1.3;
  box-sizing: border-box;
  min-height: 0; /* Allow content to shrink */
`;

const NodeLabel = styled.div`
  width: 100%;
  text-align: center;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 3; /* Limit label to 3 lines */
  -webkit-box-orient: vertical;
`;

const InfoButton = styled.button<{ bgColor: string }>`
  position: absolute;
  top: 0;
  right: 0;
  width: 22px;
  height: 22px;
  background: ${(e) => e.bgColor};
  color: #333;
  border: none;
  font-size: 12px;
  font-weight: bold;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 10;
  padding: 0;
  margin: 0;
  border-bottom-left-radius: 4px;
  opacity: 0.8;
  transition: opacity 0.2s ease;

  &:hover {
    opacity: 1;
  }
`;

const EvidenceNode: React.FC<NodeProps<EvidenceNodeData>> = ({
  data,
  isConnectable,
  id, // id is available in NodeProps
  selected, // selected is available in NodeProps
  className = "", // className prop is passed by React Flow for styling
}) => {
  const nodeColor = getNodeColor(data.type);

  const renderTooltipContent = useCallback(() => {
    const sourceProps = getDisplayableProperties(data._sourceData);
    const allProps = { ...sourceProps, ...data.properties };

    // Exclude certain properties from the general list
    delete allProps.name;
    delete allProps.label;
    delete allProps.description;
    delete allProps["@id"];
    delete allProps["@type"];
    delete allProps.count;

    return (
      <TooltipWrapper>
        <h4>{data.label || data.displayName || "Node Details"}</h4>{" "}
        {/* Use displayName if label is missing */}
        {/* Essential Node Metadata */}
        <div className="tooltip-section node-meta">
          <div className="prop-item">
            <span className="prop-key">@id:</span>
            {/* Using id from data, which comes from _sourceData["@id"] */}
            <span
              className="prop-value"
              dangerouslySetInnerHTML={{ __html: formatPropertyValue(data.id) }}
            ></span>
          </div>
          <div className="prop-item">
            <span className="prop-key">@type:</span>
            <span className="prop-value">{data.type}</span>
          </div>
          {data.description && (
            <div className="prop-item">
              <span className="prop-key">description:</span>
              <span className="prop-value">{data.description}</span>
            </div>
          )}
          {/* Special display for DatasetCollection item count */}
          {data.type === "DatasetCollection" &&
            data.properties?.count !== undefined && (
              <div className="prop-item">
                <span className="prop-key">Items:</span>
                <span className="prop-value">{data.properties.count}</span>
              </div>
            )}
          {/* Special display for DatasetGroup member count */}
          {data.type === "DatasetGroup" &&
            data.properties?.["evi:memberCount"] !== undefined && (
              <div className="prop-item">
                <span className="prop-key">Members:</span>
                <span className="prop-value">
                  {data.properties["evi:memberCount"]}
                </span>
              </div>
            )}
        </div>
        {/* Display other properties if any exist */}
        {Object.entries(allProps).length > 0 && (
          <div className="tooltip-section">
            {Object.entries(allProps).map(([key, value]) => (
              <div key={key} className="prop-item">
                <span className="prop-key">{key}:</span>
                <span
                  className="prop-value"
                  dangerouslySetInnerHTML={{
                    __html: formatPropertyValue(value),
                  }}
                ></span>
              </div>
            ))}
          </div>
        )}
        {/* Expansion/Selection Hints */}
        {data.expandable && (
          <em className="expand-hint">
            (Click node center to expand{" "}
            {data.type === "DatasetCollection" || data.type === "DatasetGroup"
              ? "next item"
              : "details"}
            )
            <br />
            (Shift+Click to select for path)
          </em>
        )}
        {!data.expandable && ( // Show hint even if not expandable
          <em className="expand-hint">(Shift+Click to select for path)</em>
        )}
      </TooltipWrapper>
    );
  }, [data]); // Dependency on data ensures tooltip updates if data changes

  const handleIconClick = (e: React.MouseEvent) => {
    // Prevent the click event on the 'i' button from propagating to the node wrapper
    // This ensures clicking 'i' doesn't trigger node expansion/selection.
    e.stopPropagation();
  };

  return (
    // NodeWrapper accepts className prop which React Flow passes
    <NodeWrapper
      expandable={!!data.expandable} // Convert to boolean
      color={nodeColor}
      className={className} // Apply the className provided by React Flow (includes highlight classes)
    >
      {/* Target Handle (for incoming edges) */}
      <Handle
        type="target"
        position={Position.Left}
        isConnectable={isConnectable}
        style={{ background: "#555", zIndex: 1 }} // Ensure handle is above wrapper content
      />

      {/* Node Header (Type) */}
      <NodeHeader bgColor={nodeColor}>{data.type}</NodeHeader>

      {/* Node Content (Display Name) */}
      <NodeContent>
        {/* Use title for full text on hover if truncated */}
        <NodeLabel title={data.displayName || data.label}>
          {data.displayName || data.label || id}
        </NodeLabel>{" "}
        {/* Fallback to id if displayName/label missing */}
      </NodeContent>

      {/* Tippy for Tooltip */}
      <Tippy
        content={renderTooltipContent()}
        theme="light" // Use the light theme defined in CSS
        interactive={true} // Allow interaction within the tooltip (e.g., copying text)
        placement="right-start" // Position tooltip
        trigger="mouseenter focus click" // Show on hover, focus, or click
        appendTo={() => document.body} // Append tooltip to body to avoid clipping issues
        maxWidth={500}
        delay={[150, 0]} // Delay showing, no delay hiding
      >
        {/* Info Button */}
        <InfoButton
          onClick={handleIconClick}
          aria-label={`Details for ${data.displayName || data.label || id}`}
          bgColor={nodeColor} // Use node color for button background
        >
          i
        </InfoButton>
      </Tippy>

      {/* Source Handle (for outgoing edges) */}
      <Handle
        type="source"
        position={Position.Right}
        isConnectable={isConnectable}
        style={{ background: "#555", zIndex: 1 }} // Ensure handle is above wrapper content
      />
    </NodeWrapper>
  );
};

export default React.memo(EvidenceNode);
