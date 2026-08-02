import {readdirSync} from 'fs';
import {spawnSync} from 'child_process';
import {dirname, join} from 'path';
import {fileURLToPath} from 'url';

const toolsDir = dirname(fileURLToPath(import.meta.url));
const requested = process.argv.slice(2);
const checks = readdirSync(toolsDir)
  .filter(name => name.startsWith('verify_') && name.endsWith('.mjs'))
  .filter(name => requested.length === 0 || requested.some(part => name.includes(part)))
  .sort();

if (!checks.length) {
  console.error(requested.length
    ? `No verify_*.mjs files match: ${requested.join(', ')}`
    : 'No verify_*.mjs files found.');
  process.exit(2);
}

const failed = [];
for (const [index, check] of checks.entries()) {
  console.log(`\n[${index + 1}/${checks.length}] ${check}`);
  const result = spawnSync(process.execPath, [join(toolsDir, check)], {
    cwd: join(toolsDir, '..'),
    env: process.env,
    encoding: 'utf8',
    stdio: 'inherit',
  });
  if (result.error) {
    console.error(result.error);
    failed.push(check);
  } else if (result.status !== 0) {
    failed.push(check);
  }
}

if (failed.length) {
  console.error(`\nFAILED ${failed.length}/${checks.length}: ${failed.join(', ')}`);
  console.error('Re-run each failed file by itself before classifying it as a product regression.');
  process.exit(1);
}

console.log(`\nALL ${checks.length} UI REGRESSIONS PASSED`);
