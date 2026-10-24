"""
Jeux de test ANNOTÉS À LA MAIN pour mesurer la qualité des parties IA.

Chaque membre complète SON jeu (visez 30 à 50 exemples réalistes) :
plus il y a d'exemples variés, plus les métriques présentées au jury sont crédibles.
Ne réutilisez pas ces phrases dans les consignes (prompts), sinon le test est faussé.
"""

# M1 — modération : (message, doit être signalé ?)
MODERATION = [
    ("Bonjour, le colis sera prêt à 9h demain", False),
    ("Merci pour la livraison, tout est arrivé", False),
    ("Pouvez-vous passer par la porte arrière du dépôt ?", False),
    ("Le camion a du retard ?", False),
    ("Appelez-moi au 22 345 678 on règle ça en direct", True),
    ("Mon numéro : +216 98 765 432, payez-moi en espèces", True),
    ("Vous êtes un idiot, rien n'est arrivé", True),
    ("C'est une arnaque votre service", True),
    ("Je préfère qu'on se mette d'accord hors de la plateforme pour éviter la commission", True),
    ("Quel est le poids maximum accepté ?", False),
    # Messages normaux, y compris des chiffres et des mots proches de la liste interdite
    ("Les 3 palettes pèsent 450 kg au total", False),
    ("Je serai au dépôt de Sfax vers 14h30", False),
    ("Le quai de chargement est le numéro 4, à gauche de l'entrée", False),
    ("Le paiement en ligne a bien été validé de mon côté", False),
    ("Pouvez-vous confirmer l'adresse de livraison à Sousse ?", False),
    ("Le suivi en direct ne s'affiche pas sur mon téléphone", False),
    ("Attention, les cartons du fond sont fragiles", False),
    ("Bien reçu, je signe le contrat ce soir", False),
    ("Nous avons 2 heures de retard à cause des travaux sur l'autoroute", False),
    ("Est-ce que vous acceptez les produits surgelés ?", False),
    ("La référence de la commande est CMD-2026-118", False),
    ("Désolé pour le retard, le chauffeur est tombé en panne", False),
    ("Merci beaucoup, très professionnel comme d'habitude", False),
    ("Pouvez-vous apporter un transpalette pour décharger ?", False),
    ("Je viens de déposer la lettre de voiture dans les documents", False),
    # À signaler : coordonnées, paiement ou accord en dehors de CargoHub
    ("Écrivez-moi sur WhatsApp, ce sera plus simple", True),
    ("Envoyez-moi un mail à karim.transport@gmail.com", True),
    ("Je vous laisse mon 55.123.456 pour la prochaine fois", True),
    ("Payez-moi en liquide à l'arrivée, c'est moins cher pour vous", True),
    ("La prochaine fois on fait sans passer par le site", True),
    ("Je vous fais 20 % de remise si on traite en direct", True),
    ("Contactez-moi sur Messenger, mon profil est Sami Transport", True),
    ("Virement sur mon compte personnel et on oublie la commission", True),
    # À signaler : insultes et menaces
    ("Espèce d'escroc, rendez-moi ma marchandise", True),
    ("Vous êtes vraiment minable", True),
    ("Si le colis n'est pas là demain, tu vas le regretter", True),
    ("Bande d'incapables, c'est la dernière fois", True),
    ("Quel abruti ce chauffeur", True),
    ("Je vais vous faire payer ça, croyez-moi", True),
    ("Ferme-la et livre", True),
]

# M2 — saisie intelligente : (description, type attendu, interdit ?)
EXPEDITIONS = [
    ("12 cartons de vêtements, environ 300 kg", "TEXTILE", False),
    ("40 bidons d'huile d'olive, 800 kg", "ALIMENTAIRE", False),
    ("3 palettes de dattes deglet nour", "ALIMENTAIRE", False),
    ("20 ordinateurs portables dans leurs boîtes", "ELECTRONIQUE", False),
    ("50 sacs de ciment de 50 kg", "MATERIAUX", False),
    ("carrelage pour salle de bain, 2 palettes", "MATERIAUX", False),
    ("caisses de fromage frais", "ALIMENTAIRE", False),
    ("10 écrans de télévision", "ELECTRONIQUE", False),
    ("une caisse d'explosifs pour chantier", "INTERDIT", True),
    ("pièces détachées diverses, 120 kg", "GENERAL", False),
    ("rouleaux de tissu en coton", "TEXTILE", False),
    ("bouteilles de gaz inflammable", "INTERDIT", True),
]

# M5 — sentiment des avis : (commentaire, note /5, sentiment attendu)
AVIS = [
    ("Livraison rapide et soigneuse, merci !", 5, "POSITIF"),
    ("Chauffeur ponctuel, parfait", 5, "POSITIF"),
    ("Très bien, je recommande", 4, "POSITIF"),
    ("Correct, rien à signaler", 3, "NEUTRE"),
    ("Livré, sans plus", 3, "NEUTRE"),
    ("Un peu de retard mais colis en bon état", 3, "NEUTRE"),
    ("Carton abîmé et deux heures de retard", 2, "NEGATIF"),
    ("Colis perdu, jamais reçu", 1, "NEGATIF"),
    ("Chauffeur impoli", 2, "NEGATIF"),
    ("Excellent service, très professionnel", 5, "POSITIF"),
    ("Marchandise cassée à l'arrivée", 1, "NEGATIF"),
    ("Livraison faite dans les délais annoncés", 4, "POSITIF"),
]
