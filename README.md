This is a heviliy modified version of [https://github.com/Marx1/Meshtastic-mesh-replier-Local/](https://github.com/OH1KK/Meshtastic-mesh-replier/) 's great bot. 


This is python bot for meshtastic intended to run on raspberry pi. Bot can be used to measure signal strength using ping, show telemetry and position data from nodes and send messages to channels/nodes.

## What this bot does

This bot listens for a direct (0-hop) message, and auto DMs them two specific messages instructing them how to get on the event mesh, and how to join the the local mesh after the event. It also saves the node ID so it doesn't re-spam the user.

This was made for Pacificon 2025 in San Ramon, CA. The SF Bay area is on Medium Slow (for the most part)

## Radio setup
I set my radio up this way to prevent spamming outaide of the physically local mesh:

- max hops 0
- unchecked ok to mqtt
- checked ignore ok to mqtt
- station is Client_Mute
- turned off all telemetry
- set node info to 600 (we want people to see this node name in thier list when they get the DM, and to get the key exchange)
- Adjust TX power down as needed to keep it local (10dbm should be more than enough)
- Locate the device indoors.


## Install

Python depencies
````
pip install meshtatic pyserial
````

Start this on your home node.

```
git clone https://github.com/Marx1/Meshtastic-mesh-replier-Local.git
cd Meshtastic-mesh-replier-Local
chmod +x mesh-replier.py
```

## Starting

```
./mesh-replier.py
```

You should see messages

```
Connected to radio. My node ID: 1129887680 (0x4358b7c0)
Waiting for messages
```

and then you should se messages received from radio. There are messages, telemetry, position reports. They are visible on screen as they arrives. Same data is also logged into /tmp/mesh-replier.log

## Usage

Then send 'ping' message from another node to your node.

If your node hears it, it replies

```
pong 2025-05-11 15:06:46. rxSNR 6.25 dB RSSI -63 dBm (direct)
```

and if packet is relayed through another node then you see reply like

```
pong 2025-05-11 15:07:53. rxSNR 6.5 dB RSSI -30 dBm (relayed via 24)
```

# Words of warning/Notes

- This bot was written down-and-dirty. it works, and everything is hard coded. 
- If you want to change the text, start looking  at lines 365. 
- If you want to run more than one, you'll need to modify the code to write to two diffrent node dbs (line 39), and select the correct device.
- Do not bug OH1KK about this script. I modified it and cut a lot of thier features out. If you want anything outside of these features, use thier bot.
