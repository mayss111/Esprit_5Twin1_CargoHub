from django.contrib import admin

from .models import CertificatEco, EmpreinteCarbone


@admin.register(EmpreinteCarbone)
class EmpreinteCarboneAdmin(admin.ModelAdmin):
    pass


@admin.register(CertificatEco)
class CertificatEcoAdmin(admin.ModelAdmin):
    pass
