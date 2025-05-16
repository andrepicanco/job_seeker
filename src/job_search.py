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
import sys
from datetime import datetime, timedelta
import mimetypes
import time

# Add the project root directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.profile_tokens import profile_tokens_pt, profile_tokens_en
from collections import Counter
from config import (
    GOOGLE_API_KEY,
    SEARCH_ENGINE_ID,
    DIFY_API_KEY,
    DIFY_AGENT_URL,
    DIFY_USER
)

# --- CONFIGURATION ---
API_KEY = GOOGLE_API_KEY
SEARCH_ENGINE_ID = SEARCH_ENGINE_ID
QUERIES_PATH = os.path.join(os.path.dirname(__file__), '../lib/queries.json')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '../output/job_results.json')
DAYS_LOOKBACK = 3  # How many days back to search

# --- FUNCTIONS ---
def load_queries(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def build_query(base_query, days_lookback):
    date_str = (datetime.now() - timedelta(days=days_lookback)).strftime('%Y-%m-%d')
    return f"{base_query}{date_str}"

# Search Google for raw job postings
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



# Send to Dify agent: JOB SCREENER (1)
def send_to_dify_agent(text, api_key, user, agent_url):
    
    # Upload the file first
    file_path = os.path.join(os.path.dirname(__file__), '../output/job_results.txt')
    
    #file_id = upload_file_to_dify(file_path, api_key, user)
    # files_param = []
    # if file_id:
    #     files_param = [{
    #         "type": "file",
    #         "transfer_method": "local_file",
    #         "upload_file_id": file_id
    #     }]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "inputs": {},
        "query": text,
        "response_mode": "blocking",
        "conversation_id": "",
        "user": user
        # "files": files_param
    }
    time.sleep(1)
    response = requests.post(agent_url, headers=headers, json=data)
    if response.status_code == 200:
        result = response.json()
        print("Dify Agent Response:\n", result.get("answer", result))
        return result.get("answer", result)
    else:
        print(f"Error from Dify: {response.status_code}")
        print(f'{json.loads(response.text)}')
        return None



def analyze_text_for_tokens(text, tokens_pt, tokens_en):
    """
    Analyze text for matching tokens and return detailed results
    """
    text_lower = text.lower()
    matches = {
        'pt': [],
        'en': [],
        'total': 0
    }
    
    # Check Portuguese tokens
    for token in tokens_pt:
        if token.lower() in text_lower:
            matches['pt'].append(token)
            matches['total'] += 1
    
    # Check English tokens
    for token in tokens_en:
        if token.lower() in text_lower:
            matches['en'].append(token)
            matches['total'] += 1
    
    return matches

def filter_job_listings(save=False, min_tokens=1):
    """
        Filter raw job listings based on token matches.
        Args:
            save (bool): Whether to save the filtered job listings to a file.
            min_tokens (int): Minimum number of tokens to match.
        Returns:
            dict: Filtered job listings.
    """

    # Load job listings
    with open('output/job_results.json', 'r', encoding='utf-8') as f:
        job_listings = json.load(f)

    # Process each listing
    for listing in job_listings:
        # Combine title and snippet for analysis
        text_to_check = f"{listing['Title']} {listing['Snippet']}"
        
        # Analyze text for tokens
        token_matches = analyze_text_for_tokens(text_to_check, profile_tokens_pt, profile_tokens_en)
        
        # Add analysis results to listing
        listing['token_analysis'] = {
            'matches_pt': token_matches['pt'],
            'matches_en': token_matches['en'],
            'total_matches': token_matches['total']
        }
        
        # Add remove flag (True if no tokens found)
        listing['remove'] = token_matches['total'] == 0

    # Print detailed results
    # print(f"Total listings: {len(job_listings)}")
    # print(f"Listings to remove: {sum(1 for listing in job_listings if listing['remove'])}")
    # print(f"Listings to keep: {sum(1 for listing in job_listings if not listing['remove'])}")

    # Filter job listings that has at least two token matches
    job_listings = [job for job in job_listings if job['token_analysis']['total_matches'] > min_tokens]

    # Save updated listings
    if save:
        with open('output/job_results_filtered.json', 'w', encoding='utf-8') as f:
            json.dump(job_listings, f, indent=2, ensure_ascii=False)

    return job_listings

### MAIN ###
def main():
    queries = load_queries(QUERIES_PATH)

    # TEMPORARY SECTION: READ FROM FILE "JOB_RESULTS.TXT"
    OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '../output/job_results.json')
    all_results = []

    """
    IMPROVEMENTS:
    1. Do pagination for Google Search
    """
    # TEMPORARY COMMENTED OUT (16/05/2025) ###########
    #
    # for name, base_query in queries.items():
    #     full_query = build_query(base_query, DAYS_LOOKBACK)
    #     print(f"Searching for: {name} -> {full_query}")
    #     results = search_google(full_query, API_KEY, SEARCH_ENGINE_ID)
    #     for item in results:
    #         formatted = format_result(item)
    #         all_results.append(formatted)
    #
    # TEMPORARY COMMENTED OUT (16/05/2025) ###########

    # os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    # Comment out the old txt file creation
    # with open(OUTPUT_PATH, 'w', encoding='utf-8') as f:
    #     f.writelines(all_results)
    # print(f"Results written to {OUTPUT_PATH}")

    # TEMPORARY COMMENTED OUT (16/05/2025) ###########
    #
    ## New section: Write results as JSON
    # json_output_path = os.path.join(os.path.dirname(__file__), '../output/job_results.json')
    # json_results = []
    # for result in all_results:
    #     lines = result.strip().split('\n')
    #     if len(lines) >= 3:
    #         title = lines[0].replace('Title: ', '')
    #         url = lines[1].replace('URL: ', '')
    #         snippet = lines[2].replace('Snippet: ', '')
    #         json_results.append({
    #             "Title": title,
    #             "URL": url,
    #             "Snippet": snippet
    #         })
    # with open(json_output_path, 'w', encoding='utf-8') as f:
    #     f.write(json.dumps(json_results, indent=2))
    # print(f"Results written to {json_output_path}")
    #
    # TEMPORARY COMMENTED OUT (16/05/2025) ###########


    """
    Filtering:
    1. Filtering by tokenized words from CV
    """

    filtered_job_listings = filter_job_listings(save=False, min_tokens=1)

    # Format job listings into a readable string
    formatted_listings = []
    for listing in filtered_job_listings:
        formatted_listings.append(
            f"Title: {listing['Title']}\n"
            f"URL: {listing['URL']}\n"
            f"Snippet: {listing['Snippet']}\n"
            "---"
        )

    # Create screening prompt with formatted listings
    screening_prompt = f"""
    Please analyze these job listings and provide insights on their relevance and fit.
    {chr(10).join(formatted_listings)}
    """
        
    response = send_to_dify_agent(screening_prompt, DIFY_API_KEY, DIFY_USER, DIFY_AGENT_URL)
    print(response)

if __name__ == "__main__":
    main() 