import { readFileSync, readdirSync } from "node:fs";
import { gzipSync } from "node:zlib";


const assetsDir = new URL("../dist/assets/", import.meta.url);
const files = readdirSync(assetsDir).filter((name) => /\.(?:js|css)$/.test(name));
const measurements = files.map((name) => {
  const bytes = readFileSync(new URL(name, assetsDir));
  return { name, raw: bytes.byteLength, gzip: gzipSync(bytes).byteLength };
});

const limits = {
  anyJavaScript: { raw: 600 * 1024, gzip: 210 * 1024 },
  entryJavaScript: { raw: 300 * 1024, gzip: 80 * 1024 },
  css: { raw: 325 * 1024, gzip: 60 * 1024 },
};

const failures = [];
for (const item of measurements) {
  const budget = item.name.endsWith(".css")
    ? limits.css
    : /^index-.*\.js$/.test(item.name)
      ? limits.entryJavaScript
      : limits.anyJavaScript;
  if (item.raw > budget.raw || item.gzip > budget.gzip) {
    failures.push(
      `${item.name}: ${(item.raw / 1024).toFixed(2)} KiB raw / ${(item.gzip / 1024).toFixed(2)} KiB gzip `
      + `(budget ${(budget.raw / 1024).toFixed(0)} / ${(budget.gzip / 1024).toFixed(0)} KiB)`,
    );
  }
}

if (failures.length > 0) {
  throw new Error(`Production bundle budget exceeded:\n${failures.join("\n")}`);
}

const entry = measurements.find((item) => /^index-.*\.js$/.test(item.name));
process.stdout.write(
  `Bundle budgets passed${entry ? `; entry ${(entry.raw / 1024).toFixed(2)} KiB raw / ${(entry.gzip / 1024).toFixed(2)} KiB gzip` : ""}.\n`,
);
