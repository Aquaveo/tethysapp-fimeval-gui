// reactapp/src/BootstrapBoxPlots.tsx
import ReactEChartsCore from 'echarts-for-react/lib/core';
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

function BootstrapBoxPlots({ data }: Props) {
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
          {data.candidates.length > 1 && <div className="boxplot-cand">{cand}</div>}
          <ReactEChartsCore
            echarts={echarts}
            option={chartOption(data.metrics, data.stats[cand] ?? {})}
            style={{ height: 300 }}
            opts={{ renderer: 'svg' }}
          />
        </div>
      ))}
    </div>
  );
}

export default BootstrapBoxPlots;
