import { Link } from "react-router-dom";
import {
  Globe,
  Mail,
  MailOpen,
  MessageCircle,
  Phone,
  type LucideIcon,
} from "lucide-react";
import type { Party } from "@/lib/types";
import { yearOf } from "@/lib/data";
import { hasWebPresence } from "@/lib/filter";
import { PartyAvatar } from "./PartyAvatar";
import { StatusBadge } from "./StatusBadge";

function ContactDots({ p }: { p: Party }) {
  const items: Array<{ ok: boolean; label: string; Icon: LucideIcon }> = [
    { ok: p.phone_kind === "mobile", label: "SMS (mobitel)", Icon: MessageCircle },
    { ok: !!p.phone, label: "Telefon", Icon: Phone },
    { ok: !!p.email, label: "Email", Icon: Mail },
    { ok: !!p.address, label: "Pošta (adresa)", Icon: MailOpen },
    { ok: hasWebPresence(p), label: "Web/društvene", Icon: Globe },
  ];
  return (
    <div className="flex items-center gap-1.5 text-xs">
      {items.map((it) => (
        <span
          key={it.label}
          title={`${it.label}: ${it.ok ? "da" : "ne"}`}
          className={
            "inline-flex items-center justify-center w-5 h-5 rounded-full transition-colors " +
            (it.ok
              ? "bg-emerald-50 text-emerald-700"
              : "bg-surface text-muted/50")
          }
        >
          <it.Icon size={12} strokeWidth={2.2} />
        </span>
      ))}
    </div>
  );
}

export function PartyCard({ party }: { party: Party }) {
  const year = yearOf(party.registered_at);
  return (
    <Link
      to={`/stranka/${party.slug}`}
      className="card-hover p-4 flex gap-4 items-center group no-underline"
    >
      <PartyAvatar party={party} size={56} />
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-semibold text-navy leading-snug line-clamp-2 group-hover:text-flag-red transition-colors">
            {party.canonical_name}
          </h3>
          <StatusBadge status={party.status} size="xs" />
        </div>
        <div className="text-xs text-muted truncate mt-0.5">
          {party.short_name && (
            <span className="font-medium text-navy-700">{party.short_name}</span>
          )}
          {party.short_name && (party.city || year) && " · "}
          {party.city}
          {party.city && year && " · "}
          {year && `reg. ${year}.`}
        </div>
        {party.president && (
          <div className="text-xs text-muted truncate mt-0.5">
            {party.president}
          </div>
        )}
        <div className="mt-2">
          <ContactDots p={party} />
        </div>
      </div>
    </Link>
  );
}
