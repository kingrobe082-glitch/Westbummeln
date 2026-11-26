from django.http import HttpResponse


def health_check(get_response):
    """Antwortet auf /healthz, bevor Django den Host-Header prüft.

    Docker (Healthcheck im Container) ruft ihn über 127.0.0.1 auf, der Host-Header ist dann nicht die
    öffentliche Adresse und stünde nicht in ALLOWED_HOSTS."""

    def middleware(request):
        if request.path == '/healthz':
            return HttpResponse('ok', content_type='text/plain')
        return get_response(request)

    return middleware
