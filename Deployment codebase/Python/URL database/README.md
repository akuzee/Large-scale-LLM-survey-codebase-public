# URL Database API

A Flask application that serves as an intermediary between Qualtrics surveys and a Firestore database, managing task URLs and their availability for research participants.

## Setup

1. Ensure you have Python 3.7+ installed
2. Place your Firestore credentials JSON file in the same directory as `URL_database.py` and name it `firestore_credentials.json`
3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

## Running the Application

```
python URL_database.py
```

The server will start at http://0.0.0.0:5000 by default.

## API Endpoints

### 1. Get Task URLs

**GET /get_task_urls**

Retrieves a task instance and associated response URLs, marking the task instance as unavailable.

Query parameters:
- `task_id`: The ID of the task to retrieve

Example response:
```json
{
  "task_url": "https://example.com/task.pdf",
  "response_urls": [
    "https://example.com/response1.pdf",
    "https://example.com/response2.pdf",
    "https://example.com/response3.pdf",
    "https://example.com/response4.pdf",
    "https://example.com/response5.pdf"
  ],
  "task_instance_id": "abc123"
}
```

### 2. Update Task Availability

**POST /update_task_availability**

Updates the availability status of multiple task instances in a batch operation.

Request body:
```json
{
  "task_instances": [
    {"task_instance_id": "id1", "available": true},
    {"task_instance_id": "id2", "available": false}
  ]
}
```

### 3. Check Occupation Status

**GET /check_occupation_status**

Checks if an occupation has any available tasks.

Query parameters:
- `occupation_id`: The ID of the occupation to check

Example response:
```json
{
  "has_available_tasks": true
}
```

## Firestore Data Structure

The application expects the following structure in Firestore:

Collection: `task_instances`
Document fields:
- `task_id`: String - ID of the task
- `occupation_id`: String - ID of the occupation
- `available`: Boolean - Availability status
- `task_url`: String - URL to task PDF
- `response_url_1`: String - URL to first response PDF
- `response_url_2`: String - URL to second response PDF
- `response_url_3`: String - URL to third response PDF
- `response_url_4`: String - URL to fourth response PDF
- `response_url_5`: String - URL to fifth response PDF
- `assigned_at`: Timestamp - When the task was assigned (set automatically)

## Deployment

For production deployment, consider:
1. Running with a production WSGI server like Gunicorn
2. Setting up behind a reverse proxy (Nginx/Apache)
3. Deploying to a cloud platform (Google Cloud Run, Heroku, etc.)
4. Setting up proper monitoring and scaling 