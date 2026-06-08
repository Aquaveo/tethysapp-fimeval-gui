// Brand color tokens used across React inline styles.
// (The CSS-variable equivalents live in src/styles/theme.css for global stylesheet use;
//  this module is the source of truth for TSX inline-style references.)
export const COLORS = {
  brand:        '#25C2DF',  // FIMbench primary cyan
  brandHover:   '#1da8c4',  // darker cyan for hover states
  ink:          '#152428',  // dark ink / text on light bg
  inkLight:     '#D1EFF6',  // pale cyan / text on dark bg
  taglineGreen: '#1b4332',  // dark green used for header tagline
} as const;
