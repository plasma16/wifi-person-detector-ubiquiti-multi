#!/usr/bin/env python3
"""
WiFi Person Detector for Ubiquiti Multi-Floor, Multi-AP
With auto-discovery of gateway and Ubiquiti access points.
"""

import yaml
import time
import logging
import random
import subprocess
import re
import socket
from datetime import datetime, timedelta
from collections import defaultdict
import ipaddress

# Load configuration
def load_config(config_path='config.yaml'):
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def get_gateway_ip():
    """Get the default gateway IP address."""
    try:
        output = subprocess.check_output(['ip', 'route', 'show', 'default'], stderr=subprocess.STDOUT, universal_newlines=True)
        # Example: default via 192.168.1.1 dev eth0  proto dhcp  src 192.168.1.100  metric 100
        match = re.search(r'default via (\S+)', output)
        if match:
            return match.group(1)
    except Exception as e:
        logging.debug(f"Could not get gateway IP: {e}")
    return None

def get_local_subnet(gateway_ip):
    """Determine the local subnet from gateway IP and interface."""
    try:
        # Get interface for the gateway
        output = subprocess.check_output(['ip', 'route', 'show', 'default'], stderr=subprocess.STDOUT, universal_newlines=True)
        # default via 192.168.1.1 dev eth0 ...
        match = re.search(r'default via \S+ dev (\S+)', output)
        if match:
            iface = match.group(1)
            # Get IP address and netmask for that interface
            output = subprocess.check_output(['ip', '-f', 'inet', 'addr', 'show', iface], stderr=subprocess.STDOUT, universal_newlines=True)
            # inet 192.168.1.100/24 brd 192.168.1.255 scope global dynamic eth0
            match = re.search(r'inet (\S+)', output)
            if match:
                ip_with_mask = match.group(1)
                # ipaddress module can give us the network
                network = ipaddress.IPv4Network(ip_with_mask, strict=False)
                return str(network)
    except Exception as e:
        logging.debug(f"Could not determine subnet: {e}")
    return None

def arp_scan(network):
    """Scan the network for devices using arp (read from /proc/net/arp or arp -n)."""
    devices = []  # list of (ip, mac)
    try:
        # Try to read /proc/net/arp first (doesn't require root)
        with open('/proc/net/arp', 'r') as f:
            lines = f.readlines()[1:]  # skip header
            for line in lines:
                parts = line.split()
                if len(parts) >= 6:
                    ip_addr = parts[0]
                    mac_addr = parts[3]
                    if mac_addr != '00:00:00:00:00:00' and not ip_addr.endswith('.255') and not ip_addr.endswith('.0'):
                        devices.append((ip_addr, mac_addr))
    except Exception:
        # Fallback to arp -n
        try:
            output = subprocess.check_output(['arp', '-n'], stderr=subprocess.STDOUT, universal_newlines=True)
            for line in output.splitlines()[1:]:  # skip header
                parts = line.split()
                if len(parts) >= 3:
                    ip_addr = parts[0]
                    mac_addr = parts[2]
                    if mac_addr != '00:00:00:00:00:00' and not ip_addr.endswith('.255') and not ip_addr.endswith('.0'):
                        devices.append((ip_addr, mac_addr))
        except Exception as e:
            logging.debug(f"ARP scan failed: {e}")
    return devices

def is_ubiquiti_mac(mac):
    """Check if MAC address belongs to Ubiquiti (based on known OUI)."""
    oui = mac.upper().replace(':', '')[:6]  # first 6 hex chars
    # Ubiquiti OUI list (from https://linuxnet.ca/ieee/oui.txt)
    ubiquiti_ouis = {
        '00156D',  # Ubiquiti Networks Inc.
        '002722',  # Ubiquiti Networks Inc.
        '0418D6',  # Ubiquiti Networks Inc.
        '2CB05D',  # Ubiquiti Networks Inc.
        '6CF37F',  # Ubiquiti Networks Inc.
        '74ACB9',  # Ubiquiti Networks Inc.
        '802AA8',  # Ubiquiti Networks Inc.
        '880355',  # Ubiquiti Networks Inc.
        '881544',  # Ubiquiti Networks Inc.
        '90640D',  # Ubiquiti Networks Inc.
        '9483C4',  # Ubiquiti Networks Inc.
        'B4FBF4',  # Ubiquiti Networks Inc.
        'C46E1F',  # Ubiquiti Networks Inc.
        'CC1DC2',  # Ubiquiti Networks Inc.
        'D4CA6D',  # Ubiquiti Networks Inc.
        'E4D53D',  # Ubiquiti Networks Inc.
        'F09FC2',  # Ubiquiti Networks Inc.
        'F4F26D',  # Ubiquiti Networks Inc.
        'F8F10F',  # Ubiquiti Networks Inc.
        'FCECDA',  # Ubiquiti Networks Inc.
    }
    return oui in ubiquiti_ouis

def discover_aps():
    """Discover Ubiquiti access points on the local network."""
    gateway = get_gateway_ip()
    if not gateway:
        logging.warning("Could not determine gateway IP")
        return []
    
    subnet = get_local_subnet(gateway)
    if not subnet:
        logging.warning("Could not determine local subnet")
        return []
    
    logging.info(f"Discovering Ubiquiti APs on subnet {subnet} via gateway {gateway}")
    
    devices = arp_scan(subnet)
    aps = []
    for ip, mac in devices:
        if is_ubiquiti_mac(mac):
            # Generate a name based on last part of IP or MAC
            name = f"UBNT-{mac.replace(':', '')[-6:]}"
            aps.append({
                'name': name,
                'mac': mac,
                # We don't know floor/location from discovery; leave as empty or default
                'floor': 'unknown',
                'location': 'unknown',
                # We'll keep threshold configurable; maybe default -70
                'threshold': -70  # will be overridden if config provides per-AP threshold
            })
            logging.info(f"Discovered Ubiquiti AP: {name} ({mac}) at {ip}")
    
    if not aps:
        logging.warning("No Ubiquiti APs discovered via ARP scan")
    
    return aps

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
        return random.randint(-60, -50)  # Strong signal
    else:
        return random.randint(-95, -85)  # Weak signal (no person)

def detect_person(config):
    # Use discovered APs if not provided in config, else use config
    if 'access_points' not in config or not config['access_points']:
        logging.info("No access points in config, attempting auto-discovery...")
        aps = discover_aps()
        if not aps:
            logging.error("No access points discovered and none in config. Exiting.")
            return
    else:
        aps = config['access_points']
    
    detection_settings = config['detection']
    min_aps = detection_settings['min_aps']
    time_window = detection_settings['time_window']
    cooldown = detection_settings['cooldown']
    
    # Track detection state per AP
    ap_states = defaultdict(dict)
    last_trigger = None
    
    logging.info(f"Starting person detection with {len(aps)} access points...")
    
    while True:
        current_time = datetime.now()
        detections_in_window = []
        
        # Check each AP
        for ap in aps:
            ap_name = ap['name']
            # Use threshold from AP config, fallback to -70
            threshold = ap.get('threshold', -70)
            
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
                    'floor': ap.get('floor', 'unknown'),
                    'location': ap.get('location', 'unknown')
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