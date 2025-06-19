"""
Script to generate a review plan for Prolific submissions with completion code validation.

This script:
1. Fetches submissions from Prolific (including their actual completion codes)
2. Reads your CSV analysis file  
3. Compares actual completion codes vs. your CSV predictions
4. Generates a plan showing agreements/disagreements
5. Recommends actions based on actual completion codes (trusting Qualtrics)

Usage:
    python "Python files/generate_review_plan.py"
"""

import sys
import os
import csv
import json

# Adjust sys.path to import modules from the parent directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(SCRIPT_DIR)
if PARENT_DIR not in sys.path:
    sys.path.append(PARENT_DIR)

# --- Define Project Root relative to this script ---
# This allows the script to be run from any directory
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "../../../../../../"))

import prolific_utils
import config

# Import completion codes configuration
try:
    sys.path.append(os.path.dirname(__file__))
    from completion_codes_config import determine_completion_code, get_code_name, COMPLETION_CODES
except ImportError:
    print("ERROR: Could not import completion_codes_config.py. Make sure it's in the same directory as this script.")
    sys.exit(1)

CSV_COLUMN_PROLIFIC_ID = "prolific_id"

def get_study_submissions(study_id):
    """
    Retrieves a list of submissions for a specific Prolific study.
    """
    print(f"\nAttempting to retrieve submissions for Study ID: {study_id}")
    endpoint = f'/studies/{study_id}/submissions/'
    submissions_response = prolific_utils.make_api_request(method='GET', endpoint=endpoint)

    if submissions_response and 'results' in submissions_response:
        submissions_list = submissions_response['results']
        print(f"Successfully retrieved {len(submissions_list)} submission(s) for study {study_id}.")
        
        # Sort submissions by the time they were started to ensure a consistent order
        submissions_list.sort(key=lambda x: x.get('started_at', ''))
        
        return submissions_list
    else:
        print(f"Failed to retrieve submissions for study {study_id}.")
        return []

def load_participant_flags(csv_filepath):
    """
    Loads participant flags from the specified local CSV file.
    Returns a dictionary mapping prolific_id to the full CSV row.
    """
    participant_data = {}
    
    try:
        with open(csv_filepath, mode='r', encoding='utf-8', newline='') as infile:
            reader = csv.DictReader(infile)
            required_columns = [CSV_COLUMN_PROLIFIC_ID, 'status']
            
            # Check if required columns exist
            if not all(col in reader.fieldnames for col in required_columns):
                print(f"ERROR: CSV file must contain columns: {required_columns}")
                print(f"Found columns: {reader.fieldnames}")
                return None

            print(f"CSV columns found: {reader.fieldnames}")

            for row_num, row in enumerate(reader, 1):
                prolific_id = row.get(CSV_COLUMN_PROLIFIC_ID, '').strip()

                if not prolific_id:
                    print(f"WARNING: Skipping row {row_num} due to missing '{CSV_COLUMN_PROLIFIC_ID}'.")
                    continue
                
                # Skip header-like rows
                if prolific_id.upper() in ['PROLIFIC_ID', 'ATTN CHECKS', 'NO CONSENT']:
                    print(f"INFO: Skipping header/example row {row_num}: {prolific_id}")
                    continue
                
                if prolific_id not in participant_data:
                    participant_data[prolific_id] = row

        print(f"Successfully loaded {len(participant_data)} participant records from {csv_filepath}.")
        return participant_data
        
    except FileNotFoundError:
        print(f"ERROR: CSV file not found at {csv_filepath}")
        return None
    except Exception as e:
        print(f"ERROR: Could not read CSV file {csv_filepath}. Error: {e}")
        return None

def generate_review_plan(prolific_submissions, participant_data):
    """
    Generates a plan by comparing actual completion codes with local status decisions.
    """
    review_plan = []
    validation_summary = {'matches': 0, 'mismatches': 0, 'csv_only': 0, 'code_only': 0, 'neither': 0}
    
    for sub in prolific_submissions:
        submission_id = sub.get('id')
        participant_id = sub.get('participant_id')
        current_status = sub.get('status')
        actual_completion_code = sub.get('study_code', '')

        # Defaults
        proposed_action = "NO_ACTION_NO_CSV_DATA"
        local_status = ""
        local_reason = ""
        local_category = ""
        validation_status = "NO_CSV_DATA"
        notes = ""

        if participant_id in participant_data:
            csv_row = participant_data[participant_id]
            
            # Read the processed status from CSV (not raw survey data)
            local_status = csv_row.get('status', '').strip()
            local_reason = csv_row.get('reason', '').strip()  
            local_category = csv_row.get('category', '').strip()
            
            # Compare actual completion code with local decision
            if actual_completion_code and local_status:
                # Map completion codes to expected local statuses
                # (This mapping should align with your R script logic)
                if ((actual_completion_code in ['C1DQRLH1', 'COMPLETION_CODE_APPROVED'] and local_status == "APPROVED") or
                    (actual_completion_code in ['TIMEOUT', 'FAILED_ATTENTION'] and local_status == "REJECTED") or  
                    (actual_completion_code in ['NO_CONSENT', 'SCREENED_OUT'] and local_status in ["SCREENED-OUT", "REJECTED"])):
                    validation_status = "MATCH"
                    validation_summary['matches'] += 1
                    # Propose action based on local status
                    if local_status == "APPROVED":
                        proposed_action = "APPROVE"
                    elif local_status == "REJECTED":
                        proposed_action = "REJECT"
                    elif local_status == "SCREENED-OUT":
                        proposed_action = "SCREEN_OUT"
                else:
                    validation_status = "MISMATCH"
                    validation_summary['mismatches'] += 1
                    notes = f"Local analysis: {local_status} but Qualtrics code: {actual_completion_code}"
                    proposed_action = "MANUAL_REVIEW_MISMATCH"
                    
            elif actual_completion_code and not local_status:
                validation_status = "CODE_ONLY"
                validation_summary['code_only'] += 1
                notes = "Qualtrics assigned code but no local decision found"
                proposed_action = "MANUAL_REVIEW_NO_LOCAL_DECISION"
                
            elif not actual_completion_code and local_status:
                validation_status = "CSV_ONLY"
                validation_summary['csv_only'] += 1
                notes = "Local decision exists but no completion code from Qualtrics"
                # Still propose action based on local decision, but flag for verification
                if local_status == "APPROVED":
                    proposed_action = "APPROVE_NO_CODE"
                elif local_status == "REJECTED":
                    proposed_action = "REJECT_NO_CODE"
                elif local_status == "SCREENED-OUT":
                    proposed_action = "SCREEN_OUT_NO_CODE"
                    
            else:
                validation_status = "NEITHER"
                validation_summary['neither'] += 1
                notes = "No completion code and no local decision"
                proposed_action = "MANUAL_REVIEW_NO_DATA"
        else:
            print(f"INFO: P_ID {participant_id} (Sub {submission_id}) not found in local data.")
            if actual_completion_code:
                proposed_action = "APPROVE_NO_LOCAL_DATA"
                notes = "Using completion code (participant not in local data)"
            else:
                proposed_action = "MANUAL_REVIEW_NO_LOCAL_DATA"

        review_plan.append({
            "prolific_submission_id": submission_id,
            "prolific_participant_id": participant_id,
            "current_prolific_status": current_status,
            "actual_completion_code": actual_completion_code,
            "local_status": local_status,
            "local_reason": local_reason,
            "local_category": local_category,
            "validation_status": validation_status,
            "proposed_action": proposed_action,
            "notes": notes
        })

    # Print validation summary
    print(f"\n=== VALIDATION SUMMARY ===")
    print(f"MATCHES (local and Qualtrics agree): {validation_summary['matches']}")
    print(f"MISMATCHES (local and Qualtrics disagree): {validation_summary['mismatches']}")
    print(f"CODE_ONLY (Qualtrics assigned, no local decision): {validation_summary['code_only']}")
    print(f"CSV_ONLY (local decision, no Qualtrics code): {validation_summary['csv_only']}")
    print(f"NEITHER (no code, no local decision): {validation_summary['neither']}")

    if validation_summary['mismatches'] > 0:
        print(f"\n⚠️  You have {validation_summary['mismatches']} mismatches to investigate!")
        print("Recommended: Review the output CSV to understand why local and Qualtrics disagree.")
    else:
        print(f"\n✅ No mismatches found! Local analysis and Qualtrics are in agreement.")

    return review_plan

def save_review_plan_to_csv(review_plan, output_filepath="review_plan_with_validation.csv"):
    """
    Saves the generated review plan with validation results to a CSV file.
    """
    if not review_plan:
        print("No review plan data to save.")
        return
    
    output_dir = os.getcwd()
    full_output_path = os.path.join(output_dir, output_filepath)

    fieldnames = [
        "prolific_submission_id", 
        "prolific_participant_id", 
        "current_prolific_status",
        "actual_completion_code",
        "local_status",
        "local_reason",
        "local_category",
        "validation_status",
        "proposed_action",
        "notes"
    ]
    
    try:
        with open(full_output_path, mode='w', encoding='utf-8', newline='') as outfile:
            writer = csv.DictWriter(outfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(review_plan)
        print(f"\nReview plan with validation saved to: {full_output_path}")
        
        # Print action summary
        action_counts = {}
        validation_counts = {}
        for row in review_plan:
            action = row['proposed_action']
            validation = row['validation_status']
            action_counts[action] = action_counts.get(action, 0) + 1
            validation_counts[validation] = validation_counts.get(validation, 0) + 1
        
        print("\nProposed Actions:")
        for action, count in action_counts.items():
            print(f"  {action}: {count}")
            
    except Exception as e:
        print(f"ERROR: Could not save review plan to CSV at {full_output_path}. Error: {e}")


if __name__ == "__main__":
    print("--- Completion Code Validation & Review Plan Generation ---")
    print("This script compares your CSV analysis with actual Qualtrics completion codes.")
    print(f"Configured completion codes: {COMPLETION_CODES}\n")

    # 1. Get Prolific Study ID from config.py
    if not hasattr(config, 'PROLIFIC_STUDY_ID') or not config.PROLIFIC_STUDY_ID or config.PROLIFIC_STUDY_ID == "YOUR_ACTUAL_PROLIFIC_STUDY_ID" or config.PROLIFIC_STUDY_ID == "YOUR_STUDY_ID_HERE":
        print("\nERROR: PROLIFIC_STUDY_ID is not set or is a placeholder in config.py.")
        print("Please set config.PROLIFIC_STUDY_ID = \"YOUR_ACTUAL_PROLIFIC_STUDY_ID\"")
        sys.exit(1)
    STUDY_ID_TO_PROCESS = config.PROLIFIC_STUDY_ID
    print(f"Using Prolific Study ID from config.py: {STUDY_ID_TO_PROCESS}")

    # 2. Define the path to local CSV file using the project root
    relative_csv_path = "Code and data/FULL SURVEY data/Final survey data/all_participants_rejection_flags_15May25AK.csv"
    local_csv_path = os.path.join(PROJECT_ROOT, relative_csv_path)
    print(f"Using CSV file: {local_csv_path}")

    # 3. Fetch submissions from Prolific
    prolific_submissions = get_study_submissions(STUDY_ID_TO_PROCESS)

    # 4. Load participant flags from CSV
    participant_flags = load_participant_flags(local_csv_path)

    # 5. Generate the review plan with validation
    if prolific_submissions is not None and participant_flags is not None:
        if not prolific_submissions:
            print("No submissions found for this study on Prolific. Nothing to plan.")
        elif not participant_flags:
            print("No valid participant data loaded from CSV (check for errors above). Cannot generate plan.")
        else:
            plan = generate_review_plan(prolific_submissions, participant_flags)
            save_review_plan_to_csv(plan, "review_plan_with_validation.csv")
    else:
        print("Could not generate review plan due to errors.")

    print("--- Review Plan Generation with Validation Finished ---") 