"""
ARCH-L1-014 IcdManagement — Service stubs.

TODO(COMP-ICD-001): Implement IcdService:
  - create_icd(data, ctx) -> Icd  (IF-L1-037 from ApplicationService)
  - update_icd(id, data, ctx) -> IcdVersion  (creates new immutable version)
  - validate_compatibility(icd_id, new_version_data, ctx) -> CompatibilityReport
  - get_icd_history(icd_id, ctx) -> list[IcdVersion]
  - get_icd_versions(workspace_id) -> list[IcdVersion]  (IF-L1-038 for BaselineService)

Reference: docs/se/L1/Gesamtsystem/L2/IcdManagementSystem/L2_IcdManagementSystem_Architecture.md
"""
