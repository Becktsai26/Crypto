class AppError(Exception):
    """所有應用程式自定義錯誤的基類"""
    pass

class ConfigurationError(AppError):
    """設定錯誤 (如缺少環境變數)"""
    pass

class DataSourceError(AppError):
    """資料來源錯誤 (如 Bybit API 連線失敗)"""
    pass

class DataDestinationError(AppError):
    """資料寫入錯誤 (如 Notion API 失敗)"""
    pass

class BusinessLogicError(AppError):
    """業務邏輯錯誤 (如重複交易檢查失敗)"""
    pass
