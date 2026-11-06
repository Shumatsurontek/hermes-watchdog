// Run with `bb browser-automation run ... --script-file ... --script-host ...`.
// Uses the explicitly labelled SDK fixture, never a native Desktop claim.
const p = await browser.getPage('main');
const checks = [];
async function click(text) {
  await p.evaluate((label) => {
    const button = [...document.querySelectorAll('button')].find(b => b.textContent === label);
    if (!button || button.disabled) throw new Error('Unavailable button: ' + label);
    button.click();
  }, text);
}
async function waitFor(kind) {
  const found = await p.evaluate(async (kind) => {
    for (let attempt = 0; attempt < 80; attempt++) {
      const body = document.body.textContent;
      const detail = document.querySelector('[aria-label="Native work details"]');
      const loaded = !body.includes('Refreshing…');
      if (loaded && (kind === 'detail' ? detail : kind === 'returned' ? body.includes('release-notes') : kind === 'related' ? body.includes('Matching failures across workers') : kind === 'empty' ? body.includes('No related failure groups observed.') : kind === 'error' ? document.querySelector('[role="alert"]') : kind === 'legacy' ? body.includes('Execution slots reserved') : kind === 'loaded' ? document.querySelector('main') : false)) return true;
      await new Promise(resolve => setTimeout(resolve, 25));
    }
    return false;
  }, kind);
  if (!found) throw new Error('UI did not reach: ' + kind);
}
async function selectFirst() {
  await p.evaluate(() => document.querySelector('[aria-label="Inbox items"] button').click());
  await waitFor('detail');
}
await click('Related failures');
await waitFor('related');
await selectFirst();
await click('Open conversation');
const opened = await p.evaluate(() => window.watchdogHarness.opened);
if (opened.id !== 'release-conversation' || opened.profile !== 'preview-fixtures') throw new Error('Wrong conversation route');
checks.push({name: 'Open conversation uses the stored root and current profile', status: 'passed'});
await click('Returned results');
await waitFor('returned');
await selectFirst();
await click('Open worker');
const worker = await p.evaluate(() => window.watchdogHarness.opened.id);
if (worker !== 'release-notes') throw new Error('Wrong worker route');
await click('Related failures');
await waitFor('related');
await selectFirst();
checks.push({name: 'Switch between incident and result details without a render crash', status: 'passed'});
await p.evaluate(() => {window.watchdogHarness.empty = true; window.watchdogHarness.switchProfile('empty-profile');});
await waitFor('empty');
const leaked = await p.evaluate(() => Boolean(document.querySelector('[aria-label="Native work details"]')));
if (leaked) throw new Error('Old detail survived profile switch');
checks.push({name: 'Profile switch removes old details and actions', status: 'passed'});
await p.evaluate(() => {window.watchdogHarness.fail = true;});
await click('Needs you');
await waitFor('error');
checks.push({name: 'Backend failure is visible without blanking the page', status: 'passed'});
await p.evaluate(() => {window.watchdogHarness.empty = false; window.watchdogHarness.fail = false; window.watchdogHarness.switchProfile('preview-fixtures');});
await click('Related failures');
await waitFor('related');
await click('Legacy launcher history');
await waitFor('legacy');
checks.push({name: 'Legacy history remains accessible', status: 'passed'});
await click('Native recovery inbox');
await waitFor('loaded');
await click('Related failures');
await waitFor('related');
await selectFirst();
const errors = await p.evaluate(() => window.watchdogErrors || []);
if (errors.length) throw new Error(JSON.stringify(errors));
return checks;
