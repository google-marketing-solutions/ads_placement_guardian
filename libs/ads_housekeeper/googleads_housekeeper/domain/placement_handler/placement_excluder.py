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

# pylint: disable=C0330, g-bad-import-order, g-multiple-import

"""Performs exclusion of placements from Google Ads."""

from __future__ import annotations

import dataclasses
import functools
import logging
import operator
from collections import defaultdict
from collections.abc import Iterable
from copy import deepcopy

import gaarf
import proto
import tenacity
from google.ads import googleads
from google.api_core import exceptions

from googleads_housekeeper.services import enums


@dataclasses.dataclass
class ExclusionResult:
  """Contains data on results of placement exclusion.

  As a result of exclusion some placements can be excluded and some can be
  associated with placement exclusion lists.

  Attributes:
    excluded_placements:
      A report containing placements that were excluded from Google Ads.
    associated_with_list_placements:
      A report containing placements that were added to placement
      negative lists.
    excludable_from_account_only:
      A report containing placements that cannot be excluded at
      current exclusion level.
  """

  excluded_placements: gaarf.report.GaarfReport | None = None
  associated_with_list_placements: gaarf.report.GaarfReport | None = None
  excludable_from_account_only: gaarf.report.GaarfReport | None = None


@dataclasses.dataclass
class ExclusionOperations:
  """Operations to be sent to Google Ads API.

  Attributes:
    placement_exclusion_operations:
      Operations for excluding placements from Google Ads.
    shared_set_creation_operations:
      Operations for creating placement exclusion lists in Google Ads.
    campaign_set_association_operations:
      Operations for attaching placements to placement exclusion lists
      in Google Ads.
    associated_with_list_placements:
      A report containing placements that were excluded from Google Ads.
    associated_with_list_placements:
      A report containing placements that were added to placement
      negative lists.
    excludable_from_account_only:
      A report containing placements that cannot be excluded at
      current exclusion level.
  """

  placement_exclusion_operations: dict
  shared_set_creation_operations: dict
  campaign_set_association_operations: dict
  excluded_placements: gaarf.report.GaarfReport
  associated_with_list_placements: gaarf.report.GaarfReport
  excludable_from_account_only: gaarf.report.GaarfReport


@dataclasses.dataclass
class PlacementOperation:
  """Represent exclusion operation for single placement.

  Attributes:
    customer_id:
      Google Ads account id.
    exclusion_operation:
      Operation for excluding placement from Google Ads.
    shared_set_resource_name:
      Resource name of placement exclusion list the placement can be
      associated with.
    is_associatable:
      Whether or not placement can be associated with placement exclusion
      list.
  """

  customer_id: int
  exclusion_operation: proto.message.Message
  shared_set_resource_name: str | None = None
  is_associatable: bool = False


class PlacementExcluder:
  """Handles excluding placements from Google Ads.

  Attributes:
    associable_with_negative_lists:
      Placements from these campaigns can be added to placement exclusion
      lists but campaigns cannot be associated with the list via API.
    associatable_to_negative_lists:
      Placements from these campaigns can be added to placement exclusion
      lists and campaigns can be associated with the list via API.
    excludable_from_account_only:
      Placements from these campaigns can be excluded only from
      account level.
  """

  associable_with_negative_lists = ('VIDEO',)
  associatable_to_negative_lists = ('DISPLAY', 'SEARCH')
  excludable_from_account_only = ('PERFORMANCE_MAX',)

  def __init__(
    self,
    client: gaarf.api_clients.GoogleAdsApiClient,
    exclusion_level: enums.ExclusionLevelEnum,
  ) -> None:
    self._client = client
    self.exclusion_level = (
      enums.ExclusionLevelEnum[exclusion_level]
      if isinstance(exclusion_level, str)
      else exclusion_level
    )

  @property
  def client(self):
    """Google Ads client to handle mutate requests."""
    return self._client.client

  @functools.cached_property
  def campaign_service(self):
    """Google Ads service for mutating campaigns."""
    return self.client.get_service('CampaignService')

  @functools.cached_property
  def campaign_set_operation(self):
    """Google Ads operation for creating campaign shared sets."""
    return self.client.get_type('CampaignSharedSetOperation')

  @functools.cached_property
  def shared_set_service(self):
    """Google Ads service for creating shared sets."""
    return self.client.get_service('SharedSetService')

  @functools.cached_property
  def shared_criterion_service(self):
    """Google Ads service for creating shared set criterion (placements)."""
    return self.client.get_service('SharedCriterionService')

  @functools.cached_property
  def campaign_shared_set_service(self):
    """Google Ads service for attaching campaigns to share set."""
    return self.client.get_service('CampaignSharedSetService')

  @functools.cached_property
  def shared_set_operation(self):
    """Google Ads operation for managing shared sets."""
    return self.client.get_type('SharedSetOperation')

  @functools.cached_property
  def criterion_service(self):
    """Google Ads service for adding placement as a negative criterion."""
    if self.exclusion_level == enums.ExclusionLevelEnum.AD_GROUP:
      return self.client.get_service('AdGroupCriterionService')
    if self.exclusion_level == enums.ExclusionLevelEnum.CAMPAIGN:
      return self.client.get_service('CampaignCriterionService')
    if self.exclusion_level == enums.ExclusionLevelEnum.ACCOUNT:
      return self.client.get_service('CustomerNegativeCriterionService')
    return None

  @functools.cached_property
  def mutate_operation(self):
    """Google Ads operation for changing negative criteria."""
    if self.exclusion_level == enums.ExclusionLevelEnum.AD_GROUP:
      return self.criterion_service.mutate_ad_group_criteria
    if self.exclusion_level == enums.ExclusionLevelEnum.CAMPAIGN:
      return self.criterion_service.mutate_campaign_criteria
    if self.exclusion_level == enums.ExclusionLevelEnum.ACCOUNT:
      return self.criterion_service.mutate_customer_negative_criteria
    return None

  @functools.cached_property
  def criterion_operation(self):
    """Google Ads operation for managing negative criteria."""
    if self.exclusion_level == enums.ExclusionLevelEnum.AD_GROUP:
      return self.client.get_type('AdGroupCriterionOperation')
    if self.exclusion_level == enums.ExclusionLevelEnum.CAMPAIGN:
      return self.client.get_type('CampaignCriterionOperation')
    if self.exclusion_level == enums.ExclusionLevelEnum.ACCOUNT:
      return self.client.get_type('CustomerNegativeCriterionOperation')
    return None

  @functools.cached_property
  def entity_id(self):
    """Specified resource id (ad_group, campaign) for building path."""
    if self.exclusion_level == enums.ExclusionLevelEnum.AD_GROUP:
      return 'ad_group_id'
    if self.exclusion_level == enums.ExclusionLevelEnum.CAMPAIGN:
      return 'campaign_id'
    return None

  def exclude_placements(
    self,
    to_be_excluded_placements: gaarf.report.GaarfReport,
    placement_exclusion_lists: dict[str, str] | None = None,
  ) -> ExclusionResult:
    """Perform exclusion of placements from Google Ads.

    Some placement might be directly excluded while other are associated
    with a negative placement list.

    Args:
      to_be_excluded_placements:
        Report containing placements to be excluded.
      placement_exclusion_lists:
        Mapping between placement exclusion list name and
        its resource_name.

    Returns:
      Results of exclusion.
    """
    if not placement_exclusion_lists:
      placement_exclusion_lists = {}
    exclusion_operations = self._create_exclusion_operations(
      to_be_excluded_placements, placement_exclusion_lists
    )
    for (
      customer_id,
      operations,
    ) in exclusion_operations.shared_set_creation_operations.items():
      try:
        if operations:
          self._add_placements_to_shared_set(customer_id, operations)
          logging.info(
            'Added %d placements to shared_set for %d account',
            len(operations),
            customer_id,
          )
      except Exception as e:
        logging.error(e)
    for (
      customer_id,
      operations,
    ) in exclusion_operations.placement_exclusion_operations.items():
      try:
        if operations:
          excluded_placements = self._exclude(customer_id, operations)
          logging.info(
            'Excluded %d placements from account %s',
            len(operations),
            customer_id,
          )
          logging.info(
            '%d placements was excluded',
            excluded_placements,
          )
      except Exception as e:
        logging.error(e)
    if exclusion_operations.campaign_set_association_operations:
      operations = self._create_campaign_set_operations(
        customer_id, exclusion_operations.campaign_set_association_operations
      )
      self._add_campaigns_to_shared_set(customer_id, operations)
    if excluded_placements := exclusion_operations.excluded_placements:
      excluded_placements = functools.reduce(
        operator.add, exclusion_operations.excluded_placements
      )
    if (
      associated_with_list_placements
      := exclusion_operations.associated_with_list_placements
    ):
      associated_with_list_placements = functools.reduce(
        operator.add, associated_with_list_placements
      )
    if (
      excludable_from_account_only
      := exclusion_operations.excludable_from_account_only
    ):
      excludable_from_account_only = functools.reduce(
        operator.add, exclusion_operations.excludable_from_account_only
      )
    return ExclusionResult(
      excluded_placements=excluded_placements,
      associated_with_list_placements=associated_with_list_placements,
      excludable_from_account_only=excludable_from_account_only,
    )

  def _create_exclusion_operations(
    self,
    placements: gaarf.report.GaarfReport,
    placement_exclusion_lists: dict[str, str],
  ) -> ExclusionOperations:
    """Create exclusion operations to be send to Google Ads API.

    Args:
      placements:
        Report containing placements to be excluded.
      placement_exclusion_lists:
        Mapping between placement exclusion list name and
        its resource_name.

    Returns:
      Mutate operations to be send to Google Ads API.
    """
    operations_mapping: dict[str, list] = defaultdict(list)
    excluded_placements: list[gaarf.report.GaarfReport] = []
    shared_set_operations_mapping: dict[str, list] = defaultdict(list)
    associated_with_list_placements: list[gaarf.report.GaarfReport] = []
    excludable_from_account_only_placements: list[gaarf.report.GaarfReport] = []
    campaign_set_mapping: dict[str, int] = {}
    for placement_info in placements:
      if placement_info.allowlisted or placement_info.excluded_already:
        continue
      placement_operation, relevant_placement_info = (
        self._create_placement_operation(
          placement_info, placement_exclusion_lists
        )
      )
      if not placement_operation:
        excludable_from_account_only_placements.append(relevant_placement_info)
        continue
      if shared_set := placement_operation.shared_set_resource_name:
        shared_set_operations_mapping[placement_operation.customer_id].append(
          placement_operation.exclusion_operation
        )
        associated_with_list_placements.append(relevant_placement_info)
        if placement_operation.is_associatable:
          campaign_set_mapping[shared_set] = placement_info.campaign_id
      else:
        operations_mapping[placement_operation.customer_id].append(
          placement_operation.exclusion_operation
        )
        excluded_placements.append(relevant_placement_info)
    return ExclusionOperations(
      placement_exclusion_operations=operations_mapping,
      shared_set_creation_operations=shared_set_operations_mapping,
      campaign_set_association_operations=campaign_set_mapping,
      excluded_placements=excluded_placements,
      associated_with_list_placements=associated_with_list_placements,
      excludable_from_account_only=excludable_from_account_only_placements,
    )

  def _create_placement_operation(
    self,
    placement_info: gaarf.report.GaarfRow,
    placement_exclusion_lists: dict[str, str] | None = None,
  ) -> tuple[PlacementOperation | None, gaarf.report.GaarfReport]:
    """Create exclusion operation for a single placement.

    Args:
      placement_info:
        Row from report containing placements to be excluded.
      placement_exclusion_lists:
        Mapping between placement exclusion list name and
        its resource_name.

    Returns:
      Tuple containing optional exclusion operation and subset of
      placement_info with information on placement.
    """
    entity_criterion = None
    shared_set_resource_name = None
    is_associatable = False
    if (
      self.exclusion_level != enums.ExclusionLevelEnum.ACCOUNT
      and placement_info.campaign_type in self.excludable_from_account_only
    ):
      relevant_placement_info = gaarf.report.GaarfReport(
        results=[placement_info.data], column_names=placement_info.column_names
      )
      return None, relevant_placement_info
    if (
      self.exclusion_level
      in (enums.ExclusionLevelEnum.CAMPAIGN, enums.ExclusionLevelEnum.AD_GROUP)
      and placement_info.campaign_type in self.associable_with_negative_lists
    ):
      if shared_set_resource_name := self._create_shared_set(
        placement_info.customer_id,
        placement_info.campaign_id,
        placement_exclusion_lists,
      ):
        shared_criterion_operation = self.client.get_type(
          'SharedCriterionOperation'
        )
        entity_criterion = shared_criterion_operation.create
        entity_criterion.shared_set = shared_set_resource_name
      if placement_info.campaign_type in self.associatable_to_negative_lists:
        is_associatable = True

    if (
      placement_info.placement_type
      == enums.PlacementTypeEnum.MOBILE_APPLICATION.name
    ):
      app_id = self._format_app_id(placement_info.placement)
    if not entity_criterion:
      entity_criterion = self.criterion_operation.create
    # Assign specific criterion
    if placement_info.placement_type == (enums.PlacementTypeEnum.WEBSITE.name):
      entity_criterion.placement.url = self._format_website(
        placement_info.placement
      )
    if (
      placement_info.placement_type
      == enums.PlacementTypeEnum.MOBILE_APPLICATION.name
    ):
      entity_criterion.mobile_application.app_id = app_id
    if placement_info.placement_type == (
      enums.PlacementTypeEnum.YOUTUBE_VIDEO.name
    ):
      entity_criterion.youtube_video.video_id = placement_info.placement
    if (
      placement_info.placement_type
      == enums.PlacementTypeEnum.YOUTUBE_CHANNEL.name
    ):
      entity_criterion.youtube_channel.channel_id = placement_info.placement
    if not shared_set_resource_name:
      if self.exclusion_level != enums.ExclusionLevelEnum.ACCOUNT:
        entity_criterion.negative = True
      if self.exclusion_level == enums.ExclusionLevelEnum.AD_GROUP:
        entity_criterion.ad_group = self.criterion_service.ad_group_path(
          placement_info.customer_id, placement_info.get(self.entity_id)
        )
      elif self.exclusion_level == enums.ExclusionLevelEnum.CAMPAIGN:
        entity_criterion.campaign = self.criterion_service.campaign_path(
          placement_info.customer_id, placement_info.get(self.entity_id)
        )
    if shared_set_resource_name:
      operation = deepcopy(shared_criterion_operation)
    else:
      operation = deepcopy(self.criterion_operation)
    placement_operation = PlacementOperation(
      customer_id=placement_info.customer_id,
      exclusion_operation=operation,
      shared_set_resource_name=shared_set_resource_name,
      is_associatable=is_associatable,
    )
    relevant_placement_info = gaarf.report.GaarfReport(
      results=[placement_info.data], column_names=placement_info.column_names
    )
    return placement_operation, relevant_placement_info

  def _create_shared_set(
    self,
    customer_id: int,
    campaign_id: int,
    placement_exclusion_lists: dict[str, str],
    base_share_set_name: str = 'CPR Negative placements list - Campaign:',
  ) -> str | None:
    """Create placement exclusion list in Google Ads API.

    Args:
      customer_id:
        Google Ads account number.
      campaign_id:
        Id of campaign that will be associated with the placement
        exclusion list.
      placement_exclusion_lists:
        Mapping between already existing placements exclusion lists and
        its resource names.
      base_share_set_name:
        Common name for all placement exclusion lists.

    Returns:
      Resource name of extracted or created placement exclusion list
      resource name.
    """
    name = f'{base_share_set_name} {campaign_id}'
    if name in placement_exclusion_lists:
      return placement_exclusion_lists[name]
    shared_set = self.shared_set_operation.create
    shared_set.name = name
    shared_set.type_ = self.client.enums.SharedSetTypeEnum.NEGATIVE_PLACEMENTS

    operation = deepcopy(self.shared_set_operation)
    try:
      shared_set_response = self.shared_set_service.mutate_shared_sets(
        customer_id=str(customer_id), operations=[operation]
      )
      shared_set_resource_name = shared_set_response.results[0].resource_name
      logging.debug('Created shared set "%s".', shared_set_resource_name)
      return shared_set_resource_name
    except googleads.errors.GoogleAdsException:
      logging.debug('Shared set "%s" already exists.', name)
      return None

  def _add_placements_to_shared_set(
    self, customer_id: int, operations: list
  ) -> None:
    """Adds placements to placement exclusion list.

    Args:
      customer_id: Google Ads account number.
      operations: Shared set attachment operations for a given customer_id.
    """
    if not isinstance(operations, Iterable):
      operations = [operations]
    try:
      for attempt in tenacity.Retrying(
        retry=tenacity.retry_if_exception_type(exceptions.InternalServerError),
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(),
      ):
        with attempt:
          self.shared_criterion_service.mutate_shared_criteria(
            customer_id=str(customer_id), operations=operations
          )
    except tenacity.RetryError as retry_failure:
      logging.error(
        'Cannot add placements to exclusion list for account ' "'%s' %d times",
        customer_id,
        retry_failure.last_attempt.attempt_number,
      )

  def _create_campaign_set_operations(
    self, customer_id, campaign_set_mapping: dict
  ) -> list:
    """Create operations for adding placements to placement exclusion lists.

    Args:
      customer_id:
        Google Ads account number.
      campaign_set_mapping:
        Mapping between shared_set resource_name and campaign_id.

    Returns:
      Operations for adding campaigns to placement exclusion lists.
    """
    campaign_set = self.campaign_set_operation.create
    operations = []
    for shared_set, campaign_id in campaign_set_mapping.items():
      campaign_set.campaign = self.campaign_service.campaign_path(
        customer_id, campaign_id
      )
      campaign_set.shared_set = shared_set
      operation = deepcopy(self.campaign_set_operation)
      operations.append(operation)
    return operations

  def _add_campaigns_to_shared_set(
    self, customer_id: str, operations: list
  ) -> None:
    """Adds campaigns to placement exclusion list.

    Args:
      customer_id:
        Google Ads account number.
      operations:
        Operations for adding campaigns to placement exclusion lists.
    """
    self.campaign_shared_set_service.mutate_campaign_shared_sets(
      customer_id=str(customer_id), operations=operations
    )

  def _format_app_id(self, app_id: str) -> str:
    """Returns app_id as acceptable negative criterion."""
    if app_id.startswith('mobileapp::'):
      criteria = app_id.split('-')
      app_id = criteria[-1]
      app_store = criteria[0].split('::')[-1]
      app_store = app_store.replace('mobileapp::1000', '')
      app_store = app_store.replace('1000', '')
      return f'{app_store}-{app_id}'
    return app_id

  def _format_website(self, website_url: str) -> str:
    """Returns website as acceptable negative criterion."""
    return website_url.split('/')[0]

  def _exclude(self, customer_id: str, operations) -> int:
    """Exclude placements from Google Ads.

    Args:
      customer_id:
        Google Ads account number.
      operations:
        Operations for excluding placements from Google Ads.

    Returns:
      Number of placements excluded.
    """
    if not isinstance(operations, Iterable):
      operations = [operations]
    try:
      for attempt in tenacity.Retrying(
        retry=tenacity.retry_if_exception_type(exceptions.InternalServerError),
        stop=tenacity.stop_after_attempt(3),
        wait=tenacity.wait_exponential(),
      ):
        with attempt:
          result = self.mutate_operation(
            customer_id=str(customer_id), operations=operations
          )
          return len(result.results)
    except tenacity.RetryError as retry_failure:
      logging.error(
        "Cannot exclude placements for account '%s' %d times",
        customer_id,
        retry_failure.last_attempt.attempt_number,
      )
    return 0
