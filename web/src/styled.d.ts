import "styled-components";
import { ThemeType } from "./styles/theme";

// Derived from the theme object so the two can't drift apart.
// (Types are erased at build time, so this file could not be recovered from the
// shipped bundle - it is reconstructed to match the recovered theme.)
declare module "styled-components" {
  export interface DefaultTheme extends ThemeType {
    // Referenced by a few components behind `?.` / `||` fallbacks but absent
    // from the shipped theme object - these were undefined in production too.
    shadows?: { subtle?: string; medium?: string; strong?: string };
    colors: ThemeType["colors"] & {
      lightGrey?: string;
      successLight?: string;
    };
    spacing: ThemeType["spacing"] & { xxs?: string };
  }
}
