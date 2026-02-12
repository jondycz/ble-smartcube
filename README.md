# BLE Smart Cube

Home Assistant integration for Bluetooth smart cubes.

## Supported cubes

| Brand | Model family | Supported | Tested |
| --- | --- | --- | --- |
| Giiker | Gi / Hi- / HiG | ✅ | ✅ |
| GoCube | GoCube / Rubiks | ✅ | ❌ |
| GAN | GAN / MG / AiCube | ✅ | ❌ |
| QiYi | QY-QYSC / XMD-TornadoV4-i | ✅ | ❌ |

Giiker is the only tested cube so far.

This project started as a fast experiment, so there may be rough edges.

If you hit issues with other cubes, pull requests are welcome.

## How it works

The integration uses Home Assistant's Bluetooth stack to listen for cube advertisements and establish BLE connections when needed.

Once connected, it subscribes to notifications and parses move/state data into sensors and events.

An Auto-Connect switch lets you disable connections when you want to play without Home Assistant.

## HACS

If you have HACS installed, add this repository (jondycz/ble-smartcube) as a custom repository of type "Integration".

See https://hacs.xyz/docs/faq/custom_repositories/

## Usage notes

- Keep Auto-Connect enabled if you want the cube to reconnect on wake/advertise.
- Turn Auto-Connect off to stop connecting and disconnect the cube.
