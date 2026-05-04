import { existsSync, readdirSync, rmSync } from 'node:fs';
import { join, resolve } from 'node:path';

const apply = process.argv.includes('--apply');
const root = resolve(process.cwd());
const testingRoot = resolve(root, 'testing');
const targets = [
  'playwright-artifacts',
  'playwright-report',
  'runs',
  'screenshots',
  'videos',
  'logs',
];

function assertInsideTesting(path) {
  const resolved = resolve(path);
  if (!resolved.startsWith(`${testingRoot}\\`) && !resolved.startsWith(`${testingRoot}/`)) {
    throw new Error(`Refusing to clean outside testing/: ${resolved}`);
  }
  return resolved;
}

const removals = [];

for (const target of targets) {
  const dir = assertInsideTesting(join(testingRoot, target));
  if (!existsSync(dir)) continue;
  for (const entry of readdirSync(dir)) {
    if (entry === '.gitkeep') continue;
    removals.push(assertInsideTesting(join(dir, entry)));
  }
}

if (removals.length === 0) {
  console.log('No generated testing artifacts found.');
  process.exit(0);
}

if (!apply) {
  console.log('Dry run. Re-run with --apply to remove these generated testing artifacts:');
  for (const item of removals) console.log(`- ${item}`);
  process.exit(0);
}

for (const item of removals) {
  rmSync(item, { recursive: true, force: true });
  console.log(`Removed ${item}`);
}
