import { createElement as h } from 'react';
import { createRoot } from 'react-dom/client';
import plugin from '../../desktop/plugin.js';
const root = createRoot(document.getElementById('root'));
window.watchdogHarness.requests = [];
const ctx = {
  registerMany(contributions) { root.render(contributions.find(c => c.area === 'routes').render()); },
  async rest(path, opts = {}) {
    window.watchdogHarness.requests.push({ path, ...opts });
    if (window.watchdogHarness.fail) throw new Error('Fixture: backend unavailable');
    if (window.watchdogHarness.empty && path.startsWith('/tasks?')) return {tasks: [], next_cursor: null};
    const response = await fetch('/api/plugins/hermes-watchdog' + path, {method: opts.method || 'GET', headers: {'Content-Type': 'application/json'}, body: opts.body ? JSON.stringify(opts.body) : undefined});
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || 'Request failed');
    return body;
  },
};
plugin.register(ctx);
