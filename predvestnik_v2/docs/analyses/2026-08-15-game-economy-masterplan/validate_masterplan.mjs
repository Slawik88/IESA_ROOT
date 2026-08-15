#!/usr/bin/env node

// Structural and consistency checks for the current owner-v3 paper package.
// This proves reproducibility and internal agreement, not player enjoyment.

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

const requiredFiles = [
  'START_HERE.md',
  'PRODUCTION_SNAPSHOT.md',
  'GAME_ECONOMY_OWNER_V3.md',
  'OWNER_V3_SELF_CRITIQUE.md',
  'GAME_ECONOMY_MASTER_SPEC.md',
  'EVENT_ECONOMY_CATALOG.md',
  'VALIDATION_AND_SELF_CRITIQUE.md',
  'economy_model_v3.mjs',
  'artifact.json',
  'report.html',
];
for (const name of requiredFiles) {
  const target = join(root, name);
  check(existsSync(target) && statSync(target).size > 0, `${name} is missing or empty.`);
}

const snapshot = read('PRODUCTION_SNAPSHOT.md');
check(snapshot.includes('183'), 'Production snapshot must retain the 183-account research baseline.');
check(snapshot.includes('2026-08-15 09:48:14 UTC'), 'Production snapshot timestamp is missing or stale.');
check(snapshot.includes('REPEATABLE READ READ ONLY'), 'Production query mode must remain documented.');

// The 40-event v2 catalog remains a complete research inventory. V3 warnings
// prevent its rejected caps or monetization rules from becoming implementation canon.
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
check(eventMatches.length === 40, `Expected 40 historical event contracts, found ${eventMatches.length}.`);
eventMatches.forEach((match, index) => {
  const expectedId = `E${String(index + 1).padStart(2, '0')}`;
  check(match[1] === expectedId, `Expected ${expectedId}, found ${match[1]}.`);
  const labels = [...match[3].matchAll(/^- \*\*([^*]+):\*\*/gm)].map((item) => item[1]);
  requiredFields.forEach((field) => {
    check(labels.filter((label) => label === field).length === 1, `${match[1]} must contain exactly one “${field}” field.`);
  });
});
check(catalog.includes('v3'), 'Historical event catalog must point to the owner-v3 override.');

const v3 = read('GAME_ECONOMY_OWNER_V3.md');
const v3Rules = [
  '1 Зарник = 150 Моры',
  'необратимый обмен Зарники → Мора',
  'Новый положительный баланс Зарников появляется только из подтверждённой покупки за Telegram Stars',
  '100 Моры',
  '75 Моры',
  '50 Моры',
  '36 096 XP',
  'вся новая косметика',
  'цену только в Зарниках',
  'Аукцион',
  'Биржа',
  '50 дней',
  '6 300 XP',
  '50 000 синтетических аккаунтов',
  'квитанц',
];
for (const rule of v3Rules) check(v3.includes(rule), `Owner-v3 rule is missing: ${rule}`);
check(!v3.includes('ЗАРНИКИ МОЖНО'), 'Raw owner comment leaked into the canonical v3 specification.');
check(!v3.includes('промо-операции'), 'V3 must not mint positive Zarniki from promotions.');

for (const historicalName of [
  'GAME_ECONOMY_MASTER_SPEC.md',
  'EVENT_ECONOMY_CATALOG.md',
  'VALIDATION_AND_SELF_CRITIQUE.md',
]) {
  const historical = read(historicalName);
  check(
    historical.includes('v3') && historical.includes('GAME_ECONOMY_OWNER_V3.md'),
    `${historicalName} must explicitly defer conflicting decisions to owner v3.`,
  );
}

const modelPath = join(root, 'economy_model_v3.mjs');
const firstRun = execFileSync(process.execPath, [modelPath], { encoding: 'utf8' });
const secondRun = execFileSync(process.execPath, [modelPath], { encoding: 'utf8' });
check(firstRun === secondRun, 'Owner-v3 stress model is not deterministic.');
const model = JSON.parse(firstRun);
check(model.model === 'owner-v3-provisional-1', 'Stress model must use owner-v3-provisional-1.');
check(model.horizon_weeks === 520, 'Stress model must cover 520 weeks.');
check(model.unit_level_cap_xp === 36096, 'Unit level cap must remain 36,096 XP.');
check(model.rows?.length === 8, `Expected 8 model personas, found ${model.rows?.length ?? 0}.`);
check(Array.isArray(model.violations) && model.violations.length === 0, 'Stress model reports invariant violations.');
check(model.rows.every((row) => row.ending_mora >= 0), 'Stress model produced a negative ending balance.');
const hostile = model.rows.find((row) => row.persona === 'hostile_bot');
check(
  hostile && hostile.accepted_results_per_week / hostile.contracts_per_week < 0.02,
  'Hostile automation acceptance exceeds the 2% stress threshold.',
);
const hoarder = model.rows.find((row) => row.persona === 'hoarder');
check(hoarder?.ending_mora > 3_000_000, 'Hoarder risk signal disappeared; review model or self-critique.');
check(
  read('OWNER_V3_SELF_CRITIQUE.md').includes('3,6 млн Моры'),
  'Self-critique must disclose the modeled long-term hoarder balance.',
);

const artifact = JSON.parse(read('artifact.json'));
const artifactRaw = read('artifact.json');
check(artifact.surface === 'report', 'artifact.json must use the report surface.');
check(artifact.manifest?.title === 'Экономика Предвестника v3: решения владельца', 'Artifact title is stale.');
check(artifact.manifest?.blocks?.length === 21, `Expected 21 report blocks, found ${artifact.manifest?.blocks?.length ?? 0}.`);
for (const blockId of ['executive_summary', 'owner_decisions', 'model_table', 'blocking_gates', 'caveats']) {
  check(artifact.manifest.blocks.some((block) => block.id === blockId), `Report block ${blockId} is missing.`);
}
check(
  !artifact.manifest.blocks.some((block) => block.type === 'markdown' && /(^|\n)\|[^\n]+\|/.test(block.body ?? '')),
  'Owner report contains Markdown tables that break the no-JS fallback.',
);
for (const sourceId of ['production_snapshot', 'owner_v3', 'owner_v3_self_critique', 'economy_model']) {
  check(artifact.sources.some((source) => source.id === sourceId), `Artifact source ${sourceId} is missing.`);
}
const modelTable = artifact.manifest.tables.find((table) => table.id === 'v3_model');
check(Boolean(modelTable), 'V3 model native table is missing.');
const artifactModelRows = artifact.snapshot?.datasets?.v3_model;
check(Array.isArray(artifactModelRows) && artifactModelRows.length === model.rows.length, 'Artifact model rows are missing or stale.');
model.rows.forEach((row, index) => {
  const rendered = artifactModelRows?.[index];
  for (const field of ['contracts_per_week', 'first_unit_cap_week', 'earned_mora_10y', 'paid_exchange_mora_10y', 'ending_mora']) {
    check(rendered?.[field] === row[field], `Artifact model field ${field} is stale for ${row.persona}.`);
  }
});
check(artifactRaw.includes('Что пока запрещает включать реальные награды'), 'P0 blocking gates are missing from the owner report.');
check(!artifactRaw.includes('## Executive Summary'), 'English executive heading remains in the owner report.');

const reportPath = join(root, 'report.html');
const reportHtml = read('report.html');
check(statSync(reportPath).mtimeMs >= statSync(join(root, 'artifact.json')).mtimeMs, 'report.html is older than artifact.json.');
check(reportHtml.includes('<html lang="ru"'), 'Portable report must declare Russian document language.');
check(reportHtml.includes('Экономика Предвестника v3: решения владельца'), 'Portable report title is stale.');
check(reportHtml.includes('Что пока запрещает включать реальные награды'), 'Portable report omitted P0 blocking gates.');

const staticReportPath = join(root, '../../../FastAPI/static/economy-masterplan-report.html');
if (existsSync(staticReportPath)) {
  check(readFileSync(staticReportPath, 'utf8') === reportHtml, 'Dev-server report copy differs from the canonical report.html.');
}

if (failures.length) {
  process.stderr.write(`Owner-v3 masterplan validation failed (${failures.length}):\n- ${failures.join('\n- ')}\n`);
  process.exitCode = 1;
} else {
  process.stdout.write(`Owner-v3 masterplan validation passed: ${eventMatches.length} historical events, ${model.rows.length} stress personas, 21 report blocks, fresh 183-account baseline.\n`);
}
