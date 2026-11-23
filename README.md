# Westbummeln – Multiplayer-Webseite

Diese Webseite läuft auf einem Python-Webserver und kann über einen Hosting-Anbieter online gestellt werden.

## Lokal testen

Python 3 installieren, im Ordner `python server.py` ausführen und `http://localhost:8765` öffnen.

## Online mit Render bereitstellen

1. Kostenloses GitHub-Konto und Render-Konto erstellen (gegebenenfalls mit Unterstützung eines Erwachsenen).
2. Neues GitHub-Repository anlegen und die Dateien `index.html`, `server.py`, `render.yaml` hochladen.
3. Bei Render **New > Blueprint** wählen, das GitHub-Repository verbinden und die `render.yaml` verwenden.
4. Nach dem Deploy den von Render bereitgestellten HTTPS-Link öffnen und an Mitspieler weitergeben.
5. Alle verwenden denselben Raumcode.

**Wichtig:** Die kostenlose Hosting-Stufe kann einschlafen. Die Spieldaten sind momentan nur im Arbeitsspeicher und gehen bei Neustarts verloren. Es gibt noch keine Konten oder private Zugangssicherung. Teile den Raumcode nur mit vertrauten Personen. Diese Webseite ist ein Multiplayer-Prototyp, noch nicht das komplette Einzelspieler-Spiel mit Karte und Grafiken.
