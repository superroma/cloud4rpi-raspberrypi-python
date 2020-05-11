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


trigger = False
pouring = False
pulses = 0


def on_pulse():
    global pulses
    global trigger
    global pouring
    if pulses == 0:
        trigger = True
    pouring = True
    pulses = pulses + 1


def on_tick():
    if pouring and (pulses == 0):
        trigger = True
        pouring = False


last_call_sec = time()


def get_litres():
    if trigger:
        return 0

    global last_call_sec
    global pulses
    now_sec = time()
    liters = pulses / PULSE_PER_LITER
    liters_per_sec = liters / (now_sec - last_call_sec)
    last_call_sec = now_sec
    pulses = 0
    return liters_per_sec


def main():
    ds18b20.init_w1()
    ds_sensors = ds18b20.DS18b20.find_all()
    button = Button(17)
    button.when_pressed = on_pulse

    # Put variable declarations here
    # Available types: 'bool', 'numeric', 'string', 'location'
    variables = {
        "Cellar Temp": {
            "type": "numeric" if ds_sensors else "string",
            "bind": ds_sensors[0] if ds_sensors else sensor_not_connected,
        },
        "Liters/Sec": {"type": "numeric", "bind": get_litres},
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
        global started
        while True:
            on_tick()
            if (data_timer <= 0) or trigger:
                print("trigger")
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
