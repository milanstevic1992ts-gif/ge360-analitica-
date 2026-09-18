import { useEffect, useMemo, useState } from 'react'
import LocalAIPage from './LocalAIPage'
import SetupWizardPage from './SetupWizardPage'
import {
  Activity,
  BarChart3,
  Bell,
  Building2,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  ExternalLink,
  Gauge,
  Globe2,
  LayoutDashboard,
  Link2,
  Menu,
  MessageCircle,
  RefreshCw,
  Search,
  Settings2,
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
  ['7d', '7 giorni', 7],
  ['30d', '30 giorni', 30],
  ['90d', '90 giorni', 90],
  ['365d', '1 anno', 365],
]

const nav = [
  { id: 'overview', label: 'Panoramica', icon: LayoutDashboard },
  { id: 'setup', label: 'Configurazione', icon: Settings2 },
  { id: 'acquisition', label: 'Acquisizione', icon: TrendingUp },
  { id: 'content', label: 'Contenuti', icon: BarChart3 },
  { id: 'leads', label: 'Lead', icon: Target },
  { id: 'seo', label: 'SEO locale', icon: Search },
  { id: 'connectors', label: 'Connettori', icon: Link2 },
  { id: 'local-ai', label: 'AI Locale', icon: Sparkles },
]

const formatNumber = (value) =>
  new Intl.NumberFormat('it-IT', { maximumFractionDigits: 0 }).format(value || 0)

const formatMoney = (value) =>
  new Intl.NumberFormat('it-IT', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(value || 0)

function App() {
  const [activeView, setActiveView] = useState(() => {
    const googleReturned = new URLSearchParams(window.location.search).get('google') === 'connected'
    if (googleReturned) return 'setup'
    return localStorage.getItem('ge360-setup-seen') ? 'overview' : 'setup'
  })
  const [period, setPeriod] = useState('30d')
  const [data, setData] = useState(null)
  const [connectors, setConnectors] = useState([])
  const [diagnostics, setDiagnostics] = useState([])
  const [leadsSummary, setLeadsSummary] = useState(null)
  const [recentLeads, setRecentLeads] = useState([])
  const [contentPerformance, setContentPerformance] = useState([])
  const [seoRows, setSeoRows] = useState([])
  const [anomalyRows, setAnomalyRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [actionMessage, setActionMessage] = useState('')
  const [menuOpen, setMenuOpen] = useState(false)

  const days = periods.find(([value]) => value === period)?.[2] || 30

  const loadData = async () => {
    setLoading(true)
    try {
      const responses = await Promise.all([
        fetch(`/api/dashboard?period=${period}`).then((r) => r.json()),
        fetch('/api/connectors').then((r) => r.json()),
        fetch('/api/connectors/diagnostics').then((r) => r.json()),
        fetch(`/api/analytics/leads-summary?days=${days}`).then((r) => r.json()),
        fetch(`/api/analytics/recent-leads?days=${days}&limit=50`).then((r) => r.json()),
        fetch(`/api/analytics/content-performance?days=${Math.min(days, 365)}&limit=50`).then((r) => r.json()),
        fetch(`/api/analytics/local-seo?days=${Math.min(days, 365)}&contains=trieste&limit=100`).then((r) => r.json()),
        fetch(`/api/analytics/anomalies?days=${Math.min(days, 30)}&threshold_percent=25&limit=30`).then((r) => r.json()),
      ])

      const [
        dashboard,
        connectorData,
        diagnosticData,
        leadData,
        recentLeadData,
        contentData,
        seoData,
        anomalyData,
      ] = responses

      setData(dashboard)
      setConnectors(connectorData.items || [])
      setDiagnostics(diagnosticData.items || [])
      setLeadsSummary(leadData)
      setRecentLeads(Array.isArray(recentLeadData) ? recentLeadData : [])
      setContentPerformance(Array.isArray(contentData) ? contentData : [])
      setSeoRows(Array.isArray(seoData) ? seoData : [])
      setAnomalyRows(Array.isArray(anomalyData) ? anomalyData : [])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [period])

  const navigate = (view) => {
    setActiveView(view)
    setMenuOpen(false)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const connectGoogle = async () => {
    setActionMessage('')
    const response = await fetch('/api/oauth/google/start')
    const payload = await response.json()
    if (!response.ok) {
      setActionMessage(payload.detail || 'Configurazione Google incompleta')
      return
    }
    window.location.href = payload.authorization_url
  }

  const syncProvider = async (provider) => {
    setSyncing(true)
    setActionMessage('')
    try {
      const response = await fetch(`/api/sync/${provider}`, { method: 'POST' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || `Sync ${provider} fallita`)
      setActionMessage(payload.message || `${prettyProvider(provider)} sincronizzato`)
      await loadData()
    } catch (error) {
      setActionMessage(error.message)
    } finally {
      setSyncing(false)
    }
  }

  const syncAll = async () => {
    setSyncing(true)
    setActionMessage('')
    try {
      const response = await fetch('/api/sync', { method: 'POST' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Sincronizzazione fallita')
      const ok = payload.results?.filter((item) => item.ok).length || 0
      setActionMessage(`Sincronizzazione completata: ${ok} connettori attivi.`)
      await loadData()
    } catch (error) {
      setActionMessage(error.message)
    } finally {
      setSyncing(false)
    }
  }

  const googleConfigured = diagnostics.some(
    (item) => ['ga4', 'search_console', 'google_business'].includes(item.provider) && item.configured
  )

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

  const currentNav = nav.find((item) => item.id === activeView) || nav[0]

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
          {nav.map(({ id, label, icon: Icon }) => (
            <button
              className={activeView === id ? 'nav-item active' : 'nav-item'}
              key={id}
              onClick={() => navigate(id)}
            >
              <Icon size={19} />
              <span>{label}</span>
              {activeView === id && <ChevronRight size={16} className="nav-arrow" />}
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

        <button className="sidebar-card sidebar-card-button" onClick={() => navigate('local-ai')}>
          <Sparkles size={18} />
          <strong>GE360 Intelligence</strong>
          <p>Ollama + Qwen analizzano i dati direttamente sul tuo Linux.</p>
          <span>Configura AI locale →</span>
        </button>
      </aside>

      {menuOpen && <button className="mobile-backdrop" onClick={() => setMenuOpen(false)} />}

      <main className="main">
        <header className="topbar">
          <div className="title-row">
            <button className="menu-button" onClick={() => setMenuOpen(true)}><Menu size={21} /></button>
            <div>
              <span className="eyebrow">CENTRO DATI DIGITALE</span>
              <h1>{currentNav.label}</h1>
            </div>
          </div>

          <div className="top-actions">
            <div className={`live-pill ${data?.mode === 'live' ? 'is-live' : ''}`}>
              <span /> {data?.mode === 'live' ? 'Dati reali' : 'Dati demo'}
            </div>
            <button className="icon-button" onClick={loadData} title="Aggiorna"><RefreshCw size={18} /></button>
            <button className="icon-button"><Bell size={19} /></button>
            <div className="avatar">MS</div>
          </div>
        </header>

        {activeView !== 'local-ai' && activeView !== 'connectors' && activeView !== 'setup' && (
          <PeriodBar period={period} setPeriod={setPeriod} />
        )}

        {activeView === 'overview' && (
          <OverviewPage
            data={data}
            conversionRate={conversionRate}
            connectors={connectors}
            diagnostics={diagnostics}
            googleConfigured={googleConfigured}
            connectGoogle={connectGoogle}
            syncAll={syncAll}
            syncing={syncing}
            actionMessage={actionMessage}
            navigate={navigate}
          />
        )}

        {activeView === 'acquisition' && <AcquisitionPage data={data} />}
        {activeView === 'content' && <ContentPage data={data} items={contentPerformance} />}
        {activeView === 'leads' && <LeadsPage summary={leadsSummary} recent={recentLeads} />}
        {activeView === 'seo' && <SeoPage rows={seoRows} anomalies={anomalyRows} />}
        {activeView === 'connectors' && (
          <ConnectorsPage
            connectors={connectors}
            diagnostics={diagnostics}
            connectGoogle={connectGoogle}
            googleConfigured={googleConfigured}
            syncAll={syncAll}
            syncProvider={syncProvider}
            syncing={syncing}
            actionMessage={actionMessage}
          />
        )}
        {activeView === 'setup' && <SetupWizardPage onFinish={() => navigate('overview')} />}
        {activeView === 'local-ai' && <LocalAIPage days={days} dashboardMode={data?.mode} />}
      </main>
    </div>
  )
}

function PeriodBar({ period, setPeriod }) {
  return (
    <div className="view-toolbar">
      <span className="view-toolbar-label">Periodo analisi</span>
      <div className="period-switcher">
        {periods.map(([value, label]) => (
          <button key={value} onClick={() => setPeriod(value)} className={period === value ? 'selected' : ''}>
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}

function OverviewPage({
  data,
  conversionRate,
  connectors,
  diagnostics,
  googleConfigured,
  connectGoogle,
  syncAll,
  syncing,
  actionMessage,
  navigate,
}) {
  return (
    <>
      <section className="hero">
        <div>
          <span className="hero-kicker"><Sparkles size={15} /> Ecosistema digitale</span>
          <h2>Capisci cosa porta davvero nuovi clienti.</h2>
          <p>Social, Google, sito, SEO e lead letti come un unico percorso invece che come dashboard separate.</p>
        </div>
        <button className="hero-action" onClick={() => navigate('local-ai')}>
          <Sparkles size={17} /> Analizza con AI Locale
        </button>
      </section>

      <section className="kpi-grid">
        {data?.kpis?.map((item, index) => <KpiCard key={item.key} item={item} index={index} />)}
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
        <TrendPanel data={data} />
        <SourcesPanel data={data} />
        <FunnelPanel data={data} />
        <ContentPanel items={data?.top_content || []} />
        <InsightsPanel items={data?.insights || []} />
      </section>

      <ConnectorStrip
        connectors={connectors}
        diagnostics={diagnostics}
        googleConfigured={googleConfigured}
        connectGoogle={connectGoogle}
        syncAll={syncAll}
        syncing={syncing}
        actionMessage={actionMessage}
      />
    </>
  )
}

function AcquisitionPage({ data }) {
  const sources = data?.sources || []
  return (
    <>
      <PageIntro
        icon={TrendingUp}
        kicker="ACQUISIZIONE"
        title="Da dove arrivano visite e lead"
        text="Confronta le sorgenti e guarda dove il traffico si trasforma davvero in contatti."
      />
      <section className="two-column-grid">
        <SourcesPanel data={data} />
        <FunnelPanel data={data} />
      </section>
      <article className="panel page-panel">
        <PanelHeader eyebrow="SORGENTI" title="Dettaglio acquisizione" />
        <div className="data-table">
          <div className="data-row data-head"><span>Sorgente</span><span>Visite</span><span>Lead</span><span>Conversione</span></div>
          {sources.length ? sources.map((item) => {
            const conversion = item.visits ? ((item.leads / item.visits) * 100).toFixed(1) : '0.0'
            return (
              <div className="data-row" key={item.name}>
                <strong>{item.name}</strong>
                <span>{formatNumber(item.visits)}</span>
                <span>{formatNumber(item.leads)}</span>
                <span>{conversion}%</span>
              </div>
            )
          }) : <EmptyState text="Nessun dato di acquisizione reale ancora disponibile." />}
        </div>
      </article>
    </>
  )
}

function ContentPage({ data, items }) {
  const rows = items.length
    ? items.map((item) => ({
        title: item.url,
        type: 'Pagina',
        views: item.page_views || 0,
        actions: (item.whatsapp_clicks || 0) + (item.phone_clicks || 0) + (item.form_submits || 0),
        leads: item.leads || 0,
        conversion: item.lead_conversion_percent,
      }))
    : (data?.top_content || []).map((item) => ({ ...item, actions: item.actions || 0 }))

  return (
    <>
      <PageIntro
        icon={BarChart3}
        kicker="CONTENUTI"
        title="Quali pagine stanno lavorando per te"
        text="Visite, azioni e lead nello stesso posto. Qui diventa evidente cosa porta contatti e cosa no."
      />
      <article className="panel page-panel">
        <PanelHeader eyebrow="PERFORMANCE" title="Pagine e contenuti" />
        <div className="data-table content-data-table">
          <div className="data-row data-head"><span>Contenuto</span><span>Visite</span><span>Azioni</span><span>Lead</span><span>Conv.</span></div>
          {rows.length ? rows.map((item, index) => (
            <div className="data-row" key={`${item.title}-${index}`}>
              <div className="table-title"><strong>{item.title}</strong><small>{item.type}</small></div>
              <span>{formatNumber(item.views)}</span>
              <span>{formatNumber(item.actions)}</span>
              <span>{formatNumber(item.leads)}</span>
              <span>{item.conversion == null ? '—' : `${item.conversion}%`}</span>
            </div>
          )) : <EmptyState text="Installa/collega il tracker WordPress e sincronizza per vedere i contenuti reali." />}
        </div>
      </article>
    </>
  )
}

function LeadsPage({ summary, recent }) {
  const total = summary?.total || { leads: 0, total_value: 0 }
  return (
    <>
      <PageIntro
        icon={Target}
        kicker="LEAD"
        title="Contatti e provenienza"
        text="Qui vedrai quanti lead arrivano, da quale canale e da quale sorgente."
      />
      <section className="mini-kpi-grid">
        <MiniKpi label="Lead periodo" value={formatNumber(total.leads)} />
        <MiniKpi label="Valore attribuito" value={formatMoney(total.total_value)} />
        <MiniKpi label="Canali attivi" value={formatNumber(summary?.by_channel?.length || 0)} />
        <MiniKpi label="Sorgenti attribuite" value={formatNumber(summary?.by_source?.length || 0)} />
      </section>
      <section className="two-column-grid">
        <article className="panel">
          <PanelHeader eyebrow="CANALI" title="Lead per canale" />
          <SimpleRows
            rows={summary?.by_channel || []}
            labelKey="channel"
            valueKey="leads"
            empty="Nessun lead ancora registrato."
          />
        </article>
        <article className="panel">
          <PanelHeader eyebrow="ATTRIBUZIONE" title="Lead per sorgente" />
          <SimpleRows
            rows={summary?.by_source || []}
            labelKey="source"
            valueKey="leads"
            empty="Nessuna sorgente attribuita."
          />
        </article>
      </section>
      <article className="panel page-panel">
        <PanelHeader eyebrow="RECENTI" title="Ultimi lead analitici" />
        <div className="data-table">
          <div className="data-row data-head"><span>Canale</span><span>Sorgente</span><span>Pagina</span><span>Stato</span></div>
          {recent.length ? recent.map((item, index) => (
            <div className="data-row" key={`${item.created_at}-${index}`}>
              <strong>{item.channel || '—'}</strong>
              <span>{item.source || '—'}</span>
              <span className="truncate-cell">{item.landing_page || '—'}</span>
              <span>{item.status || '—'}</span>
            </div>
          )) : <EmptyState text="Non ci sono ancora lead reali nel database." />}
        </div>
      </article>
    </>
  )
}

function SeoPage({ rows, anomalies }) {
  return (
    <>
      <PageIntro
        icon={Search}
        kicker="SEO LOCALE"
        title="Come ti trovano a Trieste"
        text="Query locali da Search Console e Google Business, più variazioni anomale da controllare."
      />
      <section className="two-column-grid">
        <article className="panel">
          <PanelHeader eyebrow="RICERCHE" title="Query locali" />
          <div className="seo-list">
            {rows.length ? rows.slice(0, 30).map((item, index) => (
              <div className="seo-row" key={`${item.provider}-${item.query}-${item.metric}-${index}`}>
                <div><strong>{item.query}</strong><small>{prettyProvider(item.provider)} · {item.metric}</small></div>
                <span>{formatNumber(item.value)}</span>
              </div>
            )) : <EmptyState text="Collega Search Console o Google Business per vedere le query locali." />}
          </div>
        </article>
        <article className="panel">
          <PanelHeader eyebrow="ANOMALIE" title="Cambiamenti da controllare" />
          <div className="insight-list vertical">
            {anomalies.length ? anomalies.map((item, index) => (
              <div className={`insight ${item.direction === 'down' ? 'warning' : 'positive'}`} key={index}>
                <div className="insight-icon">{item.direction === 'down' ? <CircleAlert size={18} /> : <TrendingUp size={18} />}</div>
                <div>
                  <strong>{item.metric}</strong>
                  <p>{prettyProvider(item.provider)} · {item.change_percent > 0 ? '+' : ''}{item.change_percent}%</p>
                </div>
              </div>
            )) : <EmptyState text="Nessuna anomalia rilevabile con i dati attuali." />}
          </div>
        </article>
      </section>
    </>
  )
}

function ConnectorsPage({
  connectors,
  diagnostics,
  connectGoogle,
  googleConfigured,
  syncAll,
  syncProvider,
  syncing,
  actionMessage,
}) {
  const providers = ['wordpress', 'ga4', 'search_console', 'google_business', 'meta']
  return (
    <>
      <PageIntro
        icon={Link2}
        kicker="CONNETTORI"
        title="Collega le fonti reali"
        text="Qui puoi vedere cosa è configurato, cosa manca e lanciare le sincronizzazioni."
      />
      <div className="connector-page-grid">
        {providers.map((provider) => {
          const state = connectors.find((item) => item.provider === provider) || {}
          const diag = diagnostics.find((item) => item.provider === provider) || {}
          const ready = state.status === 'connected' || diag.configured
          return (
            <article className="panel connector-card" key={provider}>
              <div className="connector-card-top">
                <div className="connector-provider-icon">{providerIcon(provider)}</div>
                <div>
                  <strong>{prettyProvider(provider)}</strong>
                  <span className={ready ? 'status-text ready-text' : 'status-text'}>
                    {state.status === 'connected' ? 'Sincronizzato' : ready ? 'Configurato' : 'Da configurare'}
                  </span>
                </div>
              </div>
              <p>{state.message || connectorDescription(provider)}</p>
              {!diag.configured && diag.required_env?.length > 0 && (
                <div className="missing-box">
                  <span>Mancano:</span>
                  {diag.required_env.map((env) => <code key={env}>{env}</code>)}
                </div>
              )}
              <div className="connector-card-actions">
                {['ga4', 'search_console', 'google_business'].includes(provider) && (
                  <button className="primary-action" onClick={connectGoogle}>
                    {googleConfigured ? 'Ricollega Google' : 'Collega Google'}
                  </button>
                )}
                <button className="secondary-action" onClick={() => syncProvider(provider)} disabled={syncing}>
                  Sincronizza
                </button>
              </div>
            </article>
          )
        })}
      </div>
      <div className="connector-footer-actions">
        <button className="primary-action big-action" onClick={syncAll} disabled={syncing}>
          <RefreshCw size={16} /> {syncing ? 'Sincronizzazione…' : 'Sincronizza tutto'}
        </button>
        {actionMessage && <span className="inline-message">{actionMessage}</span>}
      </div>
    </>
  )
}

function PageIntro({ icon: Icon, kicker, title, text }) {
  return (
    <section className="page-intro">
      <div className="page-intro-icon"><Icon size={22} /></div>
      <div><span className="eyebrow">{kicker}</span><h2>{title}</h2><p>{text}</p></div>
    </section>
  )
}

function MiniKpi({ label, value }) {
  return <article className="mini-kpi"><span>{label}</span><strong>{value}</strong></article>
}

function SimpleRows({ rows, labelKey, valueKey, empty }) {
  if (!rows.length) return <EmptyState text={empty} />
  return (
    <div className="simple-rows">
      {rows.map((row, index) => (
        <div className="simple-row" key={`${row[labelKey]}-${index}`}>
          <span>{row[labelKey] || 'non attribuita'}</span>
          <strong>{formatNumber(row[valueKey])}</strong>
        </div>
      ))}
    </div>
  )
}

function EmptyState({ text }) {
  return <div className="empty-state">{text}</div>
}

function CommandBox({ command }) {
  const copy = async () => {
    try { await navigator.clipboard.writeText(command) } catch {}
  }
  return <button className="command-box" onClick={copy}><code>{command}</code><span>Copia</span></button>
}

function TrendPanel({ data }) {
  return (
    <article className="panel trend-panel">
      <PanelHeader eyebrow="ANDAMENTO" title="Traffico, interazioni e lead" extra={<span className="panel-badge">Confronto periodo</span>} />
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
      <div className="chart-legend"><span><i className="dot visits" /> Visite</span><span><i className="dot interactions" /> Interazioni</span></div>
    </article>
  )
}

function SourcesPanel({ data }) {
  return (
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
      <div className="source-summary"><strong>{formatNumber(data?.sources?.reduce((sum, item) => sum + item.leads, 0))}</strong><span>lead attribuiti alle sorgenti</span></div>
    </article>
  )
}

function FunnelPanel({ data }) {
  return (
    <article className="panel funnel-panel">
      <PanelHeader eyebrow="PERCORSO" title="Funnel cliente" />
      <div className="funnel-list">
        {data?.funnel?.map((item, index) => {
          const max = data.funnel[0]?.value || 1
          const width = Math.max(6, (item.value / max) * 100)
          const next = data.funnel[index + 1]?.value
          const rate = item.value && next != null ? ((next / item.value) * 100).toFixed(1) : null
          return (
            <div className="funnel-row" key={item.label}>
              <div className="funnel-meta"><span>{item.label}</span><strong>{formatNumber(item.value)}</strong></div>
              <div className="funnel-track"><span style={{ width: `${width}%` }} /></div>
              {rate != null && <small>{rate}% passa allo step successivo</small>}
            </div>
          )
        })}
      </div>
    </article>
  )
}

function ContentPanel({ items }) {
  return (
    <article className="panel content-panel">
      <PanelHeader eyebrow="CONTENUTI" title="Cosa sta funzionando" />
      <div className="content-table">
        <div className="content-head"><span>Contenuto</span><span>Visite</span><span>Lead</span></div>
        {items.length ? items.map((item, index) => (
          <div className="content-row" key={`${item.title}-${index}`}>
            <div className="content-name"><span className="rank">{String(index + 1).padStart(2, '0')}</span><div><strong>{item.title}</strong><small>{item.type}</small></div></div>
            <strong>{formatNumber(item.views)}</strong>
            <span className="lead-chip">{item.leads}</span>
          </div>
        )) : <EmptyState text="Nessun contenuto reale ancora disponibile." />}
      </div>
    </article>
  )
}

function InsightsPanel({ items }) {
  return (
    <article className="panel insight-panel">
      <PanelHeader eyebrow="GE360 INTELLIGENCE" title="Segnali da guardare" extra={<Sparkles size={19} className="sparkle" />} />
      <div className="insight-list">
        {items.map((item) => (
          <div className={`insight ${item.severity}`} key={item.title}>
            <div className="insight-icon">{item.severity === 'positive' ? <CircleCheck size={18} /> : item.severity === 'warning' ? <CircleAlert size={18} /> : <Sparkles size={18} />}</div>
            <div><strong>{item.title}</strong><p>{item.text}</p></div>
          </div>
        ))}
      </div>
    </article>
  )
}

function ConnectorStrip({ connectors, diagnostics, googleConfigured, connectGoogle, syncAll, syncing, actionMessage }) {
  return (
    <section className="connector-strip">
      <div>
        <span className="eyebrow">PROSSIMO PASSO</span>
        <h3>Collega le fonti reali</h3>
        <p>Apri Connettori per vedere cosa manca oppure avvia subito una sincronizzazione.</p>
      </div>
      <div className="connector-actions">
        <div className="connector-mini-grid">
          {connectors.map((connector) => {
            const diag = diagnostics.find((item) => item.provider === connector.provider)
            const ready = connector.status === 'connected' || diag?.configured
            return (
              <div className="connector-mini" key={connector.provider}>
                <span className={`status-dot ${ready ? 'ready' : ''}`} />
                <div><strong>{prettyProvider(connector.provider)}</strong><small>{connector.status === 'connected' ? 'Sincronizzato' : ready ? 'Pronto' : 'Da configurare'}</small></div>
              </div>
            )
          })}
        </div>
        <div className="connector-buttons">
          <button className="primary-action" onClick={connectGoogle}>{googleConfigured ? 'Ricollega Google' : 'Collega Google'}</button>
          <button className="secondary-action" onClick={syncAll} disabled={syncing}>{syncing ? 'Sincronizzo…' : 'Sincronizza tutto'}</button>
        </div>
        {actionMessage && <p className="action-message">{actionMessage}</p>}
      </div>
    </section>
  )
}

function connectorDescription(provider) {
  return ({
    wordpress: 'Pagine, articoli e tracker conversioni del sito.',
    ga4: 'Sessioni, utenti, landing page e key events.',
    search_console: 'Query, click, impression, CTR e posizione.',
    google_business: 'Search/Maps, chiamate, sito, indicazioni e keyword.',
    meta: 'Facebook Page Insights e contenuti.',
  })[provider] || ''
}

function providerIcon(provider) {
  const Icon = ({
    wordpress: Globe2,
    ga4: Activity,
    search_console: Search,
    google_business: Building2,
    meta: Share2,
  })[provider] || Link2
  return <Icon size={20} />
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
  return <div className="source-status"><Icon size={16} /><span>{label}</span><i className={connected ? 'connected' : ''} /></div>
}

function KpiCard({ item, index }) {
  const icons = [Users, Share2, Globe2, Target]
  const Icon = icons[index] || Activity
  const change = Number(item.change || 0)
  return (
    <article className="kpi-card">
      <div className="kpi-top"><span className="kpi-icon"><Icon size={19} /></span><span className={`change ${change >= 0 ? 'positive' : 'negative'}`}>{change > 0 ? '+' : ''}{change}%</span></div>
      <strong>{formatNumber(item.value)}</strong>
      <p>{item.label}</p>
    </article>
  )
}

function PanelHeader({ eyebrow, title, extra }) {
  return <div className="panel-header"><div><span>{eyebrow}</span><h3>{title}</h3></div>{extra}</div>
}

function TrendTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return <div className="tooltip"><small>{label}</small>{payload.map((item) => <div key={item.dataKey}><span>{item.dataKey}</span><strong>{formatNumber(item.value)}</strong></div>)}</div>
}

function SourceTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const item = payload[0].payload
  return <div className="tooltip"><small>{item.name}</small><div><span>Visite</span><strong>{formatNumber(item.visits)}</strong></div><div><span>Lead</span><strong>{formatNumber(item.leads)}</strong></div></div>
}

export default App
