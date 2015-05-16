__author__ = 'ayzen'


import sys
import logging
import requests
from time import sleep

import config


ROUTER_AUTH = (config.ROUTER_USER, config.ROUTER_PASSWORD)

URL_ROUTER_DHCP_LEASES = config.ROUTER_HOST + "/getdhcpLeaseInfo.asp"

URL_SYNOLOGY_API = config.SYNOLOGY_HOST + "/webapi/"

API_INFO = "SYNO.API.Info"
API_AUTH = "SYNO.API.Auth"
API_EMAIL = "SYNO.SurveillanceStation.Notification.Email"

synology_sid = None


def request_wifi_devices():
    logging.debug("Pulling Wi-Fi devices from router")
    return requests.get(URL_ROUTER_DHCP_LEASES, auth=ROUTER_AUTH).text


def if_any_known_device_connected(connected_devices):
    return any(mac in connected_devices for mac in config.KNOWN_DEVICES)


def request_synology(path, api, method, version, **kwargs):
    if synology_sid is not None:
        kwargs["_sid"] = synology_sid
    kwargs["path"] = path
    kwargs["api"] = api
    kwargs["method"] = method
    kwargs["version"] = version

    result = requests.get(URL_SYNOLOGY_API + path, params=kwargs)

    if result.status_code != requests.codes.ok or not result.json()["success"]:
        code = None
        json = result.json()
        if "error" in json and "code" in json["error"]:
            code = json["error"]["code"]
        raise Exception("Error while requesting Synology server: code=" + str(result.status_code) + "; " + result.text,
                        code)

    return result.json()["data"] if "data" in result.json() else None


def query_synology_api(api_name):
    return request_synology("query.cgi", API_INFO, "Query", 1, query=api_name)[api_name]


def login_synology():
    auth_info = query_synology_api(API_AUTH)
    auth_result = request_synology(auth_info["path"], API_AUTH, "Login", auth_info["maxVersion"], account="admin",
                                   passwd="fnautsynology")

    global synology_sid
    synology_sid = auth_result["sid"]


def logout_synology():
    auth_info = query_synology_api(API_AUTH)
    request_synology(auth_info["path"], API_AUTH, "Logout", auth_info["maxVersion"])

    global synology_sid
    synology_sid = None


def set_synology_email_notification(enable):
    logging.debug("Sending requests to Synology to control email notifications")
    try:
        login_synology()

        email_info = query_synology_api(API_EMAIL)
        path = email_info["path"]
        version = email_info["maxVersion"]
        request_synology(path, API_EMAIL, "SetSetting", version, mailEnable=enable, mailMethod=1 if enable else 0)

        logout_synology()
    except Exception as ex:
        code = ex.args[1]

        if code == 119:
            logging.warning("Got that strange Synology error #119. Repeating request after 5 seconds...")
            sleep(5)
            set_synology_email_notification(enable)
        else:
            raise ex


def main_loop():
    logging.info("Starting the main loop")
    notifications_enabled = None

    while True:
        try:
            devices = request_wifi_devices()
            found_connected_device = if_any_known_device_connected(devices)

            logging.debug("Found connected known device" if found_connected_device else "Known devices are not found")

            should_enable_notifications = not found_connected_device
            if notifications_enabled != should_enable_notifications:
                logging.info("%sing Synology email notifications for all events",
                             "Enabl" if should_enable_notifications else "Disabl")
                set_synology_email_notification(should_enable_notifications)
                notifications_enabled = should_enable_notifications
            else:
                logging.debug("Synology email notifications are already %sed",
                              "enabl" if notifications_enabled else "disabl")

            sleep(5)
        except Exception:
            logging.exception("Exception happened, will wait 90 seconds")
            sleep(90)


logging.getLogger("requests").setLevel(logging.WARNING)
logging.basicConfig(stream=sys.stdout, format="%(asctime)s [%(name)-10.10s] [%(levelname)-5.5s]  %(message)s",
                    level=logging.DEBUG if config.DEBUG else logging.INFO)

main_loop()
