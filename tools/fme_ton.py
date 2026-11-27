"""Erzeugt den FME-Alarmton (static/sounds/Westbummeln_FME_ZVEI.wav).

Klang wie ein Funkmeldeempfänger am Gürtel: kurz die ZVEI-Fünftonfolge, danach der Weckton
als einzelne kurze Piezo-Pieps („pip pip“) in der Tonfolge A-C-A-B, mehrmals wiederholt.
Alles synthetisch erzeugt, keine Aufnahme.

Aufruf: python tools/fme_ton.py static/sounds/Westbummeln_FME_ZVEI.wav
"""
import math
import struct
import sys
import wave

RATE = 44100
# ZVEI 1: Ziffer -> Frequenz in Hz, R = Wiederholton
ZVEI1 = {'0': 2400, '1': 1060, '2': 1160, '3': 1270, '4': 1400, '5': 1530,
         '6': 1670, '7': 1830, '8': 2000, '9': 2200, 'R': 2600}
CODE = '25431'   # fiktive Schleife „Westbummeln LZ“
ZVEI_TONE = 0.070  # 70 ms je Ton (ZVEI-Norm)

# Weckton: Noten in der 6. Oktave (hell wie ein Melder). B = deutsches B (B-Dur-Grundton, 1864,7 Hz).
NOTES = {'A': 1760.0, 'C': 2093.0, 'B': 1864.66, 'H': 1975.53}
MELODY = 'ACAB'
PIP, PIP_GAP = 0.11, 0.07      # kurzer Pieps, kurze Lücke -> „pip pip pip pip“
ROUNDS, ROUND_GAP = 5, 0.30

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
        d = 'R' if digit == last else digit
        sine(ZVEI1[d], ZVEI_TONE, 0.35)
        last = digit


pause(0.03)
five_tone(CODE)
pause(0.30)
for _round in range(ROUNDS):
    for note in MELODY:
        pip(NOTES[note], PIP, 0.55)
        pause(PIP_GAP)
    pause(ROUND_GAP)

with wave.open(sys.argv[1], 'wb') as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(RATE)
    w.writeframes(b''.join(struct.pack('<h', int(max(-1, min(1, s)) * 32767)) for s in samples))
print(f'{len(samples) / RATE:.2f} s')
