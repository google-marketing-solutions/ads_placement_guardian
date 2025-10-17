# Copyright 2024 Google LLC
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
"""Handles interacting with Google Ads API."""

# pylint: disable=C0330, g-bad-import-order, g-multiple-import

from __future__ import annotations

from collections.abc import Sequence

import gaarf
import numpy as np
import pandas as pd

from googleads_housekeeper.domain.core import exclusion_specification, task
from googleads_housekeeper.domain.placement_handler import entities
from googleads_housekeeper.services import enums

DIMENSIONS = {
  'account_name': 'customer.descriptive_name',
  'campaign_name': 'campaign.name',
  'ad_group_name': 'ad_group.name',
}

METRICS = [
  'clicks',
  'impressions',
  'cost',
  'conversions',
  'video_views',
  'interactions',
  'all_conversions',
  'view_through_conversions',
]

COMPOUND_METRICS = {
  'ctr': ['clicks', 'impressions'],
  'avg_cpc': ['cost', 'clicks'],
  'avg_cpm': ['cost', 'impressions'],
  'avg_cpv': ['cost', 'video_views'],
  'video_view_rate': ['video_views', 'impressions'],
  'interaction_rate': ['interactions', 'clicks'],
  'conversions_from_interactions_rate': ['conversions', 'interactions'],
  'cost_per_conversion': ['cost', 'conversions'],
  'cost_per_all_conversion': ['cost', 'all_conversions'],
  'all_conversion_rate': ['all_conversions', 'interactions'],
  'all_conversions_from_interactions_rate': [
    'all_conversions',
    'interactions',
  ],
}


class PlacementFetcher:
  """Handles fetching of placement data from Google Ads API.

  Attributes:
    report_fetcher: An instance of AdsReportFetcher to handle API requests.
  """

  def __init__(
    self, report_fetcher: gaarf.report_fetcher.AdsReportFetcher
  ) -> None:
    """Initializes PlacementFetcher.

    Args:
      report_fetcher: An instance of AdsReportFetcher to handle API requests.
    """
    self.report_fetcher = report_fetcher

  def get_placements_for_account(
    self,
    account: str,
    task_obj: task.Task,
    limit: int | None,
  ) -> gaarf.report.GaarfReport | None:
    """Gets placement data from a given account based on task definition.

    Args:
      account: Google Ads account to get data from.
      task_obj: A task defining parameters of fetching.
      limit: Whether to fetch all data or only a subset.

    Returns:
      Report with fetched placement data.
    """
    specification = (
      exclusion_specification.ExclusionSpecification.from_expression(
        task_obj.exclusion_rule
      )
    )
    runtime_options = specification.define_runtime_options()
    if not (
      placements := self._get_placement_performance_data(
        account, task_obj, limit
      )
    ):
      return None
    if runtime_options.is_conversion_query:
      if (
        placements_by_conversion_name
        := self._get_placement_conversion_split_data(account, task_obj)
      ):
        conversion_split_exclusion_specification = (
          exclusion_specification.ExclusionSpecification(
            specifications=[runtime_options.conversion_rules]
          )
        )
        placements_by_conversion_name = (
          conversion_split_exclusion_specification.apply_specifications(
            placements_by_conversion_name
          )
        )
        placements = self._join_conversion_split(
          placements,
          placements_by_conversion_name,
          runtime_options.conversion_name,
        )
      else:
        self._extend_placement_with_conversion_split_columns(
          placements=placements
        )
    return self._aggregate_placements(placements, task_obj.exclusion_level)

  def _get_placement_performance_data(
    self, account: str, task_obj: task.Task, limit: int | None
  ) -> gaarf.report.GaarfReport:
    """Gets placement performance data (clicks, impressions, etc.).

    Args:
      account: Google Ads account to get data from.
      task_obj: A task defining parameters of fetching.
      limit: Whether to fetch all data or only a subset.

    Returns:
      Report with fetched placement data.
    """
    placements = self._get_placement_data(
      task_obj=task_obj, account=account, limit=limit
    )
    if 'YOUTUBE_VIDEO' in task_obj.placement_types and (
      detail_placements := self._get_placement_data(
        task_obj=task_obj,
        account=account,
        placement_level_granularity='detail_placement_view',
        limit=limit,
      )
    ):
      placements = placements + detail_placements
    return placements

  def _get_placement_conversion_split_data(
    self, account: str, task_obj: task.Task
  ) -> gaarf.report.GaarfReport:
    """Gets placement conversion split data (conversion_name, conversions).

    Args:
      account: Google Ads account to get data from.
      task_obj: A task defining parameters of fetching.

    Returns:
      Report with fetched placement conversion split data.
    """
    placements = self._get_placement_data(
      task_obj=task_obj,
      account=account,
      query_class=entities.PlacementsConversionSplit,
    )
    if 'YOUTUBE_VIDEO' in task_obj.placement_types and (
      detail_placements := self._get_placement_data(
        task_obj=task_obj,
        account=account,
        query_class=entities.PlacementsConversionSplit,
      )
    ):
      placements = placements + detail_placements
    return placements

  def get_already_excluded_placements(
    self, account: str, exclusion_level: enums.ExclusionLevelEnum
  ) -> dict[str, list[str]]:
    """Fetches negative placement criteria from Google Ads account.

    Negative criteria are fetched based on specified exclusion level (
    ACCOUNT, CAMPAIGN, AD_GROUP).

    Args:
      account: Google Ads account to get data from.
      exclusion_level: Level of exclusion (ACCOUNT, CAMPAIGN, AD_GROUP).

    Returns:
      Mapping between entity_id from specified exclusion level to all
      negative criteria ids.
    """
    already_excluded_placements = self.report_fetcher.fetch(
      entities.AlreadyExcludedPlacements(exclusion_level), account
    )
    if not already_excluded_placements:
      return {}
    for row in already_excluded_placements:
      row['placement'] = (
        row.website_url or row.app_id or row.video_id or row.channel_id or ''
      )
    return already_excluded_placements.to_dict(
      key_column='level_id',
      value_column='placement',
      value_column_output='list',
    )

  def get_placement_exclusion_lists(
    self, customer_ids: Sequence[int]
  ) -> dict[str, str]:
    placement_exclusion_lists = self.report_fetcher.fetch(
      entities.PlacementExclusionLists(), customer_ids
    )
    return placement_exclusion_lists.to_dict(
      key_column='name',
      value_column='resource_name',
      value_column_output='scalar',
    )

  def _build_query_part(self, spec) -> tuple[str, str] | None:
    """Returns metrics and corresponding filters based on a specification."""
    if spec.name in METRICS:
      value = (
        int(float(spec.value) * 1e6) if spec.name == 'cost' else spec.value
      )
      name = f'{spec.name}_micros' if spec.name == 'cost' else spec.name
      return (
        f'metrics.{name} {spec.operator} {value}',
        self._build_metric(spec.name),
      )
    return None

  def _build_metric(self, metric_name: str) -> str:
    name = (
      f'{metric_name}_micros / 1e6' if metric_name == 'cost' else metric_name
    )
    return f'metrics.{name} AS {metric_name}'

  def _get_placement_data(
    self,
    task_obj: task.Task,
    account: str,
    query_class: gaarf.base_query.BaseQuery = entities.Placements,
    placement_level_granularity: str = 'group_placement_view',
    limit: int | None = None,
  ) -> gaarf.report.Report:
    """Helper method for building query and fetching data from Ads API.

    Args:
      task_obj: A Task that contains necessary data for building query.
      account: Google Ads account to fetch data from.
      query_class: Class defining which query will be built.
      placement_level_granularity: Resource name to get data from.
      limit: Whether to fetch all data or only a subset.

    Returns:
      Report containing placement performance data.
    """
    metrics: set[str] = set()
    filters: set[str] = set()
    dimensions: set[str] = set()
    if spec := exclusion_specification.ExclusionSpecification.from_expression(
      task_obj.exclusion_rule
    ):
      ads_specs = spec.ads_specs_entries.specifications
      for specs in ads_specs:
        for spec in specs:
          if compound_metrics := COMPOUND_METRICS.get(spec.name):
            for metric in compound_metrics:
              metrics.add(self._build_metric(metric))
          elif info := self._build_query_part(spec):
            ads_filter, ads_metric = info
            filters.add(ads_filter)
            metrics.add(ads_metric)
          elif dimension := DIMENSIONS.get(spec.name):
            dimensions.add(f'{dimension} AS {spec.name}')

    placement_query = query_class(
      placement_types=task_obj.placement_types,
      placement_level_granularity=placement_level_granularity,
      start_date=task_obj.start_date,
      end_date=task_obj.end_date,
      limit=limit,
      metrics=metrics,
      filters=filters,
      dimensions=dimensions,
    )
    return self.report_fetcher.fetch(placement_query, customer_ids=account)

  def _join_conversion_split(
    self,
    placements: gaarf.report.GaarfReport,
    placements_by_conversion_name: gaarf.report.GaarfReport,
    conversion_name: str,
  ) -> gaarf.report.GaarfReport:
    """Joins placements performance data with its conversion split data.

    Args:
      placements:
        Report with placement performance data.
      placements_by_conversion_name:
        Report with placements conversion split data.
      conversion_name:
        Conversion_name(s) that should be used to create a dedicated
        column in joined report.

    Returns:
      New report with extra conversion specific columns.
    """
    placements_by_conversion_name = placements_by_conversion_name.to_pandas()
    final_report_values = []
    for performance_data_row in placements:
      conversions, all_conversions = self._extract_conversion_split_metrics(
        placements_by_conversion_name,
        performance_data_row.ad_group_id,
        performance_data_row.placement,
        performance_data_row.placement_type,
      )
      final_report_values.append(
        performance_data_row.data
        + [conversion_name, conversions, all_conversions]
      )
    columns = placements.column_names + [
      'conversion_name',
      'custom_conversions',
      'custom_all_conversions',
    ]
    return gaarf.report.GaarfReport(
      results=final_report_values, column_names=columns
    )

  def _extract_conversion_split_metrics(
    self,
    placements_by_conversion_name: pd.DataFrame,
    ad_group_id: int,
    placement: str,
    placement_type: str,
  ) -> tuple[float, float]:
    """Checks for rows with provided ad_group_id, placement, placement_type.

    Args:
      placements_by_conversion_name: DataFrame with conversion split data.
      ad_group_id: Ad group id.
      placement: Name of placement.
      placement_type: Type of placement.

    Returns:
      Conversions and all_conversions satisfying the condition; if nothing is
        found provides 0 as a placeholder.
    """
    conversion_row_filter = (
      (placements_by_conversion_name.ad_group_id == ad_group_id)
      & (placements_by_conversion_name.placement == placement)
      & (placements_by_conversion_name.placement_type == placement_type)
    )
    filtered_conversion_rows = placements_by_conversion_name.loc[
      conversion_row_filter
    ]
    if not (conversions := sum(filtered_conversion_rows['conversions'].values)):
      conversions = 0.0
    if not (
      all_conversions := sum(filtered_conversion_rows['all_conversions'].values)
    ):
      all_conversions = 0.0
    return conversions, all_conversions

  def _extend_placement_with_conversion_split_columns(
    self, placements: gaarf.report.GaarfReport
  ) -> None:
    """Extend placements performance data with conversion split columns.

    Args:
      placements: Report with placement performance data.
    """
    for row in placements:
      row['conversion_name'] = ''
      row['custom_conversions'] = 0.0
      row['custom_all_conversions'] = 0.0

  def _aggregate_placements(
    self,
    placements: gaarf.report.GaarfReport,
    exclusion_level: str | enums.ExclusionLevelEnum,
    perform_relative_aggregations: bool = True,
  ) -> gaarf.report.GaarfReport:
    """Aggregates placements to a desired exclusion_level.

    By default Placements report returned on Ad Group level, however exclusion
    can be performed on Campaign, Account and MCC level. By aggregating report
    to a desired level exclusion specification can be property applied to
    identify placements that should be excluded.

    Args:
      placements:
        Report with placement related metrics.
      exclusion_level:
        Desired level of aggregation.
      perform_relative_aggregations:
        Whether or not calculate relative metrics (CTR, CPC, etc.)

    Returns:
      Updated report aggregated to desired exclusion level.
    """
    if not isinstance(exclusion_level, enums.ExclusionLevelEnum):
      exclusion_level = getattr(enums.ExclusionLevelEnum, exclusion_level)
    base_groupby = [
      'placement',
      'placement_type',
      'name',
      'criterion_id',
      'url',
    ]
    aggregation_dict = dict.fromkeys(
      METRICS,
      'sum',
    )
    if 'conversion_name' in placements.column_names:
      base_groupby = base_groupby + ['conversion_name']
      aggregation_dict.update(
        dict.fromkeys(['custom_conversions', 'custom_all_conversions'], 'sum')
      )
      COMPOUND_METRICS.update(
        {
          'cost_per_custom_conversions': ['cost', 'custom_conversions'],
          'cost_per_custom_all_conversions': ['cost', 'custom_all_conversions'],
        }
      )

    aggregation_groupby = self._define_aggregation_group_by(exclusion_level)
    groupby = [
      base
      for base in base_groupby + aggregation_groupby
      if base in placements.column_names
    ]
    aggregations = {
      key: value
      for key, value in aggregation_dict.items()
      if key in placements.column_names
    }
    aggregated_placements = (
      placements.to_pandas().groupby(groupby, as_index=False).agg(aggregations)
    )
    if perform_relative_aggregations:
      for key, [numerator, denominator] in COMPOUND_METRICS.items():
        if {numerator, denominator}.issubset(
          set(aggregated_placements.columns)
        ):
          aggregated_placements[key] = (
            aggregated_placements[numerator]
            / aggregated_placements[denominator]
          )
          if key == 'avg_cpm':
            aggregated_placements[key] = aggregated_placements[key] * 1000
          if key == 'ctr':
            aggregated_placements[key] = round(aggregated_placements[key], 4)
          else:
            aggregated_placements[key] = round(aggregated_placements[key], 2)
    aggregated_placements.replace([np.inf, -np.inf], 0, inplace=True)
    return gaarf.report.GaarfReport.from_pandas(aggregated_placements)

  def _define_aggregation_group_by(
    self, exclusion_level: enums.ExclusionLevelEnum
  ) -> list[str]:
    aggregation_groupby = ['account_name', 'customer_id']
    if exclusion_level == enums.ExclusionLevelEnum.CAMPAIGN:
      aggregation_groupby += ['campaign_id', 'campaign_name', 'campaign_type']
    elif exclusion_level == enums.ExclusionLevelEnum.AD_GROUP:
      aggregation_groupby += [
        'campaign_id',
        'campaign_name',
        'campaign_type',
        'ad_group_id',
        'ad_group_name',
      ]
    return aggregation_groupby
