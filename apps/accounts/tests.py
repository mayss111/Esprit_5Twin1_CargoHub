import re

import pytest
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.forms import TAILLE_MAX_DOCUMENT, valider_document
from apps.accounts.models import ProfilPME, ProfilTransporteur, Utilisateur
from apps.core.roles import Role

PDF = b"%PDF-1.4 test"


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


def test_inscription_telephone_invalide(client, db):
    reponse = client.post(
        reverse("accounts:inscription"),
        {
            "email": "tel@pme.tn",
            "role": Role.TRANSPORTEUR,
            "telephone": "abc",
            "password1": "UnMotDePasseSolide!42",
            "password2": "UnMotDePasseSolide!42",
        },
    )
    assert reponse.status_code == 200
    assert not Utilisateur.objects.filter(email="tel@pme.tn").exists()


# ---------------------------------------------------------------- profil et documents


def _profil_pme(**changements):
    data = {
        "compte-first_name": "Sami",
        "compte-last_name": "Ben Ali",
        "compte-telephone": "22 123 456",
        "profil-raison_sociale": "Atelier Sami SARL",
        "profil-matricule_fiscal": "1234567A/B/M/000",
        "profil-secteur": "Textile",
        "profil-adresse": "Zone industrielle",
        "profil-ville": "Monastir",
    }
    data.update(changements)
    return data


@pytest.mark.parametrize("fixture", ["pme", "transporteur", "admin_user"])
def test_pages_profil_par_role(client, request, fixture):
    client.force_login(request.getfixturevalue(fixture))
    assert client.get(reverse("accounts:profil")).status_code == 200
    assert client.get(reverse("accounts:profil_modifier")).status_code == 200


def test_modifier_profil_pme(client, pme):
    client.force_login(pme)
    reponse = client.post(reverse("accounts:profil_modifier"), _profil_pme())
    assert reponse.status_code == 302
    pme.refresh_from_db()
    assert pme.last_name == "Ben Ali" and pme.telephone == "22 123 456"
    assert pme.profil_pme.raison_sociale == "Atelier Sami SARL"
    assert pme.profil_pme.ville == "Monastir"


@pytest.mark.parametrize(
    "champ, valeur",
    [("compte-telephone", "123"), ("profil-matricule_fiscal", "ABC"), ("compte-first_name", "")],
)
def test_modifier_profil_pme_invalide(client, pme, champ, valeur):
    client.force_login(pme)
    reponse = client.post(reverse("accounts:profil_modifier"), _profil_pme(**{champ: valeur}))
    assert reponse.status_code == 200
    assert ProfilPME.objects.get(utilisateur=pme).raison_sociale == "Atelier Sami"  # rien n'est enregistré


def test_admin_modifie_son_compte_sans_profil(client, admin_user):
    client.force_login(admin_user)
    reponse = client.post(
        reverse("accounts:profil_modifier"),
        {"compte-first_name": "Admin", "compte-last_name": "CargoHub", "compte-telephone": ""},
    )
    assert reponse.status_code == 302
    admin_user.refresh_from_db()
    assert admin_user.get_full_name() == "Admin CargoHub"


def test_transporteur_depose_ses_documents(client, transporteur):
    client.force_login(transporteur)
    reponse = client.post(
        reverse("accounts:profil_modifier"),
        {
            "compte-first_name": "Karim",
            "compte-last_name": "Trabelsi",
            "compte-telephone": "",
            "profil-numero_permis": "P-12345",
            "profil-permis": SimpleUploadedFile("permis.pdf", PDF, content_type="application/pdf"),
        },
    )
    assert reponse.status_code == 302
    profil = ProfilTransporteur.objects.get(utilisateur=transporteur)
    assert profil.permis and profil.numero_permis == "P-12345"
    # Un nouveau document doit être revérifié par un administrateur.
    assert profil.statut_validation == ProfilTransporteur.Statut.EN_ATTENTE


def test_document_mauvaise_extension_refuse(client, transporteur):
    client.force_login(transporteur)
    reponse = client.post(
        reverse("accounts:profil_modifier"),
        {
            "compte-first_name": "Karim",
            "compte-last_name": "T",
            "profil-permis": SimpleUploadedFile("virus.exe", b"MZ"),
        },
    )
    assert reponse.status_code == 200
    assert not ProfilTransporteur.objects.get(utilisateur=transporteur).permis


def test_document_trop_lourd_refuse():
    gros = SimpleUploadedFile("gros.pdf", b"0")
    gros.size = TAILLE_MAX_DOCUMENT + 1
    with pytest.raises(ValidationError, match="5 Mo"):
        valider_document(gros)


def test_desactiver_son_compte(client, pme):
    client.force_login(pme)
    assert client.get(reverse("accounts:desactiver")).status_code == 200
    reponse = client.post(reverse("accounts:desactiver"))
    assert reponse.status_code == 302
    pme.refresh_from_db()
    assert not pme.is_active
    assert client.get(reverse("accounts:profil")).status_code == 302  # déconnecté


# ---------------------------------------------------------------- mot de passe oublié


def test_mot_de_passe_oublie_de_bout_en_bout(client, pme):
    assert client.get(reverse("accounts:mot_de_passe_oublie")).status_code == 200
    reponse = client.post(reverse("accounts:mot_de_passe_oublie"), {"email": "pme@test.tn"})
    assert reponse.url == reverse("accounts:mot_de_passe_envoye")
    assert len(mail.outbox) == 1
    lien = re.search(r"https?://[^/]+(/\S+)", mail.outbox[0].body).group(1)

    reponse = client.get(lien, follow=True)  # Django redirige vers une URL sans le jeton
    assert reponse.context["validlink"]
    reponse = client.post(
        reponse.redirect_chain[-1][0],
        {"new_password1": "NouveauSecret!2026", "new_password2": "NouveauSecret!2026"},
    )
    assert reponse.url == reverse("accounts:reinitialisation_terminee")
    pme.refresh_from_db()
    assert pme.check_password("NouveauSecret!2026")


def test_mot_de_passe_oublie_email_inconnu_ne_revele_rien(client, db):
    reponse = client.post(reverse("accounts:mot_de_passe_oublie"), {"email": "inconnu@test.tn"})
    assert reponse.status_code == 302
    assert len(mail.outbox) == 0


def test_lien_de_reinitialisation_invalide(client, pme):
    reponse = client.get(
        reverse("accounts:reinitialiser_mot_de_passe", args=["MQ", "jeton-faux"]),
        follow=True,
    )
    assert not reponse.context["validlink"]
    assert "Lien invalide" in reponse.content.decode()


def test_connexion_propose_mot_de_passe_oublie(client):
    assert reverse("accounts:mot_de_passe_oublie") in _html(client, "accounts:connexion")


# ---------------------------------------------------------------- back-office


def test_backoffice_liste_filtres(client, admin_user, pme, transporteur):
    client.force_login(admin_user)
    url = reverse("bo_accounts:liste")
    assert "karim@test.tn" not in client.get(url, {"role": Role.PME}).content.decode()
    assert "pme@test.tn" in client.get(url, {"q": "sami"}).content.decode()
    ProfilTransporteur.objects.filter(utilisateur=transporteur).update(statut_validation="EN_ATTENTE")
    html = client.get(url, {"a_valider": "1"}).content.decode()
    assert "karim@test.tn" in html and "pme@test.tn" not in html


def test_backoffice_detail_et_modification(client, admin_user, pme):
    client.force_login(admin_user)
    assert client.get(reverse("bo_accounts:detail", args=[pme.pk])).status_code == 200
    reponse = client.post(
        reverse("bo_accounts:modifier", args=[pme.pk]),
        {"first_name": "Sami", "last_name": "B", "telephone": "", "role": Role.PME},  # case « actif » décochée
    )
    assert reponse.status_code == 302
    pme.refresh_from_db()
    assert not pme.is_active


def test_admin_ne_peut_pas_se_desactiver(client, admin_user):
    client.force_login(admin_user)
    reponse = client.post(
        reverse("bo_accounts:modifier", args=[admin_user.pk]),
        {"first_name": "", "last_name": "", "telephone": "", "role": Role.ADMIN},
    )
    assert reponse.status_code == 200
    admin_user.refresh_from_db()
    assert admin_user.is_active


def test_admin_valide_un_transporteur(client, admin_user, transporteur):
    client.force_login(admin_user)
    ProfilTransporteur.objects.filter(utilisateur=transporteur).update(statut_validation="EN_ATTENTE")
    html = client.get(reverse("bo_accounts:detail", args=[transporteur.pk])).content.decode()
    assert "Validation des documents" in html
    client.post(reverse("bo_accounts:valider", args=[transporteur.pk]), {"statut_validation": "REFUSE"})
    assert ProfilTransporteur.objects.get(utilisateur=transporteur).statut_validation == "REFUSE"
    client.post(reverse("bo_accounts:valider", args=[transporteur.pk]), {"statut_validation": "INCONNU"})
    assert ProfilTransporteur.objects.get(utilisateur=transporteur).statut_validation == "REFUSE"


def test_admin_supprime_un_utilisateur(client, admin_user, pme):
    client.force_login(admin_user)
    assert client.get(reverse("bo_accounts:supprimer", args=[pme.pk])).status_code == 200
    client.post(reverse("bo_accounts:supprimer", args=[pme.pk]))
    assert not Utilisateur.objects.filter(pk=pme.pk).exists()


def test_admin_ne_peut_pas_se_supprimer(client, admin_user):
    client.force_login(admin_user)
    client.post(reverse("bo_accounts:supprimer", args=[admin_user.pk]))
    assert Utilisateur.objects.filter(pk=admin_user.pk).exists()


@pytest.mark.parametrize("nom", ["detail", "modifier", "supprimer"])
def test_backoffice_utilisateurs_interdit_aux_pme(client, pme, nom):
    client.force_login(pme)
    assert client.get(reverse(f"bo_accounts:{nom}", args=[pme.pk])).status_code == 403
