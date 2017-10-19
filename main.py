import requests
import datetime
import time
import json
import socket
import threading

# Read the config
with open("config.json") as file:
    config = json.load(file)

loglock = threading.Lock()

class Service:
    def __init__(self, host, name, port, interval):
        self.host = host
        self.name = name
        self.port = port
        self.interval = interval
        self.status = None
        self.thread = None

    def __repr__(self):
        return f"<Service {self.name} on port {self.port} with status {self.status}>"

    def __str__(self):
        return f"{self.name} ({self.port}): {'alive' if self.status else 'dead'}"

    def poll(self):
        """Try to connect to a port"""
        s = socket.socket()
        s.setblocking(False)
        s.settimeout(5)
        try:
            s.connect((self.host.address, self.port))
            s.close()
        except socket.timeout:
            return 1
        except ConnectionError:
            return 1
        else:
            return 0


    def update(self, callback=None):
        """Update the status once"""
        oldstate = self.status
        self.status = self.poll()
        if callback is not None:
            callback(host=self.host, service=self, old=oldstate, new=self.status)

    def monitor(self, callback):
        """Run this as a thread to continuously update the status"""
        th = threading.current_thread()
        while getattr(th, "running", True):
            # Tra un tentativo e l'altro devono passare interval secondi
            t = time.clock()
            self.update(callback)
            ct = time.clock()
            time.sleep(0 if 1-(ct+t) < 0 else 1-(ct+t))

class Host:
    def __init__(self, name, **kwargs):
        self.name = name
        self.address = kwargs["address"]
        self.interval = kwargs["interval"]
        self.services = []
        for service in kwargs["services"]:
            self.services.append(Service(host=self, name=service, port=kwargs["services"][service], interval=self.interval))

    def __repr__(self):
        return f"<Host {self.name} ({self.address}), with {self.interval}s interval>"

    def __str__(self, formatting="text"):
        text = ""
        if formatting == "text":
            for service in self.services:
                text += str(service) + "\n"
        return text


def broadcast(message):
    """Send a message to the log, stdout and the telegram channel."""
    if config["stdout"]:
        print(message)
    if config["log"]["filename"] != "":
        loglock.acquire()
        with open(config["log"]["filename"], "ab") as file:
            file.write(message.encode("utf-8"))
        loglock.release()
    if config["telegram"]["channel_id"] != 0:
        requests.get(f"https://api.telegram.org/bot{config['telegram']['token']}/sendMessage", params={
            "chat_id": config["telegram"]["channel_id"],
            "text": message
        })



def handle_update(host, service, old, new):
    # 0 = Up
    # >0 = Down
    t = datetime.datetime.now()
    if old is None:
        if new == 0:
            # Service is up
            broadcast(t.strftime(r"%Y-%m-%d %H:%M:%S") + f" {service.name} on {host.name} ({host.address}:{service.port}) is 🔵 up.\n")
        else:
            # Service is down
            broadcast(t.strftime(r"%Y-%m-%d %H:%M:%S") + f" {service.name} on {host.name} ({host.address}:{service.port}) is 🔴 down.\n")
    elif old == 0 and new > 0:
        # Service died
        broadcast(t.strftime(r"%Y-%m-%d %H:%M:%S") + f" {service.name} on {host.name} ({host.address}:{service.port}) went 🔴 down.\n")
    elif old > 0 and new == 0:
        # Service was revived
        broadcast(t.strftime(r"%Y-%m-%d %H:%M:%S") + f" {service.name} on {host.name} ({host.address}:{service.port}) went 🔵 up.\n")


hosts = []

if __name__ == "__main__":
    for host in config["hosts"]:
        hosts.append(Host(host, **config["hosts"][host]))
    for host in hosts:
        for service in host.services:
            service.thread = threading.Thread(target=service.monitor, args=(handle_update,), name=repr(service))
            service.thread.running = True
            service.thread.start()
    broadcast(datetime.datetime.now().strftime(r"%Y-%m-%d %H:%M:%S") + f" ✅ Logging started.\n")
    try:
        while True:
            time.sleep(300)
    except KeyboardInterrupt:
        for host in hosts:
            for service in host.services:
                service.thread.running = False
                service.thread.join()
    broadcast(datetime.datetime.now().strftime(r"%Y-%m-%d %H:%M:%S") + f" 🛑 Logging stopped.\n")