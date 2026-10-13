import {cosineSearch} from "./search.js";

export async function loadSemantic(manifest, dataRoot, vectors) {
    const {audio: audioVectors, text: textVectors} = vectors;
    const {AutoModel, AutoTokenizer, FeatureExtractionPipeline, ClapTextModelWithProjection, env} =
        await import("./data/vendor/transformers.js");
    const vendor = new URL("vendor/", dataRoot);
    env.allowLocalModels = false;

    // One WASM thread works without cross-origin isolation on GitHub Pages.
    env.backends.onnx.wasm.numThreads = 1;
    env.backends.onnx.wasm.wasmPaths = {
        mjs: new URL("ort-wasm-simd-threaded.mjs", vendor).href,
        wasm: new URL("ort-wasm-simd-threaded.wasm", vendor).href,
    };

    const download = env.fetch;

    // Transformers.js 4.3 probes main for tokenizer metadata despite the pinned revision.
    env.fetch = async (url, options) => {
        let target = String(url);

        for (const spec of [manifest.text.encoder, manifest.audio.encoder]) {
            target = target.replace(`/${spec.model}/resolve/main/`, `/${spec.model}/resolve/${spec.revision}/`);
        }

        if (options?.headers?.has("Range") && env.useBrowserCache) {
            const cached = await caches.open(env.cacheKey).then(cache => cache.match(target)).catch(() => undefined);

            if (cached) return cached;
        }

        return download(target, options);
    };

    const textSpec = manifest.text.encoder;
    const audioSpec = manifest.audio.encoder;
    const options = spec => ({revision: spec.revision, dtype: spec.dtype, device: "wasm"});
    const textTokenizer = await AutoTokenizer.from_pretrained(textSpec.model, options(textSpec));
    const textModel = await AutoModel.from_pretrained(textSpec.model, options(textSpec));
    const text = new FeatureExtractionPipeline({
        task: "feature-extraction",
        tokenizer: textTokenizer, model: textModel
    });
    let tokenizer;
    let audio;

    try {
        tokenizer = await AutoTokenizer.from_pretrained(audioSpec.model, options(audioSpec));
        audio = await ClapTextModelWithProjection.from_pretrained(audioSpec.model, options(audioSpec));
    } catch (error) {
        await text.dispose();
        throw error;
    }

    return async query => {
        // BGE matches metadata; CLAP matches the same query against audio embeddings.
        const metadata = await text(textSpec.query_prefix + query,
            {pooling: textSpec.pooling, normalize: true});
        const inputs = tokenizer(query, {padding: true, truncation: true});
        const {text_embeds} = await audio(inputs);

        return [
            {
                ids: cosineSearch(metadata.data, textVectors.matrix, textVectors.norms, manifest.text.dimensions)
                    .map(row => manifest.track_ids[row]), weight: 0.7
            },
            {
                ids: cosineSearch(text_embeds.normalize(2, -1).data, audioVectors.matrix, audioVectors.norms,
                    manifest.audio.dimensions).map(row => manifest.track_ids[row]), weight: 0.7
            },
        ];
    };
}
