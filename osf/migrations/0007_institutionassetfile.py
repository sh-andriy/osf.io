# Generated by Django 3.2.15 on 2022-12-02 17:44

from django.db import migrations, models
import django_extensions.db.fields
import osf.models.base


class Migration(migrations.Migration):

    dependencies = [
        ('osf', '0006_institutionaffiliation'),
    ]

    operations = [
        migrations.CreateModel(
            name='InstitutionAssetFile',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created', django_extensions.db.fields.CreationDateTimeField(auto_now_add=True, verbose_name='created')),
                ('modified', django_extensions.db.fields.ModificationDateTimeField(auto_now=True, verbose_name='modified')),
                ('file', models.FileField(upload_to='assets')),
                ('name', models.CharField(choices=[('banner', 'banner'), ('logo', 'logo'), ('logo_rounded_corners', 'logo_rounded_corners')], max_length=63)),
                ('institutions', models.ManyToManyField(blank=True, related_name='asset_files', to='osf.Institution')),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model, osf.models.base.QuerySetExplainMixin),
        ),
    ]