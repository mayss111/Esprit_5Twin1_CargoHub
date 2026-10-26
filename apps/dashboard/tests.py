"""Tests M5 — tableau de bord et exports."""

from django.urls import reverse


def test_exports_reserves_a_l_admin(client, admin_user, pme):
    client.force_login(admin_user)
    excel = client.get(reverse("dashboard:export_excel"))
    pdf = client.get(reverse("dashboard:export_pdf"))
    assert excel.status_code == 200
    assert excel["Content-Type"].startswith("application/vnd.openxmlformats")
    assert excel.content[:2] == b"PK"
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    assert b"/Image" in pdf.content
    page = client.get(reverse("dashboard:accueil"))
    assert page.status_code == 200
    assert "Taux de remplissage" in page.content.decode()
    client.force_login(pme)
    assert client.get(reverse("dashboard:export_excel")).status_code == 403
    assert client.get(reverse("dashboard:export_pdf")).status_code == 403
