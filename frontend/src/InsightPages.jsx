import { useCallback, useEffect, useRef, useState } from 'react'
import { HeartPulse, History, RefreshCw, Route, SearchCheck, Users } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

// ---------------------------------------------------------------------------
// utilità condivise
// ---------------------------------------------------------------------------

const nf = new Intl.NumberFormat('it-IT', { maximumFractionDigits: 0 })
const nf1 = new Intl.NumberFormat('it-IT', { maximumFractionDigits: 1 })
const num = (v) => nf.format(v || 0)
const pct = (v) => `${nf1.format(v || 0)}%`
const duration = (seconds) => {
  if (seconds === null || seconds === undefined) return '—'
  const s = Math.round(seconds)
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, '0')}s`
  return `${Math.floor(s / 3600)}h ${Math.round((s % 3600) / 60)}m`
}
const shortUrl = (url) => {
  try {
    const u = new URL(url)
    return u.pathname || '/'
  } catch {
    return url || '/'
  }
}
const CONTACT_LABEL = {
  whatsapp_click: 'WhatsApp',
  phone_click: 'Telefono',
  form_submit: 'Modulo',
  email_click: 'Email',
}

function useApi(url) {
  const [state, setState] = useState({ data: null, loading: true, error: '' })
  const load = useCallback(async () => {
    setState((prev) => ({ ...prev, loading: true, error: '' }))
    try {
      const response = await fetch(url)
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || `Errore ${response.status}`)
      setState({ data: payload, loading: false, error: '' })
    } catch (error) {
      setState({ data: null, loading: false, error: error.message })
    }
  }, [url])
  useEffect(() => { load() }, [load])
  return { ...state, reload: load }
}

function Intro({ icon: Icon, kicker, title, text }) {
  return (
    <section className="page-intro">
      <div className="page-intro-icon"><Icon size={22} /></div>
      <div><span className="eyebrow">{kicker}</span><h2>{title}</h2><p>{text}</p></div>
    </section>
  )
}

function Panel({ eyebrow, title, extra, children, className = '' }) {
  return (
    <article className={`panel page-panel ${className}`}>
      <div className="panel-header"><div><span>{eyebrow}</span><h3>{title}</h3></div>{extra}</div>
      {children}
    </article>
  )
}

function Empty({ children }) {
  return <div className="empty-state">{children}</div>
}

function Kpis({ items }) {
  return (
    <section className="mini-kpi-grid insight-kpis">
      {items.map(([label, value, hint]) => (
        <article className="mini-kpi" key={label}>
          <span>{label}</span>
          <strong>{value}</strong>
          {hint && <small className="mini-kpi-hint">{hint}</small>}
        </article>
      ))}
    </section>
  )
}

// Tabella generica: columns = [{ key, label, render?, numeric? }]
function Table({ columns, rows, empty = 'Nessun dato nel periodo.', max }) {
  if (!rows?.length) return <Empty>{empty}</Empty>
  const visible = max ? rows.slice(0, max) : rows
  return (
    <div className="g-table-wrap">
      <table className="g-table">
        <thead>
          <tr>{columns.map((c) => <th key={c.key} className={c.numeric ? 'num' : ''}>{c.label}</th>)}</tr>
        </thead>
        <tbody>
          {visible.map((row, index) => (
            <tr key={row.id || `${index}-${row[columns[0].key]}`}>
              {columns.map((c) => (
                <td key={c.key} className={c.numeric ? 'num' : ''} title={typeof row[c.key] === 'string' ? row[c.key] : undefined}>
                  {c.render ? c.render(row) : row[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// Barre orizzontali: la lunghezza è relativa al valore più alto della lista.
function BarList({ rows, label = 'name', value = 'sessions', format = num, detail }) {
  if (!rows?.length) return <Empty>Nessun dato nel periodo.</Empty>
  const top = Math.max(...rows.map((r) => r[value] || 0), 1)
  return (
    <div className="bar-list">
      {rows.map((row) => (
        <div className="bar-row" key={row[label]}>
          <div className="bar-row-text">
            <span title={row[label]}>{row[label]}</span>
            <strong>{format(row[value])}</strong>
          </div>
          <div className="bar-track"><div className="bar-fill" style={{ width: `${((row[value] || 0) / top) * 100}%` }} /></div>
          {detail && <small>{detail(row)}</small>}
        </div>
      ))}
    </div>
  )
}

function SmallBars({ data, x, y, color = '#657fff', height = 190 }) {
  const hasData = data?.some((d) => d[y] > 0)
  if (!hasData) return <Empty>Nessun dato nel periodo.</Empty>
  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer>
        <BarChart data={data} margin={{ top: 6, right: 4, left: -22, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(148,163,184,.12)" />
          <XAxis dataKey={x} tick={{ fill: '#6f7d94', fontSize: 9 }} interval="preserveStartEnd" />
          <YAxis tick={{ fill: '#6f7d94', fontSize: 9 }} allowDecimals={false} />
          <Tooltip
            cursor={{ fill: 'rgba(101,127,255,.08)' }}
            contentStyle={{ background: '#111c2e', border: '1px solid rgba(148,163,184,.2)', borderRadius: 8, fontSize: 11 }}
            formatter={(v) => num(v)}
          />
          <Bar dataKey={y} fill={color} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function Loading({ state, children }) {
  if (state.loading && !state.data) return <Empty>Carico i dati…</Empty>
  if (state.error) return <Empty>Non riesco a leggere i dati: {state.error}</Empty>
  return children
}

// ---------------------------------------------------------------------------
// Pubblico
// ---------------------------------------------------------------------------

export function AudiencePage({ days }) {
  const state = useApi(`/api/analytics/audience?days=${days}`)
  const d = state.data
  const s = d?.summary || {}
  const engagementDetail = (row) =>
    [
      row.engagement_rate !== undefined && `coinvolgimento ${pct(row.engagement_rate)}`,
      row.conversion_rate !== undefined && `conversioni ${pct(row.conversion_rate)}`,
      row.avg_engagement_sec !== undefined && `tempo medio ${duration(row.avg_engagement_sec)}`,
    ].filter(Boolean).join(', ')

  return (
    <>
      <Intro
        icon={Users}
        kicker="PUBBLICO"
        title="Chi visita il sito e quando"
        text="Dispositivi, zone, canali, campagne e orari da Google Analytics, affiancati ai contatti misurati dal tracker del sito."
      />
      <Loading state={state}>
        {!s.sessions && !d?.tracker_devices?.length ? (
          <Panel eyebrow="DATI" title="Nessun dato di pubblico nel periodo">
            <Empty>Collega Google Analytics 4 e avvia la sincronizzazione da Connettori. Alla prima sincronizzazione GE360 scarica tutto lo storico disponibile.</Empty>
          </Panel>
        ) : (
          <>
            <Kpis
              items={[
                ['Sessioni', num(s.sessions)],
                ['Coinvolgimento', pct(s.engagement_rate), 'sessioni attive oltre 10s'],
                ['Tempo medio', duration(s.avg_engagement_sec), 'per sessione'],
                ['Pagine per sessione', nf1.format(s.pages_per_session || 0)],
                ['Conversioni GA4', num(s.key_events), pct(s.conversion_rate)],
                ['Nuovi utenti', num(s.new_users)],
                ['Pagine viste', num(s.page_views)],
                ['Visite da Trieste', pct(d.trieste_share), 'sul totale con città nota'],
              ]}
            />

            <section className="two-column-grid">
              <Panel eyebrow="DISPOSITIVI" title="Da cosa navigano">
                <BarList rows={d.devices} detail={engagementDetail} />
              </Panel>
              <Panel eyebrow="CANALI" title="Da dove arrivano">
                <BarList rows={d.channels} detail={engagementDetail} />
              </Panel>
            </section>

            <Panel eyebrow="ZONE" title="Città delle visite">
              <Table
                max={20}
                columns={[
                  { key: 'name', label: 'Città' },
                  { key: 'sessions', label: 'Sessioni', numeric: true, render: (r) => num(r.sessions) },
                  { key: 'engagement_rate', label: 'Coinvolgimento', numeric: true, render: (r) => pct(r.engagement_rate) },
                  { key: 'keyEvents', label: 'Conversioni', numeric: true, render: (r) => num(r.keyEvents) },
                  { key: 'conversion_rate', label: 'Tasso', numeric: true, render: (r) => pct(r.conversion_rate) },
                ]}
                rows={d.cities}
              />
            </Panel>

            <section className="two-column-grid">
              <Panel eyebrow="ORARI" title="Sessioni per ora">
                <SmallBars data={d.hours} x="hour" y="sessions" />
              </Panel>
              <Panel eyebrow="ORARI" title="Contatti per ora (ora italiana)">
                <SmallBars data={d.contact_hours} x="hour" y="contacts" color="#28d7a3" />
              </Panel>
            </section>

            <section className="two-column-grid">
              <Panel eyebrow="SETTIMANA" title="Sessioni per giorno">
                <SmallBars data={d.weekdays} x="day" y="sessions" />
              </Panel>
              <Panel eyebrow="SETTIMANA" title="Contatti per giorno">
                <SmallBars data={d.contact_weekdays} x="day" y="contacts" color="#28d7a3" />
              </Panel>
            </section>

            <Panel eyebrow="SORGENTI" title="Sorgente e mezzo">
              <Table
                max={25}
                columns={[
                  { key: 'name', label: 'Sorgente / mezzo' },
                  { key: 'sessions', label: 'Sessioni', numeric: true, render: (r) => num(r.sessions) },
                  { key: 'engagement_rate', label: 'Coinvolgimento', numeric: true, render: (r) => pct(r.engagement_rate) },
                  { key: 'keyEvents', label: 'Conversioni', numeric: true, render: (r) => num(r.keyEvents) },
                  { key: 'conversion_rate', label: 'Tasso', numeric: true, render: (r) => pct(r.conversion_rate) },
                ]}
                rows={d.source_medium}
              />
            </Panel>

            <section className="two-column-grid">
              <Panel eyebrow="CAMPAGNE" title="Campagne con UTM">
                <Table
                  columns={[
                    { key: 'name', label: 'Campagna' },
                    { key: 'sessions', label: 'Sessioni', numeric: true, render: (r) => num(r.sessions) },
                    { key: 'keyEvents', label: 'Conversioni', numeric: true, render: (r) => num(r.keyEvents) },
                  ]}
                  rows={d.campaigns}
                  empty="Nessuna campagna tracciata. Aggiungi utm_campaign ai link dei post e delle inserzioni."
                />
              </Panel>
              <Panel eyebrow="FEDELTÀ" title="Nuovi e di ritorno">
                <BarList rows={d.new_vs_returning} detail={engagementDetail} />
              </Panel>
            </section>

            <Panel eyebrow="TRACKER DEL SITO" title="Contatti per dispositivo">
              <Table
                columns={[
                  { key: 'name', label: 'Dispositivo' },
                  { key: 'sessions', label: 'Sessioni', numeric: true, render: (r) => num(r.sessions) },
                  { key: 'contacts', label: 'Contatti', numeric: true, render: (r) => num(r.contacts) },
                  { key: 'contact_rate', label: 'Tasso contatto', numeric: true, render: (r) => pct(r.contact_rate) },
                ]}
                rows={d.tracker_devices}
                empty="Il tracker 0.2 non ha ancora registrato sessioni. Aggiorna il plugin GE360 Tracker sul sito."
              />
              {d.notes?.map((note) => <p className="panel-copy subtle" key={note}>{note}</p>)}
            </Panel>
          </>
        )}
      </Loading>
    </>
  )
}

// ---------------------------------------------------------------------------
// Percorsi
// ---------------------------------------------------------------------------

export function JourneysPage({ days }) {
  const state = useApi(`/api/analytics/journeys?days=${days}&limit=40`)
  const d = state.data
  const groupColumns = (label) => [
    { key: 'name', label },
    { key: 'sessions', label: 'Sessioni', numeric: true, render: (r) => num(r.sessions) },
    { key: 'contacts', label: 'Contatti', numeric: true, render: (r) => num(r.contacts) },
    { key: 'contact_rate', label: 'Tasso', numeric: true, render: (r) => pct(r.contact_rate) },
    { key: 'avg_pages', label: 'Pagine', numeric: true, render: (r) => nf1.format(r.avg_pages) },
    { key: 'avg_engaged_sec', label: 'Attenzione', numeric: true, render: (r) => duration(r.avg_engaged_sec) },
  ]

  return (
    <>
      <Intro
        icon={Route}
        kicker="PERCORSI"
        title="Dalla prima visita al contatto"
        text="Ogni sessione ricostruita dal tracker del sito: da dove arriva la persona, quali pagine legge, per quanto tempo, e cosa fa prima di scriverti o chiamarti."
      />
      <Loading state={state}>
        {!d?.tracked_sessions ? (
          <Panel eyebrow="TRACKER" title="Nessuna sessione registrata">
            <Empty>
              Installa o aggiorna il plugin GE360 Tracker 0.2 sul sito WordPress. I percorsi compaiono dalle prime visite successive all'aggiornamento.
            </Empty>
          </Panel>
        ) : (
          <>
            <Kpis
              items={[
                ['Sessioni tracciate', num(d.tracked_sessions)],
                ['Sessioni con contatto', num(d.converted_sessions)],
                ['Tasso di contatto', pct(d.contact_rate)],
                ['Tempo al contatto', duration(d.median_seconds_to_contact), 'valore mediano'],
                ['Pagine prima del contatto', d.median_pages_to_contact ?? '—', 'valore mediano'],
                ['Moduli iniziati', num(d.form_abandonment.started)],
                ['Moduli inviati', num(d.form_abandonment.submitted)],
                ['Moduli abbandonati', pct(d.form_abandonment.abandon_rate)],
              ]}
            />

            <section className="two-column-grid">
              <Panel eyebrow="FUNNEL" title="Quante sessioni arrivano fino in fondo">
                <div className="funnel-steps">
                  {d.funnel.map((step, index) => {
                    const first = d.funnel[0].value || 1
                    const previous = index ? d.funnel[index - 1].value || 1 : first
                    return (
                      <div className="funnel-step" key={step.label}>
                        <div className="funnel-step-text">
                          <span>{step.label}</span>
                          <strong>{num(step.value)}</strong>
                          {index > 0 && <small>{pct((step.value / previous) * 100)} del passo prima</small>}
                        </div>
                        <div className="bar-track"><div className="bar-fill" style={{ width: `${(step.value / first) * 100}%` }} /></div>
                      </div>
                    )
                  })}
                </div>
                <p className="panel-copy subtle">Interessate: almeno 2 pagine, 30 secondi di attenzione o metà pagina letta.</p>
              </Panel>
              <Panel eyebrow="PERCORSI" title="Strade più frequenti verso un contatto">
                {d.top_paths.length ? (
                  <ol className="path-list">
                    {d.top_paths.map((p) => (
                      <li key={p.path}><span>{p.path}</span><strong>{num(p.count)}</strong></li>
                    ))}
                  </ol>
                ) : <Empty>Nessun contatto con percorso completo nel periodo.</Empty>}
              </Panel>
            </section>

            <Panel eyebrow="SORGENTI" title="Quale sorgente porta contatti">
              <Table columns={groupColumns('Sorgente')} rows={d.by_source} />
            </Panel>
            <Panel eyebrow="LANDING" title="Pagine di ingresso che convertono">
              <Table columns={groupColumns('Pagina di ingresso')} rows={d.by_landing} />
            </Panel>
            <section className="two-column-grid">
              <Panel eyebrow="DISPOSITIVI" title="Conversione per dispositivo">
                <Table columns={groupColumns('Dispositivo').slice(0, 4)} rows={d.by_device} />
              </Panel>
              <Panel eyebrow="MEZZO" title="Conversione per tipo di traffico">
                <Table columns={groupColumns('Mezzo').slice(0, 4)} rows={d.by_medium} />
              </Panel>
            </section>

            <Panel eyebrow="VISITE RIPETUTE" title="Chi torna più volte prima di contattarti">
              {d.returning_visitors.tracked_visitors ? (
                <>
                  <Kpis
                    items={[
                      ['Visitatori riconosciuti', num(d.returning_visitors.tracked_visitors)],
                      ['Con contatto', num(d.returning_visitors.converted_visitors)],
                      ['Visite prima del contatto', d.returning_visitors.avg_sessions_before_contact ?? '—', 'in media'],
                    ]}
                  />
                  <section className="two-column-grid">
                    <div>
                      <p className="panel-copy">Prima sorgente (chi li ha fatti conoscere)</p>
                      <BarList rows={d.returning_visitors.first_touch} label="source" value="contacts" />
                    </div>
                    <div>
                      <p className="panel-copy">Ultima sorgente (chi li ha convinti)</p>
                      <BarList rows={d.returning_visitors.last_touch} label="source" value="contacts" />
                    </div>
                  </section>
                </>
              ) : (
                <Empty>
                  Per collegare più visite della stessa persona attiva “Riconosci i visitatori di ritorno” nelle impostazioni del plugin, dopo aver verificato il banner consenso.
                </Empty>
              )}
            </Panel>

            <Panel eyebrow="ULTIMI CONTATTI" title="Com'è arrivato chi ti ha contattato">
              <Table
                columns={[
                  { key: 'at', label: 'Quando', render: (r) => new Date(r.at).toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' }) },
                  { key: 'contact', label: 'Contatto', render: (r) => CONTACT_LABEL[r.contact] || r.contact },
                  { key: 'source', label: 'Sorgente', render: (r) => `${r.source}${r.medium ? ` / ${r.medium}` : ''}` },
                  { key: 'device', label: 'Dispositivo' },
                  { key: 'pages', label: 'Pagine viste', render: (r) => r.pages.join(' → ') },
                  { key: 'engaged_sec', label: 'Attenzione', numeric: true, render: (r) => duration(r.engaged_sec) },
                ]}
                rows={d.recent_contacts}
              />
            </Panel>
          </>
        )}
      </Loading>
    </>
  )
}

// ---------------------------------------------------------------------------
// Ricerca Google
// ---------------------------------------------------------------------------

export function SearchDeepPage({ days }) {
  const period = Math.max(days, 28)
  const opportunities = useApi(`/api/analytics/search/opportunities?days=${period}`)
  const cannibal = useApi(`/api/analytics/search/cannibalization?days=${period}`)
  const [filter, setFilter] = useState('')
  const [device, setDevice] = useState('')
  const [query, setQuery] = useState('')
  const explorer = useApi(
    `/api/analytics/search/query-page?days=${period}&limit=300&contains=${encodeURIComponent(query)}${device ? `&device=${device}` : ''}`
  )

  return (
    <>
      <Intro
        icon={SearchCheck}
        kicker="RICERCA GOOGLE"
        title="Quale pagina esce per quale ricerca"
        text={`Search Console incrociato ricerca per ricerca e pagina per pagina, sugli ultimi ${period} giorni. Qui trovi i click che stai lasciando sul tavolo.`}
      />

      <Panel
        eyebrow="OPPORTUNITÀ"
        title="Ricerche su cui guadagnare click"
        extra={<span className="panel-badge">stima click in più</span>}
      >
        <Loading state={opportunities}>
          <Table
            columns={[
              { key: 'query', label: 'Ricerca' },
              { key: 'type', label: 'Situazione' },
              { key: 'page', label: 'Pagina', render: (r) => shortUrl(r.page) },
              { key: 'position', label: 'Posizione', numeric: true, render: (r) => nf1.format(r.position) },
              { key: 'impressions', label: 'Impression', numeric: true, render: (r) => num(r.impressions) },
              { key: 'ctr', label: 'CTR', numeric: true, render: (r) => pct(r.ctr) },
              { key: 'potential_clicks', label: 'Potenziale', numeric: true, render: (r) => `+${num(r.potential_clicks)}` },
            ]}
            rows={opportunities.data}
            empty="Nessuna opportunità: servono almeno 30 impression per ricerca nel periodo."
          />
          <p className="panel-copy subtle">
            Vicina alla top 3: migliora contenuto e link interni verso quella pagina. CTR basso: riscrivi titolo e meta description.
          </p>
        </Loading>
      </Panel>

      <Panel eyebrow="CANNIBALIZZAZIONE" title="Pagine che si rubano posizioni">
        <Loading state={cannibal}>
          {cannibal.data?.length ? (
            <div className="cannibal-list">
              {cannibal.data.map((item) => (
                <div className="cannibal-item" key={item.query}>
                  <div className="cannibal-head">
                    <strong>{item.query}</strong>
                    <span className={`rating-pill ${item.severity === 'alta' ? 'bad' : 'warn'}`}>priorità {item.severity}</span>
                    <small>{num(item.impressions)} impression, {num(item.clicks)} click</small>
                  </div>
                  <Table
                    columns={[
                      { key: 'page', label: 'Pagina', render: (r) => `${shortUrl(r.page)}${r.page === item.main_page ? ' (principale)' : ''}` },
                      { key: 'position', label: 'Posizione', numeric: true, render: (r) => nf1.format(r.position) },
                      { key: 'share_impressions', label: 'Quota impression', numeric: true, render: (r) => pct(r.share_impressions) },
                      { key: 'share_clicks', label: 'Quota click', numeric: true, render: (r) => pct(r.share_clicks) },
                    ]}
                    rows={item.pages}
                  />
                  <p className="panel-copy">{item.advice}</p>
                </div>
              ))}
            </div>
          ) : <Empty>Nessuna ricerca contesa da più pagine nel periodo.</Empty>}
        </Loading>
      </Panel>

      <Panel eyebrow="ESPLORA" title="Tutte le combinazioni ricerca e pagina">
        <form
          className="insight-filters"
          onSubmit={(event) => {
            event.preventDefault()
            setQuery(filter.trim())
          }}
        >
          <input
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filtra per parola o pagina, es. bagno, trieste, /marmorino"
            aria-label="Filtra ricerche o pagine"
          />
          <select value={device} onChange={(event) => setDevice(event.target.value)} aria-label="Dispositivo">
            <option value="">Tutti i dispositivi</option>
            <option value="mobile">Mobile</option>
            <option value="desktop">Desktop</option>
            <option value="tablet">Tablet</option>
          </select>
          <button className="secondary-action" type="submit">Filtra</button>
        </form>
        <Loading state={explorer}>
          <Table
            columns={[
              { key: 'query', label: 'Ricerca' },
              { key: 'page', label: 'Pagina', render: (r) => shortUrl(r.page) },
              { key: 'clicks', label: 'Click', numeric: true, render: (r) => num(r.clicks) },
              { key: 'impressions', label: 'Impression', numeric: true, render: (r) => num(r.impressions) },
              { key: 'ctr', label: 'CTR', numeric: true, render: (r) => pct(r.ctr) },
              { key: 'position', label: 'Posizione', numeric: true, render: (r) => nf1.format(r.position) },
            ]}
            rows={explorer.data}
            empty="Nessuna riga. I dati ricerca+pagina arrivano con la prima sincronizzazione Search Console della versione 0.7."
          />
        </Loading>
      </Panel>
    </>
  )
}

// ---------------------------------------------------------------------------
// Salute del sito
// ---------------------------------------------------------------------------

const VITAL_INFO = {
  LCP: ['Caricamento', 'tempo per vedere il contenuto principale'],
  INP: ['Reattività', 'ritardo dopo un tocco o un click'],
  CLS: ['Stabilità', 'quanto si sposta la pagina mentre carica'],
  FCP: ['Primo contenuto', 'quando appare qualcosa sullo schermo'],
  TTFB: ['Risposta server', 'tempo di risposta dell\u2019hosting'],
}
const ratingClass = { buono: 'good', 'da migliorare': 'warn', scarso: 'bad' }
const formatVital = (metric, value) =>
  value === null || value === undefined
    ? '—'
    : metric === 'CLS'
      ? nf1.format(value)
      : value >= 1000 ? `${nf1.format(value / 1000)} s` : `${num(value)} ms`

export function SiteHealthPage({ days }) {
  const state = useApi(`/api/analytics/site-health?days=${days}`)
  const d = state.data

  return (
    <>
      <Intro
        icon={HeartPulse}
        kicker="SALUTE DEL SITO"
        title="Com'è davvero il sito per chi lo usa"
        text="Velocità misurata sui telefoni e computer dei visitatori reali, pagine rotte, punti dove le persone cliccano per frustrazione e quanto leggono di ogni pagina."
      />
      <Loading state={state}>
        <section className="vital-grid">
          {(d?.vitals || []).map((v) => (
            <article className={`vital-card ${ratingClass[v.rating] || ''}`} key={v.metric}>
              <span>{VITAL_INFO[v.metric]?.[0]} ({v.metric})</span>
              <strong>{formatVital(v.metric, v.p75)}</strong>
              <em className={`rating-pill ${ratingClass[v.rating] || ''}`}>{v.samples ? v.rating : 'nessun dato'}</em>
              <small>{VITAL_INFO[v.metric]?.[1]}</small>
              {v.samples > 0 && (
                <small>
                  {num(v.samples)} misure, {pct(v.poor_share)} scarse
                  {Object.entries(v.by_device || {}).map(([dev, val]) => `, ${dev} ${formatVital(v.metric, val)}`).join('')}
                </small>
              )}
            </article>
          ))}
        </section>
        <p className="panel-copy subtle">Valori al 75° percentile, come li valuta Google: 3 visitatori su 4 hanno un'esperienza uguale o migliore.</p>

        <section className="two-column-grid">
          <Panel eyebrow="VELOCITÀ" title="Pagine da sistemare">
            <Table
              columns={[
                { key: 'page', label: 'Pagina' },
                { key: 'metric', label: 'Metrica' },
                { key: 'p75', label: 'Valore', numeric: true, render: (r) => formatVital(r.metric, r.p75) },
                { key: 'rating', label: 'Giudizio', render: (r) => <em className={`rating-pill ${ratingClass[r.rating]}`}>{r.rating}</em> },
              ]}
              rows={d?.worst_pages}
              empty="Nessuna pagina lenta con almeno 5 misure."
            />
          </Panel>
          <Panel eyebrow="CAUSE" title="Elementi che rallentano">
            <Table
              columns={[
                { key: 'element', label: 'Elemento' },
                { key: 'metric', label: 'Metrica' },
                { key: 'count', label: 'Volte', numeric: true, render: (r) => num(r.count) },
              ]}
              rows={d?.poor_elements}
              empty="Nessun elemento problematico registrato."
            />
          </Panel>
        </section>

        <Panel eyebrow="LETTURA" title="Quanto viene letta ogni pagina">
          <Table
            columns={[
              { key: 'page', label: 'Pagina' },
              { key: 'views', label: 'Visite', numeric: true, render: (r) => num(r.views) },
              { key: 'avg_engaged_sec', label: 'Attenzione media', numeric: true, render: (r) => duration(r.avg_engaged_sec) },
              { key: 'avg_max_scroll', label: 'Letta fino al', numeric: true, render: (r) => (r.avg_max_scroll ? `${r.avg_max_scroll}%` : '—') },
            ]}
            rows={d?.engagement}
            empty="Il tracker 0.2 non ha ancora registrato letture."
          />
        </Panel>

        <section className="two-column-grid">
          <Panel eyebrow="ERRORI" title="Pagine non trovate (404)">
            <Table
              columns={[
                { key: 'path', label: 'Indirizzo richiesto' },
                { key: 'count', label: 'Visite', numeric: true, render: (r) => num(r.count) },
              ]}
              rows={d?.not_found}
              empty="Nessuna pagina 404 visitata. Ottimo."
            />
          </Panel>
          <Panel eyebrow="FRUSTRAZIONE" title="Click ripetuti a vuoto">
            <Table
              columns={[
                { key: 'page', label: 'Pagina' },
                { key: 'element', label: 'Elemento' },
                { key: 'count', label: 'Volte', numeric: true, render: (r) => num(r.count) },
              ]}
              rows={d?.rage_clicks}
              empty="Nessun click ripetuto: nessun elemento sembra rotto."
            />
          </Panel>
        </section>

        <section className="two-column-grid">
          <Panel eyebrow="USCITE" title="Link esterni cliccati">
            <BarList rows={d?.outbound} label="host" value="count" />
          </Panel>
          <Panel eyebrow="DOWNLOAD" title="File scaricati">
            <Table
              columns={[
                { key: 'page', label: 'Pagina' },
                { key: 'type', label: 'Tipo' },
                { key: 'count', label: 'Download', numeric: true, render: (r) => num(r.count) },
              ]}
              rows={d?.downloads}
              empty="Nessun download nel periodo."
            />
          </Panel>
        </section>
      </Loading>
    </>
  )
}

// ---------------------------------------------------------------------------
// Storico dati (in Connettori)
// ---------------------------------------------------------------------------

const HISTORY_LABELS = {
  ga4: 'Google Analytics 4',
  search_console: 'Search Console',
  google_business: 'Google Business',
  meta: 'Facebook + Instagram',
  wordpress: 'WordPress',
  search_query_page: 'Search Console ricerca + pagina',
  tracker_sessions: 'Tracker del sito',
}

export function HistoryPanel() {
  const history = useApi('/api/analytics/history')
  const [running, setRunning] = useState([])
  const [message, setMessage] = useState('')
  const timer = useRef(null)
  const reloadHistory = history.reload

  const poll = useCallback(async () => {
    try {
      const response = await fetch('/api/sync/running')
      const payload = await response.json()
      setRunning(payload.running || [])
      if (payload.running?.length) {
        timer.current = window.setTimeout(poll, 5000)
      } else {
        reloadHistory()
      }
    } catch {
      /* il prossimo caricamento riproverà */
    }
  }, [reloadHistory])

  useEffect(() => {
    poll()
    return () => window.clearTimeout(timer.current)
  }, [poll])

  const start = async (provider) => {
    setMessage('')
    const response = await fetch(`/api/sync/${provider}/history`, { method: 'POST' })
    const payload = await response.json()
    setMessage(payload.message || payload.detail || '')
    window.clearTimeout(timer.current)
    poll()
  }

  return (
    <Panel
      eyebrow="STORICO"
      title="Da quando partono i dati"
      extra={<button className="secondary-action" onClick={() => history.reload()}><RefreshCw size={13} /> Aggiorna</button>}
    >
      <Loading state={history}>
        <Table
          columns={[
            { key: 'provider', label: 'Fonte', render: (r) => HISTORY_LABELS[r.provider] || r.provider },
            { key: 'first_data', label: 'Dal', render: (r) => r.first_data || '—' },
            { key: 'last_data', label: 'Al', render: (r) => r.last_data || '—' },
            { key: 'datapoints', label: 'Righe', numeric: true, render: (r) => num(r.datapoints) },
            {
              key: 'history_complete',
              label: 'Storico completo',
              render: (r) => {
                if (r.history_complete === null || r.history_complete === undefined) return '—'
                if (running.includes(r.provider)) return <em className="rating-pill warn">in scaricamento…</em>
                return (
                  <span className="history-action">
                    <em className={`rating-pill ${r.history_complete ? 'good' : 'warn'}`}>{r.history_complete ? 'sì' : 'no'}</em>
                    <button className="link-action" onClick={() => start(r.provider)}>
                      <History size={12} /> {r.history_complete ? 'Riscarica' : 'Scarica'}
                    </button>
                  </span>
                )
              },
            },
          ]}
          rows={history.data}
        />
        {message && <p className="panel-copy">{message}</p>}
        <p className="panel-copy subtle">
          GA4 fino a 18 mesi, Search Console 16 mesi. Il primo scaricamento può richiedere alcuni minuti; la dashboard resta utilizzabile nel frattempo.
        </p>
      </Loading>
    </Panel>
  )
}

// Componenti condivisi con le pagine Meta e Google Business.
export { useApi, Intro, Panel, Empty, Kpis, Table, BarList, SmallBars, Loading, num, pct, nf1, duration }
