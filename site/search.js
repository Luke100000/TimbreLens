export function cosineSearch(query, matrix, inverseNorms, dimensions) {
    const scores = [];

    for (let row = 0; row < inverseNorms.length; row++) {
        let dot = 0;
        const offset = row * dimensions;

        for (let column = 0; column < dimensions; column++) {
            dot += query[column] * matrix[offset + column];
        }

        // Stored row norms recover cosine similarity from the int8 dot product.
        scores.push({row, score: dot * inverseNorms[row]});
    }

    return scores.sort((a, b) => b.score - a.score).map(result => result.row);
}

export function rank(tracks, query, filters, rankings) {
    // OR within each facet, AND between facets.
    const allowed = new Set(tracks.filter(track => Object.entries(filters).every(([field, values]) =>
        values.length === 0 || values.some(value => track[field].includes(value)))).map(track => track.id));

    if (!query) return tracks.filter(track => allowed.has(track.id)).map(track => track.id);

    const scores = new Map();

    // Reciprocal rank fusion combines positions because lexical and cosine scores differ.
    // Filter before the top-50 cutoff so narrow filters still find candidates.
    for (const {ids, weight} of rankings) {
        const candidates = ids.filter(id => allowed.has(id)).slice(0, 50);

        candidates.forEach((id, index) => {
            scores.set(id, (scores.get(id) || 0) + weight / (60 + index + 1));
        });
    }

    const exact = new Set(tracks.filter(track => track.title.toLowerCase() === query.toLowerCase())
        .map(track => track.id));

    for (const id of exact) {
        if (allowed.has(id) && !scores.has(id)) {
            scores.set(id, 0);
        }
    }

    return [...scores.keys()].sort((a, b) => Number(exact.has(b)) - Number(exact.has(a))
        || scores.get(b) - scores.get(a) || a.localeCompare(b));
}
