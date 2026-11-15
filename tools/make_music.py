"""Placeholder chiptune music for Pocket Wars:  py tools/make_music.py  ->  assets/music/*.mp3
Needs numpy (py -m pip install numpy) and ffmpeg on the PATH. It overwrites the files, so don't run it after
replacing the music with your own (keep the names title, battle, victory; MP3 or OGG).

Each track is written as notes below (a tiny tracker): "C5:2" = the note C5 for 2 steps, "R" = rest.
Loops should start and end on a bar line.
"""
import os
import subprocess
import tempfile
import wave

import numpy as np

SR = 22050
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOTE = {'C': 0, 'C#': 1, 'D': 2, 'D#': 3, 'E': 4, 'F': 5, 'F#': 6, 'G': 7, 'G#': 8, 'A': 9, 'A#': 10, 'B': 11}


def hz(n):
    name, octave = n[:-1], int(n[-1])
    return 440 * 2 ** ((NOTE[name] + 12 * (octave + 1) - 69) / 12)


def osc(kind, f, n, duty=.5):
    """n samples of a square ('sq') or triangle ('tri') wave."""
    phase = (np.arange(n) / SR * f) % 1
    if kind == 'sq':
        return np.where(phase < duty, 1., -1.)
    if kind == 'tri':
        return 4 * np.abs(phase - .5) - 1
    raise ValueError(kind)


def env(n, a=.004, d=.08, s=.6, r=.03):
    """Attack, decay, sustain level, release."""
    e = np.ones(n) * s
    A, D, R = int(a * SR), int(d * SR), int(r * SR)
    e[:A] = np.linspace(0, 1, A)
    e[A:A + D] = np.linspace(1, s, min(D, max(0, n - A)))[:len(e[A:A + D])]
    if n > R:
        e[-R:] *= np.linspace(1, 0, R)
    return e


def voice(seq, step, kind, vol, duty=.5, d=.08, s=.6):
    """seq: a list of (note or 'R', length in steps)."""
    out = []
    for note, length in seq:
        n = int(round(length * step * SR))
        out.append(np.zeros(n) if note == 'R' else osc(kind, hz(note), n, duty) * env(n, d=d, s=s) * vol)
    return np.concatenate(out)


def drums(pattern, step, bars, vol=.25):
    """pattern: one bar, one character per step: k kick, s snare, h hat, . rest."""
    n, rng, out = int(round(step * SR)), np.random.default_rng(1), []
    t = np.arange(n) / SR
    for _ in range(bars):
        for ch in pattern:
            x = np.zeros(n)
            if ch == 'k':
                f = 120 * np.exp(-t * 30) + 45
                x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 18) * 1.2
            elif ch == 's':
                x = rng.uniform(-1, 1, n) * np.exp(-t * 22) * .8
            elif ch == 'h':
                x = rng.uniform(-1, 1, n) * np.exp(-t * 90) * .35
            out.append(x * vol)
    return np.concatenate(out)


def bassline(chords, octave=2, pattern='root5'):
    """One bar per chord: root and fifth ('root5'), or a driving root with a fifth at the end ('drive')."""
    seq = []
    for c in chords:
        root = c.rstrip('m')
        fifth = (NOTE[root] + 7) % 12
        names = [k for k, v in NOTE.items() if v == fifth and '#' not in k] or [k for k, v in NOTE.items() if v == fifth]
        r, f5 = f'{root}{octave}', f'{names[0]}{octave + (1 if fifth < NOTE[root] else 0)}'
        seq += [(r, 2), (f5, 2), (r, 2), (f5, 2)] if pattern == 'root5' else [(r, 1)] * 6 + [(f5, 1), (r, 1)]
    return seq


def arpeggio(chords):
    """Eight quick notes per chord, cycling through its triad."""
    names = {v: k for k, v in NOTE.items() if '#' not in k}
    names.update({8: 'G#', 1: 'C#', 6: 'F#'})
    seq = []
    for c in chords:
        r = NOTE[c.rstrip('m')]
        triad = [r, r + (3 if c.endswith('m') else 4), r + 7]
        for i in range(8):
            v = triad[i % 3]
            seq.append((names.get(v % 12, 'A') + str(4 + v // 12), 1))
    return seq


def mix(*tracks):
    m = np.zeros(max(len(t) for t in tracks))
    for t in tracks:
        m[:len(t)] += t
    return m / max(1e-9, np.abs(m).max()) * .85


def parse(s):
    return [(note, float(length)) for note, length in (tok.split(':') for tok in s.split())]


def save(name, x):
    folder = os.path.join(ROOT, 'assets', 'music')
    os.makedirs(folder, exist_ok=True)
    mp3 = os.path.join(folder, name + '.mp3')
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, name + '.wav')
        with wave.open(wav, 'wb') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((x * 32767).astype('<i2').tobytes())
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', wav, '-codec:a', 'libmp3lame', '-b:a', '64k', mp3], check=True)
    print(name, f'{len(x) / SR:.1f}s', os.path.getsize(mp3) // 1024, 'KB')


def title():
    """A bright march in C."""
    step = 60 / 116 / 2   # eighth notes at 116 bpm
    lead = parse('G4:2 C5:2 E5:2 G5:2  F5:3 E5:1 D5:2 C5:2  D5:2 E5:2 F5:2 A5:2  G5:6 R:2 '
                 'E5:2 G5:2 C6:3 B5:1  A5:2 G5:2 F5:2 E5:2  D5:2 F5:2 E5:2 D5:2  C5:6 R:2 '
                 'E5:1 F5:1 G5:2 G5:2 A5:2  G5:2 F5:2 E5:2 C5:2  F5:1 G5:1 A5:2 A5:2 B5:2  C6:4 G5:4 '
                 'A5:2 F5:2 G5:2 E5:2  F5:2 D5:2 E5:2 C5:2  D5:2 G4:2 B4:2 D5:2  C5:6 R:2')
    harmony = [(n if n == 'R' else n[:-1] + str(int(n[-1]) - 1), length) for n, length in lead]     # an octave down
    chords = ['C', 'F', 'Dm', 'G', 'C', 'F', 'G', 'C', 'C', 'C', 'F', 'C', 'F', 'C', 'G', 'C']
    return mix(voice(lead, step, 'sq', .5, .5), voice(harmony, step, 'sq', .18, .25),
               voice(bassline(chords), step, 'tri', .55, d=.2, s=.8), drums('k.h.s.h.k.h.s.hh', step / 2, 16))


def battle():
    """Driving A minor."""
    step = 60 / 148 / 2
    lead = parse('A4:1 C5:1 E5:1 A5:1 G5:2 E5:2  F5:2 E5:1 D5:1 E5:4  C5:1 D5:1 E5:1 F5:1 G5:2 F5:2  E5:2 D5:2 B4:4 '
                 'A4:1 C5:1 E5:1 A5:1 B5:2 C6:2  B5:2 A5:1 G5:1 A5:4  F5:2 A5:2 G5:2 E5:2  E5:2 G#5:2 B5:4 '
                 'A5:2 R:1 A5:1 G5:2 E5:2  F5:2 R:1 F5:1 E5:2 C5:2  D5:2 R:1 D5:1 E5:2 F5:2  E5:6 R:2 '
                 'A5:2 R:1 A5:1 C6:2 A5:2  G5:2 R:1 G5:1 F5:2 D5:2  E5:2 F5:2 G#5:2 B5:2  A5:6 R:2')
    chords = ['Am', 'Am', 'F', 'G', 'Am', 'Am', 'F', 'E', 'F', 'F', 'G', 'E', 'F', 'G', 'E', 'Am']
    return mix(voice(lead, step, 'sq', .45, .5), voice(arpeggio(chords), step, 'sq', .12, .125, d=.03, s=.3),
               voice(bassline(chords, pattern='drive'), step, 'tri', .6, d=.05, s=.9),
               drums('k.hhs.hhk.hks.hh', step / 2, 16, .28))


def victory():
    """A short fanfare (plays once)."""
    step = 60 / 150 / 2
    lead = parse('G4:1 C5:1 E5:1 G5:3 E5:1 G5:5  A5:1 G5:1 F5:1 E5:1 F5:1 G5:1 C6:8')
    bass = parse('C3:2 C3:2 G2:2 C3:4 F2:2 G2:2 G2:2 C3:8')
    melody = voice(lead, step, 'sq', .5, .5, s=.7)
    return mix(melody, voice(bass, step, 'tri', .6, d=.2, s=.8), drums('k.s.k.sskskskk..', step / 2, 3, .25)[:len(melody)])


if __name__ == '__main__':
    for name, make in (('title', title), ('battle', battle), ('victory', victory)):
        save(name, make())
