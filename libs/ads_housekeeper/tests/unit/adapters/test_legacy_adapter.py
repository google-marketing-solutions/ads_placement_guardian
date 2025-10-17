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

from googleads_housekeeper.adapters.legacy_adapter import TaskAdapter


def test_build_gads_filter_succeeds():
  task_adapter = TaskAdapter(
    {
      'gads_filter': '(metrics.ctr > 2) OR '
      '(metrics.video_views = 3 AND metrics.clicks > 20) OR '
      '(metrics.conversions_from_interactions_rate > 20)'
    }
  )

  actual_output = task_adapter._build_gads_filters()

  assert actual_output == (
    '(GOOGLE_ADS_INFO:ctr > 2) OR '
    '(GOOGLE_ADS_INFO:video_views = 3 AND GOOGLE_ADS_INFO:clicks > 20) OR '
    '(GOOGLE_ADS_INFO:conversions_from_interactions_rate > 20)'
  )
