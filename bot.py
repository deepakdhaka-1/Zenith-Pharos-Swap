# bot_phrs_wrap_swap_colored_retry.py
import os
import time
import random
import json
from datetime import datetime
from eth_abi.abi import encode
from eth_account import Account
from web3 import Web3
from colorama import Fore, Style, init

init(autoreset=True)

# ----------------- CONFIG -----------------
RPC_URL = "https://testnet.dplabs-internal.com/"

# Addresses
WPHRS = "0x76aaaDA469D23216bE5f7C596fA25F282Ff9b364"
USDC = "0x72df0bcd7276f2dFbAc900D1CE63c272C4BCcCED"
USDT = "0xD4071393f8716661958F766DF660033b3d35fD29"
SWAP_ROUTER = "0x1A4DE519154Ae51200b0Ad7c90F7faC75547888a"
QUOTER = "0x00f2f47d1ed593Cf0AF0074173E9DF95afb0206C"

ERC20_ABI = json.loads("""[
    {"type":"function","name":"decimals","stateMutability":"view","inputs":[],"outputs":[{"name":"","type":"uint8"}]},
    {"type":"function","name":"balanceOf","stateMutability":"view","inputs":[{"name":"account","type":"address"}],"outputs":[{"name":"","type":"uint256"}]},
    {"type":"function","name":"allowance","stateMutability":"view","inputs":[{"name":"owner","type":"address"},{"name":"spender","type":"address"}],"outputs":[{"name":"","type":"uint256"}]},
    {"type":"function","name":"approve","stateMutability":"nonpayable","inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"outputs":[{"name":"","type":"bool"}]},
    {"type":"function","name":"deposit","stateMutability":"payable","inputs":[],"outputs":[]}
]""")

QUOTER_ABI = [
    {
        "type": "function", "name": "quoteExactInput",
        "stateMutability": "nonpayable",
        "inputs": [{"internalType":"bytes","name":"path","type":"bytes"},{"internalType":"uint256","name":"amountIn","type":"uint256"}],
        "outputs": [{"internalType":"uint256","name":"amountOut","type":"uint256"}]
    }
]

SWAP_ROUTER_ABI = [
    {
        "type":"function","name":"multicall","stateMutability":"payable",
        "inputs":[{"internalType":"uint256","name":"deadline","type":"uint256"},{"internalType":"bytes[]","name":"data","type":"bytes[]"}],
        "outputs":[{"internalType":"bytes[]","name":"","type":"bytes[]"}]
    }
]

DEFAULT_FEE = 500  # 0.05%

# ----------------- UTIL -----------------
def now_ts():
    return datetime.now().strftime("%x %X")

def log_info(msg): print(f"{Fore.WHITE}[{now_ts()}] {msg}{Style.RESET_ALL}")
def log_ok(msg):   print(f"{Fore.GREEN}[{now_ts()}] {msg}{Style.RESET_ALL}")
def log_warn(msg): print(f"{Fore.YELLOW}[{now_ts()}] {msg}{Style.RESET_ALL}")
def log_err(msg):  print(f"{Fore.RED}[{now_ts()}] {msg}{Style.RESET_ALL}")
def log_tx(msg):   print(f"{Fore.CYAN}[{now_ts()}] {msg}{Style.RESET_ALL}")
def log_header(msg): print(f"\n{Fore.YELLOW}{Style.BRIGHT}========== {msg} =========={Style.RESET_ALL}\n")

# ----------------- MAIN BOT CLASS -----------------
class ZenithSimple:
    def __init__(self, rpc_url=RPC_URL):
        self.web3 = Web3(Web3.HTTPProvider(rpc_url))
        if not self.web3.is_connected():
            raise SystemExit("RPC not connected: " + rpc_url)
        self.used_nonce = {}

    def load_keys(self, filename="pvt.txt"):
        if not os.path.exists(filename):
            raise SystemExit("Create pvt.txt with one private key per line.")
        with open(filename, "r") as f:
            return [l.strip() for l in f if l.strip()]

    def get_address(self, pk): return Account.from_key(pk).address
    def get_native_balance(self, address): return self.web3.from_wei(self.web3.eth.get_balance(address), "ether")

    def wrap_phrs(self, pk, address, amount_phrs):
        while True:
            try:
                w3 = self.web3
                amount_wei = w3.to_wei(amount_phrs, "ether")
                contract = w3.eth.contract(address=w3.to_checksum_address(WPHRS), abi=ERC20_ABI)
                nonce = self.used_nonce[address]
                tx = contract.functions.deposit().build_transaction({
                    "from": address,
                    "value": amount_wei,
                    "nonce": nonce,
                    "gas": 100000,
                    "gasPrice": w3.to_wei("2", "gwei"),
                    "chainId": w3.eth.chain_id
                })
                signed = w3.eth.account.sign_transaction(tx, pk)
                txh = w3.eth.send_raw_transaction(signed.raw_transaction)
                txh_hex = w3.to_hex(txh)
                log_tx(f"Wrap PHRS->WPHRS tx sent: {txh_hex}")
                receipt = w3.eth.wait_for_transaction_receipt(txh)
                self.used_nonce[address] += 1
                log_ok(f"Wrapped {amount_phrs} PHRS. Block: {receipt.blockNumber}")
                return txh_hex
            except Exception as e:
                log_err(f"Wrap failed: {e}. Retrying in 10s...")
                time.sleep(10)

    def approve_if_needed(self, pk, address, token_addr, spender, amount_needed_wei):
        while True:
            try:
                w3 = self.web3
                token = w3.eth.contract(address=w3.to_checksum_address(token_addr), abi=ERC20_ABI)
                allowance = token.functions.allowance(address, spender).call()
                if allowance >= amount_needed_wei:
                    log_ok("Allowance already sufficient.")
                    return None
                nonce = self.used_nonce[address]
                tx = token.functions.approve(spender, 2**256 - 1).build_transaction({
                    "from": address,
                    "nonce": nonce,
                    "gas": 100000,
                    "gasPrice": w3.to_wei("2", "gwei"),
                    "chainId": w3.eth.chain_id
                })
                signed = w3.eth.account.sign_transaction(tx, pk)
                txh = w3.eth.send_raw_transaction(signed.raw_transaction)
                txh_hex = w3.to_hex(txh)
                log_tx(f"Approve tx sent: {txh_hex}")
                receipt = w3.eth.wait_for_transaction_receipt(txh)
                self.used_nonce[address] += 1
                log_ok(f"Approve confirmed. Block: {receipt.blockNumber}")
                return txh_hex
            except Exception as e:
                log_err(f"Approve failed: {e}. Retrying in 10s...")
                time.sleep(10)

    def get_amount_out(self, token_in, token_out, amount_in_wei, fee=DEFAULT_FEE):
        try:
            quoter = self.web3.eth.contract(address=self.web3.to_checksum_address(QUOTER), abi=QUOTER_ABI)
            path = bytes.fromhex(token_in[2:]) + fee.to_bytes(3, "big") + bytes.fromhex(token_out[2:])
            return quoter.functions.quoteExactInput(path, amount_in_wei).call()
        except Exception as e:
            log_warn(f"Quoter failed: {e}")
            return 0

    def build_exact_input_single_calldata(self, token_in, token_out, fee, recipient, amount_in_wei, amount_out_min_wei):
        selector = bytes.fromhex("04e45aaf")
        params = encode(
            ['address', 'address', 'uint24', 'address', 'uint256', 'uint256', 'uint160'],
            [token_in, token_out, fee, recipient, amount_in_wei, amount_out_min_wei, 0]
        )
        return selector + params

    def swap_wphrs_to_stable(self, pk, address, token_out, amount_in_wei, min_out_wei, fee=DEFAULT_FEE):
        while True:
            try:
                w3 = self.web3
                router = w3.eth.contract(address=w3.to_checksum_address(SWAP_ROUTER), abi=SWAP_ROUTER_ABI)
                deadline = int(time.time()) + 600
                calldata = self.build_exact_input_single_calldata(WPHRS, token_out, fee, address, amount_in_wei, min_out_wei)
                fn = router.functions.multicall(deadline, [calldata])
                est_gas = fn.estimate_gas({"from": address})
                tx = fn.build_transaction({
                    "from": address,
                    "nonce": self.used_nonce[address],
                    "gas": int(est_gas * 1.2),
                    "gasPrice": w3.to_wei("2", "gwei"),
                    "chainId": w3.eth.chain_id
                })
                signed = w3.eth.account.sign_transaction(tx, pk)
                txh = w3.eth.send_raw_transaction(signed.raw_transaction)
                txh_hex = w3.to_hex(txh)
                log_tx(f"Swap tx sent: {txh_hex}")
                receipt = w3.eth.wait_for_transaction_receipt(txh)
                self.used_nonce[address] += 1
                log_ok(f"Swap confirmed. Block: {receipt.blockNumber}")
                log_tx(f"Explorer: https://testnet.pharosscan.xyz/tx/{txh_hex}")
                return txh_hex
            except Exception as e:
                log_err(f"Swap failed: {e}. Retrying in 10s...")
                time.sleep(10)

    def process_account(self, pk, phrs_amount, token_out, slippage_pct):
        addr = self.get_address(pk)
        log_header(f"Processing wallet {addr}")
        self.used_nonce[addr] = self.web3.eth.get_transaction_count(addr, "pending")
        bal = float(self.get_native_balance(addr))
        log_info(f"Balance: {bal} PHRS")

        if bal < phrs_amount:
            log_err("Insufficient PHRS; skipping.")
            return

        self.wrap_phrs(pk, addr, phrs_amount)
        amount_in_wei = int(phrs_amount * 10**18)
        amt_out = self.get_amount_out(WPHRS, token_out, amount_in_wei)
        min_out = int(amt_out * (100 - slippage_pct) // 100) if amt_out else 0

        self.approve_if_needed(pk, addr, WPHRS, SWAP_ROUTER, amount_in_wei)
        self.swap_wphrs_to_stable(pk, addr, token_out, amount_in_wei, min_out)

    def run_all(self):
        keys = self.load_keys("pvt.txt")
        phrs_amount = float(input("Enter PHRS amount to swap per wallet -> ").strip())
        choice = input("Choose [1] USDC or [2] USDT -> ").strip()
        token_out = USDC if choice == "1" else USDT
        slippage_pct = float(input("Slippage % (e.g. 5) -> ").strip())
        min_delay = int(input("Min delay between wallets (s) -> ").strip())
        max_delay = int(input("Max delay between wallets (s) -> ").strip())
        if max_delay < min_delay: max_delay = min_delay

        for pk in keys:
            self.process_account(pk, phrs_amount, token_out, slippage_pct)
            delay = random.randint(min_delay, max_delay) if max_delay > 0 else 0
            if delay:
                log_info(f"Waiting {delay}s before next wallet...")
                time.sleep(delay)

# ----------------- ENTRY -----------------
if __name__ == "__main__":
    log_info("Zenith - PHRS -> WPHRS -> USDC/USDT Swap Bot (with retry)")
    bot = ZenithSimple()
    bot.run_all()
