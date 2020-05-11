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
    beer_line = beer_lines[input.pin.number]
    if beer_line:
        if beer_line["pulses"] == 0:
            trigger = True
            beer_line["lps"] = 0
            beer_line["last_time"] = time()
        beer_line["pouring"] = True
        beer_line["pulses"] = beer_line["pulses"] + 1


def on_tick():
    global beer_lines
    global trigger
    any_line_pouring = False
    for k, beer_line in beer_lines.items():
        if beer_line["pouring"]:
            any_line_pouring = True
            if beer_line["pulses"] == 0:
                trigger = True
                beer_line["pouring"] = False
                beer_line["lps"] = 0
                beer_line["last_time"] = time()
    return any_line_pouring


def calc_values():
    global beer_lines
    global trigger

    if trigger:
        return

    for k, beer_line in beer_lines.items():
        now_sec = time()
        liters = beer_line["pulses"] / PULSE_PER_LITER
        beer_line["liters"] = beer_line["liters"] + liters
        beer_line["lps"] = liters / (now_sec - beer_line["last_time"])
        beer_line["last_time"] = now_sec
        beer_line["pulses"] = 0
        print(beer_line)


def get_val(key):
    def get_key(pin_number):
        def get_key_pin():
            global beer_lines
            return beer_lines[pin_number][key]

        return get_key_pin

    return get_key


def main():
    global beer_lines
    global trigger

    ds18b20.init_w1()
    ds_sensors = ds18b20.DS18b20.find_all()

    for k, v in beer_lines.items():
        button = Button(k)
        button.when_pressed = on_pulse

    # Put variable declarations here
    # Available types: 'bool', 'numeric', 'string', 'location'
    variables = {
        "Cellar Temp": {
            "type": "numeric" if ds_sensors else "string",
            "bind": ds_sensors[0] if ds_sensors else sensor_not_connected,
        },
        "lps1": {"type": "numeric", "bind": get_val("lps")(17)},
        "lps2": {"type": "numeric", "bind": get_val("lps")(18)},
        "liters1": {"type": "numeric", "bind": get_val("liters")(17)},
        "liters2": {"type": "numeric", "bind": get_val("liters")(18)},
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
        while True:
            pouring = on_tick()
            if (data_timer <= 0) or trigger or pouring:
                print("trigger: ", trigger, "pouring: ", pouring)
                calc_values()
                if trigger:
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
        print("ERRORRRRR", e)
    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
