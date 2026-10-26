from django.db import migrations, models
import django.db.models.deletion


REGLES = [
    (
        "Explosifs",
        "Matières explosives et détonateurs.",
        "Les explosifs sont interdits au transport sur CargoHub.",
        "explosif, explosifs, dynamite, détonateur, detonateur",
    ),
    (
        "Armes",
        "Armes à feu et munitions.",
        "Les armes et les munitions sont interdites au transport sur CargoHub.",
        "arme, armes, munition, munitions, pistolet, fusil",
    ),
    (
        "Stupéfiants",
        "Stupéfiants et drogues.",
        "Les stupéfiants sont interdits au transport sur CargoHub.",
        "drogue, drogues, stupéfiant, stupéfiants, cannabis, cocaïne",
    ),
    (
        "Gaz inflammable",
        "Gaz inflammables sous pression.",
        "Le gaz inflammable est interdit au transport sur CargoHub.",
        "gaz inflammable",
    ),
]


def creer_regles(apps, schema_editor):
    RegleInterdite = apps.get_model("shipments", "RegleInterdite")
    for nom, description, motif, mots in REGLES:
        RegleInterdite.objects.get_or_create(
            nom=nom,
            defaults={"description": description, "motif": motif, "mots_cles": mots, "actif": True},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("shipments", "0003_date_arrivee"),
    ]

    operations = [
        migrations.AddField(
            model_name="expedition",
            name="motif_decision",
            field=models.TextField(blank=True, verbose_name="motif de la décision"),
        ),
        migrations.AddField(
            model_name="expedition",
            name="empreinte_verification",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="expedition",
            name="verifie_le",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="expedition",
            name="duree_verification_ms",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="expedition",
            name="statut",
            field=models.CharField(
                choices=[
                    ("BROUILLON", "Brouillon"),
                    ("PUBLIEE", "Publiée"),
                    ("A_VERIFIER", "À vérifier"),
                    ("REFUSEE", "Refusée"),
                    ("RESERVEE", "Réservée"),
                    ("LIVREE", "Livrée"),
                    ("ANNULEE", "Annulée"),
                ],
                default="BROUILLON",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="RegleInterdite",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="créé le")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="modifié le")),
                ("nom", models.CharField(max_length=80, unique=True)),
                ("description", models.TextField()),
                ("motif", models.TextField(verbose_name="motif d'interdiction")),
                (
                    "mots_cles",
                    models.CharField(
                        help_text="Mots séparés par des virgules, cherchés dans le nom et la description.",
                        max_length=255,
                    ),
                ),
                ("actif", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "règle d'interdiction",
                "verbose_name_plural": "règles d'interdiction",
                "ordering": ["nom"],
            },
        ),
        migrations.CreateModel(
            name="ControleArticle",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("identifiant_article", models.PositiveIntegerField()),
                ("nom", models.CharField(max_length=150)),
                ("categorie_declaree", models.CharField(max_length=20)),
                ("categorie_proposee", models.CharField(blank=True, max_length=80)),
                (
                    "risque",
                    models.CharField(
                        choices=[
                            ("FAIBLE", "Faible"),
                            ("MOYEN", "Moyen"),
                            ("ELEVE", "Élevé"),
                            ("INCONNU", "Inconnu"),
                        ],
                        default="INCONNU",
                        max_length=10,
                    ),
                ),
                ("suspicion", models.BooleanField(default=False)),
                ("verification_manuelle", models.BooleanField(default=False)),
                ("motif", models.TextField(blank=True)),
                ("informations", models.TextField(blank=True)),
                (
                    "decision",
                    models.CharField(
                        choices=[("AUTORISE", "Autorisé"), ("A_VERIFIER", "À vérifier"), ("REFUSE", "Refusé")],
                        max_length=12,
                    ),
                ),
                ("verifie_le", models.DateTimeField()),
                (
                    "article",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="shipments.articleexpedie",
                    ),
                ),
                (
                    "expedition",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="controles",
                        to="shipments.expedition",
                    ),
                ),
                (
                    "regle",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to="shipments.regleinterdite",
                    ),
                ),
            ],
            options={
                "verbose_name": "contrôle d'article",
                "ordering": ["identifiant_article"],
            },
        ),
        migrations.RunPython(creer_regles, migrations.RunPython.noop),
    ]
