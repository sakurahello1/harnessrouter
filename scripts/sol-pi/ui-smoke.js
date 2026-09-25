// Run with playwright-cli run-code --filename scripts/sol-pi/ui-smoke.js after
// signing into a local UI build. API fixtures are local to this browser session.
async (page) => {
  await page.unrouteAll({ behavior: 'ignoreErrors' });
  let agent = { id: 'sol-pi-ui-test', name: 'SoL-Pi experiment', base: 'sol-pi', baseLabel: 'SoL-Pi',
    defaultModel: 'gpt-5.4', systemPrompt: '', skills: [], mcpServers: [], plugins: [], disabledTools: [], solPi: {} };
  let saved;
  await page.route('**/api/harness/**', async route => {
    const path = route.request().url().split('?')[0];
    let body = {};
    if (path.endsWith('/harnesses/sol-pi-ui-test')) {
      if (route.request().method() === 'PUT') {
        saved = route.request().postDataJSON();
        agent = { ...agent, solPi: saved.sol_pi };
      }
      body = agent;
    } else if (path.endsWith('/harnesses')) body = { harnesses: [agent] };
    else if (path.endsWith('/workspaces')) body = { workspaces: [{id: 'default', name: 'Local test'}], default_workspace_id: 'default' };
    else if (path.endsWith('/bases')) body = { bases: [{id: 'sol-pi', label: 'SoL-Pi', tools: [], builtinSkills: []}], runtimeDefaults: { maxStep: 100, timeoutSeconds: 600 } };
    else if (path.endsWith('/traces')) body = { sessions: [], cursor: '' };
    await route.fulfill({ json: body });
  });
  await page.goto('http://127.0.0.1:3187/harnesses?h=sol-pi-ui-test&view=settings');
  const fusion = page.getByRole('button', { name: 'Action Fusion', exact: true });
  await fusion.waitFor();
  if (await fusion.getAttribute('aria-pressed') !== 'true') throw new Error('Default switch not enabled');
  await fusion.click();
  await page.getByLabel('Cache write/read price ratio').fill('0');
  await page.getByLabel('Reducer model (optional)').fill('small-model');
  await page.getByRole('button', { name: 'Save Changes', exact: true }).click();
  await page.waitForURL('**/harnesses?h=sol-pi-ui-test');
  if (saved?.base !== 'sol-pi' || saved?.sol_pi?.actionFusion !== false || saved?.sol_pi?.cacheWriteReadRatio !== 0 || saved?.sol_pi?.reducerModel !== 'small-model') {
    throw new Error('SoL-Pi config did not survive form serialization');
  }
  await page.goto('http://127.0.0.1:3187/harnesses?h=sol-pi-ui-test&view=settings');
  await fusion.waitFor();
  if (await fusion.getAttribute('aria-pressed') !== 'false') throw new Error('Saved switch did not reload');
  await page.getByRole('heading', { name: 'SoL-Pi mechanisms' }).scrollIntoViewIfNeeded();
  console.log('SoL-Pi UI: independent base, defaults, toggle, zero ratio, reducer model, save and reload passed.');
  await page.goto('http://127.0.0.1:3187/harnesses?h=sol-pi&view=settings');
  await page.getByRole('heading', { name: 'SoL-Pi mechanisms' }).waitFor();
  if (!(await fusion.isDisabled())) throw new Error('Built-in mechanisms must be read-only');
  if (await fusion.getAttribute('aria-pressed') !== 'true') throw new Error('Custom toggle leaked into built-in defaults');
  await page.getByRole('button', { name: 'Fork and Customize' }).waitFor();
}
