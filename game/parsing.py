"""Eingaben aus Spieleranfragen prüfen, mit deutschen Fehlermeldungen statt Python-Fehlertexten."""


def to_int(value, label):
    """Ganze Zahl aus einer Spieleranfrage. Unbrauchbare Werte („abc“, null, NaN, unendlich) werden zu
    ValueError mit deutscher Meldung, die /api unverändert an den Spieler gibt."""
    try:
        return int(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f'{label}: bitte eine ganze Zahl angeben.') from None
