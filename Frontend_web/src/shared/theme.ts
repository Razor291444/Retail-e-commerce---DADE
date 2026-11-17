export const theme = {
  accent: "#2563EB",
  ink: "#1A1D23",
  muted: "#6B7280",
  line: "#E2E4E9",
  bg: "#F7F6F3",
  externalBg: "#EDEBE6",
  card: "#FFFFFF",
  sidebar: "#12151C",
  sidebarActive: "#1C2230",
  sidebarTextActive: "#7FA6FF",
  status: {
    ok: "#16A34A",
    warn: "#B45309",
    bad: "#B91C1C",
    info: "#1D4ED8",
    grey: "#374151",
  },
  nutriScore: { A: "#038141", B: "#85BB2F", C: "#FECB02", D: "#EE8100", E: "#E63E11" },
  fontSans: "'IBM Plex Sans', system-ui, -apple-system, sans-serif",
  fontHeading: "'Space Grotesk', sans-serif",
  fontMono: "'IBM Plex Mono', ui-monospace, monospace",
} as const;

export function formatEuros(cents: number | null | undefined): string {
  return new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" }).format((cents ?? 0) / 100);
}

export function formatDate(value: string | Date): string {
  return new Intl.DateTimeFormat("fr-FR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value));
}
