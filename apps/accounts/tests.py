import re

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


def _html(client, nom_url):
    reponse = client.get(reverse(nom_url))
    assert reponse.status_code == 200
    return reponse.content.decode()


def test_inscription_expose_la_saisie_vocale_y_compris_le_mot_de_passe(client):
    html = _html(client, "accounts:inscription")
    assert "voice_input.js" in html
    assert "csrfmiddlewaretoken" in html
    assert 'data-voice-fields="first_name,last_name,email,telephone,raison_sociale,password1,password2"' in html
    assert 'id="voice-lang"' in html
    assert "ar-TN" in html
    assert "n’enregistre ni l’audio" in html
    for champ in ("id_first_name", "id_last_name", "id_email", "id_telephone", "id_raison_sociale"):
        assert f'id="{champ}"' in html
    assert "Prénom" in html
    assert "Adresse email" in html
    assert ">Mot de passe<" in html or "Mot de passe" in html
    mots_de_passe = re.findall(r"<input\b[^>]*type=\"password\"[^>]*>", html)
    assert len(mots_de_passe) >= 2
    assert all("data-voice-input" not in balise and "btn-voice" not in balise for balise in mots_de_passe)


def test_connexion_dicte_email_et_mot_de_passe(client):
    html = _html(client, "accounts:connexion")
    assert "voice_input.js" in html
    assert "csrfmiddlewaretoken" in html
    assert 'data-voice-fields="username,password"' in html
    assert 'id="id_username"' in html
    assert 'id="id_password"' in html
    assert 'type="password"' in html
    assert "n’enregistre ni l’audio" not in html
    mot_de_passe = re.search(r"<input\b[^>]*type=\"password\"[^>]*>", html)
    assert mot_de_passe
    assert "voice" not in mot_de_passe.group(0)


def test_saisie_manuelle_transporteur_reste_valide(client, db):
    reponse = client.post(
        reverse("accounts:inscription"),
        {
            "email": "voix@transport.tn",
            "first_name": "Karim",
            "last_name": "Trabelsi",
            "telephone": "22111222",
            "role": Role.TRANSPORTEUR,
            "raison_sociale": "",
            "password1": "UnMotDePasseSolide!42",
            "password2": "UnMotDePasseSolide!42",
        },
    )
    assert reponse.status_code == 302
    assert Utilisateur.objects.filter(email="voix@transport.tn", first_name="Karim").exists()
