// src/components/shared/DirectionA.tsx
//
// Recovered from ghcr.io/fairscape/fairscapefrontend:RELEASE.2026-08-04.v2
// (assets/DirectionA-Ca9ZUgTj.js). All CSS is verbatim from the shipped build.
// Component names are reconstructed from usage; only SectionHeader, TypeTag,
// Mono, CtaButton and ArkId were still imported by other modules in that build,
// so the rest kept their definitions but had no surviving call sites.
import React from "react";
import styled, { css } from "styled-components";

export const Eyebrow = styled.div`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: ${({ theme }) => theme.colors.ink3};
  margin-bottom: 10px;
`;

const SectionHeaderRow = styled.div`
  border-top: 2px solid ${({ theme }) => theme.colors.ink};
  padding-top: 16px;
  margin-bottom: 20px;
  display: flex;
  align-items: baseline;
  gap: 12px;
`;

const SectionIndex = styled.span`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 12px;
  color: ${({ theme }) => theme.colors.ink3};
`;

const SectionTitle = styled.h2`
  margin: 0;
  font-size: 21px;
  font-weight: 650;
  letter-spacing: -0.015em;
  color: ${({ theme }) => theme.colors.ink};
`;

export const SectionHeader: React.FC<{
  index?: string;
  title: React.ReactNode;
  children?: React.ReactNode;
}> = ({ index, title, children }) => (
  <SectionHeaderRow>
    {index && <SectionIndex>{index}</SectionIndex>}
    <SectionTitle>{title}</SectionTitle>
    {children}
  </SectionHeaderRow>
);

export const MonoLink = styled.span<{ $dim?: boolean }>`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 0.92em;
  color: ${({ theme, $dim }) => ($dim ? theme.colors.ink3 : theme.colors.primary)};
  word-break: break-all;
`;

export const ArkId = styled.span`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 13px;
  color: ${({ theme }) => theme.colors.ink};
  background: ${({ theme }) => theme.colors.background};
  border: 1px solid ${({ theme }) => theme.colors.border};
  border-radius: ${({ theme }) => theme.borderRadius.sm};
  padding: 5px 10px;
  word-break: break-all;
`;

export const TypeTag = styled.span`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: ${({ theme }) => theme.colors.primary};
  border: 1px solid ${({ theme }) => theme.colors.primary};
  border-radius: ${({ theme }) => theme.borderRadius.sm};
  padding: 3px 8px;
  background: ${({ theme }) => theme.colors.primaryTint};
  white-space: nowrap;
`;

export const Mono = styled.span`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 12.5px;
  color: ${({ theme }) => theme.colors.ink3};
`;

const buttonBase = css`
  font-size: 14px;
  font-weight: 600;
  padding: 11px 22px;
  border-radius: 2px;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  line-height: 1.2;
  cursor: pointer;
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease;

  &:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
`;

export const CtaButton = styled.button`
  ${buttonBase}
  background: ${({ theme }) => theme.colors.secondary};
  color: ${({ theme }) => theme.colors.ctaText};
  border: 1px solid ${({ theme }) => theme.colors.secondary};

  &:hover:not(:disabled) {
    background: #d98e00;
    border-color: #d98e00;
  }
`;

export const SecondaryButton = styled.button`
  ${buttonBase}
  font-weight: 550;
  background: ${({ theme }) => theme.colors.surface};
  color: ${({ theme }) => theme.colors.primary};
  border: 1px solid ${({ theme }) => theme.colors.borderStrong};

  &:hover:not(:disabled) {
    background: ${({ theme }) => theme.colors.primaryTint};
  }
`;

export const GhostButton = styled.button`
  ${buttonBase}
  font-weight: 500;
  background: transparent;
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.3);

  &:hover:not(:disabled) {
    border-color: rgba(255, 255, 255, 0.6);
  }
`;

export const DefList = styled.div`
  display: flex;
  flex-direction: column;
`;

export const DefRow = styled.div`
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 24px;
  padding: 13px 0;
  border-bottom: 1px solid ${({ theme }) => theme.colors.border};
  align-items: baseline;

  &:last-child {
    border-bottom: none;
  }

  @media (max-width: 768px) {
    grid-template-columns: 1fr;
    gap: 4px;
  }
`;

export const DefTerm = styled.span`
  font-size: 13px;
  font-weight: 550;
  color: ${({ theme }) => theme.colors.ink3};
`;

export const DefValue = styled.span`
  font-size: 14px;
  line-height: 1.6;
  color: ${({ theme }) => theme.colors.ink};
  word-break: break-word;
`;

export const Table = styled.table`
  width: 100%;
  border-collapse: collapse;

  thead {
    border-top: 2px solid ${({ theme }) => theme.colors.ink};
  }
`;

export const Th = styled.th`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 10.5px;
  font-weight: 500;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: ${({ theme }) => theme.colors.ink3};
  background: ${({ theme }) => theme.colors.background};
  text-align: left;
  padding: 9px 12px;
  border-bottom: 1px solid ${({ theme }) => theme.colors.border};
  position: sticky;
  top: 0;
  z-index: 1;
`;

export const Tr = styled.tr`
  border-bottom: 1px solid ${({ theme }) => theme.colors.border};

  &:hover {
    background: ${({ theme }) => theme.colors.primaryTint};
  }
`;

export const Td = styled.td`
  font-size: 13.5px;
  color: ${({ theme }) => theme.colors.ink};
  text-align: left;
  padding: 11px 12px;
  vertical-align: baseline;
  word-break: break-word;
`;

export const TdMono = styled.span`
  font-family: ${({ theme }) => theme.fonts.mono};
  font-size: 11.5px;
  color: ${({ theme }) => theme.colors.ink3};
`;

export const HeroSection = styled.section`
  background-color: ${({ theme }) => theme.colors.hero};
  background-image: radial-gradient(
    rgba(255, 255, 255, 0.07) 1px,
    transparent 1px
  );
  background-size: 26px 26px;
  color: #fff;
`;
