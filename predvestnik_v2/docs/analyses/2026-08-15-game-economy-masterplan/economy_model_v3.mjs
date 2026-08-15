#!/usr/bin/env node

// Deterministic stress test for the owner-v3 economy. This is not a retention
// forecast: it checks arithmetic, no-hard-cap progression and long-horizon
// balance pressure under explicit synthetic behaviours.

const WEEKS = 520;
const ZARNIKI_TO_MORA = 150;
const UNIT_LEVEL_CAP_XP = Array.from({ length: 29 }, (_, index) =>
  Math.round(220 + 35 * index + 12 * Math.pow(index, 1.4)))
  .reduce((sum, value) => sum + value, 0);

const PERSONAS = [
  { id: 'returner', contracts: 10, winRate: .62, lossEligible: .72, spend: 900, prestigeShare: .02, zarniki: 0 },
  { id: 'casual', contracts: 21, winRate: .68, lossEligible: .78, spend: 1500, prestigeShare: .04, zarniki: 0 },
  { id: 'regular', contracts: 49, winRate: .76, lossEligible: .84, spend: 3200, prestigeShare: .08, zarniki: 0 },
  { id: 'enthusiast', contracts: 98, winRate: .84, lossEligible: .90, spend: 6200, prestigeShare: .12, zarniki: 0 },
  { id: 'hardcore', contracts: 175, winRate: .90, lossEligible: .94, spend: 9800, prestigeShare: .18, zarniki: 0 },
  { id: 'payer', contracts: 49, winRate: .76, lossEligible: .84, spend: 5200, prestigeShare: .12, zarniki: 20 },
  { id: 'hoarder', contracts: 98, winRate: .84, lossEligible: .90, spend: 400, prestigeShare: 0, zarniki: 0 },
  { id: 'hostile_bot', contracts: 700, winRate: .38, lossEligible: .10, spend: 0, prestigeShare: 0, zarniki: 0, acceptedShare: .035 },
];

function tieredValue(count, values) {
  const first = Math.min(count, 35);
  const second = Math.min(Math.max(0, count - 35), 70);
  const tail = Math.max(0, count - 105);
  return first * values[0] + second * values[1] + tail * values[2];
}

function weeklyReward(persona) {
  const accepted = persona.contracts * (persona.acceptedShare ?? 1);
  const wins = accepted * persona.winRate;
  const eligibleLosses = accepted * (1 - persona.winRate) * persona.lossEligible;
  const considered = wins + eligibleLosses;
  if (!considered) return { mora: 0, unitXp: 0, accepted: 0 };
  const winShare = wins / considered;
  const mora = tieredValue(considered, [
    35 + 65 * winShare,
    26 + 49 * winShare,
    18 + 32 * winShare,
  ]);
  const unitXp = tieredValue(considered, [
    45 + 55 * winShare,
    45 + 55 * winShare,
    (45 + 55 * winShare) * .60,
  ]);
  return { mora, unitXp, accepted: considered };
}

function simulate(persona) {
  let balance = 3520;
  let maxBalance = balance;
  let earned = 0;
  let converted = 0;
  let spent = 0;
  let unitXp = 0;
  let firstUnitCapWeek = null;
  for (let week = 1; week <= WEEKS; week += 1) {
    const reward = weeklyReward(persona);
    earned += reward.mora;
    unitXp += reward.unitXp;
    const exchange = persona.zarniki * ZARNIKI_TO_MORA;
    converted += exchange;
    balance += reward.mora + exchange;
    const availableForPrestige = Math.max(0, balance - 12000);
    const desired = persona.spend + availableForPrestige * persona.prestigeShare;
    const sink = Math.min(balance, desired);
    balance -= sink;
    spent += sink;
    maxBalance = Math.max(maxBalance, balance);
    if (firstUnitCapWeek === null && unitXp >= UNIT_LEVEL_CAP_XP) firstUnitCapWeek = week;
  }
  return {
    persona: persona.id,
    contracts_per_week: persona.contracts,
    accepted_results_per_week: Number(weeklyReward(persona).accepted.toFixed(1)),
    first_unit_cap_week: firstUnitCapWeek,
    earned_mora_10y: Math.round(earned),
    paid_exchange_mora_10y: Math.round(converted),
    spent_mora_10y: Math.round(spent),
    ending_mora: Math.round(balance),
    max_mora: Math.round(maxBalance),
  };
}

const rows = PERSONAS.map(simulate);
const violations = [];
for (const row of rows) {
  if (row.ending_mora < 0) violations.push(`${row.persona}: negative balance`);
  if (row.accepted_results_per_week > 0 && row.earned_mora_10y <= 0) {
    violations.push(`${row.persona}: valid play stopped progressing`);
  }
}
const bot = rows.find((row) => row.persona === 'hostile_bot');
const hardcore = rows.find((row) => row.persona === 'hardcore');
if (bot.earned_mora_10y >= hardcore.earned_mora_10y * .35) {
  violations.push('hostile bot captures too much of the honest hardcore faucet');
}

const output = {
  model: 'owner-v3-provisional-1',
  horizon_weeks: WEEKS,
  unit_level_cap_xp: UNIT_LEVEL_CAP_XP,
  reward_tiers: '1-35:100/35; 36-105:75/26; 106+:50/18; tail XP 60%',
  rows,
  violations,
};
console.log(JSON.stringify(output, null, 2));
if (violations.length) process.exitCode = 1;
