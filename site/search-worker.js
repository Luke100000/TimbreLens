import MiniSearch from "./data/vendor/minisearch.js";

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
    const byId = new Map(tracks.map(track => [track.id, track]));

    self.onmessage = ({data: {id, query, filters}}) => {
        query = query.trim();
        let matches = query
            ? index.search(query, {combineWith: "AND"}).map(result => byId.get(result.id))
            : tracks;

        if (query) {
            const title = query.toLowerCase();
            matches.sort((a, b) => Number(b.title.toLowerCase() === title)
                - Number(a.title.toLowerCase() === title));
        }

        matches = matches.filter(track => Object.entries(filters).every(([field, values]) =>
            values.length === 0 || values.some(value => track[field].includes(value))));

        self.postMessage({id, track_ids: matches.map(track => track.id)});
    };

    self.postMessage({type: "ready", tracks});
}

load().catch(error => {
    console.error(error);
    self.postMessage({type: "error"});
});
