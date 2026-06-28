# Verification & Validation (V&V) Strategy

> **System:** ReqFlow
> **Date:** 2026-06-28
> **Scope:** Entire System (L1 to Ln)

## 1. Introduction
This Verification & Validation (V&V) strategy outlines how the ReqFlow system ensures that all requirements (L1 through Ln) are properly tested, how we manage test execution, and how suspect links affect our test coverage. It forms the backbone of the "Test Status" fields found in our requirements documents.

## 2. Test Cases vs. Test Runs

To effectively manage testing, we distinguish strictly between **Test Cases** and **Test Runs**:

*   **Test Case:** A Test Case is an immutable or versioned definition of a test. It describes the preconditions, the execution steps, and the expected results. It maps directly to one or more Requirements via a `verifies` trace link. A Test Case answers the question: *How do we test this requirement?*
*   **Test Run (Execution):** A Test Run is an instance of a Test Case being executed in a specific environment at a specific time. It contains the actual outcome (Passed, Failed, Blocked) and the execution logs. A Test Run answers the question: *Did the system pass this test today?*

**Rationale:** Separating definition (Test Case) from execution (Test Run) allows us to track historical test performance over time and across different environments without altering the fundamental test specification.

## 3. Test Status in Requirements Documents

All requirements documents (L1, L2, L3) include a **Test Status** field. This field is a direct reflection of our V&V coverage and execution state:

*   **Missing:** No Test Case is linked to this requirement, or the linked Test Case is incomplete.
*   **Covered:** At least one valid Test Case is linked to the requirement, verifying its implementation.
*   **Passed:** The requirement is `Covered` AND the most recent Test Run for all linked Test Cases is successful.
*   **Failed:** The requirement is `Covered`, but the most recent Test Run for at least one linked Test Case has failed.
*   **Suspect:** A requirement change or upstream change has invalidated the current test results (see Suspect Linking).

*Note: For the static documentation currently, we primarily use `Covered` and `Missing` to denote the existence of a Test Case. As the system evolves to track dynamic executions, `Passed`, `Failed`, and `Suspect` will be derived dynamically.*

## 4. Suspect Linking and Test Invalidation

Suspect linking is a core traceability feature that ensures test coverage remains valid as the system changes. 

When a requirement is modified, or when an upstream requirement that it derives from changes:
1.  **Trace Link Invalidation:** The trace links from the changed requirement to its downstream Test Cases are marked as *suspect*.
2.  **Status Propagation:** The `Test Status` of the affected requirement transitions to `Suspect`.
3.  **Required Action:** The V&V team must review the suspect Test Case to determine if it needs an update. Once the Test Case is updated or confirmed still valid, the suspect flag is cleared, and a new Test Run must be executed to restore the `Passed` status.

This ensures that our test coverage never silently rots due to requirement drifts.

## 5. Integration Testing across Architecture Levels (L1 to Ln)

Our system architecture is decomposed from L1 (System) down to L3 (Component). Testing follows a V-Model approach, where integration testing bridges the decomposition levels from the bottom up.

*   **L3 Component Tests (Unit/Module):** 
    *   **Scope:** Individual components (e.g., `ArtifactService`, `WorkflowFacade`).
    *   **Strategy:** Automated unit testing using mocks for external dependencies. These verify L3 requirements.
*   **L2 Subsystem Integration Tests:**
    *   **Scope:** Interaction between components within a specific subsystem (e.g., `ApplicationServiceSystem`).
    *   **Strategy:** Automated API and integration tests. We deploy the subsystem in a local environment (e.g., Docker compose) with simulated external systems. These tests verify L2 requirements and ensure L3 components integrate correctly.
*   **L1 System Validation & Acceptance Tests:**
    *   **Scope:** The entire ReqFlow system (Frontend + Backend + DB).
    *   **Strategy:** End-to-End (E2E) UI testing, user journey simulations, and performance load tests. These tests are executed against a fully deployed staging environment and verify the L1 System Requirements.

**Management of Integration Tests:**
Integration tests (L2 and L1) are managed as first-class Test Cases. They must trace back to the respective L2 or L1 requirements. A bottom-up execution strategy is mandated: L3 tests must pass before L2 integration tests are executed, and L2 must pass before L1 E2E tests are initiated.
