// reactapp/src/BootstrapBoxPlots.tsx
// Use the ESM build (clean `export default`). The CJS `lib/core` interops to an
// object under Vite/rolldown, making the element type invalid at render time.
import { useRef } from 'react';
import ReactEChartsCore from 'echarts-for-react/esm/core';
import * as echarts from 'echarts/core';
import { BoxplotChart, ScatterChart } from 'echarts/charts';
import { GridComponent, TooltipComponent } from 'echarts/components';
import { SVGRenderer } from 'echarts/renderers';
import type { EChartsOption } from 'echarts';
import type { BootstrapStats, BoxStat } from './api';
import './BootstrapBoxPlots.css';

// Tree-shaken ECharts: register only what the box plots need so we don't pull
// the entire library into the bundle.
echarts.use([BoxplotChart, ScatterChart, GridComponent, TooltipComponent, SVGRenderer]);

interface Props {
  data: BootstrapStats;
}

const BOX_BORDER = '#25C2DF';
const BOX_FILL = 'rgba(37, 194, 223, 0.25)';
const OUTLIER_COLOR = '#CC0000';
const AXIS_COLOR = '#267788';
const GRID_COLOR = '#D1EFF6';

function chartOption(
  allMetrics: string[],
  byMetric: Record<string, BoxStat>,
): EChartsOption {
  const metrics = allMetrics.filter((m) => byMetric[m]);
  const boxData = metrics.map((m) => {
    const s = byMetric[m];
    return [s.min, s.q1, s.median, s.q3, s.max];
  });
  const outliers: number[][] = [];
  metrics.forEach((m, i) => {
    byMetric[m].outliers.forEach((o) => outliers.push([i, o]));
  });

  return {
    grid: { left: 52, right: 16, top: 16, bottom: 28 },
    tooltip: { trigger: 'item' },
    xAxis: {
      type: 'category',
      data: metrics,
      axisLabel: { color: AXIS_COLOR },
      axisTick: { alignWithLabel: true },
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { color: AXIS_COLOR },
      splitLine: { lineStyle: { color: GRID_COLOR } },
    },
    series: [
      {
        name: 'distribution',
        type: 'boxplot',
        data: boxData,
        itemStyle: { color: BOX_FILL, borderColor: BOX_BORDER },
      },
      {
        name: 'outliers',
        type: 'scatter',
        data: outliers,
        symbolSize: 5,
        itemStyle: { color: OUTLIER_COLOR },
      },
    ],
  };
}

// Minimal shape we need off the ECharts instance (avoids importing its full type).
type ChartInstance = {
  getDataURL: (opts?: { backgroundColor?: string }) => string;
  getWidth: () => number;
  getHeight: () => number;
};

// The SVG renderer's getDataURL yields an SVG data URL; paint it onto a canvas to
// export a PNG (falls back to downloading the SVG if the browser can't rasterize).
function downloadChartPng(inst: ChartInstance, filename: string) {
  const svgUrl = inst.getDataURL({ backgroundColor: '#ffffff' });
  const img = new Image();
  img.onload = () => {
    const w = img.naturalWidth || inst.getWidth();
    const h = img.naturalHeight || inst.getHeight();
    const scale = 2;
    const canvas = document.createElement('canvas');
    canvas.width = w * scale;
    canvas.height = h * scale;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.scale(scale, scale);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect(0, 0, w, h);
    ctx.drawImage(img, 0, 0, w, h);
    const a = document.createElement('a');
    a.href = canvas.toDataURL('image/png');
    a.download = filename;
    a.click();
  };
  img.onerror = () => {
    const a = document.createElement('a');
    a.href = svgUrl;
    a.download = filename.replace(/\.png$/, '.svg');
    a.click();
  };
  img.src = svgUrl;
}

function BootstrapBoxPlots({ data }: Props) {
  const instances = useRef<Record<string, ChartInstance>>({});
  return (
    <div className="results-panel">
      <div className="results-panel-title">
        Bootstrap distribution
        <span className="boxplot-hint">
          {' '}
          · spread of each metric across resampling iterations (box = IQR, points = outliers)
        </span>
      </div>
      {data.candidates.map((cand) => (
        <div className="boxplot-block" key={cand}>
          <div className="boxplot-block-head">
            {data.candidates.length > 1 && <div className="boxplot-cand">{cand}</div>}
            <button
              type="button"
              className="boxplot-png"
              onClick={() => {
                const inst = instances.current[cand];
                if (inst) downloadChartPng(inst, `boxplot_${cand}.png`);
              }}
            >
              ⬇ PNG
            </button>
          </div>
          <ReactEChartsCore
            echarts={echarts}
            option={chartOption(data.metrics, data.stats[cand] ?? {})}
            style={{ height: 300 }}
            opts={{ renderer: 'svg' }}
            onChartReady={(inst: ChartInstance) => { instances.current[cand] = inst; }}
          />
        </div>
      ))}
    </div>
  );
}

export default BootstrapBoxPlots;
