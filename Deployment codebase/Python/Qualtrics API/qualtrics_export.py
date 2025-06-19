import requests
import time
import os
import zipfile
import io
import config # Import the configuration file

# --- Configuration ---
# Details are now imported from config.py
API_TOKEN = config.QUALTRICS_API_TOKEN
DATA_CENTER_ID = config.QUALTRICS_DATACENTER_ID
SURVEY_ID = config.QUALTRICS_SURVEY_ID
FILE_FORMAT = "csv"  # Desired file format (e.g., "csv", "tsv", "spss")
OUTPUT_DIR = "/Users/adamkuzee/MIT Dropbox/adam/LLM survey/FULL SURVEY/Code and data/FULL SURVEY data/Raw Qualtrics Data"  # Folder to save the exported file
OUTPUT_FILENAME = "survey_export"  # Desired name for the output file (without extension)

# --- API Endpoints ---
BASE_URL = f"https://{DATA_CENTER_ID}.qualtrics.com/API/v3"
CREATE_EXPORT_URL = f"{BASE_URL}/responseexports"
GET_PROGRESS_URL = f"{BASE_URL}/responseexports/{{exportProgressId}}"
GET_FILE_URL = f"{BASE_URL}/responseexports/{{exportProgressId}}/file"

HEADERS = {
    "X-API-TOKEN": API_TOKEN,
    "Content-Type": "application/json",
}

def create_export_request(survey_id: str, file_format: str) -> str | None:
    """Initiates a response export request."""
    payload = {
        "format": file_format,
        "surveyId": survey_id
    }
    print(f"Initiating export for survey ID: {survey_id} in format: {file_format}...")
    response = requests.post(CREATE_EXPORT_URL, headers=HEADERS, json=payload)

    if response.status_code == 200:
        response_data = response.json()
        # Try both progressId and id fields as the API format might vary
        progress_id = response_data.get("result", {}).get("progressId") or response_data.get("result", {}).get("id")
        if progress_id:
            print(f"Export initiated. Progress ID: {progress_id}")
            return progress_id
        else:
            print(f"Error: Could not get progressId from response: {response_data}")
            return None
    else:
        print(f"Error creating export: {response.status_code} - {response.text}")
        return None

def get_export_progress(progress_id: str) -> tuple[str | None, str | None]:
    """Checks the progress of an ongoing export."""
    url = GET_PROGRESS_URL.format(exportProgressId=progress_id)
    print(f"Checking export progress for ID: {progress_id}...")
    response = requests.get(url, headers=HEADERS)

    if response.status_code == 200:
        response_data = response.json()
        status = response_data.get("result", {}).get("status")
        percent_complete = response_data.get("result", {}).get("percentComplete")
        file_id = response_data.get("result", {}).get("fileId") or progress_id  # Use progress_id as file_id if fileId not present

        if status:
            print(f"Status: {status}, Percent Complete: {percent_complete}%")
            if status == "complete":
                return "complete", file_id
            elif status == "failed":
                print(f"Error: Export failed. Response: {response_data}")
                return "failed", None
            return status, None  # Still in progress or other status
        else:
            print(f"Error: Could not get status from progress response: {response_data}")
            return "error", None
    else:
        print(f"Error checking progress: {response.status_code} - {response.text}")
        return "error", None

def download_export_file(file_id: str, output_dir: str, output_filename: str, file_format: str):
    """Downloads the exported file and saves it."""
    url = GET_FILE_URL.format(exportProgressId=file_id) # Note: Qualtrics uses progressId as fileId here
    print(f"Downloading file for file ID: {file_id}...")
    response = requests.get(url, headers=HEADERS, stream=True)

    if response.status_code == 200:
        # Ensure output directory exists
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"Created output directory: {output_dir}")

        # The file is a ZIP archive, even for CSV. We need to extract it.
        try:
            with zipfile.ZipFile(io.BytesIO(response.content)) as z:
                # List files in zip, find the one with the survey name or common data file extensions
                exported_filename_in_zip = ""
                for name_in_zip in z.namelist():
                    # Often the filename inside the zip matches the survey name or is a generic data file name.
                    # This logic might need adjustment based on actual naming conventions from Qualtrics.
                    if name_in_zip.lower().endswith(f".{file_format.lower()}"):
                         exported_filename_in_zip = name_in_zip
                         break
                
                if not exported_filename_in_zip and z.namelist():
                    # If specific format not found, pick the first one (assuming it's the data)
                    # This is a fallback and might not always be correct.
                    print(f"Warning: Could not find a definitive '.{file_format}' file. Extracting '{z.namelist()[0]}'.")
                    exported_filename_in_zip = z.namelist()[0]


                if exported_filename_in_zip:
                    extracted_file_path = os.path.join(output_dir, f"{output_filename}.{file_format}")
                    with open(extracted_file_path, 'wb') as f_out:
                        f_out.write(z.read(exported_filename_in_zip))
                    print(f"File extracted and saved to: {extracted_file_path}")
                else:
                    print(f"Error: Could not find the data file within the downloaded ZIP archive.")
                    # Save the zip for inspection if extraction fails
                    zip_path = os.path.join(output_dir, f"{output_filename}_archive.zip")
                    with open(zip_path, 'wb') as f_zip:
                        f_zip.write(response.content)
                    print(f"Downloaded ZIP archive saved to: {zip_path} for inspection.")

        except zipfile.BadZipFile:
            print("Error: Downloaded file is not a valid ZIP archive.")
            # Fallback: Save the raw content if it's not a zip (e.g., if API behavior changes)
            raw_file_path = os.path.join(output_dir, f"{output_filename}_raw.{file_format}")
            with open(raw_file_path, 'wb') as f_raw:
                f_raw.write(response.content)
            print(f"Raw downloaded content saved to: {raw_file_path}")
        except Exception as e:
            print(f"An error occurred during ZIP extraction: {e}")
            zip_path = os.path.join(output_dir, f"{output_filename}_archive_error.zip")
            with open(zip_path, 'wb') as f_zip:
                f_zip.write(response.content)
            print(f"Downloaded ZIP archive saved to: {zip_path} due to extraction error.")

    else:
        print(f"Error downloading file: {response.status_code} - {response.text}")

def main():
    """Main function to orchestrate the export process."""
    if not all([API_TOKEN, DATA_CENTER_ID, SURVEY_ID]):
        print("Please ensure QUALTRICS_API_TOKEN, QUALTRICS_DATACENTER_ID, and QUALTRICS_SURVEY_ID are set in config.py")
        return

    progress_id = create_export_request(SURVEY_ID, FILE_FORMAT)

    if progress_id:
        file_id_to_download = None
        while True:
            status, file_id = get_export_progress(progress_id)
            if status == "complete" and file_id:
                file_id_to_download = file_id
                print("Export complete and file is ready for download.")
                break
            elif status in ["failed", "error"]:
                print("Export process failed or encountered an error. Exiting.")
                return
            # Wait before checking progress again
            print("Waiting for 5 seconds before checking progress again...")
            time.sleep(5)
        
        if file_id_to_download:
            download_export_file(file_id_to_download, OUTPUT_DIR, OUTPUT_FILENAME, FILE_FORMAT)
        else:
            print("Could not retrieve file ID for download.")

if __name__ == "__main__":
    main() 