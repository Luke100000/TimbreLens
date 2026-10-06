import {execFileSync} from "node:child_process";
import {createRequire} from "node:module";
import {availableParallelism} from "node:os";
import {resolve} from "node:path";

function normalize(values) {
    const norm = Math.sqrt(values.reduce((sum, value) => sum + value * value, 0));

    if (!norm || !Number.isFinite(norm)) {
        throw new Error("Invalid embedding vector.");
    }

    return Float32Array.from(values, value => value / norm);
}

async function run() {
    const require = createRequire(resolve("package.json"));
    const {pipeline, AutoProcessor, ClapAudioModelWithProjection, env} = require("@huggingface/transformers");
    let input = "";

    for await (const chunk of process.stdin) {
        input += chunk;
    }

    const job = JSON.parse(input);

    if (env.version !== job.runtime_version) {
        throw new Error("Transformers.js version differs from the embedding manifest; run npm ci.");
    }

    env.cacheDir = job.cache;
    env.allowLocalModels = false;
    let text = null;
    let processor = null;
    let audio = null;

    for (const task of job.tasks) {
        const spec = job.models[task.kind];
        const options = {
            revision: spec.revision,
            dtype: spec.dtype,
            device: "cpu",
            session_options: {intraOpNumThreads: Math.min(4, availableParallelism()), interOpNumThreads: 1},
        };
        let vector;

        if (task.kind === "text") {
            text ??= await pipeline("feature-extraction", spec.model, options);
            const result = await text(task.text, {pooling: spec.pooling, normalize: true});
            vector = result.data;
        } else {
            processor ??= await AutoProcessor.from_pretrained(spec.model, options);
            audio ??= await ClapAudioModelWithProjection.from_pretrained(spec.model, options);
            const pcm = execFileSync("ffmpeg", [
                "-hide_banner", "-loglevel", "error", "-nostdin", "-i", task.path,
                "-vn", "-ac", "1", "-ar", String(spec.sample_rate), "-f", "f32le", "pipe:1",
            ], {maxBuffer: 64 * 1024 * 1024});
            const samples = new Float32Array(pcm.length / 4);

            for (let index = 0; index < samples.length; index++) {
                samples[index] = pcm.readFloatLE(index * 4);
            }

            if (!samples.length) {
                throw new Error(`No audio samples: ${task.path}`);
            }

            const window = spec.sample_rate * spec.window_seconds;
            let sum = null;

            for (let start = 0; start < samples.length; start += window) {
                const chunk = samples.subarray(start, start + window);
                const features = await processor(chunk);
                const {audio_embeds} = await audio(features);
                const embedding = normalize(audio_embeds.data);
                sum ??= new Float64Array(embedding.length);

                for (let index = 0; index < sum.length; index++) {
                    sum[index] += embedding[index] * chunk.length;
                }
            }

            vector = normalize(sum);
        }

        console.log(JSON.stringify({key: task.key, vector: Array.from(vector)}));
        console.error(`Embedded ${task.kind}: ${task.kind === "text" ? task.text.split("\n")[0] : task.path}`);
    }

    await text?.dispose();
    await audio?.dispose();
}

run().catch(error => {
    console.error(error.code === "MODULE_NOT_FOUND" ? "Install embedding dependencies with npm ci." : error.message);
    process.exitCode = 1;
});
