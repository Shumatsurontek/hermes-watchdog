import { createElement as h, useCallback, useEffect, useRef, useState } from 'react';
import { host, useValue, ROUTES_AREA, SIDEBAR_NAV_AREA, gatewayActivationEpoch } from '@hermes/plugin-sdk';

const colors = { running: '#8b7ae6', starting: '#8b7ae6', succeeded: '#51a88a', failed: '#df826b', unknown: '#d4ac67', cancel_requested: '#d4ac67', cancelled: '#9c9ba7', interrupted: '#9c9ba7' };
const styles = {
  page: { padding: '32px', maxWidth: 1140, margin: '0 auto', color: 'var(--ui-text-primary)', fontFamily: 'inherit' },
  eyebrow: { fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.13em', color: 'var(--ui-text-tertiary)', marginBottom: 10 },
  muted: { color: 'var(--ui-text-secondary)', fontSize: 13, lineHeight: 1.6 },
  card: { border: '1px solid var(--ui-border)', borderRadius: 14, padding: 20, background: 'var(--ui-bg-surface)', minWidth: 0 },
  button: { border: '1px solid var(--ui-border)', borderRadius: 8, background: 'var(--ui-bg-surface)', color: 'inherit', padding: '8px 12px', cursor: 'pointer', font: 'inherit', fontSize: 12 },
  row: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 },
};
const label = (value) => String(value).replaceAll('_', ' ');
const badge = (state) => h('span', { style: { color: colors[state] || '#9c9ba7', fontSize: 12, whiteSpace: 'nowrap' } }, '● ', label(state));
const button = (text, onClick, disabled = false, title = '') => h('button', { type: 'button', style: { ...styles.button, opacity: disabled ? .5 : 1, cursor: disabled ? 'not-allowed' : 'pointer' }, disabled, title, onClick }, text);
const time = (value) => value ? new Date(value * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—';

function Watchdog({ ctx }) {
  const profile = useValue(host.state.profile);
  const gateway = useValue(host.state.gateway);
  const [page, setPage] = useState({ tasks: [], next_cursor: null });
  const [cursor, setCursor] = useState('');
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const alive = useRef(false);
  const route = useRef(null);
  const actionPending = useRef(false);
  const readPending = useRef(false);

  useEffect(() => { setCursor(''); setSelected(null); setDetail(null); setPage({ tasks: [], next_cursor: null }); }, [profile, gateway]);
  useEffect(() => {
    let observed = gatewayActivationEpoch();
    const timer = setInterval(() => {
      const next = gatewayActivationEpoch();
      if (next !== observed) {
        observed = next;
        setPage({tasks: [], next_cursor: null}); setDetail(null); setSelected(null); setCursor(''); setRefresh(v => v+1);
      }
    }, 500);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let timer;
    const epoch = gatewayActivationEpoch();
    const scope = { profile, epoch };
    route.current = scope;
    const current = () => !cancelled && alive.current && host.state.profile.get() === profile && gatewayActivationEpoch() === epoch;
    async function poll() {
      if (!current()) return;
      if (readPending.current) { timer = setTimeout(poll, 5000); return; }
      readPending.current = true;
      try {
        const data = await ctx.rest('/tasks?limit=50&cursor=' + encodeURIComponent(cursor));
        if (!current()) return;
        setPage(data);
        if (selected) {
          const task = await ctx.rest('/tasks/' + encodeURIComponent(selected));
          if (!current()) return;
          setDetail(task);
        }
        setError('');
      } catch (e) {
        if (current()) setError(e.message || 'Watchdog backend unavailable. Enable the agent plugin in this profile.');
      } finally {
        readPending.current = false;
        if (current()) {
          setLoading(false);
          // Schedule after completion so slow requests never accumulate.
          timer = setTimeout(poll, 5000);
        }
      }
    }
    setLoading(true);
    poll();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [ctx, profile, gateway, cursor, selected, refresh]);

  const cancelTask = useCallback(async () => {
    if (!detail || actionPending.current) return;
    const scope = route.current;
    const current = () => alive.current && scope === route.current && scope.profile === host.state.profile.get() && scope.epoch === gatewayActivationEpoch();
    if (!current()) return;
    actionPending.current = true;
    setActing(true);
    try {
      await ctx.rest('/tasks/' + encodeURIComponent(detail.id) + '/actions', { method: 'POST', body: {
        action: 'cancel', session_key: detail.session_key, revision: detail.revision, idempotency_key: crypto.randomUUID(),
      } });
      if (current()) { setError(''); setRefresh((v) => v+1); }
    } catch (e) {
      if (current()) setError(e.message || 'Cancellation request failed; refresh to inspect its state.');
    } finally {
      actionPending.current = false;
      if (alive.current) setActing(false);
    }
  }, [ctx, detail]);

  const active = page.tasks.filter(t => t.reserved).length;
  const attention = page.tasks.filter(t => ['suspected_stall', 'execution_unresolved', 'control_unavailable', 'evidence_gap'].includes(t.supervision)).length;
  const pending = page.tasks.filter(t => ['failed', 'unknown', 'pending'].includes(t.notification)).length;
  const canCancel = detail && detail.reserved && !detail.cancel_at && !detail.cancel_pending && !detail.deleted && !['succeeded', 'failed', 'cancelled', 'interrupted'].includes(detail.execution) && detail.supervision !== 'control_unavailable';

  return h('main', { style: styles.page },
    h('div', { style: styles.eyebrow }, 'Hermes / Watchdog'),
    h('div', { style: styles.row }, h('h1', { style: { fontSize: 32, fontWeight: 500, letterSpacing: '-.04em', margin: 0 } }, 'Work with an owner.'),
      h('span', { style: styles.muted }, profile || 'default', ' · ', loading ? 'Refreshing…' : 'Refreshes every 5 seconds')),
    h('p', { style: { ...styles.muted, maxWidth: 650, margin: '12px 0 28px' } }, 'Keep the conversation moving while workers run. See what returned, what needs attention, and whether Hermes accepted your notification.'),
    error && h('div', { role: 'alert', style: { ...styles.card, borderColor: '#df826b', color: '#df826b', marginBottom: 18 } }, error, ' ', button('Refresh', () => setRefresh(v => v+1))),
    h('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 12, marginBottom: 24 } },
      ...[[active, 'Execution slots reserved', 'Unresolved work keeps its slot.'], [attention, 'Need attention', 'Suspicion is not proof of a stall.'], [pending, 'Notices to inspect', 'Acceptance is not delivery.']].map(([n, title, note]) =>
        h('section', { key: title, style: styles.card }, h('div', { style: { fontSize: 30, marginBottom: 7 } }, n), h('div', { style: { fontSize: 13 } }, title), h('div', { style: { ...styles.muted, fontSize: 11 } }, note)))),
    h('div', { style: { display: 'grid', gridTemplateColumns: detail ? 'repeat(auto-fit, minmax(300px, 1fr))' : '1fr', gap: 16 } },
      h('section', { style: styles.card },
        h('div', { style: styles.row }, h('h2', { style: { fontSize: 16, fontWeight: 500, margin: 0 } }, 'Supervised tasks'), button('Refresh', () => setRefresh(v => v+1))),
        page.tasks.length === 0 && h('div', { style: { padding: '42px 0', maxWidth: 540 } },
          h('div', { style: { fontSize: 20, marginBottom: 10 } }, loading ? 'Loading tasks…' : 'Your next task starts here.'),
          h('p', { style: styles.muted }, 'In a Desktop conversation, ask Hermes: “Use Watchdog to research this in the background.” The worker will appear here after Hermes calls watchdog_start.'),
          h('p', { style: styles.muted }, 'Watchdog supervises only workers it launches. Enable the agent plugin and its notification permission in this profile.')),
        ...page.tasks.map(t => h('button', { key: t.id, type: 'button', onClick: () => { setSelected(t.id); setDetail(null); },
          style: { display: 'block', textAlign: 'left', width: '100%', background: t.id === selected ? 'var(--ui-bg-hover)' : 'transparent', color: 'inherit', border: 0, borderTop: '1px solid var(--ui-border)', padding: '18px 0', cursor: 'pointer', marginTop: 12 } },
          h('div', { style: styles.row }, h('span', { style: { fontSize: 14, fontWeight: 500, maxWidth: '75%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' } }, t.goal), badge(t.execution)),
          h('div', { style: { ...styles.muted, fontSize: 11, marginTop: 6 } }, t.id, ' · ', time(t.created), ' · ', label(t.supervision)))),
        h('div', { style: { ...styles.row, marginTop: 18 } }, h('span', { style: { ...styles.muted, fontSize: 11 } }, 'Counts reflect this page · up to 50 tasks'),
          h('div', { style: { display: 'flex', gap: 8 } }, cursor && button('First page', () => { setCursor(''); setSelected(null); setDetail(null); }),
            page.next_cursor && button('Next page', () => { setCursor(page.next_cursor); setSelected(null); setDetail(null); })))),
      detail && h('section', { style: styles.card, 'aria-label': 'Task details' },
        h('div', { style: styles.row }, h('h2', { style: { fontSize: 16, fontWeight: 500, margin: 0 } }, 'Task details'), button('Close', () => { setSelected(null); setDetail(null); })),
        h('p', { style: { fontSize: 15, lineHeight: 1.6, overflowWrap: 'anywhere' } }, detail.goal), badge(detail.execution),
        h('dl', { style: { fontSize: 12, lineHeight: 1.7, overflowWrap: 'anywhere' } },
          ...[['Supervision', label(detail.supervision)], ['Reason', label(detail.reason)], ['Notification', label(detail.notification)], ['Intervention deadline', time(detail.deadline_at)], ['Observation window', `${detail.observations.length} retained of ${detail.observation_count}; starts at #${detail.retained_from}`]].flatMap(([k, v]) => [h('dt', { key: k, style: { ...styles.muted, fontSize: 11, marginTop: 12 } }, k), h('dd', { key: k+'v', style: { margin: 0 } }, v)])),
        h('div', { style: { display: 'flex', gap: 8, margin: '20px 0 12px' } }, button(acting ? 'Requesting…' : detail.cancel_pending ? 'Cancellation queued' : 'Request cancellation', cancelTask, !canCancel || acting || loading || Boolean(error)), button('Retry unavailable', null, true, detail.retry_reason)),
        h('p', { style: { ...styles.muted, fontSize: 11 } }, detail.retry_reason),
        h('details', null, h('summary', { style: { cursor: 'pointer', fontSize: 12, padding: '12px 0' } }, 'Evidence and action history'),
          ...detail.observations.map(o => h('div', { key: 'o'+o.seq, style: { ...styles.muted, fontSize: 11, padding: '5px 0' } }, '#', o.seq, ' · ', time(o.at), ' · ', label(o.kind), o.tool ? ' · '+o.tool : '', o.status ? ' · '+o.status : '')),
          ...detail.events.map(e => h('div', { key: 'e'+e.id, style: { ...styles.muted, fontSize: 11, padding: '5px 0' } }, time(e.created), ' · ', label(e.kind), ' · ', e.status))),
        detail.result && h('details', null, h('summary', { style: { cursor: 'pointer', fontSize: 12, padding: '12px 0' } }, detail.result_excerpt ? 'Worker result — excerpt' : 'Worker result — unverified'),
          h('pre', { style: { fontFamily: 'inherit', fontSize: 12, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', lineHeight: 1.6 } }, detail.result)))),
    h('p', { style: { ...styles.muted, fontSize: 11, marginTop: 24 } }, 'Cancellation is cooperative. A worker may keep running after a deadline. Watchdog keeps unresolved work visible and reserves its capacity until the outcome is known.')
  );
}

export default {
  id: 'hermes-watchdog', name: 'Watchdog', defaultEnabled: false,
  register(ctx) {
    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: '/watchdog' }, render: () => h(Watchdog, { ctx }) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: '/watchdog', label: 'Watchdog', codicon: 'pulse' } },
    ]);
  },
};
