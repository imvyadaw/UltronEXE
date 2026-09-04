import socket


class NetworkManager:
    def status(self):
        try:
            socket.gethostbyname("example.com")
            return {"online": True}
        except OSError:
            return {"online": False}
