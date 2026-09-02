import { useEffect, useState } from 'react'
import './App.css'

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

function App() {
  const [dashboard, setDashboard] = useState<DashboardData>({
    total_units: 0,
    total_revenue: 0,
    forecast_accuracy: 0,
    top_product: '',
  })

  const [sales, setSales] = useState<SalesData[]>([])
  const [products, setProducts] = useState<ProductData[]>([])

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
  }, [])

  // Use the largest value to calculate bar heights dynamically.
  const maxSalesValue =
    sales.length > 0
      ? Math.max(
          ...sales.flatMap((item) => [
            item.actual_units,
            item.forecast_units,
          ]),
        )
      : 200

  // Revenue chart calculations
  const chartWidth = 500
  const chartHeight = 180
  const chartPadding = 8

  const maxRevenue =
    sales.length > 0
      ? Math.max(...sales.map((item) => item.revenue))
      : 1

  const minRevenue =
    sales.length > 0
      ? Math.min(...sales.map((item) => item.revenue))
      : 0

  const revenueRange = Math.max(maxRevenue - minRevenue, 1)

  const revenuePoints = sales.map((item, index) => {
    const x =
      sales.length === 1
        ? chartWidth / 2
        : (index / (sales.length - 1)) *
            (chartWidth - chartPadding * 2) +
          chartPadding

    const y =
      chartHeight -
      ((item.revenue - minRevenue) / revenueRange) *
        (chartHeight - chartPadding * 2) -
      chartPadding

    return {
      x,
      y,
    }
  })

  const revenueLinePoints = revenuePoints
    .map((point) => `${point.x},${point.y}`)
    .join(' ')

  const revenueAreaPoints =
    revenuePoints.length > 0
      ? `${revenueLinePoints} ${chartWidth - chartPadding},${chartHeight} ${chartPadding},${chartHeight}`
      : ''

  return (
    <div className="app">
      {/* SIDEBAR */}
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">M</div>

          <div>
            <div className="brand-name">MISSUBIBI</div>
            <div className="brand-subtitle">Sales Intelligence</div>
          </div>
        </div>

        <nav className="navigation">
          <div className="nav-section-title">MAIN</div>

          <button className="nav-item active">
            <span>▦</span>
            Overview
          </button>

          <button className="nav-item">
            <span>⌁</span>
            Sales Forecast
          </button>

          <button className="nav-item">
            <span>¥</span>
            Revenue
          </button>

          <button className="nav-item">
            <span>▤</span>
            Inventory Risk
          </button>

          <div className="nav-section-title analysis-title">
            ANALYSIS
          </div>

          <button className="nav-item">
            <span>◈</span>
            Products
          </button>

          <button className="nav-item">
            <span>♙</span>
            Customers
          </button>

          <button className="nav-item">
            <span>◎</span>
            Forecast Accuracy
          </button>
        </nav>

        <div className="model-status">
          <span className="status-dot" />

          <div>
            <strong>AI Model Online</strong>
            <span>Last updated just now</span>
          </div>
        </div>
      </aside>

      {/* MAIN CONTENT */}
      <main className="main">
        {/* HEADER */}
        <header className="header">
          <div>
            <div className="breadcrumb">
              DASHBOARD / OVERVIEW
            </div>

            <h1>Sales Intelligence Dashboard</h1>

            <p>
              AI-powered sales order forecasting and analysis
            </p>
          </div>

          <div className="header-right">
            <button className="period-selector">
              FY2025
              <span>⌄</span>
            </button>

            <div className="user-avatar">GS</div>
          </div>
        </header>

        {/* KPI CARDS */}
        <section className="kpi-grid">
          <div className="kpi-card">
            <div className="kpi-header">
              <span>Total Units</span>
              <div className="kpi-icon">▦</div>
            </div>

            <div className="kpi-value">
              {dashboard.total_units.toLocaleString()}
            </div>

            <div className="kpi-change positive">
              ↑ 8.4%
              <span>vs previous period</span>
            </div>
          </div>

          <div className="kpi-card">
            <div className="kpi-header">
              <span>Forecast Revenue</span>
              <div className="kpi-icon">¥</div>
            </div>

            <div className="kpi-value">
              ¥
              {(dashboard.total_revenue / 1_000_000).toFixed(
                2,
              )}
              M
            </div>

            <div className="kpi-change positive">
              ↑ 6.2%
              <span>vs previous period</span>
            </div>
          </div>

          <div className="kpi-card">
            <div className="kpi-header">
              <span>Forecast Accuracy</span>
              <div className="kpi-icon">◎</div>
            </div>

            <div className="kpi-value">
              {dashboard.forecast_accuracy.toFixed(1)}%
            </div>

            <div className="kpi-change positive">
              ↑ 2.1%
              <span>model performance</span>
            </div>
          </div>

          <div className="kpi-card">
            <div className="kpi-header">
              <span>Top Product</span>
              <div className="kpi-icon">★</div>
            </div>

            <div className="kpi-value product-kpi">
              {dashboard.top_product}
            </div>

            <div className="kpi-change neutral">
              Top revenue product
              <span>based on current data</span>
            </div>
          </div>
        </section>

        {/* CHARTS */}
        <section className="charts-grid">
          {/* SALES CHART */}
          <div className="panel sales-panel">
            <div className="panel-header">
              <div>
                <h2>Sales Performance</h2>
                <p>Actual vs forecast units</p>
              </div>

              <button className="panel-button">
                Monthly ⌄
              </button>
            </div>

            <div className="sales-chart">
              <div className="y-axis">
                <span>
                  {Math.ceil(maxSalesValue / 50) * 50}
                </span>

                <span>
                  {Math.ceil(maxSalesValue / 50) * 50 - 50}
                </span>

                <span>
                  {Math.ceil(maxSalesValue / 50) * 50 - 100}
                </span>

                <span>
                  {Math.ceil(maxSalesValue / 50) * 50 - 150}
                </span>

                <span>0</span>
              </div>

              <div className="chart-container">
                <div className="horizontal-lines">
                  <span />
                  <span />
                  <span />
                  <span />
                  <span />
                </div>

                <div className="bar-chart">
                  {sales.length > 0 ? (
                    sales.map((item) => {
                      const actualHeight =
                        (item.actual_units /
                          maxSalesValue) *
                        100

                      const forecastHeight =
                        (item.forecast_units /
                          maxSalesValue) *
                        100

                      return (
                        <div
                          className="bar-group"
                          key={item.month}
                        >
                          <div
                            className="bar actual"
                            style={{
                              height: `${actualHeight}%`,
                            }}
                            title={`Actual: ${item.actual_units} units`}
                          />

                          <div
                            className="bar forecast"
                            style={{
                              height: `${forecastHeight}%`,
                            }}
                            title={`Forecast: ${item.forecast_units} units`}
                          />
                        </div>
                      )
                    })
                  ) : (
                    <div className="chart-loading">
                      Loading sales data...
                    </div>
                  )}
                </div>

                <div className="x-axis">
                  {sales.map((item) => {
                    const date = new Date(
                      `${item.month}-01`,
                    )

                    return (
                      <span key={item.month}>
                        {date.toLocaleString('en-US', {
                          month: 'short',
                        })}
                      </span>
                    )
                  })}
                </div>
              </div>
            </div>

            <div className="chart-legend">
              <span>
                <i className="legend-dot actual-dot" />
                Actual
              </span>

              <span>
                <i className="legend-dot forecast-dot" />
                Forecast
              </span>
            </div>
          </div>

          {/* REVENUE */}
          <div className="panel revenue-panel">
            <div className="panel-header">
              <div>
                <h2>Revenue</h2>
                <p>Monthly revenue performance</p>
              </div>
            </div>

            <div className="revenue-total">
              <strong>
                ¥
                {(
                  dashboard.total_revenue / 1_000_000
                ).toFixed(2)}
                M
              </strong>

              <span>+6.2%</span>
            </div>

            <div className="revenue-chart">
              <div className="revenue-grid">
                <span />
                <span />
                <span />
                <span />
              </div>

              {sales.length > 0 ? (
                <svg
                  className="revenue-svg"
                  viewBox="0 0 500 180"
                  preserveAspectRatio="none"
                >
                  {/* Revenue area */}
                  <polyline
                    points={revenueAreaPoints}
                    fill="currentColor"
                    opacity="0.08"
                  />

                  {/* Revenue line */}
                  <polyline
                    points={revenueLinePoints}
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="4"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />

                  {/* Data points */}
                  {revenuePoints.map((point, index) => (
                    <circle
                      key={sales[index].month}
                      cx={point.x}
                      cy={point.y}
                      r="4"
                      fill="currentColor"
                    >
                      <title>
                        {sales[index].month}: ¥
                        {sales[index].revenue.toLocaleString()}
                      </title>
                    </circle>
                  ))}
                </svg>
              ) : (
                <div className="chart-loading">
                  Loading revenue data...
                </div>
              )}
            </div>

            <div className="month-labels">
              {sales.map((item) => {
                const date = new Date(
                  `${item.month}-01`,
                )

                return (
                  <span key={item.month}>
                    {date.toLocaleString('en-US', {
                      month: 'short',
                    })}
                  </span>
                )
              })}
            </div>
          </div>
        </section>

        {/* BOTTOM SECTION */}
        <section className="bottom-grid">
          {/* PRODUCTS */}
          <div className="panel">
            <div className="panel-header">
              <div>
                <h2>Product Performance</h2>
                <p>
                  Revenue contribution by product
                </p>
              </div>

              <button className="panel-button">
                View all →
              </button>
            </div>

            <div className="product-table">
              <div className="product-row product-header">
                <span>PRODUCT</span>
                <span>REVENUE</span>
                <span>FORECAST VARIANCE</span>
              </div>

              {products.length > 0 ? (
                products.map((item) => {
                  const variance =
                    item.actual_units !== 0
                      ? ((item.forecast_units -
                          item.actual_units) /
                          item.actual_units) *
                        100
                      : 0

                  const varianceClass =
                    variance > 0
                      ? 'positive'
                      : variance < 0
                        ? 'negative'
                        : 'neutral'

                  return (
                    <div
                      className="product-row"
                      key={item.product}
                    >
                      <div className="product-name">
                        <strong>{item.product}</strong>

                        <span>
                          {item.actual_units.toLocaleString()}{' '}
                          actual units
                        </span>
                      </div>

                      <strong>
                        ¥
                        {(
                          item.revenue / 1_000_000
                        ).toFixed(2)}
                        M
                      </strong>

                      <span className={varianceClass}>
                        {variance > 0 ? '+' : ''}
                        {variance.toFixed(1)}%
                      </span>
                    </div>
                  )
                })
              ) : (
                <div className="chart-loading">
                  Loading product data...
                </div>
              )}
            </div>
          </div>

          {/* AI INSIGHTS */}
          <div className="panel insights-panel">
            <div className="panel-header">
              <div>
                <h2>AI Insights</h2>
                <p>Automated recommendations</p>
              </div>
            </div>

            <div className="insight">
              <div className="insight-icon positive-icon">
                ↑
              </div>

              <div>
                <strong>Demand increasing</strong>

                <p>
                  Inverter demand is expected to rise over
                  the next quarter.
                </p>
              </div>
            </div>

            <div className="insight">
              <div className="insight-icon warning-icon">
                !
              </div>

              <div>
                <strong>Inventory attention</strong>

                <p>
                  Servo Motor inventory may require
                  replenishment.
                </p>
              </div>
            </div>

            <div className="insight">
              <div className="insight-icon neutral-icon">
                ◆
              </div>

              <div>
                <strong>Forecast stable</strong>

                <p>
                  Current model performance remains above
                  the 95% target.
                </p>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}

export default App
