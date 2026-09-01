import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
// maplibre resolves its worker via `new URL('./maplibre-gl-worker.mjs', <bundle url>)`,
// a pattern its minified build hides from Vite's static analysis — so in a
// production build Vite never emits the worker and the browser 404s for it.
// Import the worker with `?worker&url` so Vite bundles it into a self-contained
// asset and hands us the real (base-prefixed, hashed) URL to register.
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
import { fetchTileJson, fetchBasemaps, type TileJson, type Basemap } from './api';
import './ContingencyMap.css';

maplibregl.setWorkerUrl(maplibreWorkerUrl);

// Built-in fallback so the map still renders if api/basemaps is unreachable.
const FALLBACK_BASEMAPS: Basemap[] = [
  {
    key: 'satellite',
    label: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Esri, Maxar, Earthstar Geographics',
  },
];

const LEGEND = [
  { color: 'rgb(31,119,180)', label: 'TP — correct flood' },
  { color: 'rgb(214,39,40)', label: 'FP — over-prediction' },
  { color: 'rgb(255,140,0)', label: 'FN — missed flood' },
  { color: 'rgb(210,210,210)', label: 'TN — correct dry' },
  { color: 'rgb(20,40,80)', label: 'Permanent water' },
];

export default function ContingencyMap({ jobId }: { jobId: number }) {
  const container = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [tj, setTj] = useState<TileJson | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [visible, setVisible] = useState(true);
  const [opacity, setOpacity] = useState(1);
  const [basemaps, setBasemaps] = useState<Basemap[]>(FALLBACK_BASEMAPS);
  const [activeKey, setActiveKey] = useState(FALLBACK_BASEMAPS[0].key);

  const active = basemaps.find((b) => b.key === activeKey) ?? basemaps[0];
  // Read the active basemap at map-build time without making the build effect
  // depend on it (switching happens via setTiles, not a rebuild).
  const activeRef = useRef(active);
  useEffect(() => {
    activeRef.current = active;
  }, [active]);

  useEffect(() => {
    let cancelled = false;
    fetchTileJson(jobId)
      .then((t) => !cancelled && setTj(t))
      .catch(() => !cancelled && setUnavailable(true));
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  // Configurable basemaps (FE19). Best-effort — keep the fallback on failure.
  useEffect(() => {
    let cancelled = false;
    fetchBasemaps()
      .then((cfg) => {
        if (cancelled || !cfg.layers.length) return;
        setBasemaps(cfg.layers);
        setActiveKey(cfg.default);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!tj || !container.current) return;
    const bm = activeRef.current;
    const map = new maplibregl.Map({
      container: container.current,
      style: {
        version: 8,
        sources: {
          basemap: {
            type: 'raster', tiles: [bm.url], tileSize: 256, attribution: bm.attribution,
          },
          contingency: {
            type: 'raster', tiles: tj.tiles, tileSize: 256,
            bounds: tj.bounds, minzoom: tj.minzoom, maxzoom: tj.maxzoom,
          },
        },
        layers: [
          { id: 'basemap', type: 'raster', source: 'basemap' },
          { id: 'contingency', type: 'raster', source: 'contingency' },
        ],
      },
      bounds: tj.bounds,
      fitBoundsOptions: { padding: 24 },
    });
    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [tj]);

  // Swap the basemap tiles when the user picks a different layer (no rebuild).
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      const src = map.getSource('basemap') as maplibregl.RasterTileSource | undefined;
      if (src) src.setTiles([active.url]);
    };
    if (map.isStyleLoaded()) apply();
    else map.once('load', apply);
  }, [active.url, tj]);

  // Drive the overlay's visibility + opacity from the controls. Applies once the
  // style is loaded (setPaint/Layout need the layer to exist).
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    const apply = () => {
      if (!map.getLayer('contingency')) return;
      map.setLayoutProperty('contingency', 'visibility', visible ? 'visible' : 'none');
      map.setPaintProperty('contingency', 'raster-opacity', opacity);
    };
    if (map.isStyleLoaded()) apply();
    else map.once('load', apply);
  }, [visible, opacity, tj]);

  if (unavailable) return null;

  return (
    <div className="contingency-map">
      <div className="results-panel-title">Contingency Map</div>
      <div ref={container} className="contingency-map-canvas" />
      <div className="contingency-controls">
        {basemaps.length > 1 && (
          <div className="contingency-basemaps" role="group" aria-label="Basemap">
            {basemaps.map((b) => (
              <button
                key={b.key}
                type="button"
                className={`contingency-basemap-btn${b.key === activeKey ? ' is-active' : ''}`}
                onClick={() => setActiveKey(b.key)}
              >
                {b.label}
              </button>
            ))}
          </div>
        )}
        <label className="contingency-control">
          <input
            type="checkbox"
            checked={visible}
            onChange={(e) => setVisible(e.target.checked)}
          />
          Show overlay
        </label>
        <label className="contingency-control">
          Opacity
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={opacity}
            disabled={!visible}
            onChange={(e) => setOpacity(Number(e.target.value))}
          />
          <span className="contingency-control-value">{Math.round(opacity * 100)}%</span>
        </label>
      </div>
      <ul className="contingency-legend">
        {LEGEND.map((l) => (
          <li key={l.label}>
            <span className="contingency-swatch" style={{ background: l.color }} />
            {l.label}
          </li>
        ))}
      </ul>
    </div>
  );
}
