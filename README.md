# Tempo: Time keeping and invoicing app
```Tempo``` is a lightweight, efficient time-keeping and invoicing application built with FastAPI, SQLModel, and Jinja.

## Installation
Clone the repository and install the dependencies:
```
git clone https://github.com/rscheeler/tempo.git
cd tempo
pip install -r requirements.txt
```

## Setup
Create a .env file in the root directory using the template provided below:

```
COMPANY_NAME="Your Company"
COMPANY_ADDRESS="123 Business St."
COMPANY_PHONE="(555) 555-5555"
BILLING_EMAIL="billing@example.com"
COMPANY_CODE="YC"
DB_URL="sqlite:///./tempo.db"
LOGO=""
FAVICON=""
```
Note: For DB_URL, the default above uses SQLite, which requires no extra server setup. If you are using PostgreSQL or MySQL, update this string with your connection credentials.

## Branding
To customize the app with your own business branding:

Place your logo.png and favicon.ico in the static/user_assets/ folder.

Update the LOGO and FAVICON in your .env file to match your filenames.

## Running the Server
```
cd tempo
uvicorn main:app --reload
```
Navigate to the uvicorn port in your browser to get started.