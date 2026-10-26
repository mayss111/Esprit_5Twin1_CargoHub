"""
Menus affichés dans les gabarits (front-office et back-office).

Quand vous ajoutez une page à votre module, ajoutez-la ici pour qu'elle
apparaisse dans le menu. Format : (libellé, nom d'URL, icône Bootstrap Icons).
"""

from apps.bookings.models import Notification
from apps.messaging.models import Message

from .roles import Role, est_admin
from .traductions import traduire

MENU_PME = [
    ("Mes expéditions", "shipments:liste", "box-seam"),
    ("Mes réclamations", "reclamations:liste", "exclamation-circle"),
    ("Mes sinistres", "insurance:liste", "shield-exclamation"),
    ("Trouver un camion", "bookings:trouver", "search"),
    ("Entrepôts & points relais", "warehouses:liste", "shop"),
    ("Mes dépôts", "warehouses:mes_depots", "calendar-event"),
    ("Réservations", "bookings:liste", "calendar-check"),
    ("Appels d’offres", "tenders:liste", "megaphone"),
    ("Suivi", "tracking:liste", "geo-alt"),
    ("Paiements", "payments:liste", "credit-card"),
    ("Assurance", "insurance:liste", "shield-check"),
    ("Messagerie", "messaging:liste", "chat-dots"),
    ("Contrats", "contracts:liste", "file-earmark-text"),
    ("Aide et support", "messaging:assistant", "life-preserver"),
    ("Fidélité", "loyalty:liste", "gift"),
    ("CO₂ économisé", "ecology:liste", "tree"),
]
GROUPES_PME = [
    ("Expéditions", ["shipments:liste", "bookings:trouver"]),
    ("Entrepôts", ["warehouses:liste", "warehouses:mes_depots"]),
    ("Transport", ["bookings:liste", "tenders:liste", "tracking:liste"]),
    (
        "Services",
        [
            "payments:liste",
            "insurance:liste",
            "reclamations:liste",
            "messaging:liste",
            "contracts:liste",
            "messaging:assistant",
            "loyalty:liste",
        ],
    ),
]
GROUPES_TRANSPORTEUR = [
    ("Flotte", ["fleet:vehicules", "fleet:liste", "fleet:planificateur", "maintenance:liste"]),
    ("Activité", ["bookings:demandes", "bookings:liste", "tenders:liste", "tracking:liste"]),
    (
        "Services",
        [
            "payments:liste",
            "reclamations:liste",
            "insurance:liste",
            "messaging:liste",
            "contracts:liste",
            "messaging:assistant",
            "ecology:liste",
        ],
    ),
]


def _menus_groupes(menu, groupes, langue):
    """Regroupe les liens connus. Un lien nouveau reste visible dans Plus."""
    par_url = {url: (libelle, url, icone) for libelle, url, icone in menu}
    utilises = set()
    resultat = []
    for titre, urls in groupes:
        liens = [par_url[url] for url in urls if url in par_url]
        utilises.update(url for _libelle, url, _icone in liens)
        if len(liens) == 1:
            libelle, url, icone = liens[0]
            resultat.append({"titre": libelle, "url": url, "icone": icone, "liens": []})
        elif liens:
            resultat.append({"titre": traduire(titre, langue), "url": "", "icone": "", "liens": liens})
    reste = [entree for entree in menu if entree[1] not in utilises]
    if reste:
        resultat.append({"titre": traduire("Plus", langue), "url": "", "icone": "", "liens": reste})
    return resultat


def _traduit_menu(menu, langue):
    return [(traduire(libelle, langue), url, icone) for libelle, url, icone in menu]


MENU_TRANSPORTEUR = [
    ("Mes véhicules", "fleet:vehicules", "truck"),
    ("Mes trajets", "fleet:liste", "signpost-split"),
    ("Mes réclamations", "reclamations:liste", "exclamation-circle"),
    ("Mes sinistres", "insurance:liste", "shield-exclamation"),
    ("Impact écologique", "fleet:impact", "tree"),
    ("Demandes reçues", "bookings:demandes", "inbox"),
    ("Planificateur IA", "fleet:planificateur", "stars"),
    ("Réservations", "bookings:liste", "calendar-check"),
    ("Appels d’offres", "tenders:liste", "megaphone"),
    ("Entretien", "maintenance:liste", "tools"),
    ("Suivi", "tracking:liste", "geo-alt"),
    ("Revenus", "payments:liste", "cash-coin"),
    ("Messagerie", "messaging:liste", "chat-dots"),
    ("Contrats", "contracts:liste", "file-earmark-text"),
    ("Aide et support", "messaging:assistant", "life-preserver"),
    ("CO₂ économisé", "ecology:liste", "leaf"),
]

# Back-office : groupé par membre de l'équipe (même couleur que la présentation)
MENU_BACKOFFICE = [
    (
        "M1",
        "#2563EB",
        [
            ("Utilisateurs", "bo_accounts:liste", "people"),
            ("Support", "bo_messaging:liste", "life-preserver"),
            ("Conversations", "bo_messaging:conversations", "chat-dots"),
            ("Réclamations", "bo_reclamations:liste", "exclamation-circle"),
            ("Modération", "bo_messaging:moderation", "flag"),
            ("Contrats", "bo_contracts:liste", "file-earmark-text"),
        ],
    ),
    (
        "M2",
        "#0E9F8E",
        [
            ("Expéditions", "bo_shipments:liste", "box-seam"),
            ("Vérifications", "bo_shipments:verifications", "shield-check"),
            ("Interdictions", "bo_shipments:interdictions", "slash-circle"),
            ("Entrepôts", "bo_warehouses:liste", "shop"),
            ("Dépôts", "bo_warehouses:reservations", "calendar-event"),
            ("Occupation", "bo_warehouses:occupation", "pie-chart"),
            ("Sinistres", "bo_insurance:liste", "shield-exclamation"),
        ],
    ),
    (
        "M3",
        "#D97706",
        [
            ("Véhicules", "bo_fleet:liste", "truck"),
            ("Trajets", "bo_fleet:trajets", "signpost-split"),
            ("Conformité", "bo_maintenance:liste", "tools"),
            ("Écologie", "bo_ecology:liste", "tree"),
        ],
    ),
    (
        "M4",
        "#7C3AED",
        [
            ("Réservations", "bo_bookings:liste", "calendar-check"),
            ("Appels d’offres", "bo_tenders:liste", "megaphone"),
        ],
    ),
    (
        "M5",
        "#DB2777",
        [
            ("Incidents & avis", "bo_tracking:liste", "exclamation-triangle"),
            ("Paiements", "bo_payments:liste", "credit-card"),
            ("Codes promo", "bo_loyalty:liste", "gift"),
        ],
    ),
]


def navigation(request):
    user = request.user
    langue = getattr(request, "LANGUAGE_CODE", "fr")
    menu = []
    if user.is_authenticated:
        if user.role == Role.PME:
            menu = _traduit_menu(MENU_PME, langue)
            groupes = GROUPES_PME
        elif user.role == Role.TRANSPORTEUR:
            menu = _traduit_menu(MENU_TRANSPORTEUR, langue)
            groupes = GROUPES_TRANSPORTEUR
        else:
            groupes = []
    notifications = []
    if user.is_authenticated:
        notifications = list(user.notifications.filter(lu=False)[:5])
    # Une seule requête pour le badge et le menu de la messagerie (borné à 99).
    messages_non_lus = []
    if user.is_authenticated:
        messages_non_lus = list(
            Message.objects.filter(conversation__participants=user, lu=False)
            .exclude(auteur=user)
            .select_related("auteur", "conversation")
            .order_by("-created_at")[:99]
        )
    backoffice = [(membre, couleur, _traduit_menu(liens, langue)) for membre, couleur, liens in MENU_BACKOFFICE]
    return {
        "menu_front": menu,
        "menu_groupes": _menus_groupes(menu, groupes, langue) if menu else [],
        "menu_backoffice": backoffice,
        "est_admin": est_admin(user),
        "notifications_non_lues": notifications,
        "notifications_recentes": (
            Notification.objects.filter(destinataire=user).order_by("-created_at")[:5] if user.is_authenticated else []
        ),
        "messages_non_lus": messages_non_lus[:5],
        "messageries_non_lues": len(messages_non_lus),
    }
