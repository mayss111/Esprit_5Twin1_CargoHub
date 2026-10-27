import pytest
from django.test import Client


@pytest.mark.django_db
def test_transporteur_peut_ouvrir_bilan_economie_carbone(transporteur, settings):
    settings.STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
    client = Client()
    client.force_login(transporteur)

    reponse = client.get("/ecologie/")

    assert reponse.status_code == 200
    assert "CO₂ économisé grâce au partage" in reponse.content.decode()
    assert b'href="/flotte/impact/"' in reponse.content
