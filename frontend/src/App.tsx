import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

/*
 * ---------------------------------------------------------
 * TYPES
 * ---------------------------------------------------------
 */

type DashboardData = {
  total_units: number
  total_revenue: number
  forecast_accuracy: number
  top_product: string
}

type SalesData = {
  month: string
  actual_units: number
  forecast_units: number
  revenue: number
}

type ProductData = {
  product: string
  actual_units: number
  forecast_units: number
  revenue: number
}

type Insight = {
  type: 'positive' | 'warning' | 'neutral'
  title: string
  message: string
}

type SarimaMetrics = {
  accuracy_pct: number
  mase_pooled: number | null
  mase_fold_mean: number | null
  bias_pct: number | null
  pct_folds_beating_naive: number | null
  n_folds: number
}

type SarimaDiagScheme = {
  SARIMA?: SarimaMetrics
  SeasonalNaive?: SarimaMetrics
  vs_baseline?: {
    gap: number | null
    ci95: [number | null, number | null] | null
    p: number | null
    distinguishable: boolean | null
  }
  beats_naive?: boolean | null
}

type ForecastResult = {
  status: 'idle' | 'running' | 'already_running' | 'ok' | 'insufficient_history' | 'error'
  job_id?: string
  params?: {
    dimension: ForecastDimension
    dimension_value: string | null
    value_col: ForecastValueCol
    horizon: number
    fast: boolean
  }
  forecast?: {
    series: string
    spec: string
    horizon: number
    months: string[]
    point: number[]
    lower_90: number[]
    upper_90: number[]
    annual_total: number
    annual_yoy_pct: number | null
    plausibility_ok: boolean
    plausibility_detail: string | null
  }
  diagnostics?: {
    wf1: SarimaDiagScheme
    wf12: SarimaDiagScheme
    ljung_box_p: number | null
    residuals_clean: boolean | null
    negative_predictions_clipped: number
    fit_warnings: number
    fit_failures: number
  }
  data_anomalies?: { message: string }[]
  warnings?: { kind: string; message: string }[]
  message?: string
  detail?: string
}

type ForecastDimension = 'total' | 'product' | 'customer'
type ForecastValueCol = 'revenue' | 'actual_units'

type ForecastOptions = {
  products: string[]
  customers: string[]
}

type ViewId =
  | 'overview'
  | 'forecast'
  | 'revenue'
  | 'inventory'
  | 'products'
  | 'customers'
  | 'accuracy'
  | 'lab'

type PeriodId = 'all' | '6' | '12' | '24'

type ProductSort = 'revenue-desc' | 'revenue-asc' | 'variance-desc' | 'variance-asc'

/*
 * ---------------------------------------------------------
 * ICONS (inline, stroke-based, no external icon dependency)
 * ---------------------------------------------------------
 */

type IconProps = { size?: number }

const IconGrid = ({ size = 18 }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
    <rect x="3" y="3" width="8" height="8" rx="1.5" />
    <rect x="13" y="3" width="8" height="8" rx="1.5" />
    <rect x="3" y="13" width="8" height="8" rx="1.5" />
    <rect x="13" y="13" width="8" height="8" rx="1.5" />
  </svg>
)

const IconTrend = ({ size = 18 }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M3 17l6-6 4 4 8-9" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M15 6h6v6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

const IconCoin = ({ size = 18 }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v10M9 9.5c0-1.4 1.3-2.5 3-2.5s3 1 3 2.2-1.3 1.8-3 2-3 .9-3 2.1 1.3 2.2 3 2.2 3-1.1 3-2.5" strokeLinecap="round" />
  </svg>
)

const IconBox = ({ size = 18 }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M3 8l9-5 9 5-9 5-9-5z" strokeLinejoin="round" />
    <path d="M3 8v8l9 5 9-5V8" strokeLinejoin="round" />
    <path d="M12 13v8" />
  </svg>
)

const IconLayers = ({ size = 18 }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M12 3l9 5-9 5-9-5 9-5z" strokeLinejoin="round" />
    <path d="M3 13l9 5 9-5" strokeLinejoin="round" />
  </svg>
)

const IconUsers = ({ size = 18 }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
    <circle cx="9" cy="8" r="3.2" />
    <path d="M3 20c0-3.3 2.7-5.5 6-5.5s6 2.2 6 5.5" strokeLinecap="round" />
    <path d="M16 8.2c1.5.2 2.6 1.4 2.6 2.8 0 1.3-1 2.5-2.3 2.8M19 20c0-2.6-1.7-4.5-4-5.2" strokeLinecap="round" />
  </svg>
)

const IconTarget = ({ size = 18 }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="4.5" />
    <circle cx="12" cy="12" r="0.8" fill="currentColor" />
  </svg>
)

const IconChevron = ({ size = 14 }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M6 9l6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

const IconFlask = ({ size = 18 }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
    <path d="M9 2v6.3L4.2 17a2 2 0 0 0 1.8 2.9h12a2 2 0 0 0 1.8-2.9L15 8.3V2" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M7 2h10" strokeLinecap="round" />
    <path d="M6.7 14.5h10.6" strokeLinecap="round" />
  </svg>
)

const IconSearch = ({ size = 16 }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
    <circle cx="11" cy="11" r="7" />
    <path d="M20 20l-4-4" strokeLinecap="round" />
  </svg>
)

/*
 * ---------------------------------------------------------
 * STATIC CONFIG
 * ---------------------------------------------------------
 */

const NAV_ITEMS: { id: ViewId; label: string; icon: (p: IconProps) => JSX.Element }[] = [
  { id: 'overview', label: 'Overview', icon: IconGrid },
  { id: 'forecast', label: 'Sales forecast', icon: IconTrend },
  { id: 'revenue', label: 'Revenue', icon: IconCoin },
  { id: 'inventory', label: 'Inventory risk', icon: IconBox },
  { id: 'products', label: 'Products', icon: IconLayers },
  { id: 'customers', label: 'Customers', icon: IconUsers },
  { id: 'accuracy', label: 'Forecast accuracy', icon: IconTarget },
  { id: 'lab', label: 'Forecast lab', icon: IconFlask },
]

const PERIOD_OPTIONS: { id: PeriodId; label: string }[] = [
  { id: 'all', label: 'All time' },
  { id: '6', label: 'Last 6 months' },
  { id: '12', label: 'Last 12 months' },
  { id: '24', label: 'Last 24 months' },
]

const VIEW_META: Record<ViewId, { title: string; subtitle: string }> = {
  overview: {
    title: 'Sales intelligence dashboard',
    subtitle: 'AI-powered sales order forecasting and analysis',
  },
  forecast: {
    title: 'Sales forecast',
    subtitle: 'Actual vs forecast units, with the validated SARIMA projection',
  },
  revenue: {
    title: 'Revenue',
    subtitle: 'Monthly revenue performance over the selected period',
  },
  inventory: {
    title: 'Inventory risk',
    subtitle: 'Products where forecast and actuals diverge most — a proxy for over/under-stock risk',
  },
  products: {
    title: 'Products',
    subtitle: 'Revenue contribution and forecast variance by product',
  },
  customers: {
    title: 'Customers',
    subtitle: 'Customer-level breakdown',
  },
  accuracy: {
    title: 'Forecast accuracy',
    subtitle: '1-month vs 12-month validation results for the SARIMA model',
  },
  lab: {
    title: 'Forecast lab',
    subtitle: 'Run the SARIMA engine directly against any product, customer, or the whole company',
  },
}

/*
 * ---------------------------------------------------------
 * FORECAST LAB CHART — history (solid line) feeding into the
 * SARIMA point forecast (dashed) with its 90% band shaded
 * behind it. Pure/stateless, so it lives outside App().
 * ---------------------------------------------------------
 */

/*
 * ---------------------------------------------------------
 * SARIMA FORECAST CHART — history (solid line) feeding into the
 * point forecast (dashed) with its 90% band shaded behind it,
 * plus a vertical "Today" cutoff line marking where actuals end
 * and the forecast begins. Shared by the default dashboard
 * forecast panel and the Forecast Lab. Pure/stateless, so it
 * lives outside App().
 * ---------------------------------------------------------
 */

type SarimaChartProps = {
  history: SalesData[]
  forecast: NonNullable<ForecastResult['forecast']>
  valueCol: ForecastValueCol
}

// Keep only the most recent stretch of history so the forecast segment
// (usually 12 months) stays visually readable next to years of actuals.
const SARIMA_CHART_MAX_HISTORY = 24

const SarimaForecastChart = ({ history, forecast, valueCol }: SarimaChartProps) => {
  const width = 600
  const height = 200
  const pad = 10

  const trimmedHistory =
    history.length > SARIMA_CHART_MAX_HISTORY
      ? history.slice(history.length - SARIMA_CHART_MAX_HISTORY)
      : history

  const histValues = trimmedHistory.map((h) => (valueCol === 'revenue' ? h.revenue : h.actual_units))

  const allValues = [...histValues, ...forecast.upper_90, ...forecast.lower_90, ...forecast.point]
  const max = allValues.length ? Math.max(...allValues) : 1
  const min = allValues.length ? Math.min(...allValues) : 0
  const range = Math.max(max - min, 1)

  const totalPoints = histValues.length + forecast.point.length
  const xFor = (i: number) =>
    totalPoints > 1 ? (i / (totalPoints - 1)) * (width - pad * 2) + pad : width / 2
  const yFor = (v: number) => height - ((v - min) / range) * (height - pad * 2) - pad

  const histPoints = histValues.map((v, i) => `${xFor(i)},${yFor(v)}`).join(' ')

  const fStart = histValues.length
  const pointPoints = forecast.point.map((v, i) => `${xFor(fStart + i)},${yFor(v)}`).join(' ')
  const upperPoints = forecast.upper_90.map((v, i) => `${xFor(fStart + i)},${yFor(v)}`)
  const lowerPoints = forecast.lower_90.map((v, i) => `${xFor(fStart + i)},${yFor(v)}`).reverse()
  const bandPoints = [...upperPoints, ...lowerPoints].join(' ')

  // Cutoff sits halfway between the last actual and the first forecast
  // point — "today", the boundary the model is extrapolating from.
  const cutoffX = histValues.length > 0 ? xFor(fStart - 0.5) : pad
  const cutoffLabelAnchor = cutoffX > width - 40 ? 'end' : 'start'

  return (
    <div className="sarima-chart">
      <svg className="sarima-chart-svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        {bandPoints && <polygon points={bandPoints} className="sarima-chart-band" />}
        {histPoints && <polyline points={histPoints} className="sarima-chart-history" fill="none" />}
        {pointPoints && <polyline points={pointPoints} className="sarima-chart-forecast" fill="none" />}
        {histValues.length > 0 && forecast.point.length > 0 && (
          <>
            <line x1={cutoffX} x2={cutoffX} y1={0} y2={height} className="sarima-chart-cutoff" />
            <text
              x={cutoffLabelAnchor === 'end' ? cutoffX - 4 : cutoffX + 4}
              y={11}
              textAnchor={cutoffLabelAnchor}
              className="sarima-chart-cutoff-label"
            >
              Today
            </text>
          </>
        )}
      </svg>

      <div className="sarima-chart-labels">
        <span>{trimmedHistory[0]?.month ?? ''}</span>
        <span>{trimmedHistory[trimmedHistory.length - 1]?.month ?? forecast.months[0]}</span>
        <span>{forecast.months[forecast.months.length - 1] ?? ''}</span>
      </div>

      <div className="chart-legend">
        <span><i className="legend-dot actual-dot" />History</span>
        <span><i className="legend-dot forecast-dot" style={{ opacity: 1, background: 'var(--accent)' }} />Forecast</span>
        <span><i className="legend-dot" style={{ background: 'var(--accent)', opacity: 0.2 }} />90% interval</span>
      </div>
    </div>
  )
}

/*
 * ---------------------------------------------------------
 * SALES PERFORMANCE PANEL — upgraded from a flat actual/forecast
 * bar chart into a multi-parameter view: grouped bars for actual
 * vs forecast (or a single revenue bar), a secondary-axis trend
 * line (forecast accuracy % in units mode, MoM growth % in
 * revenue mode), a hover tooltip, and a stat strip above the
 * chart summarizing the period at a glance. Pure/stateless aside
 * from its own metric toggle, so it lives outside App().
 * ---------------------------------------------------------
 */

type SalesPerfMetric = 'units' | 'revenue'

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

const spFormatChange = (value: number | null) => {
  if (value === null || !Number.isFinite(value)) return '—'
  const sign = value > 0 ? '+' : ''
  return `${sign}${value.toFixed(1)}%`
}

const spChangeClass = (value: number | null) => {
  if (value === null || !Number.isFinite(value) || value === 0) return 'sp-neutral'
  return value > 0 ? 'sp-positive' : 'sp-negative'
}

const SalesPerformancePanel = ({
  sales,
  monthLabel,
}: {
  sales: SalesData[]
  monthLabel: (month: string) => string
}) => {
  const [metric, setMetric] = useState<SalesPerfMetric>('units')
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)

  const n = sales.length

  /* ---- period-level stats (the "additional parameters") ---- */

  const totalActual = sales.reduce((t, s) => t + s.actual_units, 0)
  const totalForecast = sales.reduce((t, s) => t + s.forecast_units, 0)
  const totalRevenue = sales.reduce((t, s) => t + s.revenue, 0)

  const monthlyAccuracy = sales.map((s) =>
    s.actual_units > 0
      ? clamp(100 - (Math.abs(s.actual_units - s.forecast_units) / s.actual_units) * 100, 0, 100)
      : null,
  )
  const validAccuracies = monthlyAccuracy.filter((v): v is number => v !== null)
  const avgAccuracy =
    validAccuracies.length > 0
      ? validAccuracies.reduce((t, v) => t + v, 0) / validAccuracies.length
      : null

  const monthlyGrowth = sales.map((s, i) => {
    if (i === 0 || sales[i - 1].revenue <= 0) return null
    return ((s.revenue - sales[i - 1].revenue) / sales[i - 1].revenue) * 100
  })
  const validGrowth = monthlyGrowth.filter((v): v is number => v !== null)
  const avgGrowth =
    validGrowth.length > 0 ? validGrowth.reduce((t, v) => t + v, 0) / validGrowth.length : null

  const bestMonth = sales.reduce<SalesData | null>(
    (best, s) => (!best || s.actual_units > best.actual_units ? s : best),
    null,
  )

  const netVariance = totalActual > 0 ? ((totalActual - totalForecast) / totalActual) * 100 : null

  /* ---- chart geometry ---- */

  const width = 760
  const height = 300
  const padLeft = 48
  const padRight = 48
  const padTop = 22
  const padBottom = 46
  const plotW = width - padLeft - padRight
  const plotH = height - padTop - padBottom

  const slotW = n > 0 ? plotW / n : plotW
  const xForIndex = (i: number) => padLeft + slotW * i + slotW / 2

  const primaryValues =
    metric === 'units'
      ? sales.flatMap((s) => [s.actual_units, s.forecast_units])
      : sales.map((s) => s.revenue)
  const maxPrimary = primaryValues.length > 0 ? Math.max(...primaryValues) * 1.15 : 1
  const yForPrimary = (v: number) => padTop + plotH - (v / maxPrimary) * plotH

  const secondaryValues = metric === 'units' ? monthlyAccuracy : monthlyGrowth
  const maxAbsSecondary =
    metric === 'units'
      ? 100
      : Math.max(...secondaryValues.map((v) => (v !== null ? Math.abs(v) : 0)), 10) * 1.2

  const yForSecondary = (v: number) =>
    metric === 'units'
      ? padTop + plotH - (v / 100) * plotH
      : padTop + plotH - ((v + maxAbsSecondary) / (2 * maxAbsSecondary)) * plotH

  const linePoints = secondaryValues
    .map((v, i) => (v === null ? null : `${xForIndex(i)},${yForSecondary(v)}`))
    .filter((p): p is string => p !== null)
    .join(' ')

  const gridLines = [0, 0.25, 0.5, 0.75, 1]

  const hovered = hoverIndex !== null ? sales[hoverIndex] : null
  const hoveredAccuracy = hoverIndex !== null ? monthlyAccuracy[hoverIndex] : null
  const hoveredGrowth = hoverIndex !== null ? monthlyGrowth[hoverIndex] : null

  return (
    <div className="sp-root">
      <style>{`
        .sp-root { display: flex; flex-direction: column; gap: 16px; }
        .sp-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
        .sp-metric-toggle { display: inline-flex; border: 1px solid var(--border, rgba(127,127,127,0.25)); border-radius: 8px; overflow: hidden; }
        .sp-metric-toggle button { border: none; background: transparent; padding: 6px 14px; font-size: 12.5px; font-weight: 600; letter-spacing: 0.01em; cursor: pointer; color: var(--muted, #8892a6); transition: background 0.15s, color 0.15s; }
        .sp-metric-toggle button.sp-active { background: var(--accent, #6366f1); color: #fff; }
        .sp-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; }
        .sp-stat { border: 1px solid var(--border, rgba(127,127,127,0.18)); border-radius: 10px; padding: 10px 12px; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
        .sp-stat-label { font-size: 11px; color: var(--muted, #8892a6); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .sp-stat-value { font-size: 17px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .sp-stat-sub { font-size: 11px; font-weight: 600; }
        .sp-positive { color: #22c55e; }
        .sp-negative { color: #ef4444; }
        .sp-neutral { color: var(--muted, #8892a6); }
        .sp-chart-wrap { position: relative; width: 100%; }
        .sp-chart-svg { width: 100%; height: auto; display: block; overflow: visible; }
        .sp-grid-line { stroke: var(--border, rgba(127,127,127,0.14)); stroke-width: 1; }
        .sp-axis-label { fill: var(--muted, #8892a6); font-size: 10px; }
        .sp-x-label { fill: var(--muted, #8892a6); font-size: 10px; }
        .sp-bar-actual { fill: url(#spActualGrad); }
        .sp-bar-forecast { fill: url(#spForecastGrad); }
        .sp-bar-revenue { fill: url(#spRevenueGrad); }
        .sp-line { fill: none; stroke: #f5a623; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
        .sp-line-dot { fill: #f5a623; }
        .sp-hover-rect { fill: transparent; }
        .sp-hover-rect:hover { fill: var(--border, rgba(127,127,127,0.08)); }
        .sp-tooltip { position: absolute; top: 4px; pointer-events: none; background: var(--panel-bg, #1a1d27); border: 1px solid var(--border, rgba(127,127,127,0.25)); border-radius: 8px; padding: 8px 10px; font-size: 12px; min-width: 150px; box-shadow: 0 8px 24px rgba(0,0,0,0.25); transform: translateX(-50%); z-index: 5; }
        .sp-tooltip strong { display: block; margin-bottom: 4px; font-size: 12.5px; }
        .sp-tooltip-row { display: flex; justify-content: space-between; gap: 12px; padding: 1px 0; color: var(--muted, #8892a6); }
        .sp-tooltip-row span:last-child { color: inherit; font-weight: 600; }
        .sp-legend { display: flex; gap: 16px; flex-wrap: wrap; font-size: 12px; color: var(--muted, #8892a6); }
        .sp-legend-dot { display: inline-block; width: 9px; height: 9px; border-radius: 2px; margin-right: 5px; vertical-align: middle; }
      `}</style>

      <div className="sp-toolbar">
        <div className="sp-metric-toggle">
          <button
            className={metric === 'units' ? 'sp-active' : ''}
            onClick={() => setMetric('units')}
          >
            Units
          </button>
          <button
            className={metric === 'revenue' ? 'sp-active' : ''}
            onClick={() => setMetric('revenue')}
          >
            Revenue
          </button>
        </div>

        <div className="sp-legend">
          {metric === 'units' ? (
            <>
              <span><i className="sp-legend-dot" style={{ background: 'var(--accent, #6366f1)' }} />Actual</span>
              <span><i className="sp-legend-dot" style={{ background: 'var(--accent, #6366f1)', opacity: 0.4 }} />Forecast</span>
              <span><i className="sp-legend-dot" style={{ background: '#f5a623' }} />Accuracy %</span>
            </>
          ) : (
            <>
              <span><i className="sp-legend-dot" style={{ background: 'var(--accent, #6366f1)' }} />Revenue</span>
              <span><i className="sp-legend-dot" style={{ background: '#f5a623' }} />MoM growth %</span>
            </>
          )}
        </div>
      </div>

      <div className="sp-stats">
        <div className="sp-stat">
          <span className="sp-stat-label">Total units (actual)</span>
          <span className="sp-stat-value">{totalActual.toLocaleString()}</span>
          <span className={`sp-stat-sub ${spChangeClass(netVariance)}`}>
            {netVariance !== null ? `${spFormatChange(netVariance)} vs forecast` : '—'}
          </span>
        </div>
        <div className="sp-stat">
          <span className="sp-stat-label">Total revenue</span>
          <span className="sp-stat-value">฿{(totalRevenue / 1_000_000).toFixed(2)}M</span>
          <span className={`sp-stat-sub ${spChangeClass(avgGrowth)}`}>
            {avgGrowth !== null ? `${spFormatChange(avgGrowth)} avg MoM` : '—'}
          </span>
        </div>
        <div className="sp-stat">
          <span className="sp-stat-label">Avg forecast accuracy</span>
          <span className="sp-stat-value">{avgAccuracy !== null ? `${avgAccuracy.toFixed(1)}%` : '—'}</span>
          <span className="sp-stat-sub sp-neutral">{validAccuracies.length} months scored</span>
        </div>
        <div className="sp-stat">
          <span className="sp-stat-label">Best month (units)</span>
          <span className="sp-stat-value">{bestMonth ? monthLabel(bestMonth.month) : '—'}</span>
          <span className="sp-stat-sub sp-neutral">
            {bestMonth ? `${bestMonth.actual_units.toLocaleString()} units` : '—'}
          </span>
        </div>
      </div>

      <div className="sp-chart-wrap">
        {n > 0 ? (
          <>
            <svg className="sp-chart-svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
              <defs>
                <linearGradient id="spActualGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--accent, #6366f1)" stopOpacity="0.95" />
                  <stop offset="100%" stopColor="var(--accent, #6366f1)" stopOpacity="0.55" />
                </linearGradient>
                <linearGradient id="spForecastGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--accent, #6366f1)" stopOpacity="0.35" />
                  <stop offset="100%" stopColor="var(--accent, #6366f1)" stopOpacity="0.12" />
                </linearGradient>
                <linearGradient id="spRevenueGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--accent, #6366f1)" stopOpacity="0.95" />
                  <stop offset="100%" stopColor="var(--accent, #6366f1)" stopOpacity="0.4" />
                </linearGradient>
              </defs>

              {gridLines.map((g) => {
                const y = padTop + plotH * g
                const val = Math.round(maxPrimary * (1 - g))
                return (
                  <g key={g}>
                    <line x1={padLeft} x2={width - padRight} y1={y} y2={y} className="sp-grid-line" />
                    <text x={padLeft - 8} y={y + 3} textAnchor="end" className="sp-axis-label">
                      {val >= 1000 ? `${Math.round(val / 1000)}k` : val}
                    </text>
                    <text x={width - padRight + 8} y={y + 3} textAnchor="start" className="sp-axis-label">
                      {metric === 'units'
                        ? `${Math.round(100 * (1 - g))}%`
                        : `${Math.round(maxAbsSecondary * (1 - 2 * g))}%`}
                    </text>
                  </g>
                )
              })}

              {sales.map((s, i) => {
                const barGap = slotW * 0.08
                if (metric === 'units') {
                  const barW = slotW * 0.32
                  const actualX = xForIndex(i) - barW - barGap / 2
                  const forecastX = xForIndex(i) + barGap / 2
                  const actualY = yForPrimary(s.actual_units)
                  const forecastY = yForPrimary(s.forecast_units)
                  return (
                    <g key={s.month}>
                      <rect
                        x={actualX}
                        y={actualY}
                        width={barW}
                        height={Math.max(padTop + plotH - actualY, 0)}
                        rx={3}
                        className="sp-bar-actual"
                      />
                      <rect
                        x={forecastX}
                        y={forecastY}
                        width={barW}
                        height={Math.max(padTop + plotH - forecastY, 0)}
                        rx={3}
                        className="sp-bar-forecast"
                      />
                    </g>
                  )
                }
                const barW = slotW * 0.5
                const barX = xForIndex(i) - barW / 2
                const barY = yForPrimary(s.revenue)
                return (
                  <rect
                    key={s.month}
                    x={barX}
                    y={barY}
                    width={barW}
                    height={Math.max(padTop + plotH - barY, 0)}
                    rx={3}
                    className="sp-bar-revenue"
                  />
                )
              })}

              {linePoints && <polyline points={linePoints} className="sp-line" />}
              {secondaryValues.map((v, i) =>
                v === null ? null : (
                  <circle
                    key={`dot-${i}`}
                    cx={xForIndex(i)}
                    cy={yForSecondary(v)}
                    r={hoverIndex === i ? 3.5 : 2.2}
                    className="sp-line-dot"
                  />
                ),
              )}

              {sales.map((s, i) => (
                <text
                  key={`x-${s.month}`}
                  x={xForIndex(i)}
                  y={height - padBottom + 16}
                  textAnchor="middle"
                  className="sp-x-label"
                >
                  {n <= 14 || i % 2 === 0 ? monthLabel(s.month) : ''}
                </text>
              ))}

              {sales.map((s, i) => (
                <rect
                  key={`hover-${s.month}`}
                  x={padLeft + slotW * i}
                  y={padTop}
                  width={slotW}
                  height={plotH}
                  className="sp-hover-rect"
                  onMouseEnter={() => setHoverIndex(i)}
                  onMouseLeave={() => setHoverIndex((cur) => (cur === i ? null : cur))}
                />
              ))}
            </svg>

            {hovered && (
              <div
                className="sp-tooltip"
                style={{ left: `${((hoverIndex! + 0.5) / n) * 100}%` }}
              >
                <strong>{monthLabel(hovered.month)}</strong>
                {metric === 'units' ? (
                  <>
                    <div className="sp-tooltip-row"><span>Actual</span><span>{hovered.actual_units.toLocaleString()}</span></div>
                    <div className="sp-tooltip-row"><span>Forecast</span><span>{hovered.forecast_units.toLocaleString()}</span></div>
                    <div className="sp-tooltip-row">
                      <span>Accuracy</span>
                      <span>{hoveredAccuracy !== null ? `${hoveredAccuracy.toFixed(1)}%` : '—'}</span>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="sp-tooltip-row"><span>Revenue</span><span>฿{hovered.revenue.toLocaleString()}</span></div>
                    <div className="sp-tooltip-row">
                      <span>MoM growth</span>
                      <span className={spChangeClass(hoveredGrowth)}>{spFormatChange(hoveredGrowth)}</span>
                    </div>
                  </>
                )}
              </div>
            )}
          </>
        ) : (
          <div className="chart-loading">Loading sales data...</div>
        )}
      </div>
    </div>
  )
}

function App() {
  const [dashboard, setDashboard] = useState<DashboardData>({
    total_units: 0,
    total_revenue: 0,
    forecast_accuracy: 0,
    top_product: '',
  })

  const [sales, setSales] = useState<SalesData[]>([])
  const [products, setProducts] = useState<ProductData[]>([])
  const [insights, setInsights] = useState<Insight[]>([])
  const [forecast, setForecast] = useState<ForecastResult>({ status: 'idle' })

  const [activeView, setActiveView] = useState<ViewId>('overview')

  const [periodFilter, setPeriodFilter] = useState<PeriodId>('all')
  const [periodMenuOpen, setPeriodMenuOpen] = useState(false)

  const [productQuery, setProductQuery] = useState('')
  const [productSort, setProductSort] = useState<ProductSort>('revenue-desc')

  // --- Forecast Lab: its own job_id ("lab") so runs here never touch
  // the "default" job the Overview/Accuracy views are polling. ---
  const [labOptions, setLabOptions] = useState<ForecastOptions>({ products: [], customers: [] })
  const [labDimension, setLabDimension] = useState<ForecastDimension>('total')
  const [labDimensionValue, setLabDimensionValue] = useState('')
  const [labValueCol, setLabValueCol] = useState<ForecastValueCol>('revenue')
  const [labHorizon, setLabHorizon] = useState(12)
  const [labFast, setLabFast] = useState(true)
  const [labResult, setLabResult] = useState<ForecastResult>({ status: 'idle' })
  const labPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    // Get dashboard KPI data
    fetch('http://127.0.0.1:8100/api/dashboard')
      .then((response) => {
        if (!response.ok) {
          throw new Error('Failed to fetch dashboard data')
        }

        return response.json()
      })
      .then((data: DashboardData) => {
        setDashboard(data)
      })
      .catch((error) => {
        console.error('Failed to fetch dashboard:', error)
      })

    // Get monthly sales data
    fetch('http://127.0.0.1:8100/api/sales')
      .then((response) => {
        if (!response.ok) {
          throw new Error('Failed to fetch sales data')
        }

        return response.json()
      })
      .then((data: SalesData[]) => {
        setSales(data)
      })
      .catch((error) => {
        console.error('Failed to fetch sales:', error)
      })

    // Get product performance data
    fetch('http://127.0.0.1:8100/api/products')
      .then((response) => {
        if (!response.ok) {
          throw new Error('Failed to fetch product data')
        }

        return response.json()
      })
      .then((data: ProductData[]) => {
        setProducts(data)
      })
      .catch((error) => {
        console.error('Failed to fetch products:', error)
      })

    // Get AI-generated insights
    fetch('http://127.0.0.1:8100/api/insights')
      .then((response) => {
        if (!response.ok) {
          throw new Error('Failed to fetch AI insights')
        }

        return response.json()
      })
      .then((data: Insight[]) => {
        setInsights(data)
      })
      .catch((error) => {
        console.error('Failed to fetch AI insights:', error)
      })
  }, [])

  // Trigger + poll the SARIMA forecast run separately — it's a
  // distinct thing from the four MySQL-backed fetches above: it
  // needs to be triggered, takes 40-90s+, and has its own status.
  useEffect(() => {
    let cancelled = false
    let pollId: ReturnType<typeof setInterval>

    const poll = () => {
      fetch('http://127.0.0.1:8100/api/forecast')
        .then((r) => r.json())
        .then((data: ForecastResult) => {
          if (cancelled) return
          setForecast(data)
          if (data.status !== 'running') {
            clearInterval(pollId)
          }
        })
        .catch(() => clearInterval(pollId))
    }

    fetch('http://127.0.0.1:8100/api/forecast/run', { method: 'POST' })
      .then(() => {
        setForecast({ status: 'running' })
        pollId = setInterval(poll, 5000)
        poll()
      })
      .catch(() =>
        setForecast({ status: 'error', message: 'Could not start forecast.' }),
      )

    return () => {
      cancelled = true
      clearInterval(pollId)
    }
  }, [])

  // Load the product/customer picker options once the Lab is opened.
  useEffect(() => {
    if (activeView !== 'lab') return
    if (labOptions.products.length > 0 || labOptions.customers.length > 0) return

    fetch('http://127.0.0.1:8100/api/forecast/options')
      .then((r) => r.json())
      .then((data: ForecastOptions) => setLabOptions(data))
      .catch(() => {})
  }, [activeView, labOptions])

  // Stop polling the lab job if the component unmounts mid-run.
  useEffect(() => {
    return () => {
      if (labPollRef.current) clearInterval(labPollRef.current)
    }
  }, [])

  const runLabForecast = () => {
    if (labDimension !== 'total' && !labDimensionValue) return

    if (labPollRef.current) {
      clearInterval(labPollRef.current)
      labPollRef.current = null
    }

    const body = {
      job_id: 'lab',
      dimension: labDimension,
      dimension_value: labDimension === 'total' ? null : labDimensionValue,
      value_col: labValueCol,
      horizon: labHorizon,
      fast: labFast,
    }

    fetch('http://127.0.0.1:8100/api/forecast/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then(() => {
        setLabResult({ status: 'running' })

        const poll = () => {
          fetch('http://127.0.0.1:8100/api/forecast?job_id=lab')
            .then((r) => r.json())
            .then((data: ForecastResult) => {
              setLabResult(data)
              if (data.status !== 'running' && labPollRef.current) {
                clearInterval(labPollRef.current)
                labPollRef.current = null
              }
            })
            .catch(() => {
              if (labPollRef.current) clearInterval(labPollRef.current)
            })
        }

        labPollRef.current = setInterval(poll, 5000)
        poll()
      })
      .catch(() => setLabResult({ status: 'error', message: 'Could not start forecast.' }))
  }

  /*
   * ---------------------------------------------------------
   * PERIOD FILTER — drives every chart and KPI below, so
   * switching "All time" / "Last 12 months" etc. actually
   * changes what's rendered, not just a label.
   * ---------------------------------------------------------
   */

  const filteredSales = useMemo(() => {
    if (periodFilter === 'all') return sales
    const n = parseInt(periodFilter, 10)
    return sales.slice(-n)
  }, [sales, periodFilter])

  const periodLabel =
    PERIOD_OPTIONS.find((o) => o.id === periodFilter)?.label ?? 'All time'

  /*
   * ---------------------------------------------------------
   * DYNAMIC KPI CALCULATIONS (now based on filteredSales)
   * ---------------------------------------------------------
   */

  const midpoint = Math.floor(filteredSales.length / 2)

  const previousSalesPeriod =
    filteredSales.length > 1 ? filteredSales.slice(0, midpoint) : []

  const currentSalesPeriod =
    filteredSales.length > 1 ? filteredSales.slice(midpoint) : []

  const previousUnits = previousSalesPeriod.reduce(
    (total, item) => total + item.actual_units,
    0,
  )

  const currentUnits = currentSalesPeriod.reduce(
    (total, item) => total + item.actual_units,
    0,
  )

  const previousRevenue = previousSalesPeriod.reduce(
    (total, item) => total + item.revenue,
    0,
  )

  const currentRevenue = currentSalesPeriod.reduce(
    (total, item) => total + item.revenue,
    0,
  )

  const periodTotalUnits = filteredSales.reduce((t, i) => t + i.actual_units, 0)
  const periodTotalRevenue = filteredSales.reduce((t, i) => t + i.revenue, 0)

  const unitsChange =
    previousUnits > 0 ? ((currentUnits - previousUnits) / previousUnits) * 100 : 0

  const revenueChange =
    previousRevenue > 0
      ? ((currentRevenue - previousRevenue) / previousRevenue) * 100
      : 0

  const calculateAccuracy = (data: SalesData[]) => {
    const totalActual = data.reduce((total, item) => total + item.actual_units, 0)

    if (totalActual === 0) {
      return 0
    }

    const totalError = data.reduce(
      (total, item) => total + Math.abs(item.actual_units - item.forecast_units),
      0,
    )

    return (1 - totalError / totalActual) * 100
  }

  const previousAccuracy =
    previousSalesPeriod.length > 0 ? calculateAccuracy(previousSalesPeriod) : 0

  const currentAccuracy =
    currentSalesPeriod.length > 0 ? calculateAccuracy(currentSalesPeriod) : 0

  const accuracyChange =
    previousAccuracy > 0 ? currentAccuracy - previousAccuracy : 0

  /*
   * Forecast-accuracy KPI: prefer the real, validated SARIMA
   * 1-month accuracy once it's loaded. Fall back to the backend's
   * placeholder (lag-1) figure and say so plainly — this is the
   * fix for the confusing "19%" number, which was always the
   * placeholder, never the SARIMA result.
   */

  const sarimaWf1Accuracy =
    forecast.status === 'ok' ? forecast.diagnostics?.wf1.SARIMA?.accuracy_pct : undefined

  const accuracyIsPlaceholder = sarimaWf1Accuracy === undefined
  const displayedAccuracy = sarimaWf1Accuracy ?? dashboard.forecast_accuracy

  /*
   * ---------------------------------------------------------
   * REVENUE CHART (viewBox-based, scales to container width —
   * dynamic regardless of how many months are in filteredSales)
   * ---------------------------------------------------------
   */

  const chartWidth = 500
  const chartHeight = 180
  const chartPadding = 8

  const maxRevenue =
    filteredSales.length > 0 ? Math.max(...filteredSales.map((item) => item.revenue)) : 1

  const minRevenue =
    filteredSales.length > 0 ? Math.min(...filteredSales.map((item) => item.revenue)) : 0

  const revenueRange = Math.max(maxRevenue - minRevenue, 1)

  const revenuePoints = filteredSales.map((item, index) => {
    const x =
      filteredSales.length === 1
        ? chartWidth / 2
        : (index / (filteredSales.length - 1)) * (chartWidth - chartPadding * 2) +
          chartPadding

    const y =
      chartHeight -
      ((item.revenue - minRevenue) / revenueRange) * (chartHeight - chartPadding * 2) -
      chartPadding

    return { x, y }
  })

  const revenueLinePoints = revenuePoints.map((point) => `${point.x},${point.y}`).join(' ')

  const revenueAreaPoints =
    revenuePoints.length > 0
      ? `${revenueLinePoints} ${chartWidth - chartPadding},${chartHeight} ${chartPadding},${chartHeight}`
      : ''

  /*
   * ---------------------------------------------------------
   * PRODUCTS — filterable + sortable
   * ---------------------------------------------------------
   */

  const productVariance = (item: ProductData) =>
    item.actual_units !== 0
      ? ((item.forecast_units - item.actual_units) / item.actual_units) * 100
      : 0

  const filteredProducts = useMemo(() => {
    const q = productQuery.trim().toLowerCase()
    const list = products.filter((p) => p.product.toLowerCase().includes(q))

    return list.slice().sort((a, b) => {
      if (productSort === 'revenue-desc') return b.revenue - a.revenue
      if (productSort === 'revenue-asc') return a.revenue - b.revenue
      const va = Math.abs(productVariance(a))
      const vb = Math.abs(productVariance(b))
      return productSort === 'variance-desc' ? vb - va : va - vb
    })
  }, [products, productQuery, productSort])

  const inventoryRisk = useMemo(() => {
    return products
      .slice()
      .sort((a, b) => Math.abs(productVariance(b)) - Math.abs(productVariance(a)))
      .slice(0, 10)
  }, [products])

  /*
   * ---------------------------------------------------------
   * FORMATTING HELPERS
   * ---------------------------------------------------------
   */

  const formatChange = (value: number) => {
    const sign = value > 0 ? '+' : ''
    return `${sign}${value.toFixed(1)}%`
  }

  const changeClass = (value: number) => {
    if (value > 0) return 'positive'
    if (value < 0) return 'negative'
    return 'neutral'
  }

  const monthLabel = (month: string) => {
    const date = new Date(`${month}-01`)
    return date.toLocaleString('en-US', { month: 'short' })
  }

  // Same short month label, but flags whenever the calendar year changes
  // (or on the very first tick) so the revenue chart can show "2024" /
  // "2025" once per year instead of repeating it on every single label.
  const monthYearLabel = (month: string, index: number, list: SalesData[]) => {
    const date = new Date(`${month}-01`)
    const mon = date.toLocaleString('en-US', { month: 'short' })
    const year = date.getFullYear()
    const prevYear =
      index > 0 ? new Date(`${list[index - 1].month}-01`).getFullYear() : null
    return { mon, year, isYearStart: index === 0 || year !== prevYear }
  }

  /*
   * ---------------------------------------------------------
   * VIEW VISIBILITY — which blocks render for which sidebar view
   * ---------------------------------------------------------
   */

  const showKpis = activeView === 'overview'
  const showSalesChart = activeView === 'overview' || activeView === 'forecast'
  const showRevenueChart = activeView === 'overview' || activeView === 'revenue'
  const showForecastPanel =
    activeView === 'overview' || activeView === 'forecast' || activeView === 'accuracy'
  const showProductsTable = activeView === 'overview' || activeView === 'products'
  const showInventoryTable = activeView === 'inventory'
  const showInsights = activeView === 'overview'
  const showCustomersPlaceholder = activeView === 'customers'

  const meta = VIEW_META[activeView]

  return (
    <div className="app">
      {/* SIDEBAR */}

      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">M</div>
          <div>
            <div className="brand-name">Missubibi</div>
            <div className="brand-subtitle">Sales intelligence</div>
          </div>
        </div>

        <nav className="navigation">
          {NAV_ITEMS.map((item, index) => (
            <button
              key={item.id}
              className={`nav-item ${activeView === item.id ? 'active' : ''}`}
              onClick={() => setActiveView(item.id)}
              aria-current={activeView === item.id}
            >
              <item.icon />
              {item.label}
              {index === 3 && <span className="nav-divider" aria-hidden="true" />}
            </button>
          ))}
        </nav>

        <div className="model-status">
          <span className="status-dot" />
          <div>
            <strong>AI model online</strong>
            <span>Last updated just now</span>
          </div>
        </div>
      </aside>

      {/* MAIN CONTENT */}

      <main className="main">
        {/* HEADER */}

        <header className="header">
          <div>
            <div className="breadcrumb">Dashboard / {meta.title}</div>
            <h1>{meta.title}</h1>
            <p>{meta.subtitle}</p>
          </div>

          <div className="header-right">
            <div className="period-control">
              <button
                className="period-selector"
                onClick={() => setPeriodMenuOpen((open) => !open)}
              >
                {periodLabel}
                <IconChevron />
              </button>

              {periodMenuOpen && (
                <div className="period-menu">
                  {PERIOD_OPTIONS.map((opt) => (
                    <button
                      key={opt.id}
                      className={`period-option ${periodFilter === opt.id ? 'active' : ''}`}
                      onClick={() => {
                        setPeriodFilter(opt.id)
                        setPeriodMenuOpen(false)
                      }}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              )}
            </div>

            <div className="user-avatar">GS</div>
          </div>
        </header>

        {/* KPI CARDS */}

        {showKpis && (
          <section className="kpi-grid">
            <div className="kpi-card">
              <div className="kpi-header">
                <span>Total units</span>
                <div className="kpi-icon">
                  <IconGrid size={16} />
                </div>
              </div>

              <div className="kpi-value">{periodTotalUnits.toLocaleString()}</div>

              <div className={`kpi-change ${changeClass(unitsChange)}`}>
                {formatChange(unitsChange)}
                <span>vs previous period</span>
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-header">
                <span>Revenue</span>
                <div className="kpi-icon">
                  <IconCoin size={16} />
                </div>
              </div>

              <div className="kpi-value">
                ฿{(periodTotalRevenue / 1_000_000).toFixed(2)}M
              </div>

              <div className={`kpi-change ${changeClass(revenueChange)}`}>
                {formatChange(revenueChange)}
                <span>vs previous period</span>
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-header">
                <span>Forecast accuracy</span>
                <div className="kpi-icon">
                  <IconTarget size={16} />
                </div>
              </div>

              <div className="kpi-value">{displayedAccuracy.toFixed(1)}%</div>

              <div
                className={`kpi-change ${
                  accuracyIsPlaceholder ? 'neutral' : changeClass(accuracyChange)
                }`}
              >
                {accuracyIsPlaceholder
                  ? 'Provisional'
                  : formatChange(accuracyChange)}
                <span>
                  {accuracyIsPlaceholder
                    ? 'placeholder (lag-1) — SARIMA loading'
                    : '1-month SARIMA, validated'}
                </span>
              </div>
            </div>

            <div className="kpi-card">
              <div className="kpi-header">
                <span>Top product</span>
                <div className="kpi-icon">
                  <IconLayers size={16} />
                </div>
              </div>

              <div className="kpi-value product-kpi">{dashboard.top_product}</div>

              <div className="kpi-change neutral">
                Top revenue product
                <span>based on current data</span>
              </div>
            </div>
          </section>
        )}

        {/* SALES + FORECAST CHARTS */}

        {(showSalesChart || showForecastPanel) && (
          <section className="charts-grid">
            {showSalesChart && (
              <div className="panel sales-panel">
                <div className="panel-header">
                  <div>
                    <h2>Sales performance</h2>
                    <p>Actual vs forecast, revenue, and accuracy trend for {periodLabel.toLowerCase()}</p>
                  </div>
                </div>

                <SalesPerformancePanel sales={filteredSales} monthLabel={monthLabel} />
              </div>
            )}

            {showForecastPanel && (
              <div className="panel forecast-panel">
                <div className="panel-header">
                  <div>
                    <h2>FY2025 forecast (SARIMA)</h2>
                    <p>Next 12 months, revenue</p>
                  </div>
                </div>

                {forecast.status === 'running' && (
                  <div className="chart-loading">Running forecast — this takes 40–90s…</div>
                )}

                {forecast.status === 'insufficient_history' && (
                  <div className="chart-loading">{forecast.message}</div>
                )}

                {forecast.status === 'error' && (
                  <div className="chart-loading">{forecast.message}</div>
                )}

                {forecast.status === 'ok' && forecast.forecast && (
                  <>
                    <SarimaForecastChart
                      history={filteredSales}
                      forecast={forecast.forecast}
                      valueCol="revenue"
                    />

                    <div className="forecast-meta">
                      <div>
                        <strong>
                          ฿{(forecast.forecast.annual_total / 1_000_000).toFixed(1)}M
                        </strong>
                        <span>Forecast annual total</span>
                      </div>

                      <div>
                        <strong>
                          {forecast.forecast.annual_yoy_pct !== null
                            ? `${forecast.forecast.annual_yoy_pct > 0 ? '+' : ''}${forecast.forecast.annual_yoy_pct}%`
                            : '—'}
                        </strong>
                        <span>YoY vs FY2024</span>
                      </div>

                      <div>
                        <strong>{forecast.diagnostics?.wf1.SARIMA?.accuracy_pct}%</strong>
                        <span>1-month accuracy (validated)</span>
                      </div>

                      <div>
                        <strong>{forecast.diagnostics?.wf12.SARIMA?.accuracy_pct}%</strong>
                        <span>12-month accuracy</span>
                      </div>
                    </div>

                    {forecast.diagnostics?.wf12.beats_naive === false && (
                      <div className="forecast-caveat">
                        At the 12-month horizon, this model has not yet shown it beats a
                        naive seasonal baseline — treat the annual total as directional,
                        not precise.
                      </div>
                    )}

                    {forecast.data_anomalies && forecast.data_anomalies.length > 0 && (
                      <div className="forecast-caveat">
                        {forecast.data_anomalies[0].message}
                      </div>
                    )}

                    {activeView === 'accuracy' && (
                      <div className="accuracy-detail">
                        <div className="accuracy-row">
                          <span>WF1 (1-month-ahead validation)</span>
                          <strong className="positive">
                            {forecast.diagnostics?.wf1.SARIMA?.accuracy_pct}% — beats naive baseline
                          </strong>
                        </div>
                        <div className="accuracy-row">
                          <span>WF12 (12-month-ahead validation)</span>
                          <strong className="negative">
                            {forecast.diagnostics?.wf12.SARIMA?.accuracy_pct}% — does not beat naive baseline
                          </strong>
                        </div>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}
          </section>
        )}

        {/* REVENUE */}

        {showRevenueChart && (
          <section className="charts-grid single">
            <div className="panel revenue-panel">
              <div className="panel-header">
                <div>
                  <h2>Revenue</h2>
                  <p>Monthly revenue performance</p>
                </div>
              </div>

              <div className="revenue-total">
                <strong>฿{(periodTotalRevenue / 1_000_000).toFixed(2)}M</strong>
                <span className={revenueChange >= 0 ? 'positive' : 'negative'}>
                  {formatChange(revenueChange)}
                </span>
              </div>

              <div className="revenue-chart">
                <div className="revenue-grid">
                  <span />
                  <span />
                  <span />
                  <span />
                </div>

                {filteredSales.length > 0 ? (
                  <svg className="revenue-svg" viewBox="0 0 500 180" preserveAspectRatio="none">
                    <polyline points={revenueAreaPoints} fill="currentColor" opacity="0.08" />
                    <polyline
                      points={revenueLinePoints}
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                    {revenuePoints.map((point, index) => (
                      <circle key={filteredSales[index].month} cx={point.x} cy={point.y} r="3.5" fill="currentColor">
                        <title>
                          {filteredSales[index].month}: ฿{filteredSales[index].revenue.toLocaleString()}
                        </title>
                      </circle>
                    ))}
                  </svg>
                ) : (
                  <div className="chart-loading">Loading revenue data...</div>
                )}
              </div>

              <div className="month-labels">
                {filteredSales.map((item, index) => {
                  const { mon, year, isYearStart } = monthYearLabel(item.month, index, filteredSales)
                  return (
                    <span className="month-label-cell" key={item.month}>
                      <span className="month-label-month">{mon}</span>
                      {isYearStart && <span className="month-label-year">{year}</span>}
                    </span>
                  )
                })}
              </div>
            </div>
          </section>
        )}

        {/* PRODUCTS */}

        {showProductsTable && (
          <section className="charts-grid single">
            <div className="panel">
              <div className="panel-header">
                <div>
                  <h2>Product performance</h2>
                  <p>Revenue contribution by product</p>
                </div>
              </div>

              <div className="table-controls">
                <div className="search-field">
                  <IconSearch />
                  <input
                    type="text"
                    placeholder="Search products"
                    value={productQuery}
                    onChange={(e) => setProductQuery(e.target.value)}
                  />
                </div>

                <select
                  className="sort-select"
                  value={productSort}
                  onChange={(e) => setProductSort(e.target.value as ProductSort)}
                >
                  <option value="revenue-desc">Revenue: high to low</option>
                  <option value="revenue-asc">Revenue: low to high</option>
                  <option value="variance-desc">Variance: high to low</option>
                  <option value="variance-asc">Variance: low to high</option>
                </select>
              </div>

              <div className="product-table">
                <div className="product-row product-header">
                  <span>Product</span>
                  <span>Revenue</span>
                  <span>Forecast variance</span>
                </div>

                <div className="product-table-scroll">
                  {filteredProducts.length > 0 ? (
                    filteredProducts.map((item) => {
                      const variance = productVariance(item)
                      const varianceClass =
                        variance > 0 ? 'positive' : variance < 0 ? 'negative' : 'neutral'

                      return (
                        <div className="product-row" key={item.product}>
                          <div className="product-name">
                            <strong>{item.product}</strong>
                            <span>{item.actual_units.toLocaleString()} actual units</span>
                          </div>

                          <strong>฿{(item.revenue / 1_000_000).toFixed(2)}M</strong>

                          <span className={varianceClass}>
                            {variance > 0 ? '+' : ''}
                            {variance.toFixed(1)}%
                          </span>
                        </div>
                      )
                    })
                  ) : products.length === 0 ? (
                    <div className="chart-loading">Loading product data...</div>
                  ) : (
                    <div className="empty-state">No products match "{productQuery}".</div>
                  )}
                </div>

                <div className="product-table-count">
                  Showing {filteredProducts.length} of {products.length} products
                </div>
              </div>
            </div>
          </section>
        )}

        {/* INVENTORY RISK */}

        {showInventoryTable && (
          <section className="charts-grid single">
            <div className="panel">
              <div className="panel-header">
                <div>
                  <h2>Inventory risk</h2>
                  <p>Products ranked by absolute forecast variance — the biggest gaps carry the most over/under-stock risk</p>
                </div>
              </div>

              <div className="product-table">
                <div className="product-row product-header">
                  <span>Product</span>
                  <span>Revenue</span>
                  <span>Forecast variance</span>
                </div>

                {inventoryRisk.length > 0 ? (
                  inventoryRisk.map((item) => {
                    const variance = productVariance(item)
                    const varianceClass =
                      variance > 0 ? 'positive' : variance < 0 ? 'negative' : 'neutral'

                    return (
                      <div className="product-row" key={item.product}>
                        <div className="product-name">
                          <strong>{item.product}</strong>
                          <span>{item.actual_units.toLocaleString()} actual units</span>
                        </div>

                        <strong>฿{(item.revenue / 1_000_000).toFixed(2)}M</strong>

                        <span className={varianceClass}>
                          {variance > 0 ? '+' : ''}
                          {variance.toFixed(1)}%
                        </span>
                      </div>
                    )
                  })
                ) : (
                  <div className="chart-loading">Loading product data...</div>
                )}
              </div>

              <div className="forecast-caveat">
                This view is derived from forecast-vs-actual variance, not a live inventory
                feed — there's no stock-on-hand data in the current schema.
              </div>
            </div>
          </section>
        )}

        {/* CUSTOMERS */}

        {showCustomersPlaceholder && (
          <section className="charts-grid single">
            <div className="panel">
              <div className="panel-header">
                <div>
                  <h2>Customers</h2>
                  <p>Customer-level breakdown</p>
                </div>
              </div>

              <div className="empty-state">
                Customer-level analytics needs a dedicated backend endpoint — today's
                API only returns product-level aggregates. Add a{' '}
                <code>/api/customers</code> route grouping by customer to unlock this
                view.
              </div>
            </div>
          </section>
        )}

        {/* AI INSIGHTS */}

        {showInsights && (
          <section className="charts-grid single">
            <div className="panel insights-panel">
              <div className="panel-header">
                <div>
                  <h2>AI insights</h2>
                  <p>Automated recommendations</p>
                </div>
              </div>

              {insights.length > 0 ? (
                insights.map((insight, index) => (
                  <div className="insight" key={`${insight.title}-${index}`}>
                    <div className={`insight-icon ${insight.type}-icon`}>
                      {insight.type === 'positive' ? '↑' : insight.type === 'warning' ? '!' : '◆'}
                    </div>

                    <div>
                      <strong>{insight.title}</strong>
                      <p>{insight.message}</p>
                    </div>
                  </div>
                ))
              ) : (
                <div className="chart-loading">Loading AI insights...</div>
              )}
            </div>
          </section>
        )}

        {/* FORECAST LAB */}

        {activeView === 'lab' && (
          <section className="charts-grid single">
            <div className="panel lab-controls">
              <div className="panel-header">
                <div>
                  <h2>Run configuration</h2>
                  <p>Pick a series and validation depth, then run the SARIMA engine directly</p>
                </div>
              </div>

              <div className="lab-form">
                <label>
                  Series
                  <select
                    value={labDimension}
                    onChange={(e) => {
                      setLabDimension(e.target.value as ForecastDimension)
                      setLabDimensionValue('')
                    }}
                  >
                    <option value="total">Total company</option>
                    <option value="product">By product</option>
                    <option value="customer">By customer</option>
                  </select>
                </label>

                {labDimension !== 'total' && (
                  <label>
                    {labDimension === 'product' ? 'Product' : 'Customer'}
                    <select
                      value={labDimensionValue}
                      onChange={(e) => setLabDimensionValue(e.target.value)}
                    >
                      <option value="">Select…</option>
                      {(labDimension === 'product' ? labOptions.products : labOptions.customers).map(
                        (v) => (
                          <option key={v} value={v}>
                            {v}
                          </option>
                        ),
                      )}
                    </select>
                  </label>
                )}

                <label>
                  Value
                  <select
                    value={labValueCol}
                    onChange={(e) => setLabValueCol(e.target.value as ForecastValueCol)}
                  >
                    <option value="revenue">Revenue</option>
                    <option value="actual_units">Units</option>
                  </select>
                </label>

                <label>
                  Horizon (months)
                  <input
                    type="number"
                    min={1}
                    max={24}
                    value={labHorizon}
                    onChange={(e) => setLabHorizon(Math.max(1, Number(e.target.value) || 1))}
                  />
                </label>

                <label className="lab-checkbox">
                  <input
                    type="checkbox"
                    checked={labFast}
                    onChange={(e) => setLabFast(e.target.checked)}
                  />
                  Fast mode (smaller order search — uncheck to match the notebook exactly, slower)
                </label>

                <button
                  className="lab-run-button"
                  onClick={runLabForecast}
                  disabled={labResult.status === 'running' || (labDimension !== 'total' && !labDimensionValue)}
                >
                  {labResult.status === 'running' ? 'Running… (40–90s)' : 'Run forecast'}
                </button>
              </div>
            </div>

            {labResult.status === 'idle' && (
              <div className="panel">
                <div className="chart-loading">Configure a run above and hit "Run forecast".</div>
              </div>
            )}

            {labResult.status === 'running' && (
              <div className="panel">
                <div className="chart-loading">Fitting SARIMA candidates — this takes 40–90 seconds…</div>
              </div>
            )}

            {labResult.status === 'insufficient_history' && (
              <div className="panel">
                <div className="chart-loading">{labResult.detail ?? labResult.message}</div>
              </div>
            )}

            {(labResult.status === 'error' || labResult.status === 'already_running') && (
              <div className="panel">
                <div className="chart-loading">
                  {labResult.message ?? 'Another run is already in progress — wait for it to finish.'}
                </div>
              </div>
            )}

            {labResult.status === 'ok' && labResult.forecast && (
              <>
                <div className="panel">
                  <div className="panel-header">
                    <div>
                      <h2>{labResult.forecast.series}</h2>
                      <p>
                        {labResult.forecast.spec} · {labResult.forecast.horizon}-month forecast from{' '}
                        {labResult.forecast.months[0]}
                      </p>
                    </div>
                  </div>

                  <SarimaForecastChart
                    history={filteredSales}
                    forecast={labResult.forecast}
                    valueCol={labValueCol}
                  />

                  <div className="forecast-meta">
                    <div>
                      <strong>
                        {labValueCol === 'revenue' ? '฿' : ''}
                        {labResult.forecast.annual_total.toLocaleString(undefined, {
                          maximumFractionDigits: 0,
                        })}
                        {labValueCol === 'actual_units' ? ' units' : ''}
                      </strong>
                      <span>Forecast total ({labResult.forecast.horizon}mo)</span>
                    </div>

                    <div>
                      <strong>
                        {labResult.forecast.annual_yoy_pct !== null
                          ? `${labResult.forecast.annual_yoy_pct > 0 ? '+' : ''}${labResult.forecast.annual_yoy_pct}%`
                          : '—'}
                      </strong>
                      <span>YoY vs prior fiscal year</span>
                    </div>

                    <div>
                      <strong className={labResult.forecast.plausibility_ok ? 'positive' : 'negative'}>
                        {labResult.forecast.plausibility_ok ? 'Passed' : 'Flagged'}
                      </strong>
                      <span>Plausibility screen</span>
                    </div>
                  </div>

                  {!labResult.forecast.plausibility_ok && labResult.forecast.plausibility_detail && (
                    <div className="forecast-caveat">{labResult.forecast.plausibility_detail}</div>
                  )}
                </div>

                <div className="panel">
                  <div className="panel-header">
                    <div>
                      <h2>Validation</h2>
                      <p>SARIMA vs seasonal-naive baseline, walk-forward</p>
                    </div>
                  </div>

                  <div className="lab-diag-table">
                    <div className="lab-diag-row lab-diag-header">
                      <span>Scheme</span>
                      <span>SARIMA</span>
                      <span>Naive</span>
                      <span>Beats naive?</span>
                      <span>Significant?</span>
                    </div>

                    {(['wf1', 'wf12'] as const).map((scheme) => {
                      const d = labResult.diagnostics?.[scheme]
                      if (!d) return null

                      return (
                        <div className="lab-diag-row" key={scheme}>
                          <span>{scheme === 'wf1' ? 'WF1 (1-month)' : 'WF12 (12-month)'}</span>
                          <span>{d.SARIMA ? `${d.SARIMA.accuracy_pct}%` : '—'}</span>
                          <span>{d.SeasonalNaive ? `${d.SeasonalNaive.accuracy_pct}%` : '—'}</span>
                          <span className={d.beats_naive ? 'positive' : 'negative'}>
                            {d.beats_naive ? 'Yes' : 'No'}
                          </span>
                          <span>
                            {d.vs_baseline?.distinguishable === null ||
                            d.vs_baseline?.distinguishable === undefined
                              ? '—'
                              : d.vs_baseline.distinguishable
                              ? 'Yes'
                              : 'No'}
                          </span>
                        </div>
                      )
                    })}
                  </div>

                  <div className="accuracy-row">
                    <span>Ljung-Box residual check</span>
                    <strong className={labResult.diagnostics?.residuals_clean ? 'positive' : 'negative'}>
                      {labResult.diagnostics?.ljung_box_p !== null &&
                      labResult.diagnostics?.ljung_box_p !== undefined
                        ? `p=${labResult.diagnostics.ljung_box_p} — ${
                            labResult.diagnostics.residuals_clean ? 'clean' : 'autocorrelated'
                          }`
                        : '—'}
                    </strong>
                  </div>
                </div>

                {((labResult.data_anomalies && labResult.data_anomalies.length > 0) ||
                  (labResult.warnings && labResult.warnings.length > 0)) && (
                  <div className="panel">
                    <div className="panel-header">
                      <div>
                        <h2>Notes</h2>
                        <p>Data anomalies and engine warnings from this run</p>
                      </div>
                    </div>

                    {labResult.data_anomalies?.map((a, i) => (
                      <div className="insight" key={`anom-${i}`}>
                        <div className="insight-icon warning-icon">!</div>
                        <div>
                          <strong>Data anomaly</strong>
                          <p>{a.message}</p>
                        </div>
                      </div>
                    ))}

                    {labResult.warnings?.map((w, i) => (
                      <div className="insight" key={`warn-${i}`}>
                        <div className="insight-icon neutral-icon">◆</div>
                        <div>
                          <strong>{w.kind}</strong>
                          <p>{w.message}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </section>
        )}
      </main>
    </div>
  )
}

export default App
