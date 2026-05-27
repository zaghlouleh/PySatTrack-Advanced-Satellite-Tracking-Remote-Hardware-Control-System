import time
import threading
import logging
from src.services.api_service import fetch_geolocation_data, fetch_satellite_position
from src.models.data_manager import get_satellite_id, save_satellite_tracking_info, load_all_satellite_mappings
from src.hardware.arduino import send_data_to_arduino

def continuous_update(satellite_name, city_name, observer_alt, seconds, arduino_port, baud_rate, satellite_id, callback_msg_func):
    """
    Loop that continuously fetches satellite data and saves it to a JSON file.
    """
    while True:
        # Fetch geolocation data
        observer_lat, observer_lng = fetch_geolocation_data(city_name)
        
        if observer_lat is None or observer_lng is None:
            callback_msg_func("Error fetching geolocation data.\n", "red")
            return
        
        # Fetch satellite position data
        position_info = fetch_satellite_position(observer_lat, observer_lng, observer_alt, seconds, satellite_id)
        
        if position_info is None:
            callback_msg_func("Error fetching satellite position data.\n", "red")
            return
        
        # Save the satellite data to a JSON file
        save_satellite_tracking_info(satellite_name, position_info)

        # Log success message
        logging.info(f"Updated satellite data for {satellite_name} saved.")

        # Wait for the specified seconds before the next update
        time.sleep(int(seconds))

def run_single_fetch_and_send(satellite_name, city_name, observer_alt, seconds, arduino_port, baud_rate, arduino_description, callback_msg_func):
    """
    Logic for a single fetch operation that also sends data to the Arduino.
    Equivalent to the original fetch_satellite_data function.
    """
    # Validate inputs
    try:
        seconds_int = int(seconds)
        if seconds_int > 300:
            callback_msg_func("Error: Seconds must be 300 or less.\n", "red")
            return
    except ValueError:
        callback_msg_func("Error: Invalid input for seconds.\n", "red")
        return

    try:
        observer_alt_float = float(observer_alt)
    except ValueError:
        callback_msg_func("Error: Invalid input for observer altitude.\n", "red")
        return

    # Get satellite ID
    mappings = load_all_satellite_mappings()
    satellite_id = get_satellite_id(satellite_name, mappings)
    if not satellite_id:
        callback_msg_func("Error: Satellite name not found.\n", "red")
        return

    # Fetch geolocation
    lat, lng = fetch_geolocation_data(city_name)
    if lat is None or lng is None:
        callback_msg_func("Error fetching geolocation data.\n", "red")
        return

    # Fetch position
    position_info = fetch_satellite_position(lat, lng, observer_alt_float, seconds_int, satellite_id)
    if position_info is None:
        callback_msg_func("Error fetching satellite position data.\n", "red")
        return

    # Save data
    save_satellite_tracking_info(satellite_name, position_info)
    logging.info(f"Satellite data for {satellite_name} saved.")

    # Send to Arduino
    success, message = send_data_to_arduino(arduino_port, int(baud_rate), position_info)
    if success:
        callback_msg_func(f"Arduino connection verified\n", "green")
    else:
        callback_msg_func(f"{message}\n", "red")

def fetch_satellite_data_threaded(satellite_name, city_name, observer_alt, seconds, arduino_port, baud_rate, arduino_description, callback_msg_func):
    """
    Starts the continuous update loop in a background thread.
    """
    mappings = load_all_satellite_mappings()
    satellite_id = get_satellite_id(satellite_name, mappings)
    
    if not satellite_id:
        callback_msg_func("Error: Satellite name not found.\n", "red")
        return

    thread = threading.Thread(
        target=continuous_update, 
        args=(satellite_name, city_name, observer_alt, seconds, arduino_port, baud_rate, satellite_id, callback_msg_func),
        daemon=True
    )
    thread.start()