from eth_account import Account
from eth_abi import encode
from web3 import Web3
from hexbytes import HexBytes

# Gnosis Safe v1.3.0 EIP-712 Constants
# EIP712Domain(uint256 chainId,address verifyingContract)
DOMAIN_SEPARATOR_TYPEHASH = HexBytes("0x47e79534a245952e8b16893a336b85a3d9ea9fa8c573f3d803afb92a79469218")

# SafeTx(address to,uint256 value,bytes data,uint8 operation,uint256 safeTxGas,uint256 baseGas,uint256 gasPrice,address gasToken,address refundReceiver,uint256 nonce)
SAFE_TX_TYPEHASH = HexBytes("0xbb8310d486368db6bd6f849402fdd73ad53d316b5a4b2644ad6efe0f941286d8")

def sign_safe_tx(
    safe_address,
    to,
    value,
    data,
    operation,
    safe_tx_gas,
    base_gas,
    gas_price,
    gas_token,
    refund_receiver,
    nonce,
    private_key,
    chain_id=137
):
    """
    Signs a Gnosis Safe transaction using EIP-712.
    Returns the signature bytes.
    """
    
    # 1. Prepare Data Hash
    if isinstance(data, str):
        if data.startswith("0x"):
            data_bytes = HexBytes(data)
        else:
            # Fallback for non-hex strings, though data usually passed as hex or bytes
            data_bytes = HexBytes(data) 
    elif isinstance(data, bytes):
        data_bytes = data
    else:
        data_bytes = b''
        
    data_hash = Web3.keccak(data_bytes)

    # 2. Calculate SafeTxHash
    # Encode the struct according to EIP-712
    # uint256/address are padded to 32 bytes
    safe_tx_encoded = encode(
        [
            'bytes32', 'address', 'uint256', 'bytes32', 'uint8', 
            'uint256', 'uint256', 'uint256', 'address', 'address', 'uint256'
        ],
        [
            SAFE_TX_TYPEHASH,
            to,
            value,
            data_hash,
            operation,
            safe_tx_gas,
            base_gas,
            gas_price,
            gas_token,
            refund_receiver,
            nonce
        ]
    )
    safe_tx_hash = Web3.keccak(safe_tx_encoded)

    # 3. Calculate Domain Separator
    domain_separator_encoded = encode(
        ['bytes32', 'uint256', 'address'],
        [DOMAIN_SEPARATOR_TYPEHASH, chain_id, safe_address]
    )
    domain_separator = Web3.keccak(domain_separator_encoded)

    # 4. Calculate Final EIP-712 Message Hash
    # \x19\x01 + domainSeparator + safeTxHash
    encoded_packed = b'\x19\x01' + domain_separator + safe_tx_hash
    message_hash = Web3.keccak(encoded_packed)

    # 5. Sign the Hash
    # Using internal _sign_hash to sign the raw digest without 'Ethereum Signed Message' prefix
    # Standard eth_account sign_message adds the prefix, which breaks EIP-712
    signed_msg = Account._sign_hash(message_hash, private_key)

    # 6. Return Signature
    # Gnosis Safe `execTransaction` expects r || s || v
    # Account.signHash returns v in the signature object, or we can construct it
    return signed_msg.signature
