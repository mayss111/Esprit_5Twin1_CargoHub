"""Tests des corrections issues des essais en production (M4)."""

from io import StringIO
from unittest import mock

import pytest
from django.apps import apps
from django.core.management import call_command

from apps.core import ai
from apps.tenders import apps as config_tenders
from apps.tenders.ai import chauffer_modele

# ---------------------------------------------------------------- 1. préchargement de scikit-learn et chauffe


@pytest.mark.parametrize(
    "argv, attendu",
    [
        (["manage.py", "migrate"], False),
        (["manage.py", "collectstatic", "--noinput"], False),
        (["manage.py", "runserver"], True),
        (["/usr/local/bin/daphne", "config.asgi:application"], True),
        (["/usr/local/bin/celery", "-A", "config", "worker"], True),
    ],
)
def test_quand_precharger(argv, attendu):
    assert config_tenders.doit_prechauffer(argv, en_test=False) is attendu


def test_pas_de_prechargement_pendant_les_tests():
    assert config_tenders.doit_prechauffer() is False


def test_chauffe_du_modele():
    modele = chauffer_modele()
    assert modele.predict([[150.0, 1500.0, 225.0]])[0] > 0


def test_ready_ne_bloque_jamais_le_demarrage():
    config = apps.get_app_config("tenders")
    with (
        mock.patch.object(config_tenders, "doit_prechauffer", return_value=True),
        mock.patch("apps.tenders.ai.chauffer_modele", side_effect=ImportError("scikit-learn absent")) as chauffe,
    ):
        config.ready()  # aucune exception
    chauffe.assert_called_once()


def test_chauffer_ia_sans_cle(db):
    sortie = StringIO()
    call_command("chauffer_ia", stdout=sortie)
    texte = sortie.getvalue()
    assert "Suggestion de prix :" in texte and " ms (formule" in texte and "pas de clé" in texte


def test_chauffer_ia_avec_llm(db, settings):
    settings.AI_API_KEY, settings.AI_MODEL = "cle-de-test", "modele-test"
    sortie = StringIO()
    with mock.patch("apps.core.ai.demander", return_value="OK"):
        call_command("chauffer_ia", stdout=sortie)
    assert "LLM (modele-test) :" in sortie.getvalue()
    with mock.patch("apps.core.ai.demander", side_effect=ai.IAIndisponible("modèle introuvable")):
        call_command("chauffer_ia", stdout=sortie)
    assert "indisponible : modèle introuvable" in sortie.getvalue()
