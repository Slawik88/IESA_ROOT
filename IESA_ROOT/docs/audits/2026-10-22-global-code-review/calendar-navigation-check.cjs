// Diagnostic against the actual template function, including DST boundaries.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
process.env.TZ = 'Europe/Zurich';
const source = fs.readFileSync(path.resolve(__dirname, '../../../users/templates/users/partner_calendar.html'), 'utf8');
const fn = source.match(/function navigateDay\(delta\)\s*\{[\s\S]*?\n\}/)[0];
for (const [day, delta, expected] of [
    ['2026-03-28', 1, '2026-03-29'],
    ['2026-03-29', 1, '2026-03-30'],
    ['2026-10-24', 1, '2026-10-25'],
    ['2026-10-25', 1, '2026-10-26'],
    ['2026-11-01', -1, '2026-10-31'],
]) {
    const context = {URL, Date, SELECTED_DAY: day, delta, window: {location: {href: 'http://localhost/auth/partner/calendar/?jump=2026-01&filter=keep'}}};
    vm.runInNewContext(fn + '; navigateDay(delta);', context);
    const result = new URL(context.window.location.href);
    assert.equal(result.searchParams.get('day'), expected);
    assert.equal(result.searchParams.get('month'), expected.slice(0, 7));
    assert.equal(result.searchParams.has('jump'), false);
    assert.equal(result.searchParams.get('filter'), 'keep');
}
console.log('Calendar navigation: 5 Zurich/DST cases passed.');
