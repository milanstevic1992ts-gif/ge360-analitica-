import { useEffect, useMemo, useState } from 'react'
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  Camera,
  Check,
  CheckCircle2,
  CircleAlert,
  Cpu,
  ExternalLink,
  FileJson,
  Globe2,
  Link2,
  LogIn,
  RefreshCw,
  Search,
  Settings2,
  Share2,
  Sparkles,
  Upload,
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
  const params = new URLSearchParams(window.location.search)
  const [step, setStep] = useState(() => {
    if (params.get('meta') === 'connected') return 4
    if (params.get('google') === 'connected') return 3
    return 0
  })
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const [googleResources, setGoogleResources] = useState(null)
  const [metaPages, setMetaPages] = useState([])

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
      const detectedModels = payload.ai?.models || []
      const configuredModel = payload.ai?.selected_available ? payload.ai?.selected_model : ''
      const qwenModel = detectedModels.find((item) =>
        String(item.name || '').toLowerCase().includes('qwen')
      )?.name
      setAiModel(
        configuredModel ||
        qwenModel ||
        detectedModels[0]?.name ||
        payload.ai?.selected_model ||
        ''
      )
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
        graph_version: payload.meta?.META_GRAPH_VERSION?.value || 'v26.0',
      }))
    } finally {
      setBusy('')
    }
  }

  const discoverGoogle = async ({ silent = false } = {}) => {
    setBusy('google-discover')
    if (!silent) setMessage('')
    try {
      const response = await fetch('/api/setup/google/discover')
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Scoperta risorse Google fallita')
      setGoogleResources(payload)

      setGoogle((prev) => ({
        ...prev,
        ga4_property_id: prev.ga4_property_id || payload.ga4_properties?.[0]?.id || '',
        search_console_site_url:
          prev.search_console_site_url || payload.search_console_sites?.[0]?.url || '',
        business_location_name:
          prev.business_location_name || payload.business_locations?.[0]?.name || '',
      }))

      if (!silent) {
        setMessage('Account Google collegato. Ho cercato automaticamente proprietà e sedi.')
      }
    } catch (error) {
      if (!silent) setMessage(error.message)
    } finally {
      setBusy('')
    }
  }

  const loadMetaPages = async ({ silent = false } = {}) => {
    setBusy('meta-pages')
    if (!silent) setMessage('')
    try {
      const response = await fetch('/api/oauth/meta/pages')
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Non riesco a leggere le Pagine Facebook')
      setMetaPages(payload.items || [])
      if (!silent) {
        setMessage(
          payload.items?.length
            ? 'Login Facebook riuscito. Scegli la Pagina da collegare.'
            : 'Login riuscito, ma non vedo Pagine amministrate con questo account.'
        )
      }
    } catch (error) {
      if (!silent) setMessage(error.message)
    } finally {
      setBusy('')
    }
  }

  useEffect(() => {
    const initialize = async () => {
      await loadStatus()
      if (params.get('google') === 'connected') {
        await discoverGoogle({ silent: true })
      }
      if (params.get('meta') === 'connected') {
        await loadMetaPages({ silent: true })
      }
    }
    initialize()
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
        body: JSON.stringify({ base_url: aiBaseUrl, model: aiModel, think: aiThink }),
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

  const importGoogleJson = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return

    setBusy('google-import')
    setMessage('')
    try {
      const parsed = JSON.parse(await file.text())
      const response = await fetch('/api/setup/google/import-oauth-json', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payload: parsed }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'File Google OAuth non valido')

      setMessage(payload.message)
      await loadStatus()
    } catch (error) {
      setMessage(`Importazione Google fallita: ${error.message}`)
    } finally {
      event.target.value = ''
      setBusy('')
    }
  }

  const saveGoogleAdvanced = async () => {
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
      setMessage('Configurazione Google salvata.')
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
      const response = await fetch('/api/oauth/google/start')
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Google Login non ancora configurato')
      window.location.href = payload.authorization_url
    } catch (error) {
      setMessage(
        `${error.message}. Se è la prima volta, importa il file OAuth JSON nella sezione qui sotto.`
      )
      setBusy('')
    }
  }

  const saveGoogleSelections = async () => {
    await saveGoogleAdvanced()
    setMessage('Selezioni Google salvate.')
  }

  const saveMetaCredentials = async () => {
    setBusy('meta-save')
    setMessage('')
    try {
      const response = await fetch('/api/setup/meta/credentials', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(meta),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Configurazione Meta non salvata')
      setMessage(
        payload.oauth_ready
          ? 'Configurazione Meta pronta. Ora premi Accedi con Facebook.'
          : 'Servono App ID e App Secret.'
      )
      await loadStatus()
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy('')
    }
  }

  const connectMeta = async () => {
    setBusy('meta-login')
    setMessage('')
    try {
      const response = await fetch('/api/oauth/meta/start')
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Facebook Login non ancora configurato')
      window.location.href = payload.authorization_url
    } catch (error) {
      setMessage(
        `${error.message}. Apri "Configurazione una tantum" e inserisci App ID/Secret.`
      )
      setBusy('')
    }
  }

  const selectMetaPage = async (pageId) => {
    setBusy(`meta-select-${pageId}`)
    setMessage('')
    try {
      const response = await fetch('/api/oauth/meta/select-page', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ page_id: pageId }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Pagina non collegata')

      setMessage(
        payload.instagram?.connected
          ? `Collegato: ${payload.facebook_page.name} + Instagram @${payload.instagram.username || payload.instagram.id}`
          : `Collegato: ${payload.facebook_page.name}. Instagram professionale non rilevato.`
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
          <h2>Collega gli account senza cercare ID e token</h2>
          <p>
            GE360 usa login OAuth per Google e Meta. La parte tecnica resta nascosta e si fa
            una sola volta; poi scegli semplicemente account, proprietà o Pagina.
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
                <span>
                  <strong>{index + 1}. {item.label}</strong>
                  <small>{done ? 'Pronto' : 'Da completare'}</small>
                </span>
              </button>
            )
          })}
        </aside>

        <main className="wizard-content">
          <div className="wizard-title">
            <div className="wizard-title-icon"><CurrentIcon size={22} /></div>
            <div><span>PASSAGGIO {step + 1} DI {steps.length}</span><h3>{current.label}</h3></div>
          </div>

          {step === 0 && <SystemStep status={status} reload={loadStatus} busy={busy} />}

          {step === 1 && (
            <section className="wizard-form">
              <GuideText
                title="GE360 cerca Ollama già installato"
                text="Non scarichiamo nulla. Scegli uno dei modelli che GE360 trova già sul tuo Linux."
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
                <span><strong>Thinking / reasoning</strong><small>Attivalo solo se il modello lo supporta.</small></span>
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
                title="WordPress"
                text="Incolla la chiave del plugin GE360 Tracker. Hai già trovato questa parte, quindi non serve altro."
              />
              <Field label="URL sito">
                <input value={wordpress.base_url} onChange={(e) => setWordpress({ ...wordpress, base_url: e.target.value })} />
              </Field>
              <Field
                label="Chiave GE360 Tracker"
                hint={status?.wordpress?.WORDPRESS_GE360_KEY?.configured ? 'Già configurata: lascia vuoto per conservarla.' : ''}
              >
                <input type="password" value={wordpress.ge360_key} onChange={(e) => setWordpress({ ...wordpress, ge360_key: e.target.value })} />
              </Field>
              <details className="advanced-box">
                <summary>Opzioni WordPress avanzate</summary>
                <div className="advanced-box-body">
                  <Field label="Utente WordPress (opzionale)">
                    <input value={wordpress.username} onChange={(e) => setWordpress({ ...wordpress, username: e.target.value })} />
                  </Field>
                  <Field label="Application Password (opzionale)">
                    <input type="password" value={wordpress.app_password} onChange={(e) => setWordpress({ ...wordpress, app_password: e.target.value })} />
                  </Field>
                </div>
              </details>
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
                title="Google: fai login e GE360 trova il resto"
                text="Dopo l'accesso, GE360 cerca automaticamente Analytics, Search Console e Google Business Profile."
              />

              <div className={status?.completion?.google_connected ? 'login-card connected' : 'login-card'}>
                <div className="login-card-icon"><Search size={24} /></div>
                <div>
                  <strong>{status?.completion?.google_connected ? 'Google collegato' : 'Accedi con Google'}</strong>
                  <p>
                    {status?.completion?.google_connected
                      ? 'Account autorizzato. Ora possiamo cercare le proprietà disponibili.'
                      : 'Apri la pagina Google, scegli il tuo account e autorizza GE360.'}
                  </p>
                </div>
                <button className="primary-action login-action" onClick={connectGoogle} disabled={Boolean(busy)}>
                  <LogIn size={15} /> {status?.completion?.google_connected ? 'Ricollega' : 'Accedi con Google'}
                </button>
              </div>

              {!status?.completion?.google_credentials && (
                <div className="one-time-setup">
                  <div className="one-time-heading">
                    <FileJson size={18} />
                    <div><strong>Prima volta: importa il file OAuth di Google</strong><span>È una configurazione una tantum.</span></div>
                  </div>
                  <p>
                    Da Google Cloud crea un client OAuth <strong>Applicazione Web</strong>,
                    aggiungi il redirect GE360 e scarica il file JSON. Poi caricalo qui.
                  </p>
                  <code>http://127.0.0.1:8788/api/oauth/google/callback</code>
                  <div className="one-time-actions">
                    <a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noreferrer">
                      Apri Google Cloud <ExternalLink size={13} />
                    </a>
                    <label className="secondary-action file-action">
                      <Upload size={14} /> Importa JSON OAuth
                      <input type="file" accept=".json,application/json" onChange={importGoogleJson} />
                    </label>
                  </div>
                </div>
              )}

              <details className="advanced-box">
                <summary>Configurazione Google avanzata</summary>
                <div className="advanced-box-body">
                  <Field label="Client ID">
                    <input value={google.client_id} onChange={(e) => setGoogle({ ...google, client_id: e.target.value })} />
                  </Field>
                  <Field
                    label="Client Secret"
                    hint={status?.google?.GOOGLE_CLIENT_SECRET?.configured ? 'Già configurato: lascia vuoto per conservarlo.' : ''}
                  >
                    <input type="password" value={google.client_secret} onChange={(e) => setGoogle({ ...google, client_secret: e.target.value })} />
                  </Field>
                  <button className="secondary-action" onClick={saveGoogleAdvanced}>Salva configurazione</button>
                </div>
              </details>

              {status?.completion?.google_connected && (
                <>
                  <div className="wizard-divider" />
                  <ActionRow>
                    <button className="secondary-action" onClick={() => discoverGoogle()} disabled={Boolean(busy)}>
                      <RefreshCw size={14} /> Trova automaticamente tutto
                    </button>
                  </ActionRow>

                  {googleResources && (
                    <div className="auto-found-grid">
                      <FoundCard label="Analytics" count={googleResources.ga4_properties?.length || 0} />
                      <FoundCard label="Search Console" count={googleResources.search_console_sites?.length || 0} />
                      <FoundCard label="Business Profile" count={googleResources.business_locations?.length || 0} />
                    </div>
                  )}

                  <Field label="Google Analytics">
                    {googleResources?.ga4_properties?.length ? (
                      <select value={google.ga4_property_id} onChange={(e) => setGoogle({ ...google, ga4_property_id: e.target.value })}>
                        <option value="">Seleziona proprietà</option>
                        {googleResources.ga4_properties.map((item) => (
                          <option key={item.id} value={item.id}>{item.name} · {item.id}</option>
                        ))}
                      </select>
                    ) : <input value={google.ga4_property_id} onChange={(e) => setGoogle({ ...google, ga4_property_id: e.target.value })} />}
                  </Field>

                  <Field label="Search Console">
                    {googleResources?.search_console_sites?.length ? (
                      <select value={google.search_console_site_url} onChange={(e) => setGoogle({ ...google, search_console_site_url: e.target.value })}>
                        <option value="">Seleziona sito</option>
                        {googleResources.search_console_sites.map((item) => (
                          <option key={item.url} value={item.url}>{item.url}</option>
                        ))}
                      </select>
                    ) : <input value={google.search_console_site_url} onChange={(e) => setGoogle({ ...google, search_console_site_url: e.target.value })} />}
                  </Field>

                  <Field label="Google Business Profile">
                    {googleResources?.business_locations?.length ? (
                      <select value={google.business_location_name} onChange={(e) => setGoogle({ ...google, business_location_name: e.target.value })}>
                        <option value="">Seleziona attività</option>
                        {googleResources.business_locations.map((item) => (
                          <option key={item.name} value={item.name}>{item.title || item.name}</option>
                        ))}
                      </select>
                    ) : <input value={google.business_location_name} onChange={(e) => setGoogle({ ...google, business_location_name: e.target.value })} />}
                  </Field>

                  <ActionRow>
                    <button className="primary-action" onClick={saveGoogleSelections}>
                      <Check size={14} /> Salva account trovati
                    </button>
                  </ActionRow>
                </>
              )}
            </section>
          )}

          {step === 4 && (
            <section className="wizard-form">
              <GuideText
                title="Facebook e Instagram: un solo login"
                text="Fai accesso con Facebook. GE360 legge le Pagine che amministri e prova a trovare l'Instagram professionale collegato."
              />

              <div className={status?.completion?.meta ? 'login-card connected' : 'login-card'}>
                <div className="login-card-icon"><Share2 size={24} /></div>
                <div>
                  <strong>{status?.completion?.meta ? 'Facebook / Instagram collegati' : 'Accedi con Facebook'}</strong>
                  <p>
                    Niente Page ID o token da copiare: dopo il login scegli la Pagina da un elenco.
                  </p>
                </div>
                <button className="primary-action login-action" onClick={connectMeta} disabled={Boolean(busy)}>
                  <LogIn size={15} /> {status?.completion?.meta ? 'Ricollega' : 'Accedi con Facebook'}
                </button>
              </div>

              {!status?.meta?.META_APP_ID?.configured || !status?.meta?.META_APP_SECRET?.configured ? (
                <div className="one-time-setup">
                  <div className="one-time-heading">
                    <Settings2 size={18} />
                    <div><strong>Prima volta: identifica GE360 a Meta</strong><span>App ID e Secret si inseriscono una volta sola.</span></div>
                  </div>
                  <ol className="wizard-numbered compact">
                    <li><strong>Apri Meta for Developers</strong><span>Crea/seleziona una app adatta alla gestione della tua Pagina.</span></li>
                    <li><strong>Configura Facebook Login</strong><span>Aggiungi il redirect GE360 indicato sotto.</span></li>
                    <li><strong>Copia App ID e App Secret</strong><span>Poi non dovrai più cercare Page ID o token.</span></li>
                  </ol>
                  <code>http://127.0.0.1:8788/api/oauth/meta/callback</code>
                  <a className="wizard-external-link" href="https://developers.facebook.com/apps/" target="_blank" rel="noreferrer">
                    Apri Meta for Developers <ExternalLink size={13} />
                  </a>
                  <div className="advanced-box-body meta-onetime-fields">
                    <Field label="Meta App ID">
                      <input value={meta.app_id} onChange={(e) => setMeta({ ...meta, app_id: e.target.value })} />
                    </Field>
                    <Field
                      label="Meta App Secret"
                      hint={status?.meta?.META_APP_SECRET?.configured ? 'Già salvato: lascia vuoto per conservarlo.' : ''}
                    >
                      <input type="password" value={meta.app_secret} onChange={(e) => setMeta({ ...meta, app_secret: e.target.value })} />
                    </Field>
                    <button className="secondary-action" onClick={saveMetaCredentials}>Salva configurazione una tantum</button>
                  </div>
                </div>
              ) : (
                <details className="advanced-box">
                  <summary>Configurazione Meta avanzata</summary>
                  <div className="advanced-box-body">
                    <Field label="Meta App ID">
                      <input value={meta.app_id} onChange={(e) => setMeta({ ...meta, app_id: e.target.value })} />
                    </Field>
                    <Field label="Meta App Secret">
                      <input type="password" value={meta.app_secret} onChange={(e) => setMeta({ ...meta, app_secret: e.target.value })} />
                    </Field>
                    <button className="secondary-action" onClick={saveMetaCredentials}>Aggiorna</button>
                  </div>
                </details>
              )}

              {metaPages.length > 0 && (
                <>
                  <div className="wizard-divider" />
                  <div className="selection-heading">
                    <span className="eyebrow">SCEGLI LA PAGINA</span>
                    <h4>Quale attività vuoi collegare a GE360?</h4>
                  </div>
                  <div className="page-choice-grid">
                    {metaPages.map((page) => (
                      <button
                        key={page.id}
                        className="page-choice"
                        onClick={() => selectMetaPage(page.id)}
                        disabled={busy === `meta-select-${page.id}`}
                      >
                        <div className="page-choice-icon"><Share2 size={18} /></div>
                        <div>
                          <strong>{page.name || page.id}</strong>
                          <small>{page.category || 'Pagina Facebook'}</small>
                          {page.instagram?.connected ? (
                            <span className="instagram-found"><Camera size={12} /> @{page.instagram.username || page.instagram.id}</span>
                          ) : (
                            <span className="instagram-missing">Instagram non rilevato</span>
                          )}
                        </div>
                        <ArrowRight size={16} />
                      </button>
                    ))}
                  </div>
                </>
              )}

              {(params.get('meta') === 'connected' || status?.meta?.META_USER_ACCESS_TOKEN?.configured) && (
                <ActionRow>
                  <button className="secondary-action" onClick={() => loadMetaPages()}>
                    <RefreshCw size={14} /> Rileggi le Pagine disponibili
                  </button>
                </ActionRow>
              )}
            </section>
          )}

          {step === 5 && (
            <section className="wizard-form">
              <GuideText
                title="Controllo finale"
                text="Qui verifichiamo tutto e lanciamo una sincronizzazione completa."
              />
              <div className="setup-review-grid">
                <Review label="AI locale" ok={status?.completion?.ai} />
                <Review label="WordPress Tracker" ok={status?.completion?.wordpress} />
                <Review label="Google OAuth" ok={status?.completion?.google_connected} />
                <Review label="Risorse Google" ok={status?.completion?.google_resources} />
                <Review label="Facebook / Instagram" ok={status?.completion?.meta} />
              </div>
              <ActionRow>
                <button className="primary-action" onClick={finalSync} disabled={busy === 'sync'}>
                  <RefreshCw size={14} /> Sincronizza tutto e verifica
                </button>
              </ActionRow>
              <div className="wizard-final-note">
                <Sparkles size={18} />
                <div>
                  <strong>Dopo la prima sincronizzazione</strong>
                  <p>Vai su AI Locale e genera il primo Report completo con Qwen.</p>
                </div>
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
        text="Non reinstalliamo niente. Verifichiamo AI locale e connessioni già salvate."
      />
      <div className="system-detect-grid">
        <Detection label="Ollama" value={status?.ai?.ok ? 'Rilevato' : 'Non raggiungibile'} ok={status?.ai?.ok} detail={status?.ai?.base_url} />
        <Detection
          label="Modello AI"
          value={status?.ai?.selected_available ? status.ai.selected_model : 'Da scegliere'}
          ok={status?.ai?.selected_available}
          detail={status?.ai?.models?.length ? `${status.ai.models.length} modelli trovati` : 'Nessun modello rilevato'}
        />
        <Detection label="WordPress" value={status?.completion?.wordpress ? 'Configurato' : 'Da completare'} ok={status?.completion?.wordpress} />
        <Detection label="Google" value={status?.completion?.google_connected ? 'Account collegato' : 'Da collegare'} ok={status?.completion?.google_connected} />
        <Detection label="Facebook / Instagram" value={status?.completion?.meta ? 'Collegati' : 'Da collegare'} ok={status?.completion?.meta} />
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

function FoundCard({ label, count }) {
  return (
    <div className={count ? 'found-card ok' : 'found-card'}>
      {count ? <CheckCircle2 size={16} /> : <CircleAlert size={16} />}
      <div><strong>{label}</strong><span>{count ? `${count} trovati` : 'Nessuno trovato'}</span></div>
    </div>
  )
}

export default SetupWizardPage
