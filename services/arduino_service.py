import json
import logging
import time
import serial
import serial.tools.list_ports as list_ports

def find_arduino_ports(description):
    """
    Scans the available COM ports and returns paths of devices
    whose description matches the target search string.
    """
    if not description:
        # If no search filter is specified, return all active COM port devices
        return [p.device for p in list_ports.comports()]
        
    return [
        p.device
        for p in list_ports.comports()
        if description.lower() in p.description.lower()
    ]

def send_data_to_arduino(port, baud_rate, data_dict):
    """
    Opens serial interface connection, waits for Arduino initialization,
    writes the structured data dictionary as a JSON bytes string, 
    and closes connection safely.
    """
    logging.info(f"Connecting to Arduino on port {port} at {baud_rate} baud...")
    
    try:
        arduino = serial.Serial(port, baud_rate)
    except Exception as e:
        raise Exception(f"Failed to connect to Arduino: {str(e)}")
        
    # Wait for the bootloader/microcontroller connection to initialize
    time.sleep(2)
    
    if not arduino.is_open:
        raise Exception("Could not verify active status of Arduino serial port.")
        
    try:
        # Package and serialize structured tracking parameters
        data_string = json.dumps(data_dict)
        arduino.write(data_string.encode())
    except Exception as e:
        raise Exception(f"Error during serial write execution: {str(e)}")
    finally:
        # Ensure serial resources are freed safely
        arduino.close()
        logging.info("Arduino communication completed successfully. Connection closed.")