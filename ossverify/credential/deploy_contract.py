"""Polygon Amoy testnet에 OSSVerifyRegistry 컨트랙트를 배포한다.

실행 전 준비:
  1. .env 파일에 POLYGON_PRIVATE_KEY 설정 (0x 포함 또는 미포함 모두 가능)
  2. 해당 지갑 주소에 Amoy MATIC 확보
     https://faucet.polygon.technology/ 에서 무료 수령

실행:
  python -m ossverify.credential.deploy_contract

성공 시 출력된 POLYGON_CONTRACT_ADDRESS를 .env에 추가하면 VC 발급 시
실제 트랜잭션으로 해시가 기록된다.
"""

import os
import sys

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())

_AMOY_RPC = os.getenv("POLYGON_RPC_URL", "https://rpc-amoy.polygon.technology/")
_SOL_PATH = os.path.join(os.path.dirname(__file__), "OSSVerifyRegistry.sol")
_SOLC_VERSION = "0.8.20"


def _compile() -> tuple[list, str]:
    try:
        from solcx import compile_source, install_solc, set_solc_version
    except ImportError:
        sys.exit("py-solc-x 가 설치되지 않았습니다: pip install py-solc-x")

    print(f"[1/3] solc {_SOLC_VERSION} 설치 중 (이미 있으면 건너뜀)...")
    install_solc(_SOLC_VERSION, show_progress=True)
    set_solc_version(_SOLC_VERSION)

    with open(_SOL_PATH, encoding="utf-8") as f:
        source = f.read()

    compiled = compile_source(source, output_values=["abi", "bin"])
    key = "<stdin>:OSSVerifyRegistry"
    abi = compiled[key]["abi"]
    bytecode = compiled[key]["bin"]
    print(f"[1/3] 컴파일 완료. bytecode {len(bytecode) // 2} bytes")
    return abi, bytecode


def _deploy(abi: list, bytecode: str) -> str:
    try:
        from web3 import Web3
    except ImportError:
        sys.exit("web3 가 설치되지 않았습니다: pip install web3")

    private_key = os.getenv("POLYGON_PRIVATE_KEY", "")
    if not private_key:
        sys.exit("POLYGON_PRIVATE_KEY 환경변수가 설정되지 않았습니다.")
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key

    print(f"[2/3] Polygon Amoy ({_AMOY_RPC}) 연결 중...")
    w3 = Web3(Web3.HTTPProvider(_AMOY_RPC))
    if not w3.is_connected():
        sys.exit(f"RPC 연결 실패: {_AMOY_RPC}")

    account = w3.eth.account.from_key(private_key)
    balance = w3.eth.get_balance(account.address)
    print(f"[2/3] 지갑 주소: {account.address}")
    print(f"[2/3] MATIC 잔고: {w3.from_wei(balance, 'ether'):.4f}")
    if balance == 0:
        sys.exit("MATIC 잔고 부족. https://faucet.polygon.technology/ 에서 수령하세요.")

    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx = contract.constructor().build_transaction({
        "from": account.address,
        "nonce": w3.eth.get_transaction_count(account.address),
        "gas": 500_000,
        "gasPrice": w3.eth.gas_price,
        "chainId": 80002,  # Polygon Amoy
    })
    signed = w3.eth.account.sign_transaction(tx, private_key)

    print("[3/3] 배포 트랜잭션 전송 중...")
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    print(f"[3/3] tx hash: {tx_hash.hex()}")
    print("[3/3] 컨트랙트 주소 확인 대기 (최대 60초)...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
    contract_address = receipt.contractAddress
    print(f"\n✅ 배포 성공!")
    print(f"   Contract Address: {contract_address}")
    print(f"\n.env 에 추가하세요:")
    print(f"   POLYGON_CONTRACT_ADDRESS={contract_address}")
    return contract_address


if __name__ == "__main__":
    abi, bytecode = _compile()
    _deploy(abi, bytecode)
