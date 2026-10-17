// Write dist/artifact.html: the same page in the shape the Artifact tool publishes — no
// doctype/html/head/body of its own (the tool wraps it), title and styles first, the CSS
// inlined (an artifact may only load stylesheets from Google Fonts), the module script
// left as a file. Used to publish a no-login preview; the real site serves index.html.
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const dist = resolve(dirname(fileURLToPath(import.meta.url)), "../dist");
const html = readFileSync(join(dist, "index.html"), "utf8");
const head = html.match(/<head>([\s\S]*?)<\/head>/)[1];
const body = html.match(/<body[^>]*>([\s\S]*?)<\/body>/)[1];
const title = head.match(/<title>[\s\S]*?<\/title>/)[0];
const fonts = [...head.matchAll(/<link[^>]+fonts\.(googleapis|gstatic)\.com[^>]*>/g)].map((m) => m[0]).join("\n");
const css = [...head.matchAll(/<link rel="stylesheet"[^>]*href="\.\/(assets\/[^"]+\.css)"[^>]*>/g)]
  .map((m) => readFileSync(join(dist, m[1]), "utf8")).join("\n");
const scripts = [...head.matchAll(/<script type="module"[^>]*><\/script>/g)].map((m) => m[0]).join("\n");
const out = `${title.replace(/<title>[^<]*<\/title>/, "<title>Wilinski Atlas Preview</title>")}\n<meta name="claude:viewport-fit-sides" content="cover">\n${fonts}\n<style>${css}</style>\n${body.trim()}\n${scripts}\n`;
writeFileSync(join(dist, "artifact.html"), out);
console.log(`wrote dist/artifact.html (${(out.length / 1024).toFixed(0)} KB)`);
