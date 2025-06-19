# Qualtrics API: Survey Response Export Guide

This document outlines the key Qualtrics API endpoints used for exporting survey responses, as implemented in the accompanying Python script.

## Authentication

All API requests require an API Token to be included in the request headers:

-   **Header Name**: `X-API-TOKEN`
-   **Header Value**: Your Qualtrics API Token

## Core API Endpoints

The export process involves three main API calls:

### 1. Create Response Export

Initiates the process of exporting survey responses.

-   **HTTP Method**: `POST`
-   **Endpoint**: `https://{dataCenterId}.qualtrics.com/API/v3/responseexports`
    -   `{dataCenterId}`: Your organization's data center ID (e.g., `ca1`, `co1`, `eu1`, `iad1`).
-   **Request Body (JSON)**:
    ```json
    {
      "format": "csv", // Or "tsv", "xml", "spss", "json"
      "surveyId": "SV_yourSurveyID"
      // Optional: other parameters like "startDate", "endDate", "useLabels", etc.
    }
    ```
-   **Successful Response (200 OK)**:
    -   Returns a JSON object containing a `progressId`. This ID is crucial for tracking the export status and downloading the file.
    ```json
    {
      "result": {
        "progressId": "ES_...",
        "httpStatus": "200 - OK"
      },
      "meta": {
        "requestId": "...",
        "httpStatus": "200 - OK"
      }
    }
    ```

### 2. Get Response Export Progress

Checks the status of an ongoing export request.

-   **HTTP Method**: `GET`
-   **Endpoint**: `https://{dataCenterId}.qualtrics.com/API/v3/responseexports/{exportProgressId}`
    -   `{exportProgressId}`: The `progressId` obtained from the "Create Response Export" call.
-   **Successful Response (200 OK)**:
    -   Returns a JSON object detailing the export's `status` (`"inProgress"`, `"complete"`, `"failed"`) and `percentComplete`.
    -   Once `"status"` is `"complete"`, the response will also include a `fileId`. This `fileId` is the same as the `exportProgressId` and is used to download the file.
    ```json
    {
      "result": {
        "fileId": "ES_...", // Same as exportProgressId when complete
        "percentComplete": 100.0,
        "status": "complete", // or "inProgress", "failed"
        "httpStatus": "200 - OK"
      },
      "meta": {
        "requestId": "...",
        "httpStatus": "200 - OK"
      }
    }
    ```

### 3. Get Response Export File

Downloads the exported survey data file. This is available once the export progress is "complete".

-   **HTTP Method**: `GET`
-   **Endpoint**: `https://{dataCenterId}.qualtrics.com/API/v3/responseexports/{fileId}/file`
    -   `{fileId}`: The `fileId` (which is the `exportProgressId`) obtained from the "Get Response Export Progress" call when the status is "complete".
-   **Successful Response (200 OK)**:
    -   The response body will be the exported file itself, typically a ZIP archive (even for formats like CSV). The script handles unzipping this file.
    -   **Content-Type Header**: Will indicate the type of file, e.g., `application/zip`.

## Important Notes

-   **File Format**: The API returns data in a ZIP file, even if you request CSV or another format. The script is designed to extract the actual data file from this ZIP archive.
-   **Rate Limiting**: Be mindful of Qualtrics API rate limits. Avoid making excessive requests in a short period. The script includes a 30-second delay between progress checks.
-   **Error Handling**: The provided script includes basic error handling for API responses and file operations. Review API error messages for detailed diagnostics if issues arise.
-   **Further Details**: For more advanced options (e.g., filtering responses, including specific questions), refer to the official Qualtrics API documentation: [Survey Response Export Guide](https://api.qualtrics.com/u9e5lh4172v0v-survey-response-export-guide)

This documentation should help you understand how the script interacts with the Qualtrics API. 