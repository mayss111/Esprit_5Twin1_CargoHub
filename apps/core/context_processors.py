"""
Menus affichés dans les gabarits (front-office et back-office).

Quand vous ajoutez une page à votre module, ajoutez-la ici pour qu'elle
apparaisse dans le menu. Format : (libellé, nom d'URL, icône Bootstrap Icons).
"""

from .roles import Role, est_admin

MENU_PME = [
    ("Mes expéditions", "shipments:liste", "box-seam"),
    ("Trouver un camion", "bookings:trouver", "search"),
    ("Points relais", "warehouses:liste", "shop"),
    ("Réservations", "bookings:liste", "calendar-check"),
    ("Appels d’offres", "tenders:liste", "megaphone"),
    ("Suivi", "tracking:liste", "geo-alt"),
    ("Paiements", "payments:liste", "credit-card"),
    ("Assurance", "insurance:liste", "shield-check"),
    ("Messagerie", "messaging:liste", "chat-dots"),
    ("Contrats", "contracts:liste", "file-earmark-text"),
    ("Aide et support", "messaging:assistant", "life-preserver"),
    ("Fidélité", "loyalty:liste", "gift"),
]
MENU_TRANSPORTEUR = [
    ("Mes véhicules", "fleet:vehicules", "truck"),
    ("Mes trajets", "fleet:liste", "signpost-split"),
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
    ("Mon bilan CO₂", "ecology:liste", "tree"),
]

# Back-office : groupé par membre de l'équipe (même couleur que la présentation)
MENU_BACKOFFICE = [
    (
        "M1",
        "#2563EB",
        [
            ("Utilisateurs", "bo_accounts:liste", "people"),
            ("Support", "bo_messaging:liste", "life-preserver"),
            ("Modération", "bo_messaging:moderation", "flag"),
            ("Contrats", "bo_contracts:liste", "file-earmark-text"),
        ],
    ),
    (
        "M2",
        "#0E9F8E",
        [
            ("Expéditions", "bo_shipments:liste", "box-seam"),
            ("Entrepôts", "bo_warehouses:liste", "shop"),
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
    menu = []
    if user.is_authenticated:
        if user.role == Role.PME:
            menu = MENU_PME
        elif user.role == Role.TRANSPORTEUR:
            menu = MENU_TRANSPORTEUR
    return {
        "menu_front": menu,
        "menu_backoffice": MENU_BACKOFFICE,
        "est_admin": est_admin(user),
    }
