from django.contrib import admin
from django.urls import path

from accounts import views as account_views
from game import views as game_views
from westbummeln import pwa

urlpatterns = [
    path('', game_views.index, name='index'),
    path('index.html', game_views.index),
    path('api', game_views.api, name='api'),
    path('developer', game_views.developer, name='developer'),
    path('account', account_views.account, name='account'),
    path('auth/discord', account_views.discord_start, name='discord_start'),
    path('auth/discord/callback', account_views.discord_callback, name='discord_callback'),
    path('admin/', admin.site.urls),
    path('manifest.webmanifest', pwa.manifest, name='manifest'),
    path('sw.js', pwa.service_worker, name='service_worker'),
    path('offline', pwa.offline, name='offline'),
    path('favicon.ico', pwa.root_file, {'name': 'favicon.ico'}),
    path('apple-touch-icon.png', pwa.root_file, {'name': 'apple-touch-icon.png'}),
]

handler404 = 'westbummeln.views.not_found'
handler500 = 'westbummeln.views.server_error'
