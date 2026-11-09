"""Names for common AVL IO element IDs on FMB/FMC/FMM devices.

Only well-known, model-independent IDs are listed. Many IDs (CAN, FMS, BLE,
tachograph) depend on the device model and configuration, so check the AVL ID
list for your device on the Teltonika wiki before trusting a name.
"""

IO_NAMES = {
    1: "Digital Input 1",
    2: "Digital Input 2",
    3: "Digital Input 3",
    9: "Analog Input 1",
    11: "ICCID1",
    12: "Fuel Used GPS",
    13: "Fuel Rate GPS",
    14: "ICCID2",
    16: "Total Odometer",
    17: "Axis X",
    18: "Axis Y",
    19: "Axis Z",
    21: "GSM Signal",
    24: "Speed",
    66: "External Voltage",
    67: "Battery Voltage",
    68: "Battery Current",
    69: "GNSS Status",
    80: "Data Mode",
    113: "Battery Level",
    179: "Digital Output 1",
    180: "Digital Output 2",
    181: "GNSS PDOP",
    182: "GNSS HDOP",
    199: "Trip Odometer",
    200: "Sleep Mode",
    205: "GSM Cell ID",
    206: "GSM Area Code",
    239: "Ignition",
    240: "Movement",
    241: "Active GSM Operator",
    246: "Towing",
    247: "Crash Detection",
    249: "Jamming",
    250: "Trip",
    251: "Idling",
    252: "Unplug",
    253: "Green Driving Type",
    254: "Green Driving Value",
    255: "Over Speeding",
}


def io_name(io_id: int) -> str:
    return IO_NAMES.get(io_id, f"IO {io_id}")
