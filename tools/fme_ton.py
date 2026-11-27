"""Erzeugt einen eigenen FME-Alarmton (ZVEI-1-Fünftonfolge + Weckton) als WAV.

Alles synthetisch erzeugt, keine Aufnahme. Aufruf: python tools/fme_ton.py static/sounds/Westbummeln_FME_ZVEI.wav
"""
import math
import struct
import sys
import wave

RATE = 22050
# ZVEI 1: Ziffer -> Frequenz in Hz, R = Wiederholton
ZVEI1 = {'0': 2400, '1': 1060, '2': 1160, '3': 1270, '4': 1400, '5': 1530,
         '6': 1670, '7': 1830, '8': 2000, '9': 2200, 'R': 2600}
CODE = '25431'  # fiktive Schleife „Westbummeln LZ“
TONE = 0.070     # 70 ms je Ton (ZVEI-Norm)

samples = []


def tone(freq, seconds, level=0.55, freq2=None):
    n = int(RATE * seconds)
    fade = int(RATE * 0.004)
    for i in range(n):
        t = i / RATE
        v = math.sin(2 * math.pi * freq * t)
        if freq2:
            v = (v + math.sin(2 * math.pi * freq2 * t)) / 2
        env = min(1, i / fade, (n - 1 - i) / fade) if fade else 1
        samples.append(v * level * env)


def pause(seconds):
    samples.extend([0.0] * int(RATE * seconds))


def five_tone(code):
    last = None
    for digit in code:
        d = 'R' if digit == last else digit
        tone(ZVEI1[d], TONE)
        last = digit


pause(0.05)
five_tone(CODE)
pause(0.45)
five_tone(CODE)
pause(0.35)
# Weckton: dreimal steigender Zweiklang, danach ein langer Doppelton
for _ in range(3):
    tone(1060, 0.16)
    pause(0.03)
    tone(1400, 0.16)
    pause(0.03)
    tone(1830, 0.22)
    pause(0.18)
tone(1060, 0.9, level=0.45, freq2=1400)
pause(0.1)

with wave.open(sys.argv[1], 'wb') as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(RATE)
    w.writeframes(b''.join(struct.pack('<h', int(max(-1, min(1, s)) * 32767)) for s in samples))
print(f'{len(samples) / RATE:.2f} s')
