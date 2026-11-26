class ModerationError(ValueError):
    """Moderationsaktion nicht erlaubt oder ungültig. Die Meldung ist deutsch und geht an die Oberfläche."""


class BannedError(ValueError):
    """Das Konto ist gesperrt. Die Meldung nennt das Sperrende."""
