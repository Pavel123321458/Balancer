import { useRef, useState, type FormEvent } from 'react'
import { post, type Catalog, type Config, type Dataset, type Run } from './api'
import { Feedback, fmt, Icon, Title, useData } from './shared'

export const checkLabels: Record<string, string> = {
  check_ar_drop_by_product: 'Падение доли одобрений по продукту',
  check_attribute_new_loss: 'Появление и исчезновение атрибутов',
  check_external_score_drift: 'Сдвиг внешнего скора',
  check_stop_factor_disappeared: 'Исчезновение стоп-фактора',
  check_target_model_changed: 'Смена целевой модели',
}
const roles = [
  ['normalize', 'normalizer', 'normalize_params', 'Нормализация'],
  ['compare', 'comparator', 'compare_params', 'Сравнение'],
  ['aggregate', 'aggregator', 'aggregate_params', 'Агрегация'],
] as const

export function NewAnalysis({ copy }: { copy?: string }) {
  const datasets = useData<Dataset[]>('/datasets')
  const catalog = useData<Catalog>('/plugins')
  if (datasets.error || catalog.error) return <Feedback error={datasets.error ?? catalog.error} />
  if (!datasets.data || !catalog.data) return <Feedback />
  return copy
    ? <CopyConfiguration copy={copy} datasets={datasets.data} catalog={catalog.data} reload={datasets.reload} />
    : <ConfigForm datasets={datasets.data} catalog={catalog.data} reload={datasets.reload} />
}

function CopyConfiguration({ copy, ...props }: { copy: string; datasets: Dataset[]; catalog: Catalog; reload: () => void }) {
  const run = useData<Run>('/runs/' + encodeURIComponent(copy))
  if (!run.data) return <Feedback error={run.error} />
  return <ConfigForm {...props} initial={run.data} />
}

function ConfigForm({ datasets, catalog, reload, initial }: {
  datasets: Dataset[]; catalog: Catalog; reload: () => void; initial?: Run
}) {
  const [dataset, setDataset] = useState(initial?.dataset_id ?? datasets[0]?.id ?? 0)
  const [procedures, setProcedures] = useState({
    normalizer: initial?.settings.normalizer ?? 'builtin', comparator: initial?.settings.comparator ?? 'builtin',
    aggregator: initial?.settings.aggregator ?? 'builtin',
  })
  const [params, setParams] = useState(() => Object.fromEntries(roles.map(([, , key]) => [
    key, JSON.stringify(initial?.settings[key] ?? {}, null, 2),
  ])))
  const [selected, setSelected] = useState(() => initial ? Object.keys(initial.settings.checks) : catalog.checks)
  const [checkParams, setCheckParams] = useState(() => Object.fromEntries(
    Object.entries(initial?.settings.checks ?? {}).map(([name, value]) => [name, JSON.stringify(value, null, 2)]),
  ))
  const [file, setFile] = useState<File>()
  const fileInput = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')

  function jsonObject(text: string, label: string) {
    try {
      const value: unknown = JSON.parse(text)
      if (value && typeof value === 'object' && !Array.isArray(value)) return value as Record<string, unknown>
    } catch { /* show a field-specific error */ }
    throw new Error(`${label}: укажите параметры в виде JSON-объекта`)
  }

  async function upload() {
    if (!file) return
    setBusy('Загрузка датасета…'); setError('')
    try {
      const form = new FormData()
      form.set('file', file)
      const result = await post<{ id: number }>('/datasets', form)
      setDataset(result.id); setFile(undefined)
      if (fileInput.current) fileInput.current.value = ''
      reload()
    } catch (err) { setError((err as Error).message) }
    finally { setBusy('') }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!dataset) return
    setBusy('Сохранение…'); setError('')
    try {
      const config: Config = {
        ...procedures,
        normalize_params: jsonObject(params.normalize_params, 'Нормализация'),
        compare_params: jsonObject(params.compare_params, 'Сравнение'),
        aggregate_params: jsonObject(params.aggregate_params, 'Агрегация'),
        checks: Object.fromEntries(selected.map(name => [name, jsonObject(checkParams[name] ?? '{}', name)])),
      }
      const result = await post<{ id: number }>('/runs', { dataset_id: dataset, ...config })
      location.hash = '#/runs/' + result.id
    } catch (err) { setError((err as Error).message) }
    finally { setBusy('') }
  }

  return <>
    <a href="#/" className="back-link"><Icon name="back" /> Все анализы</a>
    <Title eyebrow="Рабочая область" title="Новый анализ"
      subtitle="Выберите данные и Python-процедуры. Конфигурацию можно сохранить и запустить позже." />
    <form className="stack" onSubmit={save}>
      <section className="panel form-panel">
        <div className="section-title"><span className="step">01</span><div><h2>Датасет</h2><p>Пары ответов BEFORE_MASTER и AFTER_BETA</p></div></div>
        <label>Выбранный датасет<select aria-label="Выбранный датасет" value={dataset} onChange={event => setDataset(Number(event.target.value))}>
          <option value={0}>Выберите датасет</option>
          {datasets.map(item => <option key={item.id} value={item.id}>{item.name} · {fmt(item.application_count)} заявок · #{item.id}</option>)}
        </select></label>
        <div className="upload-row"><label>Загрузить ZIP<input ref={fileInput} type="file" accept=".zip,application/zip"
          onChange={event => setFile(event.target.files?.[0])} /></label>
          <button className="btn secondary" type="button" disabled={!file || !!busy} onClick={() => void upload()}>Загрузить датасет</button></div>
      </section>
      <section className="panel form-panel">
        <div className="section-title"><span className="step">02</span><div><h2>Процедуры</h2><p>Встроенные обработчики и Python-файлы из каталога плагинов</p></div></div>
        <div className="form-grid">{roles.map(([role, name, param, label]) => <div key={role}>
          <label>{label}<select aria-label={label} value={procedures[name]} onChange={event => setProcedures({ ...procedures, [name]: event.target.value })}>
            {[...new Set([...catalog[role], procedures[name]])].map(option => <option key={option} value={option}>{option === 'builtin' ? 'Встроенная процедура' : option + '.py'}</option>)}
          </select></label>
          <details><summary>Параметры</summary><label className="sr-only" htmlFor={param}>Параметры: {label}</label>
            <textarea id={param} rows={4} value={params[param]} onChange={event => setParams({ ...params, [param]: event.target.value })} /></details>
        </div>)}</div>
      </section>
      <section className="panel form-panel">
        <div className="section-title"><span className="step">03</span><div><h2>Автоматические проверки</h2><p>Выберите проверки для итогового отчёта</p></div></div>
        {![...catalog.checks, ...selected].length && <p className="muted">В каталоге нет Python-проверок.</p>}
        {[...new Set([...catalog.checks, ...selected])].map(name => <div className="check-choice" key={name}>
          <label className="check-line"><input type="checkbox" checked={selected.includes(name)}
            onChange={event => setSelected(event.target.checked ? [...selected, name] : selected.filter(item => item !== name))} />
            {checkLabels[name] ?? name}</label>
          {selected.includes(name) && <details><summary>Параметры</summary><textarea aria-label={`Параметры: ${name}`} rows={4}
            value={checkParams[name] ?? '{}'} onChange={event => setCheckParams({ ...checkParams, [name]: event.target.value })} /></details>}
        </div>)}
      </section>
      {error && <Feedback error={error} />}
      {busy && <Feedback>{busy}</Feedback>}
      <div className="actions"><button className="btn primary" disabled={!dataset || !!busy} type="submit"><Icon name="check" /> Сохранить конфигурацию</button>
        <a className="btn secondary" href="#/">Отмена</a></div>
    </form>
  </>
}

