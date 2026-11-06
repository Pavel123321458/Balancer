import { useState } from 'react'
import { api, query, type Application, type Attribute, type Check, type Comparison, type Dimension, type Filters,
  type PivotRow, type Run, type Change } from './api'
import { changes, decision, Feedback, fmt, Icon, Pager, Table, useData } from './shared'

const dimensions: Record<Dimension, string> = {
  PREFIX: 'Префикс', CLASS: 'Класс', SUFFIX: 'Суффикс', ARRAY_KEY: 'Ключ массива', KEY: 'Атрибут',
  VALUE_ADJUSTED: 'Значение / бакет', DIFF_FLAG: 'Различие', SOURCE: 'Срез',
}
const keys = Object.keys(dimensions) as Dimension[]
const filterLabel = (key: Dimension, value: string | number | undefined) =>
  key === 'DIFF_FLAG' ? (Number(value) ? 'Изменилось' : 'Совпадает') : value === '' ? '∅ Пусто' : value ?? '—'
const PAGE_SIZE = 30
const appsLink = (base: string, options: Parameters<typeof query>[0] = {}) => '#' + base + '/applications' + query(options)

export function Overview({ base, run }: { base: string; run: Run }) {
  const top = useData<Attribute[]>(base + '/top-attributes')
  if (!run.summary) return null
  const cards = [
    ['Всего заявок', run.summary.applications, 'all', 'layers', 'Сопоставлено в двух срезах'],
    ['Заявки с различиями', run.summary.apps_with_differences, 'differences', 'pulse', 'Хотя бы один изменённый атрибут'],
    ['Смена решения', run.summary.apps_with_decision_change, 'decisions', 'check', 'Итоговое решение изменилось'],
  ] as const
  return <div className="stack">
    <div className="metrics">{cards.map(([label, value, scope, icon, note], index) => <a className="metric panel" href={appsLink(base, { scope })} key={scope}>
      <span className={`metric-icon tone-${index}`}><Icon name={icon} /></span>
      <span className="metric-label">{label}</span><strong>{fmt(value)}</strong><span className="metric-note">{note}</span>
      <span className="metric-arrow"><Icon name="arrow" /></span>
    </a>)}</div>
    <section className="panel">
      <header className="panel-head"><div><h2>Чаще всего меняются</h2><p>Уникальные заявки с различием по пути атрибута</p></div>
        <span className="tag">{fmt(run.summary.comparison_rows)} строк сравнения</span></header>
      {!top.data ? <Feedback error={top.error} /> :
        <Table columns={['Путь атрибута', 'Доля от всех заявок', 'Заявок']} empty={!top.data.length}>
          {top.data.map(row => <tr key={row.path}><td className="mono">{row.path}</td>
            <td className="bar-cell"><div className="bar"><i style={{ width: `${row.applications / Math.max(1, run.summary!.applications) * 100}%` }} /></div></td>
            <td><a className="number-link" href={appsLink(base, { path: row.path })}>{fmt(row.applications)} <Icon name="arrow" /></a></td></tr>)}
        </Table>}
    </section>
  </div>
}

export function Pivot({ base }: { base: string }) {
  const [first, setFirst] = useState<Dimension>('CLASS')
  const [second, setSecond] = useState<Dimension | ''>('KEY')
  const [split, setSplit] = useState<'none' | 'SOURCE' | 'DIFF_FLAG'>('SOURCE')
  const [filterKey, setFilterKey] = useState<Dimension>('DIFF_FLAG')
  const [filterValue, setFilterValue] = useState('1')
  const [filters, setFilters] = useState<Filters>({ DIFF_FLAG: 1 })
  const [offset, setOffset] = useState(0)
  const group: Dimension[] = second ? [first, second] : [first]
  const result = useData<{ rows: PivotRow[]; has_more: boolean }>(base + '/pivot' +
    query({ group, split, filters: JSON.stringify(filters), offset, limit: PAGE_SIZE }))
  const cells = split === 'SOURCE' ? [['BEFORE', 'BEFORE', 'BEFORE'], ['AFTER', 'AFTER', 'AFTER']] as const
    : split === 'DIFF_FLAG' ? [['Совпадает', 'same_count', 0], ['Изменилось', 'diff_count', 1]] as const : []
  function link(row: PivotRow, value?: string | number) {
    const selected = { ...filters }
    group.forEach(name => { selected[name] = row[name] })
    if (value !== undefined && split !== 'none') selected[split] = value
    return appsLink(base, { filters: JSON.stringify(selected) })
  }
  return <section className="panel">
    <header className="panel-head"><div><h2>Сводная таблица</h2><p>Сумма сохранённых counts. Одна заявка может входить в несколько фактов.</p></div></header>
    <div className="pivot-controls">
      <label>Первая группировка<select aria-label="Первая группировка" value={first} onChange={event => {
        const value = event.target.value as Dimension; setFirst(value); if (value === second) setSecond(''); setOffset(0)
      }}>{keys.filter(key => key !== split).map(key => <option key={key} value={key}>{dimensions[key]}</option>)}</select></label>
      <label>Вторая группировка<select aria-label="Вторая группировка" value={second} onChange={event => { setSecond(event.target.value as Dimension | ''); setOffset(0) }}>
        <option value="">Без группировки</option>{keys.filter(key => key !== first && key !== split).map(key => <option key={key} value={key}>{dimensions[key]}</option>)}</select></label>
      <label>Колонки<select aria-label="Колонки" value={split} onChange={event => { setSplit(event.target.value as typeof split); setOffset(0) }}>
        <option value="none">Только итог</option>{(['SOURCE', 'DIFF_FLAG'] as const).filter(key => !group.includes(key)).map(key => <option key={key} value={key}>{dimensions[key]}</option>)}</select></label>
    </div>
    <form className="pivot-controls filters" onSubmit={event => {
      event.preventDefault()
      setFilters({ ...filters, [filterKey]: filterKey === 'DIFF_FLAG' ? Number(filterValue) : filterValue }); setOffset(0)
    }}>
      <label>Поле фильтра<select aria-label="Поле фильтра" value={filterKey} onChange={event => {
        const key = event.target.value as Dimension; setFilterKey(key); setFilterValue(key === 'DIFF_FLAG' ? '1' : key === 'SOURCE' ? 'AFTER' : '')
      }}>{keys.map(key => <option key={key} value={key}>{dimensions[key]}</option>)}</select></label>
      <label>Значение фильтра{filterKey === 'DIFF_FLAG' || filterKey === 'SOURCE'
        ? <select aria-label="Значение фильтра" value={filterValue} onChange={event => setFilterValue(event.target.value)}>{filterKey === 'DIFF_FLAG'
          ? <><option value="1">Изменилось</option><option value="0">Совпадает</option></>
          : <><option>AFTER</option><option>BEFORE</option></>}</select>
        : <input value={filterValue} onChange={event => setFilterValue(event.target.value)} placeholder="Точное значение" />}</label>
      <button className="btn secondary">Применить фильтр</button>
    </form>
    <div className="chips">{Object.entries(filters).map(([key, value]) => <button className="tag removable" key={key} type="button" aria-label={`Убрать фильтр ${dimensions[key as Dimension]}`}
      onClick={() => { const next = { ...filters }; delete next[key as Dimension]; setFilters(next); setOffset(0) }}>
      {dimensions[key as Dimension]}: {filterLabel(key as Dimension, value)} ×</button>)}</div>
    {!result.data ? <Feedback error={result.error} /> : <>
      <Table columns={[...group.map(key => dimensions[key]), ...cells.map(([label]) => label), 'Сумма counts']} empty={!result.data.rows.length}>
        {result.data.rows.map(row => <tr key={JSON.stringify(group.map(key => row[key]))}>
          {group.map(key => <td key={key} className="mono">{filterLabel(key, row[key])}</td>)}
          {cells.map(([label, field, value]) => <td key={label}>{row[field] ? <a className="number-link" href={link(row, value)}>{fmt(row[field])}</a> : '0'}</td>)}
          <td><a className="number-link" href={link(row)}>{fmt(row.total)} <Icon name="arrow" /></a></td>
        </tr>)}
      </Table><Pager offset={offset} size={PAGE_SIZE} next={result.data.has_more} set={setOffset} />
    </>}
  </section>
}

function downloadReport(checks: Check[], base: string) {
  const escape = (value: unknown) => String(value).replace(/[&<>"']/g, char => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]!
  ))
  const root = location.origin + location.pathname
  const cells = (values: unknown[]) => values.map(value => `<td>${escape(value)}</td>`).join('')
  const rows = checks.map(row => `<tr>${cells([row.LABEL, row.SOURCE, row.ARGUMENT, row.CNT, row.TOTAL, row.METRIC,
    row.RESULT, row.CONFIDENCE === 'LOW' ? 'Низкая' : 'Высокая'])}<td>${row.APP_IDS.length
      ? `<a href="${escape(root + appsLink(base, { app_id: row.APP_IDS }))}">${row.APP_IDS.length}</a>` : '—'}</td></tr>`).join('')
  const html = `<!doctype html><html lang="ru"><meta charset="utf-8"><title>Balancer — отчёт проверок</title>
  <style>body{font:15px system-ui;margin:32px;color:#17172a}table{border-collapse:collapse}td,th{border:1px solid #ddd;padding:8px;text-align:left}th{background:#f0edf9}</style>
  <h1>Отчёт автоматических проверок</h1><p><a href="${escape(root + '#' + base + '/pivot')}">Открыть сводную в Balancer</a></p>
  <table><thead><tr>${['Проверка','Срез','Аргумент','Затронуто','Всего','Метрика','Результат','Уверенность','Заявки']
    .map(label => `<th>${label}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></html>`
  const blob = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = blob; anchor.download = `balancer-run-${base.split('/').at(-1)}.html`; anchor.click()
  setTimeout(() => URL.revokeObjectURL(blob), 1000)
}

export function Checks({ base }: { base: string }) {
  const [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const checks = useData<Check[]>(base + '/checks' + query({ offset, limit: PAGE_SIZE + 1 }))
  async function exportReport() {
    setBusy(true); setError('')
    try {
      const all: Check[] = []
      while (true) {
        const batch = await api<Check[]>(base + '/checks' + query({ offset: all.length, limit: 1000 }))
        all.push(...batch)
        if (batch.length < 1000) break
      }
      downloadReport(all, base)
    } catch (err) { setError((err as Error).message) }
    finally { setBusy(false) }
  }
  return <section className="panel">
    <header className="panel-head"><div><h2>Автоматические проверки</h2><p>Единый отчёт PASS / FAIL</p></div>
      <button className="btn secondary" disabled={busy || !checks.data} onClick={() => void exportReport()}><Icon name="download" /> Скачать HTML</button></header>
    {error && <Feedback error={error} />}
    {!checks.data ? <Feedback error={checks.error} /> : <>
      <Table columns={['Проверка', 'Срез', 'Аргумент', 'Затронуто / всего', 'Метрика', 'Результат', 'Заявки']} empty={!checks.data.length}>
        {checks.data.slice(0, PAGE_SIZE).map((row, index) => <tr key={index}>
          <td>{row.LABEL}</td><td><span className="tag">{row.SOURCE}</span></td><td className="mono">{row.ARGUMENT || '—'}</td>
          <td>{fmt(row.CNT)} / {fmt(row.TOTAL)}</td><td>{fmt(row.METRIC)}</td>
          <td><span className={`verdict ${row.RESULT === 'PASS' ? 'pass' : row.CONFIDENCE === 'LOW' ? 'low' : 'fail'}`}>{row.RESULT}</span>
            {row.CONFIDENCE === 'LOW' && <small className="block muted">Низкая уверенность</small>}</td>
          <td>{row.APP_IDS.length ? <a className="number-link" href={appsLink(base, { app_id: row.APP_IDS })}>{fmt(row.APP_IDS.length)} <Icon name="arrow" /></a> : '—'}</td>
        </tr>)}
      </Table><Pager offset={offset} size={PAGE_SIZE} next={checks.data.length > PAGE_SIZE} set={setOffset} />
    </>}
  </section>
}

export function Applications({ base, search }: { base: string; search: string }) {
  const [offset, setOffset] = useState(0)
  const params = new URLSearchParams(search)
  params.set('offset', String(offset)); params.set('limit', String(PAGE_SIZE))
  const list = useData<{ rows: Application[]; total: number }>(base + '/applications?' + params)
  const path = params.get('path') ?? undefined
  const facts = params.get('filters') ?? undefined
  const scope = params.get('scope')
  const caption = path ?? (facts ? 'Заявки, соответствующие выбранной ячейке сводной'
    : params.has('app_id') ? 'Заявки из результата проверки'
    : scope === 'differences' ? 'С различиями' : scope === 'decisions' ? 'Со сменой итогового решения' : 'Все заявки')
  return <section className="panel">
    <header className="panel-head"><div><h2>Список заявок</h2><p>{caption}</p></div>
      {list.data && <span className="tag">{fmt(list.data.total)} уникальных заявок</span>}</header>
    {!list.data ? <Feedback error={list.error} /> : <>
      <Table columns={['Заявка', 'BEFORE', 'AFTER', 'Атрибуты', 'Продукты']} empty={!list.data.rows.length}>
        {list.data.rows.map(row => <tr key={row.APP_ID}>
          <td><a className="number-link" href={`#${base}/applications/${encodeURIComponent(row.APP_ID)}` +
            query({ path, facts, from: search })}>{row.APP_ID} <Icon name="arrow" /></a></td>
          <td>{decision(row.DECISION_BEFORE)}</td><td className={row.DECISION_CHANGED ? 'emphasis' : ''}>{decision(row.DECISION_AFTER)}</td>
          <td>{row.DIFF_FLAG ? 'Есть различия' : 'Совпадают'}</td><td>{row.PRODUCTS?.split(';').join(', ') || '—'}</td>
        </tr>)}
      </Table><Pager offset={offset} size={PAGE_SIZE} next={offset + PAGE_SIZE < list.data.total} set={setOffset} />
    </>}
  </section>
}

export function ApplicationDetail({ base, appId, search }: { base: string; appId: string; search: string }) {
  const params = new URLSearchParams(search)
  const [focus, setFocus] = useState(params.has('path') || params.has('facts'))
  const [only, setOnly] = useState(params.has('path'))
  const [offset, setOffset] = useState(0)
  const [kind, setKind] = useState<Change | ''>('')
  const app = useData<Application>(base + '/applications/' + encodeURIComponent(appId))
  const result = useData<{ rows: Comparison[] }>(base + '/results' + query({
    app_id: appId, path: focus ? params.get('path') ?? undefined : undefined,
    facts: focus ? params.get('facts') ?? undefined : undefined,
    only_differences: String(only), change_type: kind || undefined, offset, limit: PAGE_SIZE + 1,
  }))
  if (!app.data) return <Feedback error={app.error} />
  return <div className="stack">
    <a href={`#${base}/applications${params.get('from') ?? ''}`} className="back-link"><Icon name="back" /> К списку заявок</a>
    <section className="panel panel-head"><div><h2>Заявка {appId}</h2><p>Сравнение результатов стратегии</p></div>
      <div className="decision-flow"><span>BEFORE <strong>{decision(app.data.DECISION_BEFORE)}</strong></span><Icon name="arrow" />
        <span>AFTER <strong>{decision(app.data.DECISION_AFTER)}</strong></span></div>
    </section>
    <section className="panel">
      <header className="panel-head"><div><h2>Атрибуты заявки</h2><p>{focus ? 'Строки, соответствующие переходу из отчёта' : 'Значения по двум срезам'}</p></div>
        {(params.has('path') || params.has('facts')) && <button className="btn secondary" onClick={() => {
          setFocus(!focus); setOnly(false); setKind(''); setOffset(0)
        }}>
          {focus ? 'Все атрибуты заявки' : 'Вернуть выборку из отчёта'}</button>}</header>
      <div className="pivot-controls">
        <label>Тип изменения<select value={kind} onChange={event => { setKind(event.target.value as Change | ''); setOnly(false); setOffset(0) }}>
          <option value="">Все типы</option>{Object.entries(changes).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="check-line"><input type="checkbox" checked={only} onChange={event => {
          setOnly(event.target.checked); setKind(''); setOffset(0)
        }} /> Только различия</label>
      </div>
      {!result.data ? <Feedback error={result.error} /> : <>
        <Table columns={['Атрибут', 'Ключ массива', 'BEFORE', 'AFTER', 'Тип изменения']} empty={!result.data.rows.length}>
          {result.data.rows.slice(0, PAGE_SIZE).map(row => <tr key={JSON.stringify([row.PATH, row.ARRAY_KEY])}>
            <td className="mono">{row.PATH}</td><td className="mono muted">{row.ARRAY_KEY || '—'}</td>
            <td className="mono">{row.VALUE_BEFORE ?? '—'}</td><td className="mono">{row.VALUE_AFTER ?? '—'}</td>
            <td><span className={`change change-${row.CHANGE_TYPE.toLowerCase()}`}>{changes[row.CHANGE_TYPE]}</span></td>
          </tr>)}
        </Table><Pager offset={offset} size={PAGE_SIZE} next={result.data.rows.length > PAGE_SIZE} set={setOffset} />
      </>}
    </section>
  </div>
}

