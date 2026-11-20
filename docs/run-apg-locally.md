# How to run Ads Placement Guardian locally

There are two main ways you can run Ads Placement Guardian locally:

* Run in containers
* Run as a standalone script


## Run in containers

### Prerequisites

* Google Ads API access and [google-ads.yaml](https://github.com/google/ads-api-report-fetcher/blob/main/docs/how-to-authenticate-ads-api.md#setting-up-using-google-adsyaml) file - follow documentation on [API authentication](https://github.com/google/ads-api-report-fetcher/blob/main/docs/how-to-authenticate-ads-api.md).
* API Key to access YouTube Data API -  more at [Setting up API keys](https://support.google.com/googleapi/answer/6158862?hl=en).
* [Docker Compose](https://docs.docker.com/compose/install/) installed.
* Node.js and NPM installed

### Installation & usage

1. Build frontend

    ```
    ./gcp/install.sh build_frontend
    ```

2. Expose required environmental variables (including a database password and shared `/api/*` key):

    ```
    export GOOGLE_ADS_YAML=/path/to/google-ads.yaml
    export YOUTUBE_DATA_API_KEY="YOUR_DATA_API_KEY"
    export APG_DB_PASSWORD="$(openssl rand -hex 32)"
    export APG_API_KEY="$(openssl rand -hex 32)"
    ```

3. Start containers

    ```
    docker compose up -d
    ```

It will create 3 services:

* `cpr_backend` - main application to perform exclusions and save tasks
* `cpr_scheduler` - execute tasks based on the schedule
* `cpr_db` - database to store created tasks

Open [http://localhost:5000](http://localhost:5000) and start using Ads Placement Guardian.

### Run as a standalone script

### Prerequisites

* Google Ads API access and [google-ads.yaml](https://github.com/google/ads-api-report-fetcher/blob/main/docs/how-to-authenticate-ads-api.md#setting-up-using-google-adsyaml) file - follow documentation on [API authentication](https://github.com/google/ads-api-report-fetcher/blob/main/docs/how-to-authenticate-ads-api.md).
* API Key to access YouTube Data API -  more at [Setting up API keys](https://support.google.com/googleapi/answer/6158862?hl=en).
* Python3.9+ and pip installed
* Node.js and NPM installed

### Installation & usage

1. Build frontend

    ```
    ./gcp/install.sh build_frontend
    ```

2. Install dependencies:

    ```
    pip install -r backend/requirements.txt
    ```

3. Expose environmental variables:

    ```
    export GOOGLE_ADS_YAML=/path/to/google-ads.yaml
    export YOUTUBE_DATA_API_KEY="YOUR_DATA_API_KEY"
    export ADS_HOUSEKEEPER_DEPLOYMENT_MODE="Dev"
    ```

4. Start Flask server

    ```
    python backend/server.py
    ```


Open [http://localhost:5000](http://localhost:5000) and start using Ads Placement Guardian.
