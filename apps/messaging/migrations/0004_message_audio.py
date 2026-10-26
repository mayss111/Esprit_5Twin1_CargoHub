from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("messaging", "0003_conversation_bloquee_par")]

    operations = [
        migrations.AddField(
            model_name="message",
            name="fichier_audio",
            field=models.FileField(blank=True, upload_to="messagerie/audio/"),
        ),
        migrations.AddField(
            model_name="message",
            name="transcription",
            field=models.TextField(blank=True),
        ),
    ]
