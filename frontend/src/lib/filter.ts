import type { Party } from "./types";
import { deburr } from "./data";

export type StatusFilter = "active" | "defunct" | "all";

export interface PartyFilter {
  q: string;
  status: StatusFilter;
  city?: string;
  hasMobile: boolean;
  hasPhone: boolean;
  hasEmail: boolean;
  hasWeb: boolean;
  onlyFull: boolean;
}

export const EMPTY_FILTER: PartyFilter = {
  q: "",
  status: "active",
  city: undefined,
  hasMobile: false,
  hasPhone: false,
  hasEmail: false,
  hasWeb: false,
  onlyFull: false,
};

export function isFullContact(p: Party): boolean {
  return (
    !!p.phone &&
    !!p.email &&
    !!p.address &&
    !!(p.website || p.fb_url || p.ig_url)
  );
}

export function hasWebPresence(p: Party): boolean {
  return !!(p.website || p.fb_url || p.ig_url || p.x_url);
}

export function applyFilter(parties: Party[], f: PartyFilter): Party[] {
  const q = deburr(f.q.trim());
  return parties.filter((p) => {
    if (f.status === "active" && p.status !== "AKTIVAN") return false;
    if (f.status === "defunct" && p.status !== "PRESTANAK") return false;
    if (f.city && p.city !== f.city) return false;
    if (f.hasMobile && p.phone_kind !== "mobile") return false;
    if (f.hasPhone && !p.phone) return false;
    if (f.hasEmail && !p.email) return false;
    if (f.hasWeb && !hasWebPresence(p)) return false;
    if (f.onlyFull && !isFullContact(p)) return false;
    if (q) {
      const hay = deburr(
        `${p.canonical_name} ${p.short_name || ""} ${p.city || ""} ${p.county || ""} ${p.president || ""}`,
      );
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

export function readFilterFromSearchParams(sp: URLSearchParams): PartyFilter {
  const bool = (v: string | null) => v === "1" || v === "true";
  const st = sp.get("status");
  return {
    q: sp.get("q") || "",
    status: st === "defunct" || st === "all" ? st : "active",
    city: sp.get("grad") || undefined,
    hasMobile: bool(sp.get("mob")),
    hasPhone: bool(sp.get("tel")),
    hasEmail: bool(sp.get("em")),
    hasWeb: bool(sp.get("web")),
    onlyFull: bool(sp.get("full")),
  };
}

export function writeFilterToSearchParams(f: PartyFilter): URLSearchParams {
  const sp = new URLSearchParams();
  if (f.q) sp.set("q", f.q);
  if (f.status !== "active") sp.set("status", f.status);
  if (f.city) sp.set("grad", f.city);
  if (f.hasMobile) sp.set("mob", "1");
  if (f.hasPhone) sp.set("tel", "1");
  if (f.hasEmail) sp.set("em", "1");
  if (f.hasWeb) sp.set("web", "1");
  if (f.onlyFull) sp.set("full", "1");
  return sp;
}
