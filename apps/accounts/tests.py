from django.urls import reverse

from apps.accounts.models import ProfilPME, Utilisateur
from apps.core.roles import Role


def test_inscription_pme_cree_le_profil(client, db):
    reponse = client.post(
        reverse("accounts:inscription"),
        {
            "email": "nouvelle@pme.tn",
            "first_name": "Ines",
            "last_name": "B",
            "telephone": "",
            "role": Role.PME,
            "raison_sociale": "Huilerie Ines",
            "password1": "UnMotDePasseSolide!42",
            "password2": "UnMotDePasseSolide!42",
        },
    )
    assert reponse.status_code == 302
    user = Utilisateur.objects.get(email="nouvelle@pme.tn")
    assert user.role == Role.PME
    assert ProfilPME.objects.get(utilisateur=user).raison_sociale == "Huilerie Ines"


def test_inscription_pme_sans_entreprise_refusee(client, db):
    reponse = client.post(
        reverse("accounts:inscription"),
        {
            "email": "x@pme.tn",
            "role": Role.PME,
            "password1": "UnMotDePasseSolide!42",
            "password2": "UnMotDePasseSolide!42",
        },
    )
    assert reponse.status_code == 200
    assert not Utilisateur.objects.filter(email="x@pme.tn").exists()


def test_connexion_par_email(client, pme):
    reponse = client.post(reverse("accounts:connexion"), {"username": "pme@test.tn", "password": "motdepasse123"})
    assert reponse.status_code == 302
