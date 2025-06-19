import pytest
from unittest.mock import Mock, patch
import json
import pandas as pd
from datetime import datetime, timedelta
import pytz
from URL_database import app

# Mock data setup
@pytest.fixture
def mock_task_data():
    """Generate mock task data for testing"""
    return [
        {
            "task_id": "task1",
            "occupation_id": "software_engineer",
            "available": True,
            "assigned_at": None,
            "task_url": "https://qualtrics.com/task1",
            "response_url_1": "https://dropbox.com/response1_1",
            "response_url_2": "https://dropbox.com/response1_2",
            "response_url_3": "https://dropbox.com/response1_3",
            "response_url_4": "https://dropbox.com/response1_4",
            "response_url_5": "https://dropbox.com/response1_5"
        },
        {
            "task_id": "task2",
            "occupation_id": "data_scientist",
            "available": False,
            "assigned_at": datetime.now(pytz.UTC).isoformat(),
            "task_url": "https://qualtrics.com/task2",
            "response_url_1": "https://dropbox.com/response2_1",
            "response_url_2": "https://dropbox.com/response2_2",
            "response_url_3": "https://dropbox.com/response2_3",
            "response_url_4": "https://dropbox.com/response2_4",
            "response_url_5": "https://dropbox.com/response2_5"
        }
    ]

@pytest.fixture
def client():
    """Create a test client"""
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

# Mock Firestore for testing
@pytest.fixture
def mock_firestore():
    """Create a mock Firestore client"""
    with patch('URL_database.db') as mock_db:
        mock_collection = Mock()
        mock_db.collection.return_value = mock_collection
        yield mock_db

# Test cases
def test_get_task_urls(client, mock_firestore, mock_task_data):
    """Test the get_task_urls endpoint"""
    # Mock Firestore query response
    mock_docs = [Mock(to_dict=lambda: doc) for doc in mock_task_data]
    mock_firestore.collection().where().where().limit().stream.return_value = mock_docs[:1]
    
    # Test successful task retrieval
    response = client.get('/get_task_urls?occupation_id=software_engineer')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "task_url" in data
    assert len(data["response_urls"]) == 5

    # Test no available tasks
    mock_firestore.collection().where().where().limit().stream.return_value = []
    response = client.get('/get_task_urls?occupation_id=nonexistent')
    assert response.status_code == 404

def test_update_task_availability(client, mock_firestore, mock_task_data):
    """Test the update_task_availability endpoint"""
    # Mock transaction
    mock_transaction = Mock()
    mock_firestore.transaction.return_value.__enter__.return_value = mock_transaction
    
    # Test successful update
    update_data = {
        "task_id": "task1",
        "available": False
    }
    response = client.post('/update_task_availability', 
                          json=update_data,
                          content_type='application/json')
    assert response.status_code == 200

    # Test invalid task update
    invalid_data = {
        "task_id": "nonexistent",
        "available": False
    }
    response = client.post('/update_task_availability', 
                          json=invalid_data,
                          content_type='application/json')
    assert response.status_code == 404

def test_export_data(client, mock_firestore, mock_task_data):
    """Test the export_data endpoint"""
    # Mock Firestore query response
    mock_docs = [Mock(to_dict=lambda: doc) for doc in mock_task_data]
    mock_firestore.collection().stream.return_value = mock_docs
    
    # Test CSV export
    response = client.get('/export_data?format=csv')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'text/csv'
    
    # Test JSON export
    response = client.get('/export_data?format=json')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'application/json'

def test_import_data(client, mock_firestore):
    """Test the import_data endpoint"""
    # Create mock CSV data
    csv_data = pd.DataFrame(mock_task_data).to_csv()
    
    # Test CSV import
    response = client.post('/import_data',
                          data={'file': (bytes(csv_data, 'utf-8'), 'test.csv'),
                                'clear_existing': 'false'},
                          content_type='multipart/form-data')
    assert response.status_code == 200

    # Test invalid file format
    response = client.post('/import_data',
                          data={'file': (b'invalid data', 'test.txt'),
                                'clear_existing': 'false'},
                          content_type='multipart/form-data')
    assert response.status_code == 400

def test_dashboard(client, mock_firestore, mock_task_data):
    """Test the dashboard endpoint"""
    # Mock Firestore query responses
    mock_docs = [Mock(to_dict=lambda: doc) for doc in mock_task_data]
    mock_firestore.collection().stream.return_value = mock_docs
    
    # Test HTML response
    response = client.get('/dashboard')
    assert response.status_code == 200
    assert 'text/html' in response.headers['Content-Type']
    
    # Test JSON response
    response = client.get('/dashboard?format=json')
    assert response.status_code == 200
    assert response.headers['Content-Type'] == 'application/json'

if __name__ == '__main__':
    pytest.main(['-v']) 