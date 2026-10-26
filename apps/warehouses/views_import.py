"""Import administrateur d'entrepôts par fichier."""

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views import View

from apps.core.mixins import AdminRequiredMixin
from apps.warehouses.forms import ImportEntrepotsForm
from apps.warehouses.services.import_entrepots import contenu_csv, contenu_xlsx, importer


class BackofficeImporterEntrepotsView(AdminRequiredMixin, View):
    template_name = "warehouses/backoffice_importer.html"

    def get(self, request):
        return render(request, self.template_name, {"formulaire": ImportEntrepotsForm(), "erreurs": []})

    def post(self, request):
        formulaire = ImportEntrepotsForm(request.POST, request.FILES)
        if not formulaire.is_valid():
            return render(request, self.template_name, {"formulaire": formulaire, "erreurs": []})
        nombre, erreurs = importer(formulaire.cleaned_data["fichier"])
        if erreurs:
            messages.error(request, "Aucun entrepôt n'a été créé. Corrigez le fichier, puis importez-le de nouveau.")
            return render(request, self.template_name, {"formulaire": formulaire, "erreurs": erreurs})
        messages.success(
            request, f"{nombre} entrepôt{'s' if nombre > 1 else ''} enregistré{'s' if nombre > 1 else ''}."
        )
        return redirect("bo_warehouses:liste")


class ModeleImportEntrepotsView(AdminRequiredMixin, View):
    def get(self, request):
        if request.GET.get("format") == "xlsx":
            reponse = HttpResponse(
                contenu_xlsx(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            reponse["Content-Disposition"] = 'attachment; filename="modele-entrepots.xlsx"'
            return reponse
        reponse = HttpResponse(contenu_csv(), content_type="text/csv; charset=utf-8")
        reponse["Content-Disposition"] = 'attachment; filename="modele-entrepots.csv"'
        return reponse
