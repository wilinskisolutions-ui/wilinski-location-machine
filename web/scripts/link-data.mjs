// Copy the atlas data bundle (built by `make atlas` into output/atlas) into public/, where
// Vite serves it in dev and copies it into dist/ on build. Fails loudly when the bundle is
// missing rather than shipping a site with no data.
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const bundle = resolve(here, "../../output/atlas");
const pub = resolve(here, "../public");
for (const dir of ["data", "geo"]) {
  if (!existsSync(join(bundle, dir))) {
    console.error(`missing ${join(bundle, dir)} — run \`make atlas\` from the repo root first`);
    process.exit(1);
  }
}
mkdirSync(pub, { recursive: true });
for (const dir of ["data", "geo"]) {
  rmSync(join(pub, dir), { recursive: true, force: true });
  cpSync(join(bundle, dir), join(pub, dir), { recursive: true });
}
console.log(`linked data bundle from ${bundle}`);
