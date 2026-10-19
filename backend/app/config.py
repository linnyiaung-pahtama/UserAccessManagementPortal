from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./uam.db"
    # SQL Server authentication (username + password). Kept out of DATABASE_URL so the password needs
    # no URL-encoding. Leave empty to use Windows authentication (the account running the portal).
    database_user: str = ""
    database_password: str = ""

    # Public base URL of the portal. This is the OIDC "iss" value and the base of
    # every OIDC endpoint, so client systems must be able to reach it.
    issuer: str = "http://localhost:5173"
    # Where the React app lives (login page, access-denied page).
    frontend_url: str = "http://localhost:5173"
    # Optional: path to the built React app (frontend/dist) to serve it from FastAPI.
    frontend_dist: str = "../frontend/dist"

    session_cookie_name: str = "uam_session"
    session_ttl_minutes: int = 480
    cookie_secure: bool = False  # set True in production (HTTPS)

    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    auth_code_ttl_seconds: int = 120

    keys_dir: str = "./keys"

    # Initial administrator, created on first start when the database has no users.
    admin_username: str = "admin"
    admin_email: str = "admin@pahtama.com"
    admin_password: str | None = None

    # Users created or edited in the portal must have an email at this company domain.
    allowed_email_domain: str = "pahtama.com"

    # Mail server for emailing admins about new access requests (mailer.py). Leave SMTP_HOST empty to send nothing:
    # requests still appear on the Access requests page.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""  # defaults to "Access Portal <SMTP_USER>"
    smtp_use_tls: bool = True  # STARTTLS (port 587)

    @field_validator("issuer", "frontend_url")
    @classmethod
    def _strip_slash(cls, v: str) -> str:
        return v.rstrip("/")


settings = Settings()
