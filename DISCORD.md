# Westbummeln und Discord

Alle drei Funktionen sind einzeln zuschaltbar. Ohne die Einstellungen läuft das Spiel wie bisher.
Alle Werte trägst du auf dem Server in `/opt/westbummeln/.env` ein, nie in GitHub. Danach in
`/opt/westbummeln` `docker compose up -d` ausführen, damit der Webdienst die neuen Werte liest
(siehe `deploy/RUNBOOK.md`).

| Variable | Wofür |
|---|---|
| `DISCORD_WEBHOOK_URL` | Funkprotokoll im Discord-Kanal (Spiel → Discord) |
| `DISCORD_ROOM` | Raumcode, der gespiegelt wird (im Spiel Standard: `WESTBUMMELN`). Ohne Angabe werden alle Räume gespiegelt |
| `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID` | Discord-Kanal als Funk ins Spiel (Discord → Spiel), braucht `DISCORD_ROOM` |
| `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET` | Anmeldung mit Discord |
| `DISCORD_GUILD_ID` | Optional: nur Mitglieder deines Servers dürfen sich anmelden |
| `DISCORD_VOICE_URL` | Optional: Einladungslink (`https://discord.gg/...`) zum Sprachkanal, erscheint im Sprachfunk-Bereich |

## 1. Funkprotokoll in Discord (Webhook)
1. In Discord: Kanal → Zahnrad → **Integrationen** → **Webhooks** → **Neuer Webhook** → **Webhook-URL kopieren**.
2. In `.env` `DISCORD_WEBHOOK_URL` setzen, dazu `DISCORD_ROOM`.

Gespiegelt werden Funksprüche, Einsätze, Alarme und Status. Wetter-Meldungen nicht.
Pings (`@everyone`) und Link-Vorschauen sind abgeschaltet.

## 2. Discord-Kanal als Funk ins Spiel (Bot)
1. [discord.com/developers/applications](https://discord.com/developers/applications) → **New Application**.
2. Links **Bot** → **Reset Token** → Token kopieren (nur einmal sichtbar). Weiter unten **Message Content Intent** einschalten.
3. Links **OAuth2** → **URL Generator**: Haken bei `bot`, Rechte **View Channels** und **Read Message History**. Die erzeugte URL öffnen und den Bot auf deinen Server einladen.
4. In Discord: Einstellungen → Erweitert → **Entwicklermodus** an. Rechtsklick auf den Kanal → **Kanal-ID kopieren**.
5. In `.env` `DISCORD_BOT_TOKEN`, `DISCORD_CHANNEL_ID` und `DISCORD_ROOM` setzen.

Der Bot liest den Kanal alle 3 Sekunden mit. Nachrichten von Bots und Webhooks werden ignoriert, es gibt keine Schleife.

## 3. Anmeldung mit Discord
1. In derselben Anwendung links **OAuth2**: **Client ID** und **Client Secret** kopieren.
2. Unter **Redirects** hinzufügen: `https://planspiel.7z2.de/auth/discord/callback` (allgemein `https://<DOMAIN>/auth/discord/callback`, DOMAIN wie in `.env`) und speichern.
3. In `.env` `DISCORD_CLIENT_ID` und `DISCORD_CLIENT_SECRET` setzen.
4. Optional `DISCORD_GUILD_ID` (Server-ID kopieren wie die Kanal-ID) setzen.

Das Spiel speichert nur die Discord-ID und den Namen, keine Tokens. Der Spielername wird aus dem Discord-Benutzernamen gebildet. Ist er schon vergeben, kommt ein Zusatz wie `-a3f1` dazu.

## Grenzen
- **Sprachfunk:** Das Spiel kann keinen Ton zwischen dem Spiel und einem Discord-Sprachkanal übertragen. Mit `DISCORD_VOICE_URL` bekommen Spieler einen Knopf, der den Discord-Sprachkanal öffnet.
- **Neustart:** Während eines Deploys oder Neustarts (wenige Sekunden) spiegelt der Server nichts. Nachrichten aus dieser Zeit werden nicht nachgeholt.
- **Log:** `docker compose logs web | grep Discord:` zeigt Zeilen mit `Discord:`, zum Beispiel „Funkprotokoll wird gespiegelt“ oder Hinweise auf falsche Rechte.
