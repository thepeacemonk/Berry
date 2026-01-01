# Berry Anki Add-on
# Cross-platform utility for finding connected Bluetooth devices.

import sys
import subprocess
import os
import json
import re
from typing import List, Dict, Any

def get_connected_devices() -> List[Dict[str, Any]]:
    """
    Detects connected Bluetooth devices based on the operating system.
    Returns a list of dictionaries, where each dictionary represents a device.
    """
    platform = sys.platform
    if platform == "darwin":  # macOS
        return get_macos_devices()
    elif platform == "win32":  # Windows
        return get_windows_devices()
    elif platform.startswith("linux"):  # Linux
        return get_linux_devices()
    else:
        print(f"Berry: Unsupported platform '{platform}'")
        return []

def get_windows_devices() -> List[Dict[str, Any]]:
    """
    Fetches connected Bluetooth devices on Windows using PnP (with aggressive filtering).
    """
    return get_windows_devices_pnp()

def get_windows_devices_winrt() -> List[Dict[str, Any]]:
    """
    Uses PowerShell and WinRT to get genuinely CONNECTED devices.
    """
    devices = []
    try:
        # PowerShell script using WinRT APIs
        # Protocol IDs:
        # {e0cbf06c-cd8b-4647-bb8a-263b43f0f974} = Bluetooth Classic
        # {bb7bb05e-5972-42b5-94fc-76eaa7084d49} = Bluetooth LE
        ps_script = """
        [Windows.Devices.Enumeration.DeviceInformation, Windows.Devices.Enumeration, ContentType=WindowsRuntime] | Out-Null
        $aqs = 'System.Devices.Aep.IsConnected:=System.StructuredQueryType.Boolean#True AND (System.Devices.Aep.ProtocolId:="{e0cbf06c-cd8b-4647-bb8a-263b43f0f974}" OR System.Devices.Aep.ProtocolId:="{bb7bb05e-5972-42b5-94fc-76eaa7084d49}")'
        $devices = [Windows.Devices.Enumeration.DeviceInformation]::FindAllAsync($aqs).GetAwaiter().GetResult()
        $devices | Select-Object Name, Id | ConvertTo-Json
        """
        
        cmd = ["powershell", "-Command", ps_script]
        
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=15, startupinfo=si, encoding='utf-8', errors='replace'
        )
        
        if not result.stdout.strip():
            return []

        data = json.loads(result.stdout)
        
        if isinstance(data, dict):
            data = [data]
            
        for device_info in data:
            name = device_info.get("Name")
            if name:
                devices.append({
                    "name": name,
                    "type": classify_device(name),
                    "address": device_info.get("Id", "N/A")
                })
                
    except Exception as e:
        print(f"Berry Error: WinRT discovery failed. {e}")
        # Could fallback here if needed
        
    return devices

def get_windows_devices_pnp() -> List[Dict[str, Any]]:
    """
    PnP method. Fetches actively connected Bluetooth devices.
    """
    devices = []
    try:
        # PowerShell command to get Bluetooth devices
        # NOTE: Windows PowerShell cannot reliably distinguish "paired" from "actively connected"
        # This will show all paired devices with Status = OK (which includes connected devices)
        # The aggressive filtering below removes system artifacts (RFCOMM, Services, etc.)
        cmd = [
            "powershell",
            "-Command",
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; Get-PnpDevice -Class 'Bluetooth' | Where-Object { $_.Status -eq 'OK' } | Select-Object FriendlyName, DeviceID | ConvertTo-Json"
        ]
        
        # startupinfo to prevent the console window from appearing
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=10, startupinfo=si, encoding='utf-8', errors='replace'
        )
        
        data = json.loads(result.stdout)
        
        # If there's only one device, it's not a list, so we make it one
        if isinstance(data, dict):
            data = [data]
            
        for device_info in data:
            name = device_info.get("FriendlyName")
            if name:
                # Filter out internal/service devices
                name_lower = name.lower()
                invalid_keywords = [
                    "enumerator", "enumerador", 
                    "avrcp", "a2dp", "hfp", "hands-free",
                    "le bluetooth", "le_bluetooth",
                    "rfcomm", "protocol", "tdi",
                    "service", "serviço",
                    "intel", "realtek", "qualcomm", "mediatek", # Adapters
                    "wireless bluetooth", "microsoft bluetooth",
                    "generic bluetooth", "oobe", "gatt", "endpoint", "generic",
                    "aadp", "iap", "spp"
                ]
                
                if any(keyword in name_lower for keyword in invalid_keywords):
                    continue
                    
                devices.append({
                    "name": name,
                    "type": classify_device(name),
                    "address": device_info.get("DeviceID", "N/A")
                })

    except FileNotFoundError:
        print("Berry Error: PowerShell is not available on this system.")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as e:
        print(f"Berry Error: Could not get devices on Windows. {e}")
    except Exception as e:
        print(f"Berry Error: An unexpected error occurred on Windows. {e}")
        
    return devices

def get_linux_devices() -> List[Dict[str, Any]]:
    """
    Fetches connected Bluetooth devices on Linux using bluetoothctl.
    """
    devices = []
    try:
        cmd = ["bluetoothctl", "devices", "Connected"]
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=10
        )
        
        output = result.stdout.strip()
        # Regex to capture MAC address and device name
        # e.g., Device 12:34:56:78:9A:BC My Bluetooth Keyboard
        pattern = re.compile(r"Device\s([0-9A-Fa-f:]{17})\s(.+)")
        
        for line in output.split('\n'):
            match = pattern.match(line)
            if match:
                address, name = match.groups()
                devices.append({
                    "name": name.strip(),
                    "type": classify_device(name),
                    "address": address.strip()
                })

    except FileNotFoundError:
        print("Berry Error: 'bluetoothctl' command not found. Please ensure bluez-utils is installed.")
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        print(f"Berry Error: Could not get devices on Linux. {e}")
    except Exception as e:
        print(f"Berry Error: An unexpected error occurred on Linux. {e}")

    return devices

def get_macos_devices() -> List[Dict[str, Any]]:
    """
    Fetches connected Bluetooth devices on macOS using system_profiler.
    """
    devices = []
    try:
        cmd = ["system_profiler", "SPBluetoothDataType", "-json"]
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=10
        )
        data = json.loads(result.stdout)
        
        bluetooth_sections = data.get("SPBluetoothDataType", [])
        if not bluetooth_sections:
            return []

        # Look for both legacy and current keys for connected devices
        connected_devices_list = (
            bluetooth_sections[0].get("device_connected", []) or
            bluetooth_sections[0].get("devices_connected", []) 
        )
        
        for device_dict in connected_devices_list:
            for device_name, device_info in device_dict.items():
                devices.append({
                    "name": device_name,
                    "type": classify_device(device_name),
                    "address": device_info.get("device_address", "N/A")
                })

    except Exception as e:
        print(f"Berry Error: Could not get devices via system_profiler. {e}")

    return devices

def classify_device(name: str) -> str:
    """A simple function to guess the device type from its name."""
    name_lower = name.lower()
    if "keyboard" in name_lower:
        return "keyboard"
    if "mouse" in name_lower or "trackpad" in name_lower:
        return "mouse"
    if "headphone" in name_lower or "headset" in name_lower or "buds" in name_lower or "airpods" in name_lower or "wh-1000xm5" in name_lower:
        return "headphone"
    if "controller" in name_lower or "gamepad" in name_lower:
        return "controller"
    if "imac" in name_lower or "macbook" in name_lower or "pc" in name_lower:
        return "computer"
    return "bluetooth" # Default icon
