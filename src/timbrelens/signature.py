from pathlib import Path

import librosa
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

from timbrelens.files import atomic_output

BACKGROUND = (248, 247, 243)
PALETTE = np.array([(53, 100, 79), (113, 145, 122), (178, 160, 106)], dtype=np.float32)
SEPARATOR = (50, 58, 51)


def _robust01(values, lo=5, hi=95):
    low, high = np.percentile(values, [lo, hi])
    if high <= low:
        return np.zeros_like(values)

    return np.clip((values - low) / (high - low), 0, 1)


def _aggregate(values, edges):
    return np.stack(
        [values[..., a : max(a + 1, b)].mean(axis=-1) for a, b in zip(edges[:-1], edges[1:])],
        axis=-1,
    )


def signature(input: Path, output: Path, bins: int = 64) -> None:
    """Render full-track energy, timbre, rhythmic activity, and changes as a PNG."""
    if bins < 2:
        raise ValueError("A signature needs at least two bins.")

    samples, sample_rate = librosa.load(input, sr=22050, mono=True)
    if not samples.size:
        raise ValueError(f"No audio samples: {input}")

    samples = np.pad(samples, (0, max(0, 2048 - samples.size)))
    spectrum = np.abs(librosa.stft(samples, n_fft=2048, hop_length=512))
    power = spectrum**2
    mel = librosa.feature.melspectrogram(S=power, sr=sample_rate)
    mel_db = librosa.power_to_db(mel)
    edges = np.linspace(0, spectrum.shape[1], bins + 1).astype(int)

    rms = librosa.feature.rms(y=samples, frame_length=2048, hop_length=512)[0]
    energy = gaussian_filter1d(_aggregate(rms, edges), 1.6)
    energy = 0.08 + 0.92 * _robust01(energy, 8, 92) ** 0.70

    frequencies = librosa.fft_frequencies(sr=sample_rate, n_fft=2048)
    bands = np.array(
        [
            10 * np.log10(power[(frequencies >= low) & (frequencies < high)].sum(axis=0) + 1e-12)
            for low, high in [(20, 250), (250, 2000), (2000, 8000)]
        ]
    )
    bands = _aggregate(bands, edges)
    median = np.median(bands, axis=1, keepdims=True)
    deviation = np.median(np.abs(bands - median), axis=1, keepdims=True)
    weights = (bands - median) / (1.4826 * deviation + 1e-6) / 1.10
    weights = np.exp(weights - weights.max(axis=0, keepdims=True))
    weights /= weights.sum(axis=0, keepdims=True)
    weights = gaussian_filter1d(weights, 1.0, axis=1)

    centroid = librosa.feature.spectral_centroid(S=spectrum, sr=sample_rate)[0]
    centroid = gaussian_filter1d(_robust01(_aggregate(centroid, edges), 4, 96), 1.0)
    bright_bias = (1 - centroid[:, None]) * PALETTE[1] + centroid[:, None] * PALETTE[2]
    colors = np.clip(0.88 * weights.T @ PALETTE + 0.12 * bright_bias, 0, 255).astype(np.uint8)

    onset = librosa.onset.onset_strength(S=mel_db, sr=sample_rate, hop_length=512)
    rhythm = gaussian_filter1d(_aggregate(onset, edges), 0.9)
    rhythm = _robust01(rhythm, 8, 95) ** 0.78

    mfcc = librosa.feature.mfcc(S=mel_db, n_mfcc=13)
    chroma = librosa.feature.chroma_stft(S=power, sr=sample_rate, tuning=0)
    features = np.vstack([_aggregate(mfcc, edges), _aggregate(chroma, edges), centroid])
    features -= features.mean(axis=1, keepdims=True)
    features /= features.std(axis=1, keepdims=True) + 1e-6
    features /= np.linalg.norm(features, axis=0, keepdims=True) + 1e-9
    novelty = np.maximum(0, 1 - (features[:, :-1] * features[:, 1:]).sum(axis=0))
    novelty = gaussian_filter1d(novelty, 0.8)
    peaks, _ = find_peaks(novelty, distance=max(3, bins // 12), prominence=0.15)
    separators = set(peaks + 1)

    width, height = 400, 80
    scale = 4
    image = Image.new("RGB", (width * scale, height * scale), BACKGROUND)
    draw = ImageDraw.Draw(image)
    step = (width - 4) / bins
    center = (height - 1) / 2

    for index in range(bins):
        x = 2 + (index + 0.5) * step
        bar_width = step * (0.90 - 0.40 * rhythm[index])
        if index in separators or index + 1 in separators:
            bar_width = min(bar_width, step * 0.25)

        radius = (height / 2 - 4) * energy[index]
        draw.rectangle(
            (
                round((x - bar_width / 2) * scale),
                round((center - radius) * scale),
                round((x + bar_width / 2) * scale),
                round((center + radius) * scale),
            ),
            fill=tuple(int(channel) for channel in colors[index]),
        )

    for index in separators:
        x = round((2 + index * step) * scale)
        for y in range(0, height, 7):
            draw.line(
                (x, y * scale, x, min(y + 4, height) * scale - 1),
                fill=SEPARATOR,
                width=2 * scale,
            )

    image = image.resize((width, height), Image.Resampling.LANCZOS)
    with atomic_output(output) as temporary:
        image.save(temporary, format="PNG", optimize=True)
