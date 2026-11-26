from django.contrib import admin
from django.urls import path

from accounts import views as account_views
from datenschutz import views as datenschutz_views
from game import views as game_views

urlpatterns = [
    path('', game_views.index, name='index'),
    path('index.html', game_views.index),
    path('api', game_views.api, name='api'),
    path('developer', game_views.developer, name='developer'),
    path('account', account_views.account, name='account'),
    path('account/export', datenschutz_views.export, name='account_export'),
    path('datenschutz', datenschutz_views.privacy, name='datenschutz'),
    path('auth/discord', account_views.discord_start, name='discord_start'),
    path('auth/discord/callback', account_views.discord_callback, name='discord_callback'),
    path('admin/', admin.site.urls),
]

handler404 = 'westbummeln.views.not_found'
handler500 = 'westbummeln.views.server_error'
