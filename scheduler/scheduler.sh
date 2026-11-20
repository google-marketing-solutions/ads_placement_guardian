#!/bin/bash
# wait some time before backend starts
sleep 10
CRON_FILE="/var/spool/cron/root"

if [ ! -f $CRON_FILE ]; then
	touch $CRON_FILE
	/usr/bin/crontab $CRON_FILE
fi
set -f
endpoint="${API_HOST:-localhost:5000}/api/tasks"
echo "task endpoint $endpoint"
curl_auth_args=()
curl_cron_auth=""
if [ -n "$APG_API_KEY" ]; then
	escaped_key="${APG_API_KEY//\\/\\\\}"
	escaped_key="${escaped_key//\"/\\\"}"
	(umask 077 && printf 'header = "Authorization: Bearer %s"\n' "$escaped_key" > /root/.apg_curlrc)
	curl_auth_args=(-K /root/.apg_curlrc)
	curl_cron_auth="-K /root/.apg_curlrc "
fi
while true; do
	curl -s "${curl_auth_args[@]}" -H "Accept: application/json" "$endpoint" -o task_list.json
	> crontab.txt
	jq -c '.[]' task_list.json | while read i; do
		task_id=`echo $i | jq -r ".task_id"`
		schedule=`echo $i | jq -r ".schedule"`
		echo "$schedule"
		if [ -z "$schedule" ]; then
			continue
		fi
		if [[ ! "$schedule" =~ "^[0-9]+$" ]]; then
			cron="$schedule"
		else
			hours=`expr $schedule / 24`
		fi
		if [ -z "$cron" ]; then
			if [[ "$hours" -eq 0 ]]; then
				cron="* /$schedule * * *"
			else
				cron="* * /$hours * *"
			fi
		fi
		echo "$cron" "curl -s ${curl_cron_auth}-X POST -H 'Content-Type: application/json' -d '{\"type\":\"SCHEDULED\"}' ${endpoint}/$task_id:run" >> crontab.txt
	done
	cp -f crontab.txt $CRON_FILE
	sleep 60
done
