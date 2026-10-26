import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("warehouses", "0003_creneau_reservation"),
    ]

    operations = [
        migrations.AddField(
            model_name="entrepot",
            name="duree_stockage_max_heures",
            field=models.PositiveIntegerField(
                default=48,
                help_text="Délai après l'entrée physique. 48 heures par défaut. Une sortie n'est jamais créée automatiquement.",
                validators=[django.core.validators.MinValueValidator(1)],
                verbose_name="durée maximale de stockage (heures)",
            ),
        ),
        migrations.AddField(
            model_name="mouvementcolis",
            name="commentaire",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="mouvementcolis",
            name="exceptionnel",
            field=models.BooleanField(
                default=False,
                help_text="Entrée acceptée par un administrateur en dehors du créneau de 2 heures.",
            ),
        ),
        migrations.AddField(
            model_name="mouvementcolis",
            name="motif_prolongation",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="mouvementcolis",
            name="ouvert",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="mouvementcolis",
            name="prolongation_heures",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AlterField(
            model_name="mouvementcolis",
            name="date",
            field=models.DateTimeField(default=django.utils.timezone.now, verbose_name="date et heure"),
        ),
        migrations.AlterField(
            model_name="mouvementcolis",
            name="scanne_par",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="mouvements_colis",
                to=settings.AUTH_USER_MODEL,
                verbose_name="effectué par",
            ),
        ),
        migrations.AlterField(
            model_name="mouvementcolis",
            name="type",
            field=models.CharField(
                choices=[("ENTREE", "Entrée"), ("SORTIE", "Sortie")],
                max_length=10,
                verbose_name="type de mouvement",
            ),
        ),
        migrations.AddConstraint(
            model_name="mouvementcolis",
            constraint=models.UniqueConstraint(
                condition=models.Q(("ouvert", True)),
                fields=("expedition",),
                name="une_entree_ouverte_par_expedition",
                violation_error_message="Une entrée est déjà enregistrée pour cette expédition.",
            ),
        ),
    ]
