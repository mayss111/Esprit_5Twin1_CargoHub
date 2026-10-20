from django.contrib import admin

from .models import Conversation, Message, TicketSupport


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    pass


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    pass


@admin.register(TicketSupport)
class TicketSupportAdmin(admin.ModelAdmin):
    pass
