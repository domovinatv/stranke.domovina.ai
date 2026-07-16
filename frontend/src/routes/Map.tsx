import { useEffect, useMemo, useRef, useState } from "react";
import maplibregl, { type StyleSpecification } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { Link } from "react-router-dom";
import { loadParties, loadStats } from "@/lib/data";
import type { Party, Stats } from "@/lib/types";
import { PageSpinner } from "@/components/PageSpinner";
import { PartyAvatar } from "@/components/PartyAvatar";
import { StatusBadge } from "@/components/StatusBadge";

const STATUS_COLORS: Record<string, string> = {
  AKTIVAN: "#10B981", // emerald
  PRESTANAK: "#94A3B8", // slate
  UNKNOWN: "#F59E0B", // amber
};

// CARTO Voyager — clean light basemap, no API key
const CARTO_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    carto: {
      type: "raster",
      tiles: [
        "https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png",
        "https://b.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png",
        "https://c.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png",
      ],
      tileSize: 256,
      attribution:
        '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · © <a href="https://carto.com/attributions">CARTO</a>',
    },
  },
  layers: [{ id: "carto", type: "raster", source: "carto" }],
  // Glyphs su nužni za symbol layer (cluster count). Demotiles je javni
  // MapLibre glyph endpoint, fontstack "Noto Sans Regular" je tamo dostupan.
  glyphs: "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf",
};

export default function MapView() {
  const [parties, setParties] = useState<Party[] | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [selected, setSelected] = useState<Party | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    Promise.all([loadParties(), loadStats()]).then(([p, s]) => {
      setParties(p);
      setStats(s);
    });
  }, []);

  const geoParties = useMemo(
    () => (parties ? parties.filter((p) => p.lat != null && p.lng != null) : []),
    [parties],
  );

  useEffect(() => {
    if (!containerRef.current || !geoParties.length || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: CARTO_STYLE,
      center: [16.5, 45.1],
      zoom: 6.5,
      attributionControl: { compact: true },
    });
    mapRef.current = map;

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    const geojson: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: geoParties.map((p) => ({
        type: "Feature",
        id: p.id,
        geometry: { type: "Point", coordinates: [p.lng!, p.lat!] },
        properties: {
          slug: p.slug,
          name: p.canonical_name,
          status: p.status ?? "UNKNOWN",
        },
      })),
    };

    map.on("load", () => {
      map.addSource("parties", {
        type: "geojson",
        data: geojson,
        cluster: true,
        clusterRadius: 40,
        clusterMaxZoom: 11,
      });

      map.addLayer({
        id: "clusters",
        type: "circle",
        source: "parties",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#002F6C",
          "circle-opacity": 0.85,
          "circle-stroke-color": "#FFFFFF",
          "circle-stroke-width": 2,
          "circle-radius": [
            "step",
            ["get", "point_count"],
            16,
            10,
            20,
            50,
            26,
            150,
            34,
          ],
        },
      });
      map.addLayer({
        id: "cluster-count",
        type: "symbol",
        source: "parties",
        filter: ["has", "point_count"],
        layout: {
          "text-field": ["get", "point_count_abbreviated"],
          "text-font": ["Noto Sans Regular"],
          "text-size": 12,
          "text-allow-overlap": true,
        },
        paint: {
          "text-color": "#FFFFFF",
        },
      });

      map.addLayer({
        id: "points",
        type: "circle",
        source: "parties",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": [
            "match",
            ["get", "status"],
            "AKTIVAN", STATUS_COLORS.AKTIVAN,
            "PRESTANAK", STATUS_COLORS.PRESTANAK,
            STATUS_COLORS.UNKNOWN,
          ],
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            6, ["case", ["==", ["get", "status"], "AKTIVAN"], 6, 4],
            10, ["case", ["==", ["get", "status"], "AKTIVAN"], 10, 7],
            14, ["case", ["==", ["get", "status"], "AKTIVAN"], 14, 10],
          ],
          "circle-stroke-color": "#FFFFFF",
          "circle-stroke-width": 1.5,
          "circle-opacity": 0.95,
        },
      });

      map.on("click", "clusters", (e) => {
        const feat = map.queryRenderedFeatures(e.point, {
          layers: ["clusters"],
        })[0];
        const clusterId = feat.properties?.cluster_id;
        if (clusterId == null) return;
        const src = map.getSource("parties") as maplibregl.GeoJSONSource;
        src.getClusterExpansionZoom(clusterId).then((zoom) => {
          map.easeTo({
            center: (feat.geometry as GeoJSON.Point).coordinates as [number, number],
            zoom,
          });
        });
      });

      map.on("click", "points", (e) => {
        const feat = e.features?.[0];
        if (!feat) return;
        const id = feat.id as number;
        const p = geoParties.find((x) => x.id === id);
        if (p) setSelected(p);
      });

      map.on("mouseenter", "clusters", () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", "clusters", () => (map.getCanvas().style.cursor = ""));
      map.on("mouseenter", "points", () => (map.getCanvas().style.cursor = "pointer"));
      map.on("mouseleave", "points", () => (map.getCanvas().style.cursor = ""));
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [geoParties]);

  if (!parties || !stats) return <PageSpinner />;

  return (
    <section className="container-page py-6">
      <div className="flex items-center justify-between gap-3 flex-wrap mb-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-navy">Karta stranaka</h1>
          <p className="text-sm text-muted">
            <span className="font-medium text-navy">{geoParties.length}</span> stranaka
            lociranih od{" "}
            <span className="font-medium text-navy">{stats.global.total}</span>{" "}
            ({Math.round((100 * geoParties.length) / stats.global.total)}%)
          </p>
        </div>
        <Legend />
      </div>

      <div className="relative">
        <div
          ref={containerRef}
          className="rounded-DEFAULT border border-border overflow-hidden"
          style={{ height: "78vh", minHeight: 480 }}
        />
        {selected && (
          <PartyPopupCard
            party={selected}
            onClose={() => setSelected(null)}
          />
        )}
      </div>
    </section>
  );
}

function Legend() {
  const items = [
    { color: STATUS_COLORS.AKTIVAN, label: "Aktivna" },
    { color: STATUS_COLORS.PRESTANAK, label: "Ugašena" },
    { color: STATUS_COLORS.UNKNOWN, label: "Nepoznat status" },
  ];
  return (
    <div className="flex items-center gap-3 flex-wrap text-xs text-muted">
      {items.map((it) => (
        <span key={it.label} className="inline-flex items-center gap-1.5">
          <span
            className="w-2.5 h-2.5 rounded-full ring-2 ring-white shadow-sm"
            style={{ background: it.color }}
          />
          {it.label}
        </span>
      ))}
    </div>
  );
}

function PartyPopupCard({ party, onClose }: { party: Party; onClose: () => void }) {
  return (
    <div className="absolute left-4 bottom-4 right-4 sm:left-4 sm:bottom-4 sm:right-auto sm:max-w-sm card shadow-elevated p-4 flex gap-3 items-start z-10">
      <PartyAvatar party={party} size={56} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <Link
            to={`/stranka/${party.slug}`}
            className="font-semibold text-navy hover:text-flag-red truncate"
          >
            {party.canonical_name}
          </Link>
          <button
            onClick={onClose}
            aria-label="Zatvori"
            className="text-muted hover:text-navy text-xl leading-none"
          >
            ×
          </button>
        </div>
        <div className="text-xs text-muted mt-0.5">
          {party.city || "—"}
          {party.county && ` · ${party.county.replace(" županija", "")}`}
        </div>
        <div className="mt-1.5">
          <StatusBadge status={party.status} size="xs" />
        </div>
        {party.president && (
          <div className="text-xs text-muted mt-1">{party.president}</div>
        )}
        <div className="mt-3 flex gap-2 flex-wrap">
          <Link
            to={`/stranka/${party.slug}`}
            className="btn-ghost inline-flex !px-3 !py-1.5 text-xs"
          >
            Detalji →
          </Link>
        </div>
      </div>
    </div>
  );
}
