from django.db import migrations, models


def copier_date_depart(apps, schema_editor):
    Expedition = apps.get_model("shipments", "Expedition")
    Expedition.objects.filter(date_arrivee__isnull=True).update(date_arrivee=models.F("date_souhaitee"))


class Migration(migrations.Migration):
    dependencies = [
        ("shipments", "0002_champs_expedition"),
    ]

    operations = [
        migrations.AddField(
            model_name="expedition",
            name="date_arrivee",
            field=models.DateField(null=True, verbose_name="date d'arrivée"),
        ),
        migrations.RunPython(copier_date_depart, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="expedition",
            name="date_arrivee",
            field=models.DateField(verbose_name="date d'arrivée"),
        ),
        migrations.AlterField(
            model_name="expedition",
            name="date_souhaitee",
            field=models.DateField(verbose_name="date de départ"),
        ),
    ]
