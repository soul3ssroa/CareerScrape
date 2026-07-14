from django.db import migrations, models


def fix_null_locations(apps, schema_editor):
    Job = apps.get_model('jobs', 'Job')
    Job.objects.filter(location__isnull=True).update(location='')


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0003_rename_jobs_job_posted__e9488e_idx_jobs_job_posted__0a7770_idx'),
    ]

    operations = [
        migrations.RunPython(fix_null_locations, migrations.RunPython.noop),
    ]
