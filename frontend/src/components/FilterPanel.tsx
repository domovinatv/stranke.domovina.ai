import {
  Check,
  Globe,
  Mail,
  MailOpen,
  Map,
  MessageCircle,
  Phone,
  RotateCcw,
} from "lucide-react";
import type { ReactNode } from "react";
import type { City, Stats } from "@/lib/types";
import type { PartyFilter, StatusFilter } from "@/lib/filter";

interface Props {
  filter: PartyFilter;
  onChange: (next: PartyFilter) => void;
  onReset: () => void;
  cities: City[];
  stats: Stats;
}

const STATUS_OPTIONS: Array<{ value: StatusFilter; label: string }> = [
  { value: "active", label: "Aktivne" },
  { value: "defunct", label: "Ugašene" },
  { value: "all", label: "Sve" },
];

export function FilterPanel({ filter, onChange, onReset, cities, stats }: Props) {
  const set = <K extends keyof PartyFilter>(k: K, v: PartyFilter[K]) =>
    onChange({ ...filter, [k]: v });

  const statusCount = (v: StatusFilter) =>
    v === "active"
      ? stats.global.active
      : v === "defunct"
        ? stats.global.defunct
        : stats.global.total;

  return (
    <aside className="lg:sticky lg:top-20 lg:self-start space-y-4">
      <div className="card p-4 space-y-4">
        <div>
          <label className="field-label" htmlFor="q">
            Pretraga
          </label>
          <input
            id="q"
            type="search"
            className="input"
            placeholder="Ime stranke, grad, predsjednik…"
            value={filter.q}
            onChange={(e) => set("q", e.target.value)}
          />
        </div>

        <div>
          <label className="field-label" htmlFor="status">
            Status
          </label>
          <select
            id="status"
            className="input"
            value={filter.status}
            onChange={(e) => set("status", e.target.value as StatusFilter)}
          >
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label} ({statusCount(o.value)})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="field-label" htmlFor="city">
            Grad
          </label>
          <select
            id="city"
            className="input"
            value={filter.city ?? ""}
            onChange={(e) => set("city", e.target.value || undefined)}
          >
            <option value="">Svi gradovi</option>
            {cities.map((c) => (
              <option key={c.name} value={c.name}>
                {c.name} ({c.n})
              </option>
            ))}
          </select>
        </div>

        <div>
          <div className="field-label">Filtriraj po kontaktu</div>
          <div className="space-y-2 text-sm">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                className="accent-emerald-600 w-4 h-4 rounded"
                checked={filter.onlyFull}
                onChange={(e) => set("onlyFull", e.target.checked)}
              />
              <span className="font-medium text-emerald-700 inline-flex items-center gap-1.5">
                <Check size={14} strokeWidth={2.5} /> Samo pun kontakt
              </span>
              <span className="text-muted text-xs ml-auto">
                {stats.global.full_contact}
              </span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                className="accent-navy w-4 h-4 rounded"
                checked={filter.hasMobile}
                onChange={(e) => set("hasMobile", e.target.checked)}
              />
              <span className="inline-flex items-center gap-1.5"><MessageCircle size={14} /> Mobitel (SMS)</span>
              <span className="text-muted text-xs ml-auto">
                {stats.global.can_sms}
              </span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                className="accent-navy w-4 h-4 rounded"
                checked={filter.hasPhone}
                onChange={(e) => set("hasPhone", e.target.checked)}
              />
              <span className="inline-flex items-center gap-1.5"><Phone size={14} /> Telefon</span>
              <span className="text-muted text-xs ml-auto">
                {stats.global.can_call}
              </span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                className="accent-navy w-4 h-4 rounded"
                checked={filter.hasEmail}
                onChange={(e) => set("hasEmail", e.target.checked)}
              />
              <span className="inline-flex items-center gap-1.5"><Mail size={14} /> Email</span>
              <span className="text-muted text-xs ml-auto">
                {stats.global.can_email}
              </span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                className="accent-navy w-4 h-4 rounded"
                checked={filter.hasWeb}
                onChange={(e) => set("hasWeb", e.target.checked)}
              />
              <span className="inline-flex items-center gap-1.5"><Globe size={14} /> Web/društvene</span>
              <span className="text-muted text-xs ml-auto">
                {stats.global.can_web}
              </span>
            </label>
          </div>
        </div>

        <div className="pt-2 border-t border-border">
          <button type="button" onClick={onReset} className="text-xs text-muted hover:text-flag-red">
            <span className="inline-flex items-center gap-1"><RotateCcw size={12} /> Resetiraj filtere</span>
          </button>
        </div>
      </div>

      <div className="card p-4">
        <div className="field-label">Pokrivenost</div>
        <dl className="text-sm space-y-1.5">
          <Row label="Ukupno stranaka" value={stats.global.total} bold />
          <Row
            label={<><Check size={13} strokeWidth={2.5} /> Pun kontakt</>}
            value={stats.global.full_contact}
            accent="emerald"
          />
          <Row label={<><MessageCircle size={13} /> Mogu SMS</>} value={stats.global.can_sms} />
          <Row label={<><Phone size={13} /> Mogu nazvati</>} value={stats.global.can_call} />
          <Row label={<><Mail size={13} /> Mogu email</>} value={stats.global.can_email} />
          <Row label={<><MailOpen size={13} /> Mogu poštom</>} value={stats.global.can_mail} />
          <Row label={<><Globe size={13} /> Online prisutne</>} value={stats.global.can_web} />
          <Row label={<><Map size={13} /> Imaju koord.</>} value={stats.global.with_geo} />
        </dl>
      </div>
    </aside>
  );
}

function Row({
  label,
  value,
  bold,
  muted,
  accent,
}: {
  label: ReactNode;
  value: number;
  bold?: boolean;
  muted?: boolean;
  accent?: "emerald";
}) {
  return (
    <div className="flex items-center justify-between">
      <dt
        className={
          accent === "emerald"
            ? "text-emerald-700 font-medium"
            : muted
              ? "text-muted/70"
              : "text-muted"
        }
      >
        <span className="inline-flex items-center gap-1.5">{label}</span>
      </dt>
      <dd
        className={`tabular-nums ${bold ? "font-bold text-navy" : ""} ${
          muted ? "text-muted/70" : ""
        }`}
      >
        {value.toLocaleString("hr-HR")}
      </dd>
    </div>
  );
}
