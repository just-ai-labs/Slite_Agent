import logging
import time
from functools import wraps
from typing import Any, Callable, Dict, Optional
import json
from datetime import datetime
import os
from cachetools import TTLCache

# Configure logging
def setup_logging(log_file: str = 'slite_integration.log'):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger('slite_integration')

logger = setup_logging()

# Cache configuration
note_cache = TTLCache(maxsize=100, ttl=300)  # Cache for 5 minutes
folder_cache = TTLCache(maxsize=50, ttl=600)  # Cache for 10 minutes

class RateLimiter:
    def __init__(self, max_requests: int = 60, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []

    def can_make_request(self) -> bool:
        current_time = time.time()
        # Remove old requests
        self.requests = [req_time for req_time in self.requests 
                        if current_time - req_time < self.time_window]
        
        if len(self.requests) < self.max_requests:
            self.requests.append(current_time)
            return True
        return False

    def wait_for_next_slot(self):
        while not self.can_make_request():
            time.sleep(1)

rate_limiter = RateLimiter()

def retry_with_backoff(retries: int = 3, backoff_factor: float = 0.5):
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            retry_count = 0
            while retry_count < retries:
                try:
                    rate_limiter.wait_for_next_slot()
                    return func(*args, **kwargs)
                except Exception as e:
                    retry_count += 1
                    if retry_count == retries:
                        logger.error(f"Failed after {retries} retries: {str(e)}")
                        raise
                    wait_time = backoff_factor * (2 ** (retry_count - 1))
                    logger.warning(f"Attempt {retry_count} failed: {str(e)}. Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
            return None
        return wrapper
    return decorator

class Cache:
    def __init__(self, cache_file: str = 'cache.json'):
        self.cache_file = cache_file
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                # Clean expired entries
                current_time = datetime.now().timestamp()
                cache_data = {
                    k: v for k, v in cache_data.items()
                    if current_time - v.get('timestamp', 0) < v.get('ttl', 300)
                }
                return cache_data
            except Exception as e:
                logger.error(f"Error loading cache: {str(e)}")
                return {}
        return {}

    def _save_cache(self):
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f)
        except Exception as e:
            logger.error(f"Error saving cache: {str(e)}")

    def get(self, key: str) -> Optional[Any]:
        if key in self.cache:
            entry = self.cache[key]
            if datetime.now().timestamp() - entry['timestamp'] < entry['ttl']:
                logger.debug(f"Cache hit for key: {key}")
                return entry['data']
            else:
                del self.cache[key]
                self._save_cache()
        return None

    def set(self, key: str, value: Any, ttl: int = 300):
        self.cache[key] = {
            'data': value,
            'timestamp': datetime.now().timestamp(),
            'ttl': ttl
        }
        self._save_cache()

    def clear(self):
        self.cache = {}
        self._save_cache()

class APIError(Exception):
    """Base exception for API errors"""
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class RateLimitError(APIError):
    """Raised when API rate limit is exceeded"""
    pass

class AuthenticationError(APIError):
    """Raised when API authentication fails"""
    pass

class NotFoundError(APIError):
    """Raised when a resource is not found"""
    pass

class ValidationError(APIError):
    """Raised when input validation fails"""
    pass
