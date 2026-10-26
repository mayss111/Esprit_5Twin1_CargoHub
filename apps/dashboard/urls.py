from django.urls import path

from . import views

app_name = "dashboard"
urlpatterns = [
    path("", views.AccueilBackofficeView.as_view(), name="accueil"),
    path("export.xlsx", views.ExportExcelView.as_view(), name="export_excel"),
    path("export.pdf", views.ExportPdfView.as_view(), name="export_pdf"),
]
