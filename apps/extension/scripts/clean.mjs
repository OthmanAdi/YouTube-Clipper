import { promises as fs } from "node:fs";
import path from "node:path";
import url from "node:url";

const __dirname = path.dirname(url.fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
await fs.rm(path.join(ROOT, "dist"), { recursive: true, force: true });
console.log("clean: dist/ removed");
