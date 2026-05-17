// Tiny build script for the YouTube-Clipper extension.
// Steps:
//   1. tsc compiles src/**/*.ts -> dist/**/*.js
//   2. copy manifest.json, popup.html, popup.css, icons/, public/assets/
//   3. fix manifest path references if needed
// No bundler. ~95% fewer transitive deps than vite/rollup/esbuild.

import { execSync } from "node:child_process";
import { promises as fs } from "node:fs";
import path from "node:path";
import url from "node:url";

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const DIST = path.join(ROOT, "dist");

async function exists(p) {
  try {
    await fs.access(p);
    return true;
  } catch {
    return false;
  }
}

async function rmrf(p) {
  await fs.rm(p, { recursive: true, force: true });
}

async function copyTree(src, dst) {
  await fs.mkdir(path.dirname(dst), { recursive: true });
  const stat = await fs.stat(src);
  if (stat.isDirectory()) {
    await fs.cp(src, dst, { recursive: true });
  } else {
    await fs.copyFile(src, dst);
  }
}

async function main() {
  console.log("==> clean");
  await rmrf(DIST);
  await fs.mkdir(DIST, { recursive: true });

  console.log("==> tsc");
  // Use the project-local tsc.
  const tsc = process.platform === "win32"
    ? path.join(ROOT, "node_modules", ".bin", "tsc.cmd")
    : path.join(ROOT, "node_modules", ".bin", "tsc");
  execSync(`"${tsc}" -p tsconfig.json`, { cwd: ROOT, stdio: "inherit" });

  // Move popup.html to root of dist (manifest references it there).
  const popupHtmlSrc = path.join(ROOT, "src", "popup", "popup.html");
  const popupCssSrc = path.join(ROOT, "src", "popup", "popup.css");
  await copyTree(popupHtmlSrc, path.join(DIST, "popup.html"));
  await copyTree(popupCssSrc, path.join(DIST, "popup.css"));

  // Rewrite the popup.html so it references popup.js at the dist-level path.
  const html = await fs.readFile(path.join(DIST, "popup.html"), "utf-8");
  const fixed = html.replace(/src=\"\.\.\/popup\/popup\.js\"|src=\"popup\.js\"/g, 'src="popup/popup.js"');
  await fs.writeFile(path.join(DIST, "popup.html"), fixed, "utf-8");

  // Note: we deliberately do NOT flatten the tsc output. The manifest references
  // "content/content.js" and "background/sw.js" — keeping the directory structure
  // means relative ESM imports (`../lib/api.js`) resolve correctly inside dist/.

  // Copy manifest.
  await copyTree(path.join(ROOT, "manifest.json"), path.join(DIST, "manifest.json"));

  // Copy icons.
  const iconsSrc = path.join(ROOT, "icons");
  if (await exists(iconsSrc)) {
    await copyTree(iconsSrc, path.join(DIST, "icons"));
  }

  // Copy public/assets if any (e.g. content.css).
  const publicSrc = path.join(ROOT, "public");
  if (await exists(publicSrc)) {
    const entries = await fs.readdir(publicSrc);
    for (const e of entries) {
      await copyTree(path.join(publicSrc, e), path.join(DIST, e));
    }
  }

  console.log("==> build complete:", DIST);
  console.log("==> Load unpacked at: chrome://extensions/ -> dev mode on -> Load unpacked -> select", DIST);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
