#!/usr/bin/python3

import time
import meshtastic
import meshtastic.serial_interface
from pubsub import pub
import datetime
import binascii

def onReceive(packet, interface):  # called when a packet arrives
    now = datetime.datetime.now()
    #print(f"{now} received: {packet}")
   
    pFrom = packet['from']
    pTo = packet['to']
    
    # Check if packet was received directly or relayed
    hop_start = packet.get('hopStart', 0)
    hop_limit = packet.get('hopLimit', 0)
    relay_node = packet.get('relayNode', 0)
    
    if hop_start == hop_limit:
        print(f"Packet received directly from {pFrom:x} (relayNode: {relay_node:x})")
        relay_info = "direct"
    else:
        print(f"Packet relayed, from {pFrom:x}, relayNode: {relay_node} (0x{relay_node:x})")
        relay_info = f"relayed via {relay_node:x}"

    if pTo == interface.myInfo.my_node_num:
        print(f"Packet is for me! It's from {pFrom:x}")
        # Decode payload and check portnum
        portnum = packet['decoded'].get('portnum', 'UNKNOWN')
        payload = packet['decoded'].get('payload', b'')
        print(f"Portnum: {portnum}, Payload (hex): {binascii.hexlify(payload).decode()}")
        
        # Check for ping (case-sensitive by default)
        if portnum == 'TEXT_MESSAGE_APP' and payload == b'ping':  # Use b'ping' for byte string comparison
            # Format timestamp to show only seconds
            timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
            msg = f"pong {timestamp}. rxSNR {packet['rxSnr']} dB RSSI {packet['rxRssi']} dBm ({relay_info})"
            print(f"It's a ping packet. Replying with {msg}")
            interface.sendText(msg, destinationId=pFrom, wantAck=False, wantResponse=False)
        else:
            # Optional: Case-insensitive ping check (uncomment to enable)
            # if portnum == 'TEXT_MESSAGE_APP' and payload.lower() == b'ping':
            #     timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
            #     msg = f"pong {timestamp}. rxSNR {packet['rxSnr']} dB RSSI {packet['rxRssi']} dBm ({relay_info})"
            #     print(f"It's a ping packet (case-insensitive). Replying with {msg}")
            #     interface.sendText(msg, destinationId=pFrom, wantAck=True, wantResponse=False)
            # else:
            print(f"Packet is not ping packet, payload: {payload}, ignoring")

def onConnection(interface, topic=pub.AUTO_TOPIC):  # called when connection is established
    print(f"Connected to radio. My node ID: {interface.myInfo.my_node_num} (0x{interface.myInfo.my_node_num:x})")
    print("Waiting for messages")

# Subscribe to connection and receive events
pub.subscribe(onReceive, "meshtastic.receive")
pub.subscribe(onConnection, "meshtastic.connection.established")

# Initialize serial interface
try:
    interface = meshtastic.serial_interface.SerialInterface(devPath='/dev/ttyUSB0')
except Exception as e:
    print(f"Failed to connect to radio: {e}")
    exit(1)

try:
    while True:
        time.sleep(1)  # Keep the script running with a shorter sleep
except KeyboardInterrupt:
    print("Shutting down...")
    interface.close()  # Close the interface only on exit
