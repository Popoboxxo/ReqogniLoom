from django.db import migrations, models


class Migration(migrations.Migration):
    """Issue #1300: add the ``InteractionCompleted`` outbox event type.

    Purely additive ``choices`` change (no column, no data migration): the
    ``event_type`` column already accepts any value up to 64 chars. It declares
    the generic "a generating step was completed and confirmed" event the
    memory learning loop subscribes to.
    """

    dependencies = [
        ("application", "0034_rls_hard_enforcement_policy"),
    ]

    operations = [
        migrations.AlterField(
            model_name="domaineventoutbox",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("RequirementCreated", "Requirement Created"),
                    ("RequirementUpdated", "Requirement Updated"),
                    ("RequirementDeleted", "Requirement Deleted"),
                    ("ArchitectureElementCreated", "Architecture Element Created"),
                    ("ArchitectureElementUpdated", "Architecture Element Updated"),
                    ("ArchitectureElementDeleted", "Architecture Element Deleted"),
                    ("TestCaseCreated", "Test Case Created"),
                    ("TestCaseUpdated", "Test Case Updated"),
                    ("TestCaseDeleted", "Test Case Deleted"),
                    ("BaselineCreated", "Baseline Created"),
                    ("WorkflowTransitioned", "Workflow Transitioned"),
                    ("AdrCreated", "Adr Created"),
                    ("AdrUpdated", "Adr Updated"),
                    ("AdrDeleted", "Adr Deleted"),
                    ("RiskCreated", "Risk Created"),
                    ("RiskUpdated", "Risk Updated"),
                    ("RiskDeleted", "Risk Deleted"),
                    ("IssueCreated", "Issue Created"),
                    ("IssueUpdated", "Issue Updated"),
                    ("IssueDeleted", "Issue Deleted"),
                    ("ChangeRequestCreated", "Change Request Created"),
                    ("ChangeRequestUpdated", "Change Request Updated"),
                    ("ChangeRequestDeleted", "Change Request Deleted"),
                    ("TraceLinkCreated", "Trace Link Created"),
                    ("TraceLinkUpdated", "Trace Link Updated"),
                    ("TraceLinkDeleted", "Trace Link Deleted"),
                    ("StakeholderNeedCreated", "Stakeholder Need Created"),
                    ("StakeholderNeedUpdated", "Stakeholder Need Updated"),
                    ("StakeholderNeedDeleted", "Stakeholder Need Deleted"),
                    ("GoalCreated", "Goal Created"),
                    ("MainGoalCreated", "Main Goal Created"),
                    ("InterviewChatTurn", "Interview Chat Turn"),
                    ("InterviewFormalized", "Interview Formalized"),
                    ("InterviewAbandoned", "Interview Abandoned"),
                    ("InteractionCompleted", "Interaction Completed"),
                ],
                max_length=64,
            ),
        ),
    ]
