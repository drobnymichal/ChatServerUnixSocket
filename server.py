import asyncio, socket, time
import collections
from inspect import stack

import os

from typing import AsyncIterator, Deque, List, Optional, Tuple, Union, Dict
from collections import deque


class Client:
    def __init__(self, writer: asyncio.StreamWriter, reader: asyncio.StreamReader) -> None:
        self.name = None
        self.writer = writer
        self.reader = reader
        self.channels: Dict[str, 'Channel'] = {}

    async def send_message(self, text: str):
        #print(text)
        self.writer.write((text + " \n").encode("utf-8"))
        await self.writer.drain()


class Message:
    def __init__(self, text: str, timestamp: int, nick: str) -> None:
        self.text = text
        self.timestamp: int = timestamp
        self.nick = nick


class Channel:
    def __init__(self, name: str) -> None:
        self.name: str = name
        self.clients: List['Client'] = []
        self.messages: List['Message'] = []

    async def send_to_all(self, msg: Union['Message', str]) -> None:
        if isinstance(msg, Message):
            self.messages.append(msg)
            msg = msg.text 
        
        for client in self.clients:
            await client.send_message(msg)


    async def announce_all(self, called_client: 'Client', msg: Union['Message', str]) -> None:
        if isinstance(msg, Message):
            self.messages.append(msg)
            msg = msg.text 

        for client in self.clients:
            if client is not called_client:
                await client.send_message(msg)

    async def replay(self, client: 'Client', timestamp: float):
        for msg in self.messages:
            #print(f"actual: {timestamp} msg: {msg.timestamp}")
            if msg.timestamp >= timestamp:
                await client.send_message(msg.text)


class Server:
    def __init__(self) -> None:
        self.all_channels: Dict[str, 'Channel'] = {}
        self.all_clients: List['Client'] = []

    def find_channel(self, name: str) -> Optional['Channel']:
        for name_ch, channel in self.all_channels.items():
            if name_ch == name:
                return channel
        return None

    def check_nick(self, nick: str) -> bool:
        if nick.startswith("#"):
            return False
        for client in self.all_clients:
            if client.name == nick:
                return False
        return True

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        client: 'Client' = Client(writer, reader)
        self.all_clients.append(client)
        try:
            got_text = (await reader.readuntil(b'\n')).decode("utf-8")[:-1]
        except asyncio.IncompleteReadError:
            return None

        while not writer.is_closing():
            request = got_text.split(maxsplit=2)
            timestamp = time.time()
            print(" ".join(request).encode("utf-8"))
        
            if len(request) == 2: # commands: nick, join, part
                command, param = request
                if command == "nick":
                    if not self.check_nick(param) or param.startswith("#") or param.startswith("*"):
                        await client.send_message("error You cannot use this nick.")
                    elif client.name is None:
                        client.name = param
                        await client.send_message("ok Your nick has been set.")
                    else:
                        for channel in client.channels.values():
                            for cl in channel.clients:
                                if cl is not client:
                                    await founded_channel.announce_all(client, Message(f"message {founded_channel.name} {int(timestamp)} *server* {client.name} is now known as {param}", int(timestamp), "*server*"))
                        client.name = param
                        await client.send_message("ok Your nick has been changed.")
                elif client.name is None:
                    await client.send_message("error First, you have to select your nick.")
                elif command == "join":
                    founded_channel = self.find_channel(param)
                    if len(param) < 2 or not param.startswith("#") or param.startswith("*"):
                        await client.send_message("error Channel name must start with <#>.")
                    elif founded_channel is None:
                        founded_channel = Channel(param)
                        self.all_channels[param] = founded_channel
                        founded_channel.clients.append(client)
                        client.channels[param] = founded_channel
                        founded_channel.messages.append(Message(f"message {founded_channel.name} {int(timestamp)} *server* {client.name} has joined the channel", int(timestamp), "*server*"))
                        await client.send_message("ok You have created and joined the channel.")
                    elif founded_channel not in client.channels:
                        founded_channel.clients.append(client)
                        client.channels[param] = founded_channel
                        await client.send_message("ok You have joined the channel.")
                        await founded_channel.announce_all(client, Message(f"message {founded_channel.name} {int(timestamp)} *server* {client.name} has joined the channel", int(timestamp), "*server*"))
                    else:
                        await client.send_message("error You are already joined to this channel.")
                elif command == "part":
                    founded_channel = self.find_channel(param)
                    if founded_channel is None:
                        await client.send_message("error You are not member of this channel.")
                    else:
                        founded_channel.clients.remove(client)
                        client.channels.pop(param)
                        await client.send_message("ok You have left the channel.")
                else:
                    await client.send_message("error Unknown command.")
            elif client.name is None:
                await client.send_message("error First, you have to select your nick.")
            elif len(request) == 3:
                command, channel, other = request
                if command == "message":
                    founded_channel = self.find_channel(channel)
                    if founded_channel is None:
                        await client.send_message("error The channel does not exist.")
                    elif channel not in client.channels:
                        await client.send_message("error You are no associated with this channel.")
                    else:
                        await founded_channel.send_to_all(Message(f"message {founded_channel.name} {int(timestamp)} {client.name} {other}", int(timestamp), client.name))
                elif command == "replay":
                    if not other.isdigit() or int(other) > time.time():
                        await client.send_message("error Replay command is not valid - timestamp.")
                    else:
                        founded_channel = client.channels.get(channel, None)
                        if founded_channel is None:
                            await client.send_message("error Replay command is not valid - channel.")
                        else:
                            await client.send_message("ok Replay command is valid.")
                            await founded_channel.replay(client, int(other))
                else:
                    await client.send_message("error Unknown command.")
            else:
                await client.send_message("error Unknown command.")
            try:
                got_text = (await reader.readuntil(b'\n')).decode("utf-8")[:-1]
            except asyncio.IncompleteReadError:
                return None


def check_names(inp: List[str]) -> bool:
    if len(inp) == 0:
        return False
    for name in inp:
        if name == "" or name.isspace() or os.path.exists(name):
            return False
    return True
        

async def create_server(name: str):
    try:
        sock = await asyncio.start_unix_server(Server().handle_client, name)
        await sock.serve_forever()
    except KeyboardInterrupt:
        print("ending")
        exit(1)

def main():
    user_input = input("Enter names of unix servers: ").split()
    while not check_names(user_input):
        print("Some of the names are already used.")
        user_input = input("Enter names of unix servers: ").split()

    loop = asyncio.get_event_loop()
    for name in user_input:
        loop.create_task(create_server(name))

    try:
        loop.run_forever()
    finally:
        for name in user_input:
            os.remove(name)



if __name__ == "__main__":
    main()
