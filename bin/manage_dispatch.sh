#!/bin/bash
curl -X POST -H "Accept: application/vnd.github+json" -H "Authorization: Bearer $1" "https://api.github.com/repos/acm-uic/manage/actions/workflows/ansible.yml/dispatches" -d '{"ref":"main"}'
