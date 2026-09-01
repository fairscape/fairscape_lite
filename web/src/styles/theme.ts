// src/styles/theme.ts — recovered VERBATIM from the theme object embedded in
// ghcr.io/fairscape/fairscapefrontend:RELEASE.2026-08-04.v2 (assets/index-g7fEU7Pf.js).
// Values are exact; only key order/formatting is reconstructed.
export const theme = {
  colors: {
    primary: "#005F73",
    primaryLight: "#0A9396",
    primaryDark: "#003844",
    primaryTint: "#EBF2F4",
    secondary: "#EE9B00",
    secondaryLight: "#F8DCB0",
    secondaryDark: "#B27300",
    background: "#F7F9F9",
    backgroundAlt: "#F7F9F9",
    backgroundHover: "#EBF2F4",
    surface: "#ffffff",
    text: "#18242A",
    textSecondary: "#51626B",
    textSlightlyLighter: "#51626B",
    ink: "#18242A",
    ink2: "#51626B",
    ink3: "#84939A",
    border: "#E2E8EA",
    borderLight: "#E2E8EA",
    borderStrong: "#C3CED2",
    hero: "#0A2127",
    heroSub: "#9FB9BF",
    heroAccent: "#5FB3BF",
    ctaText: "#211501",
    footer: "#101B1F",
    error: "#d00000",
    danger: "#d00000",
    success: "#40916c",
    info: "#0077b6",
    warning: "#ffb703",
  },
  fonts: {
    main: "'Inter', system-ui, Avenir, Helvetica, Arial, sans-serif",
    mono: "'IBM Plex Mono', ui-monospace, SFMono-Regular, Menlo, monospace",
  },
  spacing: { xs: "4px", sm: "8px", md: "16px", lg: "24px", xl: "32px" },
  borderRadius: { sm: "2px", md: "2px", lg: "2px" },
};

export type ThemeType = typeof theme;

// NOTE: the built code also references theme.spacing.xxs, theme.colors.lightGrey
// and theme.colors.successLight, which are NOT in the shipped theme object —
// they resolved to undefined at runtime in the released build.
