import {copyFile, mkdir, readFile, writeFile} from "node:fs/promises";
import {createRequire} from "node:module";
import {dirname, resolve} from "node:path";

const require = createRequire(resolve("package.json"));
const MiniSearch = require("minisearch");
let input = "";

for await (const chunk of process.stdin) {
    input += chunk;
}

const {documents, options, version, runtime_version, output} = JSON.parse(input);
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

const transformers = resolve(dirname(require.resolve("@huggingface/transformers")), "..");
const runtime = JSON.parse(await readFile(resolve(transformers, "package.json"), "utf8"));

if (runtime.version !== runtime_version) {
    throw new Error(`Expected Transformers.js ${runtime_version}, found ${runtime.version}.`);
}

const onnx = resolve(dirname(require.resolve("onnxruntime-web")), "..");

for (const [source, name] of [
    [resolve(transformers, "dist/transformers.min.js"), "transformers.js"],
    [resolve(transformers, "LICENSE"), "transformers.LICENSE.txt"],
    [resolve(onnx, "dist/ort-wasm-simd-threaded.mjs"), "ort-wasm-simd-threaded.mjs"],
    [resolve(onnx, "dist/ort-wasm-simd-threaded.wasm"), "ort-wasm-simd-threaded.wasm"],
]) {
    await copyFile(source, resolve(vendor, name));
}
