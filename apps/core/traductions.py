"""Libellés de l'interface traduits pour l'anglais et l'arabe.

Le français reste le texte source. La langue ne change que si la personne
la choisit : l'en-tête du navigateur ne suffit pas. Les pages lisent aussi
les fichiers catalogues/en.json et catalogues/ar.json.
"""

import json
from functools import lru_cache
from pathlib import Path

LANGUES = ("fr", "en", "ar")

EN = {
    "Accessibilité": "Accessibility",
    "Langue": "Language",
    "Taille du texte": "Text size",
    "Réduire le texte": "Decrease text size",
    "Agrandir le texte": "Increase text size",
    "Lecture vocale": "Read aloud",
    "Arrêter la lecture": "Stop reading",
    "La lecture vocale n’est pas disponible dans ce navigateur.": "Read aloud is not available in this browser.",
    "Aller au contenu": "Skip to content",
    "Navigation principale": "Main navigation",
    "CargoHub, accueil": "CargoHub, home",
    "Ouvrir le menu": "Open menu",
    "Fermer": "Close",
    "Notifications": "Notifications",
    "Aucune notification": "No notifications",
    "Mon profil": "My profile",
    "Back-office": "Back office",
    "Déconnexion": "Log out",
    "Connexion": "Log in",
    "Créer un compte": "Create an account",
    "Projet d’équipe Django": "Django team project",
    "Accueil": "Home",
    "Covoiturage de fret": "Freight ridesharing",
    "Réservez la": "Book the",
    "place libre": "spare space",
    "dans les camions déjà en route.": "in trucks already on the road.",
    "Les PME expédient moins cher, les transporteurs roulent plein, et moins de camions vides circulent.": (
        "SMEs ship for less, carriers run full, and fewer empty trucks are on the road."
    ),
    "Commencer": "Get started",
    "Se connecter": "Sign in",
    "Publier": "Publish",
    "La PME décrit son envoi, le transporteur son trajet et sa place libre.": (
        "The SME describes its shipment, the carrier its route and free space."
    ),
    "Matcher": "Match",
    "CargoHub classe les camions compatibles avec l’envoi.": "CargoHub ranks the trucks that fit the shipment.",
    "Réserver": "Book",
    "Plusieurs PME partagent le même camion.": "Several SMEs share the same truck.",
    "Livrer & payer": "Deliver and pay",
    "Suivi en temps réel, preuve de livraison, paiement en ligne.": (
        "Live tracking, proof of delivery, online payment."
    ),
    "Espace": "Area",
    "Bonjour": "Hello",
    "Aller au back-office": "Go to the back office",
    "Menu du back-office": "Back-office menu",
    "Tableau de bord": "Dashboard",
    "Modules": "Modules",
    "Retour au site": "Back to the site",
    "Back-office administrateur": "Administrator back office",
    "Mes expéditions": "My shipments",
    "Trouver un camion": "Find a truck",
    "Entrepôts & points relais": "Warehouses and relay points",
    "Mes dépôts": "My drop-offs",
    "Réservations": "Bookings",
    "Appels d’offres": "Tenders",
    "Suivi": "Tracking",
    "Paiements": "Payments",
    "Assurance": "Insurance",
    "Messagerie": "Messages",
    "Contrats": "Contracts",
    "Aide et support": "Help and support",
    "Fidélité": "Loyalty",
    "Expéditions": "Shipments",
    "Entrepôts": "Warehouses",
    "Transport": "Transport",
    "Services": "Services",
    "Flotte": "Fleet",
    "Activité": "Activity",
    "Plus": "More",
    "Mes véhicules": "My vehicles",
    "Mes trajets": "My routes",
    "Demandes reçues": "Incoming requests",
    "Planificateur IA": "AI planner",
    "Entretien": "Maintenance",
    "Revenus": "Revenue",
    "Mon bilan CO₂": "My CO₂ balance",
    "Utilisateurs": "Users",
    "Support": "Support",
    "Modération": "Moderation",
    "Vérifications": "Checks",
    "Interdictions": "Prohibited goods",
    "Dépôts": "Drop-offs",
    "Occupation": "Occupancy",
    "Sinistres": "Claims",
    "Véhicules": "Vehicles",
    "Trajets": "Routes",
    "Conformité": "Compliance",
    "Écologie": "Ecology",
    "Incidents & avis": "Incidents and reviews",
    "Codes promo": "Promo codes",
    "Nouvelle expédition": "New shipment",
    "Retour à la liste": "Back to the list",
    "Créer mon expédition avec l'IA": "Create my shipment with AI",
    (
        "L'assistant propose les champs. Vous vérifiez, vous complétez, "
        "puis vous enregistrez. Rien n'est publié avant votre confirmation."
    ): (
        "The assistant suggests the fields. You review them, complete them, "
        "then save. Nothing is published before you confirm."
    ),
    "Décrivez l'expédition": "Describe the shipment",
    (
        "Exemple : 5 cartons d'ordinateurs portables et 3 écrans, de Tunis à Sousse, "
        "le 15 novembre 2026. Poids total 80 kg. Les écrans sont fragiles."
    ): (
        "Example: 5 boxes of laptops and 3 screens, from Tunis to Sousse, "
        "on 15 November 2026. Total weight 80 kg. The screens are fragile."
    ),
    "Remplir automatiquement avec l'IA": "Fill in automatically with AI",
    "Analyse en cours…": "Analysis in progress…",
    "Créer plusieurs expéditions depuis un fichier Excel": "Create several shipments from an Excel file",
    (
        "Une ligne devient une expédition, publiée, refusée ou à vérifier. "
        "Le même groupe réunit plusieurs articles. Le formulaire manuel reste disponible."
    ): (
        "One row becomes one shipment: published, refused, or to be checked. "
        "The same group gathers several items. The manual form stays available."
    ),
    "Télécharger le modèle Excel": "Download the Excel template",
    "Fichier Excel": "Excel file",
    "Importer et publier": "Import and publish",
    "Expédition": "Shipment",
    "Adresse de départ": "Departure address",
    "Adresse d'arrivée": "Arrival address",
    "Articles": "Items",
    "Ajouter un article": "Add an item",
    "Enregistrer le brouillon": "Save draft",
    "Publier la demande": "Publish the request",
    "Rue": "Street",
    "Ville": "City",
    "Code postal": "Postal code",
    "Gouvernorat": "Governorate",
    "Date de départ": "Departure date",
    "Date d'arrivée": "Arrival date",
    "Description de l'expédition": "Shipment description",
    "Nom de l'article": "Item name",
    "Description de l'article": "Item description",
    "Catégorie": "Category",
    "Quantité": "Quantity",
    "Poids (kg)": "Weight (kg)",
    "Volume (m³)": "Volume (m³)",
    "Fragile": "Fragile",
    "Valeur déclarée (DT)": "Declared value (TND)",
    "Retirer": "Remove",
    "Marchandise générale": "General goods",
    "Alimentaire": "Food",
    "Textile": "Textile",
    "Électronique": "Electronics",
    "Matériaux de construction": "Building materials",
    "Interdit au transport": "Prohibited for transport",
    "Vos demandes d'envoi et leur statut.": "Your shipment requests and their status.",
    "Historique des expéditions": "Shipment history",
    "Expéditions passées, réservées, livrées ou annulées.": "Past, booked, delivered, or cancelled shipments.",
    "Expéditions en cours": "Current shipments",
    "Historique": "History",
    "Référence": "Reference",
    "Statut": "Status",
    "Tous": "All",
    "Ville de départ": "Departure city",
    "Ville d'arrivée": "Arrival city",
    "Date": "Date",
    "Description": "Description",
    "Départ": "Departure",
    "Arrivée": "Arrival",
    "Dates": "Dates",
    "Poids total": "Total weight",
    "Actions": "Actions",
    "Détail": "Details",
    "Télécharger le bon d'expédition PDF": "Download the shipment note (PDF)",
    "Modifier": "Edit",
    "Annuler": "Cancel",
    "Pages des expéditions": "Shipment pages",
    "Précédent": "Previous",
    "Suivant": "Next",
    "Page": "Page",
    "Aucune expédition ne correspond à cette recherche.": "No shipment matches this search.",
    "Brouillon": "Draft",
    "Publiée": "Published",
    "À vérifier": "To be checked",
    "Refusée": "Refused",
    "Réservée": "Booked",
    "Livrée": "Delivered",
    "Annulée": "Cancelled",
}

AR = {
    "Accessibilité": "إمكانية الوصول",
    "Langue": "اللغة",
    "Taille du texte": "حجم النص",
    "Réduire le texte": "تصغير النص",
    "Agrandir le texte": "تكبير النص",
    "Lecture vocale": "قراءة صوتية",
    "Arrêter la lecture": "إيقاف القراءة",
    "La lecture vocale n’est pas disponible dans ce navigateur.": "القراءة الصوتية غير متاحة في هذا المتصفح.",
    "Aller au contenu": "الانتقال إلى المحتوى",
    "Navigation principale": "التنقل الرئيسي",
    "CargoHub, accueil": "CargoHub، الصفحة الرئيسية",
    "Ouvrir le menu": "فتح القائمة",
    "Fermer": "إغلاق",
    "Notifications": "الإشعارات",
    "Aucune notification": "لا توجد إشعارات",
    "Mon profil": "ملفي",
    "Back-office": "لوحة الإدارة",
    "Déconnexion": "تسجيل الخروج",
    "Connexion": "تسجيل الدخول",
    "Créer un compte": "إنشاء حساب",
    "Projet d’équipe Django": "مشروع فريق جانغو",
    "Accueil": "الرئيسية",
    "Covoiturage de fret": "تقاسم شحن البضائع",
    "Réservez la": "احجزوا",
    "place libre": "المساحة الشاغرة",
    "dans les camions déjà en route.": "في الشاحنات المتجهة أصلاً.",
    "Les PME expédient moins cher, les transporteurs roulent plein, et moins de camions vides circulent.": (
        "تشحن المؤسسات الصغيرة بكلفة أقل، وتسير الشاحنات ممتلئة، ويقل عدد الشاحنات الفارغة."
    ),
    "Commencer": "ابدأ",
    "Se connecter": "دخول",
    "Publier": "نشر",
    "La PME décrit son envoi, le transporteur son trajet et sa place libre.": (
        "تصف المؤسسة شحنتها، ويصف الناقل مساره ومساحته الشاغرة."
    ),
    "Matcher": "مطابقة",
    "CargoHub classe les camions compatibles avec l’envoi.": "يرتب CargoHub الشاحنات المناسبة للشحنة.",
    "Réserver": "حجز",
    "Plusieurs PME partagent le même camion.": "تشترك عدة مؤسسات في الشاحنة نفسها.",
    "Livrer & payer": "التسليم والدفع",
    "Suivi en temps réel, preuve de livraison, paiement en ligne.": "تتبع مباشر، وإثبات تسليم، ودفع عبر الإنترنت.",
    "Espace": "فضاء",
    "Bonjour": "مرحبا",
    "Aller au back-office": "الذهاب إلى لوحة الإدارة",
    "Menu du back-office": "قائمة لوحة الإدارة",
    "Tableau de bord": "لوحة القيادة",
    "Modules": "الوحدات",
    "Retour au site": "العودة إلى الموقع",
    "Back-office administrateur": "إدارة المنصة",
    "Mes expéditions": "شحناتي",
    "Trouver un camion": "البحث عن شاحنة",
    "Entrepôts & points relais": "المستودعات ونقاط التسليم",
    "Mes dépôts": "إيداعاتي",
    "Réservations": "الحجوزات",
    "Appels d’offres": "طلبات العروض",
    "Suivi": "التتبع",
    "Paiements": "المدفوعات",
    "Assurance": "التأمين",
    "Messagerie": "الرسائل",
    "Contrats": "العقود",
    "Aide et support": "المساعدة والدعم",
    "Fidélité": "الولاء",
    "Expéditions": "الشحنات",
    "Entrepôts": "المستودعات",
    "Transport": "النقل",
    "Services": "الخدمات",
    "Flotte": "الأسطول",
    "Activité": "النشاط",
    "Plus": "المزيد",
    "Mes véhicules": "مركباتي",
    "Mes trajets": "رحلاتي",
    "Demandes reçues": "الطلبات الواردة",
    "Planificateur IA": "مخطط الذكاء الاصطناعي",
    "Entretien": "الصيانة",
    "Revenus": "الإيرادات",
    "Mon bilan CO₂": "حصيلة ثاني أكسيد الكربون",
    "Utilisateurs": "المستخدمون",
    "Support": "الدعم",
    "Modération": "الإشراف",
    "Vérifications": "عمليات التحقق",
    "Interdictions": "المواد الممنوعة",
    "Dépôts": "الإيداعات",
    "Occupation": "الإشغال",
    "Sinistres": "الحوادث",
    "Véhicules": "المركبات",
    "Trajets": "الرحلات",
    "Conformité": "المطابقة",
    "Écologie": "البيئة",
    "Incidents & avis": "البلاغات والآراء",
    "Codes promo": "الرموز الترويجية",
    "Nouvelle expédition": "شحنة جديدة",
    "Retour à la liste": "العودة إلى القائمة",
    "Créer mon expédition avec l'IA": "إنشاء شحنتي بالذكاء الاصطناعي",
    (
        "L'assistant propose les champs. Vous vérifiez, vous complétez, "
        "puis vous enregistrez. Rien n'est publié avant votre confirmation."
    ): ("يقترح المساعد الحقول. تراجعونها، تكملونها، ثم تحفظونها. لا يُنشر شيء قبل تأكيدكم."),
    "Décrivez l'expédition": "صف الشحنة",
    (
        "Exemple : 5 cartons d'ordinateurs portables et 3 écrans, de Tunis à Sousse, "
        "le 15 novembre 2026. Poids total 80 kg. Les écrans sont fragiles."
    ): (
        "مثال: 5 صناديق حواسيب محمولة و3 شاشات، من تونس إلى سوسة، "
        "في 15 نوفمبر 2026. الوزن الإجمالي 80 كغ. الشاشات قابلة للكسر."
    ),
    "Remplir automatiquement avec l'IA": "الملء تلقائياً بالذكاء الاصطناعي",
    "Analyse en cours…": "التحليل جارٍ…",
    "Créer plusieurs expéditions depuis un fichier Excel": "إنشاء عدة شحنات من ملف إكسل",
    (
        "Une ligne devient une expédition, publiée, refusée ou à vérifier. "
        "Le même groupe réunit plusieurs articles. Le formulaire manuel reste disponible."
    ): (
        "كل سطر يصبح شحنة: منشورة أو مرفوضة أو بانتظار التحقق. "
        "المجموعة نفسها تجمع عدة أصناف. النموذج اليدوي يبقى متاحاً."
    ),
    "Télécharger le modèle Excel": "تنزيل نموذج إكسل",
    "Fichier Excel": "ملف إكسل",
    "Importer et publier": "استيراد ونشر",
    "Expédition": "الشحنة",
    "Adresse de départ": "عنوان الانطلاق",
    "Adresse d'arrivée": "عنوان الوصول",
    "Articles": "الأصناف",
    "Ajouter un article": "إضافة صنف",
    "Enregistrer le brouillon": "حفظ المسودة",
    "Publier la demande": "نشر الطلب",
    "Rue": "الشارع",
    "Ville": "المدينة",
    "Code postal": "الرمز البريدي",
    "Gouvernorat": "الولاية",
    "Date de départ": "تاريخ الانطلاق",
    "Date d'arrivée": "تاريخ الوصول",
    "Description de l'expédition": "وصف الشحنة",
    "Nom de l'article": "اسم الصنف",
    "Description de l'article": "وصف الصنف",
    "Catégorie": "الفئة",
    "Quantité": "الكمية",
    "Poids (kg)": "الوزن (كغ)",
    "Volume (m³)": "الحجم (م³)",
    "Fragile": "قابل للكسر",
    "Valeur déclarée (DT)": "القيمة المصرح بها (د.ت)",
    "Retirer": "إزالة",
    "Marchandise générale": "بضاعة عامة",
    "Alimentaire": "مواد غذائية",
    "Textile": "نسيج",
    "Électronique": "إلكترونيات",
    "Matériaux de construction": "مواد بناء",
    "Interdit au transport": "ممنوع من النقل",
    "Vos demandes d'envoi et leur statut.": "طلبات الشحن وحالتها.",
    "Historique des expéditions": "سجل الشحنات",
    "Expéditions passées, réservées, livrées ou annulées.": "الشحنات السابقة أو المحجوزة أو المسلّمة أو الملغاة.",
    "Expéditions en cours": "الشحنات الجارية",
    "Historique": "السجل",
    "Référence": "المرجع",
    "Statut": "الحالة",
    "Tous": "الكل",
    "Ville de départ": "مدينة الانطلاق",
    "Ville d'arrivée": "مدينة الوصول",
    "Date": "التاريخ",
    "Description": "الوصف",
    "Départ": "الانطلاق",
    "Arrivée": "الوصول",
    "Dates": "التواريخ",
    "Poids total": "الوزن الإجمالي",
    "Actions": "الإجراءات",
    "Détail": "التفاصيل",
    "Télécharger le bon d'expédition PDF": "تنزيل سند الشحن PDF",
    "Modifier": "تعديل",
    "Annuler": "إلغاء",
    "Pages des expéditions": "صفحات الشحنات",
    "Précédent": "السابق",
    "Suivant": "التالي",
    "Page": "صفحة",
    "Aucune expédition ne correspond à cette recherche.": "لا توجد شحنة مطابقة لهذا البحث.",
    "Brouillon": "مسودة",
    "Publiée": "منشورة",
    "À vérifier": "بانتظار التحقق",
    "Refusée": "مرفوضة",
    "Réservée": "محجوزة",
    "Livrée": "مسلّمة",
    "Annulée": "ملغاة",
}

CATALOGUES = {"en": EN, "ar": AR}
_DOSSIER = Path(__file__).resolve().parent / "catalogues"


@lru_cache(maxsize=4)
def _fichier(langue):
    chemin = _DOSSIER / f"{langue}.json"
    if not chemin.exists():
        return {}
    return json.loads(chemin.read_text(encoding="utf-8"))


def traduire(texte, langue):
    if langue == "fr" or texte is None or texte == "":
        return texte
    texte = str(texte)
    catalogue = _fichier(langue)
    prioritaire = CATALOGUES.get(langue, {})
    if texte in prioritaire:
        return prioritaire[texte]
    if texte in catalogue:
        return catalogue[texte]
    cle = " ".join(texte.split())
    if cle in prioritaire:
        return prioritaire[cle]
    return catalogue.get(cle, texte)
