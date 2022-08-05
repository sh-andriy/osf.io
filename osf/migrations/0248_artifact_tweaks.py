# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2022-08-01 19:37
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('osf', '0247_artifact_finalized_and_deleted'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='outcomeartifact',
            name='osf_outcome_outcome_a62f5c_idx',
        ),
        migrations.AlterField(
            model_name='outcomeartifact',
            name='identifier',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='artifact_metadata', to='osf.Identifier'),
        ),
        migrations.AlterUniqueTogether(
            name='outcomeartifact',
            unique_together=set([]),
        ),
        migrations.AddIndex(
            model_name='outcomeartifact',
            index=models.Index(fields=['artifact_type', 'outcome'], name='osf_outcome_artifac_5eb92d_idx'),
        ),
    ]
