"""Erzeugt den FME-Alarmton (static/sounds/Westbummeln_FME_ZVEI.wav).

Klang wie ein Funkmeldeempfänger am Gürtel: kurz die ZVEI-Fünftonfolge, danach der typische
schrille Piezo-Weckton, ein schnelles Trillern zwischen zwei hohen Tönen in kurzen Piep-Gruppen.
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

# Piezo-Weckton: zwei hohe Töne im schnellen Wechsel (Triller)
TRILL_LOW, TRILL_HIGH = 2700, 3300
TRILL_STEP = 0.022  # Wechsel alle 22 ms -> schnelles „Trrrr“
BEEP, BEEP_GAP = 0.095, 0.035
BEEPS_PER_GROUP, GROUPS, GROUP_GAP = 4, 6, 0.22

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


def piezo(freqs, step, seconds, level):
    """Piezo-Summer: Rechteck-ähnlich (Grundton + 3. und 5. Oberton), Tonhöhe wechselt alle step s."""
    global phase
    n, fade = int(RATE * seconds), fade_len(seconds)
    for i in range(n):
        freq = freqs[int(i / RATE / step) % len(freqs)]
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
for _group in range(GROUPS):
    for _ in range(BEEPS_PER_GROUP):
        piezo([TRILL_LOW, TRILL_HIGH], TRILL_STEP, BEEP, 0.55)
        pause(BEEP_GAP)
    pause(GROUP_GAP)

with wave.open(sys.argv[1], 'wb') as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(RATE)
    w.writeframes(b''.join(struct.pack('<h', int(max(-1, min(1, s)) * 32767)) for s in samples))
print(f'{len(samples) / RATE:.2f} s')
