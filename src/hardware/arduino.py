import serial
import serial.tools.list_ports as list_ports
import json
import time
import logging

def get_arduino_ports(arduino_description):
    """
    Returns a list of COM ports where the description matches.
    """
    return [
        p.device
        for p in list_ports.comports()
        if arduino_description in p.description
    ]

def send_data_to_arduino(arduino_port, baud_rate, data_dict):
    """
    Establishes a serial connection and sends JSON data.
    Returns (success_boolean, message)
    """
    try:
        # Step 5: Connect to the Arduino
        arduino = serial.Serial(arduino_port, baud_rate)
        
        # Step 6: Verify connection
        time.sleep(2)  # Wait for Arduino to initialize
        if not arduino.is_open:
            return False, "Failed to verify Arduino connection"

        # Step 7: Send JSON data
        data_string = json.dumps(data_dict)
        arduino.write(data_string.encode())

        # Step 8: Close connection
        arduino.close()
        return True, "Arduino connection verified and data sent."

    except Exception as e:
        error_msg = f"Failed to connect to Arduino: {str(e)}"
        logging.error(error_msg)
        return False, error_msg