// Форматирование денег и дат. Чистые функции без DOM — проверяются тестами Node.
const NBSP = ' ';
const MINUS = '−';
const MONTHS = 12;
const FIRST_YEAR = 1;
const LAST_YEAR = 9999;
// 1 января 2024 — понедельник: от него строятся названия дней недели в любой локали.
const MONDAY = Date.UTC(2024, 0, 1);

const dayDate = iso => new Date(`${iso}T12:00:00Z`);

export function capitalize(text) {
  return text ? text[0].toLocaleUpperCase() + text.slice(1) : text;
}

export function moneyParts(kop, locale) {
  const value = Math.abs(kop);
  const decimal = new Intl.NumberFormat(locale).formatToParts(1.5).find(part => part.type === 'decimal').value;
  return {
    negative: kop < 0, whole: Math.floor(value / 100).toLocaleString(locale),
    cents: String(value % 100).padStart(2, '0'), decimal,
  };
}

// «328,06 CHF»: всегда два знака, валюта через неразрывный пробел, настоящий минус.
export function formatMoney(kop, locale, currency = '', { plus = false } = {}) {
  const { negative, whole, cents, decimal } = moneyParts(kop, locale);
  const sign = negative ? MINUS : plus && kop > 0 ? '+' : '';
  return `${sign}${whole}${decimal}${cents}${currency ? NBSP + currency : ''}`;
}

// «123.45» для поля ввода: сервер понимает и точку, и запятую.
export function decimalString(kop) {
  const value = Math.abs(kop);
  return `${Math.floor(value / 100)}.${String(value % 100).padStart(2, '0')}`;
}

// Оставляет в строке только цифры и один разделитель — то, что можно разобрать как сумму.
export function sanitizeAmount(text) {
  const cleaned = String(text).replace(/[^\d.,]/g, '');
  const first = cleaned.search(/[.,]/);
  if (first === -1) return cleaned;
  return cleaned.slice(0, first + 1) + cleaned.slice(first + 1).replace(/[.,]/g, '').slice(0, 2);
}

export function formatDay(iso, locale, options = { day: 'numeric', month: 'short' }) {
  return dayDate(iso).toLocaleDateString(locale, { ...options, timeZone: 'UTC' });
}

export function formatMonth(month, locale, options = { month: 'long', year: 'numeric' }) {
  return capitalize(dayDate(`${month}-01`).toLocaleDateString(locale, { ...options, timeZone: 'UTC' }));
}

export function addDays(iso, delta) {
  const day = dayDate(iso);
  day.setUTCDate(day.getUTCDate() + delta);
  return day.toISOString().slice(0, 10);
}

// '2026-10' → '2026-11'; вне годов 0001–9999 — null.
export function shiftMonth(month, delta) {
  const [year, number] = month.split('-').map(Number);
  const next = new Date(Date.UTC(year, number - 1 + delta, 1));
  const nextYear = next.getUTCFullYear();
  return nextYear < FIRST_YEAR || nextYear > LAST_YEAR ? null : next.toISOString().slice(0, 7);
}

export function monthNames(locale) {
  return Array.from({ length: MONTHS }, (_, index) => capitalize(
    new Date(Date.UTC(2024, index, 1)).toLocaleDateString(locale, { month: 'short', timeZone: 'UTC' }).replace('.', ''),
  ));
}

export function weekdayName(index, locale, width = 'short') {
  return capitalize(new Date(MONDAY + index * 86400000).toLocaleDateString(locale, { weekday: width, timeZone: 'UTC' }));
}

// «Сегодня» / «Вчера» / «3 нояб.» — подписи Сегодня и Вчера приходят готовыми (переведёнными).
export function relativeDay(iso, today, locale, labels, options) {
  if (iso === today) return labels.today;
  if (iso === addDays(today, -1)) return labels.yesterday;
  return formatDay(iso, locale, options);
}
