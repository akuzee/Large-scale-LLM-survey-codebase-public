# Tests & Edge Cases for Prolific Approval/Rejection Pipeline

## High-Level Summary

This document outlines critical tests and edge cases for `generate_review_plan.py` and `execute_prolific_actions.py`. The focus is on non-obvious issues, API interactions, data integrity, state management, and resumability, rather than basic file handling or issues the scripts already robustly address.

1.  **Input Data & CSV Integrity**: Handling of malformed Study IDs, missing or inconsistent Prolific IDs in local CSVs, absence of critical columns (especially newly required `rejection_reason`, `rejection_category`), and validation of rejection details.
2.  **File System & Permissions**: Addressing CSV read/write permission issues beyond simple file existence, and the implications of `generate_review_plan.py` overwriting an existing `review_plan.csv` that might have manual edits.
3.  **API Interaction & Reliability**: Robustness against network failures, authentication/authorization errors (401/403), API rate limits (429), Prolific server-side errors (5xx), and correct handling of API pagination for large studies.
4.  **State Management & Synchronisation**: Managing discrepancies between Prolific's live submission statuses and the local data/plan, such as submissions already actioned manually or plans generated from outdated decision CSVs.
5.  **Resumability & Idempotency**: Ensuring `execute_prolific_actions.py` can recover gracefully from interruptions (e.g., network issues, script crash) and that re-running actions does not cause unintended side-effects or duplicate processing.
6.  **Script Logic & Error Handling**: Behavior of scripts on validation failures (e.g., stop processing vs. skip item vs. warn), and robustness of user confirmation prompts.
7.  **Performance & Scalability**: Behavior with very large studies (e.g., >10,000 submissions), particularly memory usage in `generate_review_plan.py` and total execution time for `execute_prolific_actions.py`.
8.  **Security & Data Privacy**: Safeguarding the Prolific API token and ensuring sensitive information in rejection reasons or logs is handled appropriately.

---

## Detailed Discussion

### 1. Input Data & CSV Integrity

#### `generate_review_plan.py`
*   **Invalid or Missing Study ID**: Ensure graceful failure with a clear message if the Prolific API returns an error (e.g., 404) for the provided Study ID.
*   **Local CSV Column Integrity**: Verify script halts or clearly warns if essential columns (`prolific_id`, `approval_status`, `rejection_reason`, `rejection_category`) are missing from the user-supplied CSV.
*   **Duplicate `prolific_id` Rows in Local CSV**: Test behavior when the input CSV contains duplicate `prolific_id` entries. Define and verify the conflict resolution strategy (e.g., use first, use last, error out).
*   **Rejection Reason Quality (Warning vs. Inclusion)**: Confirm that a warning is issued for rejection reasons under 100 characters, but the submission is still included in `review_plan.csv`. Test boundary conditions.
*   **Rejection Category Presence (Warning vs. Inclusion)**: Confirm that a warning is issued if `rejection_category` is missing for a 'REJECT' decision in the local CSV, but the submission is still included.
*   **Encoding of User-Supplied CSV**: Test with user CSVs in different encodings (e.g., with UTF-8 BOM, Latin-1) as `generate_review_plan.py` might use system default encoding if not specified, potentially leading to misinterpretation.

#### `execute_prolific_actions.py`
*   **`review_plan.csv` Column Integrity**: Ensure the script requires `prolific_submission_id`, `proposed_action`, and (for rejections) `rejection_reason`, `rejection_category`.
*   **Action String Variations**: Test robustness against variations in `proposed_action` strings (e.g., "Approve", "approve ", "APPROVE") from `review_plan.csv` (noting the script already uses `.strip().upper()`).
*   **Rejection Reason Length Enforcement**: Verify that `execute_prolific_actions.py` enforces the ≥10 character minimum for rejection reasons before an API call, testing boundary conditions.
*   **Rejection Category Enforcement**: Confirm an error occurs and the action is skipped if `rejection_category` is missing for a `REJECT` action.
*   **Unsupported Actions in `review_plan.csv`**: Check that actions other than `APPROVE`, `REJECT`, or recognized no-action tags are logged and skipped.

### 2. File System & Permissions
*   **Path/Permission Issues for CSVs**: Test scenarios beyond simple file non-existence:
    *   `generate_review_plan.py`: Read permission denied for the input local CSV.
    *   `generate_review_plan.py`: Write permission denied for the output `review_plan.csv` in the target directory.
    *   `execute_prolific_actions.py`: Read permission denied for `review_plan.csv`.
*   **Overwriting Existing `review_plan.csv`**: `generate_review_plan.py` overwrites `review_plan.csv`. If users might manually edit this file, this could lead to loss of intermediate work. Consider this implication.

### 3. API Interaction & Reliability
*   **Network Outages/DNS Failures**: Simulate `requests.exceptions.ConnectionError` during API calls in both scripts; verify graceful exit or retry logic if implemented.
*   **HTTP 429 Rate Limiting (`execute_prolific_actions.py`)**: The current 0.5s sleep between actions might be insufficient for large batches. Test behavior under sustained rate-limiting and consider if adaptive back-off is needed.
*   **HTTP 5xx Server Errors (Prolific)**: Test how scripts handle transient 500-range errors from Prolific. Currently, no explicit retry logic exists; this could lead to partial failure.
*   **API Token Issues (401/403 Unauthorized/Forbidden)**: Ensure clear error reporting if the API token is invalid, expired, or lacks permissions, without exposing the token itself in logs.
*   **Prolific API Pagination (`generate_review_plan.py`)**: Critically test that `get_study_submissions` correctly iterates through all pages of results for studies with many submissions, ensuring no data is missed.

### 4. State Management & Synchronisation
*   **Submissions Already Actioned on Prolific (Pre-Plan Generation)**: `generate_review_plan.py` should ideally identify submissions in the Prolific fetch that are *not* `AWAITING_REVIEW` and flag them in `review_plan.csv` (e.g., `NO_ACTION_ALREADY_APPROVED`) to prevent redundant proposals.
*   **Submissions Actioned on Prolific (Post-Plan Generation, Pre-Execution)**: If a submission is manually approved/rejected on Prolific *after* `review_plan.csv` is generated but *before* `execute_prolific_actions.py` runs, the API call will likely fail (e.g., 400 error). The script should handle this for the specific submission (log error, mark as failed/skipped) and continue with others.
*   **Using a Stale Local Decision CSV with `generate_review_plan.py`**: If the user's input CSV (with `approval_status`, etc.) is outdated, the generated `review_plan.csv` will not reflect the intended actions. This is a process consideration.

### 5. Resumability & Idempotency (`execute_prolific_actions.py`)
*   **Interruption During Execution Loop**: If `execute_prolific_actions.py` is interrupted (crash, Ctrl-C, network loss mid-way):
    *   The script currently does not log successfully completed individual actions to a persistent state file before completing all actions.
    *   Re-running the script will re-attempt all actions listed in `review_plan.csv`. Actions on already-transitioned submissions will likely result in API errors from Prolific (see State Management point above).
    *   Consider strategies for robust recovery:
        1.  Log successful Prolific API calls to a separate audit/completion log. On restart, check this log and skip already processed submissions.
        2.  (More complex) Before attempting transition, query Prolific for the submission's current status. This adds API calls but ensures idempotency.

### 6. Script Logic & Error Handling
*   **Robustness of 'Proceed?' Prompt (`execute_prolific_actions.py`)**: Test the confirmation prompt's handling of various inputs (e.g., mixed case, leading/trailing whitespace, anything other than 'yes').
*   **Error Handling Strategy on Validation Failures**:
    *   `generate_review_plan.py`: Clarify and test behavior on critical input CSV data errors (e.g., missing required columns). Does it exit, skip the row, or proceed with warnings?
    *   `execute_prolific_actions.py`: It currently prints an error and returns `False` from `transition_single_submission` on validation/API failure, allowing the main loop to continue. Confirm this is the desired behavior for all anticipated per-submission errors.

### 7. Performance & Scalability
*   **Large Studies (>10,000 submissions)**:
    *   `generate_review_plan.py`: Builds an in-memory list (`review_plan`). Monitor memory usage with very large studies.
    *   `execute_prolific_actions.py`: The loop with a 0.5s sleep implies long runtimes (e.g., ~1.4 hours for 10k submissions). Consider if API token expiry could become an issue during such long runs (if tokens are short-lived).
*   **API Call Efficiency**: Ensure `get_study_submissions` in `generate_review_plan.py` uses pagination efficiently and doesn't make excessive calls.

### 8. Security & Data Privacy
*   **API Token Exposure**: Ensure `config.py` (containing the token) is appropriately gitignored and that no error message or log inadvertently prints the token.
*   **Sensitive Data in Rejection Reasons**: If rejection reasons might contain Participant PII or other sensitive data, ensure `review_plan.csv` and any logs are stored and handled securely.

---

## Suggested Automated Tests (Conceptual)

1.  **Unit Test `generate_review_plan.py` Merge Logic**: Mock Prolific API submission data and local CSV data; assert correct `proposed_action` and warnings based on diverse inputs (e.g., matching IDs, missing local data, already approved Prolific status).
2.  **Unit Test Validation Helpers**: Test specific validation functions, e.g., for rejection reason length, category presence, in both scripts.
3.  **Integration Test with Mock/Sandbox Prolific API**:
    *   Set up a mock Prolific API endpoint or use a sandbox environment.
    *   Create a small study with various submission statuses.
    *   Provide a local CSV. Run `generate_review_plan.py`, inspect `review_plan.csv`.
    *   Run `execute_prolific_actions.py` against the generated plan. Assert mock API received correct calls and final (mocked) statuses.
4.  **Resumability Test (`execute_prolific_actions.py`)**:
    *   Prepare a `review_plan.csv` with several actions.
    *   Run `execute_prolific_actions.py`, simulate an interruption (e.g., terminate script) after a few actions.
    *   Modify mock API to reflect these completed actions.
    *   Re-run `execute_prolific_actions.py`. Verify it attempts only remaining actions or handles already-completed ones gracefully (e.g., skips based on an audit log or by checking status if implemented).
5.  **API Rate Limit Test (`execute_prolific_actions.py`)**: Monkey-patch `requests.post` to return HTTP 429 after N calls. Verify script behavior (e.g., pauses, retries if implemented, or exits after failures).

---

## Observability & Logging Improvements (Future Work Ideas)

*   Implement structured (e.g., JSON) logging for clearer audit trails, especially for API requests/responses.
*   Maintain a persistent, append-only execution log for `execute_prolific_actions.py` detailing each submission ID, action attempted, parameters, and outcome (success/failure, API response).
*   Add CLI flags for more control: e.g., `--dry-run` (for both scripts), `--stop-on-first-error` (for `execute_prolific_actions.py`), `--resume-from-log <log_file_path>`.
*   Consider using a progress bar (e.g., `tqdm`) for `execute_prolific_actions.py` instead of simple print statements for better UX with large plans. 