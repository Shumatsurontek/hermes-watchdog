/** Consumed public SDK subset, checked against Hermes b200f5b (2026-11-06).
 * Narrow adapter: no private core imports and unknown at the network boundary.
 */
declare module '@hermes/plugin-sdk' {
  import type {ReactNode} from 'react';
  interface Readable<T> { get(): T }
  export interface PluginContext {
    rest(path: string, options?: {method?: string; body?: unknown; timeoutMs?: number}): Promise<unknown>;
    registerMany(contributions: Array<{
      id: string; area: string; data: {path: string; label?: string; codicon?: string}; render?: () => ReactNode;
    }>): () => void;
  }
  export const host: {
    state: {profile: Readable<string>; gateway: Readable<string>; connectionId: Readable<string | null>};
    openSession(id: string, options: {profile: string; intent: 'main'}): Promise<unknown>;
  };
  export function useValue<T>(atom: Readable<T>): T;
  export function gatewayActivationEpoch(): number;
  export const ROUTES_AREA: string;
  export const SIDEBAR_NAV_AREA: string;
}
