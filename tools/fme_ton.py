"""Erzeugt den FME-Alarmton (static/sounds/Westbummeln_FME_ZVEI.wav).

Klang wie ein Funkmeldeempfänger am Gürtel, genau 10 Sekunden:
2x ZVEI · A-C-A-B · 3x ZVEI · A-C-A-B · 2x ZVEI · A-C-A-B · 3x ZVEI · A-C-A-B.
ZVEI = Fünftonfolge der (fiktiven) Schleife, A-C-A-B = kurze Piezo-Pieps („pip pip“).
Alles synthetisch erzeugt, keine Aufnahme.

Aufruf: python tools/fme_ton.py static/sounds/Westbummeln_FME_ZVEI.wav
"""
import math
import struct
import sys
import wave

RATE = 44100
TOTAL = 10.0  # Gesamtlänge in Sekunden (Rest wird mit Stille aufgefüllt)

# ZVEI 1: Ziffer -> Frequenz in Hz, R = Wiederholton
ZVEI1 = {'0': 2400, '1': 1060, '2': 1160, '3': 1270, '4': 1400, '5': 1530,
         '6': 1670, '7': 1830, '8': 2000, '9': 2200, 'R': 2600}
CODE = '25431'     # fiktive Schleife „Westbummeln LZ“
ZVEI_TONE = 0.070  # 70 ms je Ton (ZVEI-Norm)
ZVEI_GAP = 0.15    # Pause zwischen zwei Fünftonfolgen eines Blocks

# Weckton: Noten in der 6. Oktave (hell wie ein Melder). B = deutsches B (1864,7 Hz).
NOTES = {'A': 1760.0, 'C': 2093.0, 'B': 1864.66, 'H': 1975.53}
MELODY = 'ACAB'
PIP, PIP_GAP = 0.11, 0.07  # kurzer Pieps, kurze Lücke -> „pip pip pip pip“
BLOCK_GAP = 0.30           # Pause nach jedem ZVEI-Block und jeder A-C-A-B-Runde

# Muster: so oft kommt die Fünftonfolge vor jeder A-C-A-B-Runde
PATTERN = (2, 3, 2, 3)

samples = []
phase = 0.0


def fade_len(seconds):
    return max(1, int(RATE * min(0.003, seconds / 4)))


def sine(freq, seconds, level):
    global phase
    n, fade = int(RATE * seconds), fade_len(seconds)
    for i in range(n):
        phase += 2 * math.pi * freq / RATE
        env = min(1, i / fade, (n - 1 - i) / fade)
        samples.append(math.sin(phase) * level * env)


def pip(freq, seconds, level):
    """Piezo-Pieps: Rechteck-ähnlich (Grundton + 3. und 5. Oberton), feste Tonhöhe."""
    global phase
    n, fade = int(RATE * seconds), fade_len(seconds)
    for i in range(n):
        phase += 2 * math.pi * freq / RATE
        v = math.sin(phase) + math.sin(3 * phase) / 3
        if 5 * freq < RATE / 2:
            v += math.sin(5 * phase) / 5
        env = min(1, i / fade, (n - 1 - i) / fade)
        samples.append(v / 1.3 * level * env)


def pause(seconds):
    samples.extend([0.0] * int(RATE * seconds))


def five_tone(code):
    last = None
    for digit in code:
        sine(ZVEI1['R' if digit == last else digit], ZVEI_TONE, 0.35)
        last = digit


def zvei_block(times):
    for i in range(times):
        five_tone(CODE)
        pause(ZVEI_GAP if i < times - 1 else BLOCK_GAP)


def weckton():
    for note in MELODY:
        pip(NOTES[note], PIP, 0.55)
        pause(PIP_GAP)
    pause(BLOCK_GAP)


pause(0.03)
for times in PATTERN:
    zvei_block(times)
    weckton()
assert len(samples) <= RATE * TOTAL, f'Ton länger als {TOTAL} s'
pause(TOTAL - len(samples) / RATE)

with wave.open(sys.argv[1], 'wb') as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(RATE)
    w.writeframes(b''.join(struct.pack('<h', int(max(-1, min(1, s)) * 32767)) for s in samples))
print(f'{len(samples) / RATE:.2f} s')
