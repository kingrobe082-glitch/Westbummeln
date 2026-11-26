from django import forms

from moderation.bans import DURATIONS, REASON_MAX
from moderation.roles import ROLES


class BanForm(forms.Form):
    duration = forms.ChoiceField(label='Dauer', choices=[(key, label) for key, (label, _) in DURATIONS.items()],
                                 widget=forms.RadioSelect, initial='1d')
    reason = forms.CharField(label='Grund', max_length=REASON_MAX,
                             widget=forms.Textarea(attrs={'rows': 3, 'cols': 60}),
                             help_text='Nur für Moderation und Admins sichtbar, nicht für den gesperrten Spieler.')


class RoleForm(forms.Form):
    role = forms.ChoiceField(label='Rolle', choices=list(ROLES.items()), widget=forms.RadioSelect)
