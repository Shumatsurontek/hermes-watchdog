import type {PluginContext} from '@hermes/plugin-sdk';
import type {ValidateFunction} from 'ajv';
import {validateWorkPage, validateWorkerDetail, validateHistoryPage, validateActionResult, validateCancelResult} from '../generated/validators.js';
import type {Incident, Worker, Mission} from '../generated/WorkPage';
export type {Incident, Worker, Mission};
export type {HistoryTask} from '../generated/HistoryPage';
export type {WorkerDetail} from '../generated/WorkerDetail';

const TIMEOUT_MS = 12_000;
async function read<T>(ctx: PluginContext, path: string, validate: ValidateFunction<T>, body?: unknown): Promise<T> {
  const data: unknown = await ctx.rest(path, body === undefined ? {timeoutMs: TIMEOUT_MS} : {method: 'POST', body, timeoutMs: TIMEOUT_MS});
  if (!validate(data)) throw new Error('Watchdog received an incompatible response. Reload the plugin before acting.');
  return data;
}
export const api = {
  work: (ctx: PluginContext, cursor: number) => read(ctx, `/work?cursor=${cursor}`, validateWorkPage),
  worker: (ctx: PluginContext, id: string) => read(ctx, `/work/runs/${encodeURIComponent(id)}`, validateWorkerDetail),
  history: (ctx: PluginContext, cursor: string) => read(ctx, `/history?cursor=${encodeURIComponent(cursor)}`, validateHistoryPage),
  act: (ctx: PluginContext, item: Incident, action: 'acknowledge' | 'request_recovery_review', nonce: string) => read(ctx, `/incidents/${encodeURIComponent(item.id)}/actions`, validateActionResult, {
    action, parent_session_id: item.root_id, revision: item.revision, idempotency_key: nonce,
  }),
  cancel: (ctx: PluginContext, task: {id: string; revision: number; session_key: string}, nonce: string) => read(ctx, `/tasks/${encodeURIComponent(task.id)}/actions`, validateCancelResult, {
    action: 'cancel', session_key: task.session_key, revision: task.revision, idempotency_key: nonce,
  }),
};
export function message(error: unknown): string { return error instanceof Error ? error.message : 'Watchdog could not complete the request.'; }
export function workerTitle(worker: Worker, index = 0): string {
  return worker.label || ({read_file: 'Read project files', terminal: 'Run project checks', web_search: 'Research sources', web_extract: 'Read sources'}[worker.last_tool] ?? (worker.last_tool ? `Work using ${worker.last_tool}` : `Worker ${index + 1}`));
}
export function workerState(worker: Worker): {label: string; tone: 'neutral' | 'accent' | 'warn'} {
  if (worker.waiting) return {label: 'Needs your input', tone: 'warn'};
  if (worker.state === 'returned') return worker.observed_errors ? {label: 'Returned with errors', tone: 'warn'} : {label: 'Result returned', tone: 'neutral'};
  if (worker.state === 'active') return {label: 'Working', tone: 'accent'};
  if (worker.state === 'failed') return {label: 'Failed', tone: 'warn'};
  if (worker.state === 'interrupted') return {label: 'Interrupted', tone: 'warn'};
  return {label: 'State unknown', tone: 'warn'};
}
export function missionTitle(mission: Mission): string {
  const prefixes = mission.workers.map(w => w.label.split(' · '));
  const first = prefixes[0];
  return first && first.length > 1 && first[0] && prefixes.every(p => p.length > 1 && p[0] === first[0]) ? first[0] : 'Delegated work';
}
