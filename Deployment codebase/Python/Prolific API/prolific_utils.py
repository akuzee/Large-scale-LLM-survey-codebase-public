"""
Utility functions for interacting with the Prolific API.

This module provides common functions for making requests, handling authentication,
and processing responses to reduce code duplication in the main scripts.
"""

import requests
import json
import config  # Import configuration settings from config.py

def get_auth_headers():
    """
    Creates the standard authentication headers required for Prolific API requests.

    Reads the API token from the config.py file.

    Returns:
        dict: A dictionary containing the 'Authorization' and 'Content-Type' headers.
              Returns None if the API token is not set or is the placeholder.
    """
    if not config.API_TOKEN or config.API_TOKEN == "YOUR_SECRET_API_TOKEN_HERE":
        print("ERROR: API_TOKEN is not set in config.py or is still the placeholder.")
        print("Please add your actual Prolific API token to config.py before running.")
        return None

    return {
        "Authorization": f"Token {config.API_TOKEN}",
        # Most POST/PATCH requests require a JSON body
        "Content-Type": "application/json"
    }

def make_api_request(method, endpoint, json_data=None, params=None):
    """
    Makes a request to a specific Prolific API endpoint.

    Handles constructing the full URL, adding authentication headers,
    sending the request, and basic error handling.

    Args:
        method (str): The HTTP method (e.g., 'GET', 'POST', 'PATCH', 'DELETE').
        endpoint (str): The API endpoint path (e.g., '/users/me/', '/studies/').
                        Should start with a '/'.
        json_data (dict, optional): The JSON payload for POST/PATCH requests. Defaults to None.
        params (dict, optional): URL parameters for GET requests. Defaults to None.

    Returns:
        dict or None: The parsed JSON response from the API on success (status 2xx),
                      or None if an error occurs or authentication fails.
    """
    headers = get_auth_headers()
    if not headers:
        return None # Stop if auth headers couldn't be generated

    full_url = f"{config.BASE_URL}{endpoint}"

    print(f"--- Making {method.upper()} request to: {full_url} ---")
    if json_data:
        print(f"Request Body: {json.dumps(json_data, indent=2)}") # Pretty print JSON body
    if params:
        print(f"URL Parameters: {params}")

    try:
        response = requests.request(
            method=method,
            url=full_url,
            headers=headers,
            json=json_data, # requests library handles JSON encoding
            params=params
        )

        # Raise an exception for bad status codes (4xx client errors or 5xx server errors)
        response.raise_for_status()

        print(f"API Call Successful (Status Code: {response.status_code})")

        # Handle cases where the response might be empty (e.g., 204 No Content)
        if response.status_code == 204 or not response.content:
            return {} # Return an empty dict for consistency

        # Attempt to parse the JSON response
        return response.json()

    except requests.exceptions.RequestException as e:
        print(f"\n--- API Request Failed --- ")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Message: {e}")

        # Try to get more details from the response if it exists
        if e.response is not None:
            print(f"Status Code: {e.response.status_code}")
            try:
                # Prolific API often returns detailed errors in JSON format
                error_details = e.response.json()
                print(f"API Error Details: {json.dumps(error_details, indent=2)}")
            except json.JSONDecodeError:
                # If the response isn't JSON, print the raw text
                print(f"Response Body (Non-JSON): {e.response.text}")
        else:
            print("No response received from the server (e.g., network issue).")

        print("--------------------------\n")
        return None
    except json.JSONDecodeError:
        print(f"\n--- API Response JSON Parsing Failed ---")
        print(f"Status Code: {response.status_code}")
        print(f"Could not decode JSON from response body:")
        print(response.text)
        print("--------------------------------------\n")
        return None
