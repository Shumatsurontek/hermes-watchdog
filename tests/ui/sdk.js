import { useSyncExternalStore } from 'react';
let epoch = 1;
function atom(value) {
  const listeners = new Set();
  return { get: () => value, subscribe: (fn) => { listeners.add(fn); return () => listeners.delete(fn); }, set: (next) => { value = next; for (const fn of listeners) fn(); } };
}
export const host = { state: { profile: atom('preview-fixtures'), gateway: atom('open') },
  async openSession(id, options) {window.watchdogHarness.opened = {id, ...options};} };
export const useValue = (state) => useSyncExternalStore(state.subscribe, state.get);
export const gatewayActivationEpoch = () => epoch;
export const ROUTES_AREA = 'routes';
export const SIDEBAR_NAV_AREA = 'sidebar';
window.watchdogHarness = { switchProfile(value) { epoch++; host.state.profile.set(value); }, host };
