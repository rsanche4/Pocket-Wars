"""Makes the game's sound effects as WAV files in assets/sfx/, Game Boy Advance style: square-ish pulse waves and the
GBA's noise generator. Run once:  py tools/make_sfx.py   (it overwrites the files, so don't run it after replacing
sounds with your own - or pass names to make just those:  py tools/make_sfx.py cursor select)

Each sound below is a short recipe: tone(frequency, seconds, wave, volume, slide-to, start) and
noise(seconds, volume, pitch, start, metallic, pitch-to). nt(n) is the frequency of note number n (69 = A440).
"""
import os
import struct
import sys
import wave

RATE = 22050
GAIN = 1.4          # overall loudness (the game then scales by the Effects Volume option)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def nt(n):
    return 440 * 2 ** ((n - 69) / 12)


class Sound:
    def __init__(self):
        self.buf = [0.0] * (RATE * 3)
        self.end = 0

    def tone(self, f, d, w='p50', v=.05, slide=None, at=0):
        """A note. Waves: p12 / p25 / p50 = pulse waves (the GBA's square channels), tri, saw.
        It holds its volume for the first half, then fades away."""
        start, n = int(at * RATE), int(d * RATE)
        duty = {'p12': .125, 'p25': .25, 'p50': .5}.get(w)
        phase = 0.0
        for i in range(n):
            t = i / RATE
            freq = f * (slide / f) ** (t / d) if slide else f
            phase = (phase + freq / RATE) % 1
            if duty:
                s = (1 if phase < duty else -1) - (2 * duty - 1)       # pulse wave, centred
            elif w == 'tri':
                s = 4 * abs(phase - .5) - 1
            else:
                s = 2 * phase - 1
            env = v if t < d / 2 else v * (.0001 / v) ** ((t - d / 2) / (d / 2))
            self.buf[start + i] += s * env
        self.end = max(self.end, start + n)

    def noise(self, d, v=.2, clock=8000, at=0, metallic=False, clock_to=None):
        """Noise from a 15-bit shift register, like the GBA (metallic = its short 7-bit mode).
        clock is how fast it steps: higher = hissier. The volume fades from the start."""
        start, n = int(at * RATE), int(d * RATE)
        reg, pos = 0x7FFF, 0.0
        for i in range(n):
            t = i / RATE
            c = clock * (clock_to / clock) ** (t / d) if clock_to else clock
            pos += c / RATE
            while pos >= 1:
                pos -= 1
                bit = (reg ^ (reg >> 1)) & 1
                reg = (reg >> 1) | (bit << 14)
                if metallic:
                    reg = (reg & ~0x40) | (bit << 6)
            self.buf[start + i] += (.8 if reg & 1 else -.8) * v * (.0001 / v) ** (t / d)
        self.end = max(self.end, start + n)

    def seq(self, notes, step, w='p25', v=.045, length=None):
        for k, n in enumerate(notes):
            if n:
                self.tone(nt(n), length or step * .95, w, v, None, k * step)

    def save(self, name):
        path = os.path.join(ROOT, 'assets', 'sfx', name + '.wav')
        samples = [max(-1, min(1, s * GAIN)) for s in self.buf[:self.end + RATE // 50]]
        with wave.open(path, 'wb') as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(RATE)
            f.writeframes(b''.join(struct.pack('<h', round(s * 32767)) for s in samples))
        return max(abs(s * GAIN) for s in self.buf[:self.end] or [0])


def step_heli(s):
    s.noise(.05, .09, 2400, 0, True)


RECIPES = {
    # menus
    'cursor': lambda s: s.tone(nt(91), .028, 'p25', .03),                              # menu highlight moves
    'adjust': lambda s: (s.tone(nt(88), .025, 'p25', .03), s.tone(nt(93), .025, 'p25', .025, None, .026)),
    'select': lambda s: s.seq([84, 91], .042, 'p25', .042),
    'back': lambda s: s.seq([79, 72], .042, 'p25', .038),
    'error': lambda s: (s.tone(nt(43), .08, 'p50', .045), s.tone(nt(42), .11, 'p50', .045, None, .085)),
    'open': lambda s: s.tone(nt(72), .07, 'p25', .035, nt(84)),                          # a command / pause menu opens
    'page': lambda s: (s.noise(.07, .05, 30000, 0, False, 7000), s.tone(nt(86), .03, 'p12', .025, None, .03)),
    # title intro
    'slam': lambda s: (s.noise(.32, .28, 4000, 0, False, 500), s.tone(nt(33), .3, 'p50', .07, nt(21))),
    'shine': lambda s: s.seq([88, 91, 96, 100, 103], .045, 'p12', .03),
    # on the map
    'map_cursor': lambda s: s.tone(nt(84), .02, 'p12', .028),
    'turn_green': lambda s: (s.seq([72, 76, 79, 84, 0, 79, 84], .065, 'p25', .04), s.seq([48, 0, 55, 0, 48], .13, 'tri', .07)),
    'turn_tan': lambda s: (s.seq([69, 72, 76, 81, 0, 76, 81], .065, 'p25', .04), s.seq([45, 0, 52, 0, 45], .13, 'tri', .07)),
    'march_phase': lambda s: s.seq([67, 72, 76], .05, 'p50', .035),
    'attack_phase': lambda s: (s.seq([76, 0, 76, 81], .05, 'p50', .04), s.noise(.12, .06, 12000, .15)),
    'place': lambda s: (s.tone(nt(81), .04, 'p25', .04), s.tone(nt(88), .06, 'p25', .035, None, .04)),
    'buy': lambda s: (s.seq([72, 76, 79, 84, 88], .04, 'p25', .04), s.tone(nt(96), .16, 'p12', .03, None, .21)),
    'step_soldier': lambda s: s.noise(.035, .07, 5200),                                 # marching, played every step
    'step_vehicle': lambda s: (s.noise(.1, .06, 1800), s.tone(58, .1, 'p50', .025)),
    'step_heli': step_heli,
    'capture': lambda s: (s.seq([76, 79, 84, 88], .055, 'p25', .04), s.tone(nt(91), .18, 'p12', .03, None, .22)),
    # battle
    'shot_soldier': lambda s: (s.noise(.07, .16, 24000, 0, False, 5000), s.noise(.07, .13, 24000, .09, False, 5000)),
    'shot_halftrack': lambda s: [s.noise(.04, .13, 20000, k * .055, False, 8000) for k in range(5)],
    'shot_tank': lambda s: (s.noise(.45, .3, 7000, 0, False, 300), s.tone(nt(28), .35, 'p50', .07, nt(16))),
    'shot_helicopter': lambda s: [(s.noise(.28, .1, 12000, at, False, 2000), s.tone(nt(84), .25, 'saw', .02, nt(60), at)) for at in (0, .12)],
    'shot_hq': lambda s: (s.noise(.5, .3, 5000, 0, False, 250), s.tone(nt(26), .45, 'p50', .07, nt(14))),
    'hit': lambda s: s.noise(.32, .24, 5000, 0, False, 450),
    'destroyed': lambda s: (s.noise(.75, .32, 6000, 0, False, 150), s.seq([64, 60, 55, 48], .07, 'p50', .035)),
    'hq_hit': lambda s: [s.tone(nt(81), .11, 'p50', .035, nt(76), k * .14) for k in range(3)],     # alarm
    'cleared': lambda s: s.seq([79, 84, 79, 91], .06, 'p25', .042),
    # timer, end of game, editor
    'tick': lambda s: s.tone(nt(86), .03, 'p25', .028),
    'tick_last': lambda s: s.tone(nt(93), .05, 'p50', .038),
    'time_up': lambda s: (s.tone(nt(69), .15, 'p50', .05, nt(57)), s.tone(nt(57), .3, 'p50', .05, nt(45), .15)),
    'victory': lambda s: (s.seq([72, 72, 72, 76, 79, 0, 76, 79, 84], .11, 'p25', .05, .1), s.seq([48, 0, 0, 52, 55, 0, 52, 55, 60], .11, 'tri', .08, .1)),
    'defeat': lambda s: (s.seq([67, 66, 65, 64], .2, 'p50', .045, .19), s.seq([43, 42, 41, 40], .2, 'tri', .07, .19)),
    'save': lambda s: s.seq([84, 88, 91], .05, 'p12', .04),
}

if __name__ == '__main__':
    os.makedirs(os.path.join(ROOT, 'assets', 'sfx'), exist_ok=True)
    for name in sys.argv[1:] or RECIPES:
        s = Sound()
        RECIPES[name](s)
        peak = s.save(name)
        print(f"{name:16s} {s.end / RATE:5.2f}s  peak {peak:.2f}{'  (clipped)' if peak > 1 else ''}")
