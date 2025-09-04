# Ads Placement Guardian (APG)

## Problem statement

There are a number of “spam/bot” and poor performing channels on YouTube, causing customers to spends large amounts of money on YouTube video campaigns on channels that do not drive results.

Clients need a solution that can quickly and automatically keep on top of poor performing channels or potential “spam/bot” channels and exclude them from their entire account on a regular basis.

## Solution

A Google Cloud based solution for excluding YouTube channels at an account level, based on a set of criteria defined by the client. A client can select a set of filters within their Google Ads data (such as low conversions, high CPMs or no traffic etc.) and then apply a set of YouTube filters against channel statistic (such as subscriber count, video views, language etc.) and exclude specific channels that do not meet the performance requirements.

The tool will display all the merged data, exclusions available and can be scheduled to automatically run the process on a regular basis to keep up with any new channels or campaigns that fall outside of the required performance.


## Deliverable (implementation)

Web application that can be used for performing ad-hoc placement exclusions as well as scheduling tasks.

## Deployment

### Prerequisites

1. Standard access to Google Ads account(s):
    - person responsible for deploying APG should have *Standard* access to an MCC account.
1. Credentials for Google Ads API access which stored in `google-ads.yaml`.
   See details [here](https://github.com/google/ads-api-report-fetcher/blob/main/docs/how-to-authenticate-ads-api.md).
1. A Google Cloud project with billing account attached.

### Installation

The primary installation method deploys APG into Google Cloud.
The procedure automates deploying all required components to the Cloud.

> For local deployment please refer to [local deployment guide](docs/run-cpr-locally.md).

1. First you need to clone the repo in Cloud Shell:

```
git clone https://github.com/google-marketing-solutions/ads_placement_guardian.git
```

1. Go to the repo folder: `cd ads_placement_guardian/`

1. Optionally put your `google-ads.yaml` there or be ready to provide all Google Ads API credentials

1. Optionally adjust settings in `gcp/settings.ini`

1. Run installation:

```
./gcp/install.sh deploy_all
```

This will deploy APG to Google Appengine and create all necessary components (cloud functions, PubSub topics, Datastore, etc.).

### Usage

After Google cloud installation is completed, you'll be presented with a URL when Ads Placement Guardian is running.

Alternatively you can open `default` services in [Appengine Services](https://corp.google.com/appengine/services) to access the application.
> If you changed `service` name in look for this service name in Appengine.

### Upgrade

1. Open Google Cloud Shell.
1. Ensure that you are in the `ads_placement_guardian` folder.
1. Run upgrade command

```bash
./gcp/upgrade.sh
```

## Disclaimer
This is not an officially supported Google product.
