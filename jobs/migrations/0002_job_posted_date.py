from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='job',
            name='posted_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='job',
            index=models.Index(fields=['posted_date'], name='jobs_job_posted__e9488e_idx'),
        ),
        migrations.AlterModelOptions(
            name='job',
            options={'ordering': ['-posted_date', '-last_seen', 'company', 'title']},
        ),
    ]
