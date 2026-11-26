from django.http import HttpResponse


def health_check(get_response):
    """Antwortet auf /healthz, bevor Django den Host-Header prüft.

    Render ruft den Health-Check intern auf, der Host-Header ist dann nicht unbedingt die
    öffentliche Adresse und stünde nicht in ALLOWED_HOSTS."""

    def middleware(request):
        if request.path == '/healthz':
            return HttpResponse('ok', content_type='text/plain')
        return get_response(request)

    return middleware
