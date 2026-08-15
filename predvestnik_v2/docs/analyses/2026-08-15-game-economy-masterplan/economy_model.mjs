#!/usr/bin/env node

// Deterministic stress model for the proposed economy constitution.
// It is a calibration aid, not a forecast of player behavior.

// The simulation is weekly. 520 weeks are exactly 3,640 modeled days, not
// 3,650; report the actual horizon rather than implying daily precision.
const WEEKS_10Y = 520;
const MODELED_DAYS = WEEKS_10Y * 7;
const WEEKLY_MORA_RESERVE = 2400;
const OLD_MORA_MAX = 315568.25;
const RUNS = 1000;

const PERSONAS = [
  { id: 'short', label: 'Короткий', activeChance: 0.62, weeklyEarn: 850, spendRatio: 0.92, start: 0, newAccount: true },
  { id: 'main', label: 'Основной', activeChance: 0.86, weeklyEarn: 2050, spendRatio: 0.94, start: 0, newAccount: true },
  { id: 'enthusiast', label: 'Увлечённый', activeChance: 0.97, weeklyEarn: 2400, spendRatio: 0.98, start: 0, newAccount: true },
  { id: 'returner', label: 'Возвращающийся', activeChance: 0.48, weeklyEarn: 1150, spendRatio: 0.90, start: 3520, newAccount: false },
  { id: 'veteran', label: 'Ветеран P100', activeChance: 0.90, weeklyEarn: 2300, spendRatio: 1.06, start: OLD_MORA_MAX, newAccount: false },
  { id: 'payer', label: 'Плательщик без силы', activeChance: 0.86, weeklyEarn: 2050, spendRatio: 0.94, start: 0, newAccount: true },
  { id: 'hoarder', label: 'Рациональный накопитель', activeChance: 1.0, weeklyEarn: 2400, spendRatio: 0.13, start: OLD_MORA_MAX, newAccount: false },
];

function hashSeed(text) {
  let h = 2166136261;
  for (const ch of text) {
    h ^= ch.codePointAt(0);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function mulberry32(seed) {
  return () => {
    let t = seed += 0x6D2B79F5;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function jitter(rng, center, spread = 0.15) {
  return center * (1 - spread + rng() * spread * 2);
}

function percentile(values, p) {
  const sorted = [...values].sort((a, b) => a - b);
  const i = (sorted.length - 1) * p;
  const lo = Math.floor(i);
  const hi = Math.ceil(i);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo);
}

function simulate(persona, runIndex) {
  const seedGroup = persona.id === 'payer' ? 'main' : persona.id;
  const rng = mulberry32(hashSeed(`${seedGroup}:${runIndex}`));
  let mora = persona.start;
  let totalSource = 0;
  let totalSink = 0;
  let activeWeeks = 0;
  // Eligibility is a cohort property, never inferred from current wealth. A
  // legacy account with a zero wallet must not receive newcomer grants again.
  let campaignRemaining = persona.newAccount ? 3000 : 0;
  const checkpoints = {};

  for (let week = 1; week <= WEEKS_10Y; week += 1) {
    if (rng() <= persona.activeChance) {
      activeWeeks += 1;
      const recurring = Math.min(WEEKLY_MORA_RESERVE, Math.max(0, jitter(rng, persona.weeklyEarn)));
      const campaignGrant = Math.min(campaignRemaining, activeWeeks <= 8 ? 375 : 0);
      campaignRemaining -= campaignGrant;
      const source = recurring + campaignGrant;
      mora += source;
      totalSource += source;

      // Spending is voluntary. It combines bounded build activation, care/expedition
      // choices, cosmetic atelier and prestige. Refusing to spend is modeled by hoarder.
      let desiredSink = jitter(rng, recurring * persona.spendRatio, 0.20);
      if (persona.id === 'veteran' && mora > 250000) desiredSink += 900;
      const sink = Math.min(mora, Math.max(0, desiredSink));
      mora -= sink;
      totalSink += sink;
    }

    if ([8, 52, 260, 520].includes(week)) checkpoints[week] = mora;
  }

  return { mora, totalSource, totalSink, activeWeeks, checkpoints };
}

const scenarios = PERSONAS.map((persona) => {
  const runs = Array.from({ length: RUNS }, (_, i) => simulate(persona, i));
  const at = (week) => runs.map((r) => r.checkpoints[week]);
  const source = runs.map((r) => r.totalSource);
  const sink = runs.map((r) => r.totalSink);
  const sinkSourceRatios = runs.map((r) => r.totalSink / Math.max(1, r.totalSource));
  return {
    id: persona.id,
    persona: persona.label,
    active_weeks_p50: Math.round(percentile(runs.map((r) => r.activeWeeks), 0.5)),
    // Week 8 is day 56. The previous `50d` label overstated checkpoint
    // precision and made the report internally inconsistent.
    mora_p50_56d: Math.round(percentile(at(8), 0.5)),
    mora_p50_1y: Math.round(percentile(at(52), 0.5)),
    mora_p50_5y: Math.round(percentile(at(260), 0.5)),
    mora_p50_10y: Math.round(percentile(at(520), 0.5)),
    mora_p90_10y: Math.round(percentile(at(520), 0.9)),
    total_source_p50_10y: Math.round(percentile(source, 0.5)),
    total_sink_p50_10y: Math.round(percentile(sink, 0.5)),
    sink_source_ratio_p50: Number(percentile(sinkSourceRatios, 0.5).toFixed(3)),
    combat_power_from_payment: 0,
  };
});

const earningGoals = [100, 800, 3200, 12000].map((cost) => ({
  mora_cost: cost,
  main_active_days_of_gross_income: Number((cost / (2050 / 7)).toFixed(1)),
  short_active_days_of_gross_income: Number((cost / (850 / 7)).toFixed(1)),
  main_calendar_days_at_modeled_activity: Number((cost / (2050 * 0.86 / 7)).toFixed(1)),
  short_calendar_days_at_modeled_activity: Number((cost / (850 * 0.62 / 7)).toFixed(1)),
}));

const output = {
  status: 'provisional_until_live_telemetry',
  stress_test_not_prediction: true,
  model_version: 'constitution-v2',
  horizon_weeks: WEEKS_10Y,
  horizon_days: MODELED_DAYS,
  simulated_accounts_per_persona: RUNS,
  invariants: {
    weekly_repeatable_mora_cap: WEEKLY_MORA_RESERVE,
    payment_to_gameplay_currency: false,
    payment_to_combat_power: false,
    mora_alone_unlocks_mastery: false,
    negative_balances_allowed: false,
  },
  scenarios,
  earning_goals: earningGoals,
  interpretation: [
    'Отказ тратить валюту всё равно создаёт большой кошелёк; это не ошибка модели, пока Мора не покупает силу и обязательные unlock.',
    'Prestige/atelier нужны как желанные добровольные sinks, но не как налог на старые запасы.',
    'Одинаковые gameplay-параметры main и payer подтверждают требование нулевого платёжного преимущества.',
    'Числа должны быть заменены после пилота; экономическая конституция и ограничения остаются.',
  ],
  limitations: [
    'Модель применяет независимую вероятность активности каждую неделю; она не моделирует churn, resurrection, когорты или сезонность.',
    'Желаемые траты заданы коэффициентом, а не реальным каталогом, доступностью предметов, насыщением коллекции или ценовой эластичностью.',
    'Перенос до 50% неиспользованного Reward Reserve в расчёт не включён.',
    'Алмазы, Зарники, entitlement-инвентарь, прогресс-метры, рынок, подарки, возвраты и административные выдачи не моделируются.',
    'Совпадение main и payer является тестом заданного запрета paid advantage, а не доказательством отсутствия скрытого платёжного пути в продукте.',
    'Из one-time Моры учтён только опубликованный campaign cap 3 000; onboarding 300 моделируется отдельно от десятилетнего recurring stress test.',
  ],
};

const main = scenarios.find((row) => row.id === 'main');
const payer = scenarios.find((row) => row.id === 'payer');
if (WEEKLY_MORA_RESERVE !== 2400) throw new Error('Unexpected reward reserve');
if (main.mora_p50_10y !== payer.mora_p50_10y) throw new Error('Payer received an economic advantage');
if (scenarios.some((row) => row.mora_p50_10y < 0)) throw new Error('Negative balance');
if (scenarios.some((row) => !Number.isFinite(row.sink_source_ratio_p50))) {
  throw new Error('Non-finite sink/source ratio');
}

process.stdout.write(`${JSON.stringify(output, null, 2)}\n`);
