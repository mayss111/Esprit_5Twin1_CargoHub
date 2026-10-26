from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0002_facteuremission_alter_vehicule_options_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='vehicule',
            options={'ordering': ['immatriculation'], 'verbose_name': 'véhicule'},
        ),
    ]
