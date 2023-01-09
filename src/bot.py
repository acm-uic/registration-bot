#!/usr/bin/env python3

import websocket
import string
import requests
import json
import threading
import ctypes
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from time import time,sleep
from yaml import safe_load
from os import environ
from dotenv import load_dotenv
from typing import NamedTuple
from signal import signal,SIGINT,SIGTERM

users_created = 0;
last_update = 0;
failed_interactions = 0;
failed_db_updates = 0;

class LivenessAndMetrics(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/livez":
            ok = (time() - last_update) < 120
            self.send_response(200 if ok else 500)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(bytes('ok' if ok else 'failing', "utf-8"))
        elif self.path == "/metrics":
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(bytes("# HELP registration_bot_users_created Number of users created by current process.\n", "utf-8"))
            self.wfile.write(bytes("# TYPE registration_bot_users_created counter\n", "utf-8"))
            self.wfile.write(bytes(f"registration_bot_users_created {users_created}\n", "utf-8"))
            self.wfile.write(bytes("# HELP registration_bot_last_update The last update received over the gateway.\n", "utf-8"))
            self.wfile.write(bytes("# TYPE registration_bot_last_update gauge\n", "utf-8"))
            self.wfile.write(bytes(f"registration_bot_last_update {last_update}\n", "utf-8"))
            self.wfile.write(bytes("# HELP registration_bot_failed_interactions Number of failed discord interaction responses.\n", "utf-8"))
            self.wfile.write(bytes("# TYPE registration_bot_failed_interactions counter\n", "utf-8"))
            self.wfile.write(bytes(f"registration_bot_failed_interactions {failed_interactions}\n", "utf-8"))
            self.wfile.write(bytes("# HELP registration_bot_failed_db_updates Number of failed Notion database updates.\n", "utf-8"))
            self.wfile.write(bytes("# TYPE registration_bot_failed_db_updates counter\n", "utf-8"))
            self.wfile.write(bytes(f"registration_bot_failed_db_updates {failed_db_updates}\n", "utf-8"))
        else:
            self.send_response(404)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(bytes("<html><head><title>Page not found!</title></head><body><h1>404 Page Not Found</h1></body></html>", "utf-8"))

class Options(NamedTuple):
    """ Options structure

    Parameters
    ----------
    api_url : str The api url with version client_id : str
        The discord bot client id
    token : str
        The discord bot token
    notion_token : str
        The notion api token
    notion_database : str
        The notion database id
    metrics_host : str
        The host to listen on for metrics and liveness endpoints
    port : int
        The port to listen on for metrics and liveness endpoints
    gateway : str
        The websocket gateway
    """
    api_url: str
    client_id: str
    token: str
    notion_token: str
    notion_database: str
    metrics_host: str = "localhost"
    port: int = 8080
    debug: bool = False
    gateway: str = "wss://gateway.discord.gg/?v=10&encoding=json"

class Bot(threading.Thread):

    def __init__(self, opts: Options):
        """ Initialize the bot class
        
        Parameters
        ----------
        opts : Options
            The options object
        """
        threading.Thread.__init__(self)
        self.latest_seq = 0
        self.opts = opts
        self.auth_header = {'Authorization': f"Bot {opts.token}", 'Content-Type': 'application/json'}
        self.identify = {'op': 2, 'd': {
            'token': opts.token,
            'intents': 513,
            'properties': {
                'os': 'linux',
                'browser': 'acm-bot',
                'device': 'acm-bot'
                }
            }}
    
    def run(self):
        self.last_ack = time()
        self.sock = websocket.WebSocketApp(self.opts.gateway,
                    on_message = lambda ws,msg: self.message_handler(ws, msg),
                    on_close   = lambda ws, code, msg:     self.on_close(ws, code, msg),
                    on_error   = lambda err:    print(err),
                    on_open    = lambda ws:     self.on_open(ws))
        self.sock.run_forever()

    def update_slash_cmds(self, filename: str, opts: Options):
        """ Updates slash commands

        Parameters
        ----------
        filename : str
            The file to load commands from
        opts: Options
            The options object
        """
        f = open(filename, 'r')
        commands = safe_load(f)["commands"]
        for command in commands:
            r = requests.post(f"{opts.api_url}/applications/{opts.client_id}/commands", headers=self.auth_header, json=command)
            r.raise_for_status()

    def register_user(self, interaction_id: str, interaction_token: str, options: dict, discord_id: str):
        """ Registers user with AD

        Parameters
        ----------
        options : dict
            The options dictionary from the discord interation
            https://discord.com/developers/docs/interactions/application-commands#slash-commands-example-slash-command
        discord_id : str
            The Discord id of the user
        """
        notion = Notion(self.opts.notion_token, self.opts.notion_database, self.opts.debug)
        notion.create_user(options[1]['value'], options[2]['value'], options[0]['value'], options[4]['value'] if len(options) > 4 else '', options[3]['value'], discord_id)
        r = requests.post(f"{self.opts.api_url}/interactions/{interaction_id}/{interaction_token}/callback", json={'type': 4, 'data': {'content': "You have been registered!", "flags": 64}})
        if r.status_code > 299:
            global failed_interactions
            failed_interactions += 1
            print(f"Failed to respond to interation: Code: {r.status_code} Error: {r.text}")

    def message_handler(self, ws, msg: str):
        """ Handles gateway events

        Parameters
        ----------
        msg : str
            The gateway message
        """
        if self.opts.debug:
            print(msg)
        global last_update
        last_update = time()
        msg = json.loads(msg)
        data = msg.get('d')
        if data != False and data != None:
            self.latest_seq = data.get('s')
        if msg['op'] == 0:
            t = msg['t']
            if t == "READY":
                print("Application Registered")
            elif t == "INTERACTION_CREATE" and data['type'] == 2:
                #asyncio.create_task(self.register_user(data['id'], data['token'], data['data']['options'], data['member']['user']['id']))
                x = threading.Thread(target=self.register_user, args=(data['id'], data['token'], data['data']['options'], data['member']['user']['id']))
                x.start()
        elif msg['op'] == 1:
            self.sock.send(json.dumps({'op': 1, 'd': self.latest_seq}))
        elif msg['op'] == 9:
            # We have been killed, f
            exit(-1)
        elif msg['op'] == 10:
            self.sock.send(json.dumps(self.identify))
            #asyncio.create_task(self.__heartbeat(msg['d']['heartbeat_interval']))
            x = threading.Thread(target=self.__heartbeat, args=(msg['d']['heartbeat_interval'],))
            x.start()
            self.last_ack = time()
        elif msg['op'] == 11:
            self.last_ack = time()


    def on_open(self, ws):
        """ Connect to api gateway

        Parameters
        ----------
        ws : websocket
            The active websocket
        """
        
        print("Starting Discord Bot...")
        self.latest_seq = 0
        self.last_ack = 0

    def on_close(self, ws, code, msg):
        """ Shutdown Discord Bot
        """
        print(f"Bot WS Closed with Code: {code}")

    def shutdown(self):
        print("Shutting Down WS...")
        def run(*args):
            self.sock.close()

        threading.Thread(target=run).start()
    
    def __heartbeat(self, interval: int):
        """Refresh the websocket after each interval passes
        
        Parameters
        ----------
        interval : int
            The heartbeat interval
        """
        interval_s = interval / 1000
        while True:
            sleep(interval_s)
            if (time() - self.last_ack) > interval_s*2:
                exit(-1)
            self.sock.send(json.dumps({'op': 1, 'd': self.latest_seq}))

class Notion:
    def __init__(self, token: str, database: str, debug: bool = False):
        """ Initialize the Notion class
        
        Parameters
        ----------
        token : str
            The notion api key
        database : str
            The notion database id
        debug : bool
            Whether to use debug output
        """
        self.token = token
        self.database = database
        self.auth_header = {'Authorization': f"Bearer {token}", 'Content-Type': 'application/json', 'Notion-Version': '2022-06-28'}

    def create_user(self, first_name: str, last_name: str, netid: str, national_id: str, email: str, discord_id: str):
        """ Create a user database item

        Parameters
        ----------
        first_name : str
            The user's first name
        last_name : str
            The user's last name
        netid : str
            The user's netid
        national_id : str
            The user's national acm ID
        email : str
            The user's email
        discord_id : str
            The discord id of the user
        """

        page = {
                "parent": {
                    "database_id": self.database
                    },
                "properties": {
                    "Netid": {
                        "type": "title",
                        "title": [{"type": "text", "text": {"content": netid}}]
                        },
                    "First Name": {
                        "type": "rich_text",
                        "rich_text": [{"type": "text", "text": {"content": first_name}}]
                        },
                    "Last Name": {
                        "type": "rich_text",
                        "rich_text": [{"type": "text", "text": {"content": last_name}}]
                        },
                    "Email": {
                        "type": "rich_text",
                        "rich_text": [{"type": "text", "text": {"content": email}}]
                        },
                    "ACM National ID": {
                        "type": "rich_text",
                        "rich_text": [{"type": "text", "text": {"content": national_id}}]
                        },
                    "Discord ID": {
                        "type": "rich_text",
                        "rich_text": [{"type": "text", "text": {"content": discord_id}}]
                        },
                    }
                }

        r = requests.post("https://api.notion.com/v1/pages", headers=self.auth_header, json=page)
        if r.status_code > 299:
            global failed_db_updates
            failed_db_updates += 1
            print("Failed to update notion database with data: {first_name} {last_name} {email} {netid} {national_id} {discord_id}\nCode: {r.status_code}\nError: {r.text}")
        else:
            global users_created
            users_created += 1

class LivenessAndMetricsServer(threading.Thread):
    def __init__(self, host: str = "localhost", port: int = 8080):
        """ Start a metrics and liveness server

        Parameters
        ----------
        host : str
            The host to listen on
        port : int
            The port to listen on
        """
        threading.Thread.__init__(self)
        self.host = host
        self.port = port

    def run(self):
        """ Start a metrics and liveness server.
        """
        self.webServer = HTTPServer((self.host, self.port), LivenessAndMetrics)
        print("Server started http://%s:%s" % (self.host, self.port))

        try:
            self.webServer.serve_forever()
        finally:
            pass
        print("Server stopped.")

    def raise_exception(self):
        """ Causes an exception that will be handled in the thread
        """
        self.webServer.shutdown()

def main():
    load_dotenv()
    opts = Options(environ["API_URL"], environ["CLIENT_ID"], environ["BOTTOK"], environ["NOTION_API"], environ["NOTION_DATABASE"], environ.get("METRICS_HOST", "localhost"), environ.get("PORT", 8080), environ.get("DEBUG", "false") == "true")
    if opts.debug:
        print(sys.version)
    livenessandmetrics = LivenessAndMetricsServer(opts.metrics_host, opts.port)
    livenessandmetrics.start()
    bot = Bot(opts)
    bot.daemon = True
    bot.update_slash_cmds('commands.yml', opts)
    bot.start()
    def handle_shutdown(signum, frame): 
        print("Stopping...")
        bot.shutdown()
        print("Bot Stopped.")
        livenessandmetrics.raise_exception()
        livenessandmetrics.join()
        print("Metrics Server Stopped.")
    signal(SIGINT, handle_shutdown)
    signal(SIGTERM, handle_shutdown)

if __name__ == "__main__":
    main()
