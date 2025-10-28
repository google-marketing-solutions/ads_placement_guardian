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

import gaarf
import pytest
from googleads_housekeeper.domain.placement_handler import placement_excluder
from googleads_housekeeper.services import enums

_TEST_CUSTOMER_ID = 123456789
_TEST_CAMPAIGN_ID = 23456
_TEST_AD_GROUP_ID = 34567
_TEST_CRITERION_ID = 456789
_REPORT_COLUMN_NAMES = [
  'customer_id',
  'campaign_id',
  'campaign_type',
  'ad_group_id',
  'placement_type',
  'placement',
  'criterion_id',
]
_REPORT_COLUMN_NAMES_WITH_ALLOWLISTING = _REPORT_COLUMN_NAMES + [
  'allowlisted',
  'excluded_already',
]


class TestPlacementExcluder:
  @pytest.fixture
  def test_client(self, mocker):
    mocker.patch('google.ads.googleads.client.oauth2', return_value=[])
    return gaarf.api_clients.GoogleAdsApiClient()

  @pytest.fixture
  def excluder(self, test_client, fake_tracer):
    return placement_excluder.PlacementExcluder(
      client=test_client,
      exclusion_level=enums.ExclusionLevelEnum.AD_GROUP,
      tracer=fake_tracer,
    )

  @pytest.fixture
  def placement_exclusion_lists(self):
    return {
      f'CPR Negative placements list - Campaign: {_TEST_CAMPAIGN_ID}': f'customers/{_TEST_CUSTOMER_ID}/sharedSet/123'
    }

  @pytest.fixture
  def website_placement_display_campaign(self):
    return gaarf.report.GaarfRow(
      data=[
        _TEST_CUSTOMER_ID,
        _TEST_CAMPAIGN_ID,
        'DISPLAY',
        _TEST_AD_GROUP_ID,
        'WEBSITE',
        'example.com',
        f'{_TEST_CRITERION_ID}',
      ],
      column_names=_REPORT_COLUMN_NAMES,
    )

  @pytest.fixture
  def website_placement_pmax_campaign(self):
    return gaarf.report.GaarfRow(
      data=[
        _TEST_CUSTOMER_ID,
        _TEST_CAMPAIGN_ID,
        'PERFORMANCE_MAX',
        _TEST_AD_GROUP_ID,
        'WEBSITE',
        'example.com',
        f'{_TEST_CRITERION_ID}',
      ],
      column_names=_REPORT_COLUMN_NAMES,
    )

  @pytest.fixture
  def youtube_placement_video_campaign(self):
    return gaarf.report.GaarfRow(
      data=[
        _TEST_CUSTOMER_ID,
        _TEST_CAMPAIGN_ID,
        'VIDEO',
        _TEST_AD_GROUP_ID,
        'YOUTUBE_VIDEO',
        'test-video-id',
        f'{_TEST_CRITERION_ID}',
      ],
      column_names=_REPORT_COLUMN_NAMES,
    )

  def test_create_placement_operation_returns_correct_ad_group_path(
    self,
    website_placement_display_campaign,
    excluder,
    placement_exclusion_lists,
  ):
    operation, _ = excluder._create_placement_operation(
      website_placement_display_campaign, placement_exclusion_lists
    )

    expected_path = (
      f'customers/{_TEST_CUSTOMER_ID}/adGroups/{_TEST_AD_GROUP_ID}'
    )
    assert operation.exclusion_operation.create.ad_group == expected_path
    assert 'example.com' in operation.exclusion_operation.create.placement.url
    assert not operation.is_associatable
    assert not operation.shared_set_resource_name
    assert hasattr(operation.exclusion_operation.create, 'negative')

  def test_create_placement_operation_returns_correct_campaign_path(
    self,
    website_placement_display_campaign,
    excluder,
    placement_exclusion_lists,
  ):
    exclusion_level = enums.ExclusionLevelEnum.CAMPAIGN
    excluder.exclusion_level = exclusion_level
    operation, _ = excluder._create_placement_operation(
      website_placement_display_campaign, placement_exclusion_lists
    )

    expected_path = (
      f'customers/{_TEST_CUSTOMER_ID}/campaigns/{_TEST_CAMPAIGN_ID}'
    )
    assert operation.exclusion_operation.create.campaign == expected_path
    assert hasattr(operation.exclusion_operation.create, 'negative')

  def test_create_placement_operation_returns_correct_customer_path(
    self,
    website_placement_display_campaign,
    excluder,
    placement_exclusion_lists,
  ):
    exclusion_level = enums.ExclusionLevelEnum.ACCOUNT
    excluder.exclusion_level = exclusion_level
    operation, _ = excluder._create_placement_operation(
      website_placement_display_campaign, placement_exclusion_lists
    )

    assert not hasattr(operation.exclusion_operation.create, 'negative')

  def test_create_placement_operation_returns_correct_placement_type(
    self,
    website_placement_display_campaign,
    excluder,
    placement_exclusion_lists,
  ):
    operation, _ = excluder._create_placement_operation(
      website_placement_display_campaign, placement_exclusion_lists
    )

    assert 'example.com' in operation.exclusion_operation.create.placement.url

  def test_create_placement_operation_returns_correct_placement_type_for_mobile_application(
    self, excluder, placement_exclusion_lists
  ):
    placement_info = gaarf.report.GaarfRow(
      data=[
        _TEST_CUSTOMER_ID,
        _TEST_CAMPAIGN_ID,
        'DISPLAY',
        _TEST_AD_GROUP_ID,
        'MOBILE_APPLICATION',
        'com.example.googleplay',
        '_TEST_CRITERION_ID',
      ],
      column_names=_REPORT_COLUMN_NAMES,
    )

    operation, _ = excluder._create_placement_operation(
      placement_info, placement_exclusion_lists
    )

    assert 'com.example.googleplay' in (
      operation.exclusion_operation.create.mobile_application.app_id
    )

  def test_create_placement_operation_returns_correct_placement_type_for_youtube_video(
    self, excluder, placement_exclusion_lists
  ):
    placement_info = gaarf.report.GaarfRow(
      data=[
        _TEST_CUSTOMER_ID,
        _TEST_CAMPAIGN_ID,
        'DISPLAY',
        _TEST_AD_GROUP_ID,
        'YOUTUBE_VIDEO',
        'test-video-id',
        '_TEST_CRITERION_ID',
      ],
      column_names=_REPORT_COLUMN_NAMES,
    )

    operation, _ = excluder._create_placement_operation(
      placement_info, placement_exclusion_lists
    )

    assert 'test-video-id' in (
      operation.exclusion_operation.create.youtube_video.video_id
    )

  def test_create_placement_operation_returns_correct_placement_type_for_youtube_channel(
    self, excluder, placement_exclusion_lists
  ):
    placement_info = gaarf.report.GaarfRow(
      data=[
        _TEST_CUSTOMER_ID,
        _TEST_CAMPAIGN_ID,
        'DISPLAY',
        _TEST_AD_GROUP_ID,
        'YOUTUBE_CHANNEL',
        'test-channel-id',
        '_TEST_CRITERION_ID',
      ],
      column_names=_REPORT_COLUMN_NAMES,
    )

    operation, _ = excluder._create_placement_operation(
      placement_info, placement_exclusion_lists
    )

    assert 'test-channel-id' in (
      operation.exclusion_operation.create.youtube_channel.channel_id
    )

  def test_create_placement_operation_does_not_create_shared_for_website(
    self,
    website_placement_display_campaign,
    excluder,
    placement_exclusion_lists,
  ):
    operation, _ = excluder._create_placement_operation(
      website_placement_display_campaign, placement_exclusion_lists
    )

    assert not operation.shared_set_resource_name

  def test_create_placement_operation_returns_shared_set_operation_for_video_campaign(
    self, youtube_placement_video_campaign, excluder, placement_exclusion_lists
  ):
    operation, _ = excluder._create_placement_operation(
      youtube_placement_video_campaign, placement_exclusion_lists
    )

    assert operation.exclusion_operation.create.shared_set in (
      placement_exclusion_lists.values()
    )
    assert not operation.is_associatable

  def test_create_placement_operation_returns_none_for_pmax_at_non_account_level(
    self, website_placement_pmax_campaign, excluder, placement_exclusion_lists
  ):
    operation, _ = excluder._create_placement_operation(
      website_placement_pmax_campaign, placement_exclusion_lists
    )

    assert operation is None

  def test_create_placement_exclusion_operations_returns_only_operations_for_display_campaign(
    self, excluder, placement_exclusion_lists
  ):
    report = gaarf.report.GaarfReport(
      results=[
        [
          _TEST_CUSTOMER_ID,
          _TEST_CAMPAIGN_ID,
          'DISPLAY',
          _TEST_AD_GROUP_ID,
          'WEBSITE',
          'example.com',
          '_TEST_CRITERION_ID',
          False,
          False,
        ]
      ],
      column_names=_REPORT_COLUMN_NAMES_WITH_ALLOWLISTING,
    )
    exclusion_operations = excluder._create_exclusion_operations(
      report, placement_exclusion_lists
    )

    assert (
      _TEST_CUSTOMER_ID in exclusion_operations.placement_exclusion_operations
    )
    assert not exclusion_operations.shared_set_creation_operations
    assert not exclusion_operations.campaign_set_association_operations

  def test_create_placement_exclusion_operations_returns_nothing_for_allowlisted_placement(
    self, excluder, placement_exclusion_lists
  ):
    report = gaarf.report.GaarfReport(
      results=[
        [
          _TEST_CUSTOMER_ID,
          _TEST_CAMPAIGN_ID,
          'VIDEO',
          _TEST_AD_GROUP_ID,
          'YOUTUBE_VIDEO',
          'test-video-id',
          '_TEST_CRITERION_ID',
          True,
          False,
        ]
      ],
      column_names=_REPORT_COLUMN_NAMES_WITH_ALLOWLISTING,
    )
    exclusion_operations = excluder._create_exclusion_operations(
      report, placement_exclusion_lists
    )
    assert not exclusion_operations.placement_exclusion_operations
    assert not exclusion_operations.shared_set_creation_operations
    assert not exclusion_operations.campaign_set_association_operations

  def test_create_placement_exclusion_operations_returns_only_share_set_operations_for_video_campaign(
    self, excluder, placement_exclusion_lists
  ):
    report = gaarf.report.GaarfReport(
      results=[
        [
          _TEST_CUSTOMER_ID,
          _TEST_CAMPAIGN_ID,
          'VIDEO',
          _TEST_AD_GROUP_ID,
          'YOUTUBE_VIDEO',
          'test-video-id',
          '_TEST_CRITERION_ID',
          False,
          False,
        ]
      ],
      column_names=_REPORT_COLUMN_NAMES_WITH_ALLOWLISTING,
    )
    exclusion_operations = excluder._create_exclusion_operations(
      report, placement_exclusion_lists
    )

    assert not exclusion_operations.placement_exclusion_operations
    assert (
      _TEST_CUSTOMER_ID in exclusion_operations.shared_set_creation_operations
    )
    assert not exclusion_operations.campaign_set_association_operations

  @pytest.mark.parametrize('campaign_type', ['PERFORMANCE_MAX'])
  def test_create_placement_exclusion_operations_returns_excludable_from_account_only_for_certain_campaigns(
    self, excluder, placement_exclusion_lists, campaign_type
  ):
    report = gaarf.report.GaarfReport(
      results=[
        [
          _TEST_CUSTOMER_ID,
          _TEST_CAMPAIGN_ID,
          campaign_type,
          _TEST_AD_GROUP_ID,
          'YOUTUBE_VIDEO',
          'test-video-id',
          '_TEST_CRITERION_ID',
          False,
          False,
        ]
      ],
      column_names=_REPORT_COLUMN_NAMES_WITH_ALLOWLISTING,
    )
    exclusion_operations = excluder._create_exclusion_operations(
      report, placement_exclusion_lists
    )

    assert not exclusion_operations.placement_exclusion_operations
    assert not exclusion_operations.shared_set_creation_operations
    assert not exclusion_operations.campaign_set_association_operations
    assert (
      exclusion_operations.excludable_from_account_only[0][0].placement
      == 'test-video-id'
    )
