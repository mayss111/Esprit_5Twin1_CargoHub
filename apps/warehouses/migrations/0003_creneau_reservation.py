import django.db.models.deletion
from django.db import migrations, models


def remplir_references(apps, schema_editor):
    Creneau = apps.get_model("warehouses", "CreneauDepot")
    for creneau in Creneau.objects.all():
        if not creneau.reference:
            creneau.reference = f"DP-2026-{creneau.pk:08d}"
            creneau.save(update_fields=["reference"])


class Migration(migrations.Migration):

    dependencies = [
        ("warehouses", "0002_alter_entrepot_options_entrepot_capacite_max_m3_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="creneaudepot",
            name="reference",
            field=models.CharField(max_length=20, null=True),
        ),
        migrations.RunPython(remplir_references, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="creneaudepot",
            name="reference",
            field=models.CharField(editable=False, max_length=20, unique=True),
        ),
        migrations.AddField(
            model_name="creneaudepot",
            name="statut",
            field=models.CharField(
                choices=[("RESERVE", "Réservé"), ("ANNULE", "Annulé"), ("EFFECTUE", "Effectué")],
                default="RESERVE",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="creneaudepot",
            name="motif_annulation",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="mouvementcolis",
            name="creneau",
            field=models.ForeignKey(
                blank=True,
                help_text="Lien prévu pour le scan d'entrée. Reste vide tant que le colis n'est pas passé.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="mouvements",
                to="warehouses.creneaudepot",
            ),
        ),
        migrations.AlterField(
            model_name="creneaudepot",
            name="debut",
            field=models.DateTimeField(verbose_name="début du créneau"),
        ),
        migrations.AlterField(
            model_name="creneaudepot",
            name="fin",
            field=models.DateTimeField(verbose_name="fin du créneau"),
        ),
        migrations.AlterModelOptions(
            name="creneaudepot",
            options={"ordering": ["debut"], "verbose_name": "créneau de dépôt"},
        ),
        migrations.AddIndex(
            model_name="creneaudepot",
            index=models.Index(fields=["entrepot", "statut", "debut"], name="creneau_entrepot_statut_debut"),
        ),
        migrations.AddConstraint(
            model_name="creneaudepot",
            constraint=models.UniqueConstraint(
                condition=models.Q(("statut__in", ["RESERVE", "EFFECTUE"])),
                fields=("expedition",),
                name="un_depot_actif_par_expedition",
                violation_error_message="Cette expédition a déjà un dépôt réservé.",
            ),
        ),
        migrations.AddConstraint(
            model_name="creneaudepot",
            constraint=models.CheckConstraint(
                condition=models.Q(("fin__gt", models.F("debut"))),
                name="creneau_fin_apres_debut",
                violation_error_message="L'heure de fin doit être après l'heure de début.",
            ),
        ),
    ]
