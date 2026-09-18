import { useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  Check,
  CheckCircle2,
  CircleAlert,
  Camera,
  Cpu,
  ExternalLink,
  Share2,
  Globe2,
  Link2,
  RefreshCw,
  Search,
  Settings2,
  Sparkles,
} from 'lucide-react'


const steps = [
  { id: 'system', label: 'Sistema', icon: Settings2 },
  { id: 'ai', label: 'AI locale', icon: Cpu },
  { id: 'wordpress', label: 'WordPress', icon: Globe2 },
  { id: 'google', label: 'Google', icon: Search },
  { id: 'meta', label: 'Facebook + Instagram', icon: Share2 },
  { id: 'finish', label: 'Verifica finale', icon: CheckCircle2 },
]

function SetupWizardPage({ onFinish }) {
  const [step, setStep] = useState(() =>
    new URLSearchParams(window.location.search).get('google') === 'connected' ? 3 : 0
  )
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const [googleResources, setGoogleResources] = useState(null)

  const [aiBaseUrl, setAiBaseUrl] = useState('http://127.0.0.1:11434')
  const [aiModel, setAiModel] = useState('')
  const [aiThink, setAiThink] = useState(false)

  const [wordpress, setWordpress] = useState({
    base_url: 'https://triesteincostruzione.com',
    username: '',
    app_password: '',
    ge360_key: '',
  })

  const [google, setGoogle] = useState({
    client_id: '',
    client_secret: '',
    ga4_property_id: '',
    search_console_site_url: 'https://triesteincostruzione.com/',
    business_location_name: '',
  })

  const [meta, setMeta] = useState({
    app_id: '',
    app_secret: '',
    page_id: '',
    page_access_token: '',
    instagram_account_id: '',
    graph_version: 'v26.0',
  })

  const current = steps[step]
  const CurrentIcon = current.icon

  const loadStatus = async () => {
    setBusy('status')
    try {
      const payload = await fetch('/api/setup/status').then((r) => r.json())
      setStatus(payload)

      setAiBaseUrl(payload.ai?.base_url || 'http://127.0.0.1:11434')
      setAiModel(payload.ai?.selected_model || payload.ai?.models?.[0]?.name || '')
      setAiThink(Boolean(payload.ai?.think))

      setWordpress((prev) => ({
        ...prev,
        base_url: payload.wordpress?.WORDPRESS_BASE_URL?.value || prev.base_url,
        username: payload.wordpress?.WORDPRESS_USERNAME?.value || '',
      }))

      setGoogle((prev) => ({
        ...prev,
        client_id: payload.google?.GOOGLE_CLIENT_ID?.value || '',
        ga4_property_id: payload.google?.GA4_PROPERTY_ID?.value || '',
        search_console_site_url:
          payload.google?.SEARCH_CONSOLE_SITE_URL?.value || prev.search_console_site_url,
        business_location_name: payload.google?.GOOGLE_BUSINESS_LOCATION_NAME?.value || '',
      }))

      setMeta((prev) => ({
        ...prev,
        app_id: payload.meta?.META_APP_ID?.value || '',
        page_id: payload.meta?.META_PAGE_ID?.value || '',
        instagram_account_id: payload.meta?.META_INSTAGRAM_ACCOUNT_ID?.value || '',
        graph_version: payload.meta?.META_GRAPH_VERSION?.value || 'v26.0',
      }))
    } finally {
      setBusy('')
    }
  }

  useEffect(() => {
    loadStatus()
  }, [])

  const progress = status?.percent || 0
  const aiModels = status?.ai?.models || []

  const completedSteps = useMemo(() => ({
    system: true,
    ai: Boolean(status?.completion?.ai),
    wordpress: Boolean(status?.completion?.wordpress),
    google: Boolean(status?.completion?.google_connected),
    meta: Boolean(status?.completion?.meta),
    finish: progress >= 80,
  }), [status, progress])

  const saveAI = async () => {
    setBusy('ai')
    setMessage('')
    try {
      const response = await fetch('/api/local-ai/configure', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: aiBaseUrl,
          model: aiModel,
          think: aiThink,
        }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Configurazione AI non salvata')

      const testResponse = await fetch('/api/local-ai/test', { method: 'POST' })
      const testPayload = await testResponse.json()
      if (!testResponse.ok) throw new Error(testPayload.detail || 'Test Ollama fallito')

      setMessage(`AI locale pronta: ${testPayload.selected_model}`)
      await loadStatus()
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy('')
    }
  }

  const saveWordPress = async () => {
    setBusy('wordpress')
    setMessage('')
    try {
      const response = await fetch('/api/setup/wordpress', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(wordpress),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'WordPress non collegato')
      setMessage(payload.message)
      await loadStatus()
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy('')
    }
  }

  const saveGoogle = async () => {
    setBusy('google-save')
    setMessage('')
    try {
      const response = await fetch('/api/setup/google', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(google),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Impostazioni Google non salvate')
      setMessage('Credenziali Google salvate. Ora puoi collegare il tuo account.')
      await loadStatus()
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy('')
    }
  }

  const connectGoogle = async () => {
    setBusy('google-login')
    setMessage('')
    try {
      await saveGoogle()
      const response = await fetch('/api/oauth/google/start')
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'OAuth Google non pronto')
      window.location.href = payload.authorization_url
    } catch (error) {
      setMessage(error.message)
      setBusy('')
    }
  }

  const discoverGoogle = async () => {
    setBusy('google-discover')
    setMessage('')
    try {
      const response = await fetch('/api/setup/google/discover')
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Scoperta risorse Google fallita')
      setGoogleResources(payload)

      const next = {
        ...google,
        ga4_property_id:
          google.ga4_property_id || payload.ga4_properties?.[0]?.id || '',
        search_console_site_url:
          google.search_console_site_url || payload.search_console_sites?.[0]?.url || '',
        business_location_name:
          google.business_location_name || payload.business_locations?.[0]?.name || '',
      }
      setGoogle(next)
      setMessage('Risorse Google rilevate. Scegli quelle corrette e salva.')
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy('')
    }
  }

  const saveMeta = async () => {
    setBusy('meta')
    setMessage('')
    try {
      const response = await fetch('/api/setup/meta', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(meta),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Meta non collegato')

      setMeta((prev) => ({
        ...prev,
        instagram_account_id: payload.instagram?.id || prev.instagram_account_id,
      }))

      setMessage(
        payload.instagram?.connected
          ? `Facebook OK · Instagram @${payload.instagram.username || payload.instagram.id} rilevato`
          : 'Facebook OK. Nessun account Instagram professionale collegato alla Pagina.'
      )
      await loadStatus()
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy('')
    }
  }

  const finalSync = async () => {
    setBusy('sync')
    setMessage('')
    try {
      const response = await fetch('/api/sync', { method: 'POST' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Sincronizzazione fallita')
      const ok = payload.results?.filter((item) => item.ok).length || 0
      setMessage(`Configurazione completata: ${ok} connettori sincronizzati.`)
      await loadStatus()
      localStorage.setItem('ge360-setup-seen', '1')
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy('')
    }
  }

  return (
    <div className="setup-wizard">
      <section className="setup-header">
        <div>
          <span className="eyebrow">CONFIGURAZIONE GUIDATA</span>
          <h2>Impostiamo GE360 passo per passo</h2>
          <p>
            Il wizard rileva ciò che hai già sul Linux e ti chiede solo quello che manca.
            Password e token restano sul tuo server.
          </p>
        </div>
        <div className="setup-progress-card">
          <strong>{progress}%</strong>
          <span>configurato</span>
          <div><i style={{ width: `${progress}%` }} /></div>
        </div>
      </section>

      <div className="wizard-shell">
        <aside className="wizard-steps">
          {steps.map((item, index) => {
            const Icon = item.icon
            const done = completedSteps[item.id]
            return (
              <button
                key={item.id}
                className={index === step ? 'wizard-step active' : 'wizard-step'}
                onClick={() => { setStep(index); setMessage('') }}
              >
                <span className={done ? 'step-icon done' : 'step-icon'}>
                  {done ? <Check size={15} /> : <Icon size={15} />}
                </span>
                <span><strong>{index + 1}. {item.label}</strong><small>{done ? 'Pronto' : 'Da completare'}</small></span>
              </button>
            )
          })}
        </aside>

        <main className="wizard-content">
          <div className="wizard-title">
            <div className="wizard-title-icon"><CurrentIcon size={22} /></div>
            <div><span>PASSAGGIO {step + 1} DI {steps.length}</span><h3>{current.label}</h3></div>
          </div>

          {step === 0 && (
            <SystemStep status={status} reload={loadStatus} busy={busy} />
          )}

          {step === 1 && (
            <section className="wizard-form">
              <GuideText
                title="GE360 cerca Ollama già installato"
                text="Non scarichiamo nulla. Se Ollama gira sullo stesso Linux, lascia 127.0.0.1:11434 e scegli uno dei modelli già presenti."
              />
              <Field label="Server Ollama">
                <input value={aiBaseUrl} onChange={(e) => setAiBaseUrl(e.target.value)} />
              </Field>
              <Field label="Modello locale">
                <select value={aiModel} onChange={(e) => setAiModel(e.target.value)}>
                  <option value="">Seleziona un modello rilevato</option>
                  {aiModels.map((item) => (
                    <option key={item.name} value={item.name}>
                      {item.name}{item.parameter_size ? ` · ${item.parameter_size}` : ''}
                    </option>
                  ))}
                </select>
              </Field>
              <label className="wizard-check">
                <input type="checkbox" checked={aiThink} onChange={(e) => setAiThink(e.target.checked)} />
                <span><strong>Thinking / reasoning</strong><small>Attivalo solo se il tuo Qwen lo supporta.</small></span>
              </label>
              <ActionRow>
                <button className="secondary-action" onClick={loadStatus}><RefreshCw size={14} /> Rileva di nuovo</button>
                <button className="primary-action" onClick={saveAI} disabled={busy === 'ai'}><Check size={14} /> Salva e prova</button>
              </ActionRow>
            </section>
          )}

          {step === 2 && (
            <section className="wizard-form">
              <GuideText
                title="Colleghiamo il tuo WordPress"
                text="Il sito può essere letto via REST. Per gli eventi GE360 copia la chiave da WordPress → Impostazioni → GE360 Tracker."
              />
              <Field label="URL sito">
                <input value={wordpress.base_url} onChange={(e) => setWordpress({ ...wordpress, base_url: e.target.value })} />
              </Field>
              <Field label="Utente WordPress (opzionale)">
                <input value={wordpress.username} onChange={(e) => setWordpress({ ...wordpress, username: e.target.value })} />
              </Field>
              <Field
                label="Application Password (opzionale)"
                hint={status?.wordpress?.WORDPRESS_APP_PASSWORD?.configured ? 'Già configurata: lascia vuoto per conservarla.' : ''}
              >
                <input type="password" value={wordpress.app_password} onChange={(e) => setWordpress({ ...wordpress, app_password: e.target.value })} />
              </Field>
              <Field
                label="Chiave GE360 Tracker"
                hint={status?.wordpress?.WORDPRESS_GE360_KEY?.configured ? 'Già configurata: lascia vuoto per conservarla.' : 'La trovi nella pagina impostazioni del plugin GE360 Tracker.'}
              >
                <input type="password" value={wordpress.ge360_key} onChange={(e) => setWordpress({ ...wordpress, ge360_key: e.target.value })} />
              </Field>
              <ActionRow>
                <button className="primary-action" onClick={saveWordPress} disabled={busy === 'wordpress'}>
                  <Link2 size={14} /> Salva e testa WordPress
                </button>
              </ActionRow>
            </section>
          )}

          {step === 3 && (
            <section className="wizard-form">
              <GuideText
                title="Un login Google per Analytics, Search Console e Business Profile"
                text="Inserisci una volta Client ID e Client Secret. Dopo il login GE360 prova a trovarti automaticamente proprietà, siti e sedi."
              />
              <div className="wizard-help-card">
                <div><Building2 size={18} /><strong>Prima volta?</strong></div>
                <p>Crea un client OAuth Web nel tuo progetto Google Cloud, abilita le API Analytics Data/Admin, Search Console e Business Profile e usa come redirect:</p>
                <code>http://127.0.0.1:8788/api/oauth/google/callback</code>
                <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noreferrer">
                  Apri Google Cloud Credentials <ExternalLink size={13} />
                </a>
              </div>
              <Field label="Google Client ID">
                <input value={google.client_id} onChange={(e) => setGoogle({ ...google, client_id: e.target.value })} />
              </Field>
              <Field
                label="Google Client Secret"
                hint={status?.google?.GOOGLE_CLIENT_SECRET?.configured ? 'Già configurato: lascia vuoto per conservarlo.' : ''}
              >
                <input type="password" value={google.client_secret} onChange={(e) => setGoogle({ ...google, client_secret: e.target.value })} />
              </Field>

              <ActionRow>
                <button className="secondary-action" onClick={saveGoogle} disabled={Boolean(busy)}>
                  <Check size={14} /> Salva credenziali
                </button>
                <button className="primary-action" onClick={connectGoogle} disabled={Boolean(busy)}>
                  <ExternalLink size={14} /> Collega account Google
                </button>
              </ActionRow>

              {status?.completion?.google_connected && (
                <div className="wizard-success"><CheckCircle2 size={17} /> Account Google collegato.</div>
              )}

              <div className="wizard-divider" />

              <ActionRow>
                <button className="secondary-action" onClick={discoverGoogle} disabled={!status?.completion?.google_connected || Boolean(busy)}>
                  <RefreshCw size={14} /> Trova automaticamente proprietà e sedi
                </button>
              </ActionRow>

              <Field label="Proprietà GA4">
                {googleResources?.ga4_properties?.length ? (
                  <select value={google.ga4_property_id} onChange={(e) => setGoogle({ ...google, ga4_property_id: e.target.value })}>
                    <option value="">Seleziona</option>
                    {googleResources.ga4_properties.map((item) => (
                      <option key={item.id} value={item.id}>{item.name} · {item.id}</option>
                    ))}
                  </select>
                ) : (
                  <input value={google.ga4_property_id} onChange={(e) => setGoogle({ ...google, ga4_property_id: e.target.value })} placeholder="es. 123456789" />
                )}
              </Field>

              <Field label="Search Console">
                {googleResources?.search_console_sites?.length ? (
                  <select value={google.search_console_site_url} onChange={(e) => setGoogle({ ...google, search_console_site_url: e.target.value })}>
                    <option value="">Seleziona</option>
                    {googleResources.search_console_sites.map((item) => (
                      <option key={item.url} value={item.url}>{item.url}</option>
                    ))}
                  </select>
                ) : (
                  <input value={google.search_console_site_url} onChange={(e) => setGoogle({ ...google, search_console_site_url: e.target.value })} />
                )}
              </Field>

              <Field label="Google Business Profile">
                {googleResources?.business_locations?.length ? (
                  <select value={google.business_location_name} onChange={(e) => setGoogle({ ...google, business_location_name: e.target.value })}>
                    <option value="">Seleziona</option>
                    {googleResources.business_locations.map((item) => (
                      <option key={item.name} value={item.name}>{item.title || item.name}</option>
                    ))}
                  </select>
                ) : (
                  <input value={google.business_location_name} onChange={(e) => setGoogle({ ...google, business_location_name: e.target.value })} placeholder="locations/..." />
                )}
              </Field>

              <ActionRow>
                <button className="primary-action" onClick={saveGoogle} disabled={Boolean(busy)}>
                  <Check size={14} /> Salva selezioni Google
                </button>
              </ActionRow>
            </section>
          )}

          {step === 4 && (
            <section className="wizard-form">
              <GuideText
                title="Facebook e Instagram insieme"
                text="GE360 usa la Meta Graph API. Con Facebook Login, Instagram deve essere un account professionale collegato alla Pagina Facebook."
              />
              <div className="social-guide-grid">
                <div><Share2 size={18} /><strong>Facebook</strong><span>Pagina professionale + Page Access Token</span></div>
                <div><Camera size={18} /><strong>Instagram</strong><span>Business/Creator collegato alla Pagina</span></div>
              </div>
              <a className="wizard-external-link" href="https://developers.facebook.com/apps/" target="_blank" rel="noreferrer">
                Apri Meta for Developers <ExternalLink size={13} />
              </a>

              <Field label="Meta App ID">
                <input value={meta.app_id} onChange={(e) => setMeta({ ...meta, app_id: e.target.value })} />
              </Field>
              <Field
                label="Meta App Secret"
                hint={status?.meta?.META_APP_SECRET?.configured ? 'Già configurato: lascia vuoto per conservarlo.' : ''}
              >
                <input type="password" value={meta.app_secret} onChange={(e) => setMeta({ ...meta, app_secret: e.target.value })} />
              </Field>
              <Field label="Facebook Page ID">
                <input value={meta.page_id} onChange={(e) => setMeta({ ...meta, page_id: e.target.value })} />
              </Field>
              <Field
                label="Page Access Token"
                hint={status?.meta?.META_PAGE_ACCESS_TOKEN?.configured ? 'Già configurato: lascia vuoto per conservarlo.' : 'Usa un token della Pagina, non la password Facebook.'}
              >
                <textarea rows={3} value={meta.page_access_token} onChange={(e) => setMeta({ ...meta, page_access_token: e.target.value })} />
              </Field>
              <Field label="Instagram Business Account ID" hint="Puoi lasciarlo vuoto: GE360 proverà a rilevarlo dalla Pagina.">
                <input value={meta.instagram_account_id} onChange={(e) => setMeta({ ...meta, instagram_account_id: e.target.value })} />
              </Field>
              <ActionRow>
                <button className="primary-action" onClick={saveMeta} disabled={busy === 'meta'}>
                  <Link2 size={14} /> Salva, testa e trova Instagram
                </button>
              </ActionRow>
            </section>
          )}

          {step === 5 && (
            <section className="wizard-form">
              <GuideText
                title="Controllo finale"
                text="Non serve avere tutto per iniziare: GE360 funziona anche con una parte delle fonti. Qui vedi cosa è pronto."
              />
              <div className="setup-review-grid">
                <Review label="AI locale" ok={status?.completion?.ai} />
                <Review label="WordPress Tracker" ok={status?.completion?.wordpress} />
                <Review label="Google OAuth" ok={status?.completion?.google_connected} />
                <Review label="Risorse Google" ok={status?.completion?.google_resources} />
                <Review label="Facebook / Meta" ok={status?.completion?.meta} />
              </div>
              <ActionRow>
                <button className="primary-action" onClick={finalSync} disabled={busy === 'sync'}>
                  <RefreshCw size={14} /> Sincronizza tutto e verifica
                </button>
              </ActionRow>
              <div className="wizard-final-note">
                <Sparkles size={18} />
                <div><strong>Dopo la prima sincronizzazione</strong><p>Vai su AI Locale e genera il primo Report completo. Qwen userà solo i dati che GE360 è riuscito realmente a raccogliere.</p></div>
              </div>
            </section>
          )}

          {message && <div className="wizard-message">{message}</div>}

          <footer className="wizard-footer">
            <button className="secondary-action" onClick={() => setStep(Math.max(0, step - 1))} disabled={step === 0}>
              <ArrowLeft size={14} /> Indietro
            </button>
            {step < steps.length - 1 ? (
              <button className="primary-action" onClick={() => { setStep(step + 1); setMessage('') }}>
                Avanti <ArrowRight size={14} />
              </button>
            ) : (
              <button
                className="primary-action"
                onClick={() => {
                  localStorage.setItem('ge360-setup-seen', '1')
                  onFinish?.()
                }}
              >
                <Check size={14} /> Vai alla dashboard
              </button>
            )}
          </footer>
        </main>
      </div>
    </div>
  )
}

function SystemStep({ status, reload, busy }) {
  return (
    <section className="wizard-form">
      <GuideText
        title="GE360 controlla ciò che è già presente"
        text="Non reinstalliamo niente. Il programma verifica AI locale, configurazioni esistenti e connessioni già salvate."
      />
      <div className="system-detect-grid">
        <Detection
          label="Ollama"
          value={status?.ai?.ok ? 'Rilevato' : 'Non raggiungibile'}
          ok={status?.ai?.ok}
          detail={status?.ai?.base_url}
        />
        <Detection
          label="Modello AI"
          value={status?.ai?.selected_available ? status.ai.selected_model : 'Da scegliere'}
          ok={status?.ai?.selected_available}
          detail={status?.ai?.models?.length ? `${status.ai.models.length} modelli trovati` : 'Nessun modello rilevato'}
        />
        <Detection
          label="WordPress"
          value={status?.completion?.wordpress ? 'Configurato' : 'Da completare'}
          ok={status?.completion?.wordpress}
        />
        <Detection
          label="Google"
          value={status?.completion?.google_connected ? 'Account collegato' : 'Da collegare'}
          ok={status?.completion?.google_connected}
        />
        <Detection
          label="Meta"
          value={status?.completion?.meta ? 'Configurato' : 'Da completare'}
          ok={status?.completion?.meta}
        />
      </div>
      <ActionRow>
        <button className="secondary-action" onClick={reload} disabled={busy === 'status'}>
          <RefreshCw size={14} /> Ripeti controllo
        </button>
      </ActionRow>
    </section>
  )
}

function Field({ label, hint, children }) {
  return (
    <label className="wizard-field">
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  )
}

function GuideText({ title, text }) {
  return <div className="wizard-guide"><Sparkles size={18} /><div><strong>{title}</strong><p>{text}</p></div></div>
}

function ActionRow({ children }) {
  return <div className="wizard-actions">{children}</div>
}

function Detection({ label, value, ok, detail }) {
  return (
    <div className={ok ? 'detection-card ok' : 'detection-card'}>
      <div>{ok ? <CheckCircle2 size={17} /> : <CircleAlert size={17} />}<strong>{label}</strong></div>
      <span>{value}</span>
      {detail && <small>{detail}</small>}
    </div>
  )
}

function Review({ label, ok }) {
  return (
    <div className={ok ? 'review-item ok' : 'review-item'}>
      {ok ? <CheckCircle2 size={17} /> : <CircleAlert size={17} />}
      <span>{label}</span>
      <strong>{ok ? 'Pronto' : 'Da completare'}</strong>
    </div>
  )
}

export default SetupWizardPage
