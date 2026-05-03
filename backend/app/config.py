from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://fileflow:fileflow@localhost:5432/fileflow"

    # Security
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_expiry_days: int = 7

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""
    google_callback_url: str = "http://localhost:3001/api/auth/google/callback"

    # Microsoft OAuth (login)
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_callback_url: str = "http://localhost:3001/api/auth/microsoft/callback"

    # OneDrive OAuth (storage)
    onedrive_client_id: str = ""
    onedrive_client_secret: str = ""
    onedrive_callback_url: str = "http://localhost:3001/api/auth/onedrive/callback"

    # Dropbox OAuth
    dropbox_app_key: str = ""
    dropbox_app_secret: str = ""
    dropbox_callback_url: str = "http://localhost:3001/api/auth/dropbox/callback"

    # Google Drive OAuth (storage – separate from Google login)
    google_drive_callback_url: str = "http://localhost:3001/api/auth/googledrive/callback"

    # Apple OAuth
    # client_id  = Services ID (e.g. com.example.fileflow.signin)
    # team_id    = 10-char Apple Developer Team ID
    # key_id     = 10-char Key ID from the .p8 private key
    # private_key = full PEM content of the .p8 file (newlines as \n)
    apple_client_id: str = ""
    apple_team_id: str = ""
    apple_key_id: str = ""
    apple_private_key: str = ""
    apple_callback_url: str = "http://localhost:3001/api/auth/apple/callback"

    # Upload
    # Files larger than this (in MB) use multipart/session-based upload APIs
    multipart_upload_threshold_mb: int = 5

    # Server
    port: int = 3001
    frontend_url: str = "http://localhost"


settings = Settings()
