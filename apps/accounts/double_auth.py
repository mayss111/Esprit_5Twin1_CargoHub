"""
Double authentification des administrateurs (django-otp, codes TOTP).

Un admin connecté doit saisir le code de son application (Google Authenticator,
Microsoft Authenticator…) avant d'accéder au back-office. Le contrôle est fait
par AdminRequiredMixin (apps/core/mixins.py). Appareil perdu : supprimer son
« TOTP device » dans django-admin, l'admin reconfigurera à la connexion suivante.
"""

from base64 import b32encode
from urllib.parse import urlencode

import qrcode
import qrcode.image.svg
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.core.roles import est_admin


def double_auth_requise(user):
    # Juste après login(), request.user n'est pas encore passé par OTPMiddleware : donc non vérifié.
    return est_admin(user) and getattr(user, "otp_device", None) is None


def url_double_auth_si_requise(user, suivant):
    """URL de la page de code si l'admin n'a pas encore saisi son code, sinon None."""
    if double_auth_requise(user):
        return f"{reverse('accounts:double_auth')}?{urlencode({'next': suivant})}"
    return None


def appareil_de(user):
    """Appareil confirmé de l'admin, sinon un appareil en attente de configuration."""
    appareil = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    if appareil is None:
        appareil = TOTPDevice.objects.filter(user=user, confirmed=False).first()
    if appareil is None:
        appareil = TOTPDevice.objects.create(user=user, name="Application d’authentification", confirmed=False)
    return appareil


def cle_secrete(appareil):
    """Clé à saisir à la main si le QR code ne peut pas être scanné."""
    return b32encode(appareil.bin_key).decode()


def qr_code_svg(appareil):
    image = qrcode.make(appareil.config_url, image_factory=qrcode.image.svg.SvgPathImage, box_size=8)
    return image.to_string(encoding="unicode")
