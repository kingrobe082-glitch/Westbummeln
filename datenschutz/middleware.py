import logging

from django.db import DatabaseError

from datenschutz.services import cleanup_if_due

logger = logging.getLogger(__name__)


def session_cleanup(get_response):
    """Nach einer Anfrage höchstens einmal pro Stunde abgelaufene Sitzungen löschen.

    Ein Fehler dabei darf die Antwort nie kaputtmachen; geloggt wird nur der Fehlertyp."""

    def middleware(request):
        response = get_response(request)
        try:
            cleanup_if_due()
        except DatabaseError as error:
            logger.warning('Abgelaufene Sitzungen konnten nicht gelöscht werden (%s).', type(error).__name__)
        return response

    return middleware
