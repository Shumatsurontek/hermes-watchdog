import {useEffect, useRef, useState, useCallback} from 'react';
import {host, useValue, gatewayActivationEpoch, type PluginContext} from '@hermes/plugin-sdk';
import {api, message, type Incident, type HistoryTask, type WorkerDetail} from './api';
import type {WorkPage} from '../generated/WorkPage';
import type {HistoryPage} from '../generated/HistoryPage';

// A page switch/reload cannot create overlapping reads or competing actions.
const io = {reading: false, acting: false};
const POLL_MS = 5_000;
export function useWatchdog(ctx: PluginContext, history: boolean) {
  const profile = useValue(host.state.profile);
  const gateway = useValue(host.state.gateway);
  const connection = useValue(host.state.connectionId);
  const [epoch, setEpoch] = useState(gatewayActivationEpoch);
  const [cursor, setCursor] = useState(0);
  const [historyCursor, setHistoryCursor] = useState('');
  const [work, setWork] = useState<WorkPage | null>(null);
  const [past, setPast] = useState<HistoryPage | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [selectedWorker, setSelectedWorker] = useState<string | null>(null);
  const [detail, setDetail] = useState<WorkerDetail | null>(null);
  const scope = `${connection ?? ''}\0${profile}\0${gateway}\0${epoch}`;
  const loadedScope = useRef('');
  const currentScope = useRef(scope);
  currentScope.current = scope;
  const alive = useRef(false);
  const intent = useRef<{key: string; nonce: string} | null>(null);
  useEffect(() => {alive.current = true; return () => {alive.current = false;};}, []);
  useEffect(() => {
    const timer = setInterval(() => setEpoch(gatewayActivationEpoch()), 500);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {setWork(null); setPast(null); setDetail(null); setSelectedWorker(null); setCursor(0); setHistoryCursor(''); setError(''); intent.current = null;}, [scope]);
  const valid = useCallback(() => alive.current && currentScope.current === scope && host.state.profile.get() === profile && host.state.connectionId.get() === connection && gatewayActivationEpoch() === epoch && host.state.gateway.get() === gateway, [scope, profile, connection, epoch, gateway]);
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const current = () => !cancelled && valid();
    async function poll(): Promise<void> {
      if (!current()) return;
      if (io.reading) {timer = setTimeout(() => {void poll();}, 250); return;}
      io.reading = true;
      try {
        if (history) {
          const page = await api.history(ctx, historyCursor);
          if (current()) setPast(page);
        } else {
          const page = await api.work(ctx, cursor);
          if (current()) setWork(page);
          if (current() && selectedWorker) {
            const next = await api.worker(ctx, selectedWorker);
            if (current()) setDetail(next);
          }
        }
        if (current()) {loadedScope.current = scope; setError('');}
      } catch (e: unknown) {if (current()) setError(message(e));}
      finally {
        io.reading = false;
        if (current()) {setLoading(false); timer = setTimeout(() => {void poll();}, POLL_MS);}
      }
    }
    setLoading(true);
    void poll();
    return () => {cancelled = true; clearTimeout(timer);};
  }, [ctx, valid, scope, cursor, historyCursor, history, refresh, selectedWorker]);

  async function perform(key: string, action: (nonce: string) => Promise<unknown>): Promise<void> {
    if (io.acting || !valid() || loadedScope.current !== scope || loading || error || gateway !== 'open') return;
    if (intent.current?.key !== key) intent.current = {key, nonce: crypto.randomUUID()};
    io.acting = true; setActing(true);
    try {
      await action(intent.current.nonce);
      if (valid()) {setError(''); setRefresh(v => v + 1);}
    } catch (e: unknown) {if (valid()) setError(message(e));}
    finally {io.acting = false; if (alive.current) setActing(false);}
  }
  return {
    // Suppress old-profile data synchronously; effects run after paint.
    work: loadedScope.current === scope ? work : null, past: loadedScope.current === scope ? past : null,
    profile, scope, loading, acting, error, cursor, historyCursor, setCursor, setHistoryCursor,
    detail: loadedScope.current === scope && detail?.worker.session_id === selectedWorker ? detail : null,
    selectedWorker, selectWorker: (id: string | null) => {setDetail(null); setSelectedWorker(id);},
    disabled: acting || loading || Boolean(error) || gateway !== 'open',
    refresh: () => setRefresh(v => v + 1),
    act: (item: Incident, action: 'acknowledge' | 'request_recovery_review') => perform(`${scope}:${item.id}:${item.revision}:${action}`, nonce => api.act(ctx, item, action, nonce)),
    cancel: (task: HistoryTask) => perform(`${scope}:${task.id}:${task.revision}:cancel`, nonce => api.cancel(ctx, task, nonce)),
    open: (id: string) => perform(`${scope}:${id}:open`, () => host.openSession(id, {profile, intent: 'main'})),
  };
}
export type Controller = ReturnType<typeof useWatchdog>;
