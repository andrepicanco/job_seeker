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
import re
from sseclient import SSEClient
from trello_integration import create_trello_cards_from_jobs

# Add the project root directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.profile_tokens import profile_tokens_pt, profile_tokens_en
from collections import Counter
GOOGLE_API_KEY = os.environ['GOOGLE_API_KEY']
SEARCH_ENGINE_ID = os.environ['SEARCH_ENGINE_ID']
DIFY_API_KEY = os.environ['DIFY_API_KEY']
DIFY_API_KEY_SEEKER = os.environ['DIFY_API_KEY_SEEKER']
DIFY_AGENT_URL = os.environ['DIFY_AGENT_URL']
DIFY_USER = os.environ['DIFY_USER']

# --- CONFIGURATION ---
###***********************************************************************************************************************###
API_KEY = GOOGLE_API_KEY
SEARCH_ENGINE_ID = SEARCH_ENGINE_ID
QUERIES_PATH = os.path.join(os.path.dirname(__file__), '../lib/queries.json')
OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '../output/job_results.json')
AI_SCREEN_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '../output/ai_screening.json')
JOB_ANALYSIS_OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '../output/job_analysis.json')
DAYS_LOOKBACK = 1  # How many days back to search
MAX_RESULTS = 50

# --- FUNCTIONS ---
###***********************************************************************************************************************###
def load_queries(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

###***********************************************************************************************************************###
def build_query(base_query, days_lookback):
    date_str = (datetime.now() - timedelta(days=days_lookback)).strftime('%Y-%m-%d')
    return f"{base_query}{date_str}"

###***********************************************************************************************************************###
# Search Google for raw job postings
def search_google(query, api_key, engine_id, num_results=10, start=1):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'key': api_key,
        'cx': engine_id,
        'q': query,
        'num': num_results,
        'start': start
    }
    
    response = requests.get(url, params=params)
    j = json.loads(response.text)

    if response.status_code == 200:
        print(f"Resultados: {int(j['searchInformation']['totalResults'])}") ## DESCOMENTAR
        obj = {
            'search_results': int(j['searchInformation']['totalResults']),
            'items': [response.json().get('items', [])]
        }
        return obj
    else:
        print(f"Error: {response.status_code} for query: {query}")
        return []

###***********************************************************************************************************************###
def format_result(item):
    title = item.get('title', '')
    link = item.get('link', '')
    snippet = item.get('snippet', '')
    return f"Title: {title}\nURL: {link}\nSnippet: {snippet}\n---\n"

###***********************************************************************************************************************###
# Group searches Google Search Engine (optimized way)
def group_search(queries, max_results_per_query=30):

    """
        Optimize Google Engine searches, avoiding 429 error callbacks.
    Args:
        queries (dict): List of queries to be performed
        max_results_per_query (int): Max items to be provided by google search, for a given query
    Returns:
        dict: List of potential job applications, structured in JSON format
    """

    current_queries = {}
    group_results = []

    # Transform JSON structure for ATS queries
    for ats, base_query in queries.items():

        current_queries[ats] = {
            'name': build_query(base_query, DAYS_LOOKBACK),
            'num_results': 1,
            'finished': False
        }

    # Performing queries to each item in list of queries
    for name, query in current_queries.items():

        while query['finished'] is not True:

            # Google Search Query
            results = search_google(query['name'], GOOGLE_API_KEY, SEARCH_ENGINE_ID, start=query['num_results'])

            # Accessing query items, appending it to every result found.
            try:
                print(f"Consulta de {name}: {results['search_results']} resultados.")
                for item in results['items'][0]:
                    formatted = format_result(item)
                    group_results.append(formatted)
            except:
                print(f'Deu um erro no item: {query}')
                break

            # Preparando para próximas iterações
            if (results['search_results'] > 10) & (query['num_results'] <= max_results_per_query):
                query['num_results'] += 10
            else:
                query['num_results'] = results['search_results']
                ## print(f"Acabaram consultas de: {name} ({query['num_results']} resultados)")
                query['finished'] = True
    
    return group_results

###***********************************************************************************************************************###
# Send messages to Dify Agents and Assistants
def send_to_dify_agent(text, api_key, user, dify_url, response_mode='blocking'):
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    data = {
        "inputs": {},
        "query": text,
        "response_mode": response_mode,
        "conversation_id": "",
        "user": user
    }
    time.sleep(1)

    if response_mode == 'blocking':
        response = requests.post(dify_url, headers=headers, json=data)
        if response.status_code == 200:
            result = response.json()
            # print("Dify Agent Response:\n", result.get("answer", result))
            return result.get("answer", result)
        else:
            print(f"Error from Dify: {response.status_code}")
            print(f'{json.loads(response.text)}')
            return None
    
    # Streaming mode using sseclient-py
    else:
        full_response_text = ""
        try:
            # Create a session with the headers
            session = requests.Session()
            session.headers.update(headers)
            
            # Make the initial POST request to get the SSE stream
            response = session.post(dify_url, json=data, stream=True)
            if response.status_code != 200:
                print(f"Error from Dify: {response.status_code}")
                print(f'{response.text}')
                return None

            # Create SSEClient with the response
            messages = SSEClient(response)
            
            # Process SSE events by iterating over messages.events()
            for msg in messages.events():
                try:
                    if msg.data:
                        event_data = json.loads(msg.data)
                        
                        # Handle different event types
                        if event_data.get('event') == 'agent_message':
                            text_content = event_data.get('answer', '')
                            full_response_text += text_content
                        elif event_data.get('event') == 'error':
                            error_msg = event_data.get('answer', 'Unknown error')
                            print(f"Streaming error: {error_msg}")
                            return None
                        elif event_data.get('event') == 'workflow_finished':
                            # End of stream
                            break
                            
                except json.JSONDecodeError as e:
                    print(f"Error decoding JSON event: {e}")
                    continue
                except Exception as e:
                    print(f"Error processing event: {e}")
                    continue

            return full_response_text

        except requests.exceptions.Timeout:
            print("Request timed out")
            return None
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error: {e}")
            return None

###***********************************************************************************************************************###
## Parses JSON outputs from LLM
def parse_llm_json(json_from_llm_output):
    """
    Args:
        json_from_llm_output (str): Text usually generated by LLMs for JSON structures
    Output:
        Object
    """

    parsed_data = []

    # Regex to find all blocks starting with ```json and ending with ```
    # It captures the content between these markers.
    # The 's' flag makes '.' match newlines as well.
    json_blocks = re.findall(r"```json\s*(.*?)\s*```", json_from_llm_output, re.DOTALL)

    for block in json_blocks:
        # Clean the block: remove any trailing commas and strip whitespace
        cleaned_block = block.strip()
        if cleaned_block.endswith(','):
            cleaned_block = cleaned_block[:-1] # Remove the trailing comma

        try:
            # Additional cleaning steps for common JSON issues
            # Replace invalid escape sequences with spaces
            cleaned_block = re.sub(r'\\[^"\\/bfnrtu]', ' ', cleaned_block)
            # Replace \xa0 with space
            cleaned_block = cleaned_block.replace('\\xa0', ' ')
            # Replace other common problematic characters
            cleaned_block = cleaned_block.replace('\\u00a0', ' ')
            cleaned_block = cleaned_block.replace('\\u2014', '-')
            cleaned_block = cleaned_block.replace('\\u2013', '-')
            cleaned_block = cleaned_block.replace('\\u2019', "'")
            cleaned_block = cleaned_block.replace('\\u2018', "'")
            cleaned_block = cleaned_block.replace('\\u201c', '"')
            cleaned_block = cleaned_block.replace('\\u201d', '"')
            
            # Remove any remaining invalid escape sequences
            cleaned_block = re.sub(r'\\(?!["\\/bfnrtu])', '', cleaned_block)

            # Parse the cleaned JSON string
            json_object = json.loads(cleaned_block)
            parsed_data.append(json_object)
        except json.JSONDecodeError as e:
            print(f"Erro ao decodificar JSON: {e}")
            print(f"Bloco problemático: \n---\n{cleaned_block}\n---")
            # Try to fix common JSON formatting issues
            try:
                # Remove any remaining invalid characters
                cleaned_block = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', cleaned_block)
                # Try parsing again
                json_object = json.loads(cleaned_block)
                parsed_data.append(json_object)
            except json.JSONDecodeError as e2:
                print(f"Falha na segunda tentativa de decodificação: {e2}")
                continue

    # Optionally, extract the summary text if it's always at the end after all JSON blocks
    # summary_match = re.search(r"```\s*(Resumo das vagas:.*?)\s*$", json_from_llm_output, re.DOTALL)
    #summary_text = summary_match.group(1).strip() if summary_match else None

    return parsed_data

###***********************************************************************************************************************###
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

###***********************************************************************************************************************###
def filter_job_listings(raw_job_listings, save=False, min_tokens=1):
    """
        Filter raw job listings based on token matches.
        Args:
            raw_job_listings (dict): List of raw job listings saved in "output/job_results.json"
            save (bool): Whether to save the filtered job listings to a file.
            min_tokens (int): Minimum number of tokens to match.
        Returns:
            dict: Filtered job listings.
    """

    # Process each listing
    for listing in raw_job_listings:
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
    # print(f"Total listings: {len(raw_job_listings)}")
    # print(f"Listings to remove: {sum(1 for listing in raw_job_listings if listing['remove'])}")
    # print(f"Listings to keep: {sum(1 for listing in raw_job_listings if not listing['remove'])}")

    # Filter job listings that has at least two token matches
    filtered_job_listings = [job for job in raw_job_listings if job['token_analysis']['total_matches'] > min_tokens]

    # Save updated listings
    if save:
        with open('output/job_results_filtered.json', 'w', encoding='utf-8') as f:
            json.dump(filtered_job_listings, f, indent=2, ensure_ascii=False)

    return filtered_job_listings

###***********************************************************************************************************************###
def parse_ai_screening_results(json_content):
    """
    Parse the AI screening results from JSON format into a readable text format.
    
    Args:
        json_content (str): The JSON content from ai_screening.json
        
    Returns:
        str: Formatted text containing the job listings
    """
    try:
        # If the content is already a string, try to parse it directly
        if isinstance(json_content, str):
            # Remove the ```json wrapper if present
            if json_content.startswith('```json'):
                json_content = json_content[7:]
            if json_content.endswith('```'):
                json_content = json_content[:-3]
            
            # Clean up escaped characters
            json_content = json_content.replace('\\n', ' ').replace('\\xa0', ' ')
            json_content = json_content.strip()
            
            # Parse the JSON content
            job_listings = json.loads(json_content)
        else:
            # If it's already a parsed JSON object, use it directly
            job_listings = json_content
        
        # Format each job listing
        formatted_text = "AI Screening Results:\n\n"
        for idx, job in enumerate(job_listings, 1):
            formatted_text += f"Job #{idx}\n"
            formatted_text += f"Title: {job['title']}\n"
            formatted_text += f"Fit Score: {job['fit_score']}/100\n"
            formatted_text += f"Description: {job['snippet']}\n"
            formatted_text += f"Link: {job['link']}\n"
            formatted_text += "-" * 80 + "\n\n"
            
        return formatted_text
        
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON content: {e}")
        return None
    except Exception as e:
        print(f"Error processing content: {e}")
        return None

############################################# MAIN ###################################################
def main():

    """
    NO API CALL SECTION (FOR DEV PURPOSES) - 31/05
    """
    # # TEMPORARY SECTION: READ FROM FILE "JOB_RESULTS.TXT"
    # OUTPUT_PATH = os.path.join(os.path.dirname(__file__), '../output/job_results.json')
    
    # # Load job listings
    # with open('output/job_results.json', 'r', encoding='utf-8') as f:
    #     job_listings = json.load(f)

    # #### Filtering:
    # #### 1. Filtering by tokenized words from CV
    # filtered_job_listings = filter_job_listings(job_listings, save=False, min_tokens=1)

    # # Format job listings into readable format for AIs
    # formatted_listings = []
    # for listing in filtered_job_listings:

    #     formatted_listings.append(
    #         f"Title: {listing['Title']} §"
    #         f"URL: {listing['URL']} §"
    #         f"Snippet: {listing['Snippet']} §"
    #         "---"
    #     )

    # # Saving filtered job listings to a file
    # with open('output/formmatted_job_listings.json', 'w', encoding='utf-8') as f:
    #     json.dump(formatted_listings, f, indent=2, ensure_ascii=False)

    # # Create screening prompt with formatted listings
    # screening_prompt = f"""Please analyze these job listings and provide insights on their relevance and fit.
    # ---
    # {chr(10).join(str(formatted_listings))}"""

    # ## Load job listings (30/05) - RUN THIS TO REDUCE API CONSUMPTION
    # with open('output/ai_screening.json', 'r', encoding='utf-8') as f:
    #     response = json.load(f)
    
    # parsed_json = parse_ai_screening_results(response)

    # ### Load job analysis (30/05) - RUN THIS TO REDUCE API CONSUMPTION
    # with open('output/job_analysis.json', 'r', encoding='utf-8') as f:
    #     response = json.load(f)

    # parsed_json = parse_llm_json(response)[0]
    
    """********************************************
            PRODUCTION CODE SECTION - 31/05
    ********************************************"""

    queries = load_queries(QUERIES_PATH)

    ## TEMPORARY SECTION: USED TO AVOID GOOGLE SEARCHING DURING DEV    
    ## (26/05/2025): Testing a group function
    all_results = group_search(queries) ## DESCOMENTAR P/ PERFORMAR NOVAS BUSCAS
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    
    ## New section: Write results as JSON
    json_output_path = os.path.join(os.path.dirname(__file__), '../output/job_results.json')
    job_listings = []
    for result in all_results:
        lines = result.strip().split('\n')
        if len(lines) >= 3:
            title = lines[0].replace('Title: ', '')
            url = lines[1].replace('URL: ', '')
            snippet = lines[2].replace('Snippet: ', '')
            job_listings.append({
                "Title": title,
                "URL": url,
                "Snippet": snippet
            })
    
    ### For log purposes
    with open(json_output_path, 'w', encoding='utf-8') as f:
        f.write(json.dumps(job_listings, indent=2))
    print(f"Search results written to {json_output_path}")

    ### Filtering:
    ### 1. Filtering by tokenized words from CV
    filtered_job_listings = filter_job_listings(job_listings, save=False, min_tokens=1)

    # Format job listings into readable format for AIs
    formatted_listings = []
    for listing in filtered_job_listings:

        formatted_listings.append(
            f"Title: {listing['Title']} §"
            f"URL: {listing['URL']} §"
            f"Snippet: {listing['Snippet']} §"
            "---"
        )

    # Saving filtered job listings to a file
    with open('output/formmatted_job_listings.json', 'w', encoding='utf-8') as f:
        json.dump(formatted_listings, f, indent=2, ensure_ascii=False)

    # Create screening prompt with formatted listings
    screening_prompt = f"""Please analyze these job listings and provide insights on their relevance and fit.
    ---
    {chr(10).join(str(formatted_listings))}
    """

    ## (30/05) - RESPONSE COMMENTED TO REDUCE API CONSUMPTION. UNCOMMENT WHEN IN PRD
    response = send_to_dify_agent(screening_prompt, DIFY_API_KEY, DIFY_USER, DIFY_AGENT_URL)

    ## Write AI screening response to JSON file
    os.makedirs(os.path.dirname(AI_SCREEN_OUTPUT_PATH), exist_ok=True)
    with open(AI_SCREEN_OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(response, f, indent=2, ensure_ascii=False)
    print(f"AI screening results written to {AI_SCREEN_OUTPUT_PATH}")

    parsed_json = parse_ai_screening_results(response)

    ## (30/05) - RESPONSE COMMENTED TO REDUCE API CONSUMPTION. UNCOMMENT WHEN IN PRD
    listings_analysis = send_to_dify_agent(parsed_json, DIFY_API_KEY_SEEKER, DIFY_USER, DIFY_AGENT_URL, response_mode='streaming')

    ## Write AI screening response to JSON file
    os.makedirs(os.path.dirname(JOB_ANALYSIS_OUTPUT_PATH), exist_ok=True)
       
    with open(JOB_ANALYSIS_OUTPUT_PATH, 'w', encoding='utf-8') as f:
        json.dump(listings_analysis, f, indent=2, ensure_ascii=False)

    parsed_json = parse_llm_json(listings_analysis)[0]

    print(f"Job analysis written into {JOB_ANALYSIS_OUTPUT_PATH}")

    """********************************************
          [END] PRODUCTION CODE SECTION - 31/05
    ********************************************"""

    recomendados = ['INVESTIGAR MAIS', 'CANDIDATAR-SE']

    try:
        trello_cards = [job for job in parsed_json if job['RECOMENDAÇÃO'] in recomendados]

        # Create Trello cards for recommended jobs
        if trello_cards:
            print(f"\nCreating Trello cards for {len(trello_cards)} recommended jobs...")
            created_cards = create_trello_cards_from_jobs(trello_cards)
            print(f"Successfully created {len(created_cards)} Trello cards")
        else:
            print("\nNo jobs to create Trello cards for")

    except Exception as e:
        print(f'Failed to create trello cards: {e}')

if __name__ == "__main__":
    main() 