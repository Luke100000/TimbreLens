import MiniSearch from "./data/vendor/minisearch.js";
import {rank} from "./search.js";
import {loadSemantic} from "./semantic.js";

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

    function publish(request, rankings, pending = false) {
        self.postMessage({
            id: request.id, pending,
            track_ids: rank(tracks, request.query, request.filters, rankings)
        });
    }

    async function searchSemantic() {
        running = true;

        try {
            if (!semantic) {
                self.postMessage({type: "semantic", state: "loading"});
                semantic = await loadSemantic(manifest, dataRoot);
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

                publish(request, [request.lexical, ...rankings]);
                break;
            }
        } catch (error) {
            console.error(error);
            failed = true;
            self.postMessage({type: "semantic", state: "error"});
            publish(latest, [latest.lexical]);
        } finally {
            running = false;
        }
    }

    self.onmessage = ({data}) => {
        data.query = data.query.trim();
        data.lexical = {
            ids: data.query
                ? index.search(data.query, {combineWith: "AND"}).map(result => result.id) : [],
            weight: data.query.split(/\s+/).length <= 2 ? 2 : 1
        };
        latest = data;

        if (data.retry) {
            failed = false;
        }

        const rankings = cached.get(data.query);

        // Show keyword matches immediately, then add semantic results when ready.
        publish(data, [data.lexical, ...(rankings || [])], Boolean(data.query && !rankings && !failed));

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
