"""Tests des corrections issues des essais en production (M4, réservations)."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.bookings import services
from apps.bookings.templatetags.trajets import itineraire
from apps.fleet.models import Trajet
from apps.tenders.models import Offre


@pytest.fixture
def trajet_via_monastir(trajet):
    """Sfax → Tunis en passant par Sousse puis Monastir : compatible avec un envoi Monastir → Tunis."""
    Trajet.objects.filter(pk=trajet.pk).update(ville_depart="Sfax")
    trajet.refresh_from_db()
    trajet.etapes.create(ville="Monastir", ordre=2)
    trajet.etapes.create(ville="Sousse", ordre=1)
    return trajet


# ---------------------------------------------------------------- 3. étapes du trajet visibles


def test_filtre_itineraire(trajet, trajet_via_monastir):
    assert itineraire(trajet_via_monastir) == "Sfax → Tunis, via Sousse, Monastir"  # dans l'ordre du trajet
    trajet_via_monastir.etapes.all().delete()
    assert itineraire(trajet_via_monastir) == "Sfax → Tunis"
    assert itineraire(None) == "—"


def test_etapes_affichees_partout(client, pme, transporteur, expedition, trajet_via_monastir, appel_offre):
    attendu = "Sfax → Tunis, via Sousse, Monastir"
    client.force_login(pme)
    html = client.get(reverse("bookings:camions", args=[expedition.pk])).content.decode()
    assert attendu in html  # « Camions compatibles »

    reservation = services.reserver(expedition, trajet_via_monastir)
    assert attendu in client.get(reverse("bookings:detail", args=[reservation.pk])).content.decode()

    Offre.objects.create(appel=appel_offre, transporteur=transporteur, trajet=trajet_via_monastir, prix=Decimal("90"))
    assert attendu in client.get(reverse("tenders:detail", args=[appel_offre.pk])).content.decode()  # offres

    client.force_login(transporteur)
    assert attendu in client.get(reverse("bookings:demandes")).content.decode()
    assert attendu in client.get(reverse("tenders:detail", args=[appel_offre.pk])).content.decode()  # mon offre


def test_pas_de_requete_par_etape(client, django_assert_max_num_queries, pme, expedition, trajet_via_monastir):
    services.reserver(expedition, trajet_via_monastir)
    for i in range(3):  # 3 réservations de plus : le nombre de requêtes ne doit pas grandir
        services.reserver(
            expedition,
            Trajet.objects.create(
                transporteur=trajet_via_monastir.transporteur,
                vehicule=trajet_via_monastir.vehicule,
                ville_depart="Sfax",
                ville_arrivee="Tunis",
                date_depart=trajet_via_monastir.date_depart + timedelta(hours=i + 1),
                capacite_dispo_kg=Decimal("500"),
                capacite_dispo_m3=Decimal("5"),
            ),
        )
    client.force_login(trajet_via_monastir.transporteur)
    with django_assert_max_num_queries(15):
        client.get(reverse("bookings:demandes"))


# ---------------------------------------------------------------- 4. expédition de 0 kg


@pytest.fixture
def expedition_vide(expedition):
    expedition.articles.all().delete()
    return expedition


def test_reserver_une_expedition_vide_est_refuse(client, pme, expedition_vide, trajet):
    client.force_login(pme)
    html = client.get(reverse("bookings:camions", args=[expedition_vide.pk])).content.decode()
    assert services.EXPEDITION_VIDE in html and "Réserver" not in html
    reponse = client.post(reverse("bookings:reserver", args=[expedition_vide.pk, trajet.pk]), follow=True)
    assert services.EXPEDITION_VIDE in reponse.content.decode()
    assert not expedition_vide.reservations.exists()
    trouver = client.get(reverse("bookings:trouver")).content.decode()
    assert services.EXPEDITION_VIDE in trouver
    assert "Camions compatibles<span" not in trouver and "Lancer un appel d’offres" not in trouver


def test_le_service_refuse_une_expedition_vide(expedition_vide, trajet):
    with pytest.raises(services.ReservationImpossible, match=r"aucune marchandise \(0 kg\)"):
        services.reserver(expedition_vide, trajet)
    assert not expedition_vide.reservations.exists()


def test_petit_poids_pas_arrondi_a_zero(client, pme, expedition, trajet):
    expedition.articles.update(quantite=1, poids_kg="0.40")
    client.force_login(pme)
    html = client.get(reverse("bookings:trouver")).content.decode()
    assert "0,40 kg" in html and services.EXPEDITION_VIDE not in html  # 0,40 kg n’est pas « 0 kg »
    client.post(reverse("bookings:reserver", args=[expedition.pk, trajet.pk]))
    assert expedition.reservations.exists()
