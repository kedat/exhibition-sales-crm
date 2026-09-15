from django.db import migrations, models


def uppercase_existing_decisions(apps, schema_editor):
    handoff_run = apps.get_model("crm", "HandoffRun")
    handoff_run.objects.filter(coordinator_decision="continue").update(
        coordinator_decision="CONTINUE"
    )
    handoff_run.objects.filter(coordinator_decision="stop").update(
        coordinator_decision="STOP"
    )


def lowercase_existing_decisions(apps, schema_editor):
    handoff_run = apps.get_model("crm", "HandoffRun")
    handoff_run.objects.filter(coordinator_decision="CONTINUE").update(
        coordinator_decision="continue"
    )
    handoff_run.objects.filter(coordinator_decision="STOP").update(
        coordinator_decision="stop"
    )


class Migration(migrations.Migration):
    dependencies = [("crm", "0002_initial_schema")]

    operations = [
        migrations.AddField(
            model_name="handoffrun",
            name="reason_codes",
            field=models.JSONField(default=list),
        ),
        migrations.RunPython(
            uppercase_existing_decisions,
            lowercase_existing_decisions,
        ),
        migrations.AlterField(
            model_name="handoffrun",
            name="coordinator_decision",
            field=models.CharField(
                choices=[("CONTINUE", "Continue"), ("STOP", "Stop")],
                max_length=16,
            ),
        ),
    ]
