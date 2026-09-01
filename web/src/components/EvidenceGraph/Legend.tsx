// src/components/EvidenceGraph/Legend.tsx
import React from "react";
import styled from "styled-components";

const LegendContainer = styled.div`
  font-size: 11px;
  padding: 5px;
  border-radius: 4px;
`;

const LegendItem = styled.div`
  display: flex;
  align-items: center;
  margin-bottom: 4px;
`;

const ColorBox = styled.span<{ bgColor: string }>`
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 3px;
  margin-right: 6px;
  background-color: ${(props) => props.bgColor};
  border: 1px solid rgba(0, 0, 0, 0.2);
`;

const ExpandableIcon = styled.span`
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 3px;
  margin-right: 6px;
  border: 2px dashed #333;
`;

const Legend: React.FC = () => {
  return (
    <LegendContainer>
      <LegendItem>
        <ExpandableIcon />
        Expandable Node
      </LegendItem>
    </LegendContainer>
  );
};

export default Legend;
