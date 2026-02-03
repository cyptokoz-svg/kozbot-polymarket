"""
Input validation utilities for trading bot
防止无效数据导致错误交易
"""
import logging
from typing import Optional, Any, Dict

logger = logging.getLogger(__name__)

class ValidationError(ValueError):
    """Validation error for invalid inputs"""
    pass

def validate_price(price: float, name: str = "price") -> float:
    """
    Validate price is in valid range (0, 1]
    
    Args:
        price: Price to validate
        name: Name for error messages
        
    Returns:
        Validated and rounded price
        
    Raises:
        ValidationError: If price is invalid
    """
    if not isinstance(price, (int, float)):
        raise ValidationError(f"{name} must be numeric, got {type(price)}")
    
    if price <= 0:
        raise ValidationError(f"{name} must be > 0, got {price}")
    
    if price > 1:
        raise ValidationError(f"{name} must be <= 1 for prediction markets, got {price}")
    
    return round(price, 4)

def validate_size(size: float, min_size: float = 0.0001) -> float:
    """
    Validate order size
    
    Args:
        size: Order size in shares
        min_size: Minimum allowed size
        
    Returns:
        Validated size
        
    Raises:
        ValidationError: If size is invalid
    """
    if not isinstance(size, (int, float)):
        raise ValidationError(f"size must be numeric, got {type(size)}")
    
    if size < min_size:
        raise ValidationError(f"size must be >= {min_size}, got {size}")
    
    if size > 1000000:
        logger.warning(f"Unusually large size: {size}")
    
    return round(size, 4)

def validate_token_id(token_id: Any) -> str:
    """
    Validate token ID format
    
    Args:
        token_id: Token ID to validate
        
    Returns:
        Validated token ID as string
        
    Raises:
        ValidationError: If token_id is invalid
    """
    if not token_id:
        raise ValidationError("token_id is required")
    
    token_str = str(token_id)
    
    # Polymarket token IDs are large integers as strings
    if not token_str.isdigit():
        raise ValidationError(f"token_id must be numeric string, got: {token_str[:50]}")
    
    if len(token_str) < 10:
        raise ValidationError(f"token_id too short: {token_str}")
    
    return token_str

def validate_market_data(market_data: Optional[Dict]) -> Dict:
    """
    Validate market data has required fields
    
    Args:
        market_data: Market data dictionary
        
    Returns:
        Validated market data
        
    Raises:
        ValidationError: If required fields missing
    """
    if not market_data:
        raise ValidationError("market_data is required")
    
    if not isinstance(market_data, dict):
        raise ValidationError(f"market_data must be dict, got {type(market_data)}")
    
    required_fields = ["slug", "clobTokenIds"]
    missing = [f for f in required_fields if f not in market_data]
    
    if missing:
        raise ValidationError(f"market_data missing required fields: {missing}")
    
    return market_data

def sanitize_log_data(data: Any, max_length: int = 200) -> str:
    """
    Sanitize data for logging, removing sensitive information
    
    Args:
        data: Data to sanitize
        max_length: Maximum string length
        
    Returns:
        Sanitized string safe for logging
    """
    if data is None:
        return "None"
    
    # Convert to string
    data_str = str(data)
    
    # Sensitive patterns to mask
    sensitive_patterns = [
        ("PRIVATE_KEY", "***PRIVATE_KEY***"),
        ("API_SECRET", "***API_SECRET***"),
        ("API_KEY", "***API_KEY***"),
        ("PASSWORD", "***PASSWORD***"),
        ("PASSPHRASE", "***PASSPHRASE***"),
    ]
    
    for pattern, replacement in sensitive_patterns:
        if pattern in data_str.upper():
            # If it looks like JSON/dict
            if "{" in data_str and ":" in data_str:
                # Mask the value after the key
                import re
                data_str = re.sub(
                    rf'(["\']?{pattern}["\']?\s*[:=]\s*)[^,}}\]]+',
                    rf'\1"{replacement}"',
                    data_str,
                    flags=re.IGNORECASE
                )
            else:
                # Simple replacement
                data_str = replacement
    
    # Truncate if too long
    if len(data_str) > max_length:
        data_str = data_str[:max_length] + "..."
    
    return data_str
