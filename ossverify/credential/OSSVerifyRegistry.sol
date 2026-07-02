// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title OSSVerify Credential Registry
/// @notice Stores SHA-256 hashes of Verifiable Credentials on Polygon Amoy testnet.
///         Anyone can verify a credential hash was registered at a specific time.
contract OSSVerifyRegistry {
    /// credentialHash → block.timestamp at registration time (0 = not registered)
    mapping(bytes32 => uint256) public timestamps;

    event HashStored(bytes32 indexed credentialHash, uint256 timestamp);

    /// @notice Register a credential hash. Reverts if already registered.
    function storeHash(bytes32 _hash) external {
        require(timestamps[_hash] == 0, "OSSVerify: hash already registered");
        timestamps[_hash] = block.timestamp;
        emit HashStored(_hash, block.timestamp);
    }

    /// @notice Return the registration timestamp (0 if not registered).
    function getTimestamp(bytes32 _hash) external view returns (uint256) {
        return timestamps[_hash];
    }
}
