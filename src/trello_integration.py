"""
trello_integration.py

This module handles the integration with Trello API to create and manage cards for job opportunities.
"""
import sys
import os

# Add the project root directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import os
import requests

# Get environment variables directly
TRELLO_API_KEY = os.environ['TRELLO_API_KEY']
TRELLO_TOKEN = os.environ['TRELLO_TOKEN']
TRELLO_BOARD_ID = os.environ['TRELLO_BOARD_ID']
TRELLO_LIST_ID = os.environ['TRELLO_LIST_ID']


def create_trello_card(job_data):
    """
    Create a Trello card for a job opportunity.
    
    Args:
        job_data (dict): Dictionary containing job information with keys:
            - title: Job title
            - url: Job posting URL
            - description: Job description/snippet
            - recommendation: AI recommendation (e.g., "INVESTIGAR MAIS", "CANDIDATAR-SE")
    
    Returns:
        dict: Response from Trello API containing the created card information
    """
    url = "https://api.trello.com/1/cards"
    
    # Prepare card data
    card_data = {
        'idList': TRELLO_LIST_ID,
        'key': TRELLO_API_KEY,
        'token': TRELLO_TOKEN,
        'name': job_data["EMPRESA"],
        'desc': f'CLASSIFICAÇÃO: **{job_data['CLASSIFICAÇÃO']}**\n{job_data["ANÁLISE"]}\n\n**RECOMENDAÇÃO: {job_data['RECOMENDAÇÃO']}**',
        'urlSource': job_data['URL'],
        'pos': 'top'
    }

    # Add a label for jobs that are recommended, according to AI Agent
    if job_data['RECOMENDAÇÃO'] == 'CANDIDATAR-SE':
        card_data['idLabels'] = '67eddecc96db48eddbbeb469' # it's a Green Label ID
    
    try:
        response = requests.post(url, json=card_data)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error creating Trello card: {e}")
        return None

def create_trello_cards_from_jobs(jobs):
    """
    Create multiple Trello cards from a list of job opportunities.
    
    Args:
        jobs (list): List of job dictionaries containing job information
    
    Returns:
        list: List of created Trello card responses
    """
    created_cards = []
    
    for job in jobs:
        card_response = create_trello_card(job)
        if card_response:
            created_cards.append(card_response)
            print(f"Created Trello card for: {job['EMPRESA']}")
    
    return created_cards 