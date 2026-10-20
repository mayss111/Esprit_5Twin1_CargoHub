from django.contrib import admin

from .models import Contrat, DocumentTransport


@admin.register(Contrat)
class ContratAdmin(admin.ModelAdmin):
    pass


@admin.register(DocumentTransport)
class DocumentTransportAdmin(admin.ModelAdmin):
    pass
