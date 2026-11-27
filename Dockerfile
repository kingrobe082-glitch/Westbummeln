# Produktions-Image für Westbummeln (Django + gunicorn + WhiteNoise).
# Gebaut von der GitHub Action (.github/workflows/release.yml) als
# ghcr.io/kingrobe082-glitch/westbummeln:<git-sha>. Betrieb: deploy/RUNBOOK.md.
# Python-Minor und Debian-Release fest. Patches und Debian-Sicherheitsupdates holt der wöchentliche
# Neubau (release.yml, schedule). Python-Upgrade: hier und in .python-version zusammen ändern.
FROM python:3.13-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# curl nur für den Healthcheck. Eigener Benutzer ohne Login-Shell, der Container läuft nie als root.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# collectstatic im Produktionsmodus, damit das WhiteNoise-Manifest (gehashte, komprimierte Dateien)
# entsteht. Die Pflichtwerte sind reine Build-Platzhalter: collectstatic verbindet sich nicht mit
# der Datenbank. Die echten Werte kommen zur Laufzeit aus /opt/westbummeln/.env.
RUN DJANGO_ENV=prod \
    SECRET_KEY=build-only-not-a-secret-0123456789abcdefghijklmnopqrstuvwxyz \
    DATABASE_URL=postgresql://build:build@build/build \
    ALLOWED_HOSTS=build \
    python manage.py collectstatic --noinput \
    && chmod +x /app/entrypoint.sh \
    && mkdir -p /app/state && chown app:app /app/state
# /app/state gehört app: Ein neues Docker-Volume (room-state) übernimmt beim ersten Einhängen diese
# Rechte, damit gunicorn dort die Spielräume sichern kann (game/persistence.py).

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

ENTRYPOINT ["./entrypoint.sh"]
CMD ["gunicorn", "westbummeln.wsgi:application", "-c", "gunicorn.conf.py"]
