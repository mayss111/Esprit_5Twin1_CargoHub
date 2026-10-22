from datetime import timedelta

from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Utilisateur
from apps.bookings.models import Reservation
from apps.core.roles import Role
from apps.shipments.forms import SaisieExpedition
from apps.shipments.models import Expedition


def test_admin_liste_les_expeditions(client, admin_user, expedition):
    client.force_login(admin_user)
    reponse = client.get(reverse("admin:shipments_expedition_changelist"))
    assert reponse.status_code == 200
    assert expedition.reference in reponse.content.decode()


def test_admin_fiche_expedition_affiche_les_articles(client, admin_user, expedition):
    client.force_login(admin_user)
    reponse = client.get(reverse("admin:shipments_expedition_change", args=[expedition.pk]))
    assert reponse.status_code == 200
    assert "Cartons de vêtements" in reponse.content.decode()
    assert expedition.reference in reponse.content.decode()


def test_pme_ne_ouvre_pas_ladmin_des_expeditions(client, pme):
    client.force_login(pme)
    reponse = client.get(reverse("admin:shipments_expedition_changelist"))
    assert reponse.status_code == 302
    assert "django-admin" in reponse.url


def _donnees(date, articles, initial=0):
    donnees = {
        "depart-ligne": "Zone industrielle",
        "depart-ville": "Monastir",
        "depart-gouvernorat": "Monastir",
        "depart-code_postal": "5000",
        "arrivee-ligne": "Rue de Marseille",
        "arrivee-ville": "Tunis",
        "arrivee-gouvernorat": "Tunis",
        "arrivee-code_postal": "1000",
        "generale-date_souhaitee": date.isoformat(),
        "generale-description": "Envoi textile",
        "articles-TOTAL_FORMS": str(len(articles)),
        "articles-INITIAL_FORMS": str(initial),
        "articles-MIN_NUM_FORMS": "0",
        "articles-MAX_NUM_FORMS": "30",
    }
    for index, article in enumerate(articles):
        prefixe = f"articles-{index}-"
        donnees[prefixe + "designation"] = article.get("designation", "Cartons")
        donnees[prefixe + "description"] = article.get("description", "")
        donnees[prefixe + "type_marchandise"] = article.get("type_marchandise", "TEXTILE")
        donnees[prefixe + "quantite"] = str(article.get("quantite", 2))
        donnees[prefixe + "poids_kg"] = str(article.get("poids_kg", "10"))
        donnees[prefixe + "volume_m3"] = str(article.get("volume_m3", "0.200"))
        donnees[prefixe + "valeur_declaree"] = article.get("valeur_declaree", "")
        if article.get("id"):
            donnees[prefixe + "id"] = str(article["id"])
    return donnees


def _article(**extra):
    article = {"designation": "Cartons de vêtements", "quantite": 2, "poids_kg": "10", "volume_m3": "0.200"}
    article.update(extra)
    return article


def test_brouillon_valide_sans_article(pme):
    date = timezone.localdate() + timedelta(days=3)
    saisie = SaisieExpedition(_donnees(date, []), pme=pme, publier=False)
    assert saisie.is_valid(), saisie.generale.errors
    expedition = saisie.save()
    assert expedition.statut == Expedition.Statut.BROUILLON
    assert expedition.reference.startswith("CH-")
    assert expedition.articles.count() == 0
    assert expedition.adresse_depart.gouvernorat == "Monastir"


def test_publication_valide_avec_un_article(pme):
    date = timezone.localdate() + timedelta(days=3)
    saisie = SaisieExpedition(_donnees(date, [_article()]), pme=pme, publier=True)
    assert saisie.is_valid(), saisie.generale.errors
    expedition = saisie.save()
    assert expedition.statut == Expedition.Statut.PUBLIEE
    assert expedition.articles.count() == 1
    assert expedition.poids_total_kg == 20


def test_publication_sans_article_refusee(pme):
    date = timezone.localdate() + timedelta(days=3)
    saisie = SaisieExpedition(_donnees(date, []), pme=pme, publier=True)
    assert not saisie.is_valid()
    assert "au moins un article" in saisie.generale.non_field_errors()[0]


def test_poids_quantite_et_volume_invalides(pme):
    date = timezone.localdate() + timedelta(days=3)
    saisie = SaisieExpedition(
        _donnees(date, [_article(quantite=0, poids_kg="0", volume_m3="0")]),
        pme=pme,
        publier=True,
    )
    assert not saisie.is_valid()
    erreurs = saisie.articles.errors[0]
    assert "quantité" in erreurs["quantite"][0].lower()
    assert "poids" in erreurs["poids_kg"][0].lower()
    assert "volume" in erreurs["volume_m3"][0].lower()


def test_categorie_interdite_bloquee_a_la_publication(pme):
    date = timezone.localdate() + timedelta(days=3)
    article = _article(type_marchandise="INTERDIT", designation="Produit interdit")
    publication = SaisieExpedition(_donnees(date, [article]), pme=pme, publier=True)
    assert not publication.is_valid()
    assert "interdite" in publication.generale.non_field_errors()[0]

    brouillon = SaisieExpedition(_donnees(date, [article]), pme=pme, publier=False)
    assert brouillon.is_valid(), brouillon.generale.errors


def test_date_passee_refusee_a_la_creation(pme):
    hier = timezone.localdate() - timedelta(days=1)
    saisie = SaisieExpedition(_donnees(hier, [_article()]), pme=pme, publier=False)
    assert not saisie.is_valid()
    assert "passé" in saisie.generale.errors["date_souhaitee"][0]


def test_adresse_obligatoire(pme):
    date = timezone.localdate() + timedelta(days=3)
    donnees = _donnees(date, [_article()])
    donnees["depart-ligne"] = ""
    saisie = SaisieExpedition(donnees, pme=pme, publier=True)
    assert not saisie.is_valid()
    assert saisie.depart.errors["ligne"]


def test_modification_d_un_brouillon(pme):
    date = timezone.localdate() + timedelta(days=4)
    creee = SaisieExpedition(_donnees(date, [_article()]), pme=pme, publier=False).save()
    article = creee.articles.get()
    nouvelles = _donnees(
        date,
        [_article(id=article.pk, designation="Balles de tissu", quantite=3)],
        initial=1,
    )
    saisie = SaisieExpedition(nouvelles, expedition=creee, publier=False)
    assert saisie.is_valid(), (saisie.generale.errors, saisie.articles.errors)
    modifiee = saisie.save()
    assert modifiee.pk == creee.pk
    assert modifiee.articles.get().designation == "Balles de tissu"
    assert modifiee.statut == Expedition.Statut.BROUILLON


def test_modification_impossible_si_reservation_confirmee(pme, expedition, trajet):
    Reservation.objects.create(expedition=expedition, trajet=trajet, statut=Reservation.Statut.ACCEPTEE)
    date = expedition.date_souhaitee
    article = expedition.articles.get()
    donnees = _donnees(date, [_article(id=article.pk)], initial=1)
    saisie = SaisieExpedition(donnees, expedition=expedition, publier=False)
    assert not saisie.is_valid()
    assert "ne peut plus être modifiée" in saisie.generale.non_field_errors()[0]


def test_creer_publier_et_consulter(client, pme):
    client.force_login(pme)
    jour = timezone.localdate() + timedelta(days=6)
    reponse = client.post(reverse("shipments:creer"), {**_donnees(jour, [_article()]), "publier": "1"})
    expedition = Expedition.objects.get(pme=pme)
    assert reponse.status_code == 302
    assert reponse.url == reverse("shipments:detail", args=[expedition.pk])
    assert expedition.statut == Expedition.Statut.PUBLIEE

    liste = client.get(reverse("shipments:liste"))
    assert liste.status_code == 200
    assert expedition.reference in liste.content.decode()

    detail = client.get(reverse("shipments:detail", args=[expedition.pk]))
    assert detail.status_code == 200
    assert "Cartons de vêtements" in detail.content.decode()


def test_modification_affiche_la_date_existante(client, pme):
    client.force_login(pme)
    jour = timezone.localdate() + timedelta(days=5)
    client.post(reverse("shipments:creer"), {**_donnees(jour, [_article()]), "brouillon": "1"})
    expedition = Expedition.objects.get(pme=pme)
    page = client.get(reverse("shipments:modifier", args=[expedition.pk]))
    assert f'value="{jour.isoformat()}"' in page.content.decode()


def test_modifier_une_expedition_par_la_page(client, pme):
    client.force_login(pme)
    jour = timezone.localdate() + timedelta(days=5)
    client.post(reverse("shipments:creer"), {**_donnees(jour, [_article()]), "brouillon": "1"})
    expedition = Expedition.objects.get(pme=pme)
    article = expedition.articles.get()
    donnees = _donnees(jour, [_article(id=article.pk, designation="Rouleaux de tissu")], initial=1)
    reponse = client.post(reverse("shipments:modifier", args=[expedition.pk]), donnees)
    assert reponse.status_code == 302
    article.refresh_from_db()
    assert article.designation == "Rouleaux de tissu"


def test_autre_pme_ne_modifie_pas(client, expedition):
    autre = Utilisateur.objects.create_user("encore@pme.tn", "motdepasse123", role=Role.PME)
    client.force_login(autre)
    assert client.get(reverse("shipments:modifier", args=[expedition.pk])).status_code == 404
    assert client.post(reverse("shipments:supprimer", args=[expedition.pk])).status_code == 404
    assert Expedition.objects.filter(pk=expedition.pk).exists()


def test_creation_sans_jeton_csrf_refusee(pme):
    client = Client(enforce_csrf_checks=True)
    client.force_login(pme)
    jour = timezone.localdate() + timedelta(days=6)
    reponse = client.post(reverse("shipments:creer"), {**_donnees(jour, [_article()]), "publier": "1"})
    assert reponse.status_code == 403
    assert not Expedition.objects.filter(pme=pme).exists()


def test_filtre_par_ville_de_depart(client, pme, expedition):
    client.force_login(pme)
    trouve = client.get(reverse("shipments:liste"), {"depart": "Monastir"})
    html = trouve.content.decode()
    assert expedition.reference in html
    assert "data-filtre-auto" in html
    assert "shipments/js/filtre.js" in html
    assert ">Filtrer<" not in html
    absent = client.get(reverse("shipments:liste"), {"depart": "Sfax"})
    assert expedition.reference not in absent.content.decode()


def test_autre_pme_ne_voit_pas_lexpedition(client, expedition):
    autre = Utilisateur.objects.create_user("autre@pme.tn", "motdepasse123", role=Role.PME)
    client.force_login(autre)
    assert client.get(reverse("shipments:detail", args=[expedition.pk])).status_code == 404
    assert client.post(reverse("shipments:annuler", args=[expedition.pk])).status_code == 404


def test_annulation_conserve_lexpedition(client, pme, expedition):
    client.force_login(pme)
    reponse = client.post(reverse("shipments:annuler", args=[expedition.pk]))
    assert reponse.status_code == 302
    expedition.refresh_from_db()
    assert expedition.statut == Expedition.Statut.ANNULEE
    assert client.get(reverse("shipments:historique")).status_code == 200
    assert expedition.reference in client.get(reverse("shipments:historique")).content.decode()


def test_suppression_dun_brouillon(client, pme, expedition):
    expedition.statut = Expedition.Statut.BROUILLON
    expedition.save(update_fields=["statut"])
    client.force_login(pme)
    assert client.get(reverse("shipments:supprimer", args=[expedition.pk])).status_code == 200
    reponse = client.post(reverse("shipments:supprimer", args=[expedition.pk]))
    assert reponse.status_code == 302
    assert not Expedition.objects.filter(pk=expedition.pk).exists()


def test_suppression_dune_publication_refusee(client, pme, expedition):
    client.force_login(pme)
    client.post(reverse("shipments:supprimer", args=[expedition.pk]))
    assert Expedition.objects.filter(pk=expedition.pk).exists()


def test_transporteur_ne_cree_pas_dexpedition(client, transporteur):
    client.force_login(transporteur)
    assert client.get(reverse("shipments:creer")).status_code == 403


def test_backoffice_filtre_et_detail(client, admin_user, expedition):
    client.force_login(admin_user)
    liste = client.get(reverse("bo_shipments:liste"), {"pme": expedition.pme.email, "statut": "PUBLIEE"})
    assert liste.status_code == 200
    html = liste.content.decode()
    assert expedition.reference in html
    assert "data-filtre-auto" in html
    assert "shipments/js/filtre.js" in html
    assert ">Filtrer<" not in html

    autre_statut = client.get(reverse("bo_shipments:liste"), {"statut": "BROUILLON"})
    assert expedition.reference not in autre_statut.content.decode()

    detail = client.get(reverse("bo_shipments:detail", args=[expedition.pk]))
    assert detail.status_code == 200
    assert "Cartons de vêtements" in detail.content.decode()
    assert expedition.pme.email in detail.content.decode()
    assert "Atelier Sami" in liste.content.decode()
    assert "Atelier Sami" in detail.content.decode()


def test_pme_ne_ouvre_pas_le_backoffice_des_expeditions(client, pme, expedition):
    client.force_login(pme)
    assert client.get(reverse("bo_shipments:liste")).status_code == 403
    assert client.get(reverse("bo_shipments:detail", args=[expedition.pk])).status_code == 403

