import React, { ReactNode } from "react";
import { theme } from "./theme";

export function LoadingState({ label = "Chargement en cours…" }: { label?: string }) {
  return <div className="state-panel" aria-live="polite"><div className="spinner" /><span>{label}</span></div>;
}
export function KpiSkeleton() { return <div className="kpi-grid">{[1, 2, 3, 4].map((id) => <div className="skeleton kpi" key={id} />)}</div>; }
export function TableSkeleton({ rows = 5 }: { rows?: number }) { return <div className="table-skeleton">{Array.from({ length: rows }, (_, id) => <div className="skeleton row" key={id} />)}</div>; }
export function ProductGridSkeleton() { return <div className="product-grid">{[1, 2, 3, 4].map((id) => <div className="skeleton product-skeleton" key={id} />)}</div>; }
export function ButtonSpinner() { return <span className="button-spinner" aria-label="Traitement en cours" />; }

export function ErrorState({ status, message, retry }: { status?: number; message?: string; retry?: () => void }) {
  const messages: Record<number, string> = {
    401: "Session expirée : reconnectez-vous pour continuer.",
    403: "Accès refusé (403) : votre rôle RBAC actuel ne permet pas cette action.",
    409: "Conflit métier : stock insuffisant ou produit déjà commandé. Archivez-le plutôt que de le supprimer.",
    422: "Paiement refusé : la Saga a annulé la transaction et libéré la réservation de stock.",
    429: "Trop de requêtes : le débit est limité, veuillez patienter avant de réessayer.",
    503: "Dégradation maîtrisée : Circuit Breaker ouvert. Votre réservation a été libérée, aucun montant n'a été débité.",
  };
  return <div className="error-state" role="alert"><strong>{status ? `${status} — ` : ""}{messages[status || 0] || message || "Une erreur est survenue."}</strong>{retry && <button onClick={retry}>Réessayer</button>}{status === 409 && <button onClick={retry}>Archiver le produit</button>}</div>;
}
export function EmptyState({ title, action, onAction }: { title: string; action: string; onAction?: () => void }) {
  return <div className="empty-state"><span className="empty-icon">∅</span><strong>{title}</strong>{onAction && <button onClick={onAction}>{action}</button>}</div>;
}
export function StatusPill({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const kind = normalized.includes("fail") || normalized.includes("rupture") ? "bad" : normalized.includes("prepar") || normalized.includes("pending") ? "info" : normalized.includes("warn") || normalized.includes("saturation") ? "warn" : normalized.includes("deliver") || normalized.includes("paid") || normalized.includes("nominal") ? "ok" : "grey";
  return <span className={`pill ${kind}`}>{status}</span>;
}
export function NutriScoreBadge({ score }: { score?: string }) { const value = (score || "—").toUpperCase(); return <span className="nutri" style={{ background: theme.nutriScore[value as keyof typeof theme.nutriScore] || theme.muted }}>{value}</span>; }
export function NutritionTable100g() { return <table className="mini-table"><tbody><tr><td>Énergie</td><td>210 kcal / 879 kJ</td></tr><tr><td>Lipides / saturés</td><td>12 g / 4 g</td></tr><tr><td>Glucides / sucres</td><td>18 g / 12 g</td></tr><tr><td>Protéines / sel</td><td>6 g / 0,2 g</td></tr><tr><td>Allergènes</td><td>Voir la fiche Open Food Facts</td></tr></tbody></table>; }
export function TerroirDirectBadge() { return <div className="terroir-details"><span className="terroir-badge">TerroirDirect · Producteur local</span><small>Ferme des Alpes · Isère · récolté le 12/11/2026</small><small>Tarifs caisses : 1 = 2,99 € · 5 = 2,79 € · 10 = 2,49 €</small></div>; }
export function RoleGuard({ roles, role, children, disabled = false }: { roles: string[]; role: string; children: ReactNode; disabled?: boolean }) {
  if (!roles.includes(role)) return disabled ? <span className="disabled-action" title="Accès refusé (403)">{children}</span> : null;
  return <>{children}</>;
}
export function ToastProvider({ children }: { children: ReactNode }) { return <div className="toast-region" aria-live="polite" aria-atomic="true">{children}</div>; }
export function QrCodeModal({ barcode, onClose }: { barcode: string; onClose: () => void }) {
  return <div className="modal-backdrop" role="dialog" aria-modal="true"><div className="modal"><button className="close" onClick={onClose}>×</button><h2>QR Nutrition</h2><div className="qr">{barcode.split("").map((char, id) => <i key={id} style={{ opacity: Number(char) % 2 ? 1 : .25 }} />)}</div><code>{barcode}</code><p>Scannez ce code pour ouvrir la fiche nutritionnelle.</p></div></div>;
}
