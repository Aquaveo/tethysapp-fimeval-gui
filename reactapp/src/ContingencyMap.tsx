import { useEffect, useRef, useState } from 'react';
import * as maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { fetchTileJson, type TileJson } from './api';
import './ContingencyMap.css';

const ESRI_IMAGERY =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

const LEGEND = [
  { color: 'rgb(31,119,180)', label: 'TP — correct flood' },
  { color: 'rgb(214,39,40)', label: 'FP — over-prediction' },
  { color: 'rgb(255,140,0)', label: 'FN — missed flood' },
  { color: 'rgb(210,210,210)', label: 'TN — correct dry' },
  { color: 'rgb(20,40,80)', label: 'Permanent water' },
];

export default function ContingencyMap({ jobId }: { jobId: number }) {
  const container = useRef<HTMLDivElement | null>(null);
  const [tj, setTj] = useState<TileJson | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchTileJson(jobId)
      .then((t) => !cancelled && setTj(t))
      .catch(() => !cancelled && setUnavailable(true));
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  useEffect(() => {
    if (!tj || !container.current) return;
    const map = new maplibregl.Map({
      container: container.current,
      style: {
        version: 8,
        sources: {
          basemap: {
            type: 'raster', tiles: [ESRI_IMAGERY], tileSize: 256, attribution: 'Esri',
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
    return () => map.remove();
  }, [tj]);

  if (unavailable) return null;

  return (
    <div className="contingency-map">
      <div className="results-panel-title">Contingency Map</div>
      <div ref={container} className="contingency-map-canvas" />
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
