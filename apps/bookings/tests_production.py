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
