import MiniSearch from "./data/vendor/minisearch.js";
import {rank, similaritySearch} from "./search.js";
import {loadSemantic} from "./semantic.js";
import {loadVectors} from "./vectors.js";

const dataRoot = new URL("./data/", import.meta.url);

async function load() {
    const manifestResponse = await fetch(new URL("manifest.json", dataRoot));

    if (!manifestResponse.ok) {
        throw new Error("Catalog manifest could not be loaded.");
    }

    const manifest = await manifestResponse.json();
    const responses = await Promise.all([
        fetch(new URL(manifest.catalog.file, dataRoot)),
        fetch(new URL(manifest.lexical.file, dataRoot)),
    ]);

    if (responses.some(response => !response.ok)) {
        throw new Error("Catalog or search index could not be loaded.");
    }

    const [{tracks}, serialized] = await Promise.all([responses[0].json(), responses[1].text()]);
    const index = MiniSearch.loadJSON(serialized, manifest.lexical.options);

    // Reuse query rankings when only filters change.
    const cached = new Map();
    let latest;
    let running = false;
    let semantic;
    let failed = false;
    let vectors;
    let vectorsLoading;
    let similarity;
    let similarityRunning = false;
    let similarityFailed = false;

    function loadCatalogVectors() {
        if (!vectorsLoading) {
            vectorsLoading = Promise.all([
                loadVectors(manifest.audio, dataRoot), loadVectors(manifest.text, dataRoot)
            ]).then(([audio, text]) => {
                if ([audio, text].some(vector => vector.norms.length !== manifest.track_ids.length)) {
                    throw new Error("Vectors do not match the catalog.");
                }

                vectors = {audio, text};
                return vectors;
            }).catch(error => {
                vectorsLoading = null;
                throw error;
            });
        }

        return vectorsLoading;
    }

    function similarityRanking(id) {
        if (!id) return null;
        if (!vectors) return {id, ids: []};

        if (similarity?.id !== id) {
            const row = manifest.track_ids.indexOf(id);
            similarity = {
                id, ids: similaritySearch(row, vectors.audio, vectors.text)
                    .map(index => manifest.track_ids[index])
            };
        }

        return similarity;
    }

    function publish(request) {
        const rankings = cached.get(request.query);
        const pending = Boolean((request.query && !rankings && !failed)
            || (request.similar_to && !vectors && !similarityFailed));
        self.postMessage({
            id: request.id, pending,
            track_ids: rank(tracks, request.query, request.filters,
                [request.lexical, ...(rankings || [])], similarityRanking(request.similar_to))
        });
    }

    async function searchSimilar() {
        similarityRunning = true;

        try {
            await loadCatalogVectors();
            self.postMessage({type: "similarity", state: "ready"});
        } catch (error) {
            console.error(error);
            similarityFailed = true;
            self.postMessage({type: "similarity", state: "error"});
        } finally {
            similarityRunning = false;
            publish(latest);
        }
    }

    async function searchSemantic() {
        running = true;

        try {
            if (!semantic) {
                self.postMessage({type: "semantic", state: "loading"});
                const catalogVectors = await loadCatalogVectors();

                if (latest.similar_to && similarityFailed) {
                    similarityFailed = false;
                    self.postMessage({type: "similarity", state: "ready"});
                    publish(latest);
                }

                semantic = await loadSemantic(manifest, dataRoot, catalogVectors);
                self.postMessage({type: "semantic", state: "ready"});
            }

            // Finish in-flight inference, then skip to the newest query.
            while (latest.query) {
                const request = latest;
                let rankings = cached.get(request.query);

                if (!rankings) {
                    rankings = await semantic(request.query);
                    cached.set(request.query, rankings);

                    if (cached.size > 20) {
                        cached.delete(cached.keys().next().value);
                    }
                }

                if (request !== latest) continue;

                publish(request);
                break;
            }
        } catch (error) {
            console.error(error);
            failed = true;
            self.postMessage({type: "semantic", state: "error"});
            publish(latest);
        } finally {
            running = false;
        }
    }

    self.onmessage = ({data}) => {
        data.query = data.query.trim();
        if (data.similar_to && !manifest.track_ids.includes(data.similar_to)) {
            data.similar_to = null;
        }

        data.lexical = {
            ids: data.query
                ? index.search(data.query, {combineWith: "AND"}).map(result => result.id) : [],
            weight: data.query.split(/\s+/).length <= 2 ? 2 : 1
        };
        latest = data;

        if (data.retry) {
            failed = false;
            similarityFailed = false;
        }

        if (data.similar_to) {
            if (vectors) {
                similarityFailed = false;
            }

            self.postMessage({
                type: "similarity", state: vectors ? "ready"
                    : similarityFailed ? "error" : "loading"
            });
        }

        const rankings = cached.get(data.query);

        // Show keyword matches immediately, then add semantic results when ready.
        publish(data);

        if (data.similar_to && !vectors && !similarityRunning && !similarityFailed) {
            searchSimilar();
        }

        if (data.query && !rankings && !running && !failed) {
            searchSemantic();
        }
    };

    self.postMessage({type: "ready", tracks});
}

load().catch(error => {
    console.error(error);
    self.postMessage({type: "error"});
});
