from django.apps import AppConfig


class GameConfig(AppConfig):
    name = 'game'
    verbose_name = 'Spiel'

    def ready(self):
        # Die Spiellogik kennt Django nicht; KI- und Fahrzeit-Werte aus den Settings werden hier übertragen.
        from django.conf import settings

        from game import engine, strassen
        for name in engine.AI_SETTINGS:
            setattr(engine, name, getattr(settings, name))
        strassen.SPEED.update(settings.DRIVE_SPEED)
        engine.DEPARTURE_TIME = settings.DRIVE_DEPARTURE_TIME
