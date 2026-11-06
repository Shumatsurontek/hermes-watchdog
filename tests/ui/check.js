// Actual compiled UI + FastAPI. Host navigation is an explicitly labelled fixture.
const p = await browser.getPage('main');
const checks = [];
await p.goto('http://127.0.0.1:8766');
async function waitFor(text) {
  const found = await p.evaluate(async (needle) => {
    for (let attempt = 0; attempt < 160; attempt++) {
      if (document.body.innerText.toLowerCase().includes(needle.toLowerCase()) && !document.querySelector('.wd-watch')?.textContent.includes('Updating') && !document.querySelector('.wd-heading button')?.disabled) return true;
      await new Promise(resolve => setTimeout(resolve, 25));
    }
    return false;
  }, text);
  if (!found) throw new Error('UI did not reach: ' + text);
}
async function click(text) {
  await p.evaluate(async label => {
    for (let attempt = 0; attempt < 160; attempt++) {
      const button = [...document.querySelectorAll('button')].find(b => b.textContent === label);
      if (button && !button.disabled) {button.click(); return;}
      await new Promise(resolve => setTimeout(resolve, 25));
    }
    throw new Error('Unavailable button: ' + label);
  }, text);
}
await waitFor('Changelog & rollback');
const visible = await p.evaluate(() => document.body.innerText);
if (visible.includes('release-conversation') || visible.includes('release-ci')) throw new Error('Technical IDs dominate the default view');
if (!visible.includes('Returned with errors')) throw new Error('Completion incorrectly hides tool errors');
checks.push({name:'Readable task goals; IDs hidden; returned work retains error evidence',status:'passed'});
await click('Open conversation ↗');
await waitFor('Observing');
let opened = await p.evaluate(() => window.watchdogHarness.opened);
if (opened.id !== 'release-conversation' || opened.profile !== 'preview-fixtures') throw new Error('Wrong root/profile navigation');
await p.evaluate(async () => {
  for (let attempt = 0; attempt < 160; attempt++) {
    const button = [...document.querySelectorAll('.wd-worker')].find(row => row.textContent.includes('Changelog & rollback')).querySelector('.wd-worker-actions button');
    if (!button.disabled) {button.click(); return;}
    await new Promise(resolve => setTimeout(resolve, 25));
  }
  throw new Error('Result button stayed disabled');
});
await waitFor('Observing');
opened = await p.evaluate(() => window.watchdogHarness.opened);
if (opened.id !== 'release-notes') throw new Error('Wrong result navigation');
checks.push({name:'Conversation and result actions use native IDs and current profile',status:'passed'});
await click('Release readiness · CI & build');
await waitFor('retained events');
await click('Launcher history');
await waitFor('Compare Hermes plugin lifecycle');
await click('← Back to native work');
await waitFor('Changelog & rollback');
checks.push({name:'Worker evidence and legacy history survive mode changes',status:'passed'});
await p.evaluate(() => document.querySelector('.wd-more').open = true);
await click('Ask Hermes to recover');
await waitFor('Recovery review queued');
const posts = await p.evaluate(() => window.watchdogHarness.requests.filter(r => r.method === 'POST' && r.path.includes('/incidents/')));
if (posts.length !== 1 || posts[0].body.parent_session_id !== 'release-conversation') throw new Error('Recovery not scoped or not bounded');
checks.push({name:'Recovery queues once for its owning conversation, without pretending it finished',status:'passed'});
await p.evaluate(() => {window.watchdogHarness.empty = true; window.watchdogHarness.switchProfile('empty-profile');});
await waitFor('Delegate the work. Keep the thread.');
const stale = await p.evaluate(() => document.body.innerText.includes('Release readiness'));
if (stale) throw new Error('Previous profile leaked');
checks.push({name:'Profile change removes previous work and its actions',status:'passed'});
await p.evaluate(() => {window.watchdogHarness.empty = false; window.watchdogHarness.malformed = true; window.watchdogHarness.switchProfile('malformed-profile');});
await waitFor('incompatible response');
checks.push({name:'Malformed response fails runtime validation visibly',status:'passed'});
await p.evaluate(() => {window.watchdogHarness.malformed = false; window.watchdogHarness.fail = true; window.watchdogHarness.switchProfile('failed-profile');});
await waitFor('Fixture: backend unavailable');
checks.push({name:'Backend failure is not treated as an empty success',status:'passed'});
await p.evaluate(() => {window.watchdogHarness.fail = false; window.watchdogHarness.switchProfile('preview-fixtures');});
await waitFor('Changelog & rollback');
await p.setViewport({width:390,height:844});
const overflow = await p.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
if (overflow) throw new Error('Mobile viewport overflows horizontally');
checks.push({name:'Narrow layout fits a 390px viewport',status:'passed'});
await p.setViewport({width:1440,height:1024});
const errors = await p.evaluate(() => window.watchdogErrors || []);
if (errors.length) throw new Error(JSON.stringify(errors));
return checks;
