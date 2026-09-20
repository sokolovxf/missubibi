"""
SARIMA forecasting engine — importable, silent, side-effect free.

The modelling functions below are lifted VERBATIM from
`backend/sarima_sales_forecast_v7.py` (the Colab export). They were extracted by
AST rather than retyped, so the order search, the walk-forward validation, the
plausibility screening and the bias correction are byte-identical to the version
that was validated in the notebook. Do not "tidy" them here — if the modelling
logic needs to change, change it in the notebook, re-export, and re-extract.

What this module adds around that core:

  * no I/O          — the caller supplies a DataFrame; nothing reads a CSV
  * no printing     — the notebook's narrative print()/plt.show() calls are not
                      carried over; the one remaining print sits behind the
                      `verbose` flag it always sat behind
  * no plotting     — matplotlib is never imported
  * collected notes — what the notebook printed as a checklist is returned as a
                      list of {kind, message} dicts instead

Run state (FULL_INDEX, WD_FULL, SERIES_CLIP, resid_df, ...) lives in module
globals because that is how the notebook is written and rewriting every call site
would be the risky change, not the safe one. `run_forecast()` therefore holds a
lock for the whole run and resets that state on entry — it is safe to call from
concurrent requests, but calls are serialised.

COST: a full run fits several hundred SARIMA models. On 48 months of history it
takes roughly 40-90 seconds per series. Do not call it synchronously inside a
request handler — cache it, or run it from a background task.
"""

from __future__ import annotations

import contextlib
import threading
import time
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.tsa.seasonal import STL
from statsmodels.tsa.stattools import adfuller, kpss

try:                                    # supplies the Thai lunar + in-lieu holidays
    import holidays as _holidays_pkg
except ImportError:                     # falls back to the fixed-date table below
    _holidays_pkg = None


# ----------------------------------------------------------------------------------
# Diagnostics infrastructure. The notebook printed these; here they are collected
# and handed back to the caller.
# ----------------------------------------------------------------------------------
FIT_LOG: list = []
FAILURES: list = []
CLIP_LOG: list = []
NOTES: list = []

_LOCK = threading.RLock()
_DEBUG = False


@contextlib.contextmanager
def capture_warnings(context):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        yield
    for w in caught:
        FIT_LOG.append({"context": context, "category": w.category.__name__,
                        "message": str(w.message).split("\n")[0][:160]})


def log_failure(context, exc):
    FAILURES.append({"context": context, "error": type(exc).__name__,
                     "message": str(exc)[:200]})


def note(kind, msg):
    """Anything the caller must act on. Collected, and printed only under debug."""
    NOTES.append({"kind": kind, "message": msg})
    if _DEBUG:
        print(f"[{kind}] {msg}")


# ----------------------------------------------------------------------------------
# Run-scoped state. `run_forecast()` sets these; nothing else should.
# ----------------------------------------------------------------------------------
FULL_INDEX: pd.DatetimeIndex | None = None
WD_FULL: np.ndarray | None = None
FUTURE_WD: np.ndarray | None = None
SERIES_CLIP: dict = {}
SPEC_CACHE: dict = {}
PI_SOURCE: dict = {}
resid_df: pd.DataFrame | None = None
HOLIDAY_SOURCE: dict = {}
HOLIDAY_DROPPED: dict = {}
_HOLIDAY_CACHE: dict = {}


# ==================================================================================
# Below this line: extracted VERBATIM from sarima_sales_forecast_v7.py. Do not edit.
# ==================================================================================
CONFIG = dict(
    SEED                     = 42,
    SEASONAL_PERIOD          = 12,
    FISCAL_START_MONTH       = 4,        # April

    # --- evaluation -------------------------------------------------------------
    MIN_TRAIN_MONTHS         = 24,
    WF12_HORIZON             = 12,
    WF12_STEP                = 6,
    SPEC_REFRESH_MONTHS      = 6,        # re-select the SARIMA spec as the window grows
    RUN_LOFO                 = True,     # robustness check; NEVER used to judge accuracy

    # --- exogenous ----------------------------------------------------------------
    USE_WORKING_DAYS         = True,     # the one free exogenous driver
    HOLIDAY_COUNTRY          = "TH",     # "TH" | "NONE" — public holidays removed from working days
    EXOG_SELECTION           = True,     # let AICc decide whether working days actually helps

    # --- order search -------------------------------------------------------------
    UNIT_ROOT_TEST           = "both",   # "both" = difference unless KPSS *and* ADF agree it is
                                         # stationary; also "kpss" or "adf" alone
    DD_SELECTION             = "cv",     # "cv" = pick the differencing order by rolling-origin
                                         # CV inside the training window (AICc cannot compare
                                         # across differencing); "test" = seasonal strength alone
    CV_HORIZON               = 6,        # steps ahead scored per CV origin — 1 would tune the
                                         # spec for WF1 only and ignore the annual-plan horizon
    CV_ORIGINS               = 4,        # rolling origins used for that CV
    CV_MIN_TRAIN_MONTHS      = 15,       # training floor for the INNER CV windows only. This
                                         # used to be MIN_TRAIN_MONTHS, which answers a
                                         # different question - how much history a fold needs
                                         # before its forecast COUNTS, not how much a model
                                         # needs to be FITTED. Tying them together disabled
                                         # the CV entirely at a 24-month window and left room
                                         # for exactly one origin at 30, so at the earliest
                                         # origins the drift term was never scored, the
                                         # seasonal veto never fired and no bias correction
                                         # was ever estimated. At 15 both windows get four.
    MAX_PQ                   = 2,        # p, q each range over 0..MAX_PQ
    MAX_PQ_SEASONAL          = 1,        # P, Q each range over 0..MAX_PQ_SEASONAL
    SEASONAL_MIN_CYCLES      = 2.0,      # full seasonal cycles of TRAINING data required
                                         # before a (P,D,Q)[m] term is offered at all. Was
                                         # effectively 3, which disqualified seasonality on
                                         # every fold under 36 months — most of them, since
                                         # MIN_TRAIN_MONTHS is 24.
    SEASONAL_TRUST_CYCLES    = 3.0,      # full cycles required before a seasonal (P,Q)[m]
                                         # term is trusted on AICc alone. Between
                                         # SEASONAL_MIN_CYCLES and this, the term is still
                                         # fitted, screened and scored — it just has to beat
                                         # the best non-seasonal structure on HELD-OUT error
                                         # before it is selected. Offering seasonality at two
                                         # cycles was right; letting an in-sample, one-step
                                         # criterion buy it there is what moved WF12 bias from
                                         # -10.2% to -17.5%.
    SEASONAL_CV_MARGIN       = 0.05,     # how much held-out error a seasonal ARMA term must
                                         # SAVE to win below SEASONAL_TRUST_CYCLES. A tie goes
                                         # to the simpler model.
    MAX_FOURIER_K            = 2,        # Fourier pairs offered when D = 0
    ALLOW_DRIFT              = True,     # with d+D == 1 a constant IS the drift term
    TREND_SELECTION          = "cv",     # "cv" = pick the trend/drift term by held-out error,
                                         # "aicc" = by in-sample fit. AICc is a one-step
                                         # criterion and a deterministic trend always improves
                                         # in-sample fit, so it over-extrapolates at h=12.
    BIAS_CORRECTION          = True,     # subtract the model's own held-out mean error, measured
                                         # on the TRAINING window only (no leakage). A training
                                         # window with room for only ONE rolling origin cannot
                                         # produce a standard error for that mean, so the
                                         # correction is switched OFF there rather than applied
                                         # in full - which is what it used to do, and what put a
                                         # -8,808 adjustment on a series averaging 18,138.
    BIAS_RECENCY_LAMBDA      = 0.5,      # geometric weight on CV origins, most recent first.
                                         # 1.0 = flat average over the whole CV window (a
                                         # GLOBAL correction); <1 leans on recent origins so
                                         # the correction tracks a level that has moved.
    BIAS_CORRECTION_MAX_FRAC = 0.15,     # hard ceiling on the APPLIED correction, as a share
                                         # of the training window's own mean level. A held-out
                                         # bias worth more than this is a level shift, not a
                                         # tilt, and extrapolating it is how one unlucky window
                                         # once produced an adjustment of half the series. The
                                         # estimate is still reported in full; only what is
                                         # applied is bounded.
    BIAS_CORRECTION_WEIGHT   = 0.5,      # cap on that correction, then shrunk further by the
                                         # signal-to-noise of the estimate. Measured on this
                                         # data: 0 leaves WF1 bias at -7.8% (MASE 0.866), 0.5
                                         # gives -1.1% (0.938), 1.0 overshoots to +4.9% (1.092).
                                         # Held-out bias does not transfer one-for-one, so a
                                         # full correction trades away more accuracy than the
                                         # bias it removes is worth.

    # --- data window --------------------------------------------------------------
    DATA_CUTOFF              = None,     # drop every row ON OR AFTER this date, before any
                                         # fiscal-year detection runs. None = use the whole
                                         # export. Set it to a FISCAL_START_MONTH boundary or
                                         # the last fiscal year in the window is incomplete.
    FISCAL_YEAR_LABEL        = "start",  # "start": FY2021 = Apr-2021..Mar-2022 (the Japanese /
                                         # Thai convention). "end": FY2022 for the same months.
                                         # Labels only — the months in each year never change.

    # --- data cleaning ----------------------------------------------------------
    DROP_NEGATIVE_QTY        = False,    # False = keep returns as negative revenue
    DROP_NEGATIVE_PRICE      = True,
    N_TOP_CATEGORIES         = 3,

    # --- output / safety --------------------------------------------------------
    CLIP_NEGATIVE_PREDICTIONS= True,     # applied ONLY to non-negative series
    SEASONAL_STRENGTH_MIN    = 0.30,     # below this on the TRAINING window, D is set to 0
    ZERO_MONTH_WARN_FRAC     = 0.20,
    FY_DEVIATION_WARN_PCT    = 15.0,
    FY_ANOMALY_MAD_Z         = 3.0,
    N_BOOT                   = 5000,
    FAST_MODE                = False,    # True => smaller grid, faster, slightly worse specs
    PI_FROM_WALK_FORWARD     = True,     # 90% band from OUT-OF-SAMPLE errors, not in-sample ones
)

# ----------------------------------------------------------------------------------
# Constants the extracted functions bind at definition time (default arguments), so
# they must exist before those defs are executed.
# ----------------------------------------------------------------------------------
np.random.seed(CONFIG["SEED"])

M = CONFIG["SEASONAL_PERIOD"]
FISCAL_START = CONFIG["FISCAL_START_MONTH"]
FY_LABEL = str(CONFIG.get("FISCAL_YEAR_LABEL", "start")).lower()
if FY_LABEL not in ("start", "end"):
    raise ValueError("CONFIG['FISCAL_YEAR_LABEL'] must be 'start' or 'end'")
HORIZON = int(CONFIG["WF12_HORIZON"])


def fiscal_year_vec(dt, start_month=FISCAL_START):
    if FY_LABEL == "start":
        return dt.dt.year - (dt.dt.month < start_month).astype(int)
    return dt.dt.year + (dt.dt.month >= start_month).astype(int)


def fiscal_year(ts, start_month=FISCAL_START):
    ts = pd.Timestamp(ts)
    if FY_LABEL == "start":
        return ts.year - (1 if ts.month < start_month else 0)
    return ts.year + (1 if ts.month >= start_month else 0)


def fy_start(fy, start_month=FISCAL_START):
    """First month of fiscal year `fy`. The single place the label convention is turned
    back into a date, so nothing downstream has to know which convention is in force."""
    y = int(fy) if FY_LABEL == "start" else int(fy) - 1
    return pd.Timestamp(year=y, month=start_month, day=1)


def robust_z(x):
    x = np.asarray(x, dtype=float)
    med = np.median(x)
    mad = np.median(np.abs(x - med))
    return np.zeros_like(x) if mad == 0 else 0.6745 * (x - med) / mad


THAI_FIXED_HOLIDAYS = [(1, 1),                      # New Year's Day
                       (4, 6),                      # Chakri Memorial Day
                       (4, 13), (4, 14), (4, 15),   # Songkran
                       (5, 1),                      # Labour Day
                       (5, 4),                      # Coronation Day
                       (6, 3),                      # Queen Suthida's Birthday
                       (7, 28),                     # King Vajiralongkorn's Birthday
                       (8, 12),                     # Mother's Day
                       (10, 13),                    # King Bhumibol Memorial Day
                       (10, 23),                    # Chulalongkorn Day
                       (12, 5),                     # Father's Day / National Day
                       (12, 10),                    # Constitution Day
                       (12, 31)]


HOLIDAY_CALENDARS = {"TH": THAI_FIXED_HOLIDAYS, "NONE": []}


HOLIDAY_EXCLUDE_PATTERNS = ("bridge", "children")


def _fixed_holiday_dates(years, country):
    fixed = HOLIDAY_CALENDARS.get(country, [])
    if not fixed:
        return pd.DatetimeIndex([])
    return pd.DatetimeIndex(sorted({pd.Timestamp(year=int(y), month=mth, day=day)
                                    for y in years for mth, day in fixed}))


def holiday_dates(years, country=None):
    """Public holidays for `years`, from the `holidays` package where it is installed.

    Memoised: working_days() is called once per spec search for the forward horizon, and
    rebuilding a multi-year calendar each time is pure waste.
    """
    country = str(country or CONFIG["HOLIDAY_COUNTRY"] or "NONE").upper()
    years = tuple(sorted({int(y) for y in years}))
    key = (country, years)
    if key in _HOLIDAY_CACHE:
        return _HOLIDAY_CACHE[key]
    if country == "NONE":
        HOLIDAY_SOURCE[country] = "none (CONFIG['HOLIDAY_COUNTRY'] is NONE)"
        out = pd.DatetimeIndex([])
    else:
        out = None
        if _holidays_pkg is not None:
            try:
                cal = _holidays_pkg.country_holidays(country, years=list(years))
                kept, dropped = [], []
                for d, name in cal.items():
                    low = str(name).lower()
                    if any(pat in low for pat in HOLIDAY_EXCLUDE_PATTERNS):
                        dropped.append((pd.Timestamp(d), str(name)))
                    else:
                        kept.append(pd.Timestamp(d))
                if kept:
                    HOLIDAY_DROPPED[country] = sorted(dropped)
                    HOLIDAY_SOURCE[country] = (
                        f"holidays=={_holidays_pkg.__version__} (lunar + in-lieu INCLUDED; "
                        f"{len(dropped)} discretionary day(s) excluded by name)")
                    out = pd.DatetimeIndex(sorted(kept))
            except Exception as e:
                log_failure(f"holidays[{country}]", e)
        if out is None:
            HOLIDAY_SOURCE[country] = ("built-in fixed-date list "
                                       "(lunar and in-lieu days MISSING)")
            out = _fixed_holiday_dates(years, country)
    _HOLIDAY_CACHE[key] = out
    return out


def working_days(index, country=None):
    """Mon-Fri per month, minus public holidays that actually fall on a weekday."""
    idx = pd.DatetimeIndex(index)
    hol = holiday_dates(range(idx.min().year - 1, idx.max().year + 3), country)
    hol = hol[hol.dayofweek < 5]            # a holiday on a weekend costs no working day
    hol_np = hol.values.astype("datetime64[D]")
    out = []
    for ts in idx:
        start = np.datetime64(pd.Timestamp(ts).date(), "D")
        end = np.datetime64((pd.Timestamp(ts) + pd.DateOffset(months=1)).date(), "D")
        out.append(float(np.busday_count(start, end, holidays=hol_np)))
    return np.array(out)


def naive_scale_fixed(s, n_ref):
    """MASE denominator: MAE of the lag-1 naive forecast over the INITIAL training window only."""
    v = s.to_numpy(dtype=float)[:n_ref]
    d = np.abs(np.diff(v))
    d = d[np.isfinite(d)]
    if d.size == 0 or np.mean(d) == 0:
        return np.nan
    return float(np.mean(d))


def core_metrics(y_true, y_pred, scale):
    yt = np.asarray(y_true, float)
    yp = np.asarray(y_pred, float)
    ok = np.isfinite(yt) & np.isfinite(yp)
    out = {k: np.nan for k in ("MASE", "sMAPE_%", "MAE", "RMSE", "ME", "MPE_%", "MAPE_%")}
    out.update({"n": 0, "n_pred_missing": int((~ok).sum()),
                "n_zero_actual": 0, "n_neg_actual": 0})
    yt, yp = yt[ok], yp[ok]
    if yt.size == 0:
        return out
    err = yt - yp
    out["MAE"] = float(np.mean(np.abs(err)))
    out["RMSE"] = float(np.sqrt(np.mean(err ** 2)))
    out["ME"] = float(np.mean(err))                     # >0 => model under-forecasts
    out["n"] = int(yt.size)
    out["n_zero_actual"] = int((yt == 0).sum())
    out["n_neg_actual"] = int((yt < 0).sum())
    nz = yt != 0
    if nz.any():
        out["MAPE_%"] = float(np.mean(np.abs(err[nz] / yt[nz])) * 100)
        out["MPE_%"] = float(np.mean(err[nz] / yt[nz]) * 100)
    den = np.abs(yt) + np.abs(yp)
    ok2 = den > 0
    if ok2.any():
        out["sMAPE_%"] = float(np.mean(2 * np.abs(err[ok2]) / den[ok2]) * 100)
    if scale is not None and np.isfinite(scale) and scale > 0:
        out["MASE"] = out["MAE"] / scale
    return out


def make_folds(index, fys, cfg):
    n = len(index)
    folds = []
    for origin in range(cfg["MIN_TRAIN_MONTHS"], n):          # WF1
        tr = np.zeros(n, bool); tr[:origin] = True
        te = np.zeros(n, bool); te[origin] = True
        folds.append({"scheme": "WF1", "fold": str(index[origin].date())[:7],
                      "train_mask": tr, "test_mask": te, "origin": origin})
    origin = cfg["MIN_TRAIN_MONTHS"]                          # WF12
    while origin + cfg["WF12_HORIZON"] <= n:
        tr = np.zeros(n, bool); tr[:origin] = True
        te = np.zeros(n, bool); te[origin:origin + cfg["WF12_HORIZON"]] = True
        folds.append({"scheme": "WF12", "fold": f"from {str(index[origin].date())[:7]}",
                      "train_mask": tr, "test_mask": te, "origin": origin})
        origin += cfg["WF12_STEP"]
    if cfg["RUN_LOFO"]:                                       # LOFO (advisory only)
        lab = np.array([fy_of(t) for t in index])
        for fy in fys:
            te = lab == fy
            folds.append({"scheme": "LOFO", "fold": f"FY{fy}",
                          "train_mask": ~te, "test_mask": te, "origin": None})
    return folds


def masked_values(s, train_mask):
    """The only view of the data any model is given: NaN everywhere outside training."""
    v = s.astype(float).to_numpy().copy()
    v[~np.asarray(train_mask, bool)] = np.nan
    return v


def postprocess(pred, series_name, context="", model=""):
    """Clip at zero ONLY where the series is non-negative in-sample, and log every clip.

    `model` is recorded explicitly: the audit in Section 9.4 used to derive it by splitting
    `context` on '|', which yields the SERIES name, so every clip was attributed to a model
    called e.g. 'revenue_SV'.
    """
    p = np.asarray(pred, dtype=float)
    if not SERIES_CLIP.get(series_name, False):
        return p
    neg = np.isfinite(p) & (p < 0)
    if neg.any():
        CLIP_LOG.append({"context": context, "series": series_name, "model": model or "unknown",
                         "n_clipped": int(neg.sum()), "clip_mass": float(-p[neg].sum()),
                         "worst": float(p[neg].min())})
    return np.where(np.isfinite(p), np.maximum(p, 0.0), p)


def build_exog(positions, K, wd_values, use_wd=None):
    """Fourier pairs (seasonality proxy) + standardised working days.

    `use_wd` lets the order search switch the working-days regressor OFF. It used to be
    forced on for every candidate on the strength of CONFIG alone; its correlation with
    the target is 0.03-0.25 here, which is not evidence that it earns its parameter.
    """
    use_wd = CONFIG["USE_WORKING_DAYS"] if use_wd is None else bool(use_wd)
    cols = {}
    if K:
        t = np.asarray(positions, dtype=float)
        for k in range(1, K + 1):
            cols[f"sin{k}"] = np.sin(2 * np.pi * k * t / M)
            cols[f"cos{k}"] = np.cos(2 * np.pi * k * t / M)
    if use_wd and wd_values is not None:
        cols["working_days"] = (np.asarray(wd_values, float) - WD_FULL.mean()) / WD_FULL.std()
    if not cols:
        return None
    return pd.DataFrame(cols)


def longest_contiguous_observed(v):
    obs = np.isfinite(np.asarray(v, dtype=float))
    best_lo = best_hi = 0
    lo = None
    for i, o in enumerate(obs):
        if o and lo is None:
            lo = i
        if lo is not None and (not o or i == len(obs) - 1):
            hi = i if not o else i + 1
            if hi - lo > best_hi - best_lo:
                best_lo, best_hi = lo, hi
            lo = None
    return np.asarray(v, dtype=float)[best_lo:best_hi]


def select_d(values, max_d=2, alpha=0.05, context=""):
    """
    Regular differencing order, chosen by repeated unit-root testing.

    Both tests are used, because at n~24-48 neither is trustworthy alone: ADF (null = unit
    root) almost never rejects, and KPSS (null = stationary) has so little power that it
    fails to flag a 48-point random walk. The default rule differences unless BOTH agree
    the series is stationary — under-differencing is the more expensive error here, since
    a d=0 model carries a constant and its forecast is the sample mean, which sits above a
    declining series by construction. That is where most of the walk-forward high bias came
    from: the old search offered d=0 as the only option whenever ADF happened to reject.
    """
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    test = str(CONFIG["UNIT_ROOT_TEST"]).lower()
    d = 0
    while d < max_d and len(v) >= 12:
        try:
            with capture_warnings(f"unitroot-d[{context}]"):
                kpss_stationary = bool(kpss(v, regression="c", nlags="auto")[1] > alpha) \
                    if test in ("kpss", "both") else True
                adf_stationary = bool(adfuller(v, autolag="AIC")[1] < alpha) \
                    if test in ("adf", "both") else True
            stationary = kpss_stationary and adf_stationary
        except Exception as e:
            log_failure(f"unitroot-d[{context}]", e)
            break
        if stationary:
            break
        v = np.diff(v)
        d += 1
    return d


def seasonal_strength_of(v, period=M, context=""):
    """STL seasonal strength (Wang-Smyth-Hyndman F_S) on OBSERVED values only."""
    v = np.asarray(v, dtype=float)
    v = v[np.isfinite(v)]
    if v.size < 3 * period:
        return np.nan
    try:
        with capture_warnings(f"stl-strength[{context}]"):
            r = STL(pd.Series(v), period=period, robust=True).fit()
        return float(max(0.0, 1 - r.resid.var() / (r.seasonal + r.resid).var()))
    except Exception as e:
        log_failure(f"stl-strength[{context}]", e)
        return np.nan


def select_D(v_train, period=M, context=""):
    """
    Seasonal differencing order, from seasonal strength measured on the TRAINING window.

    Below 3 full cycles the STL decomposition is not identifiable — it will fit 2 cycles
    exactly and report a strength of 1.00 for pure noise — so D is forced to 0 there and
    seasonality is left to the Fourier terms instead.
    """
    n = int(np.isfinite(np.asarray(v_train, dtype=float)).sum())
    if n < 3 * period:
        return 0, np.nan
    fs = seasonal_strength_of(v_train, period, context)
    return int(np.isfinite(fs) and fs >= CONFIG["SEASONAL_STRENGTH_MIN"]), fs


def tukey_fence(x, k=1.5):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if x.size < 4:
        return -np.inf, np.inf
    q1, q3 = np.percentile(x, [25, 75])
    iqr = q3 - q1
    return q1 - k * iqr, q3 + k * iqr


def gap_plausible(path, y_masked, k=1.5, horizon=None, nonneg=False):
    """
    Screen for candidate specs whose predictions leave the neighbourhood of the data INSIDE a
    masked gap. A model can be stationary, invertible and have an excellent AICc while still
    extrapolating absurdly across a 12-month hole; AICc only sees the observed points.

    `horizon` bounds how far into the gap the screen looks, and it matters more than it
    sounds. A walk-forward training mask leaves EVERYTHING after the origin missing - 24
    months at the earliest origin - but no fold ever forecasts more than WF12_HORIZON steps.
    Judging a candidate on a 24-month extrapolation in order to license a 12-month one
    rejects specs that are entirely sane over the horizon actually used, and that is where
    nearly every "every candidate failed the screen" fallback came from. A LOFO gap is
    exactly 12 months wide, so nothing about the interior-gap case changes.

    `nonneg` floors the lower fence at zero for a series that never goes negative in-sample.
    Without it the Tukey fence sits well below zero whenever the IQR is wide - revenue_SV's
    lower fence is about -15M against a smallest observed month of +11M - so a forecast of
    -21M passed the screen and was then quietly repaired by the clip in postprocess(). The
    clip is meant to be the last safety net; refusing the specification is the actual fix.

    Raises if there is no gap - this guard must never silently no-op on a gapless series.
    """
    missing = ~np.isfinite(y_masked)
    if not missing.any():
        raise ValueError("gap_plausible() called on a series with no gap - use "
                         "future_plausibility() for the forward horizon instead.")
    obs = y_masked[np.isfinite(y_masked)]
    pos = np.where(missing)[0]
    if horizon is not None and len(pos) > int(horizon):
        pos = pos[:int(horizon)]
    gap = np.asarray(path, dtype=float)[pos]
    if not np.isfinite(gap).all():
        return False
    lo, hi = tukey_fence(obs, k)
    lo = min(lo, obs.min())
    hi = max(hi, obs.max())
    if nonneg:
        lo = max(lo, 0.0)
    return bool(gap.min() >= lo and gap.max() <= hi)


def future_plausibility(point, history, k=1.5, verbose=False, nonneg=False):
    """
    Screen the FORWARD horizon, which gap_plausible() structurally cannot see.

    Two empirical tests, both Tukey fences on distributions taken from the data itself:
      * level  - each forecast month against the distribution of observed monthly levels
      * change - each forecast's step from the last observation, against the observed
                 distribution of same-length steps in the history

    `nonneg` does the same job here as in gap_plausible(): on a series that has never been
    negative, a negative forecast is not a wide interval, it is a wrong model.

    This is a smoke alarm. Passing it does NOT make a forecast statistically valid; it only
    means the model has not produced something the history says is impossible.
    """
    y = np.asarray(history, dtype=float)
    p = np.asarray(point, dtype=float)
    res = {"level_ok": True, "change_ok": True, "detail": ""}
    if not np.isfinite(p).all():
        return {"level_ok": False, "change_ok": False, "detail": "non-finite forecast", "ok": False}

    lo_l, hi_l = tukey_fence(y, k)
    lo_l, hi_l = min(lo_l, y.min()), max(hi_l, y.max())
    if nonneg:
        lo_l = max(lo_l, 0.0)
    if p.min() < lo_l or p.max() > hi_l:
        res["level_ok"] = False
        res["detail"] += (f"level outside [{lo_l:,.0f}, {hi_l:,.0f}] "
                          f"(forecast spans [{p.min():,.0f}, {p.max():,.0f}]); ")

    changes = []
    for h in range(1, len(p) + 1):
        if len(y) > h:
            changes.append(y[h:] - y[:-h])
    if changes:
        allc = np.concatenate(changes)
        lo_c, hi_c = tukey_fence(allc, k)
        lo_c, hi_c = min(lo_c, allc.min()), max(hi_c, allc.max())
        step = p - y[-1]
        if step.min() < lo_c or step.max() > hi_c:
            res["change_ok"] = False
            res["detail"] += (f"step from last actual outside [{lo_c:,.0f}, {hi_c:,.0f}] "
                              f"(forecast steps span [{step.min():,.0f}, {step.max():,.0f}])")
    res["ok"] = res["level_ok"] and res["change_ok"]
    if verbose and not res["ok"]:
        print("  plausibility flag:", res["detail"])
    return res


def trend_options(d, D):
    """
    Deterministic-trend candidates for a given differencing order.

    In statsmodels a constant is applied to the level of the series, so with one difference
    it survives as a DRIFT term. The original code hardcoded `trend='n'` whenever d>0 or
    D>0, which left the model unable to express a trend at all: it could only revert to a
    level (d=0) or hold the last one flat (d=1). Drift is offered exactly when d+D == 1,
    the same rule `auto.arima` uses, and AICc decides whether it is worth its parameter.
    """
    if d == 0 and D == 0:
        # 'ct' matters as much as drift does. Without it the only undifferenced shape is
        # "revert to the sample mean", which sits above a declining series by construction —
        # and an undifferenced model is often the lower-variance choice on 24-48 points, so
        # forcing a difference just to express the trend trades bias for error.
        return ("c", "ct") if CONFIG["ALLOW_DRIFT"] else ("c",)
    if d + D == 1 and CONFIG["ALLOW_DRIFT"]:
        return ("n", "c")                  # 'c' under one difference == drift
    return ("n",)


def candidate_specs(n_train_obs, d, D, seasonal_ok, fast=False, period=M):
    """
    Candidate structures, ALL SHARING THE SAME (d, D).

    That constraint is the point. statsmodels evaluates the log-likelihood over
    `n_obs - d - D*period` observations, so AIC/AICc from models with different
    differencing orders describe DIFFERENT data and cannot be ranked against one another.
    The original grid mixed d in {d-1, d} and D in {0, 1} into a single AICc ranking; a
    constant-mean SARIMA(0,0,0) won 70 of 186 fits that way. Here (d, D) are settled by
    test in `select_sarima_spec`, and AICc only ever compares like with like.
    """
    max_pq = 1 if fast else int(CONFIG["MAX_PQ"])
    pq = tuple(range(max_pq + 1))
    specs = []

    # A seasonal term used to need 3 full cycles (36 months) of training data before it was
    # even a candidate, so with MIN_TRAIN_MONTHS = 24 most folds never had one offered: it was
    # disqualified before AICc or the rolling-origin CV could weigh it. Two cycles is enough to
    # estimate a lag-m term, and whether it earns its parameters is exactly the question the
    # selection machinery exists to answer — so it is asked, not assumed.
    #
    # `seasonal_ok` remains in the signature but is no longer consulted. select_sarima_spec has
    # passed True ever since the STL strength threshold stopped gating candidate generation:
    # STL reports a seasonal strength of 1.00 on pure noise at n=24, so it is not trusted to
    # disqualify anything. Fourier terms stay unconditional when D == 0, so even the shortest
    # fold always has a seasonal shape to argue against a flat model.
    min_cycles = float(CONFIG.get("SEASONAL_MIN_CYCLES", 2.0))
    seasonal_arma_ok = (D == 1) or (n_train_obs >= min_cycles * period)
    if seasonal_arma_ok:
        max_PQ = 1 if fast else int(CONFIG["MAX_PQ_SEASONAL"])
        for p in pq:
            for q in pq:
                for P in range(max_PQ + 1):
                    for Q in range(max_PQ + 1):
                        if D == 0 and P == 0 and Q == 0:
                            continue                     # that is the Fourier branch below
                        if (P or Q) and (n_train_obs - D * period) / period < min_cycles:
                            continue                     # too few cycles left to estimate it
                        if n_train_obs - D * period - d < 12:
                            continue
                        specs.append({"order": (p, d, q),
                                      "seasonal_order": (P, D, Q, period), "K": 0})

    if D == 0:
        Ks = (0, 1) if fast else tuple(range(int(CONFIG["MAX_FOURIER_K"]) + 1))
        for p in pq:
            for q in pq:
                for K in Ks:
                    if K and n_train_obs < 4 * K + 12:
                        continue
                    specs.append({"order": (p, d, q),
                                  "seasonal_order": (0, 0, 0, 0), "K": K})
    return specs


def fit_sarimax(y, order, seasonal_order, exog, context, trend=None):
    if trend is None:
        trend = "c" if (order[1] == 0 and seasonal_order[1] == 0) else "n"
    mod = sm.tsa.statespace.SARIMAX(y, exog=exog, order=order, seasonal_order=seasonal_order,
                                    trend=trend, enforce_stationarity=True,
                                    enforce_invertibility=True)
    with capture_warnings(context):
        res = mod.fit(disp=False, maxiter=300, method="lbfgs")
    return mod, res


def smoothed_path(mod, params, n):
    """
    E[y_t | ALL observed data] from the Kalman SMOOTHER. There is deliberately NO fallback to
    get_prediction(): that returns the FILTERED path, which flatlines across a gap and is the
    classic bug this notebook exists to avoid.
    """
    sres = mod.smooth(params)
    for getter in (lambda: sres.smoother_results.smoothed_forecasts,
                   lambda: sres.smoothed_forecasts,
                   lambda: mod.ssm.smooth(params).smoothed_forecasts):
        try:
            arr = np.asarray(getter(), dtype=float).ravel()
        except Exception:
            continue
        if arr.shape[0] == n:
            return arr
    raise RuntimeError("Kalman smoother output unavailable — refusing to fall back to the "
                       "filtered path")


def aicc_of(res, n_obs, d, D, period=M):
    """AICc on the effective sample. Only comparable across models with the same (d, D) —
    which is exactly the set `candidate_specs` returns."""
    k = len(res.params)
    denom = (n_obs - d - D * period) - k - 1
    if denom <= 0 or not np.isfinite(res.aic):
        return np.inf
    return float(res.aic + (2 * k * (k + 1)) / denom)


def spec_label(spec):
    p, d, q = spec["order"]
    P, D, Q, m = spec["seasonal_order"]
    s = f"SARIMA({p},{d},{q})"
    if (P, D, Q) != (0, 0, 0):
        s += f"({P},{D},{Q})[{m}]"
    else:
        s += "(0,0,0)[0]"          # no seasonal term was supportable — reported, not hidden
    if spec.get("K"):
        s += f"+F{spec['K']}"
    if spec.get("trend") == "c" and (d + D) >= 1:
        s += "+drift"
    elif spec.get("trend") == "ct":
        s += "+trend"
    if spec.get("exog_wd"):
        s += "+WD"
    return s


def residual_burn_in(res, spec, period=M):
    """
    How many leading residuals to discard before testing them for autocorrelation.

    statsmodels runs the Kalman filter on the UNDIFFERENCED series, so the first
    d + D*m residuals are diffuse-initialisation prediction errors, not model errors - the
    very first one is literally the first observation. Trimming only `d` of them (which is
    ZERO for a (p,0,q)(P,1,Q)[12] model) leaves twelve values the size of the series itself
    in the sample, and Ljung-Box rejects whatever it is handed. That is what produced
    revenue_SV's p=0.000 in v6: with the correct burn-in the identical residuals give
    p=0.60, so the failure was in the diagnostic, not in the fit.
    """
    d = int(spec["order"][1])
    D = int(spec["seasonal_order"][1]) * int(spec["seasonal_order"][3] or 0)
    return max(d + D, int(getattr(res, "loglikelihood_burn", 0) or 0), 1)


def cv_rolling_stats(y_masked, spec, context=""):
    """
    Rolling-origin, multi-horizon MAE inside the TRAINING window only.

    This exists because AICc physically cannot compare a D=0 model against a D=1 one - they
    are fitted to different numbers of observations. Something has to choose between them,
    and a seasonal-strength threshold on its own is not it: STL measures strength 1.00 on 24
    points of pure noise, 0.56 at 36 and 0.24 at 48 on the same series, so a fixed cut-off
    imposes a seasonal difference on short windows and drops it on long ones. Held-out error
    is the criterion that actually matters, and it leaks nothing: every point scored here is
    one the fold already owns.

    Each origin is scored over CV_HORIZON steps, not one. A one-step criterion picks the
    spec that wins WF1 and is indifferent to the twelve-month horizon the annual plan is
    built on - and seasonal differencing is precisely the choice that costs little at h=1
    and pays at h=12.

    The INNER training windows are floored at CV_MIN_TRAIN_MONTHS, not at MIN_TRAIN_MONTHS.
    Those two numbers answer different questions: MIN_TRAIN_MONTHS is how much history a
    fold must have before its forecast is allowed to count, while this one is only how much
    a model needs in order to be fitted at all. Tying them together quietly disabled the
    whole mechanism exactly where it mattered most - at a 24-month window there is nothing
    left over, so this function returned NaN, which meant that at the earliest origins the
    drift term was never scored, the seasonal veto never fired, and the bias correction was
    never estimated. At a 30-month window it left room for exactly ONE origin, which is not
    enough to produce a standard error and therefore also yielded no correction. With the
    floor at 15 both windows get the four origins the shrinkage rule was designed around.

    Returns (MAE, mean signed error, standard error of that mean). The signed part is what
    the bias correction uses: err = actual - pred, so a model running high produces a
    negative mean here. The standard error is what stops the correction firing on noise.
    """
    H = int(CONFIG["CV_HORIZON"])
    n_origins = int(CONFIG["CV_ORIGINS"])
    y_masked = np.asarray(y_masked, dtype=float)
    n = len(y_masked)
    obs_idx = np.where(np.isfinite(y_masked))[0]
    cv_min = int(CONFIG.get("CV_MIN_TRAIN_MONTHS", CONFIG["MIN_TRAIN_MONTHS"]))
    if obs_idx.size < cv_min + 2:
        return np.nan, np.nan, np.nan
    H = int(min(H, max(1, obs_idx.size - cv_min)))
    exog = build_exog(np.arange(n), spec["K"], WD_FULL, use_wd=spec.get("exog_wd"))
    errs, per_origin = [], []
    for j in range(n_origins):
        k = H + j
        if k > obs_idx.size or obs_idx.size - k < cv_min:
            break
        cut = int(obs_idx[-k])
        y = y_masked.copy()
        y[cut:] = np.nan                    # hide the origin month and everything after it
        try:
            mod, res = fit_sarimax(y, spec["order"], spec["seasonal_order"], exog,
                                   f"cv[{context}]", trend=spec.get("trend"))
            path = smoothed_path(mod, res.params, n)
            cur = [float(y_masked[int(pos)]) - float(path[int(pos)])
                   for pos in obs_idx[obs_idx >= cut][:H] if np.isfinite(path[int(pos)])]
            if cur:
                per_origin.append(np.asarray(cur, dtype=float))
                errs.extend(cur)
        except Exception as e:
            log_failure(f"cv[{context}]", e)
    if not errs:
        return np.nan, np.nan, np.nan
    e = np.asarray(errs, dtype=float)
    mae = float(np.mean(np.abs(e)))

    # The bias is a RECENCY-WEIGHTED mean over origins, not a flat one. j=0 hides the fewest
    # months, so it is the origin closest to the forecast date; weighting geometrically makes
    # the correction local. A flat average is a global correction: it spreads a level shift
    # evenly over a year of history and therefore tracks nothing.
    lam = float(CONFIG.get("BIAS_RECENCY_LAMBDA", 1.0))
    means = np.array([o.mean() for o in per_origin], dtype=float)
    w = np.array([lam ** j for j in range(means.size)], dtype=float)
    wsum = float(w.sum())
    bias = float(np.sum(w * means) / wsum)
    if means.size > 1:
        var = float(np.sum(w * (means - bias) ** 2) / wsum)
        se = float(np.sqrt(var / (means.size - 1)))
    else:
        # ONE origin cannot produce a standard error for the mean ACROSS origins, and the
        # within-origin one is a different quantity entirely: six consecutive months sitting
        # on the wrong side of a level shift have a tiny spread, so the shrink read them as a
        # near-certain tilt. That is how qty_total at the 30-month origin - which has room for
        # exactly one CV origin - earned a -8,808 correction on a series averaging 18,138:
        # half the level subtracted from every forecast, driving six of them below zero.
        # Report the uncertainty as unbounded; the caller then declines to correct on it.
        se = np.inf
    return mae, bias, se


def prefer_screened(winners):
    """
    Stage-3 candidates, with any differencing group whose winner failed the plausibility
    screen demoted below one whose winner passed.

    Without this, a group in which EVERY candidate was implausible still entered the
    held-out comparison on equal terms - and won it. qty_total at the 30-month origin is the
    worked example: every (0,1,0)[12] candidate forecast below zero on a series that has
    never been below 6,186, the group was handed through as a flagged fallback anyway, and
    it beat a (1,0) group holding two dozen perfectly plausible winners. That single
    ordering accounted for most of the screen-failure fallbacks and for the negative
    forecasts Section 9.4 was clipping.
    """
    clean = [w for w in winners if not w.get("screen_failed", False)]
    return clean if clean else winners


def select_sarima_spec(y_masked, series_name, context, horizon=None, fast=None):
    """
    Order search on the GAPPED series.

      stage 0 - candidate differencing orders are enumerated by test: one with no seasonal
                difference, one with, each with its own regular d from the unit-root rule.
      stage 1 - for EACH (d, D), structure (p, q, P, Q, K) is ranked by AICc - but SEPARATELY
                for candidates that carry a seasonal ARMA term and candidates that do not,
                giving two finalists per group instead of one.
      stage 1b - the better AICc of the two takes the group, EXCEPT that a seasonal winner
                on fewer than SEASONAL_TRUST_CYCLES cycles of history must ALSO beat the
                non-seasonal finalist on rolling-origin, multi-horizon held-out error by
                SEASONAL_CV_MARGIN. A tie goes to the simpler model.
      stage 2 - the surviving winner has its deterministic trend (drift / linear trend) and
                its working-days regressor switched on and off, still at the same (d, D).
      stage 3 - the group winners are compared by the same rolling-origin error, because
                AICc cannot compare across differencing orders. With one group there is
                nothing to compare and the stage is skipped.

    Stage 1b is the answer to a real regression. Offering seasonal ARMA terms from two
    cycles of history instead of three was correct - it stopped the search disqualifying
    seasonality on most folds before anything could weigh it - but it handed the decision to
    AICc, and AICc is an in-sample, effectively one-step criterion. A (P,Q)[12] term at 24-30
    months can fit the two cycles it has seen and buy nothing out of sample, and that is
    exactly what happened: seasonal usage went from 13% to 28% of fits while WF12 bias went
    from -10.2% to -17.5%. Held-out multi-horizon error is the criterion that can tell the
    difference, so the seasonal term is still always OFFERED and always SCORED - it just has
    to earn the selection on a short window instead of winning it on in-sample fit.

    The veto is deliberately narrow. Replacing AICc with held-out CV for the whole structure
    search was tried and is worse: ~24 held-out points cannot rank two dozen structures, and
    doing it cost revenue_SV its seasonal MA term at 36 months and about 10% of its WF1
    accuracy. From SEASONAL_TRUST_CYCLES cycles upward, AICc keeps the decision.

    The plausibility screen matches the situation automatically:
       * series has a gap  -> gap_plausible() on the smoothed path, bounded to `horizon`
       * series has no gap -> future_plausibility() on an h-step forecast
    and on a series that is non-negative in-sample both of them refuse a negative path
    outright, rather than leaving it to the clip in postprocess().
    """
    fast = CONFIG["FAST_MODE"] if fast is None else fast
    n = len(y_masked)
    has_gap = bool((~np.isfinite(y_masked)).any())
    horizon = horizon or CONFIG["WF12_HORIZON"]
    nonneg = bool(SERIES_CLIP.get(series_name, False))

    n_obs = int(np.isfinite(y_masked).sum())
    v_train = longest_contiguous_observed(y_masked)

    Ks = range(int(CONFIG["MAX_FOURIER_K"]) + 1)
    exog_by_K = {(K, ew): build_exog(np.arange(n), K, WD_FULL, use_wd=ew)
                 for K in Ks for ew in (True, False)}
    fut_pos = np.arange(n, n + horizon)
    fut_idx = pd.date_range(FULL_INDEX[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    fut_wd = working_days(fut_idx)
    fexog_by_K = {(K, ew): build_exog(fut_pos, K, fut_wd, use_wd=ew)
                  for K in Ks for ew in (True, False)}

    stats = {"tried": 0, "failed": 0, "implausible": 0, "negative": 0}
    cv_cache = {}

    def cv_of(cand):
        """Held-out CV for a candidate, memoised - stages 1b, 2 and 3 ask for the same
        specs repeatedly and each call costs CV_ORIGINS full fits."""
        key = (tuple(cand["order"]), tuple(cand["seasonal_order"]), cand["K"],
               cand.get("trend"), bool(cand.get("exog_wd")))
        if key not in cv_cache:
            cv_cache[key] = cv_rolling_stats(y_masked, cand, context=context)
        return cv_cache[key]

    def evaluate(cand):
        """(screened AICc, raw AICc, whether the forecast stayed non-negative)."""
        key = (cand["K"], bool(cand["exog_wd"]))
        try:
            mod, res = fit_sarimax(y_masked, cand["order"], cand["seasonal_order"],
                                   exog_by_K[key], f"select[{context}]", trend=cand["trend"])
            Dv = cand["seasonal_order"][1] if cand["seasonal_order"][3] else 0
            score = aicc_of(res, n_obs, cand["order"][1], Dv)
            stats["tried"] += 1
            if not np.isfinite(score):
                return None, None, False
            if has_gap:
                path = smoothed_path(mod, res.params, n)
                ok = gap_plausible(path, y_masked, horizon=horizon, nonneg=nonneg)
                probe = np.asarray(path, float)[~np.isfinite(y_masked)][:horizon]
            else:
                probe = np.asarray(res.get_forecast(steps=horizon,
                                                    exog=fexog_by_K[key]).predicted_mean, float)
                ok = future_plausibility(probe, y_masked[np.isfinite(y_masked)],
                                         nonneg=nonneg)["ok"]
            neg_free = bool(np.isfinite(probe).all() and (not nonneg or probe.min() >= 0))
            if not neg_free:
                stats["negative"] += 1
            if not ok:
                stats["implausible"] += 1
                return None, score, neg_free
        except Exception as e:
            stats["failed"] += 1
            log_failure(f"select[{context}] {cand}", e)
            return None, None, False
        return score, score, neg_free

    def search_group(d, D):
        """Best structure at this fixed (d, D): AICc within each of the two families, then
        held-out error between them."""
        trends = trend_options(d, D)
        base_trend, base_exog = trends[0], bool(CONFIG["USE_WORKING_DAYS"])
        pool = {True: None, False: None}        # keyed by "carries a seasonal ARMA term"
        fallback = {True: None, False: None}
        for spec in candidate_specs(n_obs, d, D, True, fast):
            cand = {**spec, "trend": base_trend, "exog_wd": base_exog}
            score, raw, neg_free = evaluate(cand)
            sarma = bool(spec["seasonal_order"][0] or spec["seasonal_order"][2])
            if raw is not None:
                cur = fallback[sarma]
                # A fallback that stays non-negative beats a better-fitting one that does not:
                # if the screen has to be overruled, overrule it with the least absurd option.
                if cur is None or (neg_free, -raw) > (cur["neg_free"], -cur["aicc"]):
                    fallback[sarma] = {**cand, "aicc": raw, "neg_free": neg_free}
            if score is not None and (pool[sarma] is None or score < pool[sarma]["aicc"]):
                pool[sarma] = {**cand, "aicc": score}

        cand_s, cand_p = pool[True], pool[False]
        finalists = [c for c in (cand_s, cand_p) if c is not None]
        best = min(finalists, key=lambda c: c["aicc"]) if finalists else None
        cycles = n_obs / float(M)
        if (best is cand_s and cand_p is not None
                and cycles < float(CONFIG["SEASONAL_TRUST_CYCLES"])):
            # AICc has bought a seasonal ARMA term on less history than it can judge one on.
            # The term is kept only if held-out, multi-horizon error agrees by a margin; a
            # tie goes to the simpler structure. The margin lives here, in the comparison,
            # rather than in the candidate grid - the term is still fitted, screened, scored
            # and reported either way.
            margin = float(CONFIG["SEASONAL_CV_MARGIN"])
            mae_s, bias_s, se_s = cv_of(cand_s)
            mae_p, bias_p, se_p = cv_of(cand_p)
            if np.isfinite(mae_s) and np.isfinite(mae_p):
                if mae_s <= mae_p * (1.0 - margin):
                    best = {**cand_s, "cv_mae": mae_s, "cv_bias": bias_s, "cv_bias_se": se_s}
                else:
                    best = {**cand_p, "cv_mae": mae_p, "cv_bias": bias_p, "cv_bias_se": se_p}
                best["seasonal_cv_margin"] = margin
                best["seasonal_cv_ratio"] = float(mae_s / mae_p) if mae_p > 0 else np.nan

        if best is None:
            # Every structure was screened out. Falling back to a hardcoded SARIMA(1,d,0)
            # discards the whole search; the best-fitting candidate is the better answer,
            # and it is flagged so the reader knows the screen was not satisfied.
            cands = [c for c in fallback.values() if c is not None]
            if not cands:
                return None
            fb = dict(max(cands, key=lambda c: (c["neg_free"], -c["aicc"])))
            fb.pop("neg_free", None)
            fb["screen_failed"] = True
            return fb

        struct = {k: best[k] for k in ("order", "seasonal_order", "K")}
        already = (best["trend"], best["exog_wd"])
        exogs = ((True, False) if (CONFIG["EXOG_SELECTION"] and CONFIG["USE_WORKING_DAYS"])
                 else (base_exog,))
        # The working-days regressor is a same-period covariate, so AICc judges it fairly.
        for ew in exogs:
            if (base_trend, ew) == already:
                continue
            score, _, _ = evaluate({**struct, "trend": base_trend, "exog_wd": ew})
            if score is not None and score < best["aicc"]:
                best = {**best, **struct, "trend": base_trend, "exog_wd": ew, "aicc": score}
                # the held-out numbers belonged to the other exog setting - drop them so they
                # are recomputed for the spec that is actually going to be used
                for stale in ("cv_mae", "cv_bias", "cv_bias_se"):
                    best.pop(stale, None)
        # The deterministic trend is NOT judged by AICc. A trend term always improves
        # in-sample fit, and AICc is effectively a one-step criterion, so it will happily buy
        # a slope that is extrapolated twelve times over in Section 12. Held-out multi-step
        # error is the criterion that reflects that cost.
        if len(trends) > 1 and str(CONFIG["TREND_SELECTION"]).lower() == "cv":
            scored = []
            for tr in trends:
                cand = {**struct, "trend": tr, "exog_wd": best["exog_wd"]}
                if evaluate(cand)[0] is None:
                    continue
                mae, bias, se = cv_of(cand)
                if np.isfinite(mae):
                    scored.append(({**best, **cand, "aicc": best["aicc"], "cv_mae": mae,
                                    "cv_bias": bias, "cv_bias_se": se}, mae))
            if scored:
                best = min(scored, key=lambda t: t[1])[0]
        return best

    # ---- stage 0: enumerate the differencing orders worth considering -------------------
    fs = seasonal_strength_of(v_train, M, context)
    # d=2 is only allowed once there are 3 full cycles to judge it on. At n=24 a second
    # difference is what produced forecasts of -34.8M on a series whose smallest observed
    # month is +11M, all of which then had to be clipped at zero.
    d_plain = int(min(select_d(v_train, max_d=(2 if n_obs >= 3 * M else 1), context=context), 2))
    groups = [(d_plain, 0)]
    if n_obs >= (float(CONFIG.get("SEASONAL_MIN_CYCLES", 2.0)) + 0.5) * M:
        v_sd = np.diff(v_train, M)
        d_seas = int(min(select_d(v_sd, max_d=1, context=context), 1))
        groups.append((d_seas, 1))
    if str(CONFIG["DD_SELECTION"]).lower() != "cv" and len(groups) > 1:
        # test-only mode: keep the seasonal group iff measured strength supports it
        D_test, _ = select_D(v_train, context=context)
        groups = [groups[1]] if D_test else [groups[0]]

    # ---- stages 1-2: best structure inside each differencing order ----------------------
    winners = []
    for (dd, DD) in groups:
        w = search_group(dd, DD)
        if w is not None:
            w.update({"d": dd, "D": DD})
            winners.append(w)

    # ---- stage 3: choose between differencing orders by held-out error ------------------
    # A group whose winner failed the plausibility screen is demoted first: it is a
    # flagged fallback, not a peer of a group that produced something plausible.
    ranked = prefer_screened(winners)
    best = None
    if len(ranked) == 1:
        best = ranked[0]
    elif ranked:
        for w in ranked:
            if not np.isfinite(w.get("cv_mae", np.nan)):
                w["cv_mae"], w["cv_bias"], w["cv_bias_se"] = cv_of(w)
        scored = [w for w in ranked if np.isfinite(w.get("cv_mae", np.nan))]
        if scored:
            best = min(scored, key=lambda w: w["cv_mae"])
        else:
            best = min(ranked, key=lambda w: w["aicc"] if np.isfinite(w["aicc"]) else np.inf)

    # Bias correction, measured on the TRAINING window only. `cv_bias` is the mean signed
    # held-out error of this exact spec over CV_ORIGINS rolling origins; adding a share of it
    # to the forecast removes the part of the model's tilt that is persistent. It cannot
    # anticipate a level shift that has not happened yet.
    #
    # The share is not fixed. It is shrunk by the signal-to-noise of the estimate itself,
    # b^2 / (b^2 + se^2), so a bias that is large next to its own standard error is applied
    # nearly in full while one indistinguishable from zero is applied hardly at all. A flat
    # weight corrects the real tilt and injects the sampling noise of ~24 held-out errors
    # everywhere else, which shows up as a worse MASE for a better-looking bias.
    if best is not None:
        if not np.isfinite(best.get("cv_bias", np.nan)) and CONFIG["BIAS_CORRECTION"]:
            best["cv_mae"], best["cv_bias"], best["cv_bias_se"] = cv_of(best)
        b = float(best.get("cv_bias", np.nan))
        se = float(best.get("cv_bias_se", np.nan))
        if CONFIG["BIAS_CORRECTION"] and np.isfinite(b):
            # An unusable standard error means NO correction, not a full one. The old rule
            # read a non-finite `se` as "perfectly certain" and applied the whole estimate,
            # which is exactly backwards - a bias measured on a single rolling origin is the
            # one that deserves the least trust.
            if not np.isfinite(se):
                shrink = 0.0
            elif se <= 0:
                shrink = 1.0
            else:
                shrink = b * b / (b * b + se * se)
            best["bias_shrink"] = float(shrink)
            adj = float(CONFIG["BIAS_CORRECTION_WEIGHT"]) * b * shrink
            # A held-out bias worth more than BIAS_CORRECTION_MAX_FRAC of the level is not a
            # tilt this correction can remove; it is a level shift, and extrapolating it is
            # how a single unlucky window once produced an adjustment of half the series.
            # The estimate is still reported in full - only what gets APPLIED is bounded.
            lvl = float(np.mean(np.abs(y_masked[np.isfinite(y_masked)])))
            cap = float(CONFIG.get("BIAS_CORRECTION_MAX_FRAC", np.inf)) * lvl
            if np.isfinite(cap) and abs(adj) > cap:
                best["bias_capped"] = True
                adj = float(np.sign(adj) * cap)
            best["bias_adj"] = adj
        else:
            best["bias_shrink"] = 0.0
            best["bias_adj"] = 0.0

    if best is None:
        best = {"order": (1, d_plain, 0), "seasonal_order": (0, 0, 0, 0), "K": 1,
                "trend": trend_options(d_plain, 0)[0], "exog_wd": bool(CONFIG["USE_WORKING_DAYS"]),
                "aicc": np.nan, "cv_mae": np.nan, "d": d_plain, "D": 0, "screen_failed": True,
                "bias_adj": 0.0}
        log_failure(f"select[{context}]",
                    RuntimeError("every candidate failed; falling back to SARIMA(1,d,0)+F1"))
    best.update({"n_candidates": stats["tried"], "n_failed": stats["failed"],
                 "n_implausible": stats["implausible"], "n_negative": stats["negative"],
                 "screen": "gap" if has_gap else "future",
                 "n_groups": len(groups), "seasonal_strength_train": fs})
    best.setdefault("screen_failed", False)
    for k in ("cv_mae", "cv_bias", "cv_bias_se"):
        best.setdefault(k, np.nan)
    best.setdefault("bias_shrink", 0.0)
    best.setdefault("bias_adj", 0.0)
    best.setdefault("bias_capped", False)
    return best


def wf_spec_for(series_name, s, origin):
    """
    Spec for a walk-forward origin, refreshed every SPEC_REFRESH_MONTHS as the window grows.
    The reference window always ENDS AT OR BEFORE the origin (no leakage), so a 36-month
    origin is not stuck with a spec chosen on 24 months.
    """
    mt, rf = CONFIG["MIN_TRAIN_MONTHS"], CONFIG["SPEC_REFRESH_MONTHS"]
    ref = mt + ((origin - mt) // rf) * rf
    key = (series_name, "WF", ref)
    if key not in SPEC_CACHE:
        tr = np.zeros(len(s), bool)
        tr[:ref] = True
        SPEC_CACHE[key] = select_sarima_spec(masked_values(s, tr), series_name,
                                             f"{series_name}|WF@{ref}m")
    return SPEC_CACHE[key], ref


def sarima_fold(s, train_mask, test_mask, series_name, spec=None, context=""):
    """
    One code path serves both schemes because everything outside train_mask is NaN:
      interior gap (LOFO) -> the smoother interpolates from both sides
      trailing gap  (WF)  -> the smoother reduces to the h-step-ahead forecast
    """
    y = masked_values(s, train_mask)
    n = len(y)
    if spec is None:
        spec = select_sarima_spec(y, series_name, context)
    exog = build_exog(np.arange(n), spec["K"], WD_FULL, use_wd=spec.get("exog_wd"))
    try:
        mod, res = fit_sarimax(y, spec["order"], spec["seasonal_order"], exog,
                               f"fit[{context}]", trend=spec.get("trend"))
        fitted = smoothed_path(mod, res.params, n)
        # Applied ONLY outside the training window: the correction is an out-of-sample
        # adjustment, and adding it to in-sample fitted values would corrupt the smoothed
        # path this fold is scored on. Its size comes from training data alone.
        adj = float(spec.get("bias_adj", 0.0) or 0.0)
        if adj:
            fitted = fitted + adj * (~np.asarray(train_mask, bool)).astype(float)
        status = "ok"
    except Exception as e:
        log_failure(f"fit[{context}] {spec_label(spec)}", e)
        fitted = np.full(n, np.nan)
        status = f"failed:{type(e).__name__}"
    # Clip (and audit) only the values this fold actually predicts. postprocess() used to be
    # handed the whole 48-month smoothed path, so the clipping audit in 9.4 counted negative
    # in-sample fitted values and months past the test window as if they were forecasts.
    te = np.asarray(test_mask, bool)
    pred = postprocess(fitted[te], series_name, context, model="SARIMA")
    return pred, spec, status


def seasonal_naive_fold(s, train_mask, test_mask, series_name, period=M):
    y = masked_values(s, train_mask)
    n = len(y)
    work = y.copy()
    preds = np.full(n, np.nan)
    for pos in np.where(np.asarray(test_mask, bool))[0]:
        val, ref = np.nan, pos - period
        while ref >= 0:
            if np.isfinite(work[ref]):
                val = work[ref]
                break
            ref -= period
        if not np.isfinite(val):
            seen = np.where(np.isfinite(work[:pos]))[0]
            if len(seen):
                val = work[seen[-1]]
        preds[pos] = val
        work[pos] = val
    te = np.asarray(test_mask, bool)
    status = "ok" if np.isfinite(preds[te]).all() else "insufficient_history"
    return postprocess(preds[te], series_name, "snaive", model="SeasonalNaive"), status


def block_bootstrap_ci(d, n_boot=None, seed=None, alpha=0.05, groups=None):
    """
    Moving-block bootstrap. Expanding-window folds overlap heavily, so an i.i.d. bootstrap
    understates the uncertainty. Block length ~ n^(1/3), the usual default.

    `groups` marks which entries belong to the same series. Blocks are drawn WITHIN a group
    and never straddle a boundary: the input is ordered by (series, fold), so a block that
    runs off the end of revenue_INV and into revenue_PLC is not a stretch of any real time
    series, and the serial dependence the block bootstrap exists to preserve is not there to
    preserve. Block length is also computed per group, because one global length taken from
    the pooled n can equal the entire length of a short group — at 3 WF12 folds per series
    that leaves exactly one possible block and the bootstrap stops resampling at all.
    """
    n_boot = CONFIG["N_BOOT"] if n_boot is None else n_boot
    seed = CONFIG["SEED"] if seed is None else seed
    d = np.asarray(d, dtype=float)
    groups = np.zeros(d.size, dtype=int) if groups is None else np.asarray(groups)
    ok = np.isfinite(d)
    d, groups = d[ok], groups[ok]
    n = d.size
    if n < 4:
        return np.nan, np.nan, n, np.nan
    rng = np.random.default_rng(seed)
    parts = []
    for g in pd.unique(groups):
        dg = d[groups == g]
        ng = dg.size
        if ng == 0:
            continue
        bg = int(min(max(1, int(np.ceil(ng ** (1 / 3)))), ng))
        nb = int(np.ceil(ng / bg))
        starts = rng.integers(0, ng - bg + 1, size=(n_boot, nb))
        idx = (starts[:, :, None] + np.arange(bg)[None, None, :]).reshape(n_boot, -1)[:, :ng]
        parts.append(dg[idx])
    if not parts:
        return np.nan, np.nan, n, np.nan
    means = np.concatenate(parts, axis=1).mean(axis=1)
    lo, hi = np.percentile(means, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    p = 2 * min(float((means <= 0).mean()), float((means >= 0).mean()))
    return float(lo), float(hi), n, min(1.0, p)


MIN_PI_POOL = 8


def oos_residual_pool(series_name, model_name):
    """Out-of-sample errors by horizon, taken from the walk-forward evaluation.

    `err = actual - pred`, so `pred + quantile(err)` is a band built from errors the model
    actually made on data it had not seen. WF12 contributes one error per fold at each
    horizon (3 folds here), too thin to read a 5th/95th percentile from, so the WF1 errors
    are scaled by sqrt(h) and pooled in when the WF12 pool is smaller than MIN_PI_POOL.
    That scaling assumes random-walk error growth; it is an approximation and is labelled
    as one on the chart rather than hidden.
    """
    pool = {}
    d12 = resid_df[(resid_df["series"] == series_name) & (resid_df["model"] == model_name)
                   & (resid_df["scheme"] == "WF12")]
    d1 = resid_df[(resid_df["series"] == series_name) & (resid_df["model"] == model_name)
                  & (resid_df["scheme"] == "WF1")]
    base = d1["err"].to_numpy(dtype=float)
    base = base[np.isfinite(base)]
    for h in range(1, HORIZON + 1):
        e = d12[d12["h"] == h]["err"].to_numpy(dtype=float)
        e = e[np.isfinite(e)]
        if e.size < MIN_PI_POOL and base.size >= 3:
            e = np.concatenate([e, base * np.sqrt(h)])
        pool[h] = e if e.size else np.array([0.0])
    return pool


def oos_interval(point, pool, alpha=0.10):
    """90% band = point forecast + the empirical 5th/95th percentile of OUT-OF-SAMPLE error
    at that horizon. In-sample residual intervals are systematically too narrow, which is
    why the walk-forward errors are the ones used."""
    point = np.asarray(point, dtype=float)
    lo = np.empty(point.size)
    hi = np.empty(point.size)
    for i in range(point.size):
        e = np.asarray(pool.get(i + 1, np.array([0.0])), dtype=float)
        e = e[np.isfinite(e)]
        if e.size == 0:
            e = np.array([0.0])
        q_lo, q_hi = np.percentile(e, [100 * alpha / 2, 100 * (1 - alpha / 2)])
        lo[i], hi[i] = point[i] + q_lo, point[i] + q_hi
    return lo, hi


def sarima_future(s, series_name, spec, usable=None, horizon=HORIZON, context="", pi_pool=None):
    y = s.astype(float).to_numpy().copy()
    if usable is not None:
        y[~np.asarray(usable, bool)] = np.nan
    n = len(y)
    exog = build_exog(np.arange(n), spec["K"], WD_FULL, use_wd=spec.get("exog_wd"))
    fexog = build_exog(np.arange(n, n + horizon), spec["K"], FUTURE_WD,
                       use_wd=spec.get("exog_wd"))
    _, res = fit_sarimax(y, spec["order"], spec["seasonal_order"], exog, f"future[{context}]",
                         trend=spec.get("trend"))
    fc = res.get_forecast(steps=horizon, exog=fexog)
    point = np.asarray(fc.predicted_mean, dtype=float) + float(spec.get("bias_adj", 0.0) or 0.0)
    if pi_pool is not None and CONFIG["PI_FROM_WALK_FORWARD"]:
        lo, hi = oos_interval(point, pi_pool, alpha=0.10)
        PI_SOURCE[series_name] = "out-of-sample walk-forward errors"
    else:
        # Fallback only. These are the model's own intervals, built from in-sample residual
        # variance, and they are systematically too narrow — Section 12's headline claim is
        # the walk-forward band above, which is what oos_residual_pool() exists to supply.
        ci = np.asarray(fc.conf_int(alpha=0.10), dtype=float)
        lo, hi = ci[:, 0], ci[:, 1]
        # setdefault, not assignment: Section 12.4 refits this same function without a pool
        # to test sensitivity, and must not relabel the band the headline forecast used.
        PI_SOURCE.setdefault(series_name, "model-based (in-sample residual variance)")
    return (postprocess(point, series_name, "future", model="SARIMA"),
            postprocess(lo, series_name, "future", model="SARIMA"),
            postprocess(hi, series_name, "future", model="SARIMA"), res)


def snaive_future(s, series_name, usable=None, horizon=HORIZON, period=M):
    """Honours `usable` so the Section 12.4 sensitivity test is not vacuous for this model."""
    y = s.astype(float).to_numpy().copy()
    if usable is not None:
        y[~np.asarray(usable, bool)] = np.nan
    tail, i = [], len(y) - 1
    while len(tail) < period and i >= 0:
        if np.isfinite(y[i]):
            tail.append(y[i])
        i -= 1
    tail = np.array(tail[::-1])                     # most recent `period` OBSERVED months
    if tail.size == 0:
        return np.full(horizon, np.nan)
    out = np.array([tail[(len(tail) - period + (i % period)) % len(tail)]
                    for i in range(horizon)])
    return postprocess(out, series_name, "future", model="SeasonalNaive")



def fy_of(ts):
    return fiscal_year(ts)


# ==================================================================================
# Everything below is the service wrapper. The modelling code above is unchanged.
# ==================================================================================

_MONTH_HINTS = ("month", "date", "period", "sales_order_date", "order_date")
_VALUE_HINTS = ("revenue", "amount", "sales", "net_amount", "value")
_QTY_HINTS = ("actual_units", "quantity", "qty", "units")


def _pick_col(df, hints, explicit=None):
    if explicit:
        if explicit not in df.columns:
            raise KeyError(f"column {explicit!r} is not in the frame; have {list(df.columns)}")
        return explicit
    lowered = {c.lower(): c for c in df.columns}
    for h in hints:
        if h in lowered:
            return lowered[h]
    for h in hints:
        for lc, orig in lowered.items():
            if h in lc:
                return orig
    return None


def _reset_run_state():
    global SPEC_CACHE, PI_SOURCE, resid_df, FULL_INDEX, WD_FULL, FUTURE_WD, SERIES_CLIP
    SPEC_CACHE = {}
    PI_SOURCE = {}
    resid_df = None
    FULL_INDEX = None
    WD_FULL = None
    FUTURE_WD = None
    SERIES_CLIP = {}
    for log in (FIT_LOG, FAILURES, CLIP_LOG, NOTES):
        log.clear()


def _monthly(df, month_col, value_col, index, mask=None):
    d = df if mask is None else df[mask]
    s = (d.groupby(pd.Grouper(key=month_col, freq="MS"))[value_col].sum()
           .reindex(index, fill_value=0.0).astype(float))
    s.index.name = "month"
    return s


def _fy_anomalies(df, month_col, value_col, fys):
    """Fiscal-year totals screened the way Section 3.7 screens them: a robust z-score
    on the year totals plus a deviation-from-median check. The notebook can also tell an
    extraction gap from a real decline using order counts and calendar coverage; an
    aggregated monthly frame does not carry that evidence, so this reports the deviation
    and says plainly that the cause is unverified."""
    out = []
    tot = (df.assign(_fy=fiscal_year_vec(df[month_col]))
             .groupby("_fy")[value_col].sum().reindex(fys))
    if tot.notna().sum() < 3:
        return out, tot
    z = robust_z(tot.to_numpy(dtype=float))
    med = float(np.nanmedian(tot.to_numpy(dtype=float)))
    for fy, val, zz in zip(tot.index, tot.to_numpy(dtype=float), z):
        if not np.isfinite(val) or med == 0:
            continue
        dev = 100.0 * (val / med - 1.0)
        if abs(zz) >= CONFIG["FY_ANOMALY_MAD_Z"] or abs(dev) >= CONFIG["FY_DEVIATION_WARN_PCT"]:
            out.append({
                "fiscal_year": int(fy),
                "deviation_pct_vs_median": round(dev, 1),
                "robust_z": (round(float(zz), 2) if np.isfinite(zz) else None),
                "verdict": "unverified",
                "message": (f"FY{int(fy)} sits {dev:+.1f}% from the median year. This frame "
                            f"cannot tell an extraction gap from a real business change - "
                            f"confirm against order counts and calendar coverage before "
                            f"trusting a forecast built on it."),
            })
    return out, tot


def _complete_fiscal_years(months):
    """Only fiscal years with all 12 months present are modelled - a partial year would
    otherwise read as a collapse."""
    fy = fiscal_year_vec(pd.Series(months))
    counts = pd.Series(months).groupby(fy.values).nunique()
    complete = sorted(int(f) for f, n in counts.items() if n == 12)
    # keep only a contiguous run, ending at the most recent complete year
    run = []
    for f in reversed(complete):
        if not run or run[-1] - f == 1:
            run.append(f)
        else:
            break
    return sorted(run)


def _pooled(rows):
    a = np.asarray([r["actual"] for r in rows], dtype=float)
    p = np.asarray([r["pred"] for r in rows], dtype=float)
    e = a - p
    den = np.abs(a).sum()
    return {
        "accuracy_pct": round(100.0 - (np.abs(e).sum() / den * 100.0), 1) if den else None,
        "wape_pct": round(np.abs(e).sum() / den * 100.0, 1) if den else None,
        "mae": float(np.abs(e).mean()),
    }


def run_forecast(sales_df, *, month_col=None, value_col=None, horizon=None,
                 fast=True, series_name="revenue_total", debug=False):
    """Fit, validate and forecast one monthly series. See get_sarima_forecast()."""
    global FULL_INDEX, WD_FULL, FUTURE_WD, SERIES_CLIP, resid_df, _DEBUG

    global HORIZON

    t0 = time.time()
    with _LOCK:
        _DEBUG = bool(debug)
        _reset_run_state()
        # FAST_MODE and HORIZON are read by the extracted code through module state, so
        # they are set for the duration of the run and restored afterwards.
        prev_fast, prev_h = CONFIG["FAST_MODE"], HORIZON
        CONFIG["FAST_MODE"] = bool(fast)
        if horizon:
            HORIZON = int(horizon)
        try:
            return _run(sales_df, month_col, value_col, horizon, fast, series_name, t0)
        except Exception as exc:                       # never take the API down
            log_failure("run_forecast", exc)
            return {
                "status": "error",
                "message": f"{type(exc).__name__}: {exc}",
                "fiscal_years": None, "forecast": None, "diagnostics": None,
                "warnings": list(NOTES),
                "runtime_seconds": round(time.time() - t0, 1),
            }
        finally:
            CONFIG["FAST_MODE"], HORIZON = prev_fast, prev_h
            _DEBUG = False


def _insufficient(msg, detail, t0):
    return {"status": "insufficient_history", "message": msg, "detail": detail,
            "fiscal_years": None, "forecast": None, "diagnostics": None,
            "warnings": list(NOTES), "runtime_seconds": round(time.time() - t0, 1)}


def _run(sales_df, month_col, value_col, horizon, fast, series_name, t0):
    global FULL_INDEX, WD_FULL, FUTURE_WD, SERIES_CLIP, resid_df

    if not isinstance(sales_df, pd.DataFrame) or sales_df.empty:
        return _insufficient("No rows supplied.", {"rows": 0}, t0)

    df = sales_df.copy()
    mcol = _pick_col(df, _MONTH_HINTS, month_col)
    if mcol is None:
        raise KeyError(f"no month/date column found; have {list(df.columns)}")
    vcol = _pick_col(df, _VALUE_HINTS, value_col) or _pick_col(df, _QTY_HINTS, value_col)
    if vcol is None:
        raise KeyError(f"no revenue/quantity column found; have {list(df.columns)}")

    df[mcol] = pd.to_datetime(df[mcol], errors="coerce")
    df = df[df[mcol].notna()].copy()
    df[mcol] = df[mcol].values.astype("datetime64[M]")
    df[mcol] = pd.to_datetime(df[mcol])
    df[vcol] = pd.to_numeric(df[vcol], errors="coerce").fillna(0.0)
    if df.empty:
        return _insufficient("Every row had an unparseable date.", {"rows": 0}, t0)

    months = sorted(df[mcol].unique())
    fys = _complete_fiscal_years(months)
    horizon = int(horizon or HORIZON)
    # Retain partial fiscal years; prediction must start after the last observed month.
    # Validation length is bounded by available history, independent of requested horizon.
    need = CONFIG["MIN_TRAIN_MONTHS"] + 1
    idx = pd.date_range(months[0], months[-1], freq="MS", name="month")
    if len(idx) < need:
        return _insufficient(f"Need at least {need} monthly observations.",
                             {"months_available": len(idx), "months_needed": need}, t0)

    FULL_INDEX = idx
    WD_FULL = working_days(FULL_INDEX)

    s = _monthly(df, mcol, vcol, FULL_INDEX)
    series_dict = {series_name: s}
    SERIES_CLIP = {series_name: bool(CONFIG["CLIP_NEGATIVE_PREDICTIONS"] and s.min() >= 0)}

    anomalies, fy_totals = _fy_anomalies(df, mcol, vcol, fys)
    for a in anomalies:
        note("DATA ANOMALY", a["message"])

    scale = naive_scale_fixed(s, CONFIG["MIN_TRAIN_MONTHS"])
    # LOFO is advisory only (it trains on months after the ones it predicts), so it is
    # not run here - it must never reach a production number.
    cfg = dict(CONFIG, RUN_LOFO=False, WF12_HORIZON=min(12, len(idx)-CONFIG["MIN_TRAIN_MONTHS"]))
    folds = make_folds(FULL_INDEX, fys, cfg)

    rows, preds = [], {}
    for f in folds:
        tr, te = f["train_mask"], f["test_mask"]
        y_true = s[te]
        ctx = f"{series_name}|{f['scheme']}|{f['fold']}"
        for model in ("SeasonalNaive", "SARIMA"):
            if model == "SeasonalNaive":
                pred, status = seasonal_naive_fold(s, tr, te, series_name)
            else:
                spec, _ref = wf_spec_for(series_name, s, f["origin"])
                pred, _used, status = sarima_fold(s, tr, te, series_name, spec=spec, context=ctx)
            preds[(model, f["scheme"], f["fold"])] = pd.Series(pred, index=s.index[te])
            rows.append({"model": model, "scheme": f["scheme"], "fold": f["fold"],
                         "status": status,
                         **core_metrics(y_true.to_numpy(), pred, scale)})

    metrics = pd.DataFrame(rows)
    ok = metrics[(metrics["status"] == "ok") & metrics["MAE"].notna()]
    complete = {k for k, n in ok.groupby(["scheme", "fold"])["model"].nunique().items() if n == 2}

    pair_rows = []
    for (model, scheme, fold), p in preds.items():
        if (scheme, fold) not in complete:
            continue
        st = metrics[(metrics["model"] == model) & (metrics["scheme"] == scheme)
                     & (metrics["fold"] == fold)]["status"]
        if st.empty or st.iloc[0] != "ok":
            continue
        for h, (dt, pv) in enumerate(p.items(), start=1):
            pair_rows.append({"series": series_name, "model": model, "scheme": scheme,
                              "fold": fold, "month": dt, "h": h,
                              "actual": float(s.loc[dt]), "pred": float(pv)})
    resid_df = pd.DataFrame(pair_rows, columns=["series", "model", "scheme", "fold", "month", "h", "actual", "pred"])
    resid_df["err"] = resid_df["actual"] - resid_df["pred"]

    # ---- diagnostics ------------------------------------------------------------------
    diag = {}
    for scheme in ("WF1", "WF12"):
        entry = {}
        for model in ("SARIMA", "SeasonalNaive"):
            g = resid_df[(resid_df["scheme"] == scheme) & (resid_df["model"] == model)]
            if g.empty:
                continue
            m = core_metrics(g["actual"].to_numpy(), g["pred"].to_numpy(), scale)
            den = float(np.abs(g["actual"].to_numpy()).mean())
            fold_mase = ok[(ok["scheme"] == scheme) & (ok["model"] == model)]["MASE"]
            entry[model] = {
                **_pooled(g.to_dict("records")),
                "mase_pooled": round(float(m["MASE"]), 3) if np.isfinite(m["MASE"]) else None,
                "mase_fold_mean": round(float(fold_mase.mean()), 3) if len(fold_mase) else None,
                "bias_pct": round(100.0 * float(g["err"].mean()) / den, 1) if den else None,
                "pct_folds_beating_naive": round(100.0 * float((fold_mase < 1).mean()), 1)
                                           if len(fold_mase) else None,
                "n_folds": int(g["fold"].nunique()),
            }
        # paired significance test on per-fold MASE
        wide = (ok[ok["scheme"] == scheme].pivot_table(index="fold", columns="model",
                                                       values="MASE"))
        sig = {"gap": None, "ci95": None, "p": None, "distinguishable": None}
        if {"SARIMA", "SeasonalNaive"}.issubset(wide.columns):
            d = (wide["SeasonalNaive"] - wide["SARIMA"]).dropna()
            if len(d) >= 4:
                lo, hi, n, p = block_bootstrap_ci(d.to_numpy(),
                                                  groups=np.zeros(len(d), dtype=int))
                sig = {"gap": round(float(d.mean()), 3),
                       "ci95": [None if not np.isfinite(lo) else round(lo, 3),
                                None if not np.isfinite(hi) else round(hi, 3)],
                       "p": None if not np.isfinite(p) else round(float(p), 4),
                       "distinguishable": bool(np.isfinite(lo) and lo > 0)}
            else:
                sig["gap"] = round(float(d.mean()), 3) if len(d) else None
        entry["vs_baseline"] = sig
        entry["beats_naive"] = (
            None if not entry.get("SARIMA") or not entry.get("SeasonalNaive")
            else bool(entry["SARIMA"]["mase_pooled"] < entry["SeasonalNaive"]["mase_pooled"])
        )
        diag[scheme] = entry

    # ---- production forecast -----------------------------------------------------------
    spec, ref = wf_spec_for(series_name, s, len(s) - 1)
    future_index = pd.date_range(FULL_INDEX[-1] + pd.offsets.MonthBegin(1),
                                 periods=horizon, freq="MS", name="month")
    FUTURE_WD = working_days(future_index)
    pool = oos_residual_pool(series_name, "SARIMA")
    point, lo, hi, res = sarima_future(s, series_name, spec, horizon=horizon,
                                       context=series_name, pi_pool=pool)

    p_lb = None
    try:
        burn = residual_burn_in(res, spec)
        r_lb = np.asarray(res.resid, float)[burn:]
        r_lb = r_lb[np.isfinite(r_lb)]
        lags = int(min(12, max(1, len(r_lb) // 4)))
        p_lb = float(acorr_ljungbox(r_lb, lags=[lags], return_df=True)["lb_pvalue"].iloc[0])
    except Exception as exc:
        log_failure(f"ljungbox[{series_name}]", exc)

    scr = future_plausibility(np.asarray(point, float), s.to_numpy(dtype=float),
                              nonneg=SERIES_CLIP.get(series_name, False))
    if not scr["ok"]:
        note("FORECAST FLAG", f"{series_name}: {scr['detail']}")

    last_fy_total = float(fy_totals.iloc[-1]) if len(fy_totals) else float("nan")
    annual = float(np.nansum(point))

    return {
        "status": "ok",
        "message": f"Forecast for {horizon} months from {future_index[0]:%Y-%m}.",
        "fiscal_years": {
            "used": [int(f) for f in fys],
            "label_convention": FY_LABEL,
            "start_month": FISCAL_START,
            "first_month": str(FULL_INDEX[0].date()),
            "last_month": str(FULL_INDEX[-1].date()),
            "n_months": int(len(FULL_INDEX)),
            "forecast_fiscal_year": int(fiscal_year(future_index[0])),
            "totals_by_fiscal_year": {int(k): float(v) for k, v in fy_totals.dropna().items()},
        },
        "forecast": {
            "series": series_name,
            "spec": spec_label(spec),
            "selected_on_months": int(ref) if ref is not None else None,
            "horizon": horizon,
            "months": [str(d.date()) for d in future_index],
            "point": [round(float(v), 2) for v in point],
            "lower_90": [round(float(v), 2) for v in lo],
            "upper_90": [round(float(v), 2) for v in hi],
            "interval_source": PI_SOURCE.get(series_name),
            "annual_total": round(annual, 2),
            "annual_yoy_pct": (round(100.0 * (annual / last_fy_total - 1.0), 1)
                               if np.isfinite(last_fy_total) and last_fy_total else None),
            "plausibility_ok": bool(scr["ok"]),
            "plausibility_detail": scr["detail"] or None,
        },
        "diagnostics": {
            "wf1": diag.get("WF1"),
            "wf12": diag.get("WF12"),
            "ljung_box_p": None if p_lb is None else round(p_lb, 4),
            "residuals_clean": None if p_lb is None else bool(p_lb >= 0.05),
            "negative_predictions_clipped": int(sum(c["n_clipped"] for c in CLIP_LOG)),
            "spec_screen_failed": bool(spec.get("screen_failed", False)),
            "fit_warnings": len(FIT_LOG),
            "fit_failures": len(FAILURES),
            "mase_scale": round(float(scale), 4) if np.isfinite(scale) else None,
            "fast_mode": bool(fast),
        },
        "data_anomalies": anomalies,
        "warnings": list(NOTES),
        "runtime_seconds": round(time.time() - t0, 1),
    }
