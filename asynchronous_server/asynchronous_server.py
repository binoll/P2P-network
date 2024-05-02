import asyncio
import socket
from typing import Tuple, List, Dict, Optional

BUFFER_SIZE = 1024
BACKLOG = 100
commands = ['list', 'get', 'exit', 'error', 'exist']


class FileInfo:
    def __init__(self, size: int, hash_value: str, filename: str, is_filename_changed: bool = False,
                 is_filename_modify: bool = False):
        self.size = size
        self.hash = hash_value
        self.filename = filename
        self.is_filename_changed = is_filename_changed
        self.is_filename_modify = is_filename_modify


class Connection:
    def __init__(self):
        self.sockets: List[Tuple[socket.socket, socket.socket]] = []
        self.storage: Dict[Tuple[socket, socket], FileInfo] = {}
        self.addr_listen: Tuple[str, int] = ('0.0.0.0', 0)
        self.addr_communicate: Tuple[str, int] = ('0.0.0.0', 0)
        self.synchronization_lock = asyncio.Lock()

    async def wait_connection(self):
        socket_communicate = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socket_communicate.bind(self.addr_communicate)
        socket_communicate.listen(5)  # backlog установлен на 5

        socket_listen = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        socket_listen.bind(self.addr_listen)
        socket_listen.listen(5)  # backlog установлен на 5

        print(f'[*] Server is listening on port for communicate: {socket_communicate.getsockname()[1]}.')
        print(f'[*] Server is listening on port for listening: {socket_listen.getsockname()[1]}.')

        await asyncio.gather(
            self.handle_clients(),
            self.accept_connections(socket_listen, socket_communicate)
        )

    async def accept_connections(self, socket_listen, socket_communicate):
        while True:
            client_socket_communicate, _ = await asyncio.get_event_loop().sock_accept(socket_communicate)
            client_socket_listen, _ = await asyncio.get_event_loop().sock_accept(socket_listen)

            print(f'[+] Success: Client connected: {client_socket_listen.getpeername()}, '
                  f'{client_socket_communicate.getpeername()}')

            synchronization_task = asyncio.create_task(
                self.synchronization(client_socket_listen, client_socket_communicate)
            )

            synchronization_result = await synchronization_task

            if synchronization_result:
                self.sockets.append((client_socket_listen, client_socket_communicate))
            else:
                print('[-] Error: Client disconnected. The storage could not be synchronized.')
                await Connection.close_client_connections(client_socket_listen, client_socket_communicate)

    @staticmethod
    async def close_client_connections(client_socket_listen, client_socket_communicate):
        try:
            client_socket_listen.close()
            client_socket_communicate.close()
        except Exception as e:
            print(f'[-] Error occurred while closing client connections: {e}')

    async def handle_clients(self):
        while True:
            if not self.sockets:
                await asyncio.sleep(0)
                continue

            tasks = [self.handle_client(client_socket_listen, client_socket_communicate) for
                     client_socket_listen, client_socket_communicate in self.sockets]
            await asyncio.gather(*tasks)

    async def handle_client(self, client_socket_listen, client_socket_communicate):
        command = await self.receive_message(client_socket_listen, BUFFER_SIZE)

        if not command:
            return

        if command == commands[0]:
            await self.send_list(client_socket_listen)
        elif command.startswith(commands[1]):
            filename = command.split(':')[1]
            await self.send_file(client_socket_listen, filename)
        elif command == commands[2]:
            self.remove_clients((client_socket_listen, client_socket_communicate))
            await self.close_client_connections(client_socket_listen, client_socket_communicate)
            print('[+] Success: Client disconnected.')

    async def synchronization(self, client_socket_listen: socket.socket,
                              client_socket_communicate: socket.socket) -> bool:
        command_error = commands[3]

        message = await self.receive_message(client_socket_listen, BUFFER_SIZE)
        if not message or message == command_error:
            return False

        message_size, message = self.process_response(message)
        if message_size is None:
            return False

        while message_size > 0:
            try:
                for file_info in message.split(' '):
                    if not file_info:
                        break

                    filename, file_size_str, file_hash = file_info.split(':')
                    file_size = int(file_size_str)
                    self.store_files((client_socket_listen, client_socket_communicate), filename, file_size, file_hash)
            except ValueError as err:
                print('[-] Error:', err)
                return False
            except Exception as err:
                print('[-] Error:', err)
                return False

            message_size -= len(message)
            if message_size <= 0:
                break

            message = await self.receive_message(client_socket_listen, message_size)
            if not message or message == command_error:
                return False

        self.update_storage()
        return True

    @staticmethod
    async def send_message(sock: socket.socket, message: str) -> None:
        buffer = bytearray(message.encode())
        await Connection.send_bytes(sock, buffer)

    @staticmethod
    async def receive_message(sock: socket.socket, size: int) -> Optional[str]:
        buffer = await Connection.receive_bytes(sock, size)
        if not buffer:
            return None
        try:
            buffer_str = buffer.decode()
        except UnicodeDecodeError:
            return None
        return buffer_str

    @staticmethod
    async def send_bytes(sock: socket.socket, buffer: bytes) -> None:
        loop = asyncio.get_event_loop()
        return await loop.sock_sendall(sock, buffer)

    @staticmethod
    async def receive_bytes(sock: socket.socket, size: int) -> bytes | None:
        loop = asyncio.get_event_loop()
        buffer = await loop.sock_recv(sock, size)
        if not buffer:
            return None
        return buffer

    @staticmethod
    def process_response(message: str) -> tuple[int, str] | None:
        try:
            size, _, rest = message.partition(':')
            return int(size), rest
        except ValueError:
            return None

    async def send_list(self, sock: socket.socket) -> int | None:
        files = self.get_list_files()

        try:
            list_str = ' '.join(files)
            message_size = len(list_str)
        except Exception as e:
            print('[-] Error:', e)
            return -1

        message = f'{message_size}: {list_str}'
        await self.send_message(sock, message)

    async def send_file(self, sock: socket.socket, filename: str) -> int | None:
        command_error = commands[3]
        command_exist = commands[4]
        message_size = self.get_size(filename)
        total_bytes = 0

        real_filename = filename if not self.is_filename_modify(filename) else self.remove_index(filename)

        if self.is_filename_change(sock, filename):
            await self.send_message(sock, command_exist)
            return 0

        try:
            message = f'{message_size}:'
        except Exception as e:
            print('[-] Error:', e)
            return -1

        await self.send_message(sock, message)

        sockets = self.find_socket(filename)
        sockets = [(pair[0], pair[1]) for pair in sockets if pair[0] != sock and pair[1] != sock]

        if not sockets:
            return -1

        for i, (_, client_socket_communicate) in enumerate(sockets):
            for offset in range(0, message_size, BUFFER_SIZE):
                client_socket_communicate = sockets[i % len(sockets)][1]
                chunk_size = min(message_size - offset, BUFFER_SIZE)

                message = f'{commands[1]}:{offset}:{chunk_size}:{real_filename}'
                if not self.check_connection(client_socket_communicate):
                    return -1

                await self.send_message(client_socket_communicate, message)

                try:
                    buffer = await self.receive_bytes(client_socket_communicate, chunk_size)
                except sock.timeout:
                    continue
                except Exception as e:
                    print('[-] Error:', e)
                    continue

                if not buffer:
                    continue

                try:
                    buffer_str = str(buffer)
                    if buffer_str == command_error:
                        return -2
                except ValueError:
                    pass

                bytes_sent = self.send_bytes(sock, buffer)
                if bytes_sent is None:
                    continue

                total_bytes += bytes_sent

        return total_bytes

    def find_socket(self, filename: str) -> List[Tuple[socket.socket, socket.socket]]:
        result = []
        for key, value in self.storage.items():
            if value.filename == filename:
                result.append(key)
        return result

    def get_list_files(self) -> List[str]:
        filename_counts = {}
        unique_filenames = []
        duplicate_filenames = []
        for value in self.storage.values():
            filename_counts[value.filename] = filename_counts.get(value.filename, 0) + 1

        for filename, count in filename_counts.items():
            if count == 1:
                unique_filenames.append(filename)
            else:
                duplicate_filenames.append(filename)

        unique_filenames.extend(duplicate_filenames)
        return unique_filenames

    def get_size(self, filename: str) -> int:
        for value in self.storage.values():
            if value.filename == filename:
                return value.size
        return -1

    def update_storage(self):
        hash_count = {}
        for value in self.storage.values():
            hash_count[value.hash] = hash_count.get(value.hash, 0) + 1

        for first_key, first_value in self.storage.items():
            for second_key, second_value in self.storage.items():
                file_occurrences = hash_count[first_value.hash]
                if first_value.hash != second_value.hash and first_value.filename == second_value.filename:
                    if file_occurrences > 1:
                        first_value.filename += '(' + str(file_occurrences - 1) + ')'
                        second_value.filename += '(' + str(file_occurrences) + ')'
                        first_value.is_filename_modify = True
                        second_value.is_filename_modify = True
                        hash_count[first_value.hash] -= 1
                        hash_count[second_value.hash] -= 1
                elif first_value.hash == second_value.hash and first_value.filename != second_value.filename:
                    second_value.filename = first_value.filename
                    second_value.is_filename_changed = True

    def store_files(self, pair: Tuple[socket.socket, socket.socket], filename: str, size: int, hash_val: str):
        data = FileInfo(size, hash_val, filename)
        self.storage[pair] = data
        print("[+] Success: Stored the file:", filename)

    def remove_clients(self, pair: Tuple[socket.socket, socket.socket]):
        for key, value in list(self.storage.items()):
            if key == pair:
                filename = self.remove_index(value.filename)
                for entry_key, entry_value in self.storage.items():
                    if entry_value.filename.startswith(filename):
                        entry_value.filename = self.remove_index(entry_value.filename)
                del self.storage[key]
        self.update_storage()

    @staticmethod
    def remove_index(filename: str) -> str:
        pos = filename.rfind('(')
        if pos != -1:
            filename = filename[:pos]
        return filename

    def is_filename_modify(self, filename: str) -> bool:
        for value in self.storage.values():
            if value.filename == filename:
                return value.is_filename_modify
        return False

    def is_filename_change(self, sock: socket.socket, filename: str) -> bool:
        for key, value in self.storage.items():
            if value.filename == filename and (key[0] == sock or key[1] == sock):
                return value.is_filename_changed
        return False

    @staticmethod
    def check_connection(client_socket_communicate: socket.socket) -> bool:
        try:
            client_socket_communicate.getpeername()
            return True
        except OSError:
            return False


def main():
    connection = Connection()
    asyncio.run(connection.wait_connection())


if __name__ == "__main__":
    main()
