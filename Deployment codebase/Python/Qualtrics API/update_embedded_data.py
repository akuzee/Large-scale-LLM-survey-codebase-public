import requests
import json
import os
from typing import List, Optional
import traceback # Added for more detailed exception logging
import config # Import our configuration

HIDDEN_OCCUPATION_NUMBERS_FILE = "qualtrics_hidden_occupation_numbers.txt"

class QualtricsEmbeddedDataUpdater:
    def __init__(self, api_token: str, data_center_id: str, survey_id: str):
        """
        Initialize the Qualtrics embedded data updater.
        
        Args:
            api_token (str): Your Qualtrics API token
            data_center_id (str): Your Qualtrics data center ID (e.g., 'co1')
            survey_id (str): The ID of the survey to update
        """
        self.api_token = api_token
        self.data_center_id = data_center_id
        self.survey_id = survey_id
        self.base_url = f"https://{self.data_center_id}.qualtrics.com/API/v3"
        self.headers = {
            "X-API-TOKEN": self.api_token,
            "Content-Type": "application/json"
        }

    def update_hidden_occupation_numbers(self, occupation_numbers: List[int]) -> bool:
        """Updates an existing Embedded Data element named
        ``hidden_occupation_numbers`` in the Survey Flow so that its value is set
        to the provided comma-separated list of occupation numbers.

        If the 'hidden_occupation_numbers' field is not found within any
        EmbeddedData element in the survey flow, this method will
        print a message and return False without making changes.

        This uses the Survey Definition Flow endpoints:
        1. GET /survey-definitions/{surveyId}/flow   – to fetch current flow.
        2. Locate the EmbeddedData element containing the 'hidden_occupation_numbers' field.
        3. If found, PUT the updated element to /survey-definitions/{surveyId}/flow/{flowElementId}.
        """
        try:
            occupation_numbers_str = ",".join(map(str, occupation_numbers))
            print(f"Attempting to set hidden_occupation_numbers to: {occupation_numbers_str}")

            # 1. Fetch current flow definition
            flow_url = f"{self.base_url}/survey-definitions/{self.survey_id}/flow"
            print(f"Fetching survey flow from: {flow_url}")
            flow_resp = requests.get(flow_url, headers=self.headers)
            
            print(f"Get flow response status: {flow_resp.status_code}")
            if flow_resp.status_code != 200:
                print(f"Failed to fetch survey flow. Response text: {flow_resp.text}")
                return False

            try:
                flow_data_full = flow_resp.json()
                flow_data = flow_data_full.get("result", {})
            except json.JSONDecodeError:
                print(f"Failed to decode JSON from get flow response. Response text: {flow_resp.text}")
                return False
                
            if not flow_data or "Flow" not in flow_data:
                print(f"Survey flow data is missing 'result' or 'Flow' key. Full response: {json.dumps(flow_data_full, indent=2)}")
                return False
            flow_elements = flow_data.get("Flow", [])
            print(f"Found {len(flow_elements)} elements in the survey flow.")

            target_element = None
            field_found_in_element = False
            for i, el in enumerate(flow_elements):
                if el.get("Type") == "EmbeddedData":
                    current_embedded_data_list = el.get("EmbeddedData", [])
                    for ed_field_obj in current_embedded_data_list:
                        if ed_field_obj.get("Field") == "hidden_occupation_numbers":
                            print(f"  Found 'hidden_occupation_numbers' field in element with FlowID: {el.get('FlowID')}")
                            target_element = el
                            
                            ed_field_obj["Value"] = occupation_numbers_str
                            ed_field_obj["Type"] = "Custom" 
                            print(f"    Updated field object locally: {json.dumps(ed_field_obj, indent=2)}")
                            field_found_in_element = True
                            break 
                if target_element and field_found_in_element:
                    break 
            
            if target_element and field_found_in_element:
                target_flow_id = target_element['FlowID']
                update_url = f"{flow_url}/{target_flow_id}"
                print(f"Attempting to PUT updated element to: {update_url}")
                print(f"Payload for PUT request (element FlowID: {target_flow_id}):\\n{json.dumps(target_element, indent=2)}")
                update_resp = requests.put(update_url, headers=self.headers, json=target_element)
                
                print(f"Update flow element response status: {update_resp.status_code}")
                print(f"Update flow element response text: {update_resp.text}")

                if update_resp.status_code == 200:
                    print(f"Successfully updated hidden_occupation_numbers = {occupation_numbers_str} in element {target_flow_id}")
                    return True
                else:
                    print(f"Failed to update embedded data field in element {target_flow_id}.")
                    return False
            else:
                print(f"Embedded data field 'hidden_occupation_numbers' not found in the survey flow. Please ensure it exists and is of Type 'EmbeddedData'.")
                return False

        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            print(traceback.format_exc())
            return False

def main():
    # Initialize updater from config.py
    if not all([config.QUALTRICS_API_TOKEN, config.QUALTRICS_DATACENTER_ID, config.QUALTRICS_SURVEY_ID]):
        print("Please ensure QUALTRICS_API_TOKEN, QUALTRICS_DATACENTER_ID, and QUALTRICS_SURVEY_ID are set in config.py")
        return
        
    updater = QualtricsEmbeddedDataUpdater(
        api_token=config.QUALTRICS_API_TOKEN,
        data_center_id=config.QUALTRICS_DATACENTER_ID,
        survey_id=config.QUALTRICS_SURVEY_ID
    )
    
    occupation_numbers_to_hide = []
    try:
        # Determine the absolute path to the script's directory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, HIDDEN_OCCUPATION_NUMBERS_FILE)
        
        print(f"Attempting to read hidden occupation numbers from: {file_path}")
        with open(file_path, 'r') as f:
            line = f.readline().strip()
            if line:
                occupation_numbers_to_hide = [int(num_str.strip()) for num_str in line.split(',') if num_str.strip().isdigit()]
                if not occupation_numbers_to_hide and line: # handles cases like "a,b,c" or empty strings between commas
                    print(f"Warning: File '{file_path}' contained non-integer or improperly formatted data: '{line}'. Proceeding with empty list.")
            else:
                print(f"Warning: File '{file_path}' is empty. No occupation numbers will be hidden.")
        
        if not occupation_numbers_to_hide and line: # If parsing resulted in empty list but file wasn't empty
             print(f"Could not parse any valid numbers from '{line}' in '{file_path}'. Check file format (e.g., 1,2,3).")
             # Decide if you want to exit or proceed with empty:
             # return 

    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found. Please create it with comma-separated numbers.")
        return 
    except ValueError as ve:
        print(f"Error: Could not parse numbers from '{file_path}'. Ensure it contains comma-separated integers. Details: {ve}")
        return
    except Exception as e:
        print(f"An unexpected error occurred while reading the file: {e}")
        print(traceback.format_exc())
        return

    if not occupation_numbers_to_hide:
        print("No valid occupation numbers to hide were read from the file. The embedded data field might be set to an empty string if it exists.")
        # If you want to ensure it's always a non-empty string for Qualtrics, you could default here,
        # or let it proceed to potentially set an empty value. For now, it proceeds.

    print(f"Numbers to set in Qualtrics for 'hidden_occupation_numbers': {occupation_numbers_to_hide}")
    
    success = updater.update_hidden_occupation_numbers(occupation_numbers_to_hide)
    
    if success:
        print("Update completed successfully")
    else:
        print("Update failed")

if __name__ == "__main__":
    main() 