import { useEffect, useMemo, useState } from 'react'
import {
  Check,
  CircleAlert,
  Copy,
  Cpu,
  Download,
  FileText,
  Gauge,
  RefreshCw,
  Sparkles,
  WandSparkles,
} from 'lucide-react'


const formatBytes = (value) => {
  if (!value) return ''
  const gb = value / 1024 / 1024 / 1024
  return `${gb.toFixed(gb >= 10 ? 0 : 1)} GB`
}

function LocalAIPage({ days = 30, dashboardMode = 'demo' }) {
  const [status, setStatus] = useState(null)
  const [baseUrl, setBaseUrl] = useState('http://127.0.0.1:11434')
  const [model, setModel] = useState('')
  const [think, setThink] = useState(false)
  const [reportType, setReportType] = useState('full')
  const [report, setReport] = useState(null)
  const [history, setHistory] = useState([])
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')

  const models = status?.models || []

  const selectedModel = useMemo(
    () => models.find((item) => item.name === model || item.model === model),
    [models, model],
  )

  const loadStatus = async () => {
    setBusy('status')
    setMessage('')
    try {
      const [statusResponse, historyResponse] = await Promise.all([
        fetch('/api/local-ai/status'),
        fetch('/api/local-ai/reports?limit=12'),
      ])

      const statusPayload = await statusResponse.json()
      const historyPayload = await historyResponse.json()

      setStatus(statusPayload)
      setBaseUrl(statusPayload.base_url || 'http://127.0.0.1:11434')
      setModel(statusPayload.selected_model || '')
      setThink(Boolean(statusPayload.think))
      setHistory(historyPayload.items || [])

      if (!statusPayload.ok) {
        setMessage(statusPayload.message)
      }
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy('')
    }
  }

  useEffect(() => {
    loadStatus()
  }, [])

  const saveConfig = async () => {
    if (!model) {
      setMessage('Seleziona prima un modello Ollama.')
      return
    }

    setBusy('save')
    setMessage('')
    try {
      const response = await fetch('/api/local-ai/configure', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: baseUrl,
          model,
          think,
        }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Configurazione non salvata')

      setMessage('Configurazione AI locale salvata nel database GE360.')
      await loadStatus()
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy('')
    }
  }

  const testConnection = async () => {
    setBusy('test')
    setMessage('')
    try {
      const response = await fetch('/api/local-ai/test', { method: 'POST' })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Test Ollama fallito')
      setMessage(`Ollama OK · ${payload.selected_model} pronto.`)
      setStatus(payload)
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy('')
    }
  }

  const generateReport = async (type = reportType) => {
    setBusy('report')
    setMessage('')
    setReportType(type)
    try {
      const response = await fetch('/api/local-ai/report', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          days,
          report_type: type,
        }),
      })
      const payload = await response.json()
      if (!response.ok) throw new Error(payload.detail || 'Report non generato')
      setReport(payload)
      setMessage('Analisi completata e salvata nello storico GE360.')
      const historyPayload = await fetch('/api/local-ai/reports?limit=12').then((r) => r.json())
      setHistory(historyPayload.items || [])
    } catch (error) {
      setMessage(error.message)
    } finally {
      setBusy('')
    }
  }

  const openHistoricalReport = async (id) => {
    setBusy('history')
    try {
      const payload = await fetch(`/api/local-ai/reports/${id}`).then((r) => r.json())
      setReport(payload)
    } finally {
      setBusy('')
    }
  }

  const copyText = async (text, success) => {
    try {
      await navigator.clipboard.writeText(text || '')
      setMessage(success)
    } catch {
      setMessage('Il browser non ha permesso la copia automatica.')
    }
  }

  const downloadReport = () => {
    if (!report?.report_markdown) return
    const blob = new Blob([report.report_markdown], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `ge360-report-${report.period_days || days}giorni-${report.id || 'ultimo'}.md`
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <>
      <section className="page-intro local-ai-intro">
        <div className="page-intro-icon"><Cpu size={22} /></div>
        <div>
          <span className="eyebrow">GE360 INTELLIGENCE · LOCALE</span>
          <h2>Ollama + Qwen analizzano tutto sul tuo server</h2>
          <p>
            Nessuna API AI, nessun login esterno. GE360 prepara i numeri, Qwen li interpreta,
            e quando vuoi puoi copiare il report completo in ChatGPT o Claude.
          </p>
        </div>
        <div className={`local-ai-health ${status?.ok ? 'ok' : ''}`}>
          {status?.ok ? <Check size={17} /> : <CircleAlert size={17} />}
          <span>{status?.ok ? 'Ollama online' : 'Da configurare'}</span>
        </div>
      </section>

      {dashboardMode === 'demo' && (
        <div className="important-note">
          <CircleAlert size={18} />
          <div>
            <strong>Attenzione: GE360 sta ancora mostrando dati demo</strong>
            <p>Puoi testare Qwen, ma per report utili conviene prima collegare almeno WordPress/Google/Meta.</p>
          </div>
        </div>
      )}

      <section className="local-ai-grid">
        <article className="panel local-ai-config">
          <div className="panel-header">
            <div><span>CONFIGURAZIONE</span><h3>Motore AI locale</h3></div>
            <button className="text-button" onClick={loadStatus} disabled={busy === 'status'}>
              <RefreshCw size={14} /> Rileva
            </button>
          </div>

          <label className="form-field">
            <span>Server Ollama</span>
            <input
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder="http://127.0.0.1:11434"
            />
            <small>Se Ollama è installato sullo stesso Linux lascia questo valore.</small>
          </label>

          <label className="form-field">
            <span>Modello</span>
            <select value={model} onChange={(event) => setModel(event.target.value)}>
              <option value="">Seleziona un modello installato</option>
              {models.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name}
                  {item.parameter_size ? ` · ${item.parameter_size}` : ''}
                </option>
              ))}
            </select>
            {selectedModel && (
              <small>
                {selectedModel.family || 'modello'} · {selectedModel.parameter_size || ''}
                {selectedModel.quantization_level ? ` · ${selectedModel.quantization_level}` : ''}
                {selectedModel.size ? ` · ${formatBytes(selectedModel.size)}` : ''}
              </small>
            )}
          </label>

          <label className="toggle-row">
            <div>
              <strong>Reasoning / thinking</strong>
              <small>Attivalo solo se il modello selezionato lo supporta; consuma più tempo e token locali.</small>
            </div>
            <input type="checkbox" checked={think} onChange={(event) => setThink(event.target.checked)} />
          </label>

          <div className="local-ai-actions">
            <button className="secondary-action" onClick={testConnection} disabled={Boolean(busy)}>
              <Gauge size={15} /> Test
            </button>
            <button className="primary-action" onClick={saveConfig} disabled={Boolean(busy)}>
              <Check size={15} /> Salva configurazione
            </button>
          </div>

          {message && <div className="local-ai-message">{message}</div>}

          <div className="detected-models">
            <span className="eyebrow">MODELLI RILEVATI</span>
            {models.length ? models.map((item) => (
              <button
                className={model === item.name ? 'model-chip selected' : 'model-chip'}
                key={item.name}
                onClick={() => setModel(item.name)}
              >
                <Cpu size={13} />
                <span>{item.name}</span>
              </button>
            )) : (
              <p>Nessun modello rilevato. Controlla che Ollama sia avviato.</p>
            )}
          </div>
        </article>

        <article className="panel report-launcher">
          <div className="panel-header">
            <div><span>ANALISI</span><h3>Genera un nuovo report</h3></div>
            <Sparkles size={18} className="sparkle" />
          </div>

          <div className="analysis-period">
            <span>Periodo corrente</span>
            <strong>{days} giorni</strong>
          </div>

          <button
            className="analysis-mode-card"
            onClick={() => generateReport('quick')}
            disabled={Boolean(busy)}
          >
            <WandSparkles size={19} />
            <div><strong>Brief rapido</strong><small>Quadro generale, problemi e 3 azioni prioritarie.</small></div>
          </button>

          <button
            className="analysis-mode-card featured"
            onClick={() => generateReport('full')}
            disabled={Boolean(busy)}
          >
            <FileText size={19} />
            <div><strong>Report completo</strong><small>Acquisizione, lead, contenuti, SEO, anomalie e piano operativo.</small></div>
          </button>

          {busy === 'report' && (
            <div className="ai-working">
              <div className="loading-orb" />
              <div><strong>Qwen sta analizzando GE360…</strong><span>Il modello lavora localmente sul tuo server.</span></div>
            </div>
          )}

          <div className="privacy-local-box">
            <Cpu size={17} />
            <div><strong>100% locale</strong><span>I dati restano sul tuo Linux e vengono inviati solo al tuo Ollama locale.</span></div>
          </div>
        </article>
      </section>

      {report && (
        <article className="panel generated-report">
          <div className="report-toolbar">
            <div>
              <span className="eyebrow">REPORT #{report.id}</span>
              <h3>{report.report_type === 'quick' ? 'Brief GE360' : 'Analisi GE360 completa'}</h3>
              <small>{report.model} · {report.period_days} giorni · {report.created_at || ''}</small>
            </div>
            <div className="report-actions">
              <button
                className="secondary-action"
                onClick={() => copyText(report.report_markdown, 'Report copiato.')}
              >
                <Copy size={14} /> Copia report
              </button>
              <button
                className="secondary-action"
                onClick={() => copyText(report.handoff_prompt, 'Prompt completo copiato per ChatGPT/Claude.')}
              >
                <Sparkles size={14} /> Copia per ChatGPT/Claude
              </button>
              <button className="secondary-action" onClick={downloadReport}>
                <Download size={14} /> Markdown
              </button>
            </div>
          </div>
          <pre className="report-markdown">{report.report_markdown}</pre>
        </article>
      )}

      <article className="panel local-ai-history">
        <div className="panel-header">
          <div><span>STORICO</span><h3>Report salvati</h3></div>
        </div>
        <div className="history-list">
          {history.length ? history.map((item) => (
            <button key={item.id} onClick={() => openHistoricalReport(item.id)}>
              <div>
                <strong>#{item.id} · {item.report_type === 'quick' ? 'Brief' : 'Report completo'}</strong>
                <small>{item.model} · {item.period_days} giorni</small>
              </div>
              <span>{item.created_at}</span>
            </button>
          )) : (
            <div className="empty-state">Non hai ancora generato report AI locali.</div>
          )}
        </div>
      </article>
    </>
  )
}

export default LocalAIPage
