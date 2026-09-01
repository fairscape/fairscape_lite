// src/styles/GlobalStyles.ts
import { createGlobalStyle } from "styled-components";
import { ThemeType } from "./theme";

export const GlobalStyle = createGlobalStyle<{ theme: ThemeType }>`
  *, *::before, *::after {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  html, body {
    height: 100%;
  }

  body {
    font-family: ${({ theme }) => theme.fonts.main};
    line-height: 1.6;
    color: ${({ theme }) => theme.colors.text};
    background-color: ${({ theme }) => theme.colors.background};
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    display: flex;
    flex-direction: column;
  }

  #root {
    display: flex;
    flex-direction: column;
    min-height: 100vh;
    width: 100%;
  }

  main {
    flex: 1 0 auto; // Makes main content area grow and shrink
    width: 100%;
    max-width: 1280px; // Max width for content
    margin: 0 auto;
    padding: ${({ theme }) => theme.spacing.lg};

    @media (max-width: 768px) {
      padding: ${({ theme }) => theme.spacing.md};
    }
  }

  a {
    color: ${({ theme }) => theme.colors.primary};
    text-decoration: none;
    transition: color 0.2s ease-in-out;

    &:hover {
      color: ${({ theme }) => theme.colors.primaryDark};
      text-decoration: underline;
    }
  }

  h1, h2, h3, h4, h5, h6 {
    color: ${({ theme }) => theme.colors.ink};
    font-weight: 650;
    letter-spacing: -0.02em;
    margin-bottom: ${({ theme }) => theme.spacing.md};
    line-height: 1.3;
  }

  h1 { font-size: 2.2rem; font-weight: 700; letter-spacing: -0.03em; }
  h2 { font-size: 1.8rem; font-weight: 700; }
  h3 { font-size: 1.5rem; }
  h4 { font-size: 1.2rem; }

  p {
    margin-bottom: ${({ theme }) => theme.spacing.md};
  }

  code, pre, kbd, samp {
    font-family: ${({ theme }) => theme.fonts.mono};
  }

  button {
    cursor: pointer;
    padding: ${({ theme }) => theme.spacing.sm} ${({ theme }) =>
      theme.spacing.md};
    border-radius: ${({ theme }) => theme.borderRadius.md};
    border: 1px solid transparent;
    font-family: inherit;
    font-size: 1rem;
    transition: background-color 0.2s ease, border-color 0.2s ease;

    &:disabled {
      cursor: not-allowed;
      opacity: 0.7;
    }
  }

  // Basic button styling (can be overridden by styled-components)
  button.primary {
    background-color: ${({ theme }) => theme.colors.primary};
    color: white;
    &:hover:not(:disabled) {
      background-color: ${({ theme }) => theme.colors.primaryDark};
    }
  }

   button.secondary {
    background-color: ${({ theme }) => theme.colors.surface};
    color: ${({ theme }) => theme.colors.primary};
    border: 1px solid ${({ theme }) => theme.colors.borderStrong};
    &:hover:not(:disabled) {
      background-color: ${({ theme }) => theme.colors.primaryTint};
    }
  }

  // Add styles for the Evidence Graph nodes/links if needed globally
  .reactflow-wrapper {
    width: 100%;
    height: 600px;
    border: 1px solid ${({ theme }) => theme.colors.border};
    border-radius: ${({ theme }) => theme.borderRadius.md};
    background-color: ${({ theme }) => theme.colors.surface};
  }

  .evidence-graph-node circle {
      // Base styles - specific colors set in component
      stroke-width: 2px;
  }

  .evidence-graph-link {
      stroke: ${({ theme }) => theme.colors.textSecondary};
      stroke-opacity: 0.8;
      stroke-width: 1.5px;
  }

`;
