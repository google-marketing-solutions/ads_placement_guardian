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
"""Exposes operations for previewing and excluding placements."""

# pylint: disable=C0330, g-bad-import-order, g-multiple-import

from __future__ import annotations

import dataclasses
import functools
import operator

import gaarf

from googleads_housekeeper import views
from googleads_housekeeper.domain.core import (
  exclusion_specification,
  task,
)
from googleads_housekeeper.domain.external_parsers import external_entity_parser
from googleads_housekeeper.domain.placement_handler import (
  placement_excluder,
  placement_fetcher,
)
from googleads_housekeeper.services import enums, unit_of_work


@dataclasses.dataclass
class RuntimeOptions:
  """Options for configuring, fetching and saving of data."""

  always_fetch_youtube_preview_mode: bool = False
  save_to_db: bool = False


def exclude_placements(
  task_obj: task.Task,
  uow: unit_of_work.AbstractUnitOfWork,
  client: gaarf.GoogleAdsApiClient,
  runtime_options: RuntimeOptions,
) -> placement_excluder.ExclusionResult:
  """Excludes data from Google Ads based on specified criteria.

  Args:
    task_obj: A Task for identifying placements suitable for exclusion.
    uow: Unit of Work to handle the transaction.
    client: Google Ads API client to perform fetching.
    runtime_options: Options for configuring fetching and saving of data.
  """
  report_fetcher = gaarf.report_fetcher.AdsReportFetcher(client)
  fetcher = placement_fetcher.PlacementFetcher(report_fetcher)
  excluder = placement_excluder.PlacementExcluder(
    client, task_obj.exclusion_level
  )
  to_be_excluded_placements = find_placements_for_exclusion(
    task_obj, uow, report_fetcher, runtime_options
  )
  if not to_be_excluded_placements:
    return placement_excluder.ExclusionResult()
  customer_ids = to_be_excluded_placements['customer_id'].to_list(
    flatten=True, distinct=True
  )
  placement_exclusion_lists = fetcher.get_placement_exclusion_lists(
    customer_ids
  )
  return excluder.exclude_placements(
    to_be_excluded_placements, placement_exclusion_lists
  )


def _is_already_excluded_placement(
  placement_info: gaarf.report.GaarfRow,
  already_excluded_placements: dict[int, list[int]],
  exclusion_level: enums.ExclusionLevelEnum,
) -> bool:
  """Verifies that a placement has already been added to exclusions.

  Args:
    placement_info:
      GaarfRow containing information on a single placement.
    already_excluded_placements:
      Mapping for placements added as negative criteria on a
      specific level (ACCOUNT, CAMPAIGN, AD_GROUP).
    exclusion_level:
      Level of exclusion (ACCOUNT, CAMPAIGN, AD_GROUP).

  Returns:
    Description of return.

  Raises:
    ValueError: When incorrect exclusion level is specified.
  """
  if exclusion_level == enums.ExclusionLevelEnum.ACCOUNT:
    level_id = placement_info.customer_id
  elif exclusion_level == enums.ExclusionLevelEnum.CAMPAIGN:
    level_id = placement_info.campaign_id
  elif exclusion_level == enums.ExclusionLevelEnum.AD_GROUP:
    level_id = placement_info.ad_group_id
  else:
    raise ValueError(f'Incorrect exclusion_level: {exclusion_level}')
  return placement_info.placement in already_excluded_placements.get(
    level_id, []
  )


def find_placements_for_exclusion(
  task_obj: task.Task,
  uow: unit_of_work.AbstractUnitOfWork,
  report_fetcher: gaarf.report_fetcher.AdsReportFetcher | None = None,
  runtime_options: RuntimeOptions = RuntimeOptions(),
  limit: int | None = None,
) -> gaarf.report.GaarfReport | None:
  """Identifies the placements suitable for exclusion.

  Args:
    task_obj: A Task for identifying placements suitable for exclusion.
    uow: Unit of Work to handle the transaction.
    report_fetcher: An instance of AdsReportFetcher to handle API requests.
    runtime_options: Options for configuring fetching and saving of data.
    limit: Whether to fetch all data or only a subset.

  Returns:
    Report containing placements suitable for exclusion.
  """
  fetcher = placement_fetcher.PlacementFetcher(report_fetcher)
  external_parser = external_entity_parser.ExternalEntitiesParser()
  specification = (
    exclusion_specification.ExclusionSpecification.from_expression(
      task_obj.exclusion_rule
    )
  )
  reports: list[gaarf.report.GaarfReport] = []
  include_matching_entity = False
  for account in task_obj.accounts:
    account_allowlisted_placements = views.allowlisted_placements_as_tuples(
      uow, account
    )
    if not (
      placements := fetcher.get_placements_for_account(account, task_obj, limit)
    ):
      continue
    already_excluded_placements = fetcher.get_already_excluded_placements(
      account, task_obj.exclusion_level
    )
    if ads_specs := specification.ads_specs_entries:
      placements = ads_specs.apply_specifications(
        placements, include_reason=False, include_matching_entity=False
      )
      if not placements:
        continue
    if non_ads_specs := specification.non_ads_specs_entries:
      external_parser.parse_specification_chain(placements, non_ads_specs)
      include_matching_entity = True
    elif runtime_options.always_fetch_youtube_preview_mode:
      youtube_channel_specification = (
        exclusion_specification.ExclusionSpecification(
          specifications=[
            [
              exclusion_specification.YouTubeChannelExclusionSpecificationEntry(
                'subscriberCount > 0'
              )
            ],
          ]
        )
      )
      external_parser.parse_specification_chain(
        placements, youtube_channel_specification
      )
      include_matching_entity = True
    placements = inject_extra_data(
      placements,
      account_allowlisted_placements,
      already_excluded_placements,
      task_obj.exclusion_level,
    )
    if specification:
      placements = specification.apply_specifications(
        placements, include_matching_entity=include_matching_entity
      )
    elif 'extra_info' in placements.column_names:
      for row in placements:
        row['extra_info'] = row.extra_info.to_dict()
    if placements:
      reports.append(placements)

  if reports:
    return functools.reduce(operator.add, reports)
  return None


def inject_extra_data(
  placements: gaarf.report.GaarfReport,
  allowlisted_placements: list[tuple[str, str, str]],
  already_excluded_placements: dict[int, list[int]],
  exclusion_level: enums.ExclusionLevelEnum,
) -> gaarf.report.GaarfReport:
  """Add extra placement information to the placement report.

  Args:
    placements:
      Report containing placement data.
    allowlisted_placements:
      Info on placements that shouldn't be excluded form a given account.
    already_excluded_placements:
      Mapping between entity_id from specified exclusion level to all
      negative criteria ids.
    exclusion_level: Level of exclusion (ACCOUNT, CAMPAIGN, AD_GROUP).

  Returns:
    Placement data report with new columns
    ('allowlisted', 'already_excluded', 'extra_info').
  """
  has_allowlisted_placements = allowlisted_placements or False
  for placement in placements:
    if has_allowlisted_placements:
      placement['allowlisted'] = (
        placement.name,
        placement.placement_type,
        placement.customer_id,
      ) in allowlisted_placements
    else:
      placement['allowlisted'] = False
    placement['excluded_already'] = _is_already_excluded_placement(
      placement, already_excluded_placements, exclusion_level
    )
  return placements
