"""
job_search.py

This script reads job search queries from lib/queries.json, calls the Google Programmable Search Engine API for each query, and outputs the results to a .txt file for LLM processing.

Usage:
    python job_search.py

Requirements:
    - requests
    - API key and Search Engine ID from Google Programmable Search Engine
    - queries.json in lib/
"""
import json
import requests
import os
from datetime import datetime, timedelta

# --- CONFIGURATION ---
API_KEY = "AIzaSyBUWhdqY1T3nD6Cyux2UE5j5_j7kKhkHAc"  # <-- Replace with your API key
SEARCH_ENGINE_ID = "f24bf644b72bf4b11"  # <-- Replace with your Search Engine ID
QUERIES_PATH = os.path.join(os.path.dirname(__file__), '../lib/queries.json')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '../output/job_results.txt')
DAYS_LOOKBACK = 3  # How many days back to search
DIFY_API_KEY = "YOUR_DIFY_API_KEY"  # <-- Replace with your Dify API key
DIFY_AGENT_URL = "https://api.dify.ai/v1/chat-messages"
DIFY_USER = "andre-picanco"

# --- FUNCTIONS ---
def load_queries(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def build_query(base_query, days_lookback):
    date_str = (datetime.now() - timedelta(days=days_lookback)).strftime('%Y-%m-%d')
    return f"{base_query}{date_str}"

def search_google(query, api_key, engine_id, num_results=10):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'key': api_key,
        'cx': engine_id,
        'q': query,
        'num': num_results
    }
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json().get('items', [])
    else:
        print(f"Error: {response.status_code} for query: {query}")
        return []

def format_result(item):
    title = item.get('title', '')
    link = item.get('link', '')
    snippet = item.get('snippet', '')
    return f"Title: {title}\nURL: {link}\nSnippet: {snippet}\n---\n"

def send_to_dify_agent(text, api_key, user, agent_url):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "query": text,
        "response_mode": "blocking",
        "user": user
    }
    response = requests.post(agent_url, headers=headers, json=data)
    if response.status_code == 200:
        result = response.json()
        print("Dify Agent Response:\n", result.get("answer", result))
        return result.get("answer", result)
    else:
        print(f"Error from Dify: {response.status_code} - {response.text}")
        return None

def main():
    queries = load_queries(QUERIES_PATH)
    all_results = []
    for name, base_query in queries.items():
        full_query = build_query(base_query, DAYS_LOOKBACK)
        print(f"Searching for: {name} -> {full_query}")
        results = search_google(full_query, API_KEY, SEARCH_ENGINE_ID)
        for item in results:
            formatted = format_result(item)
            all_results.append(formatted)
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
        f.writelines(all_results)
    print(f"Results written to {OUTPUT_PATH}")

    # Send to Dify agent
    with open(OUTPUT_PATH, 'r', encoding='utf-8') as f:
        job_text = f.read()
    send_to_dify_agent(job_text, DIFY_API_KEY, DIFY_USER, DIFY_AGENT_URL)

if __name__ == "__main__":
    main() 