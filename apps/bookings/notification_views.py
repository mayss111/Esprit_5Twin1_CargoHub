from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView

from .models import Notification


class NotificationsView(LoginRequiredMixin, ListView):
    model = Notification
    template_name = "bookings/notifications.html"
    context_object_name = "notifications"
    paginate_by = 30

    def get_queryset(self):
        return Notification.objects.filter(destinataire=self.request.user).order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["notifications_non_lues"] = self.get_queryset().filter(lu=False).count()
        return context


class NotificationMarquerLueView(LoginRequiredMixin, View):
    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, destinataire=request.user)
        notification.lu = True
        notification.save(update_fields=["lu", "updated_at"])
        return redirect("bookings:notifications")


class NotificationsMarquerToutesLuesView(LoginRequiredMixin, View):
    def post(self, request):
        Notification.objects.filter(destinataire=request.user, lu=False).update(lu=True)
        return redirect("bookings:notifications")
