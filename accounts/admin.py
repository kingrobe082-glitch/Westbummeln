from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts.models import User


@admin.register(User)
class AccountAdmin(UserAdmin):
    list_display = ('username', 'email', 'is_staff', 'is_active', 'date_joined', 'last_login')
    search_fields = ('username', 'email', 'google_sub', 'discord_sub')
    fieldsets = UserAdmin.fieldsets + (('Verknüpfte Anmeldungen', {'fields': ('google_sub', 'discord_sub')}),)
