# INT-02 (AUD-2026-09-058): ``azure`` was implemented as a provider but was
# not part of the LlmProvider choices enum, so it could not be selected through
# the DB-backed REST / UI path. Also refreshes the model_name help-text example
# off the retired ``claude-3-opus-20240229``. No schema change.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('persistence', '0105_normalize_residual_testcase_artifact_type'),
    ]

    operations = [
        migrations.AlterField(
            model_name='llmsettings',
            name='provider',
            field=models.CharField(
                choices=[
                    ('anthropic', 'Anthropic'),
                    ('openai', 'OpenAI'),
                    ('ollama', 'Ollama'),
                    ('azure', 'Azure OpenAI'),
                    ('opencode_go', 'OpenCode Go'),
                    ('mock', 'Mock'),
                ],
                default='mock',
                help_text='Active LLM provider. Defaults to the credential-free mock.',
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name='llmsettings',
            name='model_name',
            field=models.CharField(
                blank=True,
                default='',
                help_text="Free-text model identifier (e.g. 'claude-sonnet-4-5').",
                max_length=255,
            ),
        ),
    ]
