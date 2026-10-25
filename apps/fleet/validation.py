"""Validation serveur des fichiers justificatifs de véhicule."""

MAX_TAILLE_DOC = 5 * 1024 * 1024
SIGNATURES_AUTORISEES = {
    "application/pdf": b"%PDF-",
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n",
}


def erreur_fichier_vehicule(fichier):
    """Retourne un message d'erreur si MIME, signature ou taille ne sont pas valides."""
    if fichier.size > MAX_TAILLE_DOC:
        return "Le fichier dépasse la taille maximale de 5 Mo."
    signature = SIGNATURES_AUTORISEES.get(fichier.content_type)
    if signature is None:
        return "Format accepté : PDF, JPEG ou PNG uniquement."
    position = fichier.tell()
    debut = fichier.read(len(signature))
    fichier.seek(position)
    if debut != signature:
        return "Le contenu du fichier ne correspond pas au format annoncé."
    return None
