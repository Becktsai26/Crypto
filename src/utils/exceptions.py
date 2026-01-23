class ApiException(Exception):
    """Base exception for API related errors."""
    pass

class NotionApiException(Exception):
    """Exception raised for errors in Notion API calls."""
    pass
