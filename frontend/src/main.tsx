import { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { post, query, type Log, type Page, type Run, type RunItem } from './api'
import { checkLabels, NewAnalysis } from './configuration'
import { ApplicationDetail, Applications, Checks, Overview, Pivot } from './reports'
import { Badge, date, Feedback, fmt, Icon, Pager, stages, Table, Title, useData } from './shared'
import './styles.css'

function Home() {
  const [offset, setOffset] = useState(0)
  const page = useData<Page<RunItem>>('/runs' + query({ offset, limit: 30 }), 5000)
  return <>
    <Title eyebrow="Рабочая область" title="Анализы изменений"
      subtitle="Сравнение решений СПР между версиями MASTER и BETA"
      action={<a href="#/new" className="btn primary"><Icon name="plus" /> Новый анализ</a>} />
    <div className="intro"><div className="intro-icon"><Icon name="pulse" /></div><div>
      <strong>От изменения стратегии до конкретной заявки</strong>
      <p>Сопоставляйте ответы, отслеживайте смену решений и разбирайте результаты автоматических проверок.</p>
    </div><span className="intro-mark" aria-hidden="true"><Icon name="pulse" /></span></div>
    <section className="panel">
      <header className="panel-head"><div><h2>История анализов</h2><p>Конфигурации, состояние обработки и результаты</p></div></header>
      {!page.data ? <Feedback error={page.error} /> : <>
        <Table columns={['Анализ / датасет', 'Статус', 'Заявок', 'С различиями', 'Смена решения', 'Создан']} empty={!page.data.rows.length}>
          {page.data.rows.map(row => <tr key={row.id}>
            <td><a className="number-link" href={`#/runs/${row.id}`}>Анализ #{row.id} <Icon name="arrow" /></a>
              <span className="block muted dataset-name">{row.dataset_name}</span></td>
            <td><Badge status={row.status} /></td><td>{fmt(row.total)}</td>
            <td>{fmt(row.apps_with_differences)}</td><td>{fmt(row.apps_with_decision_change)}</td><td>{date(row.created_at)}</td>
          </tr>)}
        </Table><Pager offset={offset} size={30} next={page.data.has_more} set={setOffset} />
      </>}
    </section>
  </>
}

function Journal({ base, run }: { base: string; run: Run }) {
  const log = useData<Log[]>(base + '/logs', ['QUEUED', 'RUNNING'].includes(run.status) ? 2000 : 0)
  const [source, setSource] = useState('')
  const procedures = [
    ['normalize', run.settings.normalizer, 'Нормализация'],
    ['compare', run.settings.comparator, 'Сравнение'],
    ['aggregate', run.settings.aggregator ?? 'builtin', 'Агрегация'],
    ...Object.keys(run.settings.checks ?? {}).map(name => ['check', name, checkLabels[name] ?? name]),
  ]
  const stagesByRole: Record<string, string[]> = { processing: ['normalize', 'compare'], checks: ['check'], aggregating: ['aggregate'] }
  function codeButtons(roles: string[]) {
    return procedures.filter(([role]) => roles.includes(role)).map(([role, name, label]) =>
      <button className="code-button" key={role + name} onClick={() => setSource(`${base}/code/${role}/${encodeURIComponent(name)}`)}>
        <Icon name="code" /> {label}
      </button>)
  }
  function message(text: string) {
    if (text === 'Run queued') return 'Запуск поставлен в очередь'
    if (text === 'Reading dataset and comparing responses') return 'Чтение датасета и сравнение ответов'
    if (text === 'Run completed') return 'Обработка завершена'
    if (text === 'Worker restarted; run queued again') return 'Worker перезапущен, анализ снова в очереди'
    if (text === 'Building counts and application summary') return 'Подготовка фактов и итоговых счётчиков'
    return text.replace(/^Normalizer: /, 'Нормализация: ').replace('; comparator: ', '; сравнение: ')
      .replace(/^Checks: /, 'Проверки: ').replace(/^Проверки: none$/, 'Проверки не выбраны')
  }
  return <div className="stack">
    <section className="panel">
      <header className="panel-head"><div><h2>Журнал выполнения</h2><p>Этапы обработки и исходный код процедур</p></div></header>
      {!log.data ? <Feedback error={log.error} /> :
        <Table columns={['Время', 'Этап', 'Сообщение', 'Код этапа']} empty={!log.data.length}>
          {log.data.map((row, index) => <tr key={index}><td>{date(row.created_at)}</td><td>{stages[row.stage] ?? row.stage}</td>
            <td>{message(row.message)}</td><td><div className="flex flex-wrap gap-2">{codeButtons(stagesByRole[row.stage] ?? [])}</div></td></tr>)}
        </Table>}
    </section>
    <section className="panel form-panel"><h2>Сохранённая конфигурация</h2>
      <div className="flex flex-wrap gap-2">{codeButtons(['normalize', 'compare', 'aggregate', 'check'])}</div>
      <details><summary>Параметры запуска</summary><pre>{JSON.stringify(run.settings, null, 2)}</pre></details>
    </section>
    {source && <Source key={source} path={source} close={() => setSource('')} />}
  </div>
}

function Source({ path, close }: { path: string; close: () => void }) {
  const source = useData<{ filename: string; source: string }>(path)
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => { dialog.current?.showModal() }, [])
  return <dialog ref={dialog} className="source-dialog" aria-label="Код процедуры" onCancel={close}>
    <section className="panel">
      <header className="panel-head"><div><h2>{source.data?.filename ?? 'Код процедуры'}</h2><p>Текущая версия файла</p></div>
        <button className="btn secondary" autoFocus onClick={close}>Закрыть</button></header>
      {source.data ? <pre className="source-code">{source.data.source}</pre> : <Feedback error={source.error} />}
    </section>
  </dialog>
}

const tabs = [
  ['', 'Обзор', 'grid'], ['/pivot', 'Сводная', 'table'], ['/applications', 'Заявки', 'list'],
  ['/checks', 'Проверки', 'check'], ['/journal', 'Журнал', 'pulse'],
] as const

function Analysis({ id, section, appId, search }: { id: string; section: string; appId?: string; search: string }) {
  const base = '/runs/' + id
  const [busy, setBusy] = useState(false)
  const [startError, setStartError] = useState('')
  const [interval, setIntervalMs] = useState(2000)
  const result = useData<Run>(base, interval)
  const run = result.data
  useEffect(() => {
    if (run && ['CREATED', 'SUCCEEDED', 'FAILED'].includes(run.status)) setIntervalMs(0)
  }, [run?.status])
  async function start() {
    setBusy(true); setStartError('')
    try {
      await post(base + '/start')
      setIntervalMs(1500); result.reload()
    } catch (err) { setStartError((err as Error).message) }
    finally { setBusy(false) }
  }
  if (!run) return <Feedback error={result.error} />
  const finished = run.status === 'SUCCEEDED'
  const percent = finished ? 100 : Math.floor(run.processed / Math.max(1, run.total) * 100)
  const active = finished ? section : '/journal'
  return <>
    <a href="#/" className="back-link"><Icon name="back" /> Все анализы</a>
    <Title eyebrow="Сравнение версий СПР" title={`Анализ #${id}`} subtitle={run.dataset_name}
      action={<div className="actions">{run.status === 'CREATED'
        ? <button className="btn primary" disabled={busy} onClick={() => void start()}><Icon name="pulse" /> Запустить анализ</button>
        : <a className="btn secondary" href={`#/new?copy=${id}`}><Icon name="plus" /> Повторить с настройками</a>}</div>} />
    {startError && <Feedback error={startError} />}
    {run.error && <Feedback error={run.error} />}
    <section className="panel run-status" aria-label="Состояние обработки">
      <Badge status={run.status} /><span>{stages[run.stage] ?? run.stage}</span>
      <progress aria-label="Обработано заявок" value={percent} max={100} />
      <strong>{fmt(run.processed)} / {fmt(run.total)}</strong><span className="percent">{percent}%</span>
    </section>
    <nav className="tabs" aria-label="Разделы анализа">
      {tabs.map(([path, label, icon]) => finished || path === '/journal'
        ? <a key={path} href={`#${base}${path}`} className={active === path ? 'active' : ''} aria-current={active === path ? 'page' : undefined}><Icon name={icon} />{label}</a>
        : <span key={path} className="disabled"><Icon name={icon} />{label}</span>)}
    </nav>
    {active === '/journal' ? <Journal base={base} run={run} />
      : active === '/pivot' ? <Pivot base={base} />
      : active === '/checks' ? <Checks base={base} />
      : active === '/applications' ? appId
        ? <ApplicationDetail key={appId + search} base={base} appId={appId} search={search} />
        : <Applications key={search} base={base} search={search} />
      : <Overview base={base} run={run} />}
  </>
}

function App() {
  const [route, setRoute] = useState(() => location.hash.slice(1) || '/')
  useEffect(() => {
    const update = () => { setRoute(location.hash.slice(1) || '/'); window.scrollTo(0, 0) }
    addEventListener('hashchange', update)
    return () => removeEventListener('hashchange', update)
  }, [])
  const separator = route.indexOf('?')
  const path = separator < 0 ? route : route.slice(0, separator)
  const search = separator < 0 ? '' : route.slice(separator)
  const match = path.match(/^\/runs\/(\d+)(?:(\/pivot|\/checks|\/journal|\/applications)(?:\/([^/]+))?)?$/)
  const newPage = path === '/new'
  return <div className="shell">
    <aside className="sidebar">
      <a href="#/" className="brand"><span className="brand-mark"><Icon name="pulse" /></span>
        <span>Balancer<small>АНАЛИЗ ИЗМЕНЕНИЙ</small></span></a>
      <p className="nav-heading">РАБОЧАЯ ОБЛАСТЬ</p>
      <nav aria-label="Главная навигация"><a className={!newPage ? 'selected' : ''} href="#/"><Icon name="grid" /> Анализы</a>
        <a className={newPage ? 'selected' : ''} href="#/new"><Icon name="plus" /> Новый анализ</a></nav>
      <div className="side-foot"><span className="side-dot" /> Сравнение версий СПР</div>
    </aside>
    <main className="workspace" id="main">
      {match ? <Analysis key={match[1]} id={match[1]} section={match[2] ?? ''}
        appId={match[3] ? decodeURIComponent(match[3]) : undefined} search={search} />
        : newPage ? <NewAnalysis key={search} copy={new URLSearchParams(search).get('copy') ?? undefined} />
        : path === '/' ? <Home /> : <Feedback error="Страница не найдена" />}
    </main>
  </div>
}

createRoot(document.getElementById('root')!).render(<App />)

