import {
  Badge,
  Card,
  createTheme,
  type CSSVariablesResolver,
  Menu,
  Modal,
  Paper,
  Table,
  Tooltip,
  type MantineColorsTuple,
} from "@mantine/core";

/**
 * Dark neutrals: page #0f1115 (set as --app-bg), surfaces #161a20 (dark[7], used by Paper/Card/popovers),
 * inputs dark[6], borders dark[4]. Text dark[0]; dimmed dark[2] (~7:1 on surfaces).
 */
const dark: MantineColorsTuple = [
  "#e8eaef",
  "#c4c9d2",
  "#9ba3b0",
  "#6c7380",
  "#2c323c",
  "#232831",
  "#1c2028",
  "#161a20",
  "#111419",
  "#0b0d10",
];

export const theme = createTheme({
  primaryColor: "indigo",
  primaryShade: { light: 6, dark: 5 },
  colors: { dark },
  defaultRadius: "md",
  fontFamily: "'Inter Variable', Inter, ui-sans-serif, system-ui, -apple-system, 'Segoe UI', sans-serif",
  fontFamilyMonospace: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
  headings: { fontFamily: "'Inter Variable', Inter, ui-sans-serif, system-ui, sans-serif", fontWeight: "650" },
  cursorType: "pointer",
  focusRing: "auto",
  shadows: {
    xs: "0 1px 2px rgba(16, 24, 40, 0.05)",
    sm: "0 1px 3px rgba(16, 24, 40, 0.08), 0 1px 2px rgba(16, 24, 40, 0.04)",
    md: "0 6px 16px -4px rgba(16, 24, 40, 0.12), 0 2px 6px -2px rgba(16, 24, 40, 0.06)",
  },
  components: {
    Badge: Badge.extend({
      defaultProps: { variant: "light", radius: "sm" },
      styles: { root: { textTransform: "none", fontWeight: 600, letterSpacing: 0 } },
    }),
    Card: Card.extend({ defaultProps: { withBorder: true, radius: "md", shadow: "xs" } }),
    Paper: Paper.extend({ defaultProps: { radius: "md" } }),
    Table: Table.extend({ defaultProps: { verticalSpacing: "sm", highlightOnHover: true } }),
    Tooltip: Tooltip.extend({ defaultProps: { openDelay: 300, withArrow: true } }),
    Menu: Menu.extend({ defaultProps: { shadow: "md", radius: "md", withinPortal: true } }),
    Modal: Modal.extend({ defaultProps: { radius: "md", overlayProps: { backgroundOpacity: 0.45, blur: 2 } } }),
  },
});

export const cssVariablesResolver: CSSVariablesResolver = () => ({
  variables: {},
  light: {
    "--app-bg": "#f6f7f9",
    "--app-surface": "#ffffff",
    "--app-subtle": "#f1f3f5",
    // gray[6] is only ~3.3:1 on white; this keeps secondary text at ~6:1 (WCAG AA)
    "--mantine-color-dimmed": "#5f6672",
    "--mantine-color-default-border": "#e3e6ea",
  },
  dark: {
    "--app-bg": "#0f1115",
    "--app-surface": "#161a20",
    "--app-subtle": "#1c2028",
    "--mantine-color-default-border": "#2c323c",
  },
});
