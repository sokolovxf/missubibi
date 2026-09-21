import { useEffect, useMemo, useRef, useState } from "react";
import "./App.css";
import CsvImport from "./CsvImport";

type Row = { month: string; value: number };
type Curve = {
  months: string[];
  point: number[];
  lower_90: number[];
  upper_90: number[];
  spec: string;
  interval_source?: string;
};
type Member = {
  status: string;
  message?: string;
  forecast?: Curve;
  validation?: {
    accuracy_pct?: number | null;
    wape_pct?: number | null;
    mase: number | null;
    mae: number | null;
    folds: number;
    horizon: number;
    protocol_version?: string;
    history_points?: number;
    history_start?: string;
    history_end?: string;
    data_fingerprint?: string;
    reproducible?: boolean;
    fold_summary?: {
      test_start: string;
      test_end: string;
      horizon: number;
      wape_pct?: number | null;
    }[];
  };
};
type Result = Member & {
  history?: Row[];
  members?: Record<string, Member>;
  weights?: Record<string, number>;
  weight_method?: string;
  allocation_note?: string;
  data_fingerprint?: string;
  diagnostics?: { holdout_mae?: number; mase?: number };
  params?: { model: string; value_col: string; granularity: string };
  warnings?: { message: string }[];
};
type Options = { dimensions: Record<string, string[]> };
type InventoryRow = {
  dimension: string;
  key: string;
  item: string | null;
  vendor: string | null;
  recent_avg_units: number;
  annual_avg_units: number;
  run_rate_units_per_month: number;
  trend_pct: number | null;
  lead_time_demand_units: number;
  safety_stock_units: number;
  reorder_point_units: number;
  target_stock_units: number;
  on_hand_units: number;
  suggested_order_units: number;
  lead_time_days: number;
  on_hand_source?: string;
  lead_time_source?: string;
  days_of_cover: number | null;
  order_by_date: string;
  expected_arrival_date: string;
  status: string;
  months_with_source_data: number;
};
type InventoryPlan = {
  status: string;
  rows: InventoryRow[];
  source_as_of: string | null;
  planning_as_of: string | null;
  planning_start: string | null;
  source_rows: number;
  total_groups: number;
  vendor_mapping_available: boolean;
  assumptions: {
    lead_time_days: number;
    safety_stock_months: number;
    coverage_months: number;
    on_hand_default_units: number;
    run_rate_method: string;
    source_note: string;
  };
};
const models = [
  { id: "ensemble", name: "Ensemble", desc: "Validation-weighted blend" },
  { id: "sarima", name: "SARIMA", desc: "Seasonal statistical model" },
  {
    id: "randomforest",
    name: "Random Forest",
    desc: "Nonlinear demand patterns",
  },
  { id: "lstm", name: "LSTM", desc: "Sequential neural network" },
  { id: "xgboost", name: "XGBoost", desc: "Gradient-boosted trees" },
  { id: "trend", name: "Trend", desc: "Interpretable baseline" },
];
const grains = ["daily", "weekly", "monthly", "quarterly", "yearly"];
const titles: Record<string, string> = {
  total: "Company",
  item: "Item / SKU",
  product: "Product category",
  customer: "Customer",
  industry: "Industry",
  vendor: "Vendor",
};
const compact = (n: number) =>
  new Intl.NumberFormat("en", {
    notation: "compact",
    maximumFractionDigits: 1,
  }).format(n);
const date = (s: string) =>
  new Date(s + "T00:00:00").toLocaleDateString("en-GB", {
    month: "short",
    year: "2-digit",
    day: "numeric",
  });
async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch("/api/planning" + path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === "string"
        ? body.detail
        : `Request failed (${response.status}). Check the selected filters and server connection.`,
    );
  }
  return response.json();
}
function Mark() {
  return (
    <svg viewBox="0 0 60 54" aria-hidden="true">
      <path
        d="M30 0 40 18 30 36 20 18ZM30 36 20 54 0 54 10 36ZM30 36 50 36 60 54 40 54Z"
        fill="currentColor"
      />
    </svg>
  );
}
function Spark({ values }: { values: number[] }) {
  if (!values.length) return <span className="muted">—</span>;
  const min = Math.min(...values),
    span = Math.max(...values) - min || 1;
  return (
    <svg className="spark" viewBox="0 0 120 32" aria-hidden="true">
      <polyline
        points={values
          .map(
            (v, i) =>
              `${(i * 120) / Math.max(1, values.length - 1)},${29 - ((v - min) / span) * 26}`,
          )
          .join(" ")}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
      />
    </svg>
  );
}
function ForecastChart({
  history,
  forecast,
  scenario,
  onChange,
  unit,
}: {
  history: Row[];
  forecast?: Curve;
  scenario: number[];
  onChange: (v: number[]) => void;
  unit: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const svg = useRef<SVGSVGElement>(null);
  const drag = useRef<number | null>(null);
  const [dragMax, setDragMax] = useState<number | null>(null);
  const hist = history.slice(-36),
    points = forecast?.point || [],
    all = [...hist.map((r) => r.value), ...points];
  const width = 1060,
    height = 340,
    left = 65,
    right = 25,
    top = 28,
    bottom = 48;
  const max =
    dragMax ??
    Math.max(1, ...all, ...(forecast?.upper_90 || []), ...scenario) * 1.15;
  const x = (i: number) =>
    left + (i * (width - left - right)) / Math.max(1, all.length - 1);
  const y = (v: number) =>
    height - bottom - (v / max) * (height - top - bottom);
  const path = (values: number[], start = 0) =>
    values.map((v, i) => `${i ? "L" : "M"}${x(start + i)},${y(v)}`).join(" ");
  const join = (v: number[]) =>
    hist.length ? [hist[hist.length - 1].value, ...v] : v;
  const start = Math.max(0, hist.length - 1);
  const band = forecast
    ? [
        ...forecast.upper_90.map((v, i) => `${x(hist.length + i)},${y(v)}`),
        ...forecast.lower_90
          .map((v, i) => `${x(hist.length + i)},${y(v)}`)
          .reverse(),
      ].join(" ")
    : "";
  const active =
    hover === null
      ? null
      : hover < hist.length
        ? hist[hover]
        : {
            month: forecast?.months[hover - hist.length] || "",
            value: scenario[hover - hist.length] ?? points[hover - hist.length],
          };
  return (
    <div className="chart-wrap">
      <svg
        ref={svg}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="Historical sales and forecast with prediction range. Use scenario controls below or drag forecast points."
        onPointerMove={(e) => {
          const box = svg.current!.getBoundingClientRect();
          const sx = ((e.clientX - box.left) / box.width) * width;
          setHover(
            Math.max(
              0,
              Math.min(
                all.length - 1,
                Math.round(
                  ((sx - left) / (width - left - right)) *
                    Math.max(1, all.length - 1),
                ),
              ),
            ),
          );
          if (drag.current !== null) {
            const sy = ((e.clientY - box.top) / box.height) * height;
            const next = [...scenario];
            next[drag.current] = Math.max(
              0,
              ((height - bottom - sy) / (height - top - bottom)) * max,
            );
            onChange(next);
          }
        }}
        onPointerUp={() => {
          drag.current = null;
          setDragMax(null);
        }}
        onPointerCancel={() => {
          drag.current = null;
          setDragMax(null);
        }}
        onPointerLeave={() => {
          if (drag.current === null) setHover(null);
        }}
      >
        <defs>
          <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#687b83" stopOpacity=".12" />
            <stop offset="1" stopColor="#687b83" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line
              x1={left}
              x2={width - right}
              y1={y(max * t)}
              y2={y(max * t)}
              stroke="#e8ebed"
              strokeDasharray={t ? "3 5" : undefined}
            />
            <text x={left - 12} y={y(max * t) + 4} textAnchor="end">
              {compact(max * t)}
            </text>
          </g>
        ))}
        {hist.length > 0 && (
          <>
            <path
              d={`${path(hist.map((r) => r.value))} L${x(hist.length - 1)},${y(0)} L${left},${y(0)} Z`}
              fill="url(#area)"
            />
            <path
              d={path(hist.map((r) => r.value))}
              fill="none"
              stroke="#455e68"
              strokeWidth="2.3"
            />
          </>
        )}
        {forecast && (
          <>
            <rect
              x={x(start)}
              y={top}
              width={width - right - x(start)}
              height={height - bottom - top}
              fill="#e54a4a"
              opacity=".025"
            />
            <polygon points={band} fill="#e7c6c8" opacity=".45" />
            <line
              x1={x(start)}
              x2={x(start)}
              y1={top}
              y2={height - bottom}
              stroke="#c6b3b4"
              strokeDasharray="4 5"
            />
            <text x={x(start) + 10} y={top + 12} className="forecast-label">
              FORECAST
            </text>
            <path
              d={path(join(points), start)}
              fill="none"
              stroke="#bd333d"
              strokeWidth="2.2"
              strokeDasharray="5 4"
            />
            <path
              d={path(join(scenario), start)}
              fill="none"
              stroke="#bd333d"
              strokeWidth="2"
            />
            {scenario.map((v, i) => (
              <circle
                key={i}
                cx={x(hist.length + i)}
                cy={y(v)}
                r="4"
                fill="white"
                stroke="#bd333d"
                strokeWidth="2"
                className="drag-point"
                onPointerDown={(e) => {
                  drag.current = i;
                  setDragMax(max);
                  e.currentTarget.setPointerCapture(e.pointerId);
                }}
              >
                <title>
                  {date(forecast.months[i])}: {compact(v)} — drag to adjust
                  scenario
                </title>
              </circle>
            ))}
          </>
        )}
        {all.map(
          (_, i) =>
            i % Math.max(1, Math.ceil(all.length / 8)) === 0 && (
              <text key={i} x={x(i)} y={height - 17} textAnchor="middle">
                {date(
                  i < hist.length
                    ? hist[i].month
                    : forecast!.months[i - hist.length],
                )}
              </text>
            ),
        )}
        {active && hover !== null && (
          <g>
            <line
              x1={x(hover)}
              x2={x(hover)}
              y1={top}
              y2={height - bottom}
              stroke="#a4aeb1"
            />
            <rect
              x={Math.min(width - 190, Math.max(left, x(hover) - 75))}
              y="1"
              width="180"
              height="25"
              rx="4"
              fill="#26363d"
            />
            <text
              x={Math.min(width - 100, Math.max(left + 90, x(hover) + 15))}
              y="18"
              textAnchor="middle"
              fill="white"
              style={{ fill: "white" }}
            >
              {date(active.month)} · {unit}
              {compact(active.value)}
            </text>
          </g>
        )}
      </svg>
      {!history.length && (
        <div className="chart-empty">
          Run a forecast to explore your sales history and outlook.
        </div>
      )}
    </div>
  );
}
export default function App() {
  const [view, setView] = useState("forecast"),
    [options, setOptions] = useState<Options | null>(null),
    [error, setError] = useState("");
  const [dimension, setDimension] = useState("total"),
    [value, setValue] = useState(""),
    [filters, setFilters] = useState<Record<string, string>>({});
  const [granularity, setGranularity] = useState("monthly"),
    [calendar, setCalendar] = useState("calendar"),
    [nativeHistory, setNativeHistory] = useState(false),
    [useClassifierSignals, setUseClassifierSignals] = useState(false),
    [metric, setMetric] = useState("revenue"),
    [horizon, setHorizon] = useState(12),
    [model, setModel] = useState("trend");
  const [history, setHistory] = useState<Row[]>([]),
    [result, setResult] = useState<Result | null>(null),
    [busy, setBusy] = useState(false),
    [scenario, setScenario] = useState<number[]>([]),
    [adjust, setAdjust] = useState<number | null>(0);
  const [classifierItem, setClassifierItem] = useState(""),
    [classifierBusy, setClassifierBusy] = useState(false);
  const [classifierResults, setClassifierResults] = useState<
    {
      status: string;
      model: string;
      message?: string;
      diagnostics?: Record<string, unknown>;
      predictions: {
        item: string;
        probability: number;
        review: boolean;
        label: boolean;
      }[];
    }[]
  >([]);
  const [search, setSearch] = useState(""),
    [showFilters, setShowFilters] = useState(false),
    [classifier, setClassifier] = useState<{
      message: string;
      training?: {
        status: string;
        stage?: string;
        model?: string;
        epoch?: number;
        epochs?: number;
        message?: string;
      };
      models: {
        id: string;
        name: string;
        target: string;
        status: string;
        items?: number;
        prediction_month?: string;
        diagnostics?: {
          accuracy_pct: number;
          auc: number;
          f1: number;
          persistence_accuracy_pct: number;
          test_rows: number;
        };
      }[];
    } | null>(null);
  const [importOpen, setImportOpen] = useState(false);
  const [training, setTraining] = useState<{
    status: string;
    stage?: string;
    model?: string;
    epoch?: number;
    epochs?: number;
    message?: string;
  }>({ status: "idle" });
  const [trainingFast, setTrainingFast] = useState(true);
  const [reviewOnly, setReviewOnly] = useState(false);
  const [inventory, setInventory] = useState<InventoryPlan | null>(null);
  const [inventoryLoading, setInventoryLoading] = useState(false);
  const [inventorySettings, setInventorySettings] = useState({
    leadTimeDays: 30,
    safetyStockMonths: 1,
    coverageMonths: 2,
  });
  const [inventoryOnHand, setInventoryOnHand] = useState<Record<string, number>>({});
  const request = useRef(0);
  useEffect(() => {
    const controller = new AbortController();
    api<Options>("/options", { signal: controller.signal })
      .then(setOptions)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    api<Row[]>("/history", { signal: controller.signal })
      .then(setHistory)
      .catch(() => {});
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (view === "demand")
      api<typeof classifier>("/classifiers")
        .then((data) => {
          setClassifier(data);
          if (data?.training) setTraining(data.training);
        })
        .catch((e) => setError(e.message));
  }, [view]);
  useEffect(() => {
    if (!nativeHistory || !["daily", "weekly"].includes(granularity)) return;
    const controller = new AbortController();
    const params = new URLSearchParams({
      dimension,
      value_col: metric,
      granularity,
      native: "true",
    });
    if (dimension !== "total" && value) params.set("dimension_value", value);
    api<Row[]>(`/history?${params}`, { signal: controller.signal })
      .then(setHistory)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, [nativeHistory, granularity, dimension, value, metric]);
  async function loadInventory() {
    setInventoryLoading(true);
    try {
      const query = new URLSearchParams({
        lead_time_days: String(inventorySettings.leadTimeDays),
        safety_stock_months: String(inventorySettings.safetyStockMonths),
        coverage_months: String(inventorySettings.coverageMonths),
        limit: "40",
        dimension: "item",
      });
      const data = await api<InventoryPlan>(`/inventory/lead-time?${query}`);
      setInventory(data);
      setInventoryOnHand((previous) => {
        const next = { ...previous };
        data.rows.forEach((row) => {
          if (next[row.key] == null) next[row.key] = row.on_hand_units;
        });
        return next;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Inventory planning failed");
    } finally {
      setInventoryLoading(false);
    }
  }
  useEffect(() => {
    if (view !== "inventory") return;
    const timer = window.setTimeout(() => void loadInventory(), 0);
    return () => window.clearTimeout(timer);
    // Settings are applied with the button so planners can edit all assumptions together.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view]);
  useEffect(
    () => () => {
      request.current++;
    },
    [],
  );
  useEffect(() => {
    if (training.status !== "running") return;
    const timer = setInterval(() => {
      api<typeof training>("/classifier/training")
        .then(async (status) => {
          setTraining(status);
          if (status.status === "done") {
            const data = await api<typeof classifier>("/classifiers");
            setClassifier(data);
          }
        })
        .catch((e) => {
          setError(e.message);
          setTraining({ status: "error", message: e.message });
        });
    }, 3000);
    return () => clearInterval(timer);
  }, [training.status]);
  async function trainClassifiers() {
    try {
      setTraining(
        await api<typeof training>("/classifier/train", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ fast: trainingFast }),
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Training could not start");
    }
  }
  async function refreshData() {
    setResult(null);
    setScenario([]);
    setClassifierResults([]);
    setDimension("total");
    setValue("");
    setFilters({});
    try {
      setOptions(await api<Options>("/options"));
      setHistory(await api<Row[]>("/history"));
      setClassifier(await api<typeof classifier>("/classifiers"));
      if (view === "inventory") await loadInventory();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Refresh failed");
    }
  }
  const maxHorizon =
    granularity === "yearly" ? 10 : granularity === "quarterly" ? 40 : 60;
  const unit =
    (result?.params?.value_col || "revenue") === "revenue" ? "฿" : "";
  const shownHistory = nativeHistory ? history : result?.history || history;
  const total = shownHistory.reduce((s, r) => s + r.value, 0),
    projected = scenario.reduce((s, v) => s + v, 0);
  const base = useMemo(() => result?.forecast?.point || [], [result]);
  const scenarioFit = useMemo(() => {
    if (!result?.forecast || !base.length || scenario.length !== base.length)
      return null;
    const { lower_90: lower, upper_90: upper } = result.forecast;
    const scores = base.map((value, index) => {
      const range = Math.max(upper[index] - lower[index], Math.abs(value) * 0.1, 1);
      const movement = Math.abs(scenario[index] - value) / range;
      return Math.max(0, 100 - movement * 35);
    });
    return scores.reduce((sum, value) => sum + value, 0) / scores.length;
  }, [base, result, scenario]);
  const delta = base.reduce((s, v) => s + v, 0)
    ? (projected / base.reduce((s, v) => s + v, 0) - 1) * 100
    : 0;
  const selectedValues = (options?.dimensions[dimension] || []).filter((v) =>
    v.toLowerCase().includes(search.toLowerCase()),
  );
  const comparison = useMemo(
    () =>
      result?.members ||
      (result ? { [result.params?.model || model]: result } : {}),
    [result, model],
  );
  const inventoryRows = useMemo(
    () =>
      (inventory?.rows || []).map((row) => {
        const onHand = Math.max(0, inventoryOnHand[row.key] ?? row.on_hand_units);
        const suggested = Math.max(0, row.target_stock_units - onHand);
        const daysCover = row.run_rate_units_per_month > 0
          ? (onHand / row.run_rate_units_per_month) * 30.4375
          : null;
        return {
          ...row,
          on_hand_units: onHand,
          suggested_order_units: suggested,
          days_of_cover: daysCover,
          status: onHand <= row.reorder_point_units ? "Order now" : "Covered",
        };
      }),
    [inventory, inventoryOnHand],
  );
  function updateScenario(next: number[]) {
    setScenario(next);
    setAdjust(null);
  }
  async function run() {
    const id = ++request.current;
    setBusy(true);
    setError("");
    setResult(null);
    setScenario([]);
    setAdjust(0);
    try {
      const job = await api<{ job_id: string }>("/forecast/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model,
          dimension,
          dimension_value: value || null,
          filters,
          value_col: metric,
          granularity,
          calendar,
          use_classifier_signals: useClassifierSignals,
          horizon,
          fast: true,
        }),
      });
      while (id === request.current) {
        const data = await api<Result>("/forecast/" + job.job_id);
        if (id !== request.current) return;
        if (data.status === "running") {
          await new Promise((r) => setTimeout(r, 2000));
          continue;
        }
        if (data.status !== "ok")
          throw new Error(
            data.message ||
              "This series does not have enough history for the selected model.",
          );
        setResult(data);
        setScenario(data.forecast?.point || []);
        return;
      }
    } catch (e) {
      if (id === request.current)
        setError(e instanceof Error ? e.message : "Forecast failed");
    } finally {
      if (id === request.current) setBusy(false);
    }
  }
  async function predictDemand() {
    setClassifierBusy(true);
    setError("");
    try {
      const values = await Promise.all(
        ["nn", "tr"].map((kind) =>
          api<(typeof classifierResults)[number]>(
            "/classifier/" + kind + "/predict",
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ item: classifierItem || null }),
            },
          ),
        ),
      );
      setClassifierResults(values);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Classification failed");
    } finally {
      setClassifierBusy(false);
    }
  }
  function exportCsv() {
    if (!result?.forecast) return;
    const f = result.forecast;
    const csv = [
      "period,model_forecast,scenario,lower_90,upper_90",
      ...f.months.map((m, i) =>
        [m, f.point[i], scenario[i], f.lower_90[i], f.upper_90[i]].join(","),
      ),
    ].join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "mitsubishi-forecast.csv";
    link.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div className="workspace">
      <aside className="sidebar">
        <div className="brand">
          <Mark />
          <div>
            MITSUBISHI
            <br />
            <b>ELECTRIC</b>
            <small>Changes for the Better</small>
          </div>
        </div>
        <div className="workspace-label">
          SALES INTELLIGENCE <span>TH</span>
        </div>
        <nav aria-label="Main navigation">
          {[
            ["forecast", "◈", "Forecast workspace"],
            ["models", "≋", "Model performance"],
            ["demand", "▦", "Demand classifier"],
            ["inventory", "◷", "Lead-time inventory"],
            ["data", "▤", "Data & coverage"],
          ].map(([id, icon, label]) => (
            <button
              key={id}
              aria-label={label}
              title={label}
              className={view === id ? "active" : ""}
              onClick={() => setView(id)}
            >
              <span>{icon}</span>
              {label}
              {id === "forecast" && <i />}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <span className="small-label">PLANNING ENVIRONMENT</span>
          <strong>Thailand · Factory automation</strong>
          <p>Sales forecasts grounded in your MySQL order history.</p>
        </div>
        <div className="profile">
          <div>ME</div>
          <span>
            Planning team<small>Mitsubishi Electric</small>
          </span>
          <span>⌄</span>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <span>
            Sales intelligence <b>/</b>{" "}
            {view === "forecast"
              ? "Forecast workspace"
              : view === "models"
                ? "Model performance"
                : view === "demand"
                  ? "Demand classifier"
                  : view === "inventory"
                    ? "Lead-time inventory"
                    : "Data & coverage"}
          </span>
          <span className="connection">
            <i className={options ? "connected" : ""} />
            {options ? "MySQL connected" : "Connecting to MySQL"}
          </span>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="eyebrow">DEMAND PLANNING / THAILAND</div>
              <h1>
                {view === "forecast"
                  ? "A clearer view of what’s next."
                  : view === "models"
                    ? "Understand every forecast."
                    : view === "demand"
                      ? "Demand, at the item level."
                      : view === "inventory"
                        ? "Plan the gap between demand and arrival."
                        : "Know the data behind the plan."}
              </h1>
              <p>
                {view === "forecast"
                  ? "Explore sales patterns, compare models, and shape your next planning cycle."
                  : view === "models"
                    ? "Review model availability, chronological validation, and ensemble contributions."
                    : view === "demand"
                      ? "Separate high-demand classification from the probability of an item selling."
                      : view === "inventory"
                        ? "Translate SQL demand history into lead-time demand, safety stock, reorder points, and arrival dates."
                        : "Source coverage, planning assumptions, and available dimensions."}
              </p>
            </div>
            <div className="heading-actions">
              <button
                className="secondary"
                disabled={busy}
                onClick={() => setImportOpen(true)}
              >
                ↑ Import CSV
              </button>
              <button
                className="secondary export"
                onClick={exportCsv}
                disabled={!result?.forecast}
              >
                ↗ Export forecast
              </button>
            </div>
          </div>
          {importOpen && (
            <CsvImport
              onClose={() => setImportOpen(false)}
              onImported={refreshData}
            />
          )}
          {error && (
            <div className="error" role="alert">
              {error}
              <button onClick={() => setError("")} aria-label="Dismiss error">
                ×
              </button>
            </div>
          )}
          {view === "forecast" && (
            <>
              <section
                className="controls panel"
                aria-label="Forecast controls"
              >
                <div className="control">
                  <label htmlFor="dimension">Forecast by</label>
                  <select
                    id="dimension"
                    value={dimension}
                    disabled={busy}
                    onChange={(e) => {
                      setDimension(e.target.value);
                      setValue("");
                      setSearch("");
                    }}
                  >
                    {Object.entries(titles).map(([id, label]) => (
                      <option
                        key={id}
                        value={id}
                        disabled={
                          id === "vendor" && !options?.dimensions.vendor.length
                        }
                      >
                        {label}
                        {id === "vendor" && !options?.dimensions.vendor.length
                          ? " · no mapping"
                          : ""}
                      </option>
                    ))}
                  </select>
                </div>
                {dimension !== "total" && (
                  <div className="control selection">
                    <label htmlFor="value">
                      Select {titles[dimension].toLowerCase()}
                    </label>
                    <input
                      aria-label="Search dimension values"
                      placeholder="Search…"
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                    />
                    <select
                      id="value"
                      value={value}
                      disabled={busy}
                      onChange={(e) => setValue(e.target.value)}
                    >
                      <option value="">Choose a value</option>
                      {selectedValues.map((v) => (
                        <option key={v}>{v}</option>
                      ))}
                    </select>
                  </div>
                )}
                <div className="control">
                  <label htmlFor="metric">Measure</label>
                  <select
                    id="metric"
                    value={metric}
                    disabled={busy}
                    onChange={(e) => setMetric(e.target.value)}
                  >
                    <option value="revenue">Revenue · THB</option>
                    <option value="actual_units">Sales volume · units</option>
                  </select>
                </div>
                <div className="control">
                  <label htmlFor="grain">Frequency</label>
                  <select
                    id="grain"
                    value={granularity}
                    disabled={busy}
                    onChange={(e) => {
                      const next = e.target.value;
                      setGranularity(next);
                      setNativeHistory(false);
                      setHorizon(next === "yearly" ? 3 : 12);
                    }}
                  >
                    {grains.map((g) => (
                      <option key={g}>{g}</option>
                    ))}
                  </select>
                </div>
                <div className="control">
                  <label htmlFor="calendar">Calendar</label>
                  <select
                    id="calendar"
                    value={calendar}
                    disabled={busy}
                    onChange={(e) => setCalendar(e.target.value)}
                  >
                    <option value="calendar">Calendar year</option>
                    <option value="fiscal_apr">Fiscal year · Apr–Mar</option>
                  </select>
                </div>
                {(granularity === "daily" || granularity === "weekly") && (
                  <label className="native-toggle">
                    <input
                      type="checkbox"
                      checked={nativeHistory}
                      onChange={(e) => setNativeHistory(e.target.checked)}
                    />
                    Observed transaction dates
                  </label>
                )}
                <div className="control horizon">
                  <label htmlFor="horizon">
                    Horizon <b>{horizon} periods</b>
                  </label>
                  <input
                    id="horizon"
                    type="range"
                    min="1"
                    max={maxHorizon}
                    value={horizon}
                    disabled={busy}
                    onChange={(e) => setHorizon(+e.target.value)}
                    onPointerUp={() => {
                      if (result && !busy) void run();
                    }}
                    onKeyUp={(e) => {
                      if (
                        result &&
                        !busy &&
                        ["ArrowLeft", "ArrowRight", "Home", "End"].includes(
                          e.key,
                        )
                      )
                        void run();
                    }}
                  />
                </div>
                <button
                  className="filter-button"
                  onClick={() => setShowFilters(!showFilters)}
                  aria-expanded={showFilters}
                >
                  ☷ Filters{" "}
                  {Object.values(filters).filter(Boolean).length || ""}
                </button>
                <button
                  className="primary"
                  disabled={
                    busy || !options || (dimension !== "total" && !value)
                  }
                  onClick={run}
                >
                  {busy ? "Calculating…" : "Run forecast"} <span>↗</span>
                </button>
                {showFilters && (
                  <div className="filter-row">
                    {["item", "customer", "industry", "vendor"].map((d) => (
                      <label key={d}>
                        {titles[d]}
                        <select
                          value={filters[d] || ""}
                          disabled={busy || !options?.dimensions[d]?.length}
                          onChange={(e) =>
                            setFilters({ ...filters, [d]: e.target.value })
                          }
                        >
                          <option value="">
                            All {titles[d].toLowerCase()}s
                          </option>
                          {options?.dimensions[d]?.map((v) => (
                            <option key={v}>{v}</option>
                          ))}
                        </select>
                      </label>
                    ))}
                    <label className="signal-toggle">
                      <input
                        type="checkbox"
                        checked={useClassifierSignals}
                        onChange={(e) => setUseClassifierSignals(e.target.checked)}
                      />
                      Experimental classifier signals
                      <small>Uses dated item probabilities as forecast context.</small>
                    </label>
                  </div>
                )}
              </section>
              <div className="kpis">
                <article className="panel kpi">
                  <span>Historical {unit ? "revenue" : "volume"}</span>
                  <div>
                    <strong>
                      {unit}
                      {compact(total)}
                    </strong>
                    <Spark
                      values={shownHistory.slice(-12).map((r) => r.value)}
                    />
                  </div>
                  <small>
                    {shownHistory.length
                      ? `${date(shownHistory[0].month)} — ${date(shownHistory[shownHistory.length - 1].month)}`
                      : "Waiting for source data"}
                  </small>
                </article>
                <article className="panel kpi">
                  <span>Forecast · selected horizon</span>
                  <div>
                    <strong>
                      {result
                        ? unit + compact(base.reduce((s, v) => s + v, 0))
                        : "—"}
                    </strong>
                    <Spark values={base} />
                  </div>
                  <small>
                    {result
                      ? `${base.length} ${result.params?.granularity} periods`
                      : "Run a model to see your outlook"}
                  </small>
                </article>
                <article className="panel kpi">
                  <span>Your planning scenario</span>
                  <div>
                    <strong>{result ? unit + compact(projected) : "—"}</strong>
                    <span className="change">
                      {result
                        ? `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}%`
                        : "—"}
                    </span>
                  </div>
                  <small>
                    {scenarioFit != null
                      ? `Scenario fit ${scenarioFit.toFixed(1)}% · updates as you edit`
                      : "Adjustment relative to model forecast"}
                  </small>
                </article>
                <article className="panel kpi">
                  <span>Forecast accuracy</span>
                  <div>
                    <strong>
                      {result?.validation?.accuracy_pct != null
                        ? `${result.validation.accuracy_pct.toFixed(1)}%`
                        : "—"}
                    </strong>
                    <span className="submetric">Validation</span>
                  </div>
                  <small>
                    {result?.validation?.accuracy_pct != null
                      ? "100 − WAPE · measured on held-out history"
                      : "Run a model to measure validation accuracy"}
                  </small>
                </article>
              </div>
              <section className="panel forecast-panel">
                <div className="section-heading">
                  <div>
                    <h2>
                      Sales outlook{" "}
                      <span className="tag">
                        {result?.params?.granularity || "monthly"}
                      </span>
                    </h2>
                    <p>
                      {result?.forecast?.spec ||
                        "Your history, with a forward-looking perspective."}
                    </p>
                  </div>
                  <div className="legend">
                    <span>
                      <i className="actual" />
                      Actual / aggregated
                    </span>
                    <span>
                      <i className="forecast" />
                      Forecast
                    </span>
                    <span>
                      <i className="scenario" />
                      Planning scenario
                    </span>
                    <span>
                      <i className="range" />
                      Model range
                    </span>
                  </div>
                </div>
                {busy && (
                  <div className="progress" role="status">
                    <span />
                    Fitting the selected model. Ensemble validation can take
                    several minutes.
                  </div>
                )}
                <ForecastChart
                  history={shownHistory}
                  forecast={result?.forecast}
                  scenario={scenario}
                  onChange={updateScenario}
                  unit={unit}
                />
                <div className="chart-footer">
                  <span>
                    ⓘ{" "}
                    {result?.allocation_note ||
                      "Source: monthly sales orders. Forecasts are planning estimates."}
                  </span>
                  <span>
                    {result
                      ? "Drag forecast points to explore a scenario."
                      : "Select a model below, then run your forecast."}
                  </span>
                </div>
                {result && (
                  <div className="scenario-control">
                    <label htmlFor="adjust">
                      Scenario adjustment{" "}
                      <b>
                        {adjust === null
                          ? "Custom"
                          : `${adjust > 0 ? "+" : ""}${adjust}%`}
                      </b>
                    </label>
                    <input
                      id="adjust"
                      type="range"
                      min="-50"
                      max="100"
                      value={adjust ?? 0}
                      onChange={(e) => {
                        const a = +e.target.value;
                        setAdjust(a);
                        setScenario(base.map((v) => v * (1 + a / 100)));
                      }}
                    />
                    <button
                      className="text-button"
                      onClick={() => {
                        setScenario(base);
                        setAdjust(0);
                      }}
                    >
                      Reset to model
                    </button>
                    <span>
                      Scenario means “what if we plan for this level of demand?”
                      It changes the plan instantly. Scenario fit updates against
                      the model range; measured model validation stays fixed.
                    </span>
                  </div>
                )}
              </section>
              <div className="bottom-grid">
                <section className="panel model-panel">
                  <div className="section-heading">
                    <div>
                      <h2>Choose your forecasting model</h2>
                      <p>
                        Start with a baseline, or compare the full ensemble.
                      </p>
                    </div>
                    <span className="small-label">06 MODELS</span>
                  </div>
                  <div className="model-grid">
                    {models.map((m, i) => (
                      (() => {
                        const modelValidation =
                          result?.params?.model === m.id
                            ? result.validation
                            : comparison[m.id]?.validation;
                        return (
                          <button
                            disabled={busy}
                            key={m.id}
                            onClick={() => setModel(m.id)}
                            className={`model-card ${model === m.id ? "selected" : ""}`}
                            aria-pressed={model === m.id}
                          >
                        <div>
                          <span className="model-number">0{i + 1}</span>
                          <span className="radio" />
                        </div>
                        <strong>{m.name}</strong>
                        <small>{m.desc}</small>
                        <small className="model-accuracy">
                          {modelValidation?.accuracy_pct != null
                            ? `${modelValidation.accuracy_pct.toFixed(1)}% accuracy`
                            : "Accuracy: run model to validate"}
                        </small>
                        <span className="model-status">
                          {model === m.id
                            ? "Selected for next run"
                            : "Select model"}{" "}
                          →
                        </span>
                          </button>
                        );
                      })()
                    ))}
                  </div>
                </section>
                <section className="panel notes">
                  <div className="section-heading">
                    <h2>Planning notes</h2>
                    <span>↗</span>
                  </div>
                  <div>
                    <span className="note-number">01</span>
                    <h3>Start at the right level</h3>
                    <p>
                      Explore an item, customer, or industry. Combine filters to
                      make the forecast specific to your plan.
                    </p>
                  </div>
                  <div>
                    <span className="note-number">02</span>
                    <h3>Keep uncertainty visible</h3>
                    <p>
                      The shaded range reflects model uncertainty. Longer
                      horizons carry more uncertainty.
                    </p>
                  </div>
                  <div>
                    <span className="note-number">03</span>
                    <h3>Make assumptions explicit</h3>
                    <p>
                      Drag a point or adjust the scenario. Export both the
                      original forecast and your planning values.
                    </p>
                  </div>
                </section>
              </div>
              {result?.forecast && (
                <section className="panel detail-table">
                  <div className="section-heading">
                    <h2>Period-by-period plan</h2>
                    <span className="small-label">EDITABLE SCENARIO</span>
                  </div>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>Period</th>
                          <th>Model forecast</th>
                          <th>Lower bound</th>
                          <th>Upper bound</th>
                          <th>Planning scenario</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.forecast.months.map((m, i) => (
                          <tr key={m}>
                            <td>{date(m)}</td>
                            <td>
                              {unit}
                              {compact(base[i])}
                            </td>
                            <td>
                              {unit}
                              {compact(result.forecast!.lower_90[i])}
                            </td>
                            <td>
                              {unit}
                              {compact(result.forecast!.upper_90[i])}
                            </td>
                            <td>
                              <input
                                type="number"
                                min="0"
                                aria-label={`Scenario for ${m}`}
                                value={Math.round(scenario[i] || 0)}
                                onChange={(e) => {
                                  const v = Number(e.target.value);
                                  if (Number.isFinite(v)) {
                                    const next = [...scenario];
                                    next[i] = Math.max(0, v);
                                    updateScenario(next);
                                  }
                                }}
                              />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </>
          )}
          {view === "models" && (
            <section className="panel detail-table">
              <div className="section-heading">
                <div>
                  <h2>Model comparison</h2>
                  <p>
                    {result?.weight_method ||
                      "Run an ensemble forecast to compare models on matching chronological windows."}
                  </p>
                </div>
                <button
                  className="secondary"
                  onClick={() => {
                    setModel("ensemble");
                    setView("forecast");
                  }}
                >
                  Configure ensemble →
                </button>
              </div>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Model</th>
                      <th>Status</th>
                      <th>Accuracy</th>
                      <th>WAPE</th>
                      <th>CV MASE</th>
                      <th>Folds</th>
                      <th>Weight</th>
                      <th>Outlook</th>
                    </tr>
                  </thead>
                  <tbody>
                    {models
                      .filter((m) => m.id !== "ensemble")
                      .map((m) => {
                        const r = comparison[m.id];
                        const modelValidation =
                          result?.params?.model === m.id
                            ? result.validation
                            : r?.validation;
                        return (
                          <tr key={m.id}>
                            <td>
                              <strong>{m.name}</strong>
                              <small>{r?.message || m.desc}</small>
                            </td>
                            <td>
                              <span
                                className={`tag ${r?.status === "ok" ? "good" : ""}`}
                              >
                                {r?.status || "Not run"}
                              </span>
                            </td>
                            <td>
                              {modelValidation?.accuracy_pct != null
                                ? `${modelValidation.accuracy_pct.toFixed(1)}%`
                                : "—"}
                            </td>
                            <td>
                              {modelValidation?.wape_pct != null
                                ? `${modelValidation.wape_pct.toFixed(1)}%`
                                : "—"}
                            </td>
                            <td>{modelValidation?.mase?.toFixed(3) || "—"}</td>
                            <td>{modelValidation?.folds ?? "—"}</td>
                            <td>
                              {result?.weights?.[m.id] != null
                                ? `${(result.weights[m.id] * 100).toFixed(1)}%`
                                : "—"}
                            </td>
                            <td>
                              <Spark values={r?.forecast?.point || []} />
                            </td>
                          </tr>
                        );
                      })}
                  </tbody>
                </table>
              </div>
              <p className="table-note">
                Accuracy is max(0, 100 − validation WAPE). WAPE is total
                absolute forecast error divided by total absolute actual demand.
                MASE scales errors by a seasonal-naive reference. Validation
                uses expanding monthly windows on the SQL snapshot shown below.
                Scores are repeatable for the same data fingerprint, model code,
                and protocol; changing the SQL data or model configuration should
                change them. Weighted bounds are approximate and are not a
                calibrated ensemble interval.
              </p>
              {result?.validation?.data_fingerprint && (
                <p className="table-note validation-provenance">
                  Validation snapshot: {result.validation.history_start} —{" "}
                  {result.validation.history_end} ·{" "}
                  {result.validation.history_points} monthly points ·{" "}
                  {result.validation.folds} expanding holdout windows · fingerprint{" "}
                  <code>{result.validation.data_fingerprint.slice(0, 12)}</code>
                </p>
              )}
            </section>
          )}
          {view === "inventory" && (
            <>
              <section className="panel inventory-intro">
                <div>
                  <span className="tag">SQL DEMAND · REPLENISHMENT</span>
                  <h2>Plan inventory around the time supply takes to arrive.</h2>
                  <p>
                    Lead time runs from placing a purchase order to stock being
                    ready to sell. This planner uses Mitsubishi sales history
                    for demand and keeps supplier lead time and warehouse stock
                    as visible planning inputs.
                  </p>
                </div>
                <div className="inventory-source">
                  <strong>{inventory?.planning_as_of ? date(inventory.planning_as_of) : "—"}</strong>
                  <span>planning as-of · source {inventory?.source_as_of ? date(inventory.source_as_of) : "—"}</span>
                </div>
              </section>
              <section className="panel controls inventory-settings">
                <div className="control">
                  <label htmlFor="lead-time-days">Supplier lead time</label>
                  <input
                    id="lead-time-days"
                    type="number"
                    min="1"
                    max="365"
                    value={inventorySettings.leadTimeDays}
                    onChange={(e) =>
                      setInventorySettings({
                        ...inventorySettings,
                        leadTimeDays: Math.max(1, Math.min(365, Number(e.target.value) || 1)),
                      })
                    }
                  />
                  <small>days from PO to ready-to-use stock</small>
                </div>
                <div className="control">
                  <label htmlFor="safety-stock-months">Safety stock</label>
                  <input
                    id="safety-stock-months"
                    type="number"
                    min="0"
                    max="12"
                    step="0.25"
                    value={inventorySettings.safetyStockMonths}
                    onChange={(e) =>
                      setInventorySettings({
                        ...inventorySettings,
                        safetyStockMonths: Math.max(0, Math.min(12, Number(e.target.value) || 0)),
                      })
                    }
                  />
                  <small>months of demand held in reserve</small>
                </div>
                <div className="control">
                  <label htmlFor="coverage-months">Forward coverage</label>
                  <input
                    id="coverage-months"
                    type="number"
                    min="0.25"
                    max="24"
                    step="0.25"
                    value={inventorySettings.coverageMonths}
                    onChange={(e) =>
                      setInventorySettings({
                        ...inventorySettings,
                        coverageMonths: Math.max(0.25, Math.min(24, Number(e.target.value) || 0.25)),
                      })
                    }
                  />
                  <small>target demand covered after arrival</small>
                </div>
                <button className="primary" onClick={() => void loadInventory()} disabled={inventoryLoading}>
                  {inventoryLoading ? "Updating…" : "Apply assumptions"} <span>↗</span>
                </button>
              </section>
              <div className="inventory-kpis">
                <article className="panel kpi">
                  <span>Items needing an order</span>
                  <div><strong>{inventoryRows.filter((row) => row.status === "Order now").length.toLocaleString()}</strong></div>
                  <small>based on the on-hand values below</small>
                </article>
                <article className="panel kpi">
                  <span>Suggested order units</span>
                  <div><strong>{compact(inventoryRows.reduce((sum, row) => sum + row.suggested_order_units, 0))}</strong></div>
                  <small>lead time + safety + coverage target</small>
                </article>
                <article className="panel kpi">
                  <span>Source rows used</span>
                  <div><strong>{(inventory?.source_rows || 0).toLocaleString()}</strong></div>
                  <small>canonical Mitsubishi SQL demand rows</small>
                </article>
              </div>
              <section className="panel detail-table inventory-table">
                <div className="section-heading">
                  <div>
                    <h2>Replenishment queue <span className="tag">{inventoryRows.length} items</span></h2>
                    <p>Enter current on-hand units to make the recommended order quantity and status reflect your warehouse.</p>
                  </div>
                  <span className={`tag ${inventory?.vendor_mapping_available ? "good" : ""}`}>
                    {inventory?.vendor_mapping_available ? "VENDOR MAPPED" : "VENDOR MAPPING NEEDED"}
                  </span>
                </div>
                {inventoryLoading && <div className="progress" role="status"><span /> Reading the SQL demand snapshot…</div>}
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Item / SKU</th>
                        <th>Monthly run rate</th>
                        <th>Demand in lead time</th>
                        <th>Safety stock</th>
                        <th>Reorder point</th>
                        <th>On hand · editable</th>
                        <th>Suggested order</th>
                        <th>Order / arrival</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {inventoryRows.map((row) => (
                        <tr key={row.key}>
                          <td><strong>{row.key}</strong><small>{row.months_with_source_data} months with demand · {row.vendor || "Vendor unmapped"} · {row.lead_time_days}d lead time</small></td>
                          <td>{row.run_rate_units_per_month.toLocaleString(undefined, { maximumFractionDigits: 1 })}</td>
                          <td>{row.lead_time_demand_units.toLocaleString(undefined, { maximumFractionDigits: 1 })}</td>
                          <td>{row.safety_stock_units.toLocaleString(undefined, { maximumFractionDigits: 1 })}</td>
                          <td>{row.reorder_point_units.toLocaleString(undefined, { maximumFractionDigits: 1 })}</td>
                          <td>
                            <input
                              className="number-input"
                              aria-label={`On hand units for ${row.key}`}
                              type="number"
                              min="0"
                              step="1"
                              value={inventoryOnHand[row.key] ?? 0}
                              onChange={(e) => setInventoryOnHand({ ...inventoryOnHand, [row.key]: Math.max(0, Number(e.target.value) || 0) })}
                            />
                          </td>
                          <td><strong>{row.suggested_order_units.toLocaleString(undefined, { maximumFractionDigits: 1 })}</strong></td>
                          <td><small>{date(row.order_by_date)}<br />arrives {date(row.expected_arrival_date)}</small></td>
                          <td><span className={`tag ${row.status === "Covered" ? "good" : "status-order"}`}>{row.status}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="inventory-note">
                  Run rate is 70% trailing three source months plus 30% trailing twelve months. The source files do not contain purchase orders, receipts, warehouse balances, or supplier lead times, so those values remain explicit planner inputs rather than hidden assumptions.
                </p>
              </section>
            </>
          )}
          {view === "demand" && (
            <>
              <section className="panel demand-intro">
                <span className="tag">
                  {training.status === "running"
                    ? "TRAINING IN PROGRESS"
                    : "ITEM DEMAND MODELS"}
                </span>
                <h2>Understand demand before the next order.</h2>
                <p>
                  {classifier?.message ||
                    "Loading classifier deployment status…"}
                </p>
              </section>
              <div className="training-status" role="status">
                {training.status === "running"
                  ? `${training.model || "Models"} · ${training.stage || "Training"} ${training.epoch ? `· epoch ${training.epoch}/${training.epochs}` : ""}`
                  : training.status === "error"
                    ? training.message
                    : "Training uses earlier months. Accuracy is measured on later, held-out months."}
              </div>
              <section className="panel controls">
                <div className="control">
                  <label htmlFor="training-profile">Training profile</label>
                  <select
                    id="training-profile"
                    value={trainingFast ? "quick" : "full"}
                    disabled={training.status === "running"}
                    onChange={(e) =>
                      setTrainingFast(e.target.value === "quick")
                    }
                  >
                    <option value="quick">Quick · up to 12 epochs</option>
                    <option value="full">Full · up to 100 epochs</option>
                  </select>
                </div>
                <button
                  className="secondary"
                  onClick={trainClassifiers}
                  disabled={training.status === "running"}
                >
                  {training.status === "running"
                    ? "Training…"
                    : "Train / refresh models"}
                </button>
                <div className="control selection">
                  <label htmlFor="classifier-item">Item / SKU</label>
                  <input
                    id="classifier-item"
                    list="classifier-items"
                    placeholder="Search item code or leave blank for all"
                    value={classifierItem}
                    onChange={(e) => setClassifierItem(e.target.value)}
                  />
                  <datalist id="classifier-items">
                    {options?.dimensions.item.map((v) => (
                      <option key={v} value={v} />
                    ))}
                  </datalist>
                </div>
                <button
                  className="primary"
                  disabled={classifierBusy}
                  onClick={predictDemand}
                >
                  {classifierBusy ? "Checking…" : "Check demand"}
                </button>
              </section>
              <label className="table-note">
                <input
                  type="checkbox"
                  checked={reviewOnly}
                  onChange={(e) => setReviewOnly(e.target.checked)}
                />{" "}
                Show borderline review queue only
              </label>
              {classifierResults.map((r) => (
                <section className="panel detail-table" key={r.model}>
                  <div className="section-heading">
                    <h2>
                      {r.model === "nn" ? "High demand" : "Sold / not sold"}
                    </h2>
                    <span className="tag">{r.status}</span>
                  </div>
                  {r.message && <p className="table-note">{r.message}</p>}
                  {r.predictions.length > 0 && (
                    <table>
                      <thead>
                        <tr>
                          <th>Item</th>
                          <th>Probability</th>
                          <th>Review</th>
                        </tr>
                      </thead>
                      <tbody>
                        {r.predictions
                          .filter((p) => !reviewOnly || p.review)
                          .slice(0, 100)
                          .map((p) => (
                            <tr key={p.item}>
                              <td>{p.item}</td>
                              <td>
                                <meter min="0" max="1" value={p.probability} />{" "}
                                {(p.probability * 100).toFixed(1)}%
                              </td>
                              <td>{p.review ? "Borderline · review" : "—"}</td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  )}
                  {r.diagnostics && (
                    <div className="diagnostic-grid">
                      <div>
                        <strong>
                          {Number(r.diagnostics.accuracy_pct).toFixed(1)}%
                        </strong>
                        <span>Held-out accuracy</span>
                      </div>
                      <div>
                        <strong>{Number(r.diagnostics.auc).toFixed(3)}</strong>
                        <span>ROC AUC</span>
                      </div>
                      <div>
                        <strong>
                          {Number(r.diagnostics.balanced_accuracy_pct).toFixed(
                            1,
                          )}
                          %
                        </strong>
                        <span>Balanced accuracy</span>
                      </div>
                      <div>
                        <strong>
                          {Number(
                            r.diagnostics.persistence_accuracy_pct,
                          ).toFixed(1)}
                          %
                        </strong>
                        <span>Last-month baseline</span>
                      </div>
                      <div>
                        <strong>
                          {Number(r.diagnostics.test_rows).toLocaleString()}
                        </strong>
                        <span>Held-out item-months</span>
                      </div>
                      <div>
                        <span>
                          Confusion matrix · actual rows / predicted columns
                        </span>
                        <table>
                          <thead>
                            <tr>
                              <th></th>
                              <th>Negative</th>
                              <th>Positive</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(
                              r.diagnostics.confusion_matrix as number[][]
                            )?.map((row, i) => (
                              <tr key={i}>
                                <th>{i ? "Positive" : "Negative"}</th>
                                {row.map((v, j) => (
                                  <td key={j}>{v.toLocaleString()}</td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </section>
              ))}
              <div className="classifier-grid">
                {classifier?.models.map((m) => (
                  <section className="panel classifier-card" key={m.name}>
                    <span className="small-label">SEPTEMBER MODEL</span>
                    <h2>{m.name}</h2>
                    <div className="probability">
                      {m.diagnostics
                        ? `${m.diagnostics.accuracy_pct.toFixed(1)}%`
                        : "—"}
                      <small>
                        {m.diagnostics
                          ? "Held-out accuracy"
                          : "Train this model to measure accuracy"}
                      </small>
                    </div>
                    <p>
                      Target: {m.target} · {m.items || 0} scored items
                    </p>
                    <span className="tag">{m.status}</span>
                  </section>
                ))}
              </div>
            </>
          )}
          {view === "data" && (
            <section className="panel detail-table">
              <div className="section-heading">
                <div>
                  <h2>Connected dimensions</h2>
                  <p>MySQL · Sales_Order_Merged</p>
                </div>
                <span className="tag">MONTHLY SOURCE</span>
              </div>
              <table>
                <thead>
                  <tr>
                    <th>Dimension</th>
                    <th>Available values</th>
                    <th>Coverage</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(options?.dimensions || {}).map(
                    ([d, values]) => (
                      <tr key={d}>
                        <td>{titles[d]}</td>
                        <td>{values.length.toLocaleString()}</td>
                        <td>
                          {values.length
                            ? "Available"
                            : "No mapping in source schema"}
                        </td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
              <div className="data-notes">
                <h3>Data assumptions</h3>
                <p>
                  Daily and weekly planning views allocate monthly totals across
                  calendar days. They do not represent daily transaction
                  observations.
                </p>
                <p>
                  Order lines use the existing composite deduplication rule.
                  Confirm that rule with the source-system owner before relying
                  on reported totals.
                </p>
                <p>
                  Yearly and quarterly boundaries use calendar periods. Boundary
                  periods can be partial.
                </p>
                {result?.data_fingerprint && (
                  <p className="fingerprint">
                    Current forecast data fingerprint: {result.data_fingerprint}
                  </p>
                )}
              </div>
            </section>
          )}
          <footer>
            <span>
              MITSUBISHI ELECTRIC <b>·</b> Sales intelligence
            </span>
            <span>Built for thoughtful planning.</span>
          </footer>
        </main>
      </div>
    </div>
  );
}
