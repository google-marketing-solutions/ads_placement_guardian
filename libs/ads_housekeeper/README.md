# Google Ads Housekeeper

## Problem statement

Managing Google Ads entities that can be excluded is a complex task which requires
implementing many moving parts: parsing the rules, applying them, saving, updating,
scheduling tasks and many more.

## Solution

Ads Housekeeper simplifies tasks related to managing excludable entities
(placements, keywords, search terms, ads, etc) based on a set of custom rules.

## Deliverable (implementation)

The library provides `googleads_housekeeper` module you can using in your projects
which abstracts the following aspects:
* Applying rules that identify entities for modification
* Creating and managing tasks with aforementioned with built-in persistence mechanism
* Sending notifications to a channel of your choice
* Sending message to message broker of your choice

## Deployment

### Prerequisites

1. Python 3.9+
1. Google Ads API access and [google-ads.yaml](https://github.com/google/ads-api-report-fetcher/blob/main/docs/how-to-authenticate-ads-api.md#setting-up-using-google-adsyaml) file - follow documentation on [API authentication](https://github.com/google/ads-api-report-fetcher/blob/main/docs/how-to-authenticate-ads-api.md).

### Installation

```
pip install google-ads-housekeeper
```

### Usage

```
from googleads_housekeeper import bootstrap
from googleads_housekeeper.domain import commands

# initialiaze message bus
bus = bootstrap.bootstrap()

# execute command
task_id = 1
cmd = commands.RunTask(task_id)
bus.handle(cmd)
```


## Disclaimer
This is not an officially supported Google product.
