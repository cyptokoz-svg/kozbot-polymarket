"""
Basic unit tests for validators and core functionality
Run with: pytest test_validators.py -v
"""
import pytest
from validators import (
    validate_price,
    validate_size,
    validate_token_id,
    validate_market_data,
    ValidationError
)

class TestValidatePrice:
    """Test price validation"""
    
    def test_valid_price(self):
        assert validate_price(0.5) == 0.5
        assert validate_price(0.001) == 0.001
        assert validate_price(1.0) == 1.0
        assert validate_price(0.9999) == 0.9999
    
    def test_invalid_price_negative(self):
        with pytest.raises(ValidationError, match="must be > 0"):
            validate_price(-0.1)
    
    def test_invalid_price_zero(self):
        with pytest.raises(ValidationError, match="must be > 0"):
            validate_price(0)
    
    def test_invalid_price_too_high(self):
        with pytest.raises(ValidationError, match="must be <= 1"):
            validate_price(1.5)
    
    def test_invalid_price_non_numeric(self):
        with pytest.raises(ValidationError, match="must be numeric"):
            validate_price("0.5")

class TestValidateSize:
    """Test size validation"""
    
    def test_valid_size(self):
        assert validate_size(10.0) == 10.0
        assert validate_size(0.0001) == 0.0001
        assert validate_size(100) == 100.0
    
    def test_invalid_size_too_small(self):
        with pytest.raises(ValidationError, match="must be >="):
            validate_size(0.00001)
    
    def test_invalid_size_negative(self):
        with pytest.raises(ValidationError, match="must be >="):
            validate_size(-10)
    
    def test_invalid_size_non_numeric(self):
        with pytest.raises(ValidationError, match="must be numeric"):
            validate_size("10")

class TestValidateTokenId:
    """Test token ID validation"""
    
    def test_valid_token_id(self):
        token_id = "12345678901234567890"
        assert validate_token_id(token_id) == token_id
    
    def test_valid_token_id_large(self):
        token_id = "100088908078271870121265129190976197106091878586579358880564801094743118909157"
        assert validate_token_id(token_id) == token_id
    
    def test_invalid_token_id_empty(self):
        with pytest.raises(ValidationError, match="is required"):
            validate_token_id("")
    
    def test_invalid_token_id_none(self):
        with pytest.raises(ValidationError, match="is required"):
            validate_token_id(None)
    
    def test_invalid_token_id_non_numeric(self):
        with pytest.raises(ValidationError, match="must be numeric string"):
            validate_token_id("abc123")
    
    def test_invalid_token_id_too_short(self):
        with pytest.raises(ValidationError, match="too short"):
            validate_token_id("123")

class TestValidateMarketData:
    """Test market data validation"""
    
    def test_valid_market_data(self):
        market_data = {
            "slug": "btc-updown-15m-1234567890",
            "clobTokenIds": ["token1", "token2"],
            "strike": 78000.0
        }
        result = validate_market_data(market_data)
        assert result == market_data
    
    def test_invalid_market_data_none(self):
        with pytest.raises(ValidationError, match="is required"):
            validate_market_data(None)
    
    def test_invalid_market_data_not_dict(self):
        with pytest.raises(ValidationError, match="must be dict"):
            validate_market_data("not a dict")
    
    def test_invalid_market_data_missing_slug(self):
        market_data = {
            "clobTokenIds": ["token1", "token2"]
        }
        with pytest.raises(ValidationError, match="missing required fields"):
            validate_market_data(market_data)
    
    def test_invalid_market_data_missing_tokens(self):
        market_data = {
            "slug": "btc-updown-15m-1234567890"
        }
        with pytest.raises(ValidationError, match="missing required fields"):
            validate_market_data(market_data)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
