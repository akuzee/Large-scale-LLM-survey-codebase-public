###############################################################################
# IMPORTS
###############################################################################
import os                      # For interacting with the operating system
import json                    # For handling JSON data format
import csv                     # For handling CSV files
import pandas as pd            # For data manipulation
from flask import Flask, request, jsonify, send_file, render_template, Response  # Flask web framework
from google.cloud import firestore  # Google's NoSQL database
import logging                 # For creating logs
from datetime import datetime, timedelta   # For working with dates and times
import tempfile                # For creating temporary files
import uuid                    # For generating unique identifiers
import pytz                    # For timezone handling
import statistics              # For statistical calculations

###############################################################################
# CONFIGURATION AND SETUP
###############################################################################
# Configure logging to record events and errors
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)

# --- DATABASE SETUP ---
# Initialize Firestore client - connects to Google's cloud database
# We need a credentials JSON file to authenticate with Google Cloud
credentials_path = os.path.join(os.path.dirname(__file__), "llm-full-url-database-326c1cf4e35d.json")
# Set the environment variable that Google's library will look for to find credentials
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path
# Create the database client object - explicitly connect to the llm-full-urls database
db = firestore.Client(project="llm-full-url-database", database="llm-full-urls")

# Collection name for task data in Firestore (basically a table in the database)
TASKS_COLLECTION = "task_instances"

# Cache for unavailable occupations data
unavailable_occupations_cache = {
    "data": [],                  # The list of occupation IDs with timestamps
    "last_updated": None,        # When the cache was last updated
    "cache_duration": 15         # Cache duration in minutes (default: 15)
}

###############################################################################
# API ROUTES - TASK MANAGEMENT
###############################################################################

@app.route('/get_task_urls', methods=['GET'])
def get_task_urls():
    """
    Endpoint to get task and response URLs for a given task ID
    
    Takes:
    - task_id: The ID of the task to retrieve
    
    Returns:
    - JSON with task_url and response_urls
    """
    try:  
        # Get the task_id from the URL query parameters (e.g., ?task_id=123)
        task_id = request.args.get('task_id')
        
        # Validate that task_id was provided
        if not task_id:
            # Return an error with HTTP 400 status code (Bad Request)
            return jsonify({"error": "Missing task_id parameter"}), 400
        
        # --- DATABASE QUERY ---
        # Query Firestore for the first available task instance for this task_id
        # This is like saying "SELECT * FROM task_instances 
        #                      WHERE task_id = X AND available = true 
        #                      LIMIT 1"
        query = db.collection(TASKS_COLLECTION).where("task_id", "==", task_id).where("available", "==", True).limit(1)
        task_instances = list(query.stream())  # Execute the query and convert results to a list
        
        # Check if we found any available task instances
        if not task_instances:
            # Log a warning 
            logger.warning(f"No available task instances found for task_id: {task_id}")
            # Return a 404 error (Not Found)
            return jsonify({"error": f"No available task instances for task ID: {task_id}"}), 404
        
        # Get the first available task instance
        task_doc = task_instances[0]
        task_data = task_doc.to_dict()  # Convert Firestore document to Python dictionary
        
        # --- PREPARE RESPONSE ---
        # Create a dictionary with the data we want to return to the client
        response_data = {
            "task_url": task_data.get("task_url"),  # .get() safely retrieves values (returns None if missing)
            "response_urls": [
                task_data.get("response_url_1"),
                task_data.get("response_url_2"),
                task_data.get("response_url_3"),
                task_data.get("response_url_4"),
                task_data.get("response_url_5")
            ],
            "task_instance_id": task_doc.id  # Include the document ID for reference
        }
        
        # --- MARK TASK AS UNAVAILABLE ---
        # Get a reference to the task document in the database
        task_doc_ref = db.collection(TASKS_COLLECTION).document(task_doc.id)
        transaction = db.transaction()  # Start a transaction for atomic operations
        
        # Transactions ensure database consistency - they're all-or-nothing operations
        # This is important when multiple users might request tasks simultaneously!
        @firestore.transactional  # This decorator marks this function as part of a transaction
        def update_in_transaction(transaction, doc_ref):
            # Update the document within the transaction
            transaction.update(doc_ref, {
                "available": False,  # Mark as unavailable
                "assigned_at": datetime.now(),  # Record assignment time for testing 
            })
        
        # Execute the transaction function we just defined
        update_in_transaction(transaction, task_doc_ref)
        
        # --- CHECK IF THIS WAS THE LAST TASK ---
        # Similar query as before to see if any available tasks remain
        remaining_query = db.collection(TASKS_COLLECTION).where("task_id", "==", task_id).where("available", "==", True).limit(1)
        remaining = list(remaining_query.stream())
        
        if not remaining:
            # Log that all instances for this task are now taken
            logger.info(f"Task {task_id} has no more available instances!")
            # (CONSIDER ADDING CODE HERE TO SEND NOTIFICATIONS)
        
        # Return the response data as JSON
        return jsonify(response_data)
    
    except Exception as e:
        # Catch any unexpected errors
        # Log the error with details (exc_info=True includes the stack trace)
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        # Return a generic error to the client with 500 status (Server Error)
        return jsonify({"error": "Server error processing request"}), 500

###############################################################################
# API ROUTES - AVAILABILITY MANAGEMENT
###############################################################################

@app.route('/update_task_availability', methods=['POST'])
def update_task_availability():
    """
    Endpoint to update task availability between rounds
    
    Expected JSON payload:
    {
        "task_instances": [
            {"task_instance_id": "id1", "available": true},
            {"task_instance_id": "id2", "available": false}
        ]
    }
    """
    try:
        # Get the JSON data from the request body
        data = request.json
        
        # Validate the incoming data
        if not data or 'task_instances' not in data:
            return jsonify({"error": "Invalid request format"}), 400
        
        # --- BATCH DATABASE UPDATE ---
        # Batch operations let us update multiple documents in one atomic operation
        # This is much more efficient than individual updates
        batch = db.batch()
        updated_count = 0  # Keep track of how many we're updating
        
        # Process each task instance in the list
        for item in data['task_instances']:
            if 'task_instance_id' in item and 'available' in item:
                # Get a reference to this document
                doc_ref = db.collection(TASKS_COLLECTION).document(item['task_instance_id'])
                # Add an update operation to our batch
                batch.update(doc_ref, {"available": item['available']})
                updated_count += 1
        
        # Execute all the updates in one go
        batch.commit()
        
        # Return success message with count of updated items
        return jsonify({"status": "success", "updated_count": updated_count})
    
    except Exception as e:
        # Handle errors
        logger.error(f"Error updating task availability: {str(e)}", exc_info=True)
        return jsonify({"error": "Server error updating task availability"}), 500

###############################################################################
# API ROUTES - OCCUPATION STATUS
###############################################################################

@app.route('/check_occupation_status', methods=['GET'])
def check_occupation_status():
    """
    Endpoint to check if an occupation has available tasks
    
    Expected query parameter:
    - occupation_id: The ID of the occupation to check
    """
    try:
        # Get occupation_id from URL query parameters
        occupation_id = request.args.get('occupation_id')
        
        # Validate the parameter
        if not occupation_id:
            return jsonify({"error": "Missing occupation_id parameter"}), 400
        
        # Query Firestore for available tasks for this occupation
        # We only need to check if at least one exists, so limit(1) is efficient
        query = db.collection(TASKS_COLLECTION).where("occupation_id", "==", occupation_id).where("available", "==", True).limit(1)
        available_tasks = list(query.stream())
        
        # If the list is empty, no available tasks were found
        if not available_tasks:
            return jsonify({"has_available_tasks": False})
        
        # Otherwise, at least one task is available
        return jsonify({"has_available_tasks": True})
    
    except Exception as e:
        # Handle errors
        logger.error(f"Error checking occupation status: {str(e)}", exc_info=True)
        return jsonify({"error": "Server error checking occupation status"}), 500

@app.route('/list_unavailable_occupations', methods=['GET'])
def list_unavailable_occupations():
    """
    Endpoint to get a list of all occupations that have no available tasks
    
    Query parameters:
    - force_refresh: If 'true', forces a cache refresh regardless of time
    - cache_duration: Number of minutes to cache results (default: 15)
    - sort: How to sort results - 'chronological' (default) or 'alphabetical'
    
    Returns:
    - JSON with list of occupation IDs that have no available tasks, with timestamps
    """
    try:
        # Check if we should force refresh the cache
        force_refresh = request.args.get('force_refresh', 'false').lower() == 'true'
        
        # Get cache duration from query parameter or use default
        cache_duration = int(request.args.get('cache_duration', unavailable_occupations_cache['cache_duration']))
        unavailable_occupations_cache['cache_duration'] = cache_duration
        
        # Get sort order - chronological (newest first) or alphabetical
        sort_order = request.args.get('sort', 'chronological').lower()
        
        current_time = datetime.now()
        cache_expired = (unavailable_occupations_cache['last_updated'] is None or 
                        current_time - unavailable_occupations_cache['last_updated'] > 
                        timedelta(minutes=cache_duration))
        
        # If cache is valid and we're not forcing a refresh, return cached data
        if not cache_expired and not force_refresh and unavailable_occupations_cache['data']:
            # Get cached data
            unavailable_data = unavailable_occupations_cache['data']
            
            # Sort the data as requested
            if sort_order == 'chronological':
                # Sort by timestamp, newest first (already stored this way)
                sorted_data = unavailable_data
            else:
                # Sort alphabetically by occupation ID
                sorted_data = sorted(unavailable_data, key=lambda x: x['occupation_id'])
            
            return jsonify({
                "unavailable_occupations": sorted_data,
                "cached": True,
                "last_updated": unavailable_occupations_cache['last_updated'].isoformat(),
                "cache_expires": (unavailable_occupations_cache['last_updated'] + 
                                 timedelta(minutes=cache_duration)).isoformat()
            })
        
        # Otherwise, query Firestore for fresh data
        logger.info("Refreshing unavailable occupations cache")
        
        # Step 1: Get all unique occupation IDs from the database
        all_occupations_query = db.collection(TASKS_COLLECTION)
        all_docs = all_occupations_query.stream()
        
        # Extract all unique occupation IDs
        all_occupation_ids = set()
        for doc in all_docs:
            doc_data = doc.to_dict()
            if 'occupation_id' in doc_data:
                all_occupation_ids.add(doc_data['occupation_id'])
        
        # Step 2: For each occupation ID, check if it has any available tasks
        unavailable_occupations = []
        
        for occupation_id in all_occupation_ids:
            # Query for all tasks for this occupation
            occupation_query = db.collection(TASKS_COLLECTION).where(
                "occupation_id", "==", occupation_id
            )
            
            occupation_tasks = list(occupation_query.stream())
            
            # Check if ANY tasks are available
            any_available = False
            latest_assigned_time = None
            
            for task in occupation_tasks:
                task_data = task.to_dict()
                
                if task_data.get('available', False):
                    any_available = True
                    break
                
                # Track the most recent assignment time
                task_assigned_time = task_data.get('assigned_at')
                if task_assigned_time:
                    if isinstance(task_assigned_time, str):
                        try:
                            task_assigned_time = datetime.fromisoformat(task_assigned_time)
                        except ValueError:
                            continue
                    
                    if latest_assigned_time is None or task_assigned_time > latest_assigned_time:
                        latest_assigned_time = task_assigned_time
            
            # If no tasks are available, add to our list with timestamp
            if not any_available:
                # If we couldn't find an assigned timestamp, use current time
                if latest_assigned_time is None:
                    latest_assigned_time = current_time
                
                # Format for JSON serialization
                if isinstance(latest_assigned_time, datetime):
                    latest_assigned_time_str = latest_assigned_time.isoformat()
                else:
                    latest_assigned_time_str = str(latest_assigned_time)
                
                unavailable_occupations.append({
                    "occupation_id": occupation_id,
                    "depleted_at": latest_assigned_time_str
                })
        
        # Sort by timestamp, newest first
        unavailable_occupations.sort(key=lambda x: x['depleted_at'], reverse=True)
        
        # Update cache
        unavailable_occupations_cache['data'] = unavailable_occupations
        unavailable_occupations_cache['last_updated'] = current_time
        
        # Sort the data as requested for response
        if sort_order == 'alphabetical':
            sorted_data = sorted(unavailable_occupations, key=lambda x: x['occupation_id'])
        else:
            # Already sorted chronologically
            sorted_data = unavailable_occupations
        
        # Return the result
        return jsonify({
            "unavailable_occupations": sorted_data,
            "cached": False,
            "last_updated": current_time.isoformat(),
            "cache_expires": (current_time + timedelta(minutes=cache_duration)).isoformat()
        })
    
    except Exception as e:
        logger.error(f"Error listing unavailable occupations: {str(e)}", exc_info=True)
        return jsonify({"error": f"Server error listing unavailable occupations"}), 500

###############################################################################
# API ROUTES - DATA IMPORT/EXPORT
###############################################################################

@app.route('/import_data', methods=['POST'])
def import_data():
    """
    Endpoint to import task data from a CSV or JSON file
    
    Expected form data:
    - file: The CSV or JSON file to import
    - format: 'csv' or 'json'
    - clear_existing: 'true' or 'false' (default: 'false')
    
    Returns:
    - JSON with import status and count of imported items
    """
    try:
        # --- VALIDATE INPUT FILE ---
        # Check if a file was provided in the request
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        # Get the file from the request
        file = request.files['file']
        # Check if the filename is empty (happens when no file is selected)
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400
        
        # --- CHECK FILE FORMAT ---
        # Get the format type from the form data (csv or json)
        format_type = request.form.get('format', '').lower()
        # Validate that the format is one we can handle
        if format_type not in ['csv', 'json']:
            return jsonify({"error": "Format must be 'csv' or 'json'"}), 400
        
        # --- CHECK IF WE SHOULD CLEAR EXISTING DATA ---
        # Convert the string 'true'/'false' to a boolean
        clear_existing = request.form.get('clear_existing', 'false').lower() == 'true'
        
        # --- CLEAR EXISTING DATA IF REQUESTED ---
        if clear_existing:
            # Firestore limits batch operations to 500, so we need to delete in batches
            batch_size = 500  # Maximum batch size for Firestore
            
            # Get the first batch of documents
            docs = list(db.collection(TASKS_COLLECTION).limit(batch_size).stream())
            # Continue deleting in batches until no documents are left
            while docs:
                # Create a new batch for this group of documents
                batch = db.batch()
                # Add each document to the batch deletion
                for doc in docs:
                    batch.delete(doc.reference)
                # Execute the batch deletion
                batch.commit()
                # Get the next batch of documents (if any)
                docs = list(db.collection(TASKS_COLLECTION).limit(batch_size).stream())
            
            # Log that we've cleared the data
            logger.info("Cleared existing data")
        
        # --- PROCESS AND IMPORT THE FILE ---
        # Keep track of how many items we import
        imported_count = 0
        
        # --- HANDLE CSV FILES ---
        if format_type == 'csv':
            # Use pandas to read the CSV file into a DataFrame
            # A DataFrame is like a spreadsheet in Python - rows and columns of data
            df = pd.read_csv(file)
            
            # Process in batches to avoid Firestore limits
            # Firestore can only handle 500 operations per batch
            batch_size = 400  # Using 400 to be safe
            
            # Process each batch of rows
            for i in range(0, len(df), batch_size):
                # Create a new batch for this group
                batch = db.batch()
                # Get this slice of the DataFrame
                batch_df = df.iloc[i:i+batch_size]
                
                # Process each row in this batch
                for _, row in batch_df.iterrows():
                    # Convert the row to a Python dictionary
                    item = row.to_dict()
                    # Handle NaN values (Not a Number) by replacing them with None
                    # NaN values often appear in pandas when data is missing
                    item = {k: (v if pd.notna(v) else None) for k, v in item.items()}
                    
                    # Generate a unique ID if not provided
                    # Using either the provided task_instance_id or a new UUID
                    doc_id = str(item.get('task_instance_id', uuid.uuid4()))
                    
                    # Set a default value for availability
                    if 'available' not in item:
                        item['available'] = True
                    
                    # Create a reference to where this document will be stored
                    doc_ref = db.collection(TASKS_COLLECTION).document(doc_id)
                    # Add this document to our batch write operation
                    batch.set(doc_ref, item)
                    # Increment our counter
                    imported_count += 1
                
                # Execute this batch of writes
                batch.commit()
        
        # --- HANDLE JSON FILES ---
        elif format_type == 'json':
            # Parse the JSON file into Python objects
            data = json.load(file)
            
            # Handle different JSON formats:
            # - If it's a list of items, use as is
            # - If it's a single object, put it in a list
            items = data if isinstance(data, list) else [data]
            
            # Process in batches like we did with CSV
            batch_size = 400
            
            # Process each batch of items
            for i in range(0, len(items), batch_size):
                # Create a new batch
                batch = db.batch()
                # Get this slice of items
                batch_items = items[i:i+batch_size]
                
                # Process each item in this batch
                for item in batch_items:
                    # Generate a unique ID if not provided
                    doc_id = str(item.get('task_instance_id', uuid.uuid4()))
                    
                    # Set a default value for availability
                    if 'available' not in item:
                        item['available'] = True
                    
                    # Create a reference and add to batch
                    doc_ref = db.collection(TASKS_COLLECTION).document(doc_id)
                    batch.set(doc_ref, item)
                    imported_count += 1
                
                # Execute this batch
                batch.commit()
        
        # --- RETURN SUCCESS RESPONSE ---
        return jsonify({
            "status": "success",
            "imported_count": imported_count,
            "cleared_existing": clear_existing
        })
    
    except Exception as e:
        # Log the error and return a helpful message
        logger.error(f"Error importing data: {str(e)}", exc_info=True)
        return jsonify({"error": f"Error importing data: {str(e)}"}), 500

@app.route('/export_data', methods=['GET'])
def export_data():
    """
    Endpoint to export current database state to CSV or JSON
    
    Query parameters:
    - format: 'csv' or 'json' (default: 'csv')
    - filename: custom filename (optional)
    - include_metadata: 'true' or 'false' (default: 'true') - includes document IDs and metadata
    - filter_field: field name to filter on (optional)
    - filter_value: value to match in filter_field (required if filter_field is provided)
    
    Returns:
    - CSV or JSON file download
    """
    try:
        # --- GET EXPORT FORMAT ---
        # Check if we should export as CSV or JSON
        format_type = request.args.get('format', 'csv').lower()
        # Validate format
        if format_type not in ['csv', 'json']:
            return jsonify({"error": "Format must be 'csv' or 'json'"}), 400
        
        # --- CHECK METADATA INCLUSION ---
        # Determine if we should include Firestore metadata in the export
        # Metadata includes document IDs and timestamps
        include_metadata = request.args.get('include_metadata', 'true').lower() == 'true'
        
        # --- SET UP FILTERING ---
        # Get any filter parameters - these let you export just a subset of data
        # For example, only tasks for a specific occupation
        filter_field = request.args.get('filter_field')
        filter_value = request.args.get('filter_value')
        
        # Validate that if a filter field is provided, a value is also provided
        if filter_field and filter_value is None:
            return jsonify({"error": "filter_value is required when filter_field is provided"}), 400
        
        # --- QUERY THE DATABASE ---
        # Start with a basic query for all documents
        query = db.collection(TASKS_COLLECTION)
        # If filtering is requested, add the filter condition
        if filter_field and filter_value is not None:
            query = query.where(filter_field, '==', filter_value)
        
        # Execute the query
        docs = query.stream()
        
        # --- PROCESS QUERY RESULTS ---
        # Convert Firestore documents to a list of dictionaries
        data = []
        for doc in docs:
            # Get the document data
            item = doc.to_dict()
            # Add metadata if requested
            if include_metadata:
                item['doc_id'] = doc.id                  # The document's unique ID
                item['created_at'] = doc.create_time     # When it was created
                item['updated_at'] = doc.update_time     # When it was last updated
            data.append(item)
        
        # --- CREATE TEMPORARY FILE ---
        # We'll create a temporary file to store the export
        # This file will be automatically deleted after sending
        with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{format_type}') as temp_file:
            temp_filename = temp_file.name
            
            # --- WRITE DATA TO FILE ---
            if format_type == 'csv':
                # For CSV, convert to a pandas DataFrame and save
                df = pd.DataFrame(data)
                df.to_csv(temp_filename, index=False)
            else:
                # For JSON, write directly with the json module
                with open(temp_filename, 'w') as f:
                    # default=str helps with converting date objects to strings
                    json.dump(data, f, default=str)
        
        # --- PREPARE DOWNLOAD FILENAME ---
        # Use custom filename if provided, otherwise generate one with timestamp
        custom_filename = request.args.get('filename')
        if not custom_filename:
            # Current time formatted as YYYYMMDD_HHMMSS
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            custom_filename = f'task_data_export_{timestamp}.{format_type}'
        
        # --- SEND FILE TO CLIENT ---
        # This will prompt the browser to download the file
        return send_file(
            temp_filename,                                              # Path to the file
            as_attachment=True,                                         # Force download (not display)
            download_name=custom_filename,                              # What to name the download
            mimetype='text/csv' if format_type == 'csv' else 'application/json'  # File type
        )
    
    except Exception as e:
        # Handle any errors
        logger.error(f"Error exporting data: {str(e)}", exc_info=True)
        return jsonify({"error": f"Error exporting data: {str(e)}"}), 500

###############################################################################
# API ROUTES - DASHBOARD & MONITORING
###############################################################################

@app.route('/dashboard', methods=['GET'])
def dashboard():
    """
    Endpoint to display a dashboard with statistics and visualizations
    
    Query parameters:
    - format: 'html' (default) or 'json' - HTML for browser viewing, JSON for API access
    - refresh: If 'true', bypasses caching for fresh data
    
    Returns:
    - HTML page or JSON with system statistics
    """
    try:
        # Check requested format
        format_type = request.args.get('format', 'html').lower()
        refresh = request.args.get('refresh', 'false').lower() == 'true'
        
        # --- COLLECT STATISTICS ---
        stats = {}
        
        # System info
        stats['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        stats['timezone'] = datetime.now(pytz.timezone('America/New_York')).tzname()
        
        # --- DATABASE STATS ---
        # Get all task instances
        query = db.collection(TASKS_COLLECTION)
        all_tasks = list(query.stream())
        
        # Basic counts
        stats['total_tasks'] = len(all_tasks)
        
        # Task availability stats
        available_tasks = 0
        unavailable_tasks = 0
        
        # Occupation tracking
        occupation_stats = {}
        task_id_stats = {}
        
        # Recent activity tracking
        recent_assignments = []
        
        # Calculate time thresholds
        now = datetime.now()
        last_24h = now - timedelta(hours=24)
        last_hour = now - timedelta(hours=1)
        assignments_24h = 0
        assignments_1h = 0
        
        # Process each task
        for task in all_tasks:
            task_data = task.to_dict()
            
            # Count available vs unavailable
            if task_data.get('available', True):
                available_tasks += 1
            else:
                unavailable_tasks += 1
            
            # Get task_id and occupation_id
            task_id = task_data.get('task_id', 'unknown')
            occupation_id = task_data.get('occupation_id', 'unknown')
            
            # Initialize counters if needed
            if occupation_id not in occupation_stats:
                occupation_stats[occupation_id] = {
                    'total': 0, 
                    'available': 0, 
                    'unavailable': 0
                }
            
            if task_id not in task_id_stats:
                task_id_stats[task_id] = {
                    'total': 0, 
                    'available': 0, 
                    'unavailable': 0
                }
            
            # Update counters
            occupation_stats[occupation_id]['total'] += 1
            task_id_stats[task_id]['total'] += 1
            
            if task_data.get('available', True):
                occupation_stats[occupation_id]['available'] += 1
                task_id_stats[task_id]['available'] += 1
            else:
                occupation_stats[occupation_id]['unavailable'] += 1
                task_id_stats[task_id]['unavailable'] += 1
            
            # Track recent assignments
            assigned_at = task_data.get('assigned_at')
            if assigned_at and not task_data.get('available', True):
                # Convert string timestamps to datetime if needed
                if isinstance(assigned_at, str):
                    try:
                        assigned_at = datetime.fromisoformat(assigned_at.replace('Z', '+00:00'))
                    except (ValueError, AttributeError):
                        # Skip this one if we can't parse the timestamp
                        continue
                
                # Count recent assignments
                if assigned_at > last_24h:
                    assignments_24h += 1
                    
                    if assigned_at > last_hour:
                        assignments_1h += 1
                
                # Add to recent assignments list (only most recent 10)
                recent_assignments.append({
                    'task_id': task_id,
                    'occupation_id': occupation_id,
                    'assigned_at': assigned_at.isoformat(),
                    'doc_id': task.id
                })
        
        # Sort recent assignments by time (newest first) and limit to 10
        recent_assignments.sort(key=lambda x: x['assigned_at'], reverse=True)
        recent_assignments = recent_assignments[:10]
        
        # Add stats to the result
        stats['available_tasks'] = available_tasks
        stats['unavailable_tasks'] = unavailable_tasks
        stats['availability_percentage'] = round((available_tasks / stats['total_tasks']) * 100, 2) if stats['total_tasks'] > 0 else 0
        
        # Assignment activity
        stats['assignments_last_24h'] = assignments_24h
        stats['assignments_last_hour'] = assignments_1h
        stats['recent_assignments'] = recent_assignments
        
        # Occupation statistics
        stats['total_occupations'] = len(occupation_stats)
        
        # Calculate occupations with no available tasks
        occupations_unavailable = 0
        for occ_id, occ_data in occupation_stats.items():
            if occ_data['available'] == 0:
                occupations_unavailable += 1
        
        stats['occupations_unavailable'] = occupations_unavailable
        stats['occupations_available'] = stats['total_occupations'] - occupations_unavailable
        
        # Top 5 occupations with lowest availability percentage
        occ_availability = []
        for occ_id, occ_data in occupation_stats.items():
            if occ_data['total'] > 0:  # Avoid division by zero
                available_pct = (occ_data['available'] / occ_data['total']) * 100
                occ_availability.append({
                    'occupation_id': occ_id,
                    'available_percent': round(available_pct, 2),
                    'available': occ_data['available'],
                    'total': occ_data['total']
                })
        
        # Sort by availability percentage (ascending)
        occ_availability.sort(key=lambda x: x['available_percent'])
        stats['low_availability_occupations'] = occ_availability[:5]
        
        # System health metrics
        # Calculate assignment rate per hour over past 24 hours
        if assignments_24h > 0:
            stats['assignment_rate_per_hour'] = round(assignments_24h / 24, 2)
        else:
            stats['assignment_rate_per_hour'] = 0
        
        # Estimated time until all tasks are exhausted (at current rate)
        if stats['assignment_rate_per_hour'] > 0:
            hours_remaining = available_tasks / stats['assignment_rate_per_hour']
            stats['estimated_hours_remaining'] = round(hours_remaining, 2)
            stats['estimated_depletion_date'] = (now + timedelta(hours=hours_remaining)).strftime('%Y-%m-%d %H:%M')
        else:
            stats['estimated_hours_remaining'] = "N/A"
            stats['estimated_depletion_date'] = "N/A"
        
        # Return the data in requested format
        if format_type == 'json':
            return jsonify(stats)
        else:
            # For HTML format, return a basic dashboard page
            # This is a simple HTML template generated directly in the code
            # In a production app, you'd use a proper template file
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>URL Database Dashboard</title>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; padding: 20px; max-width: 1200px; margin: 0 auto; }}
                    h1, h2, h3 {{ color: #333; }}
                    .container {{ display: flex; flex-wrap: wrap; }}
                    .card {{ background: #f9f9f9; border-radius: 8px; padding: 20px; margin: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
                    .stat-card {{ flex: 1; min-width: 200px; }}
                    .full-width {{ flex-basis: 100%; }}
                    .stat-value {{ font-size: 32px; font-weight: bold; color: #0066cc; margin: 10px 0; }}
                    .stat-label {{ font-size: 14px; color: #666; }}
                    .alert {{ color: #cc3300; }}
                    .success {{ color: #00994c; }}
                    table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                    th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
                    th {{ background-color: #f2f2f2; }}
                    .progress-bar {{ background-color: #e0e0e0; border-radius: 4px; height: 20px; }}
                    .progress {{ background-color: #0066cc; height: 100%; border-radius: 4px; }}
                    .refresh-button {{ padding: 10px 20px; background: #0066cc; color: white; border: none; border-radius: 4px; cursor: pointer; }}
                    .last-updated {{ font-size: 12px; color: #666; margin-top: 5px; }}
                </style>
            </head>
            <body>
                <h1>URL Database Dashboard</h1>
                <p class="last-updated">Last updated: {stats['timestamp']} {stats['timezone']}</p>
                <button class="refresh-button" onclick="location.href='?refresh=true'">Refresh Data</button>
                
                <h2>Summary</h2>
                <div class="container">
                    <div class="card stat-card">
                        <div class="stat-label">Total Tasks</div>
                        <div class="stat-value">{stats['total_tasks']}</div>
                    </div>
                    <div class="card stat-card">
                        <div class="stat-label">Available Tasks</div>
                        <div class="stat-value">{stats['available_tasks']}</div>
                    </div>
                    <div class="card stat-card">
                        <div class="stat-label">Availability</div>
                        <div class="stat-value">{stats['availability_percentage']}%</div>
                        <div class="progress-bar">
                            <div class="progress" style="width: {stats['availability_percentage']}%;"></div>
                        </div>
                    </div>
                    <div class="card stat-card">
                        <div class="stat-label">Total Occupations</div>
                        <div class="stat-value">{stats['total_occupations']}</div>
                    </div>
                </div>
                
                <h2>Activity</h2>
                <div class="container">
                    <div class="card stat-card">
                        <div class="stat-label">Assignments (Last Hour)</div>
                        <div class="stat-value">{stats['assignments_last_hour']}</div>
                    </div>
                    <div class="card stat-card">
                        <div class="stat-label">Assignments (24 Hours)</div>
                        <div class="stat-value">{stats['assignments_last_24h']}</div>
                    </div>
                    <div class="card stat-card">
                        <div class="stat-label">Assignment Rate</div>
                        <div class="stat-value">{stats['assignment_rate_per_hour']}/hour</div>
                    </div>
                    <div class="card stat-card">
                        <div class="stat-label">Estimated Time Remaining</div>
                        <div class="stat-value">{stats['estimated_hours_remaining']}</div>
                        <div class="stat-label">hours (depleted by {stats['estimated_depletion_date']})</div>
                    </div>
                </div>
                
                <h2>Occupation Status</h2>
                <div class="container">
                    <div class="card stat-card">
                        <div class="stat-label">Available Occupations</div>
                        <div class="stat-value">{stats['occupations_available']}</div>
                    </div>
                    <div class="card stat-card">
                        <div class="stat-label">Depleted Occupations</div>
                        <div class="stat-value">{stats['occupations_unavailable']}</div>
                    </div>
                </div>
                
                <h2>Low Availability Occupations</h2>
                <div class="card full-width">
                    <table>
                        <thead>
                            <tr>
                                <th>Occupation ID</th>
                                <th>Available</th>
                                <th>Total</th>
                                <th>Availability %</th>
                            </tr>
                        </thead>
                        <tbody>
            """
            
            # Add rows for low availability occupations
            for occ in stats['low_availability_occupations']:
                html += f"""
                            <tr>
                                <td>{occ['occupation_id']}</td>
                                <td>{occ['available']}</td>
                                <td>{occ['total']}</td>
                                <td>{occ['available_percent']}%</td>
                            </tr>
                """
            
            html += """
                        </tbody>
                    </table>
                </div>
                
                <h2>Recent Assignments</h2>
                <div class="card full-width">
                    <table>
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>Task ID</th>
                                <th>Occupation ID</th>
                            </tr>
                        </thead>
                        <tbody>
            """
            
            # Add rows for recent assignments
            for assignment in stats['recent_assignments']:
                # Convert ISO timestamp to more readable format
                try:
                    time_str = datetime.fromisoformat(assignment['assigned_at'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S')
                except (ValueError, AttributeError):
                    time_str = assignment['assigned_at']
                
                html += f"""
                            <tr>
                                <td>{time_str}</td>
                                <td>{assignment['task_id']}</td>
                                <td>{assignment['occupation_id']}</td>
                            </tr>
                """
            
            html += """
                        </tbody>
                    </table>
                </div>
                
                <script>
                    // Auto-refresh the page every 5 minutes
                    setTimeout(function() {
                        location.reload();
                    }, 300000);
                </script>
            </body>
            </html>
            """
            
            return Response(html, mimetype='text/html')
    
    except Exception as e:
        logger.error(f"Error generating dashboard: {str(e)}", exc_info=True)
        if request.args.get('format', 'html').lower() == 'json':
            return jsonify({"error": f"Error generating dashboard: {str(e)}"}), 500
        else:
            return f"<h1>Error</h1><p>An error occurred while generating the dashboard: {str(e)}</p>", 500

###############################################################################
# MAIN ENTRY POINT
###############################################################################
if __name__ == '__main__':
    # Get the port number from environment variable, or use 5000 as default
    port = int(os.environ.get("PORT", 5000))
    # Start the Flask web server
    # host='0.0.0.0' makes it available on all network interfaces
    # debug=True enables auto-reload when code changes and shows detailed error messages
    # WARNING: debug=True should not be used in production!
    app.run(host='0.0.0.0', port=port, debug=True)