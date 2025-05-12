This is python bot for meshtastic. Used to measure signal strength using ping and send messages.

![Usage example](https://raw.githubusercontent.com/OH1KK/Meshtastic-mesh-replier/refs/heads/main/mesh_replier.jpg)

## Install

Python depencies
````
pip install meshtatic pyserial
````

Start this on your home node.

```
git clone https://github.com/OH1KK/Meshtastic-mesh-replier.git
cd Meshtastic-mesh-replier
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

### Sending messages

mesh-replier.py sets http listener to port 8080 and listens for message requests.

Sending message to channel

```
curl "http://192.168.1.123:8080/?ch_index=0&sendtext=Testing%201234"
```

Sending message to single node

```
curl "http://wg-meshtastic2.intra.vy.fi:8080/?dest=ea0a0b88&sendtext=Testing%201234"
```



