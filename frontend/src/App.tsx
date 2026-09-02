import './App.css'

function App() {
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

          <div className="nav-section-title analysis-title">ANALYSIS</div>

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
            <div className="breadcrumb">DASHBOARD / OVERVIEW</div>
            <h1>Sales Intelligence Dashboard</h1>
            <p>AI-powered sales order forecasting and analysis</p>
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

            <div className="kpi-value">1,625</div>

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

            <div className="kpi-value">¥6.50M</div>

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

            <div className="kpi-value">96.8%</div>

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

            <div className="kpi-value product-kpi">MELSEC iQ-R</div>

            <div className="kpi-change neutral">
              ¥1.62M
              <span>revenue generated</span>
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

              <button className="panel-button">Monthly ⌄</button>
            </div>

            <div className="sales-chart">
              <div className="y-axis">
                <span>200</span>
                <span>150</span>
                <span>100</span>
                <span>50</span>
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
                  <div className="bar-group">
                    <div className="bar actual" style={{ height: '58%' }} />
                    <div className="bar forecast" style={{ height: '61%' }} />
                  </div>

                  <div className="bar-group">
                    <div className="bar actual" style={{ height: '66%' }} />
                    <div className="bar forecast" style={{ height: '64%' }} />
                  </div>

                  <div className="bar-group">
                    <div className="bar actual" style={{ height: '73%' }} />
                    <div className="bar forecast" style={{ height: '70%' }} />
                  </div>

                  <div className="bar-group">
                    <div className="bar actual" style={{ height: '54%' }} />
                    <div className="bar forecast" style={{ height: '59%' }} />
                  </div>

                  <div className="bar-group">
                    <div className="bar actual" style={{ height: '62%' }} />
                    <div className="bar forecast" style={{ height: '60%' }} />
                  </div>

                  <div className="bar-group">
                    <div className="bar actual" style={{ height: '69%' }} />
                    <div className="bar forecast" style={{ height: '68%' }} />
                  </div>
                </div>

                <div className="x-axis">
                  <span>Jan</span>
                  <span>Feb</span>
                  <span>Mar</span>
                  <span>Apr</span>
                  <span>May</span>
                  <span>Jun</span>
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
              <strong>¥6.50M</strong>
              <span>+6.2%</span>
            </div>

            <div className="revenue-chart">
              <div className="revenue-grid">
                <span />
                <span />
                <span />
                <span />
              </div>

              <svg
                className="revenue-svg"
                viewBox="0 0 500 180"
                preserveAspectRatio="none"
              >
                <polyline
                  points="0,145 45,130 90,118 135,135 180,105 225,95 270,80 315,88 360,62 405,52 450,38 500,25"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />

                <polyline
                  points="0,145 45,130 90,118 135,135 180,105 225,95 270,80 315,88 360,62 405,52 450,38 500,25 500,180 0,180"
                  fill="currentColor"
                  opacity="0.08"
                />
              </svg>
            </div>

            <div className="month-labels">
              <span>Jan</span>
              <span>Mar</span>
              <span>May</span>
              <span>Jul</span>
              <span>Sep</span>
              <span>Nov</span>
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
                <p>Revenue contribution by product</p>
              </div>

              <button className="panel-button">View all →</button>
            </div>

            <div className="product-table">
              <div className="product-row product-header">
                <span>PRODUCT</span>
                <span>REVENUE</span>
                <span>GROWTH</span>
              </div>

              <div className="product-row">
                <div className="product-name">
                  <strong>MELSEC iQ-R</strong>
                  <span>PLC Systems</span>
                </div>

                <strong>¥1.62M</strong>

                <span className="positive">+12.4%</span>
              </div>

              <div className="product-row">
                <div className="product-name">
                  <strong>MELSEC iQ-F</strong>
                  <span>PLC Systems</span>
                </div>

                <strong>¥1.52M</strong>

                <span className="positive">+8.7%</span>
              </div>

              <div className="product-row">
                <div className="product-name">
                  <strong>Inverter</strong>
                  <span>Drive Systems</span>
                </div>

                <strong>¥2.10M</strong>

                <span className="positive">+5.3%</span>
              </div>

              <div className="product-row">
                <div className="product-name">
                  <strong>Servo Motor</strong>
                  <span>Motion Systems</span>
                </div>

                <strong>¥1.26M</strong>

                <span className="negative">-2.1%</span>
              </div>
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
              <div className="insight-icon positive-icon">↑</div>

              <div>
                <strong>Demand increasing</strong>

                <p>
                  Inverter demand is expected to rise over the next quarter.
                </p>
              </div>
            </div>

            <div className="insight">
              <div className="insight-icon warning-icon">!</div>

              <div>
                <strong>Inventory attention</strong>

                <p>
                  Servo Motor inventory may require replenishment.
                </p>
              </div>
            </div>

            <div className="insight">
              <div className="insight-icon neutral-icon">◆</div>

              <div>
                <strong>Forecast stable</strong>

                <p>
                  Current model performance remains above the 95% target.
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