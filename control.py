# -*- coding: utf-8 -*-

from time import sleep, time
from os import environ
from gpiozero import Button
import sys
import cloud4rpi
import ds18b20
import rpi

# Put your device token here. To get the token,
# sign up at https://cloud4rpi.io and create a device.
DEVICE_TOKEN = environ.get("C4R_TOKEN")

# Constants

DATA_SENDING_INTERVAL = 60  # secs
DIAG_SENDING_INTERVAL = 3600  # secs
POLL_INTERVAL = 0.5  # 500 ms

PULSE_PER_LITER = 500


def sensor_not_connected():
    return "Sensor not connected"


# Globals
trigger = False
beer_lines = {
    17: {"pulses": 0, "pouring": False, "liters": 0, "lps": 0, "last_time": time(),},
    18: {"pulses": 0, "pouring": False, "liters": 0, "lps": 0, "last_time": time(),},
}


def on_pulse(input):
    global beer_lines
    global trigger
    beer_line = beer_lines[input.pin]
    if beer_line:
        if beer_line["pulses"] == 0:
            trigger = True
            beer_line["lps"] = 0
            beer_line["last_time"] = time()
        beer_line["pouring"] = True
        beer_line["pulses"] = beer_line["pulses"] + 1


def on_tick():
    global trigger
    global beer_lines
    for k, beer_line in beer_lines.items():
        if beer_line["pouring"] and (beer_line["pulses"] == 0):
            trigger = True
            beer_line["pouring"] = False
            beer_line["lps"] = 0
            beer_line["last_time"] = time()


def calc_values():
    if trigger:
        return

    global beer_lines
    for k, beer_line in beer_lines.items():
        now_sec = time()
        liters = pulses / PULSE_PER_LITER
        beer_line["liters"] = beer_line["liters"] + liters
        beer_line["lps"] = liters / (now_sec - beer_line["last_time"])
        beer_line["last_time"] = now_sec
        beer_line["pulses"] = 0


def main():
    ds18b20.init_w1()
    ds_sensors = ds18b20.DS18b20.find_all()
    for k, v in beer_lines:
        button = Button(k)
        button.when_pressed = on_pulse

    # Put variable declarations here
    # Available types: 'bool', 'numeric', 'string', 'location'
    variables = {
        "Cellar Temp": {
            "type": "numeric" if ds_sensors else "string",
            "bind": ds_sensors[0] if ds_sensors else sensor_not_connected,
        },
        "lps1": {"type": "numeric", "bind": beer_lines[17]["lps"]},
        "lps2": {"type": "numeric", "bind": beer_lines[18]["lps"]},
        "liters1": {"type": "numeric", "bind": beer_lines[17]["liters"]},
        "liters2": {"type": "numeric", "bind": beer_lines[18]["liters"]},
    }

    diagnostics = {
        "CPU Temp": rpi.cpu_temp,
        "IP Address": rpi.ip_address,
        "Host": rpi.host_name,
        "Operating System": rpi.os_name,
        "Client Version:": cloud4rpi.__version__,
    }
    device = cloud4rpi.connect(DEVICE_TOKEN)

    # Use the following 'device' declaration
    # to enable the MQTT traffic encryption (TLS).
    #
    # tls = {
    #     'ca_certs': '/etc/ssl/certs/ca-certificates.crt'
    # }
    # device = cloud4rpi.connect(DEVICE_TOKEN, tls_config=tls)

    try:
        device.declare(variables)
        device.declare_diag(diagnostics)

        device.publish_config()

        # Adds a 1 second delay to ensure device variables are created
        sleep(1)

        data_timer = 0
        diag_timer = 0
        global trigger
        while True:
            on_tick()
            if (data_timer <= 0) or trigger:
                print("trigger:", trigger)
                trigger = False
                device.publish_data()
                data_timer = DATA_SENDING_INTERVAL

            if diag_timer <= 0:
                device.publish_diag()
                diag_timer = DIAG_SENDING_INTERVAL

            sleep(POLL_INTERVAL)
            diag_timer -= POLL_INTERVAL
            data_timer -= POLL_INTERVAL

    except KeyboardInterrupt:
        cloud4rpi.log.info("Keyboard interrupt received. Stopping...")

    except Exception as e:
        error = cloud4rpi.get_error_message(e)
        cloud4rpi.log.exception("ERROR! %s %s", error, sys.exc_info()[0])

    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
