#!/usr/bin/env python3
"""
WiFi Person Detector for Ubiquiti Multi-Floor, Multi-AP
"""

import yaml
import time
import logging
import random
from datetime import datetime, timedelta
from collections import defaultdict

# Load configuration
def load_config(config_path='config.yaml'):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

# Simulate getting signal strength from an AP
# In a real implementation, this would query the Ubiquiti AP via API or SSH
def get_signal_strength(ap):
    # Simulate RSSI value between -90 and -20 dBm
    # Person close to AP: -30 to -50
    # Person far: -70 to -90
    # No person: -90 to -100 (we'll simulate as -95)
    # For simulation, we'll randomly decide if a person is present near this AP
    # In reality, you'd replace this with actual AP data
    if random.random() < 0.3:  # 30% chance of person being near AP
        return random.randint(-50, -60)  # Strong signal
    else:
        return random.randint(-85, -95)  # Weak signal (no person)

def detect_person(config):
    aps = config['access_points']
    detection_settings = config['detection']
    min_aps = detection_settings['min_aps']
    time_window = detection_settings['time_window']
    cooldown = detection_settings['cooldown']
    
    # Track detection state per AP
    ap_states = defaultdict(dict)
    last_trigger = None
    
    logging.info("Starting person detection...")
    
    while True:
        current_time = datetime.now()
        detections_in_window = []
        
        # Check each AP
        for ap in aps:
            ap_name = ap['name']
            threshold = ap['threshold']
            
            # Get signal strength (simulate)
            rssi = get_signal_strength(ap)
            
            # Check if signal strength indicates person presence
            # Note: higher RSSI (less negative) means stronger signal
            detected = rssi > threshold
            
            if detected:
                detections_in_window.append({
                    'ap': ap_name,
                    'rssi': rssi,
                    'time': current_time,
                    'floor': ap['floor'],
                    'location': ap['location']
                })
                # Update AP state
                ap_states[ap_name] = {
                    'last_detection': current_time,
                    'detected': True,
                    'rssi': rssi
                }
                logging.debug(f"{ap_name}: Person detected (RSSI: {rssi} dBm)")
            else:
                # Update AP state
                ap_states[ap_name] = {
                    'last_detection': None,
                    'detected': False,
                    'rssi': rssi
                }
                logging.debug(f"{ap_name}: No person detected (RSSI: {rssi} dBm)")
        
        # Check if we have enough APs detecting a person
        if len(detections_in_window) >= min_aps:
            # Check cooldown
            if last_trigger is None or (current_time - last_trigger).total_seconds() > cooldown:
                logging.info(f"PERSON DETECTED! Triggered by {len(detections_in_window)} APs:")
                for det in detections_in_window:
                    logging.info(f"  - {det['ap']} ({det['floor']}/{det['location']}): {det['rssi']} dBm")
                
                # Here you would trigger your action (e.g., send notification, turn on light, etc.)
                # For now, just log
                last_trigger = current_time
            else:
                remaining_cooldown = cooldown - (current_time - last_trigger).total_seconds()
                logging.debug(f"Person detected but in cooldown ({remaining_cooldown:.0f}s remaining)")
        else:
            logging.debug(f"Not enough APs detecting person: {len(detections_in_window)}/{min_aps}")
        
        # Sleep for a short interval before next check
        time.sleep(5)

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler("wifi_detector.log"),
            logging.StreamHandler()
        ]
    )
    
    try:
        config = load_config()
        detect_person(config)
    except KeyboardInterrupt:
        logging.info("Detection stopped by user")
    except Exception as e:
        logging.error(f"Error in detection: {e}", exc_info=True)