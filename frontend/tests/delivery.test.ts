import test from 'node:test';
import assert from 'node:assert/strict';
import { requestJson, ApiError } from '../src/httpClient.ts';
import { normalizeTaskResponse, pollTaskUntilTerminal } from '../src/taskPolling.ts';
import { displayAgentTools } from '../src/agentTools.ts';
import { buildAnalysisReport, rankCandidates } from '../src/candidateRanking.ts';
import { displayTaskStage } from '../src/modelDisplay.ts';

test('production parser_mode survives task normalization without the legacy agent flag', () => {
  const task = normalizeTaskResponse({ task_id: 'production-fixture', status: 'completed', parser_mode: 'rules', candidates: [] });
  assert.equal(task.parser_mode, 'rules');
  assert.equal(normalizeTaskResponse({ task_id: task.task_id, status: 'completed' }, task).parser_mode, 'rules');
  assert.equal(normalizeTaskResponse({ task_id: 'unknown', status: 'completed', parser_mode: 'invalid' }).parser_mode, undefined);
});

test('production parsed_plan is shown as the Agent Plan without inventing optional constraints', () => {
  const task = normalizeTaskResponse({
    task_id: 'production-fixture', status: 'completed', parser_mode: 'rules', target: 'ESR1',
    parsed_plan: { parser: 'rules', target: 'ESR1', num_samples: 1, run_docking: true, raw_prompt: 'ESR1' },
    candidates: [],
  });
  assert.deepEqual({ target: task.agent_plan?.target, count: task.agent_plan?.num_samples, docking: task.agent_plan?.run_docking, parser: task.agent_plan?.parser },
    { target: 'ESR1', count: 1, docking: true, parser: 'rules' });
  assert.equal(task.agent_plan?.qed_threshold, null);
  assert.equal(task.agent_plan?.sa_threshold, null);
  assert.equal(normalizeTaskResponse({ task_id: task.task_id, status: 'completed' }, task).agent_plan?.run_docking, true);
});

test('agent_plan takes precedence over parsed_plan when both are present', () => {
  const task = normalizeTaskResponse({ task_id: 'plan-fixture', status: 'completed',
    agent_plan: { parser: 'llm', target: 'JAK1', num_samples: 2, run_docking: false },
    parsed_plan: { parser: 'rules', target: 'ESR1', num_samples: 1, run_docking: true }, candidates: [] });
  assert.equal(task.agent_plan?.target, 'JAK1');
  assert.equal(task.agent_plan?.run_docking, false);
});

test('legacy model tool name and progress label remain compatible with AP-MolDiff display', () => {
  const tools = displayAgentTools([{ name: 'DLPS-E2PO Generation', status: 'completed' }]);
  assert.equal(tools[1].name, 'AP-MolDiff');
  assert.equal(tools[1].status, 'completed');
  assert.equal(displayTaskStage('DLPS-E2PO inference'), 'AP-MolDiff inference');
});

test('URL and JSON params preserve false and zero', async () => {
  const body = { target: 'ESR1', num_samples: 1, run_docking: false, qed_threshold: 0 };
  const fake = (async (url, options) => {
    assert.equal(url, 'https://example.test/api/generate'); assert.equal(options?.method, 'POST');
    assert.deepEqual(JSON.parse(String(options?.body)), body);
    return Response.json({ task_id: 'test-id' });
  }) as typeof fetch;
  assert.deepEqual(await requestJson('https://example.test/', '/api/generate', { method: 'POST', body: JSON.stringify(body) }, 100, fake), { task_id: 'test-id' });
});
for (const status of [404, 405, 422, 429, 503]) test(`HTTP ${status} preserves structured detail`, async () => {
  await assert.rejects(requestJson('https://example.test', '/api/tasks/test', {}, 100, (async () => Response.json({ detail: [{ msg: 'bad input' }] }, { status })) as typeof fetch), e => e instanceof ApiError && e.status === status && e.message.includes('bad input'));
});
test('timeout and external abort are distinct', async () => {
  const fake = (async (_url, options) => new Promise((_resolve, reject) => options?.signal?.addEventListener('abort', () => reject(new DOMException('cancel', 'AbortError'))))) as typeof fetch;
  await assert.rejects(requestJson('https://example.test', '/api/health', {}, 5, fake), /请求超时/);
  const controller = new AbortController();
  const pending = requestJson('https://example.test', '/api/health', { signal: controller.signal }, 100, fake);
  controller.abort(); await assert.rejects(pending, { name: 'AbortError' });
});
test('network failure keeps task status unknown', async () => {
  await assert.rejects(requestJson('https://example.test', '/api/health', {}, 100, (async () => { throw new TypeError('network'); }) as typeof fetch), /状态未知/);
});
test('failed partial preserves provenance, zero metrics and invalid candidates', () => {
  const task = normalizeTaskResponse({ task_id: 'test-id', status: 'FAILED', result_status: 'partial', data_origin: 'synthetic_test', error: 'Vina failed', candidates: [
    { smiles: 'invalid', valid: false, vina: -99 }, { smiles: 'CCO', valid: true, qed: 0, sa: 0, molwt: 0, logp: 0, lipinski: false, vina: null },
  ] });
  assert.equal(task.status, 'failed'); assert.equal(task.result_status, 'partial'); assert.equal(task.data_origin, 'synthetic_test');
  assert.equal(task.candidates[1].qed, 0);
  const ranked = rankCandidates(task.candidates); assert.equal(ranked[0].smiles, 'CCO');
  const report = buildAnalysisReport(task, ranked); assert.equal(report?.partial, true); assert.equal(report?.generated, null);
  assert.equal(buildAnalysisReport({ ...task, candidates: [] }, []), null);
});
test('six tool states distinguish absent data from pending', () => {
  for (const status of ['pending', 'running', 'completed', 'failed', 'skipped']) assert.equal(displayAgentTools([{ name: 'ESM-2', status }])[0].status, status);
  assert.equal(displayAgentTools()[0].status, 'unknown');
});
test('404 stops querying immediately', async () => {
  let count = 0;
  await assert.rejects(pollTaskUntilTerminal('test-id', { fetchTask: async () => { count++; throw new ApiError(404, 'not found'); }, onUpdate: () => assert.fail() }), /not found/);
  assert.equal(count, 1);
});
test('hanging fetch cannot exceed total budget', async () => {
  const start = Date.now();
  await assert.rejects(pollTaskUntilTerminal('test-id', { timeoutMs: 15, intervalMs: 1, fetchTask: () => new Promise(() => {}), onUpdate: () => assert.fail() }), /超过 2 分钟/);
  assert.ok(Date.now() - start < 1000);
});
test('unmount cancellation stops polling', async () => {
  const controller = new AbortController();
  const pending = pollTaskUntilTerminal('test-id', { signal: controller.signal, fetchTask: () => new Promise(() => {}), onUpdate: () => assert.fail() });
  controller.abort(); await assert.rejects(pending, { name: 'AbortError' });
});
