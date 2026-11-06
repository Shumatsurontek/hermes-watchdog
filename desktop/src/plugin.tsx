import React, {Fragment, useState, type ReactNode} from 'react';
import {ROUTES_AREA, SIDEBAR_NAV_AREA, type PluginContext} from '@hermes/plugin-sdk';
import {missionTitle, workerTitle, workerState, type Incident, type Mission, type Worker} from './api';
import {useWatchdog, type Controller} from './controller';
import {css} from './styles';

const time = (value: number): string => new Date(value * 1000).toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
const date = (value: number): string => new Date(value * 1000).toLocaleDateString([], {month: 'short', day: 'numeric'});
function Button({children, onClick, disabled = false, primary = false}: {children: ReactNode; onClick: () => void; disabled?: boolean; primary?: boolean}) {
  return <button type="button" className={`wd-button${primary ? ' wd-primary' : ''}`} onClick={onClick} disabled={disabled}>{children}</button>;
}
function Mark() {
  return <svg className="wd-mark" viewBox="0 0 32 36" fill="none" aria-hidden="true"><path d="M16 2 29 7v10c0 8-7 14-13 17C10 31 3 25 3 17V7L16 2Z" stroke="currentColor" strokeWidth="1.4"/><path d="M7 18h5l3-7 4 13 3-6h4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}
function IncidentCard({item, mission, c}: {item: Incident; mission: Mission; c: Controller}) {
  const human = item.kind === 'human_input';
  const delivery = item.delivery.find(d => d.kind === 'recovery');
  const count = item.member_ids.length;
  const title = human ? 'A worker needs your answer' : item.kind === 'related_failures' ? `${count} workers hit the same error` : item.kind === 'worker_interrupted' ? 'A worker was interrupted' : 'A worker could not finish';
  const deliveryText = delivery ? ({pending: 'Recovery review queued', sending: 'Sending recovery review…', accepted: 'Hermes accepted the review', failed: 'Recovery message was not accepted', unknown: 'Delivery is uncertain — inspect the conversation', withdrawn: 'Recovery request withdrawn'}[delivery.state]) : null;
  return <section className="wd-attention" aria-label={title}>
    <span className="wd-overline wd-warn">{deliveryText ?? (item.status === 'acknowledged' ? 'Acknowledged · still unresolved' : human ? 'Your decision' : 'Needs a review')}</span>
    <h3>{title}</h3>
    <p>{human ? 'Answer in the original conversation. Other workers can keep going.' : `${mission.counts.returned ? 'Keep the returned work. ' : ''}Ask Hermes to inspect the blocked workers and continue only what is still needed.`}</p>
    {item.tools.length > 0 && <p className="wd-note">Observed in {item.tools.join(', ')}. {item.kind === 'related_failures' && 'Matching errors do not establish the cause.'}</p>}
    <div className="wd-actions">
      {human ? <Button primary disabled={c.disabled || mission.deleted} onClick={() => {void c.open(mission.root_id);}}>Answer in Hermes ↗</Button>
        : item.recovery_available ? <Button primary disabled={c.disabled} onClick={() => {void c.act(item, 'request_recovery_review');}}>{c.acting ? 'Requesting…' : 'Ask Hermes to recover'}</Button>
          : <Button primary disabled={c.disabled || mission.deleted} onClick={() => {void c.open(mission.root_id);}}>View conversation ↗</Button>}
      {!human && item.status === 'open' && !delivery && <button className="wd-link" disabled={c.disabled} onClick={() => {void c.act(item, 'acknowledge');}}>Acknowledge</button>}
    </div>
    <details className="wd-technical"><summary>{delivery ? 'Delivery & evidence' : 'What happens next'}</summary>
      <p>{human ? "Open the original conversation and answer its pending request. Watchdog does not answer or approve on your behalf." : "A recovery brief goes to this conversation. Hermes reviews the transcripts, preserves existing results and checks for partial effects before repeating work. This uses your conversation’s model; it does not automatically restart workers or approve writes."}</p>
      {delivery && <p>Message: {delivery.state} · {delivery.attempts} acceptance attempts. Acceptance does not confirm a reply. An uncertain send is never replayed automatically.</p>}
      {!mission.route_available && <p>The original route is unavailable. Open the conversation to decide how to continue.</p>}
      <p className="wd-id">Incident {item.id} · revision {item.revision}</p>
    </details>
  </section>;
}
function WorkerRow({worker, index, c, deleted}: {worker: Worker; index: number; c: Controller; deleted: boolean}) {
  const state = workerState(worker);
  const expanded = c.selectedWorker === worker.session_id;
  const detail = expanded ? c.detail : null;
  return <Fragment>
    <div className="wd-worker">
      <span className={`wd-worker-icon wd-${state.tone}`} aria-hidden="true">{worker.waiting ? '?' : worker.state === 'active' ? '◌' : worker.state === 'returned' ? '↳' : '!'}</span>
      <div><button className="wd-worker-title" aria-expanded={expanded} onClick={() => c.selectWorker(expanded ? null : worker.session_id)}>{workerTitle(worker, index)}{worker.label_excerpt ? '…' : ''}</button>
        <div className="wd-worker-sub"><span className={`wd-label wd-${state.tone}`}><span className="wd-dot"/>{state.label}</span><span>{time(worker.updated)}</span>{worker.gap && <span className="wd-warn">Observation incomplete</span>}</div>
      </div>
      <div className="wd-worker-actions"><button className="wd-link" disabled={c.disabled || deleted} onClick={() => {void c.open(worker.session_id);}}>{worker.state === 'returned' ? 'Read result ↗' : 'Open worker ↗'}</button></div>
    </div>
    {expanded && <section className="wd-evidence" aria-label="Worker evidence">
      {!detail ? 'Loading observed events…' : <>
        <p>{worker.label ? 'Task title is a local excerpt of the delegated goal.' : 'No task title was captured for this older worker.'} Returned results have not been independently verified.</p>
        <p>{detail.evidence.length} retained events of {worker.event_count}; starts at #{worker.retained_from}. {worker.observed_errors} errors in this window.</p>
        {worker.gap && <p className="wd-warn">{worker.gap}</p>}
        {detail.evidence.map(e => <div key={e.seq} className="wd-evidence-row"><span>{time(e.at)}</span><span>{e.tool || e.kind.replaceAll('_', ' ')}</span><span>{e.status || e.outcome}</span></div>)}
        <p className="wd-id">Worker {worker.session_id}</p>
      </>}
    </section>}
  </Fragment>;
}
function MissionView({mission, c}: {mission: Mission; c: Controller}) {
  const [primary, ...remaining] = mission.incidents;
  return <section className="wd-focus" aria-label="Conversation work">
    <header className="wd-heading">
      <p className="wd-overline">{date(mission.created)} · {time(mission.created)}</p>
      <div className="wd-line wd-between"><h2>{missionTitle(mission)}</h2><button className="wd-link" disabled={c.disabled || mission.deleted} onClick={() => {void c.open(mission.root_id);}}>Open conversation ↗</button></div>
      <p className="wd-muted">{mission.counts.workers} delegated tasks · {mission.counts.active} working · {mission.counts.returned} returned{mission.counts.waiting ? ` · ${mission.counts.waiting} waiting for input` : ""}{mission.deleted ? ' · origin deleted' : ''}</p>
    </header>
    {primary && <IncidentCard item={primary} mission={mission} c={c}/>}
    {remaining.length > 0 && <details className="wd-more"><summary>{remaining.length} more {remaining.length === 1 ? 'item needs' : 'items need'} review</summary>{remaining.map(item => <IncidentCard key={item.id} item={item} mission={mission} c={c}/>)}</details>}
    {mission.incident_count > mission.incidents.length && <p className="wd-note">Showing {mission.incidents.length} of {mission.incident_count} incidents. Inspect the full conversation for the remaining work.</p>}
    <div className="wd-section-title"><span className="wd-overline">Work in this conversation</span><span className="wd-small wd-muted">{mission.workers.length} tasks</span></div>
    {mission.workers.map((worker, index) => <WorkerRow key={worker.session_id} worker={worker} index={index} c={c} deleted={mission.deleted}/>)}
    {mission.counts.workers > mission.workers.length && <p className="wd-note">Showing {mission.workers.length} of {mission.counts.workers} workers. Open the conversation for all tasks.</p>}
    <details className="wd-technical"><summary>Observation details</summary><p>Updates every 5 seconds. Watchdog observes native delegates without model calls. Hermes owns execution, approvals and result delivery.</p><p className="wd-id">Conversation {mission.root_id}</p></details>
  </section>;
}
const EXAMPLE = `Prépare une décision de release pour ce dépôt : quels blocages empêchent de publier, quelles preuves avons-nous, que reste-t-il à vérifier ? Utilise trois delegates natifs en parallèle : tests et build ; revue des changements et risques de régression ; documentation et procédure de rollback. Donne à chaque tâche un titre court sur la première ligne, par exemple « Release readiness · Tests ». Chaque worker doit rapporter ses preuves, ses limites et les points non vérifiés. Ne publie rien et ne modifie pas les sources. Si une dépendance ou une autorisation manque, signale précisément le blocage et conserve les résultats des autres workers.`;
function Empty({attention}: {attention: boolean}) {
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState('');
  async function copy(): Promise<void> {
    try {await navigator.clipboard.writeText(EXAMPLE); setCopied(true); setError('');}
    catch {setError('Clipboard unavailable. Select the example below to copy it.');}
  }
  return <section className="wd-empty"><div className="wd-empty-icon" aria-hidden="true">{attention ? '✓' : '◌'}</div><h2>{attention ? 'Nothing needs your attention here' : 'Delegate the work. Keep the thread.'}</h2><p>{attention ? 'Other work is available in All work. Watchdog will surface a request when a worker needs you.' : 'Ask Hermes to review a real release in parallel. Its workers appear here automatically, alongside any blockers.'}</p>{!attention && <><Button primary onClick={() => {void copy();}}>{copied ? 'Prompt copied' : 'Copy release review prompt'}</Button><details className="wd-technical"><summary>Read the example</summary><p>{EXAMPLE}</p></details>{error && <p role="alert">{error}</p>}</>}</section>;
}
function History({c}: {c: Controller}) {
  return <section aria-label="Launcher history"><h2>Launcher history</h2><p className="wd-note">Earlier tasks started with watchdog_start.</p>
    {c.past?.tasks.map(task => <article className="wd-history" key={task.id}><div className="wd-line wd-between"><h3>{task.goal}</h3><Button disabled={c.disabled || !task.can_cancel} onClick={() => {void c.cancel(task);}}>{task.cancel_pending ? 'Cancellation requested' : 'Request cancellation'}</Button></div><p className="wd-muted wd-small">{task.execution.replaceAll('_', ' ')} · {task.supervision.replaceAll('_', ' ')} · {time(task.created)}</p><details className="wd-technical"><summary>Result & delivery</summary><p>Notification: {task.notification}. {task.retry_reason}</p><p>{task.result_excerpt ? 'Result excerpt' : 'Reported result · unverified'}</p><pre>{task.result || 'No result recorded.'}</pre><p className="wd-id">{task.id}</p><p>Retained tool evidence</p>{task.observations.map(e => <div key={e.seq} className="wd-evidence-row"><span>{time(e.at)}</span><span>{e.tool || e.kind}</span><span>{e.status}</span></div>)}<p>Action history</p>{task.events.map(e => <p key={e.id}>{time(e.created)} · {e.kind} · {e.status}</p>)}</details></article>)}
    {c.past?.tasks.length === 0 && <p className="wd-note">No earlier launcher tasks.</p>}
    <div className="wd-pagination">{c.historyCursor && <Button onClick={() => c.setHistoryCursor('')}>First page</Button>}{c.past?.next_cursor && <Button onClick={() => c.setHistoryCursor(c.past?.next_cursor ?? '')}>Next page</Button>}</div>
  </section>;
}
function Watchdog({ctx}: {ctx: PluginContext}) {
  const [history, setHistory] = useState(false);
  const [filter, setFilter] = useState<'all' | 'attention'>('all');
  const [selected, setSelected] = useState<{scope: string; id: string} | null>(null);
  const c = useWatchdog(ctx, history);
  const missions = c.work?.missions ?? [];
  const attention = missions.filter(m => m.counts.attention > 0);
  const visible = filter === 'attention' ? attention : missions;
  const active = visible.find(m => selected?.scope === c.scope && m.root_id === selected.id) ?? visible.find(m => m.counts.attention > 0) ?? visible[0];
  return <main className="wd"><style>{css}</style>
    <header className="wd-top"><div className="wd-brand"><Mark/><div><h1>Watchdog</h1><p className="wd-muted wd-small">Your delegates, in one place.</p></div></div><span className="wd-watch"><span className="wd-dot"/>{c.error ? 'Connection needs attention' : c.loading ? 'Updating' : 'Observing'} · {c.profile || 'default'}</span></header>
    {c.error && <div role="alert" className="wd-error"><span>{c.error}</span><button className="wd-link" onClick={c.refresh}>Refresh</button></div>}
    {Object.entries(c.work?.health ?? {}).map(([key, value]) => <div key={key} className="wd-error" role="status">{value}</div>)}
    {!history && <nav className="wd-tabs" aria-label="Work filters"><button className="wd-tab" aria-pressed={filter === 'all'} onClick={() => {setFilter('all'); c.selectWorker(null);}}>All work<span className="wd-count">{c.work?.total_missions ?? '—'}</span></button><button className="wd-tab" aria-pressed={filter === 'attention'} onClick={() => {setFilter('attention'); c.selectWorker(null);}}>Needs attention<span className="wd-count">{attention.length}</span></button></nav>}
    {history ? <History c={c}/> : !c.work ? <div className="wd-skeleton">{c.error ? 'Work is unavailable until the connection is restored.' : 'Loading your delegates…'}</div> : visible.length === 0 ? <Empty attention={filter === 'attention'}/> : <div className="wd-layout">
      <aside className="wd-rail" aria-label="Conversations">{visible.map(mission => <button key={mission.root_id} className="wd-mission" aria-pressed={active?.root_id === mission.root_id} onClick={() => {setSelected({scope: c.scope, id: mission.root_id}); c.selectWorker(null);}}><span className="wd-overline">{date(mission.created)} · {time(mission.created)}</span><strong>{missionTitle(mission)}</strong><span className={`wd-small ${mission.counts.attention ? 'wd-warn' : 'wd-muted'}`}><span className="wd-dot"/>{mission.counts.attention ? `${mission.counts.attention} to review` : mission.counts.active ? `${mission.counts.active} working` : `${mission.counts.returned} returned`}</span></button>)}</aside>
      {active && <MissionView mission={active} c={c}/>}
    </div>}
    {!history && <div className="wd-pagination">{c.cursor > 0 && <Button onClick={() => {c.setCursor(0); c.selectWorker(null);}}>Most recent</Button>}{c.work?.next_cursor !== null && c.work?.next_cursor !== undefined && <Button onClick={() => {c.setCursor(c.work?.next_cursor ?? 0); c.selectWorker(null);}}>Older work</Button>}</div>}
    <footer className="wd-footer"><span>{!history && c.work && c.work.total_missions > missions.length ? `${missions.length} of ${c.work.total_missions} conversations · filters apply to this page` : 'Native Hermes delegates · local observation'}</span><button className="wd-link" onClick={() => {setHistory(v => !v); c.selectWorker(null);}}>{history ? '← Back to native work' : 'Launcher history'}</button></footer>
  </main>;
}
export default {
  id: 'hermes-watchdog', name: 'Watchdog', defaultEnabled: false,
  register(ctx: PluginContext): void {
    ctx.registerMany([
      {id: 'page', area: ROUTES_AREA, data: {path: '/watchdog'}, render: () => <Watchdog ctx={ctx}/>},
      {id: 'nav', area: SIDEBAR_NAV_AREA, data: {path: '/watchdog', label: 'Watchdog', codicon: 'pulse'}},
    ]);
  },
};
