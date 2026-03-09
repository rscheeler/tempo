import os

from dotenv import find_dotenv, load_dotenv

# Load .env
load_dotenv(find_dotenv())


class Settings:
    COMPANY_NAME: str = os.getenv("COMPANY_NAME")
    COMPANY_CODE: str = os.getenv("COMPANY_CODE")
    COMPANY_ADDRESS: str = os.getenv("COMPANY_ADDRESS")
    COMPANY_PHONE: str = os.getenv("COMPANY_PHONE")
    BILLING_EMAIL: str = os.getenv("BILLING_EMAIL")
    DB_URL: str = os.getenv("DB_URL")
    LOGO: str = os.getenv("LOGO")
    FAVICON: str = os.getenv("FAVICON")


settings = Settings()
