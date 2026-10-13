export async function loadVectors(spec, dataRoot) {
    const buffers = await Promise.all([spec.file, spec.inverse_norms].map(async file => {
        const response = await fetch(new URL(file, dataRoot));

        if (!response.ok) {
            throw new Error(`Couldn't load ${file}.`);
        }

        return response.arrayBuffer();
    }));
    const matrix = new Int8Array(buffers[0]);
    const norms = new Float32Array(buffers[1]);

    if (matrix.length !== norms.length * spec.dimensions) {
        throw new Error(`Invalid vector dimensions in ${spec.file}.`);
    }

    return {matrix, norms, dimensions: spec.dimensions};
}
