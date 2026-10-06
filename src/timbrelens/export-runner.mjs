import {copyFile, mkdir, readFile, writeFile} from "node:fs/promises";
import {createRequire} from "node:module";
import {dirname, resolve} from "node:path";

const require = createRequire(resolve("package.json"));
const MiniSearch = require("minisearch");
let input = "";

for await (const chunk of process.stdin) {
    input += chunk;
}

const {documents, options, version, output} = JSON.parse(input);
const packagePath = resolve(dirname(require.resolve("minisearch")), "../../package.json");
const installed = JSON.parse(await readFile(packagePath, "utf8"));

if (installed.version !== version) {
    throw new Error(`Expected MiniSearch ${version}, found ${installed.version}.`);
}

const index = new MiniSearch(options);
index.addAll(documents);

await writeFile(output, JSON.stringify(index) + "\n", "utf8");

const vendor = resolve(dirname(output), "vendor");
await mkdir(vendor, {recursive: true});
await copyFile(resolve(dirname(packagePath), "dist/es/index.js"), resolve(vendor, "minisearch.js"));
await copyFile(resolve(dirname(packagePath), "LICENSE.txt"), resolve(vendor, "minisearch.LICENSE.txt"));
