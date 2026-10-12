const query = document.querySelector("#query");
const controls = document.querySelector("#controls");
const status = document.querySelector("#status");
const semanticStatus = document.querySelector("#semantic-status");
const similarity = document.querySelector("#similarity");
const similarityTitle = document.querySelector("#similarity-title");
const similarityStatus = document.querySelector("#similarity-status");
const retry = document.querySelector("#retry-search");
const catalog = document.querySelector(".catalog");
const results = document.querySelector("#results");
const empty = document.querySelector("#empty");
const more = document.querySelector("#more");
const clear = document.querySelector("#clear");
const player = document.querySelector("#player");
const audio = document.querySelector("#audio");
const playerMessage = document.querySelector("#player-message");
const template = document.querySelector("#track-template");
const filters = [...document.querySelectorAll(".filter")];

const dataRoot = new URL("./data/", import.meta.url);
const worker = new Worker(new URL("./search-worker.js", import.meta.url), {type: "module"});

const pageSize = 50;
let tracks = new Map();
let matches = [];
let visible = 0;
let requestId = 0;
let searchTimer;
let playingId = null;
let similarTo = null;
let semanticFailed = false;
let similarityFailed = false;

function duration(seconds) {
    if (seconds == null) return "";

    const rounded = Math.round(seconds);
    return `${Math.floor(rounded / 60)}:${String(rounded % 60).padStart(2, "0")}`;
}

function updatePlayback() {
    for (const button of results.querySelectorAll(".preview-button")) {
        const track = tracks.get(button.dataset.id);
        const playing = track.id === playingId && !audio.paused;
        button.classList.toggle("playing", playing);
        button.setAttribute("aria-label", `${playing ? "Pause" : "Play"} preview of ${track.title}`);
        button.setAttribute("aria-pressed", String(playing));
        button.querySelector("path").setAttribute("d",
            playing ? "M6 4h4v16H6zM14 4h4v16h-4z" : "M8 4v16l12-8z");
    }
}

async function play(track) {
    playerMessage.textContent = "";

    if (playingId === track.id && !audio.paused) {
        audio.pause();
        return;
    }

    if (playingId !== track.id || audio.error) {
        playingId = track.id;
        audio.src = new URL(`previews/${track.preview.sha256}.mp3`, dataRoot).href;
        document.querySelector("#playing-title").textContent = track.title;
        document.querySelector("#playing-artist").textContent = track.artist;
    }

    player.hidden = false;

    try {
        await audio.play();
    } catch (error) {
        if (playingId === track.id && error.name !== "AbortError") {
            playerMessage.textContent = "Couldn't play this preview. Try again.";
        }
    }
}

function renderMore() {
    const fragment = document.createDocumentFragment();
    const next = matches.slice(visible, visible + pageSize);

    for (const id of next) {
        const track = tracks.get(id);
        const row = template.content.firstElementChild.cloneNode(true);
        const button = row.querySelector(".preview-button");
        button.dataset.id = id;
        button.onclick = () => play(track);

        row.querySelector(".track-title").textContent = track.title;
        row.querySelector(".duration").textContent = duration(track.duration);
        row.querySelector(".artist").textContent = track.artist;

        const description = row.querySelector(".description");
        description.textContent = track.summary || track.description || "";
        description.hidden = !description.textContent;

        const waveform = row.querySelector(".waveform");
        waveform.querySelector("img").src = new URL(`previews/${track.preview.sha256}.png`, dataRoot).href;
        waveform.setAttribute("aria-label", `Full-track signature of ${track.title}`);

        if (track.duration > 0) {
            const start = track.preview.start;
            const end = Math.min(start + track.preview.duration, track.duration);
            const marker = waveform.querySelector(".preview-range");
            marker.style.left = `${start / track.duration * 100}%`;
            marker.style.width = `${(end - start) / track.duration * 100}%`;
            marker.hidden = false;
            waveform.title = `Preview: ${duration(start)}–${duration(end)}`;
            waveform.setAttribute("aria-label",
                `Full-track signature of ${track.title}. Preview from ${duration(start)} to ${duration(end)}.`);
        }

        const tags = row.querySelector(".tags");
        tags.title = track.display_tags.join(", ");

        for (const value of track.display_tags) {
            const tag = document.createElement("span");
            tag.className = "tag";
            tag.textContent = value;
            tags.append(tag);
        }

        row.querySelector(".source-link").href = track.source_url;
        const similar = row.querySelector(".similar-button");
        similar.setAttribute("aria-label", `Find tracks similar to ${track.title}`);
        similar.onclick = () => {
            similarTo = id;
            similarityTitle.textContent = track.title;
            similarity.hidden = false;
            search();
        };

        row.querySelector(".attribution").textContent = track.attribution;
        const license = row.querySelector(".license");
        license.href = track.license_url;
        license.textContent = track.license;
        const copy = row.querySelector(".copy-credit");

        copy.onclick = async () => {
            try {
                await navigator.clipboard.writeText(track.attribution);
                copy.textContent = "Copied";
            } catch {
                copy.textContent = "Select and copy the attribution";
            }
        };

        fragment.append(row);
    }

    results.append(fragment);
    visible += next.length;
    more.hidden = visible >= matches.length;
    more.textContent = `Show more (${visible.toLocaleString()} of ${matches.length.toLocaleString()})`;
    updatePlayback();
}

function search(retryModels = false) {
    clearTimeout(searchTimer);
    const selected = {};

    for (const filter of filters) {
        const values = [...filter.querySelectorAll("input:checked")].map(input => input.value);
        selected[filter.dataset.field] = values;
        filter.querySelector(".selected-count").textContent = values.length ? `(${values.length})` : "";
    }

    clear.hidden = Object.values(selected).every(values => values.length === 0);
    catalog.setAttribute("aria-busy", "true");
    worker.postMessage({
        id: ++requestId, query: query.value, filters: selected,
        similar_to: similarTo, retry: retryModels
    });
}

function updateRetry() {
    retry.hidden = !semanticFailed && !(similarTo && similarityFailed);
}

function fillFilters() {
    for (const filter of filters) {
        const counts = new Map();

        for (const track of tracks.values()) {
            for (const value of track[filter.dataset.field]) {
                counts.set(value, (counts.get(value) || 0) + 1);
            }
        }

        for (const [value, count] of [...counts].sort(([a], [b]) => a.localeCompare(b))) {
            const label = document.createElement("label");
            label.className = "filter-option";
            const input = document.createElement("input");
            input.type = "checkbox";
            input.value = value;
            const text = document.createElement("span");
            text.className = "facet-label";
            text.textContent = value;
            const amount = document.createElement("span");
            amount.className = "facet-count";
            amount.textContent = count.toLocaleString();
            amount.setAttribute("aria-hidden", "true");
            label.append(input, text, amount);
            filter.querySelector(".filter-options").append(label);
        }
    }
}

function loadError() {
    controls.disabled = true;
    catalog.setAttribute("aria-busy", "false");
    status.textContent = "Couldn't load the catalog. Reload the page.";
}

worker.onmessage = ({data}) => {
    if (data.type === "semantic") {
        semanticStatus.textContent = data.state === "loading" ? "Loading search models…"
            : data.state === "error" ? "Keyword search only." : "";
        semanticFailed = data.state === "error";
        updateRetry();
        return;
    }

    if (data.type === "similarity") {
        similarityStatus.textContent = data.state === "loading" ? "Loading similar tracks…"
            : data.state === "error" ? "Couldn't load similar tracks." : "";
        similarityFailed = data.state === "error";
        updateRetry();
        return;
    }

    if (data.type === "error") {
        loadError();
        return;
    }

    if (data.type === "ready") {
        tracks = new Map(data.tracks.map(track => [track.id, track]));
        fillFilters();
        controls.disabled = false;
        search();
        return;
    }

    if (data.id !== requestId) return;

    matches = data.track_ids;
    visible = 0;
    results.replaceChildren();
    renderMore();
    status.textContent = data.pending && !matches.length ? "Searching…"
        : `${matches.length.toLocaleString()} ${matches.length === 1 ? "track" : "tracks"}`;
    empty.hidden = matches.length !== 0 || data.pending;
    catalog.setAttribute("aria-busy", String(data.pending));
};

worker.onerror = loadError;
query.oninput = () => {
    clearTimeout(searchTimer);
    requestId++;
    catalog.setAttribute("aria-busy", "true");
    searchTimer = setTimeout(search, 100);
};
document.querySelector("#search-form").onsubmit = event => {
    event.preventDefault();
    search();
};

for (const filter of filters) {
    filter.onchange = () => search();
}

retry.onclick = () => search(true);

document.querySelector("#clear-similarity").onclick = () => {
    similarTo = null;
    similarity.hidden = true;
    updateRetry();
    search();
};

clear.onclick = () => {
    for (const input of document.querySelectorAll(".filter input:checked")) {
        input.checked = false;
    }

    search();
};

document.addEventListener("click", event => {
    for (const filter of filters) {
        if (!filter.contains(event.target)) {
            filter.open = false;
        }
    }
});
document.addEventListener("keydown", event => {
    if (event.key === "Escape") {
        for (const filter of filters) {
            filter.open = false;
        }
    }

    if (event.key === "/" && !controls.disabled && !event.ctrlKey && !event.metaKey
        && !event.altKey && !event.target.closest("input, textarea, [contenteditable]")) {
        event.preventDefault();
        query.focus();
    }
});

more.onclick = renderMore;
for (const event of ["play", "pause", "ended"]) {
    audio.addEventListener(event, updatePlayback);
}
audio.onerror = () => {
    playerMessage.textContent = "Couldn't play this preview. Try again.";
    updatePlayback();
};
document.querySelector("#close-player").onclick = () => {
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    playingId = null;
    player.hidden = true;
    updatePlayback();
};
