import json
import logging
import requests
from skyfield.api import load, EarthSatellite

def load_satellite_data(filename):
    """Loads satellite name-to-id mapping from a local JSON file."""
    try:
        with open(filename, 'r') as infile:
            return json.load(infile)
    except Exception as e:
        logging.error(f"Failed to load satellite data from {filename}: {str(e)}")
        return {}

def load_satellite_names(filename):
    """Loads and returns all satellite names from the local JSON database."""
    try:
        with open(filename, 'r') as infile:
            data = json.load(infile)
            return list(data.keys())
    except Exception as e:
        logging.error(f"Failed to load satellite names from {filename}: {str(e)}")
        return []

def get_satellite_id(satellite_name, satellite_data):
    """Retrieves the satellite ID based on the selected satellite name."""
    return satellite_data.get(satellite_name, None)

def fetch_tle_data(satellite_id, api_key, max_retries=3, timeout=50):
    """
    Fetches the TLE data from the N2YO API.
    Retries up to max_retries and exits the loop immediately upon success.
    """
    # Using the exact URL formatting structure from the original code
    url = f"https://api.n2yo.com/rest/v1/satellite/tle/{satellite_id}/&apiKey={api_key}"
    
    for attempt in range(max_retries):
        logging.info(f"Attempting to connect to N2YO API. Attempt {attempt + 1}/{max_retries}")
        try:
            response = requests.get(url, timeout=timeout)
            
            if response.status_code == 403:
                raise Exception("Received 403 Forbidden status code from N2YO API. Please check your API key.")
            elif response.status_code != 200:
                raise Exception(f"Received status code {response.status_code} from N2YO API.")
            
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                raise Exception(f"Failed to parse JSON response from N2YO API: {str(e)}")
            
            if 'error' in data:
                raise Exception(f"API Error: {data['error']}")
            
            if 'tle' not in data:
                raise Exception("No TLE data found in the API response.")
                
            # Successfully fetched, break out of the retry loop and return the TLE string
            return data['tle']
            
        except requests.RequestException as e:
            logging.warning(f"Connection attempt {attempt + 1} failed: {str(e)}")
            if attempt == max_retries - 1:
                raise Exception(f"Failed to fetch satellite data after {max_retries} attempts.")

def calculate_orbital_data(satellite_name, tle_str):
    """
    Calculates orbital elements using Skyfield based on the fetched TLE string.
    Returns a dictionary of calculated parameters.
    """
    lines = tle_str.splitlines()
    if len(lines) < 2:
        raise Exception("TLE data is incomplete (fewer than 2 lines).")
        
    line1 = lines[0]
    line2 = lines[1]
    
    # Initialize EarthSatellite using Skyfield
    satellite = EarthSatellite(line1, line2, satellite_name)
    
    # Fetch timescale
    ts = load.timescale()
    
    # Extract structural model elements exactly as the original code
    orbital_elements = {
        'semi_major_axis': satellite.model.a,
        'eccentricity': satellite.model.ecco,
        'inclination': satellite.model.inclo,
        'argument_periapsis': satellite.model.argpo,
        'ascending_node': satellite.model.nodeo,
        'mean_anomaly': satellite.model.mo
    }
    
    # Calculate longitude
    longitude = orbital_elements['ascending_node'] + orbital_elements['mean_anomaly']
    
    return {
        'satellite_name': satellite_name,
        'argument_periapsis': orbital_elements['argument_periapsis'],
        'eccentricity': orbital_elements['eccentricity'],
        'inclination': orbital_elements['inclination'],
        'mean_anomaly': orbital_elements['mean_anomaly'],
        'semi_major_axis': orbital_elements['semi_major_axis'],
        'ascending_node': orbital_elements['ascending_node'],
        'longitude': longitude
    }