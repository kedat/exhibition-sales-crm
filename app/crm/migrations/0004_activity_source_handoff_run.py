from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("crm", "0003_handoff_reason_codes"),
    ]

    operations = [
        migrations.AddField(
            model_name="activity",
            name="source_handoff_run",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=models.SET_NULL,
                related_name="approved_follow_up",
                to="crm.handoffrun",
            ),
        ),
    ]
