import binascii
import json
import os
import queue
import re
import socket
import sys
import threading
import time

import requests

from web3 import Web3
from eth_account import Account

from src import util

LOGGER = util.get_logger("solo")
CONF = util.get_conf()

TOPIC_MINT = "0xcf6fbb9dcea7d07263ab4f5c3a92f53af33dffc421d9d121e1c74b307e68189d"
ZKBITCOIN_ADDRESS = "0x366d17aDB24A7654DbE82e79F85F9Cb03c03cD0D"

# logging.basicConfig(level=logging.DEBUG)

with open("zkbitcoin_abi.json", encoding="utf-8") as f:
    ZKBITCOIN_ABI = f.read()


class ClientHandlerDB:
    def __init__(self):
        self.client_handlers = {}
        self.lock = threading.Lock()

    def add(self, address, handler):
        with self.lock:
            self.client_handlers[address] = handler
            self.log_info()

    def remove(self, address):
        with self.lock:
            del self.client_handlers[address]
            self.log_info()

    def get(self):
        with self.lock:
            return list(self.client_handlers.values())

    def log_info(self):
        LOGGER.info("handling %s clients", len(self.client_handlers))


class ClientHandler:
    def __init__(self, sock, address, client_handler_db, messages_from_clients):
        self.sock = sock
        self.address = address
        self.client_handler_db = client_handler_db
        self.messages_from_clients = messages_from_clients

        self.read_messages_from_client_thread = threading.Thread(
            target=self.read_messages_from_client
        )
        self.read_messages_from_client_thread.start()
        LOGGER.info("handling connection %s", address)

    def read_messages_from_client(self):
        while True:
            data = self.sock.recv(4096)
            if data is None or len(data) == 0:
                LOGGER.info("%s disconnected", self.address)
                break
            try:
                s = data.decode("utf-8")
                m = json.loads(s)
                LOGGER.debug("%s %s", self.address, repr(m))
                self.messages_from_clients.put(m)
            except ValueError:
                LOGGER.warning(
                    "unable to parse message from %s: %s", self.address, repr(data)
                )
        self.sock.close()
        self.client_handler_db.remove(self.address)
        LOGGER.debug("%s handler thread ending", self.address)

    def send(self, s):
        self.sock.send(s.encode("utf-8"))


class Server:
    def __init__(self, port, pool_address):
        self.port = port
        self.pool_address = pool_address
        self.client_handler_db = ClientHandlerDB()

        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(("127.0.0.1", self.port))
        self.server_sock.listen()

        self.accept_clients_thread = threading.Thread(target=self.accept_clients)
        self.accept_clients_thread.start()

        self.mining_target = None
        self.challenge_number = None
        self.poll_for_mining_parameters_thread = threading.Thread(
            target=self.poll_for_mining_parameters
        )
        self.poll_for_mining_parameters_thread.start()

        self.messages_from_clients = queue.SimpleQueue()
        self.process_messages_from_clients_thread = threading.Thread(
            target=self.process_messages_from_clients
        )
        self.process_messages_from_clients_thread.start()

        self.sprite = None
        self.update_sprite()

        self.work_message = None
        self.update_work_message()

    # The work message depends on the mining target, challenge number, and
    # sprite, so we should update it when any of those things change.
    def update_work_message(self):
        if not self.mining_target or not self.challenge_number:
            LOGGER.warning("don't know mining parameters yet")
            self.work_message = None
        elif not self.sprite:
            LOGGER.warning("no sprites remaining")
            self.work_message = None
        else:
            m = {
                "method": "set_work",
                "pool_address": self.pool_address,
                # "mining_target": "0x00000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
                "mining_target": self.mining_target,
                "challenge_number": self.challenge_number,
                "sprite": "0x" + self.sprite,
            }
            self.work_message = json.dumps(m) + "\n"
            LOGGER.debug("new work message: %s", self.work_message)

    def update_sprite(self):
        self.sprite = sprites_get_current()
        self.update_work_message()

    def set_mining_parameters(self, mining_target, challenge_number):
        self.mining_target = mining_target
        self.challenge_number = challenge_number
        self.update_work_message()

    def accept_clients(self):
        LOGGER.info("serving clients on port %s", self.port)
        while True:
            sock, address = self.server_sock.accept()
            LOGGER.info("accepted connection %s", address)
            ch = ClientHandler(
                sock, address, self.client_handler_db, self.messages_from_clients
            )
            self.client_handler_db.add(address, ch)
            if self.work_message:
                ch.send(self.work_message)
            else:
                LOGGER.warning("no work to send to client")

    def send_to_clients(self, s):
        for ch in self.client_handler_db.get():
            ch.send(s)

    def poll_for_mining_parameters(self):
        while True:
            mt = zkbitcoin_get_mining_target()
            cn = zkbitcoin_get_challenge_number()
            if mt != self.mining_target or cn != self.challenge_number:
                LOGGER.info("new mining parameters: mt=%s cn=%s", mt, cn)
                self.mining_target = mt
                self.challenge_number = cn
                self.set_mining_parameters(mt, cn)
                self.send_work_message_to_clients()
            time.sleep(8)

    def send_work_message_to_clients(self):
        if self.work_message:
            self.send_to_clients(self.work_message)
        else:
            LOGGER.warning("no work to send to clients")

    def process_messages_from_clients(self):
        while True:
            try:
                m = self.messages_from_clients.get()
                LOGGER.info("message from miner: %s", repr(m))
                if "method" in m and m["method"] == "submit_solution":
                    threading.Thread(target=self.submit_solution, args=(m,)).start()
                elif "method" in m and m["method"] == "ping":
                    pass
                else:
                    LOGGER.warning("did not understand message")
            except Exception as e:
                LOGGER.exception(e)
                time.sleep(1)

    # `m` should look like
    # { "method": "submit_solution",
    #   "solution": "0x<64_hex_challenge><40_hex_sender><64_hex_nonce>"
    # }
    def submit_solution(self, m):
        LOGGER.info("submitting solution %s", m)
        challenge_number = "0x" + m["solution"][2 : 2 + 64]
        miner_address = "0x" + m["solution"][66 : 66 + 40]
        miner_address = Web3.to_checksum_address(miner_address)
        nonce = "0x" + m["solution"][106 : 106 + 64]
        nonce = int(nonce, 16)
        LOGGER.debug("challenge_number: %s", repr(challenge_number))
        LOGGER.debug("miner_address: %s", repr(miner_address))
        LOGGER.debug("nonce: %s", repr(nonce))
        num_tries = 3
        for n in range(1, num_tries + 1):
            try:
                LOGGER.debug("attempt %s/%s", n, num_tries)
                account = Account.from_key(CONF["privateKey"])
                LOGGER.debug("account.address: %s", account.address)
                w3 = Web3(Web3.WebsocketProvider(CONF["providerWebsocketUrl"]))
                zkbitcoin = w3.eth.contract(
                    address=ZKBITCOIN_ADDRESS, abi=ZKBITCOIN_ABI
                )
                tx = zkbitcoin.functions.multiMint_SameAddress(
                    miner_address, [nonce]
                ).build_transaction(
                    {
                        "from": account.address,
                        "nonce": w3.eth.get_transaction_count(account.address),
                    }
                )
                LOGGER.debug("tx: %s", tx)
                signed_tx = Account.sign_transaction(tx, account.key)
                LOGGER.debug("signed_tx: %s", signed_tx)
                tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                tx_hash = "0x" + binascii.hexlify(tx_hash).decode("utf-8")
                LOGGER.debug("tx_hash: %s", tx_hash)
                w3.eth.wait_for_transaction_receipt(tx_hash)
                LOGGER.info("got receipt")
                self.submitted_solution_successfully()
                break
            except Exception as e:
                LOGGER.exception(e)
                time.sleep(1)

    def submitted_solution_successfully(self):
        LOGGER.info("submitted solution successfully")
        sprites_mark_as_done(self.sprite)
        self.update_sprite()
        self.send_work_message_to_clients()


SPRITES_FILENAME = "sprites.txt"
SPRITES_DONE_FILENAME = "sprites_done.txt"


def sprites_get_current():
    sprites_remaining = sprites_get_remaining()
    return sprites_remaining[0] if sprites_remaining else None


def sprites_get_remaining():
    sprites = sprites_get_from_file(SPRITES_FILENAME)
    sprites_done = sprites_get_from_file(SPRITES_DONE_FILENAME)
    sprites_remaining = [s for s in sprites if s not in sprites_done]
    return sprites_remaining


def sprites_get_from_file(filename):
    with open(filename, encoding="utf-8") as f:
        data = f.read().lower()
    sprites = re.findall(r"([0-9a-f]{64})", data)
    return sprites


def sprites_mark_as_done(sprite):
    with open(SPRITES_DONE_FILENAME, "a", encoding="utf-8") as f:
        f.write(sprite + "\n")


def do_jsonrpc_request(method, params):
    req = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    r = requests.post(CONF["providerHttpUrl"], json=req, timeout=4)
    d = json.loads(r.content)
    if "error" in d:
        LOGGER.error(d["error"])
        raise Exception("request failed")
    return d["result"]


def zkbitcoin_get_mining_target():
    return do_jsonrpc_request(
        "eth_call",
        [
            {
                "to": ZKBITCOIN_ADDRESS,
                # `cast sig 'miningTarget() returns (uint256)'` => 0x8a769d35
                "data": "0x8a769d3500000000000000000000000000000000000000000000000000000000",
            }
        ],
    )


def zkbitcoin_get_challenge_number():
    return do_jsonrpc_request(
        "eth_call",
        [
            {
                "to": ZKBITCOIN_ADDRESS,
                # `cast sig 'challengeNumber() returns (bytes32)'` => 0x8ae0368b
                "data": "0x8ae0368b00000000000000000000000000000000000000000000000000000000",
            }
        ],
    )


def check_or_die(f, message):
    def die():
        LOGGER.error(message)
        sys.exit(1)

    try:
        if not f():
            die()
    except Exception:
        die()


def check_basics():
    def web3_http_provider_works():
        w3 = Web3(Web3.HTTPProvider(CONF["providerHttpUrl"]))
        return w3.is_connected()

    def web3_websocket_provider_works():
        w3 = Web3(Web3.WebsocketProvider(CONF["providerWebsocketUrl"]))
        return w3.is_connected()

    check_or_die(
        lambda: re.search(r"^0x[0-9a-f]{64}$", CONF["privateKey"]),
        f"configure `privateKey` in {util.CONF_FILENAME}",
    )
    check_or_die(
        web3_http_provider_works,
        f"configure `providerHttpUrl` in {util.CONF_FILENAME}, or just try again",
    )
    check_or_die(
        web3_websocket_provider_works,
        f"configure `providerWebsocketUrl` in {util.CONF_FILENAME}, or just try again",
    )
    check_or_die(
        lambda: os.path.exists(SPRITES_FILENAME), f"configure {SPRITES_FILENAME}"
    )
    check_or_die(
        lambda: len(sprites_get_remaining()) > 0,
        f"no sprites remaining. compare {SPRITES_FILENAME} and {SPRITES_DONE_FILENAME}",
    )


def touch(path):
    with open(path, "a"):
        os.utime(path, None)


if __name__ == "__main__":
    touch(SPRITES_DONE_FILENAME)
    check_basics()
    pool_address = Account.from_key(CONF["privateKey"]).address
    server = Server(CONF["port"], pool_address)
    while True:
        time.sleep(10)
