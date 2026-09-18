import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  BarChart3,
  Bell,
  Building2,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  Gauge,
  Globe2,
  LayoutDashboard,
  Link2,
  Menu,
  Search,
  Share2,
  Sparkles,
  Target,
  TrendingUp,
  Users,
  X,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

const periods = [
  ['7d', '7 giorni'],
  ['30d', '30 giorni'],
  ['90d', '90 giorni'],
  ['365d', '1 anno'],
]

const nav = [
  ['Panoramica', LayoutDashboard],
  ['Acquisizione', TrendingUp],
  ['Contenuti', BarChart3],
  ['Lead', Target],
  ['SEO locale', Search],
  ['Connettori', Link2],
]

const formatNumber = (value) =>
  new Intl.NumberFormat('it-IT', { maximumFractionDigits: 0 }).format(value || 0)

function App() {
  const [period, setPeriod] = useState('30d')
  const [data, setData] = useState(null)
  const [connectors, setConnectors] = useState([])
  const [loading, setLoading] = useState(true)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetch(`/api/dashboard?period=${period}`).then((r) => r.json()),
      fetch('/api/connectors').then((r) => r.json()),
    ])
      .then(([dashboard, connectorData]) => {
        setData(dashboard)
        setConnectors(connectorData.items || [])
      })
      .finally(() => setLoading(false))
  }, [period])

  const conversionRate = useMemo(() => {
    if (!data?.funnel?.length) return 0
    const visits = data.funnel.find((item) => item.label === 'Visite')?.value || 0
    const leads = data.funnel.find((item) => item.label === 'Lead')?.value || 0
    return visits ? ((leads / visits) * 100).toFixed(1) : 0
  }, [data])

  if (loading && !data) {
    return (
      <div className="loading-screen">
        <div className="loading-orb" />
        <strong>GE360 Analitica</strong>
        <span>Sto preparando il quadro completo…</span>
      </div>
    )
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`}>
        <div className="brand">
          <div className="brand-mark"><Gauge size={23} /></div>
          <div>
            <strong>GE360</strong>
            <span>ANALITICA</span>
          </div>
          <button className="sidebar-close" onClick={() => setMenuOpen(false)}><X size={20} /></button>
        </div>

        <nav className="nav-list">
          {nav.map(([label, Icon], index) => (
            <button className={index === 0 ? 'nav-item active' : 'nav-item'} key={label}>
              <Icon size={19} />
              <span>{label}</span>
              {index === 0 && <ChevronRight size={16} className="nav-arrow" />}
            </button>
          ))}
        </nav>

        <div className="sidebar-section">
          <span className="section-label">FONTI DATI</span>
          <SourceStatus icon={Share2} label="Meta" status={connectors.find((c) => c.provider === 'meta')?.status} />
          <SourceStatus icon={Building2} label="Google Business" status={connectors.find((c) => c.provider === 'google_business')?.status} />
          <SourceStatus icon={Globe2} label="WordPress" status={connectors.find((c) => c.provider === 'wordpress')?.status} />
          <SourceStatus icon={Activity} label="Analytics 4" status={connectors.find((c) => c.provider === 'ga4')?.status} />
          <SourceStatus icon={Search} label="Search Console" status={connectors.find((c) => c.provider === 'search_console')?.status} />
        </div>

        <div className="sidebar-card">
          <Sparkles size={18} />
          <strong>GE360 Intelligence</strong>
          <p>Gli insight avanzati saranno disponibili parlando direttamente con ChatGPT tramite il plugin GE360.</p>
          <span>ChatGPT · Plugin MCP</span>
        </div>
      </aside>

      {menuOpen && <button className="mobile-backdrop" onClick={() => setMenuOpen(false)} />}

      <main className="main">
        <header className="topbar">
          <div className="title-row">
            <button className="menu-button" onClick={() => setMenuOpen(true)}><Menu size={21} /></button>
            <div>
              <span className="eyebrow">CENTRO DATI DIGITALE</span>
              <h1>Panoramica</h1>
            </div>
          </div>

          <div className="top-actions">
            <div className="live-pill"><span /> Dati demo</div>
            <button className="icon-button"><Bell size={19} /></button>
            <div className="avatar">MS</div>
          </div>
        </header>

        <section className="hero">
          <div>
            <span className="hero-kicker"><Sparkles size={15} /> Ecosistema digitale</span>
            <h2>Capisci cosa porta davvero nuovi clienti.</h2>
            <p>Social, Google, sito, SEO e lead letti come un unico percorso invece che come dashboard separate.</p>
          </div>

          <div className="period-switcher">
            {periods.map(([value, label]) => (
              <button key={value} onClick={() => setPeriod(value)} className={period === value ? 'selected' : ''}>
                {label}
              </button>
            ))}
          </div>
        </section>

        <section className="kpi-grid">
          {data?.kpis?.map((item, index) => (
            <KpiCard key={item.key} item={item} index={index} />
          ))}
          <article className="kpi-card conversion-card">
            <div className="kpi-top">
              <span className="kpi-icon"><Target size={19} /></span>
              <span className="kpi-mini">VISITA → LEAD</span>
            </div>
            <strong>{conversionRate}%</strong>
            <p>Tasso di conversione</p>
          </article>
        </section>

        <section className="dashboard-grid">
          <article className="panel trend-panel">
            <PanelHeader
              eyebrow="ANDAMENTO"
              title="Traffico, interazioni e lead"
              extra={<span className="panel-badge">Confronto periodo</span>}
            />
            <div className="chart-wrap">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={data?.trend || []} margin={{ top: 8, right: 8, left: -24, bottom: 0 }}>
                  <defs>
                    <linearGradient id="visitsFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#5e7cff" stopOpacity={0.32} />
                      <stop offset="95%" stopColor="#5e7cff" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(148,163,184,.12)" />
                  <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fill: '#7e8ba3', fontSize: 11 }} minTickGap={38} />
                  <YAxis axisLine={false} tickLine={false} tick={{ fill: '#7e8ba3', fontSize: 11 }} />
                  <Tooltip content={<TrendTooltip />} />
                  <Area type="monotone" dataKey="visits" stroke="#6d86ff" fill="url(#visitsFill)" strokeWidth={2.5} />
                  <Area type="monotone" dataKey="interactions" stroke="#28d7a3" fill="transparent" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div className="chart-legend">
              <span><i className="dot visits" /> Visite</span>
              <span><i className="dot interactions" /> Interazioni</span>
            </div>
          </article>

          <article className="panel sources-panel">
            <PanelHeader eyebrow="ACQUISIZIONE" title="Da dove arrivano" />
            <div className="source-chart">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data?.sources || []} layout="vertical" margin={{ top: 0, right: 12, left: 10, bottom: 0 }}>
                  <XAxis type="number" hide />
                  <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} width={105} tick={{ fill: '#a7b0c3', fontSize: 11 }} />
                  <Tooltip cursor={{ fill: 'rgba(255,255,255,.025)' }} content={<SourceTooltip />} />
                  <Bar dataKey="visits" fill="#5e7cff" radius={[0, 7, 7, 0]} barSize={13} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="source-summary">
              <strong>{formatNumber(data?.sources?.reduce((sum, item) => sum + item.leads, 0))}</strong>
              <span>lead attribuiti alle sorgenti</span>
            </div>
          </article>

          <article className="panel funnel-panel">
            <PanelHeader eyebrow="PERCORSO" title="Funnel cliente" />
            <div className="funnel-list">
              {data?.funnel?.map((item, index) => {
                const max = data.funnel[0]?.value || 1
                const width = Math.max(18, (item.value / max) * 100)
                return (
                  <div className="funnel-row" key={item.label}>
                    <div className="funnel-meta">
                      <span>{item.label}</span>
                      <strong>{formatNumber(item.value)}</strong>
                    </div>
                    <div className="funnel-track">
                      <span style={{ width: `${width}%` }} />
                    </div>
                    {index < data.funnel.length - 1 && (
                      <small>{((data.funnel[index + 1].value / item.value) * 100).toFixed(1)}% passa allo step successivo</small>
                    )}
                  </div>
                )
              })}
            </div>
          </article>

          <article className="panel content-panel">
            <PanelHeader eyebrow="CONTENUTI" title="Cosa sta funzionando" extra={<button className="text-button">Vedi tutto <ChevronRight size={14} /></button>} />
            <div className="content-table">
              <div className="content-head">
                <span>Contenuto</span><span>Visite</span><span>Lead</span>
              </div>
              {data?.top_content?.map((item, index) => (
                <div className="content-row" key={item.title}>
                  <div className="content-name">
                    <span className="rank">{String(index + 1).padStart(2, '0')}</span>
                    <div><strong>{item.title}</strong><small>{item.type}</small></div>
                  </div>
                  <strong>{formatNumber(item.views)}</strong>
                  <span className="lead-chip">{item.leads}</span>
                </div>
              ))}
            </div>
          </article>

          <article className="panel insight-panel">
            <PanelHeader eyebrow="GE360 INTELLIGENCE" title="Segnali da guardare" extra={<Sparkles size={19} className="sparkle" />} />
            <div className="insight-list">
              {data?.insights?.map((item) => (
                <div className={`insight ${item.severity}`} key={item.title}>
                  <div className="insight-icon">
                    {item.severity === 'positive' ? <CircleCheck size={18} /> : item.severity === 'warning' ? <CircleAlert size={18} /> : <Sparkles size={18} />}
                  </div>
                  <div><strong>{item.title}</strong><p>{item.text}</p></div>
                </div>
              ))}
            </div>
          </article>
        </section>

        <section className="connector-strip">
          <div>
            <span className="eyebrow">PROSSIMO PASSO</span>
            <h3>Collega le fonti reali</h3>
            <p>La struttura è pronta: quando inseriamo le credenziali, i dati demo vengono sostituiti dai tuoi dati.</p>
          </div>
          <div className="connector-mini-grid">
            {connectors.map((connector) => (
              <div className="connector-mini" key={connector.provider}>
                <span className="status-dot" />
                <div><strong>{prettyProvider(connector.provider)}</strong><small>Da configurare</small></div>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  )
}

function prettyProvider(provider) {
  return ({
    meta: 'Meta',
    wordpress: 'WordPress',
    google_business: 'Google Business',
    ga4: 'Analytics 4',
    search_console: 'Search Console',
  })[provider] || provider
}

function SourceStatus({ icon: Icon, label, status }) {
  const connected = status === 'connected'
  return (
    <div className="source-status">
      <Icon size={16} />
      <span>{label}</span>
      <i className={connected ? 'connected' : ''} />
    </div>
  )
}

function KpiCard({ item, index }) {
  const icons = [Users, Share2, Globe2, Target]
  const Icon = icons[index] || Activity
  return (
    <article className="kpi-card">
      <div className="kpi-top">
        <span className="kpi-icon"><Icon size={19} /></span>
        <span className="change positive">+{item.change}%</span>
      </div>
      <strong>{formatNumber(item.value)}</strong>
      <p>{item.label}</p>
    </article>
  )
}

function PanelHeader({ eyebrow, title, extra }) {
  return (
    <div className="panel-header">
      <div><span>{eyebrow}</span><h3>{title}</h3></div>
      {extra}
    </div>
  )
}

function TrendTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="tooltip">
      <small>{label}</small>
      {payload.map((item) => <div key={item.dataKey}><span>{item.dataKey}</span><strong>{formatNumber(item.value)}</strong></div>)}
    </div>
  )
}

function SourceTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const item = payload[0].payload
  return (
    <div className="tooltip">
      <small>{item.name}</small>
      <div><span>Visite</span><strong>{formatNumber(item.visits)}</strong></div>
      <div><span>Lead</span><strong>{formatNumber(item.leads)}</strong></div>
    </div>
  )
}

export default App
