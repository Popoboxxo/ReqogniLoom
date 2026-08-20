# Issue #377 (context_graph, Task 2): additive EventType.choices entries —
# TraceLinkCreated/Updated/Deleted (newly emitted, see trace_link_service.py)
# plus StakeholderNeedCreated/Updated/Deleted, GoalCreated, MainGoalCreated
# (already emitted at runtime as bare strings that matched no choices entry,
# now declared — no behavior change). State-only migration: event_type is a
# plain CharField, choices are not a DB-level constraint.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('application', '0015_adr_decision'),
    ]

    operations = [
        migrations.AlterField(
            model_name='domaineventoutbox',
            name='event_type',
            field=models.CharField(choices=[('RequirementCreated', 'Requirement Created'), ('RequirementUpdated', 'Requirement Updated'), ('RequirementDeleted', 'Requirement Deleted'), ('ArchitectureElementCreated', 'Architecture Element Created'), ('ArchitectureElementUpdated', 'Architecture Element Updated'), ('ArchitectureElementDeleted', 'Architecture Element Deleted'), ('TestCaseCreated', 'Test Case Created'), ('TestCaseUpdated', 'Test Case Updated'), ('TestCaseDeleted', 'Test Case Deleted'), ('BaselineCreated', 'Baseline Created'), ('WorkflowTransitioned', 'Workflow Transitioned'), ('AdrCreated', 'Adr Created'), ('AdrUpdated', 'Adr Updated'), ('AdrDeleted', 'Adr Deleted'), ('RiskCreated', 'Risk Created'), ('RiskUpdated', 'Risk Updated'), ('RiskDeleted', 'Risk Deleted'), ('IssueCreated', 'Issue Created'), ('IssueUpdated', 'Issue Updated'), ('IssueDeleted', 'Issue Deleted'), ('ChangeRequestCreated', 'Change Request Created'), ('ChangeRequestUpdated', 'Change Request Updated'), ('ChangeRequestDeleted', 'Change Request Deleted'), ('TraceLinkCreated', 'Trace Link Created'), ('TraceLinkUpdated', 'Trace Link Updated'), ('TraceLinkDeleted', 'Trace Link Deleted'), ('StakeholderNeedCreated', 'Stakeholder Need Created'), ('StakeholderNeedUpdated', 'Stakeholder Need Updated'), ('StakeholderNeedDeleted', 'Stakeholder Need Deleted'), ('GoalCreated', 'Goal Created'), ('MainGoalCreated', 'Main Goal Created')], max_length=64),
        ),
    ]
