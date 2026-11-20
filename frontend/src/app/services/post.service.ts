/**
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      https://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';

export interface ReturnPromise {
  response: string;
}

@Injectable({
  providedIn: 'root',
})
export class PostService {
  constructor(private httpClient: HttpClient) {}

  private apiPost<T>(url: string, params: string) {
    const headers = new HttpHeaders({
      'Content-Type': 'application/json; charset=utf-8',
      'X-Requested-With': 'XMLHttpRequest',
    });
    const cacheBuster = Date.now();
    return this.httpClient.post<ReturnPromise>(
      `/api/${url}?cb=${cacheBuster}`,
      params || '{}',
      { headers },
    );
  }

  private apiDelete<T>(url: string, params: string) {
    const headers = new HttpHeaders({
      'Content-Type': 'application/json; charset=utf-8',
      'X-Requested-With': 'XMLHttpRequest',
    });
    const cacheBuster = Date.now();
    const httpOptions = {
      headers,
      body: params || '{}',
    };
    return this.httpClient.delete<ReturnPromise>(
      `/api/${url}?cb=${cacheBuster}`,
      httpOptions,
    );
  }

  async preview_form(form_data_json: string) {
    return this.apiPost('placements/preview', form_data_json);
  }

  async run_manual_excluder(form_data_json: string) {
    return this.apiPost('placements/exclude', form_data_json);
  }

  async get_config() {
    return this.httpClient.get<ReturnPromise>('/api/configs');
  }

  async set_config(config_data: string) {
    return this.apiPost('configs', config_data);
  }

  async save_task(task_data: string) {
    return this.apiPost('tasks', task_data);
  }

  async get_tasks() {
    return this.httpClient.get<ReturnPromise>('/api/tasks');
  }

  async delete_task(task_id: string) {
    return this.apiDelete(`tasks/${task_id}`, '');
  }

  async run_task(task_id: string, task_data: string) {
    return this.apiPost(`tasks/${task_id}:run`, task_data);
  }

  async get_task(task_id: string) {
    return this.httpClient.get<ReturnPromise>(`/api/tasks/${task_id}`);
  }

  async migrate_old_tasks() {
    return this.httpClient.get<ReturnPromise>('/api/migrateOldTasks');
  }

  async get_customer_list() {
    return this.httpClient.get<ReturnPromise>('/api/accounts/customers');
  }

  async get_mcc_list() {
    return this.httpClient.get<ReturnPromise>('/api/accounts/mcc');
  }

  async refresh_mcc_list() {
    return this.apiPost('accounts/mcc', '');
  }

  async add_to_allowlist(channel_id: string) {
    return this.apiPost('placements/allowlist', channel_id);
  }

  async remove_from_allowlist(channel_id: string) {
    return this.apiDelete('placements/allowlist', channel_id);
  }

  async getBackendInfo() {
    return this.httpClient.get<ReturnPromise>('/api/info');
  }
}
