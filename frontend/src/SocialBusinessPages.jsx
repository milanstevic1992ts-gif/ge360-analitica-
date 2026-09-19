import { MessageSquareText, Sparkles, Star, Store } from 'lucide-react'
import {
  BarList, Empty, Intro, Kpis, Loading, Panel, SmallBars, Table, nf1, num, pct, useApi,
} from './InsightPages'

// Variazione rispetto al periodo precedente, già in percentuale.
const Change = ({ value }) => {
  if (value === null || value === undefined) return null
  const cls = value > 0 ? 'good' : value < 0 ? 'bad' : 'warn'
  return <em className={`rating-pill ${cls}`}>{value > 0 ? '+' : ''}{nf1.format(value)}%</em>
}

const kpiItems = (rows) => rows.map((r) => [
  r.label,
  num(r.value),
  r.change === null || r.change === undefined ? 'nessun confronto' : `${r.change > 0 ? '+' : ''}${nf1.format(r.change)}% sul periodo prima`,
])

const Stars = ({ value }) => (value ? '★'.repeat(value) + '☆'.repeat(5 - value) : '—')

const contentLink = (r) => (
  r.url
    ? <a href={r.url} target="_blank" rel="noreferrer">{r.title || 'Apri'}</a>
    : (r.title || '—')
)

// ---------------------------------------------------------------------------
// Meta approfondito (sotto la pagina Meta Analytics)
// ---------------------------------------------------------------------------

export function MetaDeepPage({ days }) {
  const state = useApi(`/api/analytics/meta/deep?days=${days}`)
  const d = state.data

  return (
    <>
      <Intro
        icon={Sparkles}
        kicker="META APPROFONDITO"
        title="Cosa funziona davvero su Facebook e Instagram"
        text="Ogni post, reel e storia con copertura, interazioni e tasso di coinvolgimento. Formati, orari, crescita, pubblico e visite portate al sito."
      />
      <Loading state={state}>
        {d && (
          <>
            {d.notes?.map((n) => <p className="panel-copy subtle" key={n}>{n}</p>)}

            {!!d.instagram_kpis?.length && (
              <Panel eyebrow="INSTAGRAM" title={`Account${d.followers?.instagram ? ` · ${num(d.followers.instagram)} follower` : ''}`}>
                <Kpis items={kpiItems(d.instagram_kpis)} />
              </Panel>
            )}
            {!!d.facebook_kpis?.length && (
              <Panel eyebrow="FACEBOOK" title="Pagina">
                <Kpis items={kpiItems(d.facebook_kpis)} />
              </Panel>
            )}

            <Panel eyebrow="CLASSIFICA" title={`Contenuti migliori (${d.measured_count} con metriche su ${d.content_count})`}>
              <Table
                max={30}
                empty="Nessun contenuto misurato nel periodo."
                columns={[
                  { key: 'title', label: 'Contenuto', render: contentLink },
                  { key: 'format', label: 'Formato' },
                  { key: 'published_at', label: 'Pubblicato' },
                  { key: 'reach', label: 'Copertura', numeric: true, render: (r) => num(r.reach || r.views) },
                  { key: 'interactions', label: 'Interazioni', numeric: true, render: (r) => num(r.interactions) },
                  { key: 'engagement_rate', label: 'Coinv.', numeric: true, render: (r) => pct(r.engagement_rate) },
                  { key: 'saves', label: 'Salvati', numeric: true, render: (r) => num(r.saves) },
                  { key: 'shares', label: 'Condivisi', numeric: true, render: (r) => num(r.shares) },
                  { key: 'comments', label: 'Commenti', numeric: true, render: (r) => num(r.comments) },
                ]}
                rows={d.top_content}
              />
            </Panel>

            <section className="two-column-grid">
              <Panel eyebrow="FORMATI" title="Quale formato rende di più">
                <Table
                  columns={[
                    { key: 'format', label: 'Formato' },
                    { key: 'count', label: 'Contenuti', numeric: true },
                    { key: 'avg_reach', label: 'Copertura media', numeric: true, render: (r) => num(r.avg_reach) },
                    { key: 'avg_interactions', label: 'Interazioni medie', numeric: true, render: (r) => nf1.format(r.avg_interactions) },
                    { key: 'avg_engagement_rate', label: 'Coinv. medio', numeric: true, render: (r) => pct(r.avg_engagement_rate) },
                  ]}
                  rows={d.formats}
                />
              </Panel>
              <Panel eyebrow="TASSO DI COINVOLGIMENTO" title="Chi ha coinvolto di più chi l'ha visto">
                <Table
                  empty="Servono contenuti con almeno 30 persone raggiunte."
                  columns={[
                    { key: 'title', label: 'Contenuto', render: contentLink },
                    { key: 'format', label: 'Formato' },
                    { key: 'engagement_rate', label: 'Coinv.', numeric: true, render: (r) => pct(r.engagement_rate) },
                  ]}
                  rows={d.best_engagement}
                />
              </Panel>
            </section>

            <section className="two-column-grid">
              <Panel eyebrow="QUANDO PUBBLICARE" title="Interazioni medie per giorno">
                <SmallBars data={d.weekdays} x="day" y="avg_interactions" />
              </Panel>
              <Panel eyebrow="QUANDO PUBBLICARE" title="Interazioni medie per ora (ora italiana)">
                <SmallBars data={d.hours} x="hour" y="avg_interactions" />
              </Panel>
            </section>
            {!!d.best_slots?.length && (
              <Panel eyebrow="FASCE MIGLIORI" title="Giorno e fascia oraria con più interazioni (almeno 2 post)">
                <BarList rows={d.best_slots} label="slot" value="avg_interactions" format={(v) => nf1.format(v)}
                  detail={(r) => `${r.posts} contenuti`} />
              </Panel>
            )}

            <section className="two-column-grid">
              <Panel eyebrow="CRESCITA" title="Follower guadagnati per giorno">
                <SmallBars data={d.growth} x="day" y="ig_new" color="#e1306c" />
                <SmallBars data={d.growth} x="day" y="fb_new" color="#1877f2" height={120} />
                <p className="panel-copy subtle">Rosa: Instagram · Blu: Facebook</p>
              </Panel>
              <Panel eyebrow="ONLINE" title="Quando i follower Instagram sono connessi (ora italiana)">
                <SmallBars data={d.online_hours} x="hour" y="followers" color="#28d7a3" />
              </Panel>
            </section>

            <Panel eyebrow="PUBBLICO INSTAGRAM"
              title={`Chi ti segue${d.demographics_date ? ` · aggiornato al ${d.demographics_date}` : ''}`}
              extra={d.trieste_follower_share ? <em className="rating-pill good">Trieste {pct(d.trieste_follower_share)}</em> : null}>
              {Object.keys(d.demographics || {}).length ? (
                <section className="two-column-grid">
                  {[['city', 'Città'], ['age', 'Età'], ['gender', 'Genere'], ['country', 'Paese']]
                    .filter(([key]) => d.demographics[key])
                    .map(([key, label]) => (
                      <div key={key}>
                        <h4 className="subhead">{label}</h4>
                        <BarList rows={d.demographics[key]} label="name" value="share" format={pct} />
                      </div>
                    ))}
                </section>
              ) : <Empty>Meta fornisce la demografia solo agli account con almeno 100 follower.</Empty>}
            </Panel>

            <section className="two-column-grid">
              <Panel eyebrow="VIDEO E REEL" title="Quanto vengono guardati">
                <Table
                  empty="Nessun video o reel nel periodo."
                  columns={[
                    { key: 'title', label: 'Video', render: contentLink },
                    { key: 'views', label: 'Visual.', numeric: true, render: (r) => num(r.views) },
                    { key: 'avg_watch_sec', label: 'Visione media', numeric: true, render: (r) => (r.avg_watch_sec ? `${nf1.format(r.avg_watch_sec)}s` : '—') },
                    { key: 'total_watch_min', label: 'Minuti totali', numeric: true, render: (r) => num(r.total_watch_min) },
                    { key: 'shares', label: 'Condivisi', numeric: true, render: (r) => num(r.shares) },
                  ]}
                  rows={d.reels}
                />
              </Panel>
              <Panel eyebrow="STORIE" title="Storie Instagram lette in tempo">
                <Table
                  empty="Nessuna storia registrata: le storie vanno lette entro 24 ore, lascia attiva la sincronizzazione automatica."
                  columns={[
                    { key: 'published_at', label: 'Pubblicata' },
                    { key: 'reach', label: 'Copertura', numeric: true, render: (r) => num(r.reach) },
                    { key: 'replies', label: 'Risposte', numeric: true, render: (r) => num(r.replies) },
                    { key: 'shares', label: 'Condivisioni', numeric: true, render: (r) => num(r.shares) },
                  ]}
                  rows={d.stories}
                />
              </Panel>
            </section>

            <section className="two-column-grid">
              <Panel eyebrow="DAI SOCIAL AL SITO" title="Visite e contatti arrivati da Facebook e Instagram">
                <Kpis items={[
                  ['Sessioni tracker', num(d.site_impact?.tracker_sessions)],
                  ['Contatti', num(d.site_impact?.tracker_contacts), 'WhatsApp, telefono, moduli, email'],
                  ['Tasso contatto', pct(d.site_impact?.contact_rate)],
                ]} />
                <BarList rows={d.site_impact?.ga4_sources} label="name" value="sessions" />
              </Panel>
              <Panel eyebrow="REAZIONI" title="Tipi di reazione su Facebook">
                <BarList rows={d.reactions} label="name" value="value" />
              </Panel>
            </section>
          </>
        )}
      </Loading>
    </>
  )
}

// ---------------------------------------------------------------------------
// Google Business
// ---------------------------------------------------------------------------

export function BusinessPage({ days }) {
  const state = useApi(`/api/analytics/business?days=${days}`)
  const d = state.data
  const t = d?.totals || {}
  const r = d?.reviews || {}
  const k = d?.keywords || {}

  const reviewColumns = [
    { key: 'date', label: 'Data' },
    { key: 'rating', label: 'Voto', render: (row) => <Stars value={row.rating} /> },
    { key: 'reviewer', label: 'Autore', render: (row) => row.reviewer || 'Anonimo' },
    { key: 'comment', label: 'Testo', render: (row) => row.comment || <em>solo voto</em> },
  ]

  return (
    <>
      <Intro
        icon={Store}
        kicker="GOOGLE BUSINESS"
        title="Scheda Google: chi ti trova, chi ti chiama, cosa dicono di te"
        text="Azioni dalla scheda confrontate col periodo precedente, parole cercate mese per mese e tutte le recensioni con le risposte."
      />
      <Loading state={state}>
        {d && (
          <>
            {d.notes?.map((n) => <p className="panel-copy subtle" key={n}>{n}</p>)}
            <Kpis items={[
              ['Visualizzazioni scheda', num(t.impressions), t.impressions_change === null ? '' : `${t.impressions_change > 0 ? '+' : ''}${nf1.format(t.impressions_change)}%`],
              ['Azioni totali', num(t.actions), t.actions_change === null ? '' : `${t.actions_change > 0 ? '+' : ''}${nf1.format(t.actions_change)}%`],
              ['Tasso di azione', pct(t.action_rate), 'azioni / visualizzazioni'],
              ['Da Maps', pct(t.maps_share)],
              ['Da smartphone', pct(t.mobile_share)],
              ['Voto medio', r.average ? `${nf1.format(r.average)} ★` : '—', `${num(r.total)} recensioni`],
            ]} />

            <section className="two-column-grid">
              <Panel eyebrow="AZIONI" title="Cosa fanno dalla scheda">
                <Table
                  columns={[
                    { key: 'label', label: 'Azione' },
                    { key: 'value', label: 'Periodo', numeric: true, render: (row) => num(row.value) },
                    { key: 'previous', label: 'Prima', numeric: true, render: (row) => num(row.previous) },
                    { key: 'change', label: 'Variazione', numeric: true, render: (row) => <Change value={row.change} /> },
                  ]}
                  rows={d.actions}
                />
              </Panel>
              <Panel eyebrow="VISIBILITÀ" title="Dove viene vista la scheda">
                <Table
                  columns={[
                    { key: 'label', label: 'Dove' },
                    { key: 'value', label: 'Periodo', numeric: true, render: (row) => num(row.value) },
                    { key: 'change', label: 'Variazione', numeric: true, render: (row) => <Change value={row.change} /> },
                  ]}
                  rows={d.impressions}
                />
              </Panel>
            </section>

            <section className="two-column-grid">
              <Panel eyebrow="ANDAMENTO" title="Chiamate per giorno">
                <SmallBars data={d.daily} x="day" y="calls" color="#28d7a3" />
              </Panel>
              <Panel eyebrow="SETTIMANA" title="Azioni per giorno della settimana">
                <SmallBars data={d.weekday_actions} x="day" y="actions" />
              </Panel>
            </section>

            <Panel eyebrow="KEYWORD" title={k.month ? `Cosa cercano per trovarti · ${k.month}` : 'Cosa cercano per trovarti'}>
              <Table
                max={40}
                empty="Keyword non ancora disponibili."
                columns={[
                  { key: 'keyword', label: 'Ricerca', render: (row) => <>{row.keyword}{row.is_new && <em className="rating-pill good"> nuova</em>}</> },
                  { key: 'impressions', label: 'Visualizzazioni', numeric: true, render: (row) => (row.below_threshold ? `< ${num(row.impressions)}` : num(row.impressions)) },
                  { key: 'previous', label: 'Mese prima', numeric: true, render: (row) => (row.previous ? num(row.previous) : '—') },
                  { key: 'change', label: 'Variazione', numeric: true, render: (row) => <Change value={row.change} /> },
                ]}
                rows={k.top}
              />
            </Panel>
            <section className="two-column-grid">
              <Panel eyebrow="KEYWORD" title="Visualizzazioni da ricerche, mese per mese">
                <SmallBars data={k.trend} x="month" y="impressions" />
              </Panel>
              <Panel eyebrow="KEYWORD" title="In crescita rispetto al mese prima">
                <BarList rows={k.rising} label="keyword" value="change" format={(v) => `+${nf1.format(v)}%`} />
              </Panel>
            </section>

            <Panel eyebrow="RECENSIONI" title="Reputazione" extra={<Star size={16} />}>
              <Kpis items={[
                ['Voto medio', r.average ? `${nf1.format(r.average)} ★` : '—'],
                ['Recensioni', num(r.total), `${num(r.in_period)} nel periodo`],
                ['Media nel periodo', r.in_period_average ? `${nf1.format(r.in_period_average)} ★` : '—'],
                ['Con risposta', pct(r.reply_rate)],
                ['Tempo di risposta', r.median_reply_hours === null || r.median_reply_hours === undefined ? '—' : `${nf1.format(r.median_reply_hours)} h`, 'mediana'],
              ]} />
              <section className="two-column-grid">
                <div>
                  <h4 className="subhead">Distribuzione voti</h4>
                  <BarList rows={(r.distribution || []).map((x) => ({ ...x, name: `${x.stars} ★` }))} label="name" value="count" />
                </div>
                <div>
                  <h4 className="subhead">Recensioni per mese</h4>
                  <SmallBars data={r.trend} x="month" y="count" color="#f5b85a" height={160} />
                </div>
              </section>
            </Panel>

            <section className="two-column-grid">
              <Panel eyebrow="DA FARE" title="Recensioni senza risposta">
                <Table columns={reviewColumns} rows={r.unanswered} empty="Hai risposto a tutte. Ottimo." />
              </Panel>
              <Panel eyebrow="ATTENZIONE" title="Recensioni da 1 a 3 stelle">
                <Table columns={reviewColumns} rows={r.negative} empty="Nessuna recensione sotto le 4 stelle." />
              </Panel>
            </section>

            <section className="two-column-grid">
              <Panel eyebrow="PAROLE" title="Cosa citano più spesso" extra={<MessageSquareText size={16} />}>
                <BarList rows={r.words} label="word" value="count" />
              </Panel>
              <Panel eyebrow="PAROLE" title="Nelle recensioni negative">
                <BarList rows={r.words_negative} label="word" value="count" />
              </Panel>
            </section>

            <Panel eyebrow="ULTIME" title="Recensioni più recenti">
              <Table
                columns={[...reviewColumns, { key: 'reply_comment', label: 'Risposta', render: (row) => row.reply_comment || <em className="rating-pill warn">da rispondere</em> }]}
                rows={r.recent}
                empty="Nessuna recensione importata."
              />
            </Panel>
          </>
        )}
      </Loading>
    </>
  )
}
