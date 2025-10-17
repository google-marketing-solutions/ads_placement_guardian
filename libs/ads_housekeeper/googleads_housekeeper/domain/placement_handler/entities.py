# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Contains classes and function to work with Placements from Google Ads API."""

# pylint: disable=C0330, g-bad-import-order, g-multiple-import

from __future__ import annotations

import dataclasses
import datetime
import uuid

import gaarf

from googleads_housekeeper.domain.core import entity
from googleads_housekeeper.services import enums


class Placements(entity.ExcludableEntity):
  """Contains placement meta information and it's performance.

  Placements is a wrapper on BaseQuery that builds GAQL query (located in
  `query_text` attribute) based on provided and validated inputs.

  Attributes:
    query_text: Gaarf query to be sent to Google Ads API.
  """

  _TODAY = datetime.datetime.today()
  _START_DATE = _TODAY - datetime.timedelta(days=7)
  _END_DATE = _TODAY - datetime.timedelta(days=1)
  _CAMPAIGN_TYPES = {c.name for c in enums.CampaignTypeEnum}
  _PLACEMENT_TYPES = {p.name for p in enums.PlacementTypeEnum}
  _NON_EXCLUDABLE_PLACEMENTS = (
    'youtube.com',
    'mail.google.com',
    'adsenseformobileapps.com',
  )
  base_query_text = """
        SELECT
            customer.id AS customer_id,
            campaign.id AS campaign_id,
            campaign.advertising_channel_type AS campaign_type,
            ad_group.id AS ad_group_id,
            {extra_dimensions}
            {placement_level_granularity}.placement AS placement,
            {placement_level_granularity}.placement_type AS placement_type,
            {placement_level_granularity}.display_name AS name,
            {metrics}
        FROM {placement_level_granularity}
        WHERE segments.date >= "{start_date}"
            AND segments.date <= "{end_date}"
            AND {placement_level_granularity}.placement_type IN
                ("{placement_types}")
            AND {placement_level_granularity}.target_url NOT IN
                ("{non_excludable_placements}")
            AND campaign.advertising_channel_type IN ("{campaign_types}")
            AND {filters}
        ORDER BY metrics.cost_micros DESC
        {limit}
        """

  def __init__(
    self,
    placement_types: tuple[str, ...] | None = None,
    campaign_types: tuple[str, ...] | None = None,
    placement_level_granularity: str = 'group_placement_view',
    start_date: str = _START_DATE.strftime('%Y-%m-%d'),
    end_date: str = _END_DATE.strftime('%Y-%m-%d'),
    metrics: set[str] | None = None,
    dimensions: set[str] | None = None,
    filters: set[str] | None = None,
    limit: int | None = 0,
  ):
    """Creates Gaarf query for fetching placements data.

    Args:
      placement_types: List of placement types that need to be fetched
        for exclusion.
      campaign_types: List of campaign types that need to be fetched.
      placement_level_granularity: API Resource to fetch data from.
      start_date: Start_date of the period.
      end_date: Start_date of the period.
      metrics: Metrics to be fetched.
      dimensions: Dimensions to be fetched.
      filters: Filters to be applied during fetching.
      limit: Number of rows to return in response.

    Raises:
      ValueError:
        If campaign_type, placement_type or placement_level_granularity
        are incorrect.
    """
    if campaign_types:
      if isinstance(campaign_types, str):
        campaign_types = tuple(campaign_types.split(','))
      if wrong_types := set(campaign_types).difference(self._CAMPAIGN_TYPES):
        raise ValueError('Wrong campaign type(s): ', ', '.join(wrong_types))
      self.campaign_types = '","'.join(campaign_types)
    else:
      self.campaign_types = '","'.join(self._CAMPAIGN_TYPES)
    if placement_types:
      if isinstance(placement_types, str):
        placement_types = tuple(placement_types.split(','))
      if wrong_types := set(placement_types).difference(self._PLACEMENT_TYPES):
        raise ValueError('Wrong placement(s): ', ', '.join(wrong_types))
      self.placement_types = '","'.join(placement_types)
    else:
      self.placement_types = '","'.join(self._PLACEMENT_TYPES)

    if placement_level_granularity not in (
      'detail_placement_view',
      'group_placement_view',
    ):
      raise ValueError(
        "Only 'detail_placement_view' or 'group_placement_view' "
        'can be specified!'
      )
    self.placement_level_granularity = placement_level_granularity

    self.validate_dates(start_date, end_date)
    self.start_date = start_date
    self.end_date = end_date
    self.non_excludable_placements = '","'.join(self._NON_EXCLUDABLE_PLACEMENTS)
    self.parent_url = (
      'group_placement_target_url'
      if self.placement_level_granularity == 'detail_placement_view'
      else 'target_url'
    )
    if not metrics:
      metrics = {
        'metrics.clicks AS clicks',
      }
    if dimensions:
      self.extra_dimensions = (
        ',\n'.join(dimensions)
        if len(dimensions) > 1
        else f'{dimensions.pop()},\n'
      )
    elif limit and (limit := int(limit)):
      metrics.update(self._add_extra_metrics())
      self.extra_dimensions = self._add_extra_dimensions()
    else:
      self.extra_dimensions = ''
    metrics.add('metrics.cost_micros / 1e6 AS cost')

    self.metrics = ',\n'.join(metrics)
    if not filters:
      filters = {
        'metrics.clicks > 0',
        'metrics.impressions > 0',
        'metrics.cost_micros > 0',
      }
    self.filters = ' AND '.join(filters)
    self.limit = '' if not limit else f'LIMIT {limit}'
    self.query_text = self.base_query_text.format(**self.__dict__)

  def _add_extra_metrics(self) -> str[str]:
    return {
      'metrics.clicks AS clicks',
      'metrics.impressions AS impressions',
      'metrics.cost_micros / 1e6 AS cost',
      'metrics.conversions AS conversions',
      'metrics.video_trueview_views AS video_views',
      'metrics.interactions AS interactions',
      'metrics.all_conversions AS all_conversions',
      'metrics.all_conversions_value AS all_conversions_value',
      'metrics.view_through_conversions AS view_through_conversions',
      'metrics.conversions_value AS conversions_value',
    }

  def _add_extra_dimensions(self) -> str:
    return f"""
            customer.descriptive_name AS account_name,
            campaign.name AS campaign_name,
            ad_group.name AS ad_group_name,
            {self.placement_level_granularity}.{self.parent_url} AS base_url,
            {self.placement_level_granularity}.target_url AS url,
            """

  def validate_dates(self, start_date: str, end_date: str) -> None:
    """Checks whether provides start and end dates are valid.

    Args:
      start_date: Date in "YYYY-MM-DD" format.
      end_date: Date in "YYYY-MM-DD" format.

    Raises:
      ValueError:
        if start or end_date have incorrect format or start_date greater
        than end_date.
    """
    if not self.is_valid_date(start_date):
      raise ValueError(f'Invalid start_date: {start_date}')

    if not self.is_valid_date(end_date):
      raise ValueError(f'Invalid end_date: {end_date}')

    if datetime.datetime.strptime(
      start_date, '%Y-%m-%d'
    ) > datetime.datetime.strptime(end_date, '%Y-%m-%d'):
      raise ValueError(
        f'start_date cannot be greater than end_date: {start_date} > {end_date}'
      )

  def is_valid_date(self, date_string: str) -> bool:
    """Validates date.

    Args:
      date_string: Date to be validated.

    Returns:
      Whether or not the date is a string in "YYYY-MM-DD" format.

    Raises:
      ValueError: If string format is incorrect.
    """
    try:
      datetime.datetime.strptime(date_string, '%Y-%m-%d')
      return True
    except ValueError:
      return False


class PlacementsConversionSplit(Placements):
  """Placement conversion performance by each conversion name.

  Attributes:
    query_text: Gaarf query to be sent to Google Ads API.
  """

  _TODAY = datetime.datetime.today()
  _START_DATE = _TODAY - datetime.timedelta(days=7)
  _END_DATE = _TODAY - datetime.timedelta(days=1)

  base_query_text = """
        SELECT
            campaign.advertising_channel_type AS campaign_type,
            ad_group.id AS ad_group_id,
            segments.conversion_action_name AS conversion_name,
            {placement_level_granularity}.placement_type AS placement_type,
            {placement_level_granularity}.placement AS placement,
            metrics.conversions AS conversions,
            metrics.all_conversions AS all_conversions
        FROM {placement_level_granularity}
        WHERE segments.date >= "{start_date}"
            AND segments.date <= "{end_date}"
            AND {placement_level_granularity}.placement_type IN
                ("{placement_types}")
            AND {placement_level_granularity}.target_url NOT IN
                ("{non_excludable_placements}")
            AND campaign.advertising_channel_type IN ("{campaign_types}")
    """

  def __init__(
    self,
    placement_types: tuple[str, ...] | None = None,
    campaign_types: tuple[str, ...] | None = None,
    placement_level_granularity: str = 'group_placement_view',
    start_date: str = _START_DATE.strftime('%Y-%m-%d'),
    end_date: str = _END_DATE.strftime('%Y-%m-%d'),
  ) -> None:
    """Creates Gaarf query for fetching placements conversion split data.

    Args:
      placement_types: List of placement types that need to be fetched
        for exclusion.
      campaign_types: List of campaign types that need to be fetched.
      placement_level_granularity: API Resource to fetch data from.
      start_date: Start_date of the period.
      end_date: Start_date of the period.
    """
    super().__init__(
      placement_types,
      campaign_types,
      placement_level_granularity,
      start_date,
      end_date,
    )
    self.query_text = self.base_query_text.format(**self.__dict__)


class PlacementExclusionLists(gaarf.base_query.BaseQuery):
  """Contains Gaarf query for getting placement exclusion lists.

  Attributes:
    query_text: Gaarf query to be sent to Google Ads API.
  """

  def __init__(self):
    """Creates Gaarf query for placement exclusion lists."""
    self.query_text = """
            SELECT
                shared_set.name AS name,
                shared_set.resource_name AS resource_name
            FROM shared_set
            WHERE shared_set.type = 'NEGATIVE_PLACEMENTS'
            AND shared_set.status = 'ENABLED'
            AND shared_set.name LIKE 'CPR Negative placements list%'
        """


def _add_exclusion_condition(query_text: str, condition: str) -> str:
  """
  Adds the exclusion condition right before the ORDER BY clause.
  """
  return query_text.replace('ORDER BY', f' AND {condition}\nORDER BY')


class AlreadyExcludedPlacements(gaarf.base_query.BaseQuery):
  """Contains Gaarf query for negative placement criteria.

  Negative placements can be specified on multiple levels (ACCOUNT, CAMPAIGN,
  AD_GROUP). AlreadyExcludedPlacements builds the query depending on the
  specified level.

  Attributes:
    query_text: Gaarf query to be sent to Google Ads API.
  """

  _PLACEMENT_TYPES = '","'.join(
    [
      'PLACEMENT',
      'YOUTUBE_CHANNEL',
      'YOUTUBE_VIDEO',
      'MOBILE_APPLICATION',
      'MOBILE_APP_CATEGORY',
      'WEBPAGE',
    ]
  )

  base_query_text = """
        SELECT
            {level}.id AS level_id,
            {criterion_resource_name}.placement.url AS website_url,
            {criterion_resource_name}.mobile_application.app_id AS app_id,
            {criterion_resource_name}.youtube_video.video_id AS video_id,
            {criterion_resource_name}.youtube_channel.channel_id AS channel_id
        FROM {criterion_resource_name}
        WHERE {criterion_resource_name}.type IN ("{placement_types}")
        ORDER BY {criterion_resource_name}.youtube_video.video_id,
                 {criterion_resource_name}.youtube_channel.channel_id,
                 {criterion_resource_name}.mobile_application.app_id
    """

  def __init__(self, exclusion_level: enums.ExclusionLevelEnum) -> None:
    """Creates Gaarf query based on specified exclusion level."""
    if exclusion_level == enums.ExclusionLevelEnum.ACCOUNT:
      self.query_text = self.base_query_text.format(
        level='customer',
        criterion_resource_name='customer_negative_criterion',
        placement_types=self._PLACEMENT_TYPES,
      )
    elif exclusion_level == enums.ExclusionLevelEnum.CAMPAIGN:
      self.query_text = self.base_query_text.format(
        level='campaign',
        criterion_resource_name='campaign_criterion',
        placement_types=self._PLACEMENT_TYPES,
      )
      self.query_text = _add_exclusion_condition(
        self.query_text, 'campaign_criterion.negative = true'
      )
    elif exclusion_level == enums.ExclusionLevelEnum.AD_GROUP:
      self.query_text = self.base_query_text.format(
        level='ad_group',
        criterion_resource_name='ad_group_criterion',
        placement_types=self._PLACEMENT_TYPES,
      )
      self.query_text = _add_exclusion_condition(
        self.query_text, 'ad_group_criterion.negative = true'
      )


@dataclasses.dataclass
class AllowlistedPlacement:
  """Contains information on allowlisting status of a given placement.

  Attributes:
    type: Placement type (i.e website or YouTube channel).
    name: Name of a placement (i.e. website url, channel id)
    account_id: Account where this placement is allowlisted.
    id: Unique identifier of the allowlisted placement.
  """

  type: enums.PlacementTypeEnum
  name: str
  account_id: str
  id: str = dataclasses.field(default_factory=lambda: str(uuid.uuid4()))
