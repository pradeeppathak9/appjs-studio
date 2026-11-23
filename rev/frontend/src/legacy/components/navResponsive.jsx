// Shared responsive behaviour for the dashboard and admin sidebars.
//
// Both layouts style their sidebar with inline styles, which outrank a plain class,
// so every override that has to win on small screens carries !important. The open
// state is forced to a column flex so it works whether or not the inline style
// already declared `display: flex`.
export const RESPONSIVE_NAV_CSS = `
.ar-nav-toggle { display: none; }
@media (max-width: 820px) {
  .ar-nav-toggle { display: inline-flex !important; }
  .ar-layout { flex-direction: column; }
  .ar-sidebar {
    display: none !important;
    width: auto !important;
    border-right: none !important;
    border-bottom: 1px solid #f1f5f9;
    padding: 10px 12px !important;
  }
  .ar-sidebar-open { display: flex !important; flex-direction: column; }
  .ar-content { padding: 20px 16px !important; }
}
`;

export const navToggleStyle = {
  alignItems: "center",
  justifyContent: "center",
  width: 32,
  height: 30,
  padding: 0,
  backgroundColor: "transparent",
  border: "1px solid #e2e8f0",
  borderRadius: 6,
  cursor: "pointer",
  color: "#475569",
  fontSize: 15,
  lineHeight: 1,
};

export function navToggleProps(navOpen, setNavOpen) {
  return {
    className: "ar-nav-toggle",
    onClick: () => setNavOpen((o) => !o),
    "aria-expanded": navOpen,
    "aria-controls": "app-sidebar",
    "aria-label": navOpen ? "Hide navigation" : "Show navigation",
  };
}
