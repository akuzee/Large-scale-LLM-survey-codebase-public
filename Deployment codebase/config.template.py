# Template for configuring the Survey Data Processing Pipeline
# Copy this file to config.py and fill in your actual credentials.
# The config.py file is ignored by git to protect sensitive information.

# --- Prolific API Credentials ---
# Found in your Prolific account settings under "API"
PROLIFIC_API_TOKEN = "YOUR_PROLIFIC_API_TOKEN"

# --- Qualtrics API Credentials ---
# Found in your Qualtrics account settings -> Qualtrics IDs -> API
QUALTRICS_API_TOKEN = "YOUR_QUALTRICS_API_TOKEN"
QUALTRICS_DATACENTER_ID = "YOUR_QUALTRICS_DATACENTER_ID" # e.g., "ca1", "eu1", "au1", "co1"

# --- Survey & Study Identifiers ---
QUALTRICS_SURVEY_ID = "YOUR_QUALTRICS_SURVEY_ID" # The ID of the survey you want to export
PROLIFIC_STUDY_ID = "YOUR_PROLIFIC_STUDY_ID" # The ID of the Prolific study 