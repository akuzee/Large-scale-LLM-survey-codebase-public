from flask import Flask, request, jsonify
import sqlite3
import random
import os
from typing import List, Dict, Tuple, Optional
import logging

# This is a Flask web application that serves as a backend for managing a task database
# It handles task assignments, tracks completion status, and manages model responses
# This appears to be designed for a study or survey where participants complete tasks
# and evaluate model-generated responses
app = Flask(__name__)

# Configure logging to track application events and errors
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database configuration - uses SQLite which stores all data in a single file
DATABASE_PATH = "task_database.db"

def init_db():
    """
    Initialize the database with the required tables if they don't exist.
    
    Database Schema:
    - tasks: Stores basic task information linked to occupations
    - task_instances: Stores specific instances of tasks that can be assigned
    - model_responses: Stores model-generated responses for each task instance
    """
    with sqlite3.connect(DATABASE_PATH) as conn:
        cursor = conn.cursor()
        
        # Create tasks table - main task definitions
        # - id: Primary key
        # - task_id: External identifier for the task
        # - occupation: The occupation this task is relevant for
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY,
            task_id INTEGER NOT NULL,
            occupation TEXT NOT NULL,
            UNIQUE(task_id, occupation)
        )
        ''')
        
        # Create task instances table - specific instances of tasks
        # - id: Primary key
        # - task_id: References the tasks table
        # - instance_number: Identifier for this specific instance
        # - pdf_url: Location of the task PDF
        # - is_assigned: Whether this instance has been assigned to someone
        # - is_completed: Whether this instance has been completed
        # - assigned_round: Which round of the study this was assigned in
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS task_instances (
            id INTEGER PRIMARY KEY,
            task_id INTEGER NOT NULL,
            instance_number INTEGER NOT NULL,
            pdf_url TEXT NOT NULL,
            is_assigned BOOLEAN DEFAULT FALSE,
            is_completed BOOLEAN DEFAULT FALSE,
            assigned_round INTEGER DEFAULT 0,
            FOREIGN KEY (task_id) REFERENCES tasks(id),
            UNIQUE(task_id, instance_number)
        )
        ''')
        
        # Create model responses table - stores responses from different models for each task instance
        # - id: Primary key
        # - task_instance_id: References the task_instances table
        # - model_number: Identifier for the model that generated this response
        # - pdf_url: Location of the model's response PDF
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS model_responses (
            id INTEGER PRIMARY KEY,
            task_instance_id INTEGER NOT NULL,
            model_number INTEGER NOT NULL,
            pdf_url TEXT NOT NULL,
            FOREIGN KEY (task_instance_id) REFERENCES task_instances(id),
            UNIQUE(task_instance_id, model_number)
        )
        ''')
        
        conn.commit()

# Initialize the database when the application starts
init_db()

def get_db_connection():
    """
    Create a database connection and return it.
    
    The row_factory setting allows accessing columns by name instead of index.
    """
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/get_task', methods=['GET'])
def get_task():
    """
    Endpoint to get a task instance with model responses.
    
    This endpoint is likely called by the Qualtrics survey when a participant
    needs to be assigned a new task. It returns URLs for both the task instance
    and model responses that the participant will evaluate.
    
    Query parameters:
    - task_id: ID of the task
    - occupation: Occupation of the participant
    - round_id: Current round ID (default: 1)
    
    Returns:
    - JSON with task instance URL and 5 model response URLs
    """
    task_id = request.args.get('task_id')
    occupation = request.args.get('occupation')
    round_id = int(request.args.get('round_id', 1))
    
    if not task_id or not occupation:
        return jsonify({"error": "Missing task_id or occupation parameter"}), 400
    
    try:
        # Get next available task instance and model responses
        result = get_next_task_instance(task_id, occupation, round_id)
        
        if not result:
            return jsonify({"error": "No available task instances found"}), 404
        
        task_instance_url, model_urls = result
        
        # Format response with the task and 5 model responses
        response = {
            "task_instance_url": task_instance_url,
            "model1_url": model_urls[0],
            "model2_url": model_urls[1],
            "model3_url": model_urls[2],
            "model4_url": model_urls[3],
            "model5_url": model_urls[4]
        }
        
        return jsonify(response)
    
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}")
        return jsonify({"error": "Server error"}), 500

def get_next_task_instance(task_id: str, occupation: str, round_id: int) -> Optional[Tuple[str, List[str]]]:
    """
    Get the next available task instance for the given task and occupation.
    
    This function implements the task assignment logic:
    1. Try to find an unassigned task instance
    2. If no unassigned instances, look for incomplete instances from previous rounds
    3. Once found, mark it as assigned and return its URL with model response URLs
    
    Args:
        task_id: The task ID
        occupation: The occupation
        round_id: The current round
        
    Returns:
        Tuple of (task_instance_url, [model_urls]) or None if no instance available
    """
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Get task ID from the database using the external task_id and occupation
        cursor.execute("SELECT id FROM tasks WHERE task_id = ? AND occupation = ?", 
                      (task_id, occupation))
        task_row = cursor.fetchone()
        
        if not task_row:
            logger.warning(f"Task not found: {task_id} for occupation {occupation}")
            return None
        
        task_db_id = task_row['id']
        
        # Get next unassigned task instance or next incomplete instance from previous rounds
        # This prioritizes:
        # 1. Completely unassigned instances
        # 2. Incomplete instances from earlier rounds
        cursor.execute("""
            SELECT id, pdf_url FROM task_instances 
            WHERE task_id = ? AND 
                  (
                    (is_assigned = FALSE) OR 
                    (is_completed = FALSE AND assigned_round < ?)
                  )
            ORDER BY instance_number ASC
            LIMIT 1
        """, (task_db_id, round_id))
        
        instance = cursor.fetchone()
        if not instance:
            logger.warning(f"No available task instances for task {task_id}")
            return None
        
        instance_id = instance['id']
        instance_url = instance['pdf_url']
        
        # Mark this instance as assigned for the current round
        cursor.execute("""
            UPDATE task_instances 
            SET is_assigned = TRUE, assigned_round = ? 
            WHERE id = ?
        """, (round_id, instance_id))
        
        # Get all model responses for this task instance
        cursor.execute("""
            SELECT pdf_url FROM model_responses 
            WHERE task_instance_id = ?
        """, (instance_id,))
        
        all_models = [row['pdf_url'] for row in cursor.fetchall()]
        
        # If we have more than 5 models, randomly select 5 to keep the survey manageable
        # This adds variety to the responses that participants will evaluate
        if len(all_models) > 5:
            selected_models = random.sample(all_models, 5)
        else:
            selected_models = all_models
            # Pad with None if we have fewer than 5 models
            selected_models.extend([None] * (5 - len(selected_models)))
        
        conn.commit()
        return instance_url, selected_models

@app.route('/update_completion', methods=['POST'])
def update_completion():
    """
    Endpoint to update task completion status.
    
    This would be called after each round when manually reviewing the data,
    to mark which tasks have been successfully completed by participants.
    Tasks marked as completed won't be reassigned in future rounds.
    
    Expected JSON body:
    {
        "completed_instances": [instance_id1, instance_id2, ...],
        "round_id": 1
    }
    """
    data = request.json
    
    if not data or 'completed_instances' not in data or 'round_id' not in data:
        return jsonify({"error": "Missing required parameters"}), 400
    
    completed_instances = data['completed_instances']
    round_id = data['round_id']
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Mark specified instances as completed
            for instance_id in completed_instances:
                cursor.execute("""
                    UPDATE task_instances 
                    SET is_completed = TRUE 
                    WHERE id = ? AND assigned_round = ?
                """, (instance_id, round_id))
            
            conn.commit()
            
        return jsonify({"status": "success", "updated_count": len(completed_instances)})
    
    except Exception as e:
        logger.error(f"Error updating completion status: {str(e)}")
        return jsonify({"error": "Server error"}), 500

@app.route('/load_data', methods=['POST'])
def load_data():
    """
    Endpoint to load task data into the database.
    
    This is an administrative endpoint used to initially populate the database
    with tasks, task instances, and model responses. It would typically be called
    once at the beginning of the study to set up all the data.
    
    Expected JSON body:
    {
        "tasks": [
            {
                "task_id": 1,
                "occupation": "engineer",
                "instances": [
                    {
                        "instance_number": 1,
                        "pdf_url": "https://example.com/tasks/task1_inst1.pdf",
                        "model_responses": [
                            {"model_number": 1, "pdf_url": "https://example.com/responses/task1_inst1_model1.pdf"},
                            {"model_number": 2, "pdf_url": "https://example.com/responses/task1_inst1_model2.pdf"},
                            ...
                        ]
                    },
                    ...
                ]
            },
            ...
        ]
    }
    """
    data = request.json
    
    if not data or 'tasks' not in data:
        return jsonify({"error": "Missing tasks data"}), 400
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            task_count = 0
            instance_count = 0
            model_count = 0
            
            for task in data['tasks']:
                # Add task if it doesn't already exist (uses INSERT OR IGNORE)
                cursor.execute(
                    "INSERT OR IGNORE INTO tasks (task_id, occupation) VALUES (?, ?)",
                    (task['task_id'], task['occupation'])
                )
                
                # Get task ID (either just inserted or existing)
                cursor.execute(
                    "SELECT id FROM tasks WHERE task_id = ? AND occupation = ?",
                    (task['task_id'], task['occupation'])
                )
                task_db_id = cursor.fetchone()['id']
                task_count += 1
                
                # Add instances for this task
                for instance in task['instances']:
                    cursor.execute(
                        """INSERT OR IGNORE INTO task_instances 
                           (task_id, instance_number, pdf_url) 
                           VALUES (?, ?, ?)""",
                        (task_db_id, instance['instance_number'], instance['pdf_url'])
                    )
                    
                    # Get instance ID (either just inserted or existing)
                    cursor.execute(
                        """SELECT id FROM task_instances 
                           WHERE task_id = ? AND instance_number = ?""",
                        (task_db_id, instance['instance_number'])
                    )
                    instance_db_id = cursor.fetchone()['id']
                    instance_count += 1
                    
                    # Add model responses for this instance
                    for model in instance['model_responses']:
                        cursor.execute(
                            """INSERT OR IGNORE INTO model_responses 
                               (task_instance_id, model_number, pdf_url) 
                               VALUES (?, ?, ?)""",
                            (instance_db_id, model['model_number'], model['pdf_url'])
                        )
                        model_count += 1
            
            conn.commit()
            
        return jsonify({
            "status": "success", 
            "loaded": {
                "tasks": task_count,
                "instances": instance_count,
                "model_responses": model_count
            }
        })
    
    except Exception as e:
        logger.error(f"Error loading data: {str(e)}")
        return jsonify({"error": f"Server error: {str(e)}"}), 500

@app.route('/reset_assignments', methods=['POST'])
def reset_assignments():
    """
    Reset all task assignments for a new round of data collection.
    
    This endpoint would be called when starting a new round of the study.
    It allows for tasks to be reassigned, optionally preserving completion status
    from previous rounds.
    
    Expected JSON body:
    {
        "retain_completion": true  # Whether to keep completion status from previous rounds
    }
    """
    data = request.json
    retain_completion = data.get('retain_completion', True) if data else True
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            if retain_completion:
                # Only reset assignments for incomplete tasks
                # This ensures completed tasks aren't reassigned
                cursor.execute("""
                    UPDATE task_instances 
                    SET is_assigned = FALSE, assigned_round = 0
                    WHERE is_completed = FALSE
                """)
            else:
                # Reset all assignments and completions
                # This starts the study completely fresh
                cursor.execute("""
                    UPDATE task_instances 
                    SET is_assigned = FALSE, is_completed = FALSE, assigned_round = 0
                """)
            
            updated_rows = cursor.rowcount
            conn.commit()
            
        return jsonify({"status": "success", "reset_count": updated_rows})
    
    except Exception as e:
        logger.error(f"Error resetting assignments: {str(e)}")
        return jsonify({"error": "Server error"}), 500

@app.route('/status', methods=['GET'])
def get_status():
    """
    Get system status including task completion statistics.
    
    This endpoint provides an overview of the database state, including:
    - Counts of tasks, instances, and model responses
    - Number of assigned instances
    - Number of completed instances
    
    This would be useful for monitoring the progress of the study.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Get total counts of items in each table
            cursor.execute("SELECT COUNT(*) as count FROM tasks")
            total_tasks = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM task_instances")
            total_instances = cursor.fetchone()['count']
            
            cursor.execute("SELECT COUNT(*) as count FROM model_responses")
            total_models = cursor.fetchone()['count']
            
            # Get completion statistics
            cursor.execute("""
                SELECT 
                    SUM(CASE WHEN is_assigned = TRUE THEN 1 ELSE 0 END) as assigned,
                    SUM(CASE WHEN is_completed = TRUE THEN 1 ELSE 0 END) as completed
                FROM task_instances
            """)
            stats = cursor.fetchone()
            
            return jsonify({
                "status": "running",
                "database": {
                    "tasks": total_tasks,
                    "task_instances": total_instances,
                    "model_responses": total_models,
                    "assigned_instances": stats['assigned'],
                    "completed_instances": stats['completed']
                }
            })
    
    except Exception as e:
        logger.error(f"Error getting status: {str(e)}")
        return jsonify({"error": "Server error"}), 500

# Run the Flask application when this script is executed directly
# The port can be configured via environment variable
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
