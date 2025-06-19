"""
Completion codes configuration for Prolific study.

This file contains the mapping between CSV flags and Prolific completion codes.
Update the COMPLETION_CODES dictionary when codes change.
"""

# === COMPLETION CODES CONFIGURATION === #
COMPLETION_CODES = {
    "APPROVED": "C1G9PC0D",          # Default - auto-approve
    "SCREENED_OUT": "C1NFUEQ1",      # Screened out participants  
    "FAILED_ATTENTION": "C1M8R1Y4",  # Failed attention checks
    "NO_CONSENT": "COISODYI"         # Did not give consent
}

# === CSV FLAG TO COMPLETION CODE MAPPING === #
def determine_completion_code(csv_row):
    """
    Determines the appropriate completion code based on CSV flags.
    
    Args:
        csv_row (dict): A row from the CSV with participant flags
        
    Returns:
        tuple: (completion_code, reason_for_decision)
    """
    
    # Check for no consent (highest priority)
    if csv_row.get('no_consent', '').strip().upper() == 'TRUE':
        return COMPLETION_CODES["NO_CONSENT"], "Participant did not provide valid consent to participate in this research study. Consent is required for all participants as per ethical research guidelines and institutional requirements."
    
    # Check for failed attention checks
    if csv_row.get('failed_two_plus_attention_checks', '').strip().upper() == 'TRUE':
        return COMPLETION_CODES["FAILED_ATTENTION"], "Participant failed two or more attention checks, indicating insufficient attention to study requirements."
    
    # Check for other screening issues
    screening_flags = [
        'did_not_understand_tasks',
        'occupation_not_confirmed', 
        'insufficient_work_experience'
    ]
    
    for flag in screening_flags:
        if csv_row.get(flag, '').strip().upper() == 'TRUE':
            return COMPLETION_CODES["SCREENED_OUT"], f"Participant was screened out due to: {flag.replace('_', ' ')}"
    
    # Check if they were screened out for other reasons
    if csv_row.get('screened_out', '').strip().upper() == 'TRUE':
        return COMPLETION_CODES["SCREENED_OUT"], "Participant was screened out during the study process."
    
    # Check if study was incomplete for other reasons
    if csv_row.get('incomplete_survey_other_reasons', '').strip().upper() == 'TRUE':
        return COMPLETION_CODES["FAILED_ATTENTION"], "Participant did not complete the survey for other reasons indicating insufficient engagement."
    
    # Default case - should be approved
    if csv_row.get('completed_survey', '').strip().upper() == 'TRUE' and csv_row.get('approved', '').strip().upper() != 'FALSE':
        return COMPLETION_CODES["APPROVED"], "Participant successfully completed the study and met all requirements."
    
    # Fallback - manual review needed
    return None, "Unable to determine appropriate completion code - requires manual review."

def get_api_action_for_completion_code(completion_code):
    """
    Determines what API action to take based on the completion code.
    
    Args:
        completion_code (str): The completion code from Qualtrics
        
    Returns:
        str: The action to take ("SKIP", "REJECT", "SCREEN_OUT")
    """
    if completion_code == COMPLETION_CODES["APPROVED"]:
        return "SKIP"  # Auto-approves, no action needed
    elif completion_code == COMPLETION_CODES["SCREENED_OUT"]:
        return "SCREEN_OUT"  # Use bulk screen out endpoint
    elif completion_code in [COMPLETION_CODES["FAILED_ATTENTION"], COMPLETION_CODES["NO_CONSENT"]]:
        return "REJECT"  # Use reject action
    else:
        return "MANUAL_REVIEW"  # Unknown code, needs manual review

# === COMPLETION CODE REVERSE LOOKUP === #
def get_code_name(completion_code):
    """Get the human-readable name for a completion code."""
    if not completion_code:
        return ""
    
    for name, code in COMPLETION_CODES.items():
        if code == completion_code:
            return name
    return f"UNKNOWN({completion_code})"

def is_known_completion_code(completion_code):
    """Check if a completion code is in our expected set."""
    return completion_code in COMPLETION_CODES.values()

def get_all_completion_codes():
    """Get all configured completion codes as a list."""
    return list(COMPLETION_CODES.values())

def analyze_completion_code(completion_code):
    """
    Analyze a completion code and return detailed information.
    
    Returns:
        dict: Information about the completion code including whether it's known,
              its meaning, and expected outcome.
    """
    if not completion_code:
        return {
            'code': '',
            'known': False,
            'meaning': 'NO_CODE',
            'expected_outcome': 'UNKNOWN',
            'description': 'No completion code provided'
        }
    
    if completion_code in COMPLETION_CODES.values():
        # Find which type it is
        code_name = get_code_name(completion_code)
        
        expected_outcomes = {
            'APPROVED': 'AUTO_APPROVE',
            'SCREENED_OUT': 'SCREENED_OUT_WITH_PAYMENT', 
            'FAILED_ATTENTION': 'REJECT',
            'NO_CONSENT': 'REJECT'
        }
        
        descriptions = {
            'APPROVED': 'Participant completed successfully and should be auto-approved',
            'SCREENED_OUT': 'Participant was screened out and should receive screening payment',
            'FAILED_ATTENTION': 'Participant failed attention checks and should be rejected',
            'NO_CONSENT': 'Participant did not provide consent and should be rejected'
        }
        
        return {
            'code': completion_code,
            'known': True,
            'meaning': code_name,
            'expected_outcome': expected_outcomes.get(code_name, 'UNKNOWN'),
            'description': descriptions.get(code_name, 'Known completion code')
        }
    else:
        return {
            'code': completion_code,
            'known': False,
            'meaning': f'UNKNOWN({completion_code})',
            'expected_outcome': 'MANUAL_REVIEW',
            'description': f'Unknown completion code {completion_code} - requires manual review'
        } 