from django.apps import AppConfig


class GameConfig(AppConfig):
    name = 'game'
    verbose_name = 'Spiel'

    def ready(self):
        # Die Spiellogik kennt Django nicht; die KI-Werte aus den Settings werden hier übertragen.
        from django.conf import settings

        from game import engine
        for name in engine.AI_SETTINGS:
            setattr(engine, name, getattr(settings, name))
