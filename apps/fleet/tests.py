"""Tests du module Flotte & trajets (M3) : conformité, formulaires, CO₂, IA, pages par rôle, back-office."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.bookings import services as reservations
from apps.bookings.models import Notification, Reservation
from apps.fleet import services
from apps.fleet.ai import recommander_vehicules
from apps.fleet.forms import TrajetForm, VehiculeForm
from apps.fleet.models import DocumentVehicule, FacteurEmission, Trajet, Vehicule
from apps.fleet.tasks import notifier_alerte_documents
from apps.fleet.validation import erreur_fichier_vehicule
from apps.maintenance.tasks import verifier_conformite


def _pdf(nom="assurance.pdf", contenu=b"%PDF-1.7 contenu"):
    return SimpleUploadedFile(nom, contenu, content_type="application/pdf")


def _dans(jours):
    return (timezone.now() + timedelta(days=jours)).strftime("%Y-%m-%dT%H:%M")


def _donnees_trajet(vehicule, **autres):
    return {
        "vehicule": vehicule.pk,
        "ville_depart": "Sousse",
        "ville_arrivee": "Tunis",
        "date_depart": _dans(3),
        "capacite_totale_kg": "1200",
        "capacite_totale_m3": "9",
        "distance_km": "140",
        "prix_indicatif": "90",
        "etapes": "Hammamet",
        **autres,
    }


# ---------------------------------------------------------------- conformité des véhicules


def test_vehicule_actif_par_defaut(vehicule):
    assert vehicule.statut == Vehicule.Statut.ACTIF and vehicule.peut_publier_trajet()


def test_document_expire_bloque_puis_renouvele_reactive(vehicule):
    doc = DocumentVehicule.objects.create(
        vehicule=vehicule,
        type=DocumentVehicule.Type.ASSURANCE,
        fichier="a.pdf",
        date_expiration=timezone.localdate() - timedelta(days=1),
    )
    assert vehicule.recalculer_conformite() == Vehicule.Statut.NON_CONFORME
    assert not vehicule.peut_publier_trajet() and "Assurance expiré" in vehicule.motif_non_conformite
    DocumentVehicule.objects.filter(pk=doc.pk).update(date_expiration=timezone.localdate() + timedelta(days=90))
    assert vehicule.recalculer_conformite() == Vehicule.Statut.ACTIF and vehicule.conforme


def test_controle_technique_expire(vehicule):
    vehicule.controles.create(
        date_controle=timezone.localdate() - timedelta(days=400),
        date_expiration=timezone.localdate() - timedelta(days=35),
    )
    assert vehicule.est_non_conforme()


def test_tache_conformite_bloque_et_previent(vehicule, trajet, expedition):
    DocumentVehicule.objects.create(
        vehicule=vehicule,
        type=DocumentVehicule.Type.CARTE_GRISE,
        fichier="c.pdf",
        date_expiration=timezone.localdate() - timedelta(days=1),
    )
    assert verifier_conformite() == {"bloques": 1, "reactives": 0}
    vehicule.refresh_from_db()
    assert not vehicule.conforme
    assert Notification.objects.filter(destinataire=vehicule.transporteur, titre="Véhicule non conforme").exists()
    # Le module Réservations (M4) ne propose plus ce camion.
    assert reservations.trajets_compatibles(expedition) == []


def test_alerte_documents_bientot_expires(vehicule):
    DocumentVehicule.objects.create(
        vehicule=vehicule,
        type=DocumentVehicule.Type.ASSURANCE,
        fichier="a.pdf",
        date_expiration=timezone.localdate() + timedelta(days=10),
    )
    assert notifier_alerte_documents() == 1
    assert Notification.objects.get(destinataire=vehicule.transporteur).lien == reverse("fleet:vehicules")


def test_validation_signature_document():
    assert erreur_fichier_vehicule(_pdf()) is None
    assert "ne correspond pas" in erreur_fichier_vehicule(_pdf(contenu=b"pas un pdf"))
    image = SimpleUploadedFile("a.gif", b"GIF89a", content_type="image/gif")
    assert "Format accepté" in erreur_fichier_vehicule(image)


# ---------------------------------------------------------------- formulaires


def test_formulaire_vehicule_capacite_sous_un_trajet_actif(vehicule, trajet):
    Trajet.objects.filter(pk=trajet.pk).update(capacite_totale_kg=Decimal("2500"))
    donnees = {"type": "CAMION", "immatriculation": vehicule.immatriculation, "capacite_kg": 2000, "capacite_m3": 20}
    form = VehiculeForm(donnees, instance=vehicule)
    assert not form.is_valid() and "capacite_kg" in form.errors


def test_formulaire_trajet_valide_cree_les_etapes(transporteur, vehicule):
    form = TrajetForm(_donnees_trajet(vehicule, etapes="Hammamet, Bouficha"), transporteur=transporteur)
    assert form.is_valid(), form.errors
    trajet = form.save()
    assert trajet.statut == Trajet.Statut.OUVERT and trajet.capacite_dispo_kg == Decimal("1200")
    assert [e.ville for e in trajet.etapes.all()] == ["Hammamet", "Bouficha"]


@pytest.mark.parametrize(
    "autres, champ",
    [
        ({"date_depart": _dans(-1)}, "date_depart"),
        ({"capacite_totale_kg": "999999"}, "capacite_totale_kg"),
        ({"capacite_totale_m3": "0"}, "capacite_totale_m3"),
        ({"ville_arrivee": "sousse"}, "ville_arrivee"),
        ({"distance_km": ""}, "distance_km"),
    ],
)
def test_formulaire_trajet_invalide(transporteur, vehicule, autres, champ):
    form = TrajetForm(_donnees_trajet(vehicule, **autres), transporteur=transporteur)
    assert not form.is_valid() and champ in form.errors


def test_formulaire_trajet_refuse_vehicule_non_conforme_ou_d_autrui(transporteur, vehicule, autre_trajet):
    Vehicule.objects.filter(pk=vehicule.pk).update(conforme=False, statut=Vehicule.Statut.NON_CONFORME)
    for v in (vehicule, autre_trajet.vehicule):
        form = TrajetForm(_donnees_trajet(v), transporteur=transporteur)
        assert not form.is_valid() and "vehicule" in form.errors


def test_modifier_trajet_garde_la_place_reservee(pme, transporteur, trajet, expedition):
    reservation = reservations.reserver(expedition, trajet)
    reservations.changer_statut(reservation, Reservation.Statut.ACCEPTEE, par=transporteur)
    trajet.refresh_from_db()
    reserve = expedition.poids_total_kg  # 300 kg

    trop_peu = TrajetForm(
        _donnees_trajet(trajet.vehicule, capacite_totale_kg="100"), instance=trajet, transporteur=transporteur
    )
    assert not trop_peu.is_valid() and "capacite_totale_kg" in trop_peu.errors

    form = TrajetForm(
        _donnees_trajet(trajet.vehicule, capacite_totale_kg="2000"), instance=trajet, transporteur=transporteur
    )
    assert form.is_valid(), form.errors
    trajet = form.save()
    assert trajet.capacite_dispo_kg == Decimal("2000") - reserve
    assert trajet.taux_remplissage == pytest.approx(float(reserve / 2000))


# ---------------------------------------------------------------- place et compatibilité (lien avec M4)


def test_reserver_et_liberer_capacite(trajet):
    trajet.reserver_capacite(Decimal("400"), Decimal("2"))
    trajet.refresh_from_db()
    assert trajet.capacite_dispo_kg == Decimal("600")
    trajet.liberer_capacite(Decimal("400"), Decimal("2"))
    trajet.refresh_from_db()
    assert trajet.capacite_dispo_kg == Decimal("1000")
    with pytest.raises(ValueError):
        trajet.reserver_capacite(Decimal("50000"), Decimal("1"))  # anti-surbooking


def test_trajet_complet_puis_rouvert_par_les_reservations(transporteur, trajet, expedition):
    Trajet.objects.filter(pk=trajet.pk).update(capacite_dispo_kg=expedition.poids_total_kg)
    reservation = reservations.reserver(expedition, trajet)
    reservations.changer_statut(reservation, Reservation.Statut.ACCEPTEE, par=transporteur)
    trajet.refresh_from_db()
    assert trajet.statut == Trajet.Statut.COMPLET and trajet.capacite_dispo_kg == 0

    reservations.changer_statut(reservation, Reservation.Statut.ANNULEE, par=transporteur)
    trajet.refresh_from_db()
    assert trajet.statut == Trajet.Statut.OUVERT and trajet.capacite_dispo_kg == expedition.poids_total_kg


def test_est_compatible_suit_la_regle_des_reservations(trajet, expedition):
    assert trajet.est_compatible(expedition)
    assert services.trajets_compatibles(expedition) == [trajet]
    trajet.ville_arrivee = "Sfax"
    assert not trajet.est_compatible(expedition)


@pytest.mark.parametrize(
    "changement",
    [
        {"statut": Trajet.Statut.ANNULE},
        {"date_depart": timezone.now() - timedelta(hours=1)},
        {"capacite_dispo_kg": Decimal("1")},
    ],
)
def test_trajet_incompatible(trajet, expedition, changement):
    for champ, valeur in changement.items():
        setattr(trajet, champ, valeur)
    assert not trajet.est_compatible(expedition)


def test_est_compatible_vehicule_non_conforme(trajet, expedition):
    trajet.vehicule.statut = Vehicule.Statut.NON_CONFORME
    assert not trajet.est_compatible(expedition)


def test_notifier(transporteur):
    services.notifier(transporteur, "Titre", "Message", "/flotte/")
    assert Notification.objects.get(destinataire=transporteur).lien == "/flotte/"


# ---------------------------------------------------------------- CO₂ et certificat vert


def test_facteur_emission_par_defaut_et_administrable(db):
    assert FacteurEmission.pour(Vehicule.Type.CAMION) == Decimal("0.2500")
    FacteurEmission.objects.filter(type_vehicule=Vehicule.Type.CAMION).update(kg_co2_par_km=Decimal("0.31"))
    assert FacteurEmission.pour(Vehicule.Type.CAMION) == Decimal("0.3100")


def test_calcul_co2(trajet):
    trajet.capacite_totale_kg, trajet.distance_km = Decimal("3000"), 100
    # 100 km × 0,25 kg/km × (1000 / 3000) = 8,33 kg
    assert services.calculer_co2_trajet(trajet, 1000) == pytest.approx(8.33, abs=0.01)
    assert services.calculer_co2_trajet(trajet, 0) == 0


def test_bilan_co2_par_vehicule(trajet, autre_trajet):
    Trajet.objects.filter(pk=trajet.pk).update(statut=Trajet.Statut.TERMINE, co2_kg=250.0)
    deuxieme = Vehicule.objects.create(
        transporteur=trajet.transporteur,
        type=Vehicule.Type.CAMIONNETTE,
        immatriculation="1 TU 1",
        capacite_kg=900,
        capacite_m3=5,
    )
    assert services.bilan_co2(trajet.transporteur) == {"nb_trajets": 1, "co2_total_kg": 250.0, "points_eco": 2}
    assert services.bilan_co2(trajet.transporteur, vehicule=deuxieme)["nb_trajets"] == 0


def test_page_impact_affiche_graphique_et_acces_navigation(client, transporteur, trajet):
    Trajet.objects.filter(pk=trajet.pk).update(statut=Trajet.Statut.TERMINE, co2_kg=125.0)
    client.force_login(transporteur)

    reponse = client.get(reverse("fleet:impact"))

    assert reponse.status_code == 200
    assert b"CO2 par v\xc3\xa9hicule" in reponse.content or "CO₂ par véhicule" in reponse.content.decode()
    assert b'href="/flotte/impact/"' in reponse.content


def test_certificat_vert_pdf(trajet):
    Trajet.objects.filter(pk=trajet.pk).update(
        statut=Trajet.Statut.TERMINE, date_depart=timezone.now() - timedelta(days=1), co2_kg=120.0
    )
    contenu, bilan = services.generer_certificat_vert(
        trajet.transporteur, timezone.localdate() - timedelta(days=30), timezone.localdate(), vehicule=trajet.vehicule
    )
    assert contenu.startswith(b"%PDF") and bilan["nb_trajets"] == 1


# ---------------------------------------------------------------- planificateur IA


def test_planificateur_classe_ma_flotte(transporteur, vehicule, autre_trajet):
    grand = Vehicule.objects.create(
        transporteur=transporteur,
        type=Vehicule.Type.SEMI_REMORQUE,
        immatriculation="LARGE 01",
        capacite_kg=20000,
        capacite_m3=Decimal("100"),
    )
    resultat = recommander_vehicules(
        transporteur, poids_kg=2400, volume_m3=16, distance_km=100, date_depart=timezone.localdate() + timedelta(days=2)
    )
    # Le véhicule de l'autre transporteur n'apparaît jamais ; le camion bien rempli passe devant.
    assert [r["vehicule"].pk for r in resultat["resultats"]] == [vehicule.pk, grand.pk]


def test_planificateur_sans_vehicule_adapte(transporteur, vehicule):
    resultat = recommander_vehicules(
        transporteur,
        poids_kg=vehicule.capacite_kg + 1,
        volume_m3=1,
        distance_km=50,
        date_depart=timezone.localdate() + timedelta(days=1),
    )
    assert resultat["resultats"] == [] and "Aucun véhicule" in resultat["message"]


# ---------------------------------------------------------------- pages du transporteur


@pytest.mark.parametrize(
    "nom",
    [
        "fleet:liste",
        "fleet:vehicules",
        "fleet:vehicule_creer",
        "fleet:trajet_creer",
        "fleet:impact",
        "fleet:planificateur",
    ],
)
def test_pages_du_transporteur(client, transporteur, pme, trajet, nom):
    client.force_login(transporteur)
    assert client.get(reverse(nom)).status_code == 200
    client.force_login(pme)
    assert client.get(reverse(nom)).status_code == 403


def test_impact_affiche_graphique_et_lien_dans_le_menu(client, transporteur, trajet):
    Trajet.objects.filter(pk=trajet.pk).update(statut=Trajet.Statut.TERMINE, co2_kg=125.0)
    client.force_login(transporteur)

    reponse = client.get(reverse("fleet:impact"))

    assert reponse.status_code == 200
    assert "CO₂ par véhicule" in reponse.content.decode()
    assert b'href="/flotte/impact/"' in reponse.content


def test_pages_demandent_une_connexion(client, vehicule):
    for url in (
        reverse("fleet:vehicule_modifier", args=[vehicule.pk]),
        reverse("fleet:certificat", args=[vehicule.pk]),
    ):
        assert client.get(url).status_code == 302


def test_ajouter_modifier_supprimer_un_vehicule(client, transporteur):
    client.force_login(transporteur)
    donnees = {"type": "CAMION", "immatriculation": " 77 tu 1234 ", "capacite_kg": 2000, "capacite_m3": "12"}
    assert client.post(reverse("fleet:vehicule_creer"), donnees).status_code == 302
    vehicule = Vehicule.objects.get(transporteur=transporteur)
    assert vehicule.immatriculation == "77 TU 1234"

    client.post(reverse("fleet:vehicule_modifier", args=[vehicule.pk]), {**donnees, "capacite_kg": 2500})
    vehicule.refresh_from_db()
    assert vehicule.capacite_kg == 2500

    client.post(reverse("fleet:vehicule_supprimer", args=[vehicule.pk]))
    assert not Vehicule.objects.filter(pk=vehicule.pk).exists()


def test_vehicule_avec_trajets_non_supprime(client, transporteur, vehicule, trajet):
    client.force_login(transporteur)
    reponse = client.post(reverse("fleet:vehicule_supprimer", args=[vehicule.pk]), follow=True)
    assert Vehicule.objects.filter(pk=vehicule.pk).exists()
    assert "ne peut pas être supprimé" in reponse.content.decode()


def test_vehicule_d_un_autre_transporteur_introuvable(client, autre_transporteur, vehicule):
    client.force_login(autre_transporteur)
    for nom in ("fleet:vehicule_modifier", "fleet:vehicule_supprimer", "fleet:certificat"):
        assert client.get(reverse(nom, args=[vehicule.pk])).status_code == 404
    assert client.post(reverse("fleet:document_ajouter", args=[vehicule.pk])).status_code == 404


def test_televerser_un_document(client, transporteur, vehicule):
    client.force_login(transporteur)
    url = reverse("fleet:document_ajouter", args=[vehicule.pk])
    expiration = (timezone.localdate() + timedelta(days=200)).isoformat()
    client.post(url, {"type": "ASSURANCE", "date_expiration": expiration, "fichier": _pdf()})
    client.post(url, {"type": "ASSURANCE", "date_expiration": expiration, "fichier": _pdf("nouvelle.pdf")})
    assert vehicule.documents.count() == 1  # le nouveau document remplace l'ancien

    reponse = client.post(
        url, {"type": "ASSURANCE", "date_expiration": expiration, "fichier": _pdf(contenu=b"x")}, follow=True
    )
    assert "ne correspond pas" in reponse.content.decode()


def test_certificat_vert_telecharge(client, transporteur, vehicule):
    client.force_login(transporteur)
    reponse = client.get(reverse("fleet:certificat", args=[vehicule.pk]))
    assert reponse["Content-Type"] == "application/pdf" and reponse.content.startswith(b"%PDF")


def test_publier_modifier_annuler_un_trajet(client, transporteur, vehicule):
    client.force_login(transporteur)
    assert client.post(reverse("fleet:trajet_creer"), _donnees_trajet(vehicule)).status_code == 302
    trajet = Trajet.objects.get(transporteur=transporteur)

    client.post(reverse("fleet:trajet_modifier", args=[trajet.pk]), _donnees_trajet(vehicule, prix_indicatif="110"))
    trajet.refresh_from_db()
    assert trajet.prix_indicatif == Decimal("110")

    client.post(reverse("fleet:trajet_annuler", args=[trajet.pk]))
    trajet.refresh_from_db()
    assert trajet.statut == Trajet.Statut.ANNULE
    assert client.get(reverse("fleet:trajet_modifier", args=[trajet.pk])).status_code == 302  # plus modifiable


def test_trajet_avec_reservation_acceptee_non_annulable(client, transporteur, trajet, expedition):
    reservation = reservations.reserver(expedition, trajet)
    reservations.changer_statut(reservation, Reservation.Statut.ACCEPTEE, par=transporteur)
    client.force_login(transporteur)
    client.post(reverse("fleet:trajet_annuler", args=[trajet.pk]))
    trajet.refresh_from_db()
    assert trajet.statut == Trajet.Statut.OUVERT


def test_trajet_d_un_autre_transporteur_introuvable(client, autre_transporteur, trajet):
    client.force_login(autre_transporteur)
    assert client.get(reverse("fleet:trajet_modifier", args=[trajet.pk])).status_code == 404
    assert client.post(reverse("fleet:trajet_annuler", args=[trajet.pk])).status_code == 404


def test_planificateur_par_la_page(client, transporteur, vehicule):
    client.force_login(transporteur)
    donnees = {
        "ville_depart": "Sousse",
        "ville_arrivee": "Tunis",
        "date_depart": timezone.localdate() + timedelta(days=2),
        "poids_kg": "2000",
        "volume_m3": "10",
        "distance_km": "140",
    }
    reponse = client.post(reverse("fleet:planificateur"), donnees)
    assert reponse.status_code == 200 and vehicule.immatriculation in reponse.content.decode()


# ---------------------------------------------------------------- back-office


def test_backoffice_vehicules_et_trajets(client, admin_user, vehicule, trajet):
    client.force_login(admin_user)
    reponse = client.get(reverse("bo_fleet:liste"))
    assert reponse.status_code == 200 and reponse.context["nb_vehicules"] == 1
    assert client.get(reverse("bo_fleet:liste") + "?statut=NON_CONFORME").context["object_list"].count() == 0
    assert client.get(reverse("bo_fleet:trajets")).status_code == 200


def test_backoffice_refuser_puis_valider(client, admin_user, vehicule):
    client.force_login(admin_user)
    url = reverse("bo_fleet:decision", args=[vehicule.pk])
    client.post(url, {"decision": "refuser", "motif": "Photo illisible"})
    vehicule.refresh_from_db()
    assert vehicule.statut == Vehicule.Statut.NON_CONFORME and vehicule.motif_non_conformite == "Photo illisible"
    client.post(url, {"decision": "valider"})
    vehicule.refresh_from_db()
    assert vehicule.statut == Vehicule.Statut.ACTIF and vehicule.conforme


def test_backoffice_interdit_aux_utilisateurs(client, transporteur, vehicule):
    client.force_login(transporteur)
    assert client.get(reverse("bo_fleet:liste")).status_code == 403
    assert client.post(reverse("bo_fleet:decision", args=[vehicule.pk]), {"decision": "valider"}).status_code == 403
