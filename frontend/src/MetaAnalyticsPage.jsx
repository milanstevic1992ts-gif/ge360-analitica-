import { useEffect, useMemo, useState } from 'react'
import {
  Activity,
  Camera,
  Eye,
  Heart,
  MessageCircle,
  RefreshCw,
  Share2,
  TrendingUp,
  Users,
} from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

const LABELS = {
  instagram_followers: 'Follower Instagram',
  instagram_media_count: 'Contenuti Instagram',
  instagram_reach: 'Copertura Instagram',
  instagram_views: 'Visualizzazioni Instagram',
  instagram_accounts_engaged: 'Account coinvolti',
  instagram_total_interactions: 'Interazioni Instagram',
  instagram_profile_views: 'Visite profilo',
  instagram_website_clicks: 'Click sito',
  meta_page_post_engagements: 'Interazioni Facebook',
  meta_page_follows: 'Nuovi follower Facebook',
  meta_page_views_total: 'Visite Pagina Facebook',
  meta_page_impressions: 'Impression Facebook',
  meta_page_impressions_unique: 'Copertura Facebook',
  meta_page_engaged_users: 'Utenti coinvolti Facebook',
  meta_page_video_views: 'Video views Facebook',
  meta_page_media_view: 'Visualizzazioni Facebook',
  meta_page_total_media_view_unique: 'Persone raggiunte Facebook',
  meta_page_daily_follows_unique: 'Nuovi follower Facebook',
  instagram_follower_count: 'Nuovi follower Instagram',
  instagram_profile_links_taps: 'Tap link profilo',
}

const nf = new Intl.NumberFormat('it-IT', { maximumFractionDigits: 0 })

function prettyMetric(metric) {
  return LABELS[metric] || metric
    .replace(/^meta_/, '')
    .replace(/^instagram_/, '')
    .replaceAll('_', ' ')
    .replace(/\b\w/g, (m) => m.toUpperCase())
}

function MetaAnalyticsPage({ days = 30, syncProvider, syncing }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = async () => {
    setLoading(true)
    try {
      const response = await fetch(`/api/analytics/meta-dashboard?days=${days}`)
      const payload = await response.json()
      setData(payload)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [days])

  const kpis = useMemo(() => {
    const latest = data?.latest || {}
    const priority = [
      'instagram_followers',
      'instagram_reach',
      'instagram_views',
      'instagram_total_interactions',
      'meta_page_post_engagements',
      'meta_page_media_view',
      'meta_page_total_media_view_unique',
      'meta_page_views_total',
      'meta_page_impressions',
      'meta_page_engaged_users',
    ]
    return priority
      .filter((key) => latest[key])
      .slice(0, 8)
      .map((key) => ({ key, ...latest[key] }))
  }, [data])

  const chartMetric = useMemo(() => {
    const available = data?.available_metrics || []
    return [
      'instagram_reach',
      'instagram_views',
      'meta_page_impressions',
      'meta_page_post_engagements',
      'instagram_total_interactions',
    ].find((key) => available.includes(key)) || available[0]
  }, [data])

  const chartData = useMemo(() => {
    if (!chartMetric) return []
    return (data?.series?.[chartMetric] || []).map((item) => ({
      date: new Date(item.captured_at).toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' }),
      value: item.value,
    }))
  }, [data, chartMetric])

  const content = data?.content_performance || []

  return (
    <div className="page-stack">
      <section className="hero">
        <div>
          <span className="hero-kicker"><Share2 size={15} /> META INTELLIGENCE</span>
          <h2>Facebook e Instagram, molto più in profondità.</h2>
          <p>KPI account, trend, copertura, visualizzazioni, interazioni e performance dei singoli contenuti.</p>
        </div>
        <button
          className="primary-action"
          disabled={syncing}
          onClick={async () => {
            await syncProvider?.('meta')
            await load()
          }}
        >
          <RefreshCw size={15} /> Aggiorna Meta
        </button>
      </section>

      <section className="kpi-grid">
        {kpis.length ? kpis.map((item, index) => {
          const icons = [Users, Eye, Activity, Heart, MessageCircle, TrendingUp, Camera, Share2]
          const Icon = icons[index % icons.length]
          return (
            <div className="kpi-card" key={item.key}>
              <div className="kpi-icon"><Icon size={19} /></div>
              <span>{prettyMetric(item.key)}</span>
              <strong>{nf.format(item.value || 0)}</strong>
              <small>{item.captured_at ? new Date(item.captured_at).toLocaleString('it-IT') : ''}</small>
            </div>
          )
        }) : (
          <div className="empty-card">
            <strong>{loading ? 'Carico i dati Meta…' : 'Nessun KPI Meta ancora disponibile'}</strong>
            <p>Esegui una sincronizzazione Meta per popolare le nuove statistiche.</p>
          </div>
        )}
      </section>

      {chartMetric && chartData.length > 0 && (
        <section className="panel">
          <div className="panel-heading">
            <div>
              <span className="eyebrow">TREND</span>
              <h3>{prettyMetric(chartMetric)}</h3>
            </div>
            <span>{data?.metric_count || 0} datapoint Meta nel periodo</span>
          </div>
          <div style={{ width: '100%', height: 320 }}>
            <ResponsiveContainer>
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip formatter={(value) => nf.format(value)} />
                <Area type="monotone" dataKey="value" stroke="currentColor" fill="currentColor" fillOpacity={0.12} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      <section className="panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">CONTENUTI</span>
            <h3>Post e Reel con più interazioni</h3>
          </div>
          <span>{content.length} contenuti con insight</span>
        </div>
        {content.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Contenuto</th>
                  <th>Tipo</th>
                  <th>Copertura / view</th>
                  <th>Interazioni</th>
                  <th>Metriche</th>
                </tr>
              </thead>
              <tbody>
                {content.map((item) => (
                  <tr key={item.external_id}>
                    <td>
                      {item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.title || 'Contenuto Meta'}</a> : item.title}
                    </td>
                    <td>{item.content_type}</td>
                    <td>{nf.format(item.reach_or_views || 0)}</td>
                    <td>{nf.format(item.engagement || 0)}</td>
                    <td>{Object.keys(item.metrics || {}).length}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="empty-card">
            <strong>Nessun insight per singolo contenuto ancora disponibile</strong>
            <p>Meta restituisce questi dati solo per contenuti e permessi compatibili; GE360 ignora automaticamente le metriche non concesse.</p>
          </div>
        )}
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <span className="eyebrow">COPERTURA DATI</span>
            <h3>Metriche Meta disponibili</h3>
          </div>
          <span>{data?.available_metrics?.length || 0} metriche</span>
        </div>
        <div className="chip-list">
          {(data?.available_metrics || []).map((metric) => (
            <span className="chip" key={metric}>{prettyMetric(metric)}</span>
          ))}
        </div>
      </section>
    </div>
  )
}

export default MetaAnalyticsPage
