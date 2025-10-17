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

# pylint: disable=C0330, g-bad-import-order, g-multiple-import, missing-class-docstring, missing-module-docstring, missing-function-docstring

from __future__ import annotations

import pytest
from googleads_housekeeper.domain.placement_handler import entities
from googleads_housekeeper.services import enums


class TestPlacementEntity:
  def test_placements_entity_empty_placement_types_returns_all_default_placement_types(
    self,
  ):
    placements = entities.Placements(placement_types=None)
    expected = '","'.join(placements._PLACEMENT_TYPES)
    assert placements.placement_types == expected

  def test_placements_entity_returns_formatted_placement_types_from_tuple(self):
    placements = entities.Placements(
      placement_types=('WEBSITE', 'MOBILE_APPLICATION')
    )
    assert placements.placement_types == 'WEBSITE","MOBILE_APPLICATION'

  def test_placements_entity_returns_formatted_placement_types_from_string(
    self,
  ):
    placements = entities.Placements(
      placement_types='WEBSITE,MOBILE_APPLICATION'
    )
    assert placements.placement_types == 'WEBSITE","MOBILE_APPLICATION'

  def test_placements_entity_wrong_placement_type_raises_value_error(self):
    with pytest.raises(ValueError):
      entities.Placements(placement_types=('WRONG_PLACEMENT',))

  def test_placements_entity_wrong_start_date_return_value_error(self):
    with pytest.raises(ValueError):
      entities.Placements(start_date='1/1/1/')

  def test_placements_entity_wrong_end_date_return_value_error(self):
    with pytest.raises(ValueError):
      entities.Placements(end_date='1/1/1/')

  def test_placements_entity_start_date_greater_than_end_date_returns_value_error(
    self,
  ):
    with pytest.raises(ValueError):
      entities.Placements(start_date='2023-01-01', end_date='2022-01-01')

  def test_placements_entity_empty_campaign_types_returns_all_default_campaign_types(
    self,
  ):
    placements = entities.Placements(campaign_types=None)
    expected = '","'.join(placements._CAMPAIGN_TYPES)
    assert placements.campaign_types == expected

  def test_placements_entity_returns_formatted_campaign_types_from_tuple(self):
    placements = entities.Placements(campaign_types=('DISPLAY', 'VIDEO'))
    assert placements.campaign_types == 'DISPLAY","VIDEO'

  def test_placements_entity_returns_formatted_campaign_types_from_string(self):
    placements = entities.Placements(campaign_types='DISPLAY,VIDEO')
    assert placements.campaign_types == 'DISPLAY","VIDEO'

  def test_placements_entity_wrong_campaign_type_raises_value_error(self):
    with pytest.raises(ValueError):
      entities.Placements(campaign_types=('WRONG_CAMPAIGN_TYPE',))

  def test_placements_entity_wrong_granularity_raises_value_error(self):
    with pytest.raises(ValueError):
      entities.Placements(placement_level_granularity='wrong_placement_view')


class TestPlacementConversionSplitEntity:
  def test_placements_conversion_split_is_subclass_of_placement_entity(self):
    placements_conversion_split = entities.PlacementsConversionSplit(
      placement_types=None
    )
    assert isinstance(placements_conversion_split, entities.Placements)


class TestAlreadyExcludedPlacements:
  @pytest.mark.parametrize(
    'exclusion_level,expected_resource',
    [
      (enums.ExclusionLevelEnum.ACCOUNT, 'customer_negative_criterion'),
      (enums.ExclusionLevelEnum.CAMPAIGN, 'campaign_criterion'),
      (enums.ExclusionLevelEnum.AD_GROUP, 'ad_group_criterion'),
    ],
  )
  def test_already_excluded_placements_query_is_correct(
    self, exclusion_level, expected_resource
  ):
    already_excluded_placements = entities.AlreadyExcludedPlacements(
      exclusion_level
    )
    assert expected_resource in already_excluded_placements.query_text
