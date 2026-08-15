#!/usr/bin/env node

// Structural checks for the paper design package. This does not validate player
// behavior; it prevents incomplete event cards and stale production facts from
// silently entering the approval packet.

import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const read = (name) => readFileSync(join(root, name), 'utf8');
const failures = [];
const check = (condition, message) => {
  if (!condition) failures.push(message);
};

const snapshot = read('PRODUCTION_SNAPSHOT.md');
check(snapshot.includes('183'), 'Production snapshot must use the fresh 183-account baseline.');
check(snapshot.includes('2026-08-15 09:48:14 UTC'), 'Production snapshot timestamp is missing or stale.');
check(snapshot.includes('REPEATABLE READ READ ONLY'), 'Production query mode must be documented.');

const catalog = read('EVENT_ECONOMY_CATALOG.md');
const eventMatches = [...catalog.matchAll(/^### (E\d{2})\. ([^\n]+)\n\n([\s\S]*?)(?=^### E\d{2}\.|^---$|^## )/gm)];
const requiredFields = [
  'Цель',
  'Вход',
  'Решение',
  'Создаёт',
  'Потребляет',
  'Передача',
  'Предел/catch-up',
  'Anti-abuse',
  'Телеметрия',
  'Конец/миграция',
];

check(eventMatches.length === 40, `Expected 40 event contracts, found ${eventMatches.length}.`);
eventMatches.forEach((match, index) => {
  const expectedId = `E${String(index + 1).padStart(2, '0')}`;
  check(match[1] === expectedId, `Expected ${expectedId}, found ${match[1]}.`);
  const labels = [...match[3].matchAll(/^- \*\*([^*]+):\*\*/gm)].map((item) => item[1]);
  check(labels.length === requiredFields.length, `${match[1]} has ${labels.length} fields, expected 10.`);
  requiredFields.forEach((field) => {
    check(labels.filter((label) => label === field).length === 1, `${match[1]} must contain exactly one “${field}” field.`);
  });
});

const modelPath = join(root, 'economy_model.mjs');
const model = JSON.parse(execFileSync(process.execPath, [modelPath], { encoding: 'utf8' }));
check(model.model_version === 'constitution-v2', 'Stress model/report contract must use constitution-v2.');
check(model.horizon_weeks === 520, 'Stress model must declare 520 weekly periods.');
check(model.horizon_days === 3640, 'Stress model horizon must remain the declared 520 weekly periods (3,640 modeled days).');
check(model.invariants?.weekly_repeatable_mora_cap === 2400, 'Weekly Mora reserve changed unexpectedly.');
check(model.invariants?.payment_to_combat_power === false, 'Paid-to-power invariant must remain false.');
check(model.invariants?.payment_to_gameplay_currency === false, 'Payment-to-gameplay-currency invariant must remain false.');
const main = model.scenarios.find((row) => row.id === 'main');
const payer = model.scenarios.find((row) => row.id === 'payer');
check(Boolean(main && payer), 'Main and payer scenarios are required.');
check(main?.mora_p50_10y === payer?.mora_p50_10y, 'Payer scenario has an economic advantage.');
check(model.scenarios.every((row) => row.mora_p50_10y >= 0), 'Stress model produced a negative balance.');
check(!read('economy_model.mjs').includes('earlyMilestonesRemaining'), 'Unpublished 1,000-Mora early milestone grant returned to the model.');

const optionalRequiredAtDelivery = [
  'GAME_ECONOMY_MASTER_SPEC.md',
  'VALIDATION_AND_SELF_CRITIQUE.md',
  'artifact.json',
  'report.html',
];
optionalRequiredAtDelivery.forEach((name) => {
  const path = join(root, name);
  check(existsSync(path) && statSync(path).size > 0, `${name} is missing from the delivery package.`);
});

if (existsSync(join(root, 'artifact.json'))) {
  const artifact = JSON.parse(read('artifact.json'));
  const artifactRaw = read('artifact.json');
  check(artifact.surface === 'report', 'artifact.json must use the report surface.');
  check(Boolean(artifact.manifest?.title), 'artifact.json is missing a manifest title.');
  check(
    Array.isArray(artifact.snapshot?.datasets) || typeof artifact.snapshot?.datasets === 'object',
    'artifact.json is missing snapshot datasets.',
  );
  const modelBlock = artifact.manifest?.blocks?.find((block) => block.id === 'model_results')?.body ?? '';
  const spacedInteger = (value) => new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 })
    .format(value)
    .replace(/[\u00a0\u202f]/g, ' ');
  model.scenarios.forEach((scenario) => {
    check(
      modelBlock.includes(spacedInteger(scenario.mora_p50_10y)),
      `Report is stale for ${scenario.id}: missing Mora P50 ${scenario.mora_p50_10y}.`,
    );
    check(
      modelBlock.includes(scenario.sink_source_ratio_p50.toFixed(3).replace('.', ','))
        || modelBlock.includes(`${(scenario.sink_source_ratio_p50 * 100).toFixed(1).replace('.', ',')}%`),
      `Report is stale for ${scenario.id}: missing sink/source ${scenario.sink_source_ratio_p50}.`,
    );
  });
  check(
    artifactRaw.includes('50/145/285') || artifactRaw.includes('50 / 145 / 285'),
    'Report must use the corrected 2/6/12h expedition rewards.',
  );
  check(!artifactRaw.includes('50/145/280'), 'Stale expedition reward 280 remains in report artifact.');
  check(!artifactRaw.includes('3 650'), 'Stale 3,650-day model horizon remains in report artifact.');
  check(
    artifactRaw.includes('Season 1–3')
      || artifactRaw.includes('Season 1, 2 и 3')
      || artifactRaw.includes('сезоны 1, 2 и 3'),
    'Three-season content runway is missing.',
  );
  check(artifactRaw.includes('72-час'), 'Chosen legacy crypto settlement is missing.');
  check(
    artifactRaw.includes('один `operation_id`')
      || artifactRaw.includes('один terminal action')
      || artifactRaw.includes('один идентификатор операции'),
    'Atomic one-action/one-Mora rule is missing.',
  );
  check(
    artifactRaw.includes('недополученный полный блок из 35') && artifactRaw.includes('остаток от 18'),
    'Broken-pity settlement is missing or over-compensates already satisfied guarantee blocks.',
  );
  check(artifactRaw.includes('0 / 1 / 2') && artifactRaw.includes('витрин'), 'Exact VIP replacement is missing.');
  check(artifactRaw.includes('45 осмысленных игровых дней'), 'Ten pet roles must be guaranteed within 45 meaningful days.');
  check(artifactRaw.includes('верхних 10% покупателей') && artifactRaw.includes('≤45%'), 'Market concentration gates are missing.');
  check(
    !artifact.manifest.blocks.some((block) => block.type === 'markdown' && /(^|\n)\|[^\n]+\|/.test(block.body ?? '')),
    'Owner report contains Markdown tables that break the no-JS fallback.',
  );

  const reportPath = join(root, 'report.html');
  if (existsSync(reportPath)) {
    const reportHtml = read('report.html');
    check(
      statSync(reportPath).mtimeMs >= statSync(join(root, 'artifact.json')).mtimeMs,
      'report.html is older than artifact.json; repackage the portable report.',
    );
    check(reportHtml.includes('<html lang="ru"'), 'Portable report must declare Russian document language.');
    const approvalStart = reportHtml.indexOf('data-artifact-block-id="approval_matrix"');
    const approvalEnd = reportHtml.indexOf('data-artifact-block-id="recommended_next_steps"', approvalStart);
    const approvalHtml = approvalStart >= 0 && approvalEnd > approvalStart
      ? reportHtml.slice(approvalStart, approvalEnd)
      : '';
    check((approvalHtml.match(/<li>/g) ?? []).length === 18, 'Rendered owner approval checklist must contain exactly 18 decisions.');
    check(approvalHtml.includes('1 200 Моры'), 'Rendered Mora carry value was split or lost.');
  }
}

if (failures.length) {
  process.stderr.write(`Masterplan validation failed (${failures.length}):\n- ${failures.join('\n- ')}\n`);
  process.exitCode = 1;
} else {
  process.stdout.write(`Masterplan validation passed: ${eventMatches.length} events, ${model.scenarios.length} stress personas, fresh 183-account baseline.\n`);
}
